"""Run authorized local configurations sequentially; emit redacted failure events.
No scheduler or webhook is installed/enabled by this script.
"""
import argparse,json,subprocess,sys
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',required=True,type=Path);p.add_argument('--webhook-file',type=Path);p.add_argument('configs',nargs='+',type=Path);a=p.parse_args()
    binary=a.binary.resolve();failed=False
    for config in a.configs:
        result=subprocess.run([str(binary),'run','--config',str(config.resolve())],capture_output=True,text=True)
        if result.returncode:
            failed=True
            paths=[line.removeprefix('report: ') for line in result.stdout.splitlines() if line.startswith('report: ')]
            if not paths:
                print(json.dumps({'event':'configuration-or-preflight-failure','config_name':config.name}),flush=True);continue
            report=json.loads(Path(paths[-1]).read_text());args=[str(binary),'notify','--run',report['attempt_id']]
            if a.webhook_file:args+=['--webhook-file',str(a.webhook_file.resolve())]
            notification=subprocess.run(args)
            if notification.returncode:print(json.dumps({'event':'notification-delivery-failed','attempt_id':report['attempt_id']}),flush=True)
        else:
            print(json.dumps({'event':'scheduled-run-completed','config_name':config.name}),flush=True)
    return int(failed)
if __name__=='__main__':sys.exit(main())
