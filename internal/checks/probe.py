"""Bounded checks. The query role has SELECT only, no temporary-table privilege.
Errors omit SQL, credentials and raw response bodies; numeric scalar evidence is safe.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import random
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, build_opener
import psycopg


class AssertionFailure(Exception):
    pass


def safe_file(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise AssertionFailure('unsafe attachment path')
    base = Path('/uploads').resolve()
    target = (base / name).resolve()
    if target == base or not target.is_relative_to(base):
        raise AssertionFailure('unsafe attachment path')
    return target


def digest_file(name):
    path = safe_file(name)
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise AssertionFailure('attachment missing or size limit exceeded')
    h = hashlib.sha256()
    try:
        with path.open('rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except OSError:
        raise AssertionFailure('attachment is unreadable') from None
    return h.hexdigest()


def rows(query, cap):
    # Prepared execution rejects stacked statements. SELECT wrapper excludes DDL;
    # database privileges and read-only transactions are the enforcement boundary.
    with psycopg.connect(os.environ['CHECK_DATABASE_URL'], connect_timeout=5) as db:
        db.execute('SET TRANSACTION READ ONLY')
        db.execute("SET LOCAL statement_timeout='5s'")
        with db.cursor(name='crl_bounded') as cursor:
            cursor.execute('SELECT * FROM (' + query.rstrip().rstrip(';') + ') AS crl_query LIMIT ' + str(cap + 1))
            result = cursor.fetchmany(cap + 1)
        if len(result) > cap:
            raise AssertionFailure('query row limit exceeded')
        if sum(len(str(v)) for row in result for v in row) > 1024 * 1024:
            raise AssertionFailure('query byte limit exceeded')
        return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def execute(spec):
    kind = spec['type']
    if kind == 'sql':
        result = rows(spec['query'], 1)
        if len(result) != 1 or len(result[0]) != 1:
            raise AssertionFailure('SQL assertion requires one scalar')
        actual = result[0][0]
        expected = spec['expect']['value']
        op = spec['expect']['operator']
        matched = {'eq': lambda: actual == expected, 'ne': lambda: actual != expected,
                   'gte': lambda: actual >= expected, 'lte': lambda: actual <= expected}[op]()
        evidence = {'operator': op, 'expected': expected if isinstance(expected, (int, float, bool)) else '[redacted]',
                    'actual': actual if isinstance(actual, (int, float, bool)) else '[redacted]'}
        return matched, evidence, {'mode': 'scalar', 'population': 1, 'checked': 1}
    if kind == 'file':
        matched = digest_file(spec['path']) == spec['sha256']
        return matched, {'sha256_matches': matched}, {'mode': 'explicit', 'population': 1, 'checked': 1}
    if kind == 'database_files':
        result = rows(spec['query'], 10000)
        if not result or any(len(row) != 2 or not all(isinstance(v, str) for v in row) for row in result):
            raise AssertionFailure('expected nonempty (relative path, SHA-256) rows')
        result.sort()
        scope = spec.get('scope', {'mode': 'all'})
        selected = result
        if scope['mode'] == 'sample':
            if scope['size'] > len(result):
                raise AssertionFailure('sample exceeds population')
            selected = random.Random(scope['seed']).sample(result, scope['size'])
        coverage = {'mode': scope['mode'], 'population': len(result), 'checked': 0, 'unchecked': len(result)}
        if scope['mode'] == 'sample':
            coverage['seed'] = scope['seed']
        for name, digest in selected:
            coverage['checked'] += 1
            coverage['unchecked'] -= 1
            try:
                matched = digest_file(name) == digest
            except AssertionFailure as error:
                return False, {'reason': str(error)}, coverage
            if not matched:
                return False, {'reason': 'attachment content differs from database hash'}, coverage
        return True, {'database_references_match': True}, coverage
    if kind == 'http':
        opener = build_opener(NoRedirect())
        try:
            response = opener.open('http://127.0.0.1:8080' + spec['path'], timeout=5)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(1024 * 1024 + 1)
            status = response.status
        if len(body) > 1024 * 1024:
            raise AssertionFailure('HTTP body limit exceeded')
        ok = status == spec['status'] and spec.get('contains', '').encode() in body
        return ok, {'expected_status': spec['status'], 'actual_status': status, 'body_match': ok}, {'mode': 'single endpoint', 'population': 1, 'checked': 1}
    raise AssertionFailure('unsupported check')


results = []
for spec in json.load(sys.stdin):
    row = {'id': spec['id'], 'required': spec['required'], 'status': 'error', 'evidence': 'operation failed; sensitive diagnostics omitted'}
    try:
        ok, evidence, coverage = execute(spec)
        row.update(status='passed' if ok else 'failed', evidence=json.dumps(evidence), coverage=coverage)
    except AssertionFailure as error:
        row.update(status='failed', evidence=str(error))
    except Exception:
        pass
    results.append(row)
print(json.dumps(results))
