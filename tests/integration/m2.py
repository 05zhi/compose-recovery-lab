"""M2 acceptance: offline purity, negative contracts and real configured recovery."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
# Serialize acceptance suites; each CLI still enforces its independent account lock.
import fcntl
_suite_lock = open(Path.home() / '.crl-acceptance.lock', 'a')
fcntl.flock(_suite_lock, fcntl.LOCK_EX)

import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / 'bin/crl'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, help='new persistent evidence directory')
    args = parser.parse_args()
    if args.output:
        root = args.output.resolve()
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
    else:
        parent = Path.home() / '.local/state/compose-recovery-lab/acceptance'
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix='m2-', dir=parent))
    work = root / 'work'
    bundle = root / 'bundle'
    summary = []
    env = dict(os.environ, DOCKER_HOST='unix:///var/run/docker.sock')

    def invoke(name, args, expected=0, custom_env=env):
        p = subprocess.run([str(BIN), *map(str, args)], cwd='/', env=custom_env, capture_output=True, text=True, timeout=120)
        assert p.returncode == expected, (name, p.returncode, p.stdout, p.stderr)
        assert 'DO_NOT_DISCLOSE_THIS' not in p.stdout + p.stderr, name
        summary.append({'case': name, 'exit_code': p.returncode})
        print(name, 'PASS', flush=True)
        return p

    def resources():
        return [subprocess.check_output(['docker', *args], env=env, text=True).strip() for args in (
            ['ps', '-aq'], ['volume', 'ls', '-q'], ['network', 'ls', '-q'])]

    # Generate an actual custom-format dump using the M1 path; no fixed fixture dependency.
    invoke('fresh-backup', ['backup', '--images', ROOT / 'examples/document-app/images.lock.json', '--out', bundle, '--work', root / 'producer'])
    shutil.copyfile(ROOT / 'examples/document-app/images.lock.json', root / 'images.json')
    config = {
        'schema_version': 1, 'name': 'm2-test', 'template': 'document-app-v1',
        'backup': {'type': 'local_bundle', 'path': './bundle', 'mapping': {'database': 'database.dump', 'uploads': 'uploads.tar', 'app_config': 'app-config.sanitized.json'}},
        'runtime': {'images_file': './images.json', 'work_dir': './work', 'timeout': '2m'},
        'checks': [{'id': name, 'required': True} for name in ('sql-documents', 'database-files', 'login-search-download', 'external-connectivity')],
        'report': {'formats': ['json', 'html']},
    }
    cfg = root / 'drill.yaml'
    cfg.write_text(json.dumps(config))  # JSON is a strict YAML subset.
    before = resources()
    file_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}
    shim = root / 'no-docker'
    shim.mkdir()
    marker = root / 'docker-was-called'
    executable = shim / 'docker'
    executable.write_text('#!/usr/bin/python3\nfrom pathlib import Path\n' + f'Path({str(marker)!r}).touch()\nraise SystemExit(99)\n')
    executable.chmod(0o700)
    no_docker = dict(env, PATH=str(shim) + ':' + os.environ['PATH'])
    planned = invoke('plan-with-docker-unavailable', ['plan', '--config', cfg], custom_env=no_docker)
    plan = json.loads(planned.stdout)
    assert len(plan['source_mapping']) == 3 and not plan['environment_checked']
    assert not marker.exists() and not work.exists(), 'plan caused side effects'
    (root / 'plan.json').write_text(planned.stdout)
    offline = invoke('offline-doctor', ['doctor', '--config', cfg, '--offline'], custom_env=no_docker)
    assert json.loads(offline.stdout)['status'] == 'offline_valid' and not json.loads(offline.stdout)['ready']
    assert not marker.exists() and not work.exists(), 'offline doctor caused side effects'
    failed = invoke('unavailable-docker', ['doctor', '--config', cfg], expected=1, custom_env=no_docker)
    assert not json.loads(failed.stdout)['ready'] and not work.exists()
    ready = invoke('real-doctor', ['doctor', '--config', cfg])
    assert json.loads(ready.stdout)['ready']
    (root / 'doctor.json').write_text(ready.stdout)
    assert resources() == before and not work.exists(), 'doctor modified resources'
    assert file_before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}, 'source changed'

    mutations = {
        'unsupported-version': lambda c: c.update(schema_version=2),
        'host-network': lambda c: c.update(network_mode='host'),
        'privileged': lambda c: c.update(privileged=True),
        'host-bind': lambda c: c.update(volumes=['/etc:/host']),
        'external-volume': lambda c: c.update(volumes={'external': True}),
        'command': lambda c: c.update(command='DO_NOT_DISCLOSE_THIS'),
        'secret': lambda c: c.update(password='DO_NOT_DISCLOSE_THIS'),
        'env-expansion': lambda c: c['backup'].update(path='${DO_NOT_DISCLOSE_THIS}'),
        'mapping-traversal': lambda c: c['backup']['mapping'].update(database='../database.dump'),
        'mapping-role-missing': lambda c: c['backup']['mapping'].pop('uploads'),
        'optional-check': lambda c: c['checks'][0].update(required=False),
        'custom-query': lambda c: c['checks'][0].update(query='SELECT secret'),
    }
    for name, mutate in mutations.items():
        bad = copy.deepcopy(config)
        mutate(bad)
        cfg.write_text(json.dumps(bad))
        invoke(name, ['plan', '--config', cfg], expected=2, custom_env=no_docker)
    cfg.write_text(json.dumps(config))
    invoke('mixed-runtime-flags', ['run', '--config', cfg, '--bundle', bundle], expected=2)
    for name, text in {
        'duplicate-yaml-key': 'schema_version: 1\nschema_version: 1\n',
        'multiple-documents': 'schema_version: 1\n---\nschema_version: 1\n',
        'yaml-anchor': 'schema_version: &version 1\n',
    }.items():
        cfg.write_text(text)
        invoke(name, ['plan', '--config', cfg], expected=2)
    cfg.write_text(json.dumps(config))
    original_manifest = (bundle / 'manifest.json').read_bytes()
    manifest = json.loads(original_manifest)
    for name, patch in [('wrong-major', {'postgres_major': 16}), ('wrong-extension', {'extensions': ['postgis']}), ('wrong-image', {'app_image': 'sha256:' + '0' * 64})]:
        (bundle / 'manifest.json').write_text(json.dumps(dict(manifest, **patch)))
        invoke(name, ['plan', '--config', cfg], expected=1)
    (bundle / 'manifest.json').write_bytes(original_manifest)
    bad = copy.deepcopy(config)
    alias = root / 'bundle-alias'
    alias.symlink_to(bundle, target_is_directory=True)
    bad['runtime']['work_dir'] = './bundle-alias/work'
    cfg.write_text(json.dumps(bad))
    invoke('symlink-workspace-overlap', ['plan', '--config', cfg], expected=1)
    cfg.write_text(json.dumps(config))
    assert resources() == before and not work.exists(), 'negative validation created resources'

    result = invoke('configured-real-restore', ['run', '--config', cfg])
    report = Path(result.stdout.strip().removeprefix('report: '))
    data = json.loads(report.read_text())
    assert data['verification_result'] == 'passed' and data['cleanup_result'] == 'complete'
    assert data['config_hash'] == plan['config_hash']
    assert data['backup_id'] == plan['backup_id'] and not data['remaining_resources']
    assert resources() == before, 'configured run leaked resources'

    # Change a still-valid manifest after in-process planning, during read-only doctor.
    # The runner must refuse the changed snapshot before starting restoration.
    tamper = root / 'tamper-docker'
    tamper.mkdir()
    changed = root / 'manifest-changed'
    executable = tamper / 'docker'
    executable.write_text('#!/usr/bin/python3\nimport os,sys,json\nfrom pathlib import Path\n'
                          f'marker=Path({str(changed)!r})\nmanifest=Path({str(bundle / "manifest.json")!r})\n'
                          'if sys.argv[1:3]==["image","inspect"] and not marker.exists():\n'
                          ' data=json.loads(manifest.read_text()); data["backup_id"]="changed-after-plan"; manifest.write_text(json.dumps(data)); marker.touch()\n'
                          'os.execv("/usr/bin/docker", ["docker", *sys.argv[1:]])\n')
    executable.chmod(0o700)
    refused = invoke('manifest-changed-after-plan', ['run', '--config', cfg], expected=1,
                     custom_env=dict(env, PATH=str(tamper) + ':' + os.environ['PATH']))
    refused_report = json.loads(Path(refused.stdout.strip().removeprefix('report: ')).read_text())
    assert changed.exists() and refused_report['verification_result'] == 'failed'
    assert refused_report['cleanup_result'] == 'complete' and not refused_report['remaining_resources']
    assert all(step['name'] != 'restoring' for step in refused_report['steps'])
    (bundle / 'manifest.json').write_bytes(original_manifest)
    assert resources() == before, 'snapshot rejection leaked resources'
    invoke('repeat-plan', ['plan', '--config', cfg])
    (root / 'summary.json').write_text(json.dumps(summary, indent=2))
    print('M2 acceptance passed; evidence:', root, flush=True)


if __name__ == '__main__':
    main()
