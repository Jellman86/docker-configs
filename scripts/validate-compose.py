#!/usr/bin/env python3
"""Render every manifest with synthetic values; never reads host/Dockhand secrets.

Run from a checkout with Docker Compose installed. This does not contact an
engine, create networks/containers, pull images or deploy optional stacks.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Explicit values are deliberately safe fixtures, not production credentials.
FIXTURES = {
    'CONFIG_PATH': '/mnt/services/docker/validation',
    'BN_LAT': '0', 'BN_LONG': '0', 'PUID': '1000', 'PGID': '1000',
    'TZ': 'Europe/London', 'IMMICH_DB_PASSWORD': 'ci-placeholder',
}


def validate(root=ROOT):
    sources = sorted(p for p in root.rglob('*compose*') if p.suffix in {'.yaml', '.yml'} and not p.name.startswith('._') and '.github' not in p.parts)
    env = {'PATH': os.environ['PATH'], 'HOME': os.environ.get('HOME', '/tmp')}
    # Populate only required/un-defaulted variables. Keep defaults active so CI
    # catches wrong host ports, paths and types hidden by deployment overrides.
    for source in sources:
        for key in re.findall(r'(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(?:\?[^}]*|:\?[^}]*)?\}', source.read_text()):
            env[key] = FIXTURES.get(key, 'ci-placeholder')
    env.update(FIXTURES)
    count = 0
    for source in sources:
        result = subprocess.run(
            ['docker', 'compose', '--project-directory', str(source.parent),
             '-f', str(source), '--profile', '*', 'config', '--format', 'json'],
            env=env, text=True, capture_output=True,
        )
        if result.returncode:
            raise RuntimeError(f'{source.relative_to(root)} failed to render:\n{result.stderr}')
        model = json.loads(result.stdout)
        project = model['name']
        expected_project = 'immich-ml' if source.name == 'compose.ml.yaml' else source.parent.name
        assert project == expected_project, (source, 'project differs from documented stack', project)
        assert re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', project), (source, 'use lowercase kebab-case')
        pinned_volumes = {
            ('optimisarr-sidecar', 'sidecar-config'): 'optimisarr_sidecar_sidecar-config',
            ('immich-ml', 'model-cache'): 'immich_ml_model-cache',
        }
        for (owner, key), identity in pinned_volumes.items():
            if project == owner:
                volume = model['volumes'][key]
                assert volume['name'] == identity and volume.get('external'), (source, 'state identity changed', key)
        for name, service in model['services'].items():
            log = service.get('logging', {})
            options = log.get('options', {})
            assert log.get('driver') == 'json-file', (source, name, 'unbounded Docker logging')
            assert re.fullmatch(r'[1-9][0-9]*[kKmM]', str(options.get('max-size', ''))), (source, name, 'log size missing')
            assert 1 <= int(options.get('max-file', '0')) <= 5, (source, name, 'log file count')
            # Profiled bootstrap/acceptance jobs may exit successfully by design.
            if name in {'restore', 'openviking-bootstrap', 'openviking-ollama-model', 'web-ui-machine'}:
                assert service['restart'] == 'no', (source, name, 'one-shot restart loop')
        count += len(model['services'])
        print(f'{source.relative_to(root)}: {len(model["services"])} service definitions passed')
    print(f'{len(sources)} manifests / {count} resolved service definitions passed')


if __name__ == '__main__':
    validate(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT)
