"""Real Docker M1 acceptance. Run on a dedicated Linux test host, as Docker operator.

Leaves private backup/report evidence in --output (or a new temporary directory).
Only removes this suite's sentinel and resources discovered through CRL journals.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / 'bin/crl'
ENV = dict(os.environ, DOCKER_HOST='unix:///var/run/docker.sock')


def docker(*args):
    return subprocess.check_output(['docker', *args], env=ENV, text=True).strip()


def expect(value, message):
    if not value:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or Path(tempfile.mkdtemp(prefix='crl-m1-acceptance-'))
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    work = output / 'runs'
    work.mkdir(mode=0o700)
    summary = []
    sentinel = 'crl-sentinel-' + uuid.uuid4().hex
    docker('volume', 'create', '--label', 'io.compose-recovery-lab.test=' + sentinel, sentinel)
    sentinel_before = docker('volume', 'inspect', sentinel)

    def invoke(case, command, *extra, success=True, env=ENV):
        before = set(work.glob('*/report.json'))
        proc = subprocess.run([str(BIN), command, '--work', str(work), *map(str, extra)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        reports = set(work.glob('*/report.json')) - before
        expect(len(reports) == 1, f'{case}: expected one report: {proc.stderr}')
        report_path = reports.pop()
        report = json.loads(report_path.read_text())
        expect((proc.returncode == 0) == success, f'{case}: unexpected exit {proc.returncode}: {proc.stderr}')
        expect((report_path.parent / 'report.html').is_file(), f'{case}: missing HTML')
        summary.append({'case': case, 'exit_code': proc.returncode, 'report': str(report_path), 'verification': report['verification_result'], 'cleanup': report['cleanup_result'], 'seconds': sum(s['seconds'] for s in report['steps'])})
        print(case, report['verification_result'], report['cleanup_result'], flush=True)
        return report, report_path

    def clean(report):
        expect(report['cleanup_result'] == 'complete' and not report['remaining_resources'], 'cleanup incomplete')
        for kind, args in [('containers', ['ps', '-aq']), ('networks', ['network', 'ls', '-q']), ('volumes', ['volume', 'ls', '-q'])]:
            expect(not docker(*args, '--filter', 'label=io.compose-recovery-lab.run=' + report['run_id']), 'leaked ' + kind)

    def variant(name):
        dest = output / name
        shutil.copytree(output / 'complete', dest)
        return dest

    def rehash(bundle):
        path = bundle / 'manifest.json'
        manifest = json.loads(path.read_text())
        for name in manifest['files']:
            data = (bundle / name).read_bytes()
            manifest['files'][name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        path.write_text(json.dumps(manifest))

    def interrupt(case, sig):
        before = set(work.iterdir())
        proc = subprocess.Popen([str(BIN), 'run', '--work', str(work), '--bundle', str(output / 'complete')], cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        run_dir = None
        deadline = time.monotonic() + 40
        try:
            while time.monotonic() < deadline:
                dirs = set(work.iterdir()) - before
                if dirs:
                    run_dir = dirs.pop()
                    journal = run_dir / 'resources.json'
                    if journal.exists():
                        run_id = json.loads(journal.read_text())['run_id']
                        if docker('ps', '-aq', '--filter', 'label=io.compose-recovery-lab.run=' + run_id):
                            break
                expect(proc.poll() is None, 'runner exited before fault injection')
                time.sleep(.1)
            else:
                raise AssertionError('no live resource observed before interrupt')
            if sig == signal.SIGKILL:
                os.killpg(proc.pid, sig)
            else:
                proc.send_signal(sig)
            proc.communicate(timeout=90)
            expect(proc.returncode != 0, 'interrupted run passed')
            if sig == signal.SIGKILL:
                subprocess.run([str(BIN), 'cleanup', '--run-dir', str(run_dir)], cwd=ROOT, env=ENV, check=True, timeout=90, capture_output=True)
            report = json.loads((run_dir / 'report.json').read_text())
            expect(report['verification_result'] == ('inconclusive' if sig == signal.SIGKILL else 'canceled'), 'wrong interrupted result')
            clean(report)
            summary.append({'case': case, 'verification': report['verification_result'], 'cleanup': report['cleanup_result'], 'report': str(run_dir / 'report.json')})
            print(case, report['verification_result'], report['cleanup_result'], flush=True)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)

    try:
        # A reachable host baseline makes the fixed external endpoint probe meaningful.
        with socket.create_connection(('1.1.1.1', 443), timeout=10):
            pass
        report, _ = invoke('complete-backup', 'backup', '--out', output / 'complete')
        clean(report)
        for case in ('complete-restore', 'repeat-restore'):
            report, _ = invoke(case, 'run', '--bundle', output / 'complete')
            expect(report['verification_result'] == 'passed', 'complete restore failed')
            expect(len(report['checks']) == 4, 'missing checks')
            clean(report)

        report, _ = invoke('missing-backup', 'backup', '--out', output / 'missing', '--omit-attachment')
        clean(report)
        report, _ = invoke('missing-attachment', 'run', '--bundle', output / 'missing', success=False)
        results = {check['id']: check['status'] for check in report['checks']}
        expect(results['sql-documents'] == 'passed' and results['database-files'] == 'failed' and results['login-search-download'] == 'failed', 'missing attachment not detected across storage and HTTP')
        clean(report)

        corrupt = variant('corrupt')
        with (corrupt / 'database.dump').open('ab') as stream:
            stream.write(b'corruption')
        report, _ = invoke('corrupt-hash', 'run', '--bundle', corrupt, success=False)
        expect('restoring' not in [s['name'] for s in report['steps']], 'corrupt bundle reached restore')
        clean(report)

        wrong = variant('wrong-content')
        with tarfile.open(wrong / 'uploads.tar') as archive:
            members = [(m, archive.extractfile(m).read()) for m in archive.getmembers() if m.isfile()]
        with tarfile.open(wrong / 'uploads.tar', 'w') as archive:
            for index, (member, data) in enumerate(members):
                if index == 0:
                    data = b'wrong synthetic content'
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        rehash(wrong)
        report, _ = invoke('wrong-attachment', 'run', '--bundle', wrong, success=False)
        expect(any(c['id'] == 'database-files' and c['status'] == 'failed' for c in report['checks']), 'wrong attachment not detected')
        clean(report)

        unsafe = variant('unsafe-path')
        with tarfile.open(unsafe / 'uploads.tar', 'w') as archive:
            member = tarfile.TarInfo('../escaped')
            member.size = 1
            archive.addfile(member, io.BytesIO(b'x'))
        rehash(unsafe)
        report, _ = invoke('tar-traversal', 'run', '--bundle', unsafe, success=False)
        expect(not (output / 'escaped').exists(), 'archive escaped')
        expect('restoring' not in [s['name'] for s in report['steps']], 'unsafe tar reached restore')
        clean(report)

        bad_dump = variant('bad-dump')
        (bad_dump / 'database.dump').write_bytes(b'PGDMPinvalid-format')
        rehash(bad_dump)
        report, _ = invoke('restore-error', 'run', '--bundle', bad_dump, success=False)
        expect(all(c['status'] == 'skipped' for c in report['checks']) and any(s['name'] == 'restoring' and s['status'] == 'error' for s in report['steps']), 'restore error not isolated')
        clean(report)

        # Force pg_dump failure after the source app has stopped. The resume command
        # must run even though the incomplete bundle is not published.
        backup_shim = output / 'backup-shim'
        backup_shim.mkdir()
        marker = output / 'source-resumed'
        shim_file = backup_shim / 'docker'
        shim_file.write_text('#!/usr/bin/python3\nimport os,sys\nfrom pathlib import Path\nargs=sys.argv[1:]\n'
                             'if "pg_dump" in args: sys.exit(1)\n'
                             f'if args[:1]==["compose"] and args[-2:]==["start","app"]: Path({str(marker)!r}).touch()\n'
                             'os.execv("/usr/bin/docker", ["docker", *args])\n')
        shim_file.chmod(0o700)
        report, _ = invoke('backup-error-resumes-source', 'backup', '--out', output / 'failed-backup', success=False,
                           env=dict(ENV, PATH=str(backup_shim) + ':' + os.environ['PATH']))
        expect(marker.exists() and not (output / 'failed-backup').exists(), 'failed backup did not resume source or was published')
        clean(report)

        interrupt('cancel-with-live-resources', signal.SIGTERM)
        interrupt('crash-and-explicit-cleanup', signal.SIGKILL)

        shim = output / 'docker-shim'
        shim.mkdir()
        executable = shim / 'docker'
        executable.write_text('#!/bin/sh\ncase "$1 $2" in "container rm"|"network rm"|"volume rm") exit 1;; esac\nexec /usr/bin/docker "$@"\n')
        executable.chmod(0o700)
        report, report_path = invoke('cleanup-failure', 'run', '--bundle', output / 'complete', success=False, env=dict(ENV, PATH=str(shim) + ':' + os.environ['PATH']))
        expect(report['verification_result'] == 'passed' and report['cleanup_result'] == 'failed', 'cleanup failure was hidden')
        compose = json.loads((report_path.parent / 'compose.json').read_text())
        password = compose['services']['app']['environment']['DEMO_PASSWORD']
        for artifact in ('report.json', 'report.html', 'resources.json'):
            expect(password not in (report_path.parent / artifact).read_text(), 'secret in report/journal')
        subprocess.run([str(BIN), 'cleanup', '--run-dir', str(report_path.parent)], cwd=ROOT, env=ENV, check=True, timeout=90, capture_output=True)
        recovered = json.loads(report_path.read_text())
        clean(recovered)
        summary.append({'case': 'cleanup-retry', 'verification': recovered['verification_result'], 'cleanup': recovered['cleanup_result'], 'report': str(report_path)})
        expect(docker('volume', 'inspect', sentinel) == sentinel_before, 'foreign sentinel changed')
        summary.append({'case': 'foreign-resource-preserved', 'verification': 'passed'})
    finally:
        # Reconcile only journals created in this suite's private directory.
        for journal in work.glob('*/resources.json'):
            subprocess.run([str(BIN), 'cleanup', '--run-dir', str(journal.parent)], cwd=ROOT, env=ENV, timeout=90, capture_output=True)
        inspected = json.loads(docker('volume', 'inspect', sentinel))[0]
        if inspected.get('Labels', {}).get('io.compose-recovery-lab.test') == sentinel:
            docker('volume', 'rm', sentinel)
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('M1 acceptance passed; evidence:', output, flush=True)


if __name__ == '__main__':
    main()
