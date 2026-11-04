"""Prepare both pinned adapters before offline drills. Build contexts are allowlisted."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
POSTGRES='postgres@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3'
def main():
    env={k:os.environ[k] for k in ('PATH','HOME') if k in os.environ};env['DOCKER_HOST']='unix:///var/run/docker.sock'
    subprocess.run(['docker','pull',POSTGRES],env=env,check=True)
    base=None
    for name in ('document-app','inventory-app'):
        with tempfile.TemporaryDirectory(prefix='crl-build-') as temp:
            context=Path(temp)/'context';context.mkdir();iid=Path(temp)/'image-id'
            files=['Dockerfile','app.py','smoke.py','probe.py','browser_smoke.py','ui.html']
            if name=='document-app':files+=['requirements.txt']
            dest=context if name=='document-app' else context/'examples/inventory-app';dest.mkdir(parents=True,exist_ok=True)
            for f in files:shutil.copy2(ROOT/'examples'/name/f,dest/f)
            command=['docker','build','--iidfile',str(iid)]
            if name=='inventory-app':
                common=context/'examples/document-app';common.mkdir(parents=True);shutil.copy2(ROOT/'examples/document-app/app.py',common/'app.py')
                command+=['--build-arg','BASE='+base,'-f',str(dest/'Dockerfile')]
            subprocess.run([*command,str(context)],env=env,check=True);image=iid.read_text().strip()
        lock=ROOT/'examples'/name/'images.lock.json';lock.write_text(json.dumps({'postgres':POSTGRES,'app':image},indent=2)+'\n');lock.chmod(0o600)
        if name=='document-app':base=image
        print('Trusted local image lock:',lock,flush=True)
if __name__=='__main__':main()
