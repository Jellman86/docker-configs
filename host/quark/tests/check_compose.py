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
        assert [v['source'] for v in plex['volumes'] if v['target'] == '/transcode'] == ['/mnt/services/plex-transcode']
    if 'qbittorrent' in model['services']:
        qbit = model['services']['qbittorrent']
        assert qbit['network_mode'] == 'service:gluetun'
        assert qbit['depends_on']['gluetun']['condition'] == 'service_healthy'
        assert not model['networks']['vpn_stack_brg'].get('external', False)
        assert 'gluetun-guard' not in model['services'], 'Ungated repair watchdog must be excluded from normal deployment'
    if 'immich-server' in model['services']:
        assert 'immich-machine-learning' not in model['services']
        assert model['services']['immich-database']['volumes'][0]['source'] == '/mnt/services/docker/immich/postgres'
print('Merged Quark Compose models verified')
