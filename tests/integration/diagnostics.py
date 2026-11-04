import argparse,fcntl,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
with open(Path.home()/'.crl-acceptance.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 r=subprocess.run([str(ROOT/'bin/crl'),'run','--bundle',str(args.fixture/'bad-dump'),'--images',str(args.fixture/'images.json'),'--work',str(args.output)],cwd=ROOT,capture_output=True,text=True)
 assert r.returncode==1,(r.stdout,r.stderr)
 p=Path(r.stdout.split('report: ')[-1].strip());report=json.loads(p.read_text());data=json.loads((p.parent/'diagnostics.json').read_text())
 assert report['cleanup_result']=='complete' and data and any(x['service']=='db' and x['status']=='running' for x in data),data
 assert any('database system is ready to accept connections' in x['redacted_log_lines'] for x in data),data
 print('Real safe service diagnostics PASS',p)
