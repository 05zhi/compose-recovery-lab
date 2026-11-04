"""Real Playwright child-process signals must fail the drill without leaking stderr."""
import argparse,fcntl,json,os,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MARKER='SYNTHETIC_BROWSER_STDERR_MUST_NOT_LEAK'

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--template',choices=['document-app','inventory-app'],required=True)
    args=p.parse_args()
    with open(Path.home()/'.crl-acceptance.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);execute(args)

def execute(args):
    base=args.output.resolve();base.mkdir(mode=0o700,parents=True,exist_ok=False)
    images=base/'images.json';shutil.copyfile(ROOT/'examples'/args.template/'images.lock.json',images);images.chmod(0o600)
    records=[]
    def call(case,command,*extra,env=None):
        proc=subprocess.run([str(ROOT/'bin/crl'),command,'--images',str(images),'--work',str(base/'work'),*map(str,extra)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        assert 'report: ' in proc.stdout,(case,proc.returncode)
        path=Path(proc.stdout.split('report: ')[-1].strip());report=json.loads(path.read_text())
        records.append(dict(case=case,exit_code=proc.returncode,report=str(path),verification=report['verification_result'],cleanup=report['cleanup_result']))
        (base/'summary.json').write_text(json.dumps(records,indent=2))
        assert report['cleanup_result']=='complete' and not report['remaining_resources'],records[-1]
        for query in (['ps','-aq'],['volume','ls','-q'],['network','ls','-q']):
            assert not subprocess.check_output(['/usr/bin/docker',*query,'--filter','label=io.compose-recovery-lab.run='+report['attempt_id']],text=True).strip()
        assert MARKER not in path.read_text()+proc.stdout+proc.stderr
        return proc,report,path
    proc,report,_=call('backup','backup','--template',args.template+'-v1','--out',base/'bundle')
    assert proc.returncode==0 and report['verification_result']=='passed'
    for signal in ('SEGV','ABRT'):
        shim=base/signal;shim.mkdir(mode=0o700)
        program=INJECT.replace('SIGNAL',signal).replace('MARKER',MARKER)
        wrapper=shim/'docker'
        wrapper.write_text('#!/usr/bin/python3\nimport os,sys\na=sys.argv[1:]\nif a and a[0]=="exec" and a[-2:]==["python","probe.py"]:a=a[:-2]+["python","-c",'+repr(program)+']\nos.execv("/usr/bin/docker",["docker",*a])\n')
        wrapper.chmod(0o700)
        proc,report,path=call(signal,'run','--bundle',base/'bundle',env=dict(os.environ,PATH=str(shim)+':'+os.environ['PATH']))
        assert proc.returncode!=0 and report['verification_result']=='failed',records[-1]
        expected='login-search-download' if args.template=='document-app' else 'inventory-export'
        checks={c['id']:c for c in report['checks']}
        assert checks[expected]['status']=='failed',checks
        assert 'category=browser-sig'+signal.lower() in checks[expected]['evidence'],checks[expected]
        assert 'location=browser_smoke.py:' in checks[expected]['evidence'],checks[expected]
        assert all(c['status']=='passed' for key,c in checks.items() if key!=expected),checks
        assert 'browser.webm' not in report.get('artifacts',[]) and not (path.parent/'browser.webm').exists()
        print(args.template,signal,'correct failure, redaction and cleanup PASS',flush=True)

INJECT = r"""
from pathlib import Path
from playwright.sync_api import BrowserType
executable=Path('/tmp/crl-fault-browser')
executable.write_text('#!/bin/sh\nulimit -c 0\nprintf "MARKER\\n" >&2\nkill -s SIGNAL $$\n')
executable.chmod(0o700)
original=BrowserType.launch
def failing_launch(self,*args,**kwargs):
    kwargs['executable_path']='/bin/sh'
    kwargs['ignore_default_args']=True
    kwargs['args']=[str(executable)]
    return original(self,*args,**kwargs)
BrowserType.launch=failing_launch
import probe
probe.run()
"""
if __name__=='__main__':main()
