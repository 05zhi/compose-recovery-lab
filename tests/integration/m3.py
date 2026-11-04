"""Real crash recovery at every main phase, plus fresh-attempt retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
# Serialize acceptance suites; each CLI still enforces its independent account lock.
import fcntl
_suite_lock = open(Path.home() / '.crl-acceptance.lock', 'a')
fcntl.flock(_suite_lock, fcntl.LOCK_EX)

import shutil
import signal
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / 'bin/crl'
BASE = Path.home() / 'crl-m3-acceptance'
DB = Path.home() / '.local/state/compose-recovery-lab/history.sqlite3'


def call(*args):
    p = subprocess.run([str(BIN), *map(str, args)], cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, (args, p.stdout, p.stderr)
    return p.stdout


def main():
    global BASE
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);a=p.parse_args();BASE=a.output.resolve();BASE.mkdir(mode=0o700,exist_ok=False);original=a.fixture.resolve()
    cfg = json.loads((original / 'drill.yaml').read_text())
    original_bundle=(original/cfg['backup']['path']).resolve()
    shutil.copytree(original_bundle, BASE/'bundle')
    cfg['runtime']['images_file'] = str((original / cfg['runtime']['images_file']).resolve())
    cfg['runtime']['work_dir'] = str(BASE / 'work')
    cfg['runtime']['timeout'] = '2m'
    cfg['backup']['path'] = str(BASE / 'bundle')
    config = BASE / 'drill.yaml'
    config.write_text(json.dumps(cfg))
    # Larger valid byte envelope makes the staging phase observable without a test hook.
    dump = BASE / 'bundle/database.dump'
    with dump.open('ab') as f:
        f.write(b'\0' * (64 << 20))
    manifest_path = BASE / 'bundle/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files']['database.dump'] = {'size': dump.stat().st_size, 'sha256': hashlib.sha256(dump.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest))
    results = []
    for phase in ('preflight', 'staging', 'restoring', 'starting', 'verifying', 'cleaning'):
        with sqlite3.connect(DB) as db:
            old = {row[0] for row in db.execute('SELECT id FROM attempts')}
        proc = subprocess.Popen([str(BIN), 'run', '--config', str(config)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        found = None
        deadline = time.monotonic() + 120
        try:
            while time.monotonic() < deadline and proc.poll() is None:
                with sqlite3.connect(DB) as db:
                    rows = db.execute('SELECT id,phase,directory FROM attempts ORDER BY started DESC LIMIT 3').fetchall()
                found = next((r for r in rows if r[0] not in old and r[1] == phase), None)
                if found:
                    os.killpg(proc.pid, signal.SIGKILL)
                    break
                time.sleep(.002)
            assert found, ('phase not observed', phase, proc.communicate(timeout=5))
            proc.communicate(timeout=10)
            call('recover')
            record = json.loads(call('status', '--run', found[0], '--attempt'))
            assert record['cleanup_result'] == 'complete' and record['verification_result'] != 'passed', record
            report = json.loads((Path(found[2]) / 'report.json').read_text())
            assert not report['remaining_resources']
            results.append({'phase': phase, 'attempt': found[0], 'cleanup': 'complete'})
            print(phase, 'crash/recover PASS', flush=True)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    # Restore the original bundle content. Configuration stays identical; new manifest
    # is validated on explicit retry, and the old attempt is never overwritten.
    for name in ('database.dump', 'manifest.json'):
        shutil.copyfile(original_bundle / name, BASE / 'bundle' / name)
    previous = results[-1]['attempt']
    call('retry', '--run', previous, '--config', config)
    latest = json.loads(call('status', '--run', previous))
    old = json.loads(call('status', '--run', previous, '--attempt'))
    assert latest['attempt_id'] != old['attempt_id'] and latest['run_id'] == old['run_id']
    assert latest['verification_result'] == 'passed' and old['verification_result'] == 'inconclusive'
    results.append({'phase': 'fresh-attempt-retry', 'attempt': latest['attempt_id'], 'cleanup': latest['cleanup_result']})
    (BASE / 'summary.json').write_text(json.dumps(results, indent=2))
    print('M3 acceptance PASS:', BASE, flush=True)


if __name__ == '__main__':
    main()
