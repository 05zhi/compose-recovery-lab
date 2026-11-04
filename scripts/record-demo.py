"""Record a three-minute evidence walkthrough, not a simulated live drill.
All assertion tables come from actual reports supplied by --evidence.
"""
import argparse,html,json,subprocess
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True,help='JSON mapping complete,missing,crash,inventory to real report files');p.add_argument('--images',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    reports={k:json.loads(Path(v).read_text()) for k,v in json.loads(a.evidence.read_text()).items()}
    assert reports['complete']['verification_result']=='passed' and reports['missing']['verification_result']=='failed' and reports['crash']['verification_result']=='inconclusive' and reports['inventory']['verification_result']=='passed'
    def table(r):
        return '<p>Attempt: '+html.escape(r['attempt_id'])+'</p><p>Verification: <b>'+r['verification_result']+'</b> · Cleanup: <b>'+r['cleanup_result']+'</b></p><table>'+''.join('<tr><td>'+html.escape(c['id'])+'</td><td>'+html.escape(c['status'])+'</td><td>'+html.escape(c['evidence'])+'</td></tr>' for c in r['checks'])+'</table>'
    slides=[('Compose Recovery Lab','<p>Recorded walkthrough of real acceptance evidence.</p><p>Restore PostgreSQL + attachments into fresh isolated Docker resources, then check actual application behavior.</p><p>Two trusted synthetic templates: documents and warehouse inventory.</p>',25),
    ('A structurally valid backup can still be incomplete',table(reports['missing'])+'<p>The database check passes, but attachment and application checks fail. These observations do not prove the cause of the missing file.</p>',35),
    ('Complete backup: verify the restored application',table(reports['complete'])+'<p>Chromium signs in, searches, downloads and verifies content. API tests inspect every fixture attachment.</p>',35),
    ('Crash recovery keeps the incomplete attempt',table(reports['crash'])+'<p>SQLite records intent before Docker operations. Recovery reconciles labels and resource IDs, cleans old resources and preserves inconclusive evidence. Retry creates a new attempt.</p>',30),
    ('A second data model reuses the runner',table(reports['inventory'])+'<p>Products + warehouses + stock, six nested specifications, and CSV inventory aggregation. The backup, restore, isolation, cleanup and reporting core is shared.</p>',35),
    ('Scope and limits','<p>Measured evidence covers these synthetic fixtures on the recorded Linux environment.</p><p>Internal networking is not a hostile-code sandbox. No production restore, arbitrary Compose support or RTO guarantee.</p><p>Large-data timings are documented separately; independent human trials remain pending.</p><p>See repository acceptance documentation for commands, commits and raw report locations.</p>',25)]
    style='<style>body{font:23px system-ui;background:#102d3a;color:#edf6fa;margin:0;padding:50px}h1{font-size:38px;color:#69d9cc}p{line-height:1.55}table{width:100%;border-collapse:collapse;font-size:18px}td{padding:14px;border-bottom:1px solid #36515c}footer{position:fixed;bottom:25px;color:#a5bfc9;font-size:16px}</style>'
    payload=[{'html':style+'<h1>'+title+'</h1>'+content+'<footer>Evidence walkthrough · '+str(i+1)+'/6 · Synthetic data only</footer>','seconds':seconds} for i,(title,content,seconds) in enumerate(slides)]
    code="""import json,sys,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
slides=json.load(sys.stdin)
with sync_playwright() as p:
 b=p.chromium.launch(args=['--disable-dev-shm-usage']);c=b.new_context(record_video_dir='/tmp/video',record_video_size={'width':1280,'height':900},viewport={'width':1280,'height':900});page=c.new_page()
 for slide in slides:
  page.set_content(slide['html']);page.wait_for_timeout(slide['seconds']*1000)
 video=page.video;c.close();path=video.path();b.close();sys.stdout.buffer.write(Path(path).read_bytes())
"""
    image=json.loads(a.images.read_text())['app'];a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as out:subprocess.run(['docker','run','--rm','-i','--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,size=256m,mode=1777','--memory','512m','--pids-limit','128','--cap-drop','ALL','--security-opt','no-new-privileges:true',image,'python','-c',code],input=json.dumps(payload).encode(),stdout=out,check=True,timeout=240)
    print(a.output)
if __name__=='__main__':main()
