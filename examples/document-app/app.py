"""Synthetic recovery fixture; not a production authentication service."""
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def attachment(root, name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('unsafe attachment path')
    root = Path(root).resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError('unsafe attachment path')
    return target


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()


class Store:
    def connect(self):
        import psycopg
        return psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=5)

    def authenticate(self, username, password):
        with self.connect() as db:
            row = db.execute('SELECT salt, password_hash FROM accounts WHERE username = %s', (username,)).fetchone()
        return bool(row and hmac.compare_digest(row[1], password_hash(password, row[0])))

    def documents(self, query):
        with self.connect() as db:
            return db.execute('SELECT id, title, storage_path, sha256 FROM documents WHERE title ILIKE %s ORDER BY id LIMIT 100', ('%' + query + '%',)).fetchall()

    def document(self, document_id):
        with self.connect() as db:
            return db.execute('SELECT id, title, storage_path, sha256 FROM documents WHERE id = %s', (document_id,)).fetchone()

    def healthy(self):
        with self.connect() as db:
            db.execute('SELECT count(*) FROM documents').fetchone()


def seed(store, root, password):
    """Explicit initialization only: serving never repairs missing attachments."""
    root.mkdir(parents=True, exist_ok=True)
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS accounts (username text PRIMARY KEY, salt text NOT NULL, password_hash text NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS documents (id integer PRIMARY KEY, title text NOT NULL, storage_path text NOT NULL UNIQUE, sha256 text NOT NULL)')
        if db.execute('SELECT count(*) FROM documents').fetchone()[0]:
            raise ValueError('refusing to reseed a populated database')
        salt = secrets.token_hex(16)
        db.execute('INSERT INTO accounts VALUES (%s, %s, %s)', ('demo', salt, password_hash(password, salt)))
        for i in range(1, 11):
            name = f'document-{i:02}.txt'
            content = f'Compose Recovery Lab synthetic document {i:02}\n'.encode()
            with attachment(root, name).open('xb') as output:
                output.write(content)
            db.execute('INSERT INTO documents VALUES (%s, %s, %s, %s)', (i, f'Document {i:02}', name, hashlib.sha256(content).hexdigest()))


def make_server(address, store, root):
    sessions = {}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log credentials, tokens, or search terms.

        def reply(self, status, value, binary=False):
            body = value if binary else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/octet-stream' if binary else 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            with lock:
                return sessions.get(token, 0) > time.monotonic()

        def do_POST(self):
            if self.path != '/login':
                return self.reply(404, {'error': 'not found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size <= 0 or size > 4096:
                    return self.reply(400, {'error': 'invalid request size'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in ('username', 'password')):
                    return self.reply(400, {'error': 'invalid credentials format'})
                if not store.authenticate(data['username'], data['password']):
                    return self.reply(401, {'error': 'invalid credentials'})
                with lock:
                    for old in list(sessions):
                        if sessions[old] <= time.monotonic():
                            del sessions[old]
                    if len(sessions) >= 1000:
                        return self.reply(503, {'error': 'session capacity reached'})
                    token = secrets.token_urlsafe(32)
                    sessions[token] = time.monotonic() + 900
                self.reply(200, {'token': token})
            except (ValueError, UnicodeError):
                self.reply(400, {'error': 'invalid request'})
            except Exception:
                self.reply(503, {'error': 'database unavailable'})

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                if url.path == '/health':
                    store.healthy()
                    return self.reply(200, {'status': 'ready'})
                if not self.authorized():
                    return self.reply(401, {'error': 'authentication required'})
                if url.path == '/documents':
                    query = parse_qs(url.query).get('q', [''])[0]
                    rows = store.documents(query[:200])
                    return self.reply(200, {'documents': [dict(zip(('id', 'title', 'storage_path', 'sha256'), row)) for row in rows]})
                if url.path.startswith('/download/'):
                    try:
                        document_id = int(url.path.removeprefix('/download/'))
                    except ValueError:
                        return self.reply(400, {'error': 'invalid document ID'})
                    row = store.document(document_id)
                    if row is None:
                        return self.reply(404, {'error': 'document not found'})
                    try:
                        content = attachment(root, row[2]).read_bytes()
                    except (ValueError, OSError):
                        return self.reply(409, {'error': 'attachment unavailable'})
                    if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), row[3]):
                        return self.reply(409, {'error': 'attachment hash mismatch'})
                    return self.reply(200, content, binary=True)
                self.reply(404, {'error': 'not found'})
            except Exception:
                self.reply(503, {'error': 'service unavailable'})

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

    return ThreadingHTTPServer(address, Handler)


if __name__ == '__main__':
    store = Store()
    root = Path(os.environ.get('UPLOADS_ROOT', '/uploads'))
    if sys.argv[1:] == ['seed']:
        seed(store, root, os.environ['DEMO_PASSWORD'])
    elif sys.argv[1:] == ['serve']:
        make_server(('0.0.0.0', 8080), store, root).serve_forever()
    else:
        raise SystemExit('usage: app.py seed|serve')
