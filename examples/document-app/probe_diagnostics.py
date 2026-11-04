"""Bounded failure evidence: never serialize exception messages or request data."""
from pathlib import Path
import traceback
from urllib.error import HTTPError, URLError

def failure_evidence(error):
    category = 'operation'
    if isinstance(error, HTTPError):
        category = 'http-' + str(error.code) if isinstance(error.code, int) and 100 <= error.code <= 599 else 'http'
    elif isinstance(error, URLError):
        category = 'connection'
    elif isinstance(error, (TimeoutError,)):
        category = 'timeout'
    elif isinstance(error, AssertionError):
        category = 'assertion'
    elif isinstance(error, PermissionError):
        category = 'permission'
    elif isinstance(error, FileNotFoundError):
        category = 'missing-file'
    # Match only fixed signatures; raw Playwright errors may contain credentials.
    if category == 'operation':
        message = str(error)
        for signature, code in (
            ('signal=SIGSEGV', 'browser-sigsegv'),
            ('signal=SIGABRT', 'browser-sigabrt'),
            ('No space left on device', 'disk-full'),
            ('pthread_create', 'thread-create'),
            ('Executable doesn', 'browser-executable'),
            ('Target page, context or browser has been closed', 'browser-closed'),
            ('Timeout', 'timeout'),
        ):
            if signature in message:
                category = code
                break
    location = 'unknown'
    for frame in traceback.extract_tb(error.__traceback__):
        name = Path(frame.filename).name
        if name in ('probe.py', 'smoke.py', 'browser_smoke.py', 'browser_runtime.py'):
            location = name + ':' + str(frame.lineno)
    return 'check failed; category=' + category + '; location=' + location
