"""Real Chromium startup/recording regression without a DB, app, or credentials."""
import argparse,json,re,subprocess,time,uuid
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True,help='immutable trusted image ID')
    parser.add_argument('--mode',choices=['shell','chromium','configured'],required=True)
    parser.add_argument('--runs',type=int,default=300)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',args.image):parser.error('immutable image required')
    if not 1<=args.runs<=1000:parser.error('runs must be between 1 and 1000')
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    name='crl-browser-test-'+uuid.uuid4().hex[:16];label='io.compose-recovery-lab.browser-test='+name
    program=PROGRAM.replace('RUNS',str(args.runs)).replace('MODE',repr(args.mode))
    net=None
    start=time.monotonic()
    try:
        net=subprocess.check_output(['docker','network','create','--internal','--label',label,name],text=True).strip()
        command=['docker','run','--rm','--name',name,'--label',label,'--init','--network',net,'--read-only','--tmpfs','/tmp:rw,nosuid,size=256m,mode=1777','--memory','768m','--pids-limit','256','--cpus','1','--cap-drop','ALL','--security-opt','no-new-privileges:true','-i',args.image,'python','-u','-']
        p=subprocess.run(command,input=program,capture_output=True,text=True,timeout=max(180,args.runs*4))
        (out/'output.log').write_text(p.stdout+p.stderr)
        events=[json.loads(line) for line in p.stdout.splitlines() if line.startswith('{')]
        result=dict(image=args.image,mode=args.mode,requested=args.runs,exit_code=p.returncode,seconds=time.monotonic()-start,events=events)
        (out/'summary.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
        if p.returncode or not events or events[-1].get('completed')!=args.runs:raise SystemExit(1)
    finally:
        # Names are unique; check our exact label before removing an extant object.
        for kind,ident in [('container',name),('network',net)]:
            if not ident:continue
            inspect=subprocess.run(['docker',kind,'inspect',ident],capture_output=True,text=True)
            if inspect.returncode:continue
            data=json.loads(inspect.stdout)[0]
            labels=data['Config']['Labels'] if kind=='container' else data['Labels']
            assert labels.get('io.compose-recovery-lab.browser-test')==name
            command=['docker','rm','-f',ident] if kind=='container' else ['docker','network','rm',ident]
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL)

PROGRAM = r"""
import json,re,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
folder=Path('/tmp/evidence');folder.mkdir()
def counters():
    result={}
    for item in ('pids/pids.events','memory/memory.failcnt','memory/memory.oom_control'):
        p=Path('/sys/fs/cgroup')/item
        if p.exists():result[item]=p.read_text().strip()
    return result
for i in range(RUNS):
    stage='launch'
    try:
        with sync_playwright() as p:
            if MODE=='configured':
                from browser_runtime import launch_browser
                browser=launch_browser(p)
            else:
                kwargs={'channel':'chromium'} if MODE=='chromium' else {}
                browser=p.chromium.launch(args=['--disable-dev-shm-usage'],**kwargs)
            if i==0:print(json.dumps({'browser_version':browser.version}),flush=True)
            stage='context';context=browser.new_context(record_video_dir=str(folder),viewport={'width':1280,'height':720})
            stage='page';page=context.new_page()
            page.set_content('<html><body><button>synthetic test</button></body></html>')
            page.get_by_role('button').click()
            stage='video';video=page.video;video.path();context.close();video.save_as(str(folder/'browser.webm'))
            assert (folder/'browser.webm').stat().st_size>0
            stage='close';browser.close()
        for file in folder.glob('*.webm'):file.unlink()
    except Exception as error:
        # This fixture has no accounts, DB, URLs or credentials. Retain the native
        # startup stack only here; production probes always redact raw errors.
        print(json.dumps({'failed_iteration':i,'stage':stage,'error':str(error),'counters':counters()}),flush=True)
        sys.exit(1)
    if (i+1)%50==0:print(json.dumps({'completed':i+1}),flush=True)
print(json.dumps({'completed':RUNS,'counters':counters()}),flush=True)
"""
if __name__=='__main__':main()
