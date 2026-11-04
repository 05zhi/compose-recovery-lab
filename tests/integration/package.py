"""Validate the release checksum, contents and a fresh-home installed run."""
import argparse,fcntl,hashlib,json,os,shutil,subprocess,tarfile
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with open(Path.home()/'.crl-acceptance.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);execute(a)
def execute(a):
 archive=a.archive.resolve();expected=(archive.parent/'SHA256SUMS').read_text().split()[0];assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
 out=a.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
 with tarfile.open(archive) as tf:
  members=tf.getmembers()
  for m in members:
   assert not m.name.startswith('/') and '..' not in Path(m.name).parts
   assert not m.name.endswith(('.dump','images.lock.json','.sqlite3')) and '/reports/' not in m.name
   assert not (m.mode&0o022),'group/world writable package file'
  tf.extractall(out,filter='data')
 binary=out/'compose-recovery-lab/bin/crl';assert os.access(binary,os.X_OK)
 home=out/'home';home.mkdir(mode=0o700);shutil.copyfile(a.fixture/'images.json',home/'images.json');(home/'images.json').chmod(0o600)
 c=json.loads((a.fixture/'drill.yaml').read_text());c['backup']['path']=str((a.fixture/c['backup']['path']).resolve());c['runtime'].update(images_file=str(home/'images.json'),work_dir=str(home/'work'),timeout='3m');config=home/'drill.json';config.write_text(json.dumps(c));env=dict(os.environ,HOME=str(home))
 for command in ('doctor','plan','run'):
  r=subprocess.run([str(binary),command,'--config',str(config)],env=env,cwd=out,capture_output=True,text=True,timeout=180);assert r.returncode==0,(command,r.stdout,r.stderr)
  if command=='run':report=Path(r.stdout.split('report: ')[-1].strip())
 r=json.loads(report.read_text());assert r['verification_result']=='passed' and r['cleanup_result']=='complete' and not r['remaining_resources']
 db=home/'.local/state/compose-recovery-lab/history.sqlite3';assert db.is_file() and db.stat().st_mode&0o777==0o600
 history=json.loads(subprocess.check_output([str(binary),'history'],env=env,text=True));assert len(history)==1
 (out/'summary.json').write_text(json.dumps({'archive':str(archive),'sha256':expected,'package_permissions':'checked','fresh_home_history_records':len(history),'verification':'passed','cleanup':'complete','report':str(report),'scope':'fresh extraction and HOME on same validated Linux host; cached trusted images, not independent fresh VM'},indent=2));print('Package installation acceptance PASS:',out)
if __name__=='__main__':main()
