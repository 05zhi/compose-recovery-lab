"""Additional real-container fault matrix for both trusted adapters."""
import argparse,copy,hashlib,io,json,os,shutil,signal,subprocess,tarfile,time
from pathlib import Path
# Serialize acceptance suites; each CLI still enforces its independent account lock.
import fcntl
_suite_lock = open(Path.home() / '.crl-acceptance.lock', 'a')
fcntl.flock(_suite_lock, fcntl.LOCK_EX)

ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'bin/crl'
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--template',choices=['document-app','inventory-app'],required=True);a=p.parse_args()
    base=a.output.resolve();base.mkdir(mode=0o700);work=base/'work';lock=ROOT/'examples'/a.template/'images.lock.json';summary=[];shutil.copyfile(lock,base/'images.json');lock=base/'images.json'
    env=dict(os.environ,DOCKER_HOST='unix:///var/run/docker.sock')
    def call(case,command,*args,success=True,custom_env=env):
        r=subprocess.run([str(BIN),command,'--work',str(work),'--images',str(lock),*map(str,args)],cwd=ROOT,env=custom_env,capture_output=True,text=True,timeout=200)
        assert (r.returncode==0)==success,(case,r.stdout,r.stderr)
        assert 'report: ' in r.stdout,(case,r.stdout,r.stderr)
        path=Path(r.stdout.split('report: ')[-1].strip());report=json.loads(path.read_text())
        assert report['cleanup_result']=='complete' and not report['remaining_resources'],(case,report)
        summary.append({'case':case,'verification':report['verification_result'],'cleanup':report['cleanup_result'],'report':str(path)})
        print(a.template,case,report['verification_result'],'PASS',flush=True);return report,path
    call('backup','backup','--template',a.template+'-v1','--out',base/'complete')
    ids=['sql-documents','database-files','login-search-download','external-connectivity'] if a.template=='document-app' else ['sql-inventory','database-files','inventory-export','external-connectivity']
    config={'schema_version':1,'name':a.template,'template':a.template+'-v1','backup':{'type':'local_bundle','path':'./complete','mapping':{'database':'database.dump','uploads':'uploads.tar','app_config':'app-config.sanitized.json'}},'runtime':{'images_file':'./images.json','work_dir':'./configured-work','timeout':'3m'},'checks':[{'id':x,'required':True} for x in ids],'report':{'formats':['json','html']}}
    (base/'drill.yaml').write_text(json.dumps(config))
    for name in ['complete','repeat']:call(name,'run','--bundle',base/'complete')
    call('missing-backup','backup','--template',a.template+'-v1','--out',base/'missing','--omit-attachment')
    r,_=call('missing-attachment','run','--bundle',base/'missing',success=False);assert any(x['id']=='database-files' and x['status']=='failed' for x in r['checks'])
    def variant(name):
        target=base/name;shutil.copytree(base/'complete',target);return target
    def rehash(path):
        m=json.loads((path/'manifest.json').read_text())
        for name in m['files']:
            b=(path/name).read_bytes();m['files'][name]={'size':len(b),'sha256':hashlib.sha256(b).hexdigest()}
        (path/'manifest.json').write_text(json.dumps(m))
    wrong=variant('wrong');archive=wrong/'uploads.tar'
    with tarfile.open(archive) as tf:entries=[(m,tf.extractfile(m).read() if m.isfile() else None) for m in tf.getmembers()]
    changed=False
    with tarfile.open(archive,'w') as tf:
        for m,b in entries:
            if b is not None and not changed:b=b'wrong content';m.size=len(b);changed=True
            tf.addfile(m,io.BytesIO(b) if b is not None else None)
    rehash(wrong);call('wrong-attachment','run','--bundle',wrong,success=False)
    version=variant('version');m=json.loads((version/'manifest.json').read_text());m['postgres_major']=18;(version/'manifest.json').write_text(json.dumps(m));r,_=call('version-blocked','run','--bundle',version,success=False);assert all(x['status']=='skipped' for x in r['checks'])
    for fault in ['empty-database','db-path-escape','unreadable-file','startup-failure','required-skipped']:
        shim=base/fault;shim.mkdir();script=shim/'docker'
        sql="DELETE FROM documents" if a.template=='document-app' else 'DELETE FROM stock; DELETE FROM products'
        if fault=='db-path-escape':sql="UPDATE documents SET storage_path='../escape' WHERE id=1" if a.template=='document-app' else "UPDATE products SET spec_path='../escape' WHERE id=1"
        first='document-01.txt' if a.template=='document-app' else 'specs/sku-01.txt'
        script.write_text('''#!/usr/bin/python3
import sys,subprocess,json
args=sys.argv[1:]
fault='''+repr(fault)+'''
if fault=='required-skipped' and args[-2:]==['python','probe.py']:
 print('[]');sys.exit(0)
code=subprocess.call(['/usr/bin/docker',*args])
if code==0 and fault in ('empty-database','db-path-escape') and 'pg_restore' in args:
 db=args[2];subprocess.run(['/usr/bin/docker','exec','-i',db,'psql','-X','-v','ON_ERROR_STOP=1','-U','bootstrap','-d','documents'],input='''+repr(sql.encode())+''',check=True,stdout=subprocess.DEVNULL)
if code==0 and fault in ('unreadable-file','startup-failure') and args[:1]==['compose'] and args[-3:]==['up','-d','app']:
 project=args[args.index('-p')+1];app=subprocess.check_output(['/usr/bin/docker','ps','-aq','--filter','label=io.compose-recovery-lab.run='+project,'--filter','label=com.docker.compose.service=app'],text=True).strip()
 if fault=='unreadable-file':subprocess.run(['/usr/bin/docker','exec','--user','10001:10001',app,'chmod','000','/uploads/'''+first+''''],check=True)
 else:subprocess.run(['/usr/bin/docker','stop','--time','0',app],check=True,stdout=subprocess.DEVNULL)
sys.exit(code)
''');script.chmod(0o700)
        r,_=call(fault,'run','--bundle',base/'complete','--timeout','25s' if fault=='startup-failure' else '3m',success=False,custom_env=dict(env,PATH=str(shim)+':'+os.environ['PATH']))
        assert r['verification_result']!='passed'
        if fault=='unreadable-file':assert r['verification_result']=='failed' and any(x['id']=='database-files' and x['status']=='failed' for x in r['checks']),r
    # Kill in the external-side-effect/journal gap after Docker creates the DB.
    shim=base/'intent-gap';shim.mkdir();script=shim/'docker'
    script.write_text('''#!/usr/bin/python3
import os,sys,signal,subprocess
a=sys.argv[1:];c=subprocess.call(['/usr/bin/docker',*a])
if c==0 and a[:1]==['compose'] and a[-4:]==['up','-d','--wait','db']:os.kill(os.getppid(),signal.SIGKILL)
sys.exit(c)
''');script.chmod(0o700)
    before=set(work.iterdir());r=subprocess.run([str(BIN),'run','--bundle',str(base/'complete'),'--images',str(lock),'--work',str(work)],cwd=ROOT,env=dict(env,PATH=str(shim)+':'+os.environ['PATH']),capture_output=True,timeout=90)
    assert r.returncode!=0
    attempt=(set(work.iterdir())-before).pop();journal=json.loads((attempt/'resources.json').read_text());assert not journal['resources'],journal
    subprocess.run([str(BIN),'recover'],cwd=ROOT,check=True,capture_output=True,timeout=90)
    recovered=json.loads((attempt/'report.json').read_text());assert recovered['cleanup_result']=='complete' and recovered['verification_result']=='inconclusive'
    for kind,args in [('container',['ps','-aq']),('volume',['volume','ls','-q']),('network',['network','ls','-q'])]:assert not subprocess.check_output(['docker',*args,'--filter','label=io.compose-recovery-lab.run='+journal['run_id']],env=env,text=True).strip()
    summary.append({'case':'create-journal-gap','verification':'inconclusive','cleanup':'complete','report':str(attempt/'report.json')});print(a.template,'create-journal-gap PASS',flush=True)
    (base/'summary.json').write_text(json.dumps(summary,indent=2))
if __name__=='__main__':main()
