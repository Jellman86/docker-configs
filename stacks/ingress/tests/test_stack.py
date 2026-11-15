import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

STACK = Path(__file__).resolve().parents[1]
ROOT = STACK.parents[1]
spec = importlib.util.spec_from_file_location('build_npmplus', ROOT / 'scripts/build-npmplus.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
BROAD = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', 'fc00::/7', 'fec0::/10']


class IngressContract(unittest.TestCase):
    def setUp(self):
        self.prod = yaml.safe_load((STACK / 'compose.yaml').read_text())
        self.rollback = yaml.safe_load((STACK / 'compose.rollback.yaml').read_text())
        self.npm = self.prod['services']['npm']
        self.tunnel = self.prod['services']['cloudflared']

    def test_generated_manifests_are_current(self):
        for path, text in build.render().items():
            self.assertEqual(path.read_text(), text, path)

    def test_images_are_pinned_by_digest(self):
        for model in (self.prod, self.rollback):
            for service in model['services'].values():
                self.assertRegex(service['image'], r'@sha256:[0-9a-f]{64}$')
        self.assertIn('npmplus:2026-10-22-r1@', self.npm['image'])
        self.assertNotIn('develop', self.npm['image'])

    def test_admin_port_is_loopback_only(self):
        self.assertEqual(self.npm['ports'], ['80:80', '443:443', '127.0.0.1:81:81'])
        self.assertEqual(self.npm['environment']['NPM_LISTEN_LOCALHOST'], 'false')

    def test_identity_and_networks_are_kept(self):
        self.assertEqual(self.prod['name'], 'ingress')
        self.assertEqual(self.npm['container_name'], 'npm')
        brg = self.npm['networks']['general_brg']
        self.assertEqual(brg['aliases'], ['nginx-rp'])
        self.assertEqual(brg['ipv4_address'], '172.18.254.10')
        self.assertIn('npm_proxy_backends', self.npm['networks'])
        self.assertEqual(self.prod['networks']['crowdsec_api']['name'], 'quark-crowdsec-api')
        self.assertEqual(self.tunnel['container_name'], 'cloudflare-tunnel')

    def test_tunnel_has_fixed_trusted_source_and_direct_origin(self):
        self.assertEqual(self.tunnel['networks']['general_brg']['ipv4_address'], '172.18.254.11')
        self.assertEqual(self.tunnel['extra_hosts'], ['quark.pownet.uk:172.18.254.10'])
        self.assertNotIn('ports', self.tunnel)

    def test_no_cloudflare_or_private_trust_and_no_appsec(self):
        env = self.npm['environment']
        self.assertEqual(env['TRUST_CLOUDFLARE'], 'false')
        self.assertEqual(env['ACME_PROFILE'], 'classic')
        for name in ('COOKIE_SECRET', 'CROWDSEC_BOUNCER_KEY'):
            self.assertTrue(env[name].startswith('${') and ':?' in env[name])
        self.assertNotIn('INITIAL_ADMIN_PASSWORD', env)

    def test_state_is_a_new_directory_never_the_original(self):
        source = self.npm['volumes'][0]['source']
        self.assertIn('/npmplus', source)
        self.assertNotIn('nginx-proxy-manager', source)
        self.assertFalse(self.npm['volumes'][0]['bind']['create_host_path'])

    def test_rollback_is_the_original_npm_and_path(self):
        npm = self.rollback['services']['npm']
        self.assertIn('jc21/nginx-proxy-manager@sha256:91277490', npm['image'])
        self.assertEqual(self.rollback['name'], 'ingress')
        sources = [v['source'] for v in npm['volumes']]
        self.assertTrue(all('nginx-proxy-manager' in s for s in sources))
        tunnel = self.rollback['services']['cloudflared']
        self.assertNotIn('extra_hosts', tunnel)
        self.assertNotIn('ipv4_address', json.dumps(tunnel))

    def test_staging_never_mounts_production_state(self):
        staging = yaml.safe_load((ROOT / 'tools/npmplus-rehearsal/compose.yaml').read_text())
        text = json.dumps(staging)
        self.assertNotIn('nginx-proxy-manager', text)
        self.assertNotIn('/mnt/services', text)
        self.assertTrue(all(p.startswith('127.0.0.1:') for p in staging['services']['npmplus']['ports']))
        self.assertEqual(staging['services']['trusted-probe']['profiles'], ['probe'])


@unittest.skipUnless(subprocess.run(['which', 'node'], capture_output=True).returncode == 0, 'node unavailable')
class PrestartBehaviour(unittest.TestCase):
    def run_prestart(self, key):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            conf = tmp / 'nginx.conf'
            conf.write_text('http {\n  real_ip_recursive on;\n  real_ip_header X-Forwarded-For;\n'
                            '  set_real_ip_from unix:;\n  set_real_ip_from 127.0.0.0/8;\n'
                            + ''.join(f'  set_real_ip_from {r};\n' for r in BROAD) + '}\n')
            example = tmp / 'example'
            example.write_text('ENABLED=false\nAPI_URL=http://127.0.0.1:8080\nAPI_KEY=\nMODE=live\n'
                               'APPSEC_URL=http://127.0.0.1:7422\nAPPSEC_FAILURE_ACTION=deny\n')
            (tmp / 'data').mkdir()
            env = dict(os.environ, NPMPLUS_NGINX_CONF=str(conf), NPMPLUS_DATA_DIR=str(tmp / 'data'),
                       NPMPLUS_CROWDSEC_EXAMPLE=str(example), CROWDSEC_BOUNCER_KEY=key,
                       PUID=str(os.getuid()), PGID=str(os.getgid()))
            result = subprocess.run(['node', str(STACK / 'npmplus-prestart.cjs')], env=env,
                                    capture_output=True, text=True)
            out = tmp / 'data/crowdsec/crowdsec.conf'
            return result, conf.read_text(), (out.read_text() if out.exists() else ''), \
                (oct(out.stat().st_mode & 0o777) if out.exists() else None)

    def test_strips_broad_trust_and_provisions_private_stream_bouncer(self):
        key = 'k' * 40
        result, conf, bouncer, mode = self.run_prestart(key)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(key, result.stdout + result.stderr)
        for r in BROAD:
            self.assertNotIn(r, conf)
        self.assertIn('set_real_ip_from 127.0.0.0/8;', conf)
        for line in ('ENABLED=true', 'API_URL=http://crowdsec:8080', f'API_KEY={key}', 'MODE=stream',
                     'APPSEC_URL=', 'APPSEC_FAILURE_ACTION=passthrough'):
            self.assertIn(line + '\n', bouncer + '\n')
        self.assertEqual(mode, '0o600')

    def test_rejects_missing_or_weak_key(self):
        result, _, bouncer, _ = self.run_prestart('short')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(bouncer, '')


if __name__ == '__main__':
    unittest.main()
