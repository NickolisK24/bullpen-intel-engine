"""Run the real trusted-publication builder against an exclusive test PostgreSQL DB.

Run from backend with TEST_DATABASE_URL pointing at a disposable local database
whose name contains ``rehearsal_test``. No production credential is accepted.
"""

import os
from urllib.parse import urlparse

import pytest

from tests.db_config import assert_disposable_test_target


def assert_rehearsal_target(env=None):
    env = os.environ if env is None else env
    url = env.get('TEST_DATABASE_URL')
    if not url:
        raise RuntimeError('TEST_DATABASE_URL is required for publication rehearsal')
    parsed = urlparse(url)
    if parsed.scheme not in ('postgres', 'postgresql'):
        raise RuntimeError('Publication rehearsal requires disposable PostgreSQL')
    if 'rehearsal_test' not in parsed.path.lower():
        raise RuntimeError('Publication rehearsal requires a dedicated rehearsal_test database')
    if env.get('DATABASE_URL') and env['DATABASE_URL'] != url:
        raise RuntimeError('Refusing rehearsal while DATABASE_URL points elsewhere')
    if env.get('APP_ENV') not in (None, '', 'test'):
        raise RuntimeError('Publication rehearsal requires APP_ENV=test')
    assert_disposable_test_target(url, operation='trusted publication rehearsal')
    return url


def main():
    assert_rehearsal_target()
    os.environ['APP_ENV'] = 'test'
    return pytest.main(['-q', 'tests/test_trusted_publication_rehearsal.py'])


if __name__ == '__main__':
    raise SystemExit(main())
