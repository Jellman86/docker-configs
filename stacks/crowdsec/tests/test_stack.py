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
        self.engine = self.services['crowdsec']
        self.binds = {m.split(':')[0]: m.split(':')[1] for m in self.engine['volumes'] if isinstance(m, str)}

    def test_engine_only_with_lan_syslog_port(self):
        self.assertEqual(set(self.services), {'crowdsec'})
        self.assertEqual(self.engine['ports'], ['192.168.213.102:5514:5514/udp'])
        self.assertNotIn('networks', self.engine)
        self.assertNotIn('networks', self.compose)

    def test_npm_logs_are_read_only(self):
        mounts = {v['target']: v for v in self.engine['volumes'] if isinstance(v, dict)}
        logs = mounts['/var/log/npm']
        self.assertTrue(logs['read_only'])
        self.assertEqual(logs['source'], '/mnt/services/quark/docker/nginx-proxy-manager/data/logs')
        self.assertFalse(logs['bind']['create_host_path'])
        acquis = yaml.safe_load((STACK / 'acquis.d/npm.yaml').read_text())
        self.assertEqual(acquis['labels']['type'], 'nginx-proxy-manager')
        self.assertTrue(all(f.startswith('/var/log/npm/') for f in acquis['filenames']))

    def test_app_logs_are_read_only_log_directories(self):
        mounts = [v for v in self.engine['volumes']
                  if isinstance(v, dict) and v['target'].startswith('/var/log/apps/')]
        self.assertEqual({m['target'].rsplit('/', 1)[1] for m in mounts},
                         {'jellyfin', 'seerr', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent'})
        for m in mounts:
            self.assertTrue(m['read_only'], m)
            self.assertFalse(m['bind']['create_host_path'], m)
            self.assertRegex(m['source'], r'/logs?$')
        acquired = set()
        for f in (STACK / 'acquis.d').glob('*.yaml'):
            acquired.update(yaml.safe_load(f.read_text()).get('filenames', []))
        for m in mounts:
            self.assertTrue(any(name.startswith(m['target'] + '/') for name in acquired), m['target'])

    def test_noisy_sources_are_filtered_before_parsing(self):
        # An empty list from `transform` emits no event, so the line is not "unparsed".
        for f in (STACK / 'acquis.d').glob('*.yaml'):
            acquis = yaml.safe_load(f.read_text())
            self.assertRegex(acquis['transform'], r'\? \[evt\.Line\.Raw\] : \[\]$', f.name)

    def test_unifi_syslog_listener_matches_published_port(self):
        acquis = yaml.safe_load((STACK / 'acquis.d/unifi.yaml').read_text())
        self.assertEqual(acquis['source'], 'syslog')
        self.assertEqual(acquis['labels']['type'], 'unifi')
        self.assertEqual(acquis['listen_port'], 5514)
        self.assertIn('crowdsecurity/unifi', self.engine['environment']['COLLECTIONS'])

    def test_unifi_hostname_repair_parser_runs_first(self):
        target = self.binds['./parsers/quark-unifi-syslog-host.yaml']
        self.assertEqual(target, '/etc/crowdsec/parsers/s00-raw/a-quark-unifi-syslog-host.yaml')
        parser = yaml.safe_load((STACK / 'parsers/quark-unifi-syslog-host.yaml').read_text())
        self.assertEqual(parser['onsuccess'], 'next_stage')
        self.assertNotIn('debug', parser)
        self.assertFalse((STACK / 'scenarios').exists())

    def test_console_enrollment_is_optional_secret(self):
        env = self.engine['environment']
        self.assertEqual(env['ENROLL_KEY'], '${CROWDSEC_ENROLL_KEY:-}')
        self.assertEqual(env['ENROLL_INSTANCE_NAME'], 'quark')

    def test_home_network_is_never_banned(self):
        wl = yaml.safe_load((STACK / 'parsers/quark-private-whitelist.yaml').read_text())
        for cidr in ['192.168.0.0/16', '172.16.0.0/12', '100.64.0.0/10', '::ffff:192.168.0.0/112']:
            self.assertIn(cidr, wl['whitelist']['cidr'])

    def test_recovery_selection(self):
        backup = json.loads((ROOT / 'host/quark/app-backup.example.json').read_text())
        dirs = backup['config_directories']
        self.assertIn('/mnt/services/quark/docker/crowdsec/config', dirs)
        self.assertFalse([d for d in dirs if '/crowdsec/' in d and not d.endswith('/crowdsec/config')])


if __name__ == '__main__':
    unittest.main()
