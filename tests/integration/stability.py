"""Repeat full restores with fresh resources, retaining the first failure (no retries)."""
import argparse,fcntl,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--template',choices=['document-app','inventory-app'],required=True)
    parser.add_argument('--runs',type=int,default=20)
    parser.add_argument('--browser-repeats',type=int,default=0,help='extra fresh Chromium E2E sessions per restore; stop on first failure')
    parser.add_argument('--images',type=Path,help='optional trusted image lock for an A/B baseline')
    args=parser.parse_args()
    if not 0<=args.browser_repeats<=20:parser.error('--browser-repeats must be between 0 and 20')
    if not 1<=args.runs<=100:parser.error('--runs must be between 1 and 100')
    with open(Path.home()/'.crl-acceptance.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        execute(args)

def execute(args):
    base=args.output.resolve();base.mkdir(mode=0o700,parents=True,exist_ok=False)
    images=base/'images.json';shutil.copyfile(args.images or ROOT/'examples'/args.template/'images.lock.json',images);images.chmod(0o600)
    records=[]
    env=dict(os.environ)
    repetitions=base/'repetitions';repetitions.mkdir(mode=0o700)
    if args.browser_repeats:
        make_wrapper(base,repetitions,args.browser_repeats)
        env['PATH']=str(base)+':'+env['PATH']
    def run(command,*extra):
        start=time.monotonic();before=set(repetitions.glob('*.json'))
        proc=subprocess.run([str(ROOT/'bin/crl'),command,'--images',str(images),'--work',str(base/'work'),*map(str,extra)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        if 'report: ' not in proc.stdout:raise AssertionError('CLI failed without report: '+proc.stderr)
        path=Path(proc.stdout.split('report: ')[-1].strip());report=json.loads(path.read_text())
        records.append(dict(command=command,exit_code=proc.returncode,seconds=time.monotonic()-start,attempt_id=report['attempt_id'],report=str(path),verification=report['verification_result'],cleanup=report['cleanup_result']))
        (base/'summary.json').write_text(json.dumps(records,indent=2))
        assert proc.returncode==0 and report['verification_result']=='passed',records[-1]
        assert report['cleanup_result']=='complete' and not report['remaining_resources'],records[-1]
        for query in (['ps','-aq'],['volume','ls','-q'],['network','ls','-q']):
            assert not subprocess.check_output(['docker',*query,'--filter','label=io.compose-recovery-lab.run='+report['attempt_id']],text=True).strip()
        if command=='run':
            if args.browser_repeats:
                generated=set(repetitions.glob('*.json'))-before
                assert len(generated)==1,generated
                history=json.loads(generated.pop().read_text())
                assert len(history)==args.browser_repeats and all(x['status']=='passed' for x in history),history
            assert all(c['status']=='passed' for c in report['checks']),report['checks']
            assert 'browser.webm' in report.get('artifacts',[]) and (path.parent/'browser.webm').stat().st_size>0
        return report
    run('backup','--template',args.template+'-v1','--out',base/'bundle')
    for i in range(args.runs):
        run('run','--bundle',base/'bundle')
        print(args.template,i+1,'/',args.runs,'PASS',flush=True)



def make_wrapper(base,repetitions,count):
    program=REPEAT_PROGRAM.replace('COUNT',str(count))
    script=base/'docker'
    script.write_text("#!/usr/bin/python3\n"+WRAPPER.replace('PROGRAM',repr(program)).replace('DESTINATION',repr(str(repetitions))))
    script.chmod(0o700)

WRAPPER = """
import os,sys,subprocess
from pathlib import Path
a=sys.argv[1:]
if a and a[0]=='exec' and a[-2:]==['python','probe.py']:
    result=subprocess.run(['/usr/bin/docker',*a[:-2],'python','-c',PROGRAM],capture_output=True)
    evidence=subprocess.run(['/usr/bin/docker','exec',a[1],'cat','/tmp/stability.json'],capture_output=True)
    if evidence.returncode==0:Path(DESTINATION,a[1]+'.json').write_bytes(evidence.stdout)
    sys.stdout.buffer.write(result.stdout);sys.exit(result.returncode)
os.execv('/usr/bin/docker',['docker',*a])
"""

REPEAT_PROGRAM = """
import contextlib,io,json,re
from pathlib import Path
import probe
from browser_smoke import browser_smoke
from probe_diagnostics import failure_evidence
output=io.StringIO()
with contextlib.redirect_stdout(output):probe.run()
result=json.loads(output.getvalue());history=[]
if all(c['status']=='passed' for c in result):
    for i in range(COUNT):
        for file in Path('/tmp/evidence').glob('*.webm'):file.unlink()
        try:browser_smoke();history.append({'iteration':i,'status':'passed'})
        except Exception as error:
            evidence=failure_evidence(error);history.append({'iteration':i,'status':'failed','evidence':evidence,'native_frames':[line for line in str(error).splitlines() if re.search(r'\\[err\\] (?:#\\d+ 0x|Received signal|\\s*(?:r8|r12|di|dx|ip|efl|cs|err|trp|old|cr2):)',line)][:32]})
            for c in result:
                if c['id'] in ('login-search-download','inventory-export'):c.update(status='failed',evidence=evidence)
            break
Path('/tmp/stability.json').write_text(json.dumps(history))
print(json.dumps(result))
"""
if __name__=='__main__':main()
