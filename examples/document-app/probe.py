"""Bounded checks for the synthetic M1 contract; stdout contains no credentials."""
from probe_diagnostics import failure_evidence
import hashlib
import json
from pathlib import Path
import socket

from app import Store, attachment
from smoke import smoke


def run():
    results = []

    def check(name, fn):
        try:
            evidence = fn()
            results.append({'id': name, 'required': True, 'status': 'passed', 'evidence': evidence})
        except Exception as error:
            results.append({'id': name, 'required': True, 'status': 'failed', 'evidence': failure_evidence(error)})

    def sql():
        with Store().connect() as db:
            db.execute('SET TRANSACTION READ ONLY')
            db.execute("SET LOCAL statement_timeout = '5s'")
            count = db.execute('SELECT count(*) FROM documents').fetchone()[0]
            if count != 10:
                raise ValueError('expected 10 documents')
            if db.execute('SELECT rolsuper FROM pg_roles WHERE rolname = current_user').fetchone()[0]:
                raise ValueError('application role is superuser')
        return '10 documents; non-superuser application role; read-only transaction'

    def files():
        with Store().connect() as db:
            db.execute('SET TRANSACTION READ ONLY')
            db.execute("SET LOCAL statement_timeout = '5s'")
            rows = db.execute('SELECT storage_path, sha256 FROM documents ORDER BY id LIMIT 101').fetchall()
        if len(rows) != 10:
            raise ValueError('unexpected row count')
        for name, digest in rows:
            content = attachment(Path('/uploads'), name).read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError('attachment missing or mismatched')
        return 'all 10 database references match attachment SHA-256'

    def downloads():
        smoke(quiet=True)
        from browser_smoke import browser_smoke
        browser_smoke()
        return 'login, search, all 10 HTTP downloads and hashes; Chromium UI login/search/download and content hash'

    def egress():
        try:
            connection = socket.create_connection(('1.1.1.1', 443), timeout=2)
        except OSError:
            return 'TCP connection to 1.1.1.1:443 blocked; single endpoint only'
        connection.close()
        raise ValueError('unexpected external connectivity')

    check('sql-documents', sql)
    check('database-files', files)
    check('login-search-download', downloads)
    check('external-connectivity', egress)
    print(json.dumps(results))


if __name__ == '__main__':
    run()
