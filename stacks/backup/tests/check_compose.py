"""Assert source isolation and fail-closed configuration on the resolved model."""
import json
import re
import sys
model = json.load(open(sys.argv[1]))
assert set(model['services']) == {'duplicati'}
service = model['services']['duplicati']
assert re.fullmatch(r'duplicati/duplicati:latest@sha256:[0-9a-f]{64}', service['image'])
assert not service.get('privileged')
assert service.get('network_mode') != 'host'
assert not service.get('ports'), 'UI must be reached through NPM only'
assert set(service['networks']) == {'npm_proxy_backends', 'egress'}
assert not model['networks']['egress'].get('internal', False)
assert service['networks']['egress']['gw_priority'] == 1
mounts = {v['target']: v for v in service['volumes']}
assert set(mounts) == {'/data', '/source/quark-apps'}
from pathlib import Path
expected_script = (Path(__file__).resolve().parents[1] / 'quota-guard.sh').read_text()
assert service['environment']['QUARK_QUOTA_GUARD_SCRIPT'] == expected_script
assert service['command'][:2] == ['/bin/sh', '-ec']
assert 'exec duplicati-server' in service['command'][2]
assert mounts['/source/quark-apps']['source'] == '/mnt/tank/backups/apps'
assert mounts['/source/quark-apps']['read_only']
# Compose v2 omits false values from its rendered JSON; v5 preserves them.
assert not mounts['/source/quark-apps'].get('bind', {}).get('create_host_path', False)
assert mounts['/data']['source'] == '/mnt/services/quark/docker/duplicati'
assert service['logging']['options'] == {'max-size': '10m', 'max-file': '3'}
assert service['environment']['SETTINGS_ENCRYPTION_KEY']
assert service['environment']['DUPLICATI__WEBSERVICE_PASSWORD']
print('Backup source isolation and secret configuration passed')
