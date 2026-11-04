"""Real restored PostgreSQL and isolated HTTP/file checker acceptance."""
import argparse,copy,json,subprocess,tarfile
from pathlib import Path
# Serialize acceptance suites; each CLI still enforces its independent account lock.
import fcntl
_suite_lock = open(Path.home() / '.crl-acceptance.lock', 'a')
fcntl.flock(_suite_lock, fcntl.LOCK_EX)

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);args=p.parse_args();BASE=args.output.resolve();BASE.mkdir(mode=0o700);fixture=args.fixture.resolve()
CLI=str(Path('bin/crl').resolve())
c=json.loads((fixture/'drill.yaml').read_text())
c['backup']['path']=str(fixture/'bundle')
c['runtime'].update(images_file=str((fixture/c['runtime']['images_file']).resolve()),work_dir=str(BASE/'work'),timeout='3m')
with tarfile.open(Path(c['backup']['path'])/'uploads.tar') as tf:
 import hashlib
 digest=hashlib.sha256(tf.extractfile('document-01.txt').read()).hexdigest()
extra=[{'id':'count','type':'sql','required':True,'query':'SELECT count(*) FROM documents','expect':{'operator':'eq','value':10}},
 {'id':'one-file','type':'file','required':True,'root':'uploads','path':'document-01.txt','sha256':digest},
 {'id':'sample','type':'database_files','required':True,'query':'SELECT storage_path, sha256 FROM documents','root':'uploads','scope':{'mode':'sample','size':3,'seed':42}},
 {'id':'health','type':'http','required':True,'path':'/health','status':200}]
c['checks']+=extra
def run(name,config,expected):
 p=BASE/(name+'.json');p.write_text(json.dumps(config))
 result=subprocess.run([CLI,'run','--config',str(p)],capture_output=True,text=True)
 assert 'report: ' in result.stdout,(name,result.stdout,result.stderr)
 report=json.loads(Path(result.stdout.split('report: ')[-1].strip()).read_text())
 assert report['verification_result']==expected,(name,report)
 assert report['cleanup_result']=='complete' and not report['remaining_resources'],report
 assert (result.returncode==0)==(expected=='passed'),result
 (BASE/(name+'-report.json')).write_text(json.dumps(report,indent=2))
 print(name,'PASS',flush=True)
 return report
r=run('all-checkers',c,'passed');sample=next(x for x in r['checks'] if x['id']=='sample');assert sample['coverage']=={'mode':'sample','population':10,'checked':3,'unchecked':7,'seed':42}
bad=copy.deepcopy(c);bad['checks'][4]['expect']['value']=0;run('sql-mismatch',bad,'failed')
bad=copy.deepcopy(c);bad['checks'][5]['sha256']='0'*64;run('file-mismatch',bad,'failed')
bad=copy.deepcopy(c);bad['checks'][6]['query']="SELECT '../escape', repeat('0',64)";bad['checks'][6]['scope']={'mode':'all'};run('db-path-escape',bad,'failed')
bad=copy.deepcopy(c);bad['checks'][7]['status']=404;run('http-mismatch',bad,'failed')
bad=copy.deepcopy(c);bad['checks'][4]['query']="SELECT pg_sleep(7)";run('sql-timeout',bad,'inconclusive')
bad=copy.deepcopy(c);bad['checks'][4]['query']="SELECT lo_create(0)";run('sql-write-denied',bad,'inconclusive')
bad=copy.deepcopy(c);bad['checks'][4]['query']='SELECT 1 UNION ALL SELECT 2';run('sql-row-limit',bad,'failed')
bad=copy.deepcopy(c);bad['checks'][4]['query']="SELECT 1); DELETE FROM documents; SELECT 1 --";run('stacked-query-denied',bad,'inconclusive')
bad=copy.deepcopy(c);bad['checks'][6]['query']="SELECT '../escape', repeat('0',64) FROM generate_series(1,10)";bad['checks'][6]['scope']={'mode':'all'};r=run('early-failure-coverage',bad,'failed');coverage=next(x for x in r['checks'] if x['id']=='sample')['coverage'];assert coverage['checked']==1 and coverage['unchecked']==9
safe=copy.deepcopy(c);safe['checks'][4]['query']="SELECT has_table_privilege(current_user, 'documents','INSERT') OR has_database_privilege(current_user,current_database(),'TEMP')";safe['checks'][4]['expect']['value']=False;run('restricted-role',safe,'passed')
print('M4 acceptance PASS',flush=True)
