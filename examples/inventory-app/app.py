"""Inventory fixture: products, warehouses and stock ledger with CSV export."""
import hashlib,io,csv,os,secrets,sys
from pathlib import Path
from common import Store as AuthStore,attachment,password_hash,make_server

class Store(AuthStore):
    listing_path='/inventory'
    listing_key='items'
    def documents(self,query):
        with self.connect() as db:
            return db.execute('SELECT id,sku,spec_path,sha256 FROM products WHERE sku ILIKE %s ORDER BY id LIMIT 100',('%'+query+'%',)).fetchall()
    def document(self,document_id):
        with self.connect() as db:return db.execute('SELECT id,sku,spec_path,sha256 FROM products WHERE id=%s',(document_id,)).fetchone()
    def healthy(self):
        with self.connect() as db:db.execute('SELECT count(*) FROM stock').fetchone()
    def export(self):
        with self.connect() as db:rows=db.execute('SELECT p.sku,sum(s.quantity) FROM products p JOIN stock s ON s.product_id=p.id GROUP BY p.sku ORDER BY p.sku').fetchall()
        out=io.StringIO();writer=csv.writer(out,lineterminator='\n');writer.writerow(['sku','quantity']);writer.writerows(rows);return out.getvalue().encode()

def seed(store,root,password):
    (root/'specs').mkdir(parents=True,exist_ok=True)
    with store.connect() as db:
        db.execute('CREATE TABLE accounts(username text PRIMARY KEY,salt text NOT NULL,password_hash text NOT NULL)')
        db.execute('CREATE TABLE products(id integer PRIMARY KEY,sku text UNIQUE NOT NULL,spec_path text UNIQUE NOT NULL,sha256 text NOT NULL)')
        db.execute('CREATE TABLE warehouses(id integer PRIMARY KEY,name text UNIQUE NOT NULL)')
        db.execute('CREATE TABLE stock(product_id integer REFERENCES products,warehouse_id integer REFERENCES warehouses,quantity integer NOT NULL CHECK(quantity>=0),PRIMARY KEY(product_id,warehouse_id))')
        salt=secrets.token_hex(16);db.execute('INSERT INTO accounts VALUES(%s,%s,%s)',('demo',salt,password_hash(password,salt)))
        db.execute("INSERT INTO warehouses VALUES(1,'North'),(2,'South')")
        for i in range(1,7):
            name=f'specs/sku-{i:02}.txt';content=f'Inventory synthetic specification SKU-{i:02}\n'.encode();attachment(root,name).write_bytes(content)
            db.execute('INSERT INTO products VALUES(%s,%s,%s,%s)',(i,f'SKU-{i:02}',name,hashlib.sha256(content).hexdigest()))
            db.execute('INSERT INTO stock VALUES(%s,1,%s),(%s,2,%s)',(i,i*10,i,i*5))

if __name__=='__main__':
    store=Store();root=Path('/uploads')
    if sys.argv[1:]==['seed']:seed(store,root,os.environ['DEMO_PASSWORD'])
    elif sys.argv[1:]==['reset-password']:
        salt=secrets.token_hex(16)
        with store.connect() as db:
            result=db.execute("UPDATE accounts SET salt=%s,password_hash=%s WHERE username='demo'",(salt,password_hash(os.environ['DEMO_PASSWORD'],salt)))
            assert result.rowcount==1
    elif sys.argv[1:]==['serve']:make_server(('0.0.0.0',8080),store,root).serve_forever()
    else:raise SystemExit('usage: app.py seed|reset-password|serve')
