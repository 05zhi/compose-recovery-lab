"""Warm-image compressible PostgreSQL payload benchmarks (not an RTO guarantee).
100 MiB and 1 GiB logical payloads; TOAST compression disabled, dump compression retained.
Every restore verifies business flows, row count, logical byte count and one payload sample.
"""
import argparse,fcntl,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BIN=ROOT/'bin/crl'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with open(Path.home()/'.crl-acceptance.lock','a') as lock:fcntl.flock(lock,fcntl.LOCK_EX);execute(a.output.resolve())
def execute(base):
 base.mkdir(mode=0o700,parents=True,exist_ok=False);images=base/'images.json';shutil.copyfile(ROOT/'examples/document-app/images.lock.json',images);results=[]
 for mib in (100,1024):
  case=base/str(mib);case.mkdir();shim=case/'shim';shim.mkdir();script=shim/'docker';rows=mib*32
  sql=f"SET ROLE demo; CREATE TABLE benchmark_payload(id integer PRIMARY KEY,payload text NOT NULL); ALTER TABLE benchmark_payload ALTER COLUMN payload SET STORAGE EXTERNAL; INSERT INTO benchmark_payload SELECT i,repeat(md5(i::text),1024) FROM generate_series(1,{rows}) i;"
  script.write_text('''#!/usr/bin/python3
import subprocess,sys
a=sys.argv[1:];code=subprocess.call(['/usr/bin/docker',*a])
if code==0 and a[:1]==['compose'] and a[-3:]==['python','app.py','seed']:
 project=a[a.index('-p')+1];db=subprocess.check_output(['/usr/bin/docker','ps','-q','--filter','label=io.compose-recovery-lab.run='+project,'--filter','label=com.docker.compose.service=db'],text=True).strip()
 subprocess.run(['/usr/bin/docker','exec','-i',db,'psql','-X','-v','ON_ERROR_STOP=1','-U','bootstrap','-d','documents'],input='''+repr(sql.encode())+''',stdout=subprocess.DEVNULL,check=True)
sys.exit(code)
''');script.chmod(0o700)
  env=dict(os.environ,PATH=str(shim)+':'+os.environ['PATH'])
  r=subprocess.run([str(BIN),'backup','--images',str(images),'--work',str(case/'producer'),'--out',str(case/'bundle')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=600);assert r.returncode==0,(mib,r.stdout,r.stderr)
  c={'schema_version':1,'name':'benchmark-'+str(mib),'template':'document-app-v1','backup':{'type':'local_bundle','path':str(case/'bundle'),'mapping':{'database':'database.dump','uploads':'uploads.tar','app_config':'app-config.sanitized.json'}},'runtime':{'images_file':str(images),'work_dir':str(case/'work'),'timeout':'10m'},'checks':[{'id':x,'required':True} for x in ('sql-documents','database-files','login-search-download','external-connectivity')],'report':{'formats':['json','html']}}
  for id,query,value,operator in [('rows','SELECT count(*) FROM benchmark_payload',rows,'eq'),('logical-bytes','SELECT sum(octet_length(payload)) FROM benchmark_payload',mib*1024*1024,'eq'),('sample',"SELECT payload=repeat(md5(id::text),1024) FROM benchmark_payload WHERE id=1",True,'eq'),('database-bytes','SELECT pg_database_size(current_database())',mib*1024*1024,'gte')]:c['checks'].append({'id':'benchmark-'+id,'type':'sql','required':True,'query':query,'expect':{'operator':operator,'value':value}})
  config=case/'drill.yaml';config.write_text(json.dumps(c))
  for repetition in range(1,4):
   start=time.monotonic();free_start=shutil.disk_usage('/var/lib/docker').free;min_free=free_start
   proc=subprocess.Popen([str(BIN),'run','--config',str(config)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   while proc.poll() is None:min_free=min(min_free,shutil.disk_usage('/var/lib/docker').free);time.sleep(.1)
   stdout,stderr=proc.communicate();assert proc.returncode==0,(mib,stdout,stderr)
   report_path=Path(stdout.split('report: ')[-1].strip());report=json.loads(report_path.read_text());assert report['verification_result']=='passed' and report['cleanup_result']=='complete'
   result={'logical_payload_mib':mib,'repetition':repetition,'wall_seconds':time.monotonic()-start,'stages':report['steps'],'dump_bytes':(case/'bundle/database.dump').stat().st_size,'database_bytes':json.loads(next(x for x in report['checks'] if x['id']=='benchmark-database-bytes')['evidence'])['actual'],'sampled_docker_filesystem_delta_bytes':max(0,free_start-min_free),'report':str(report_path),'cleanup':'complete','cache':'warm local images; OS cache uncontrolled','coverage':'row count, total payload length, first payload value, all fixture business checks; not a hash of every payload'}
   results.append(result);(base/'summary.json').write_text(json.dumps(results,indent=2));print(mib,'MiB repeat',repetition,'PASS',round(result['wall_seconds'],3),'s',flush=True)
 print('Benchmark complete:',base,flush=True)
if __name__=='__main__':main()
