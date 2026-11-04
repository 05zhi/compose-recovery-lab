import unittest
from urllib.error import HTTPError, URLError
from probe_diagnostics import failure_evidence

class DiagnosticTests(unittest.TestCase):
    def test_http_failure_redacts_url_headers_and_message(self):
        error = HTTPError('https://secret-token/path', 503, 'password=secret', {'Authorization':'Bearer secret'}, None)
        self.assertEqual(failure_evidence(error), 'check failed; category=http-503; location=unknown')

    def test_fixed_browser_categories_do_not_leak_raw_errors(self):
        for text, kind in [('Target page, context or browser has been closed password=secret signal=SIGSEGV', 'browser-sigsegv'), ('signal=SIGABRT secret', 'browser-sigabrt'), ('pthread_create secret', 'thread-create'), ('No space left on device secret','disk-full'), ('Target page, context or browser has been closed secret','browser-closed'), ('unknown password=secret','operation')]:
            with self.subTest(kind=kind):
                self.assertEqual(failure_evidence(RuntimeError(text)), 'check failed; category='+kind+'; location=unknown')

    def test_known_source_location_without_source_text(self):
        try:
            exec(compile("raise AssertionError('secret')", '/private/secret/smoke.py', 'exec'))
        except Exception as error:
            self.assertEqual(failure_evidence(error), 'check failed; category=assertion; location=smoke.py:1')

    def test_connection_and_permission_categories(self):
        for error,kind in [(URLError('secret'),'connection'),(PermissionError('secret'),'permission'),(FileNotFoundError('secret'),'missing-file'),(TimeoutError('secret'),'timeout')]:
            self.assertIn('category='+kind+';',failure_evidence(error))
            self.assertNotIn('secret',failure_evidence(error))

if __name__ == '__main__':unittest.main()
