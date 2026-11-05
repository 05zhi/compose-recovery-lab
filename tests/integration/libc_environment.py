"""Run the getenv/setenv race against the exact trusted application image."""
import argparse,json,re,subprocess,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',help='immutable image ID; defaults to document template lock')
    p.add_argument('--runs',type=int,default=10);args=p.parse_args()
    if not 1<=args.runs<=50:p.error('runs must be between 1 and 50')
    image=args.image or json.loads((ROOT/'examples/document-app/images.lock.json').read_text())['app']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',image):p.error('immutable image ID required')
    out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False);binary=out/'getenv-race'
    # Uses only libc symbols available since glibc 2.34; GCC is already required
    # for the project's Go/SQLite build. No compiler is added to runtime images.
    subprocess.run(['gcc','-O2','-pthread','-Wall','-Wextra','-Werror','-o',str(binary),str(ROOT/'tests/native/getenv_race.c')],check=True,timeout=30)
    records=[]
    for i in range(args.runs):
        name='crl-getenv-'+uuid.uuid4().hex[:16];label='io.compose-recovery-lab.native-test'
        start=time.monotonic()
        try:
            command=['docker','run','--name',name,'--label',label+'='+name,'--network','none','--read-only','--memory','768m','--pids-limit','256','--cpus','1','--cap-drop','ALL','--security-opt','no-new-privileges:true','--user','10001:10001','--mount','type=bind,source='+str(binary)+',target=/crl-getenv-race,readonly',image,'/crl-getenv-race']
            proc=subprocess.run(command,capture_output=True,text=True,timeout=90)
            records.append(dict(iteration=i,image=image,exit_code=proc.returncode,seconds=time.monotonic()-start,stdout=proc.stdout,stderr=proc.stderr))
        except subprocess.TimeoutExpired:
            records.append(dict(iteration=i,image=image,exit_code=None,timeout=True));raise
        finally:
            found=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
            if found.returncode==0:
                data=json.loads(found.stdout)[0];assert data['Config']['Labels'][label]==name
                subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL)
            assert not subprocess.check_output(['docker','ps','-aq','--filter','label='+label+'='+name],text=True).strip()
            (out/'summary.json').write_text(json.dumps(records,indent=2))
        assert proc.returncode==0 and re.search(r'completed=20000 reads=[1-9][0-9]*',proc.stdout),records[-1]
        print('getenv concurrency',i+1,'/',args.runs,'PASS',flush=True)
if __name__=='__main__':main()
