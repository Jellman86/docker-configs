#!/usr/bin/env python3
"""Small online settings/database backups. Never stops or deploys applications."""
import datetime
import fcntl
import fnmatch
import json
import os
from pathlib import Path
from contextlib import closing
import uuid
import re
import resource
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import tempfile
import time

GIB = 1024**3
# Three archives, one candidate and one staging tree: at most 20 GiB of data.
MAX_GENERATION = 4 * GIB
EXCLUDED = {'cache', '.cache', 'logs', 'log', 'backups', 'archive', 'models',
            'model_cache', 'media_cache', 'recordings', 'clips', 'captures',
            'attachments', 'audio_cache', 'image_cache', 'images', 'tts', 'deps',
            '.npm', '.local', 'node_modules', 'lazy-packages', 'sandboxes',
            'mediacover', 'metadata', 'media', 'sentry', 'asp', 'xdg', '.git', 'yawamf-eval'}
MEDIA = {'.mp4', '.mkv', '.ts', '.wav', '.flac', '.mp3', '.ogg', '.jpg', '.jpeg', '.png', '.webp'}


def included(relative):
    parts = relative.parts
    if parts and parts[0] == 'letsencrypt':
        return True  # Certificate archives and live symlinks are recovery data.
    return not (any(p.lower() in EXCLUDED or 'backup-' in p.lower() or 'loadtest-' in p.lower() for p in parts)
                or any(x in relative.name.lower() for x in ['.bak', '.backup', '.malformed-backup', '.pre-migration-'])
                or relative.name.endswith(('-wal', '-shm', '.log', '.lock', '.pid', '.sock'))
                or relative.suffix.lower() in MEDIA)


def retained_archives(root):
    return sorted(p for p in root.iterdir() if p.is_file() and not p.is_symlink()
                  and re.fullmatch(r'apps-\d{8}T\d{6}Z\.tar\.gz', p.name))


def sqlite_copy(source, destination):
    deadline = time.monotonic() + 120
    def progress(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise TimeoutError('SQLite backup timed out')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=256, progress=progress, sleep=.05)
            if dst.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('Database recovery copy did not pass quick_check')


