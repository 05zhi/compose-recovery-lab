"""Run inside the app container against the real PostgreSQL-backed HTTP app."""
import hashlib
import json
import os
from urllib.request import Request, urlopen


def smoke(base='http://127.0.0.1:8080', quiet=False):
    payload = json.dumps({'username': 'demo', 'password': os.environ['DEMO_PASSWORD']}).encode()
    with urlopen(Request(base + '/login', data=payload, headers={'Content-Type': 'application/json'}), timeout=10) as response:
        token = json.load(response)['token']
    headers = {'Authorization': 'Bearer ' + token}
    with urlopen(Request(base + '/documents?q=Document', headers=headers), timeout=10) as response:
        documents = json.load(response)['documents']
    if len(documents) != 10:
        raise RuntimeError(f'expected 10 documents, observed {len(documents)}')
    for doc in documents:
        with urlopen(Request(base + '/download/' + str(doc['id']), headers=headers), timeout=10) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != doc['sha256']:
            raise RuntimeError('download hash mismatch')
    if not quiet:
        print('PASS: login, search, and 10 attachment downloads with SHA-256')


if __name__ == '__main__':
    smoke()
