#!/usr/bin/env python3
"""Generate the NPMplus ingress and temporary staging manifests.

Both embed stacks/ingress/npmplus-prestart.cjs as an inline Compose config,
because Dockhand renders from its own synced copy and file configs would bind a
path that does not exist on the host. Run after changing the prestart script;
CI runs this with --check.
"""
from copy import deepcopy
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / 'stacks/ingress/compose.yaml'
STAGING = ROOT / 'tools/npmplus-rehearsal/compose.yaml'
NPMPLUS = 'ghcr.io/zoeyvid/npmplus:2026-10-22-r1@sha256:244fbf14f0c8bfb969434bfacba14ba71f8eee9911a2466035e640d64e594178'
CLOUDFLARED = 'cloudflare/cloudflared@sha256:b94b96edf2c9c4360f8879c8580cfaa99077f19c849ec595ca2f711b27d4f344'
PROXY_IP = '172.18.254.10'
TUNNEL_IP = '172.18.254.11'
LOGGING = {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}
HEALTH = ['CMD-SHELL', 'curl --insecure --fail --silent https://127.0.0.1:81/api/ '
          '| grep -Eq \'"status"[[:space:]]*:[[:space:]]*"OK"\'']
NETWORKS = {'general_brg': {'external': True}, 'npm_proxy_backends': {'external': True},
            'crowdsec_api': {'external': True, 'name': 'quark-crowdsec-api'}}


def proxy(container, restart, ports, data, extra_env):
    environment = {
        'TZ': 'Europe/London', 'PUID': '1000', 'PGID': '1000',
        'COOKIE_SECRET': '${NPMPLUS_COOKIE_SECRET:?Set as a Dockhand secret}',
        'CROWDSEC_BOUNCER_KEY': '${CROWDSEC_BOUNCER_KEY:?Set as a Dockhand secret}',
        'ACME_EMAIL': '${NPMPLUS_ACME_EMAIL:?Set in Dockhand}',
        'ACME_PROFILE': 'classic', 'DISABLE_IPV6': 'true', 'DISABLE_H3_QUIC': 'true',
        # Bridge publishing needs the container interface; the host binds 81 to loopback.
        'NPM_LISTEN_LOCALHOST': 'false', 'TRUST_CLOUDFLARE': 'false',
        'DISABLE_GRAVATAR': 'true', 'LOGROTATE': 'true', 'LOGROTATIONS': '3',
    }
    environment.update(extra_env)
    return {
        'image': NPMPLUS, 'container_name': container, 'restart': restart,
        # Keep the image's tini init; prestart must succeed before NPMplus starts.
        'entrypoint': ['tini', '--', 'sh', '-c', 'node /npmplus-prestart.cjs && exec entrypoint.sh'],
        'cap_drop': ['ALL'],
        'cap_add': ['NET_BIND_SERVICE', 'SETGID', 'SETUID', 'CHOWN', 'FOWNER', 'DAC_OVERRIDE'],
        'security_opt': ['no-new-privileges:true'], # Reloads briefly run old and new workers, each with thread pools; 1024 was exhausted.
        'mem_limit': '1536m', 'pids_limit': 4096,
        'environment': environment, 'ports': ports,
        'networks': {'general_brg': {'ipv4_address': PROXY_IP}, 'npm_proxy_backends': {}, 'crowdsec_api': {}},
        'volumes': [{'type': 'bind', 'source': data, 'target': '/data', 'bind': {'create_host_path': False}}],
        'configs': [{'source': 'npmplus-prestart', 'target': '/npmplus-prestart.cjs'}],
        'healthcheck': {'test': HEALTH, 'interval': '30s', 'timeout': '5s', 'retries': 5, 'start_period': '120s'},
        'logging': LOGGING,
    }


