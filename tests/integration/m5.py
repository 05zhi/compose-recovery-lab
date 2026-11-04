import argparse,json,subprocess,threading
from pathlib import Path
# Serialize acceptance suites; each CLI still enforces its independent account lock.
import fcntl
_suite_lock = open(Path.home() / '.crl-acceptance.lock', 'a')
fcntl.flock(_suite_lock, fcntl.LOCK_EX)

from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2];BIN=ROOT/'bin/crl';p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);args=p.parse_args();BASE=args.output.resolve();BASE.mkdir(mode=0o700);fixture=args.fixture.resolve()
def command(*args,code=0):
 r=subprocess.run([str(BIN),*map(str,args)],capture_output=True,text=True);assert r.returncode==code,(args,r.stdout,r.stderr);return r.stdout
records=json.loads(command('history','--limit','1000'))
passed=next(r for r in records if r['operation']=='run' and r['verification_result']=='passed' and r['cleanup_result']=='complete')
failed=next(r for r in records if r['verification_result']=='failed' and r['cleanup_result']=='complete')
assert json.loads(command('status','--run',passed['attempt_id'],'--attempt'))['attempt_id']==passed['attempt_id']
report=Path(passed['directory'])/'report.html';saved=report.with_suffix('.saved');report.rename(saved)
try:
 html=command('report','--run',passed['attempt_id'],'--attempt','--format','html');assert '<!doctype html>' in html and passed['attempt_id'] in html
finally:saved.rename(report)
assert not command('notify','--run',passed['attempt_id'])
received=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))));self.send_response(204);self.end_headers()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
hook=BASE/'hook.url';hook.write_text(f'http://127.0.0.1:{server.server_port}/notification');hook.chmod(0o600)
try:
 event=json.loads(command('notify','--run',failed['attempt_id'],'--webhook-file',hook));assert received==[event] and set(event)=={'version','attempt_id','verification_result','cleanup_result'}
finally:server.shutdown();server.server_close();thread.join()
# Sequential scheduler: one known SQL assertion failure then a complete run.
c=json.loads((fixture/'drill.yaml').read_text());c['backup']['path']=str(fixture/'bundle');c['runtime'].update(images_file=str((fixture/c['runtime']['images_file']).resolve()),work_dir=str(BASE/'work'),timeout='3m')
good=BASE/'good.json';good.write_text(json.dumps(c));c['checks'].append(dict(id='intentional-failure',type='sql',required=True,query='SELECT 1',expect={'operator':'eq','value':0}));bad=BASE/'bad.json';bad.write_text(json.dumps(c))
r=subprocess.run(['python3',str(ROOT/'scripts/scheduled.py'),'--binary',str(BIN),str(bad),str(good)],capture_output=True,text=True,timeout=180)
assert r.returncode==1,(r.stdout,r.stderr);events=[json.loads(line) for line in r.stdout.splitlines()];assert len(events)==2 and events[0]['verification_result']=='failed' and events[1]['event']=='scheduled-run-completed',events
(BASE/'summary.json').write_text(json.dumps({'history':True,'sqlite_html_regeneration':True,'success_no_notification':True,'failure_loopback_delivery':True,'sequential_schedule':events},indent=2))
print('M5 acceptance PASS')
