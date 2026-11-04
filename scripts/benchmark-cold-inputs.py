"""Evict only designated benchmark input files; never drop host caches globally."""
import argparse,ctypes,fcntl,json,mmap,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BIN=ROOT/'bin/crl'
def evict(path):
 with path.open('rb') as f:
  os.fsync(f.fileno());os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
  with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_COPY) as region:
   pages=(len(region)+mmap.PAGESIZE-1)//mmap.PAGESIZE;vec=(ctypes.c_ubyte*pages)();address=ctypes.addressof(ctypes.c_char.from_buffer(region));libc=ctypes.CDLL(None,use_errno=True)
   assert libc.mincore(ctypes.c_void_p(address),ctypes.c_size_t(len(region)),vec)==0
   resident=sum(bool(v&1) for v in vec)
   assert resident==0,(path,resident,pages)
 return {'file':path.name,'pages':pages,'resident_before_run':resident}
def main():
 p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 with open(Path.home()/'.crl-acceptance.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);base=args.output.resolve();base.mkdir(mode=0o700,parents=True,exist_ok=False);results=[]
  for mib in (100,1024):
   c=json.loads((args.fixture/str(mib)/'drill.yaml').read_text());c['runtime']['work_dir']=str(base/str(mib));config=base/(str(mib)+'.json');config.write_text(json.dumps(c))
   for repeat in range(1,4):
    cache=[evict(p) for p in sorted(Path(c['backup']['path']).iterdir()) if p.is_file()]
    start=time.monotonic();r=subprocess.run([str(BIN),'run','--config',str(config)],cwd=ROOT,capture_output=True,text=True,timeout=600);assert r.returncode==0,(r.stdout,r.stderr)
    path=Path(r.stdout.split('report: ')[-1].strip());report=json.loads(path.read_text());assert report['verification_result']=='passed' and report['cleanup_result']=='complete'
    results.append({'logical_payload_mib':mib,'repetition':repeat,'wall_seconds':time.monotonic()-start,'stages':report['steps'],'cache':'input files nonresident verified by mincore; images warm; no global cache eviction','input_cache':cache,'report':str(path),'cleanup':'complete'});(base/'summary.json').write_text(json.dumps(results,indent=2));print(mib,'MiB cold-input repeat',repeat,'PASS',round(results[-1]['wall_seconds'],3),'s',flush=True)
if __name__=='__main__':main()
