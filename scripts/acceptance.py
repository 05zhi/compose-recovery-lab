"""Run the reproducible acceptance suites sequentially on a dedicated Linux host."""
import argparse,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True,help='new private Linux evidence directory');p.add_argument('--resume',action='store_true',help='retain successful suites and preserve failed output before rerunning');a=p.parse_args();base=a.output.resolve();base.mkdir(mode=0o700,parents=True,exist_ok=a.resume)
    cases=[('m2',['--output',base/'m2']),('m1',['--output',base/'m1-document']),('m6',['--template','document-app','--output',base/'m6-document']),('m1',['--template','inventory-app','--output',base/'m1-inventory']),('m6',['--template','inventory-app','--output',base/'m6-inventory']),('m3',['--fixture',base/'m2','--output',base/'m3-document']),('m3',['--fixture',base/'m6-inventory','--output',base/'m3-inventory']),('m4',['--fixture',base/'m2','--output',base/'m4']),('m5',['--fixture',base/'m2','--output',base/'m5']),('diagnostics',['--fixture',base/'m1-document','--output',base/'diagnostics'])]
    cases += [('browser_failure',['--template',name,'--output',base/('browser-signals-'+name)]) for name in ('document-app','inventory-app')]
    cases += [('libc_environment',['--output',base/'libc-environment'])]
    results=[]
    if a.resume:
        results=json.loads((base/'suite-results.json').read_text())
        if results and results[-1]['exit_code']:
            failed=results.pop();failed_dir=Path(failed['arguments'][-1])
            (failed_dir/'suite-failure.json').write_text(json.dumps(failed,indent=2))
            cases[len(results)][1][-1]=failed_dir.with_name(failed_dir.name+'-retry-'+str(time.time_ns()))
        assert all(r['exit_code']==0 for r in results)
        for i,r in enumerate(results):
            assert r['suite']==cases[i][0]
    for name,args in cases[len(results):]:
        start=time.monotonic();result=subprocess.run(['python3',str(ROOT/'tests/integration'/f'{name}.py'),*map(str,args)],cwd=ROOT)
        results.append({'suite':name,'arguments':list(map(str,args)),'exit_code':result.returncode,'seconds':time.monotonic()-start});(base/'suite-results.json').write_text(json.dumps(results,indent=2))
        if result.returncode:raise SystemExit(result.returncode)
    print('All acceptance suites passed:',base)
if __name__=='__main__':main()
