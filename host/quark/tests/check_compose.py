"""Check the actual merged Compose model, not only the small extends files."""
import json
from pathlib import Path
import sys

for source in sys.argv[1:]:
    model = json.loads(Path(source).read_text())
    for name, service in model['services'].items():
        assert service['restart'] == 'no', (name, 'unsafe restart policy')
        assert service.get('image'), (name, 'extends lost base service')
    if 'optimisarr' in model['services']:
        app = model['services']['optimisarr']
        assert {'default', 'arr_stack_brg', 'general_brg'} <= set(app['networks'])
        plex = model['services']['plex']
        assert not [v for v in plex['volumes'] if v['target'] == '/transcode'], 'Plex transcodes in /dev/shm'
        assert 1024 ** 3 <= int(plex['shm_size']) <= 8 * 1024 ** 3, 'RAM transcode must stay capped'
    if 'qbittorrent' in model['services']:
        qbit = model['services']['qbittorrent']
        assert qbit['network_mode'] == 'service:gluetun'
        assert qbit['depends_on']['gluetun']['condition'] == 'service_healthy'
        assert model['networks']['vpn_stack_brg'].get('external', False)
        assert 'gluetun-guard' not in model['services'], 'Ungated repair watchdog must be excluded from normal deployment'
        for name in ['gluetun', 'radarr', 'sonarr', 'prowlarr', 'cleanuparr', 'seerr']:
            assert 'npm_proxy_backends' in model['services'][name]['networks'], (name, 'unreachable from Quark NPM')
            assert model['services'][name]['networks']['vpn_stack_brg']['gw_priority'] == 1
    if 'immich-server' in model['services']:
        assert 'immich-machine-learning' not in model['services']
        mount = model['services']['immich-database']['volumes'][0]
        assert mount['source'] == '/mnt/services/docker/immich/postgres18'
        assert mount['target'] == '/var/lib/postgresql'
print('Merged Quark Compose models verified')
