"""Build a Linux release archive from committed allowlisted source files."""
import argparse,hashlib,os,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def normalized(info):
    info.uid=info.gid=0;info.uname=info.gname=''
    info.mode=0o755 if info.isdir() or info.name.endswith('/bin/crl') else 0o644
    return info
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    commit=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'rev-parse','--short','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'status','--porcelain'],cwd=ROOT):commit+='-dirty'
    files=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'ls-files','-z'],cwd=ROOT).decode().split('\0')
    with tempfile.TemporaryDirectory(prefix='crl-package-') as temp:
        binary=Path(temp)/'crl';subprocess.run(['go','build','-buildvcs=false','-trimpath','-o',str(binary),'./cmd/crl'],cwd=ROOT,check=True)
        archive=out/f'compose-recovery-lab-{commit}-linux-amd64.tar.gz'
        with tarfile.open(archive,'w:gz') as tf:
            for name in files:
                if name and (name.startswith(('cmd/','internal/','scripts/','examples/','docs/','tests/')) or name in ('go.mod','go.sum','README.md','LICENSE','AGENTS.md','.gitignore')):tf.add(ROOT/name,arcname='compose-recovery-lab/'+name,filter=normalized)
            tf.add(binary,arcname='compose-recovery-lab/bin/crl',filter=normalized)
    (out/'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(archive)
if __name__=='__main__':main()
