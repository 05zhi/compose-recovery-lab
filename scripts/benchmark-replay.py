"""Evict only designated benchmark input files; never drop host caches globally."""
import argparse,ctypes,fcntl,json,mmap,os,shutil,subprocess,time
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
 p=argparse.ArgumentParser();p.add_argument('--cache',choices=['warm','cold'],required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 with open(Path.home()/'.crl-acceptance.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);base=args.output.resolve();base.mkdir(mode=0o700,parents=True,exist_ok=False);results=[]
  for mib in (100,1024):
   c=json.loads((args.fixture/str(mib)/'drill.yaml').read_text());c['runtime']['work_dir']=str(base/str(mib));config=base/(str(mib)+'.json');config.write_text(json.dumps(c))
   for repeat in range(1,4):
    paths=[p for p in sorted(Path(c['backup']['path']).iterdir()) if p.is_file()]
    if args.cache=='cold':cache=[evict(p) for p in paths]
    else:
     cache=[]
     for p in paths:
      with p.open('rb') as stream:
       while stream.read(1024*1024):pass
    start=time.monotonic();free_start=shutil.disk_usage('/var/lib/docker').free;minimum=free_start
    def work_bytes():return sum(p.stat().st_size for p in Path(c['runtime']['work_dir']).rglob('*') if p.is_file())
    work_start=work_bytes();peak=work_start
    r=subprocess.Popen([str(BIN),'run','--config',str(config)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    while r.poll() is None:
     minimum=min(minimum,shutil.disk_usage('/var/lib/docker').free)
     try:peak=max(peak,work_bytes())
     except FileNotFoundError:pass
     time.sleep(.1)
    stdout,stderr=r.communicate();assert r.returncode==0,(stdout,stderr)
    path=Path(stdout.split('report: ')[-1].strip());report=json.loads(path.read_text());assert report['verification_result']=='passed' and report['cleanup_result']=='complete'
    results.append({'logical_payload_mib':mib,'repetition':repeat,'wall_seconds':time.monotonic()-start,'stages':report['steps'],'cache':'input files nonresident verified by mincore; images warm; no global cache eviction' if args.cache=='cold' else 'input files read immediately before run; images warm','input_cache':cache,'report':str(path),'cleanup':'complete','sampled_docker_filesystem_delta_bytes':max(0,free_start-minimum),'sampled_workspace_delta_bytes':max(0,peak-work_start),'sampling_interval_seconds':0.1,'dump_bytes':(Path(c['backup']['path'])/'database.dump').stat().st_size,'database_bytes':json.loads(next(x for x in report['checks'] if x['id']=='benchmark-database-bytes')['evidence'])['actual']});(base/'summary.json').write_text(json.dumps(results,indent=2));print(mib,'MiB ',args.cache+'-input repeat',repeat,'PASS',round(results[-1]['wall_seconds'],3),'s',flush=True)
if __name__=='__main__':main()
