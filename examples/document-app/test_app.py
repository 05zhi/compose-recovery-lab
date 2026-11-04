import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import attachment, make_server, password_hash


class FakeStore:
    content = b'synthetic document\n'
    path = 'document.txt'

    def healthy(self):
        pass

    def authenticate(self, username, password):
        return username == 'demo' and password == 'test-only'

    def documents(self, query):
        return [self.document(1)] if query in 'Document' else []

    def document(self, document_id):
        if document_id == 1:
            return (1, 'Document', self.path, hashlib.sha256(self.content).hexdigest())


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = FakeStore()
        (self.root / self.store.path).write_bytes(self.store.content)
        self.server = make_server(('127.0.0.1', 0), self.store, self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.token = None

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None):
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def login(self):
        status, body = self.request('/login', {'username': 'demo', 'password': 'test-only'})
        self.assertEqual(status, 200)
        self.token = json.loads(body)['token']

    def test_login_search_download(self):
        self.login()
        status, body = self.request('/documents?q=Document')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['documents']), 1)
        self.assertEqual(self.request('/download/1'), (200, self.store.content))

    def test_authentication_required(self):
        self.assertEqual(self.request('/documents')[0], 401)
        self.assertEqual(self.request('/download/1')[0], 401)
        self.assertEqual(self.request('/login', {'username': 'demo', 'password': 'wrong'})[0], 401)
        self.assertEqual(self.request('/login', [1, 2])[0], 400)

    def test_missing_attachment_does_not_heal(self):
        self.login()
        (self.root / self.store.path).unlink()
        self.assertEqual(self.request('/health')[0], 200)
        self.assertEqual(self.request('/download/1')[0], 409)
        self.assertFalse((self.root / self.store.path).exists())

    def test_corrupt_attachment(self):
        self.login()
        (self.root / self.store.path).write_bytes(b'wrong')
        self.assertIn(b'hash mismatch', self.request('/download/1')[1])

    def test_database_path_escape(self):
        self.login()
        self.store.path = '../outside.txt'
        self.assertEqual(self.request('/download/1')[0], 409)

    def test_unknown_and_invalid_ids(self):
        self.login()
        self.assertEqual(self.request('/download/999')[0], 404)
        self.assertEqual(self.request('/download/no')[0], 400)

    def test_database_errors_are_redacted(self):
        def broken():
            raise RuntimeError('postgresql://secret-password@db')
        self.store.healthy = broken
        status, body = self.request('/health')
        self.assertEqual(status, 503)
        self.assertNotIn(b'secret-password', body)


class PathTests(unittest.TestCase):
    def test_reject_unsafe_names(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ('', '..', '../secret', '/etc/passwd', 'C:/secret', 'a\\secret', 'a/../../secret'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    attachment(root, name)
            self.assertEqual(attachment(root, 'nested/file.txt'), Path(root).resolve() / 'nested/file.txt')

    def test_password_hash_is_salted(self):
        self.assertEqual(password_hash('password', 'salt'), password_hash('password', 'salt'))
        self.assertNotEqual(password_hash('password', 'salt'), password_hash('password', 'other'))


if __name__ == '__main__':
    unittest.main()
