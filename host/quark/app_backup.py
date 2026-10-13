#!/usr/bin/env python3
"""Consistent app recovery snapshots. All container lifecycle uses Dockhand."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import time
import urllib.request


def write_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


def retention_plan(existing, current_bytes, next_bytes, maximum_bytes, keep=7, minimum=2):
    """Conservatively count shared extents twice and reserve the next snapshot."""
    if keep < minimum or minimum < 1 or maximum_bytes < 1:
        raise ValueError('Invalid backup retention bounds')
    retained = list(existing)
    removed = []
    projected = current_bytes + 2 * next_bytes
    while retained and (len(retained) >= keep or projected > maximum_bytes):
        if len(retained) <= minimum:
            break
        old, size = retained.pop(0)
        removed.append(old)
        projected -= size
    if projected > maximum_bytes:
        raise RuntimeError('Next backup exceeds byte budget; existing recovery copies kept')
    return removed


def sqlite_backup(source, destination):
    """Use SQLite's online backup API, including committed WAL transactions."""
    temporary = destination.with_name(destination.name + '.backup-tmp')
    temporary.unlink(missing_ok=True)
    deadline = time.monotonic() + 120

    def progress(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise TimeoutError('Online SQLite backup exceeded its deadline')

    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(temporary) as dst:
            src.backup(dst, pages=256, progress=progress, sleep=.05)
            if dst.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('SQLite recovery copy failed integrity check')
    st = source.stat()
    os.chown(temporary, st.st_uid, st.st_gid)
    os.chmod(temporary, st.st_mode & 0o777)
    for suffix in ['', '-wal', '-shm']:
        destination.with_name(destination.name + suffix).unlink(missing_ok=True)
    temporary.replace(destination)


class Backup:
    def __init__(self, config):
        self.config = config
        self.root = Path(config['destination'])
        self.current = self.root / 'current'
        self.state = Path(config['state_file'])
        self.log = None
        self.running = []
        self.guard_enabled = False
        self.smb_active = False
        self.quiescing = False

    def event(self, stage, **extra):
        write_json(self.state, {'stage': stage, 'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra})
        print(stage, flush=True)

    def run(self, command, **kwargs):
        return subprocess.run(command, check=True, **kwargs)

    def api(self, path, method='GET', timeout=60):
        headers = {'Accept': 'application/json'}
        if self.config.get('token_file'):
            headers['Authorization'] = 'Bearer ' + Path(self.config['token_file']).read_text().strip()
        req = urllib.request.Request(self.config['dockhand'].rstrip('/') + path, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)

    def containers(self):
        return {c['name']: c for c in self.api('/api/containers?env=' + str(self.config['environment']))}

    def lifecycle(self, name, action):
        c = self.containers().get(name)
        if not c:
            raise RuntimeError('Required app container is missing')
        if (action == 'stop' and c['state'] != 'running') or (action == 'start' and c['state'] == 'running'):
            return
        result = self.api('/api/containers/' + c['id'] + '/' + action + '?env=' + str(self.config['environment']), 'POST', timeout=7800 if action == 'stop' else 120)
        if result.get('success') is not True:
            raise RuntimeError('Dockhand lifecycle request failed')

    def storage(self, capacity=True):
        self.run(['/usr/local/sbin/quark-storage-workloads', '--check'], stdout=subprocess.DEVNULL)
        for path, expected in self.config['mount_uuids'].items():
            actual = subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '-T', path], text=True).strip()
            if actual != expected:
                raise RuntimeError('Backup source or destination mount changed')
        if not self.root.is_relative_to(Path('/mnt/tank/backups')) or self.root == Path('/mnt/tank/backups'):
            raise RuntimeError('Unsafe backup destination')
        if self.root.is_symlink() or self.current.is_symlink():
            raise RuntimeError('Symlink backup destination rejected')
        stat = os.statvfs('/mnt/tank')
        if capacity and stat.f_bavail * stat.f_frsize < self.config.get('minimum_free_bytes', 100 * 1024**3):
            raise RuntimeError('Insufficient backup space')

    def copy(self, source, destination, excludes=(), verify=False, live=False):
        args = ['rsync', '-aHAXSx', '--numeric-ids', '--delete']
        args += ['--exclude=' + x for x in excludes]
        if verify:
            args += ['--checksum', '--dry-run', '--itemize-changes', '--out-format=%i %n%L']
            p = subprocess.run(args + [str(source) + '/', str(destination) + '/'], capture_output=True, text=True)
            if p.returncode or p.stdout.strip() or p.stderr.strip():
                raise RuntimeError('Cold backup checksum comparison failed')
        else:
            destination.mkdir(parents=True, exist_ok=True)
            # Bound write rate and check the conservative total including temporary files.
            # Four GiB of headroom permits detection well before the configured budget.
            args += ['--bwlimit=40m']
            with subprocess.Popen(args + [str(source) + '/', str(destination) + '/'], stdout=self.log, stderr=self.log) as process:
                try:
                    while process.poll() is None:
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            limit = self.config['maximum_backup_bytes'] - self.config.get('budget_headroom_bytes', 4 * 1024**3)
                            if self.usage(self.root) > limit:
                                raise RuntimeError('Backup byte budget reached during copy')
                    if process.returncode not in ([0, 24] if live else [0]):
                        raise RuntimeError('Application file copy failed')
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()

    def usage(self, path):
        # Counting shared snapshot extents separately deliberately overestimates storage.
        # Do not use -x: Btrfs gives nested working/snapshot subvolumes distinct st_dev.
        return int(subprocess.check_output(['du', '-s', '--apparent-size', '--count-links', '--block-size=1', str(path)], text=True).split()[0])

    def budget(self):
        estimate = 1024**3  # Host files, private inventory and small growth allowance.
        for entry in self.config['sources'] + self.config['online_management']:
            args = ['rsync', '-aHAXSx', '--numeric-ids', '--dry-run', '--stats', '--delete']
            args += ['--exclude=' + x for x in entry.get('excludes', [])]
            p = subprocess.run(args + [entry['path'] + '/', str(self.current / 'files' / entry['name']) + '/'], capture_output=True, text=True, check=True)
            match = re.search(r'Total file size:\s+([\d,]+) bytes', p.stdout)
            if not match:
                raise RuntimeError('Cannot estimate the next backup size')
            estimate += int(match.group(1).replace(',', ''))
        snapshots = self.root / 'snapshots'
        existing = []
        if snapshots.exists():
            existing = [(p, self.usage(p)) for p in sorted(snapshots.iterdir())
                        if re.fullmatch(r'backup-\d{8}T\d{6}Z', p.name) and not p.is_symlink()
                        and (p / 'recovery-manifest.json').is_file()]
        # Exclude the working copy, which the next copy replaces. Snapshot sizes stay.
        used = self.usage(self.root) - self.usage(self.current)
        maximum = self.config['maximum_backup_bytes'] - self.config.get('budget_headroom_bytes', 4 * 1024**3)
        remove = retention_plan(existing, used, estimate, maximum,
                                self.config.get('keep_snapshots', 7), self.config.get('minimum_snapshots', 2))
        for old in remove:
            self.run(['btrfs', 'subvolume', 'delete', str(old)], stdout=subprocess.DEVNULL)
        write_json(self.root / 'budget.json', {'estimated_next_bytes': estimate,
                   'maximum_backup_bytes': self.config['maximum_backup_bytes'],
                   'maximum_snapshot_count': self.config.get('keep_snapshots', 7),
                   'accounting': 'Conservative apparent size, shared extents counted separately',
                   'pruned_verified_snapshots': [p.name for p in remove]})

    def copies(self, verify=False, live=False):
        for source in self.config['sources']:
            self.storage()
            src = Path(source['path'])
            relative = Path(source['name'])
            if relative.is_absolute() or '..' in relative.parts or src.is_symlink() or not src.is_dir():
                raise RuntimeError('Unsafe or unavailable backup source')
            self.copy(src, self.current / 'files' / relative, source.get('excludes', []), verify, live)

    def quiesce(self):
        self.running = [n for n, c in self.containers().items() if c['state'] == 'running']
        marker = Path(self.config['guard_enabled_file'])
        self.guard_enabled = marker.is_file()
        self.smb_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'smb.service']).returncode == 0
        self.quiescing = True
        # Record recovery instructions before stopping anything.
        write_json(self.root / 'interrupted-maintenance.json', {'running': self.running,
                   'guard_enabled': self.guard_enabled, 'smb_active': self.smb_active})
        marker.unlink(missing_ok=True)
        self.run(['systemctl', 'stop', 'quark-storage-workloads.service'])
        for name in self.config['extra_stop_order']:
            if name in self.running:
                self.lifecycle(name, 'stop')
        if self.smb_active:
            self.run(['systemctl', 'stop', 'smb.service'])
        current = self.containers()
        guarded = json.loads(Path(self.config['guard_config']).read_text())['stop_order']
        stopped = set(guarded) | set(self.config['extra_stop_order'])
        if any(current.get(n, {}).get('state') == 'running' for n in stopped):
            raise RuntimeError('An application writer did not stop')

    def recover(self):
        """Best effort for every app, even when one start fails. Preserve recovery record."""
        if not self.quiescing:
            return
        failures = []
        for name in self.config['extra_start_order']:
            if name in self.running:
                try:
                    self.storage(capacity=False)
                    self.lifecycle(name, 'start')
                except Exception:
                    failures.append(name)
        if self.guard_enabled:
            try:
                self.storage(capacity=False)
                Path(self.config['guard_enabled_file']).touch(mode=0o600)
                self.run(['systemctl', 'start', 'quark-storage-workloads.service'])
            except Exception:
                failures.append('storage guard')
        if self.smb_active:
            try:
                self.storage(capacity=False)
                self.run(['systemctl', 'start', 'smb.service'])
            except Exception:
                failures.append('SMB')
        if failures:
            raise RuntimeError('Application recovery needs attention')
        for _ in range(120):
            current = self.containers()
            if all(current.get(n, {}).get('state') == 'running' and current[n].get('health') in [None, '', 'none', 'healthy'] for n in self.running):
                self.root.joinpath('interrupted-maintenance.json').unlink(missing_ok=True)
                self.quiescing = False
                return
            time.sleep(5)
        raise RuntimeError('Application recovery did not reach healthy state')

    def management(self):
        """Keep management available; use online SQLite copies for their databases."""
        for entry in self.config['online_management']:
            src = Path(entry['path'])
            dest = self.current / 'files' / entry['name']
            # SQLite files and sidecars are always replaced from the backup API.
            self.copy(src, dest, ['*.db', '*.db-wal', '*.db-shm', '*.sqlite', '*.sqlite-wal', '*.sqlite-shm'], live=True)
            databases = []
            for db in src.rglob('*'):
                if db.is_file() and db.suffix in ['.db', '.sqlite']:
                    with db.open('rb') as f:
                        if f.read(16) != b'SQLite format 3\x00':
                            continue
                    out = dest / db.relative_to(src)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    sqlite_backup(db, out)
                    databases.append(str(db.relative_to(src)))
            if not databases:
                raise RuntimeError('Expected management SQLite database is missing')

    def manifest(self):
        dest = self.current / 'host'
        dest.mkdir(mode=0o700, exist_ok=True)
        for file in self.config['host_files']:
            source = Path(file)
            if not source.exists():
                raise RuntimeError('Required host recovery configuration is missing')
            target = dest / source.relative_to('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            self.run(['rsync', '-aHAX', str(source), str(target)], stdout=self.log, stderr=self.log)
        # Private restore inventory, including image IDs, variables and mount paths.
        ids = subprocess.check_output(['docker', 'ps', '-aq'], text=True).splitlines()
        inventory = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True))
        write_json(dest / 'container-inspect-private.json', inventory)
        write_json(self.current / 'recovery-manifest.json', {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'cold_sources_checksum_verified': True, 'management_sqlite_online_backups_checked': True,
                   'coverage': self.config['sources'], 'exclusions': self.config['excluded_rebuildable_data'],
                   'independent_backup': False, 'note': 'Apps SSD recovery copy on the same host media mirror. Keep the independent migration backup and arrange ongoing off-host backup.'})

    def execute(self):
        self.storage()
        if self.root.joinpath('interrupted-maintenance.json').exists():
            raise RuntimeError('Inspect and recover an interrupted backup before another run')
        if self.config.get('wait_for_cold_backup_state'):
            stage = json.loads(Path(self.config['wait_for_cold_backup_state']).read_text())['stage']
            if stage != 'retained-cold-app-backup-checksum-verified':
                self.event('deferred-until-initial-cold-backup-verified')
                return
        scrub = subprocess.check_output(['btrfs', 'scrub', 'status', '/mnt/tank'], text=True)
        if re.search(r'Status:\s+running', scrub):
            self.event('deferred-while-media-scrub-running')
            return
        with urllib.request.urlopen('http://127.0.0.1:8787/api/queue/status', timeout=15) as response:
            if json.load(response)['runningJobs']:
                self.event('deferred-while-encoding-active')
                return
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)
        if not self.current.exists():
            self.run(['btrfs', 'subvolume', 'create', str(self.current)], stdout=subprocess.DEVNULL)
        self.run(['btrfs', 'subvolume', 'show', str(self.current)], stdout=subprocess.DEVNULL)
        self.budget()
        log_path = self.root / 'last-run-private.log'
        with log_path.open('w') as self.log:
            log_path.chmod(0o600)
            self.event('precopying-live-application-files')
            self.copies(live=True)
            try:
                self.event('quiescing-applications-for-consistent-backup')
                self.quiesce()
                self.event('copying-and-checksum-verifying-cold-applications')
                self.copies()
                self.copies(verify=True)
                self.management()
                self.manifest()
                self.storage()
                stamp = datetime.datetime.now(datetime.timezone.utc).strftime('backup-%Y%m%dT%H%M%SZ')
                snapshots = self.root / 'snapshots'
                snapshots.mkdir(mode=0o700, exist_ok=True)
                snapshot = snapshots / stamp
                self.run(['btrfs', 'subvolume', 'snapshot', '-r', str(self.current), str(snapshot)], stdout=subprocess.DEVNULL)
                self.run(['sync', '-f', str(snapshot)])
            finally:
                self.event('restoring-application-services-after-backup')
                self.recover()
        self.event('application-backup-verified-and-services-healthy', snapshot=str(snapshot))
        # Prune only our dated, verified recovery snapshots. Never migration copies.
        snapshots = sorted(p for p in snapshots.iterdir() if re.fullmatch(r'backup-\d{8}T\d{6}Z', p.name))
        for old in snapshots[:-self.config.get('keep_snapshots', 7)]:
            if (old / 'recovery-manifest.json').is_file():
                self.run(['btrfs', 'subvolume', 'delete', str(old)], stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/quark-app-backup.json')
    args = parser.parse_args()
    os.umask(0o077)
    os.environ['LC_ALL'] = 'C'
    config = json.loads(Path(args.config).read_text())
    with open('/run/lock/quark-app-backup.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = Backup(config)

        def interrupted(_signum, _frame):
            raise InterruptedError('Backup interrupted; restoring application services')

        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        try:
            backup.execute()
        except Exception as error:
            backup.event('application-backup-needs-attention', error_type=type(error).__name__)
            raise SystemExit(1) from None


if __name__ == '__main__':
    main()
