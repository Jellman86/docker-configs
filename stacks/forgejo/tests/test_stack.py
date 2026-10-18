from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]


class ForgejoContract(unittest.TestCase):
    def test_private_git_and_state_recovery(self):
        compose = yaml.safe_load((ROOT / 'stacks/forgejo/compose.yaml').read_text())
        service = compose['services']['forgejo']
        env = service['environment']
        self.assertEqual(service['user'], '1000:1000')
        self.assertEqual(service['ports'], ['192.168.213.102:2222:2222'])
        self.assertEqual(env['FORGEJO__server__ROOT_URL'], 'https://git.pownet.uk/')
        for key in ['FORGEJO__service__DISABLE_REGISTRATION',
                    'FORGEJO__service__REQUIRE_SIGNIN_VIEW',
                    'FORGEJO__repository__FORCE_PRIVATE',
                    'FORGEJO__security__INSTALL_LOCK']:
            self.assertEqual(env[key], 'true')
        self.assertNotIn('*', env['FORGEJO__security__REVERSE_PROXY_TRUSTED_PROXIES'])
        self.assertEqual(env['FORGEJO__service__ENABLE_REVERSE_PROXY_AUTHENTICATION'], 'false')
        paths = {v['target']:v['source'] for v in service['volumes']}
        self.assertEqual(paths['/var/lib/gitea'], '/mnt/services/quark/docker/forgejo/data')
        self.assertEqual(set(paths), {'/var/lib/gitea'})
        self.assertTrue(all(not v['bind']['create_host_path'] for v in service['volumes']))
        import json
        backup = json.loads((ROOT / 'host/quark/app-backup.example.json').read_text())
        self.assertIn('/mnt/services/quark/docker/forgejo', backup['config_directories'])
