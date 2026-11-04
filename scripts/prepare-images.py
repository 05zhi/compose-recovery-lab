"""Fetch trusted base images and build the local synthetic application before drills."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
POSTGRES = 'postgres@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3'


def main():
    env = {key: os.environ[key] for key in ('PATH', 'HOME') if key in os.environ}
    env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    subprocess.run(['docker', 'pull', POSTGRES], env=env, check=True)
    with tempfile.TemporaryDirectory(prefix='crl-build-') as temp:
        iid = Path(temp) / 'image-id'
        subprocess.run(['docker', 'build', '--iidfile', str(iid), str(ROOT / 'examples/document-app')], env=env, check=True)
        image = iid.read_text().strip()
    lock = ROOT / 'examples/document-app/images.lock.json'
    lock.write_text(json.dumps({'postgres': POSTGRES, 'app': image}, indent=2) + '\n')
    lock.chmod(0o600)
    print(f'Trusted local image lock: {lock}')


if __name__ == '__main__':
    main()
