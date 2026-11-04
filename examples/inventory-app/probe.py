import hashlib,json,socket
from pathlib import Path
from app import Store,attachment
from smoke import smoke
def run():
    results=[]
    def check(name,fn,coverage):
        try:fn();results.append(dict(id=name,required=True,status='passed',evidence='inventory assertion passed',coverage=coverage))
        except Exception:results.append(dict(id=name,required=True,status='failed',evidence='inventory assertion or operation failed'))
    def sql():
        with Store().connect() as db:
            db.execute('SET TRANSACTION READ ONLY');db.execute("SET LOCAL statement_timeout='5s'")
            assert db.execute('SELECT count(*),sum(quantity) FROM stock').fetchone()==(12,315)
            assert db.execute('SELECT count(*) FROM products').fetchone()[0]==6
            assert db.execute('SELECT count(*) FROM warehouses').fetchone()[0]==2
    def files():
        with Store().connect() as db:rows=db.execute('SELECT spec_path,sha256 FROM products ORDER BY id LIMIT 100').fetchall()
        assert len(rows)==6
        for name,digest in rows:assert hashlib.sha256(attachment(Path('/uploads'),name).read_bytes()).hexdigest()==digest
    def e2e():
        smoke(quiet=True)
        from browser_smoke import browser_smoke
        browser_smoke()
    def egress():
        try:c=socket.create_connection(('1.1.1.1',443),timeout=2)
        except OSError:return
        c.close();raise AssertionError('unexpected egress')
    check('sql-inventory',sql,{'mode':'all','population':12,'checked':12})
    check('database-files',files,{'mode':'all','population':6,'checked':6,'unchecked':0})
    check('inventory-export',e2e,{'mode':'all API downloads and CSV; one browser download','population':6,'checked':6})
    check('external-connectivity',egress,{'mode':'single TCP endpoint','population':1,'checked':1})
    print(json.dumps(results))
if __name__=='__main__':run()