def plex_copy(source, destination, limit):
    """Plex's custom tokenizer requires its bundled SQLite, not host SQLite."""
    c = json.loads(subprocess.check_output(['docker', 'inspect', 'plex'], text=True))[0]
    temporary = '/tmp/app-backup-' + uuid.uuid4().hex + '.db'
    host_temporary = Path('/proc') / str(c['State']['Pid']) / 'root' / temporary.lstrip('/')
    live = '/config/' + str(source.relative_to('/mnt/services/docker/pms'))
    binary = '/usr/lib/plexmediaserver/Plex SQLite'
    try:
        subprocess.run(['docker', 'exec', '-u', '568:568', 'plex', 'sh', '-c',
                        'ulimit -f "$1"; shift; exec "$@"', 'sh', str(max(1,limit//1024)),
                        binary, live, ".backup '" + temporary + "'"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=True)
        result = subprocess.check_output(['docker', 'exec', '-u', '568:568', 'plex', binary,
                                          temporary, 'PRAGMA quick_check;'], text=True, timeout=120)
        if result.strip() != 'ok':
            raise RuntimeError('Plex recovery database check failed')
        shutil.copyfile(host_temporary, destination)
    finally:
        host_temporary.unlink(missing_ok=True)


def mount_check(config):
    for path, expected in config['mount_uuids'].items():
        actual = subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '-T', path], text=True).strip()
        if actual != expected:
            raise RuntimeError('Required backup filesystem is missing')


def backup(config):
    mount_check(config)
    root = Path(config['destination'])
    if root != Path('/mnt/tank/backups/apps') or root.is_symlink():
        raise RuntimeError('Unexpected backup destination')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    # Refuse unbounded leftovers from interrupted runs rather than accumulating them.
    for p in root.glob('.working-*'):
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
    for p in root.glob('.candidate-*.tar.gz'):
        if p.is_file() and not p.is_symlink():
            p.unlink()
    if sum(p.stat().st_size for p in retained_archives(root)) > 3 * MAX_GENERATION:
        raise RuntimeError('Existing archives exceed the configured allowance')
    if shutil.disk_usage(root).free < 2 * MAX_GENERATION:
        raise RuntimeError('Not enough free space for a bounded backup')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    candidate = root / ('.candidate-' + stamp + '.tar.gz')
    used = 0
    databases = 0
    copied = set()
    with tempfile.TemporaryDirectory(prefix='.working-', dir=root) as directory:
        stage = Path(directory)
        def copy(source):
            nonlocal used, databases
            source = Path(source)
            if str(source) in copied or not (source.is_file() or source.is_symlink()):
                return
            copied.add(str(source))
            remaining = MAX_GENERATION - used
            if source.lstat().st_size > remaining:
                raise RuntimeError('Settings/database generation exceeds 4 GiB')
            destination = stage / 'files' / source.relative_to('/')
            destination.parent.mkdir(parents=True, exist_ok=True)
            resource.setrlimit(resource.RLIMIT_FSIZE, (max(1, remaining), MAX_GENERATION))
            try:
                if source.is_symlink():
                    destination.symlink_to(source.readlink())
                else:
                    with source.open('rb') as f:
                        is_sqlite = f.read(16) == b'SQLite format 3\x00'
                    if is_sqlite:
                        (plex_copy(source, destination, remaining) if source.is_relative_to('/mnt/services/docker/pms') else sqlite_copy(source, destination))
                        databases += 1
                    else:
                        shutil.copyfile(source, destination)
                shutil.copystat(source, destination, follow_symlinks=False)
                st = source.lstat()
                os.chown(destination, st.st_uid, st.st_gid, follow_symlinks=False)
                used += destination.lstat().st_size
                # Preserve app directory ownership/modes for a usable restore.
                for parent in source.parents:
                    if parent == Path('/'):
                        break
                    target = stage / 'files' / parent.relative_to('/')
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.copystat(parent, target)
                    st = parent.stat()
                    os.chown(target, st.st_uid, st.st_gid)
            finally:
                resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_GENERATION, MAX_GENERATION))
        for directory in config['config_directories']:
            directory = Path(directory)
            if not directory.is_dir():
                raise RuntimeError('Configured application directory is missing')
            for current, dirs, files in os.walk(directory, followlinks=False):
                dirs[:] = [d for d in dirs if included((Path(current)/d).relative_to(directory))]
                for name in files:
                    source = Path(current)/name
                    if included(source.relative_to(directory)):
                        copy(source)
        for pattern in config['files']:
            import glob
            matches = glob.glob(pattern)
            if not matches:
                raise RuntimeError('Required recovery file is missing')
            for path in matches:
                copy(Path(path))
        # Logical PostgreSQL dump is consistent while Immich remains online.
        c = json.loads(subprocess.check_output(['docker', 'inspect', 'immich-database'], text=True))[0]
        env = dict(v.split('=', 1) for v in c['Config']['Env'])
        resource.setrlimit(resource.RLIMIT_FSIZE, (max(1, MAX_GENERATION-used), MAX_GENERATION))
        try:
            with (stage/'immich.dump').open('wb') as output:
                subprocess.run(['docker', 'exec', 'immich-database', 'pg_dump', '-U', env['POSTGRES_USER'],
                                '-Fc', '--no-owner', '--no-privileges', env['POSTGRES_DB']], stdout=output,
                               stderr=subprocess.DEVNULL, timeout=300, check=True)
        finally:
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_GENERATION, MAX_GENERATION))
        used += (stage/'immich.dump').stat().st_size
        with (stage/'smbpasswd-private.txt').open('wb') as output:
            subprocess.run(['pdbedit', '-L', '-w'], stdout=output, stderr=subprocess.DEVNULL, check=True)
        manifest = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'online_sqlite_backups_checked': databases, 'settings_files': len(copied),
                    'staged_data_bytes': used, 'postgresql': 'consistent logical pg_dump',
                    'coverage': 'Application settings/databases and selected host files. Other live files are best-effort copies.',
                    'excluded': 'Media/photos/VMs, recordings, models, caches and old backups. Not an independent backup.'}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        try:
            with tarfile.open(candidate, 'w:gz') as archive:
                archive.add(stage, arcname='apps', recursive=True)
            with tarfile.open(candidate, 'r:gz') as archive:
                json.load(archive.extractfile('apps/manifest.json'))
            mount_check(config)
            # Candidate verified first. Rotate only our dated archives, preserving prior copies on failure.
            old = retained_archives(root)
            for path in old[:-2]:
                path.unlink()
            final = root / ('apps-' + stamp + '.tar.gz')
            candidate.replace(final)
        finally:
            candidate.unlink(missing_ok=True)
    return {**manifest, 'stage': 'online-config-database-backup-ready', 'archive': str(final),
            'archives_kept': len(retained_archives(root)), 'maximum_archives': 3,
            'maximum_generation_bytes': MAX_GENERATION, 'maximum_routine_data_bytes': 20 * GIB}


def main():
    os.umask(0o077)
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_GENERATION, MAX_GENERATION))
    config = json.loads(Path('/etc/quark-app-backup.json').read_text())
    status = Path('/mnt/services/host/app-backup/status.json')
    status.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open('/run/lock/quark-app-backup.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = backup(config)
        except Exception as error:
            result = {'stage': 'online-config-backup-failed', 'error_type': type(error).__name__, 'error': str(error)[:200]}
            status.write_text(json.dumps(result, indent=2)+'\n')
            raise SystemExit(1) from None
        status.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ['coverage','excluded']}), flush=True)


if __name__ == '__main__':
    main()
