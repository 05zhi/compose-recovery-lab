"""Build both real adapters and verify their shared source and locked images."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    with (Path.home() / '.crl-acceptance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        execute(args.output.resolve())


def execute(output):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = {key: os.environ[key] for key in ('HOME', 'PATH') if key in os.environ}
    env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    with (output / 'prepare-images.log').open('w') as log:
        subprocess.run(['python3', 'scripts/prepare-images.py'], cwd=ROOT, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    locks = {
        name: json.loads((ROOT / 'examples' / name / 'images.lock.json').read_text())
        for name in ('document-app', 'inventory-app')
    }
    document = locks['document-app']['app']
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', document)
    base_tag = 'crl-document-base:' + document.removeprefix('sha256:')
    resolved = subprocess.check_output(
        ['docker', 'image', 'inspect', base_tag, '--format', '{{.Id}}'], env=env, text=True,
    ).strip()
    assert resolved == document, 'Build base tag differs from the locked document image'
    source_hash = hashlib.sha256((ROOT / 'examples/document-app/app.py').read_bytes()).hexdigest()
    probe = (
        "import hashlib,json,pathlib,sys; "
        "assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()==sys.argv[2]; "
        "import app; "
        "print(json.dumps({'source_hash':sys.argv[2],'app_import':'passed'}))"
    )
    probes = {}
    for name, image_lock in locks.items():
        assert re.fullmatch(r'sha256:[0-9a-f]{64}', image_lock['app'])
        assert image_lock['postgres'] == locks['document-app']['postgres']
        source_path = '/app/app.py' if name == 'document-app' else '/app/common.py'
        container = 'crl-image-probe-' + uuid.uuid4().hex
        try:
            result = subprocess.run(
                ['docker', 'run', '--rm', '--name', container, '--network', 'none',
                 '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                 '--label', 'io.compose-recovery-lab.image-preparation=' + container,
                 image_lock['app'], 'python', '-c', probe, source_path, source_hash],
                env=env, capture_output=True, text=True, timeout=30, check=True,
            )
        finally:
            remaining = subprocess.check_output(
                ['docker', 'ps', '-aq', '--filter', 'name=^/' + container + '$'],
                env=env, text=True,
            ).strip()
            if remaining:
                inspected = json.loads(subprocess.check_output(
                    ['docker', 'container', 'inspect', remaining], env=env, text=True,
                ))[0]
                assert inspected['Config']['Labels'].get('io.compose-recovery-lab.image-preparation') == container
                subprocess.run(['docker', 'container', 'rm', '-f', remaining], env=env, check=True)
        probes[name] = json.loads(result.stdout)
    (output / 'summary.json').write_text(json.dumps(
        {'locks': locks, 'base_tag': base_tag, 'probes': probes}, indent=2,
    ) + '\n')
    print('Image preparation integration PASS:', output, flush=True)


if __name__ == '__main__':
    main()
