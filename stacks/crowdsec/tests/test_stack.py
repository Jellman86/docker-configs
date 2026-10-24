from pathlib import Path
import json
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / 'stacks/crowdsec'


class CrowdSecContract(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((STACK / 'compose.yaml').read_text())
        self.services = self.compose['services']

    def test_no_host_ports_and_ingress_untouched(self):
        for name, service in self.services.items():
            if name == 'crowdsec':
                self.assertEqual(service['ports'], ['192.168.213.102:5514:5514/udp'])
            else:
                self.assertNotIn('ports', service, name)
            self.assertNotIn('general_brg', service.get('networks', {}), name)
        ui = self.services['crowdsec-web-ui']
        self.assertIn('npm_proxy_backends', ui['networks'])
        self.assertNotIn('npm_proxy_backends', self.services['crowdsec']['networks'])

    def test_npm_logs_are_read_only(self):
        mounts = {v['target']: v for v in self.services['crowdsec']['volumes'] if isinstance(v, dict)}
        logs = mounts['/var/log/npm']
        self.assertTrue(logs['read_only'])
        self.assertEqual(logs['source'], '/mnt/services/quark/docker/nginx-proxy-manager/data/logs')
        self.assertFalse(logs['bind']['create_host_path'])
        acquis = yaml.safe_load((STACK / 'acquis.d/npm.yaml').read_text())
        self.assertEqual(acquis['labels']['type'], 'nginx-proxy-manager')
        self.assertTrue(all(f.startswith('/var/log/npm/') for f in acquis['filenames']))

    def test_app_logs_are_read_only_log_directories(self):
        mounts = [v for v in self.services['crowdsec']['volumes']
                  if isinstance(v, dict) and v['target'].startswith('/var/log/apps/')]
        self.assertEqual({m['target'].rsplit('/', 1)[1] for m in mounts},
                         {'jellyfin', 'seerr', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent'})
        for m in mounts:
            self.assertTrue(m['read_only'], m)
            self.assertFalse(m['bind']['create_host_path'], m)
            self.assertRegex(m['source'], r'/logs?$')
        acquired = set()
        for f in (STACK / 'acquis.d').glob('*.yaml'):
            acquis = yaml.safe_load(f.read_text())
            acquired.update(acquis.get('filenames', []))
        for m in mounts:
            self.assertTrue(any(name.startswith(m['target'] + '/') for name in acquired), m['target'])

    def test_unifi_syslog_listener_matches_published_port(self):
        acquis = yaml.safe_load((STACK / 'acquis.d/unifi.yaml').read_text())
        self.assertEqual(acquis['source'], 'syslog')
        self.assertEqual(acquis['labels']['type'], 'unifi')
        self.assertEqual(acquis['listen_port'], 5514)
        self.assertIn('crowdsecurity/unifi', self.services['crowdsec']['environment']['COLLECTIONS'])

    def test_unifi_hostname_repair_parser_runs_first(self):
        mounts = {m.split(':')[0]: m.split(':')[1] for m in self.services['crowdsec']['volumes'] if isinstance(m, str)}
        target = mounts['./parsers/quark-unifi-syslog-host.yaml']
        self.assertEqual(target, '/etc/crowdsec/parsers/s00-raw/a-quark-unifi-syslog-host.yaml')
        parser = yaml.safe_load((STACK / 'parsers/quark-unifi-syslog-host.yaml').read_text())
        self.assertEqual(parser['onsuccess'], 'next_stage')
        self.assertNotIn('debug', parser)
        self.assertFalse((STACK / 'scenarios').exists())

    def test_dashboard_requires_login_and_secret(self):
        ui = self.services['crowdsec-web-ui']
        env = ui['environment']
        self.assertEqual(env['CONFIG_AUTH_ENABLED'], 'true')
        self.assertIn(':?', env['CONFIG_INSTANCE_LAPI_AUTH_PASSWORD'])
        self.assertEqual(ui['user'], '1000:1000')
        self.assertEqual(ui['cap_drop'], ['ALL'])

    def test_machine_registration_is_idempotent_one_shot(self):
        job = self.services['web-ui-machine']
        self.assertEqual(job['restart'], 'no')
        self.assertEqual(job['network_mode'], 'none')
        self.assertIn('--force', job['command'][0])
        self.assertIn('-f /dev/null', job['command'][0])
        ui_deps = self.services['crowdsec-web-ui']['depends_on']
        self.assertEqual(ui_deps['web-ui-machine']['condition'], 'service_completed_successfully')

    def test_only_dashboard_is_lapi_trusted(self):
        local = yaml.safe_load((STACK / 'config.yaml.local').read_text())
        ui_ip = self.services['crowdsec-web-ui']['networks']['lapi']['ipv4_address']
        self.assertEqual(set(local['api']['server']['trusted_ips']), {'127.0.0.1', '::1', ui_ip})

    def test_home_network_is_never_banned(self):
        wl = yaml.safe_load((STACK / 'parsers/quark-private-whitelist.yaml').read_text())
        for cidr in ['192.168.0.0/16', '172.16.0.0/12', '100.64.0.0/10']:
            self.assertIn(cidr, wl['whitelist']['cidr'])

    def test_recovery_selection(self):
        backup = json.loads((ROOT / 'host/quark/app-backup.example.json').read_text())
        dirs = backup['config_directories']
        self.assertIn('/mnt/services/quark/docker/crowdsec/config', dirs)
        self.assertIn('/mnt/services/quark/docker/crowdsec/web-ui', dirs)
        self.assertNotIn('/mnt/services/quark/docker/crowdsec/data', dirs)


if __name__ == '__main__':
    unittest.main()
