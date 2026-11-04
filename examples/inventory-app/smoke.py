import csv,hashlib,io,json,os
from urllib.request import Request,urlopen
def smoke(quiet=False):
    base='http://127.0.0.1:8080'
    with urlopen(Request(base+'/login',data=json.dumps({'username':'demo','password':os.environ['DEMO_PASSWORD']}).encode(),headers={'Content-Type':'application/json'}),timeout=5) as r:token=json.load(r)['token']
    def get(path):
        with urlopen(Request(base+path,headers={'Authorization':'Bearer '+token}),timeout=5) as r:return r.read()
    items=json.loads(get('/inventory?q=SKU'))['items'];assert len(items)==6
    for item in items:assert hashlib.sha256(get('/download/'+str(item['id']))).hexdigest()==item['sha256']
    rows=list(csv.DictReader(io.StringIO(get('/export').decode())))
    assert rows==[{'sku':f'SKU-{i:02}','quantity':str(i*15)} for i in range(1,7)]
    if not quiet:print('PASS: login, inventory search, six specifications and aggregated CSV export')
if __name__=='__main__':smoke()
