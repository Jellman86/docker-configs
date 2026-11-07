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
assert len(service['ports']) == 1
assert service['ports'][0]['host_ip'] == '100.122.27.35'
mounts = {v['target']: v for v in service['volumes']}
assert set(mounts) == {'/data', '/source/quark-apps'}
assert mounts['/source/quark-apps']['source'] == '/mnt/tank/backups/apps'
assert mounts['/source/quark-apps']['read_only']
assert not mounts['/source/quark-apps']['bind']['create_host_path']
assert mounts['/data']['source'] == '/mnt/services/quark/docker/duplicati'
assert service['logging']['options'] == {'max-size': '10m', 'max-file': '3'}
assert service['environment']['SETTINGS_ENCRYPTION_KEY']
assert service['environment']['DUPLICATI__WEBSERVICE_PASSWORD']
print('Backup source isolation and secret configuration passed')