def production(prestart):
    npm = proxy('npm', 'unless-stopped', ['80:80', '443:443', '127.0.0.1:81:81'],
                '${NPMPLUS_DATA_PATH:-/mnt/services/quark/docker/npmplus}', {'TZ': '${TZ}'})
    # Existing apps and the tunnel still address the proxy as nginx-rp.
    npm['networks']['general_brg']['aliases'] = ['nginx-rp']
    tunnel = {
        'image': CLOUDFLARED, 'container_name': 'cloudflare-tunnel', 'restart': 'unless-stopped',
        'logging': LOGGING,
        # Fixed address: only this source may supply CF-Connecting-IP on tunnel hosts.
        'networks': {'general_brg': {'ipv4_address': TUNNEL_IP}},
        # Same remote origin, SNI and certificate validation, but a direct bridge path
        # instead of the host-published port, whose source would be the shared gateway.
        'extra_hosts': [f'quark.pownet.uk:{PROXY_IP}'],
        'command': 'tunnel --metrics 127.0.0.1:60123 run',
        'environment': ['PUID=${PUID}', 'PGID=${PGID}', 'TZ=${TZ}', 'TUNNEL_TOKEN=${TUNNEL_TOKEN}'],
        'depends_on': {'npm': {'condition': 'service_healthy'}},
        'healthcheck': {'test': ['CMD', 'cloudflared', 'tunnel', '--metrics', '127.0.0.1:60123', 'ready'],
                        'interval': '1m', 'timeout': '10s', 'retries': 3, 'start_period': '30s'},
    }
    return {'name': 'ingress', 'services': {'npm': npm, 'cloudflared': tunnel},
            'configs': {'npmplus-prestart': {'content': prestart}}, 'networks': deepcopy(NETWORKS)}


def staging(prestart):
    npm = proxy('quark-npmplus-rehearsal', 'no', ['127.0.0.1:18080:80', '127.0.0.1:18443:443', '127.0.0.1:18081:81'],
                '${NPMPLUS_REHEARSAL_ROOT:?Set to fresh staging state}/data',
                {'INITIAL_ADMIN_EMAIL': '${NPMPLUS_ADMIN_EMAIL:?Set in Dockhand}',
                 'INITIAL_ADMIN_PASSWORD': '${NPMPLUS_ADMIN_PASSWORD:?Set as a Dockhand secret}',
                 'INITIAL_DEFAULT_PAGE': '404'})
    probe = {
        'image': NPMPLUS, 'container_name': 'quark-npmplus-trusted-probe', 'restart': 'no',
        'profiles': ['probe'], 'user': '1000:1000',
        'entrypoint': ['node', '-e', 'setInterval(() => {}, 3600000)'],
        'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'mem_limit': '128m', 'pids_limit': 64,
        # Temporary stand-in for the future tunnel address. Remove before cutover.
        'networks': {'general_brg': {'ipv4_address': TUNNEL_IP}}, 'logging': LOGGING,
    }
    return {'name': 'npmplus-rehearsal', 'services': {'npmplus': npm, 'trusted-probe': probe},
            'configs': {'npmplus-prestart': {'content': prestart}}, 'networks': deepcopy(NETWORKS)}


class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


Dumper.add_representer(str, lambda d, v: d.represent_scalar('tag:yaml.org,2002:str', v, style='|' if '\n' in v else None))
HEADER = {
    PRODUCTION: '# Generated by scripts/build-npmplus.py; edit that script, not this file.\n'
                '# Quark ingress: NPMplus with the CrowdSec bouncer, plus the Cloudflare Tunnel.\n'
                '# Rollback to the original NPM state: compose.rollback.yaml (see README).\n',
    STAGING: '# Generated by scripts/build-npmplus.py. Temporary fresh staging; no production state.\n',
}


def render():
    prestart = (ROOT / 'stacks/ingress/npmplus-prestart.cjs').read_text().replace('$', '$$')
    return {path: HEADER[path] + yaml.dump(model, Dumper=Dumper, sort_keys=False)
            for path, model in ((PRODUCTION, production(prestart)), (STAGING, staging(prestart)))}


if __name__ == '__main__':
    stale = []
    for path, text in render().items():
        if '--check' in sys.argv:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(text)
    if stale:
        raise SystemExit('Stale generated NPMplus manifests: ' + ', '.join(stale) + '; run scripts/build-npmplus.py')
    print('NPMplus manifests ' + ('current' if '--check' in sys.argv else 'generated'))
