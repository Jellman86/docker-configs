#!/usr/bin/env python3
"""Start existing migrated containers through Dockhand only with verified mounts."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time
import urllib.parse
import urllib.request


def mounted_storage(config, run=subprocess.check_output):
    """Match actual mount UUIDs and all underlying hardware, not directory existence."""
    tree = json.loads(run(['lsblk', '-J', '-o', 'NAME,TYPE,UUID,SERIAL'], text=True))
    members = {}

    def visit(nodes, serial=None):
        for node in nodes:
            identity = node.get('serial') or serial
            if node.get('uuid') and identity:
                members.setdefault(node['uuid'], set()).add(identity)
            visit(node.get('children', []), identity)

    visit(tree['blockdevices'])
    for storage in config['storage']:
        raw = run(['findmnt', '-J', '-o', 'TARGET,FSTYPE,UUID,OPTIONS', '--target', storage['mount']], text=True)
        mounts = json.loads(raw).get('filesystems', [])
        if len(mounts) != 1:
            return False
        found = mounts[0]
        if (found.get('target'), found.get('fstype'), found.get('uuid')) != (
            storage['mount'], storage['fstype'], storage['uuid']
        ):
            return False
        if members.get(storage['uuid'], set()) != set(storage['serials']):
            return False
        if 'rw' not in found.get('options', '').split(','):
            return False
        if storage['fstype'] == 'btrfs':
            layout = run(['btrfs', 'filesystem', 'show', storage['mount']], text=True)
            if 'missing' in layout.lower():
                return False
            usage = run(['btrfs', 'filesystem', 'usage', '-b', storage['mount']], text=True)
            profiles = [line.split(':', 1)[0].strip() for line in usage.splitlines()
                        if line.startswith(('Data,', 'Metadata,', 'System,'))]
            if sorted(profiles) != ['Data,RAID1', 'Metadata,RAID1', 'System,RAID1']:
                return False
            run(['btrfs', 'device', 'stats', '-c', storage['mount']], text=True)
    return True


class Guard:
    def __init__(self, config):
        self.config = config
        self.stopping = False
        self.last_state = None
        self.retries = {}

    def api(self, path, method='GET', timeout=30):
        headers = {'Accept': 'application/json'}
        if self.config.get('token_file'):
            headers['Authorization'] = 'Bearer ' + Path(self.config['token_file']).read_text().strip()
        request = urllib.request.Request(self.config['dockhand'].rstrip('/') + path, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def containers(self):
        return {c['name']: c for c in self.api('/api/containers?env=' + str(self.config['environment']))}

    def stop_workloads(self):
        # This order is explicit so servers stop before their databases.
        failures = []
        containers = self.containers()
        for name in self.config['stop_order']:
            container = containers.get(name)
            if container and container['state'] == 'running':
                try:
                    result = self.api('/api/containers/' + urllib.parse.quote(container['id'], safe='') + '/stop?env=' + str(self.config['environment']), 'POST', timeout=7800)
                    if result.get('success') is not True:
                        raise RuntimeError('Dockhand stop failed')
                    print('Stopped ' + name, flush=True)
                except Exception:
                    failures.append(name)
                    print('Dockhand stop failed for ' + name, flush=True)
        if failures:
            raise RuntimeError('Some migrated workloads could not be stopped')

    def step(self):
        ready = Path(self.config['enabled_file']).is_file() and mounted_storage(self.config)
        if ready != self.last_state:
            print('Verified storage ready' if ready else 'Storage unavailable or migration not enabled; holding migrated workloads', flush=True)
            self.last_state = ready
        if not ready:
            self.stop_workloads()
            return
        containers = self.containers()
        for item in self.config['start_order']:
            name = item['name']
            container = containers.get(name)
            # Never deploy, pull, create containers, or bypass Git approval here.
            if not container or container['state'] == 'running':
                continue
            dependencies = [containers.get(dep) for dep in item.get('healthy_dependencies', [])]
            if any(not dep or dep['state'] != 'running' or dep.get('health') != 'healthy' for dep in dependencies):
                continue
            if time.monotonic() < self.retries.get(name, 0):
                continue
            # Recheck immediately before each start, including after an API call.
            if self.stopping or not Path(self.config['enabled_file']).is_file() or not mounted_storage(self.config):
                self.stop_workloads()
                return
            # A stopped VPN container has lost its network namespace. Stop its
            # configured dependents so their next start joins the new namespace.
            for dependent in item.get('stop_before_start', []):
                found = containers.get(dependent)
                if found and found['state'] == 'running':
                    result = self.api('/api/containers/' + urllib.parse.quote(found['id'], safe='') + '/stop?env=' + str(self.config['environment']), 'POST', timeout=120)
                    if result.get('success') is not True:
                        raise RuntimeError('Dockhand dependency stop failed')
            if self.stopping or not Path(self.config['enabled_file']).is_file() or not mounted_storage(self.config):
                self.stop_workloads()
                return
            result = self.api('/api/containers/' + urllib.parse.quote(container['id'], safe='') + '/start?env=' + str(self.config['environment']), 'POST', timeout=60)
            self.retries[name] = time.monotonic() + 60
            if result.get('success') is not True:
                raise RuntimeError('Dockhand start failed for ' + name)
            print('Started ' + name, flush=True)
            containers = self.containers()

    def run(self):
        def stop(_signal, _frame):
            self.stopping = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while not self.stopping:
            try:
                self.step()
            except Exception as error:
                # Log only error type: API bodies and token values never reach logs.
                print('Storage guard check failed: ' + type(error).__name__, flush=True)
                try:
                    self.stop_workloads()
                except Exception as stop_error:
                    print('Dockhand stop unavailable: ' + type(stop_error).__name__, flush=True)
            for _ in range(10):
                if self.stopping:
                    break
                time.sleep(1)
        self.stop_workloads()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/quark-storage-workloads.json')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if args.check:
        raise SystemExit(0 if mounted_storage(config) else 1)
    Guard(config).run()


if __name__ == '__main__':
    main()
