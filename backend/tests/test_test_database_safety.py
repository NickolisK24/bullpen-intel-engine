import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.db_config import (
    assert_disposable_test_target,
    create_test_schema,
    drop_test_schema,
    is_disposable_test_target,
)


TEMP_SQLITE_URL = (
    f"sqlite:///{(Path(tempfile.gettempdir()) / 'baseballos-test' / 'test.db').as_posix()}"
)


@pytest.mark.parametrize(
    ('url', 'env', 'expected'),
    [
        ('sqlite:///:memory:', {}, True),
        ('sqlite://', {}, True),
        (TEMP_SQLITE_URL, {}, True),
        (
            'postgresql://postgres:postgres@localhost:5432/baseballos_ci_test',
            {},
            True,
        ),
        (
            'postgresql://postgres:postgres@postgres:5432/baseballos_ci_test',
            {'CI': 'true'},
            True,
        ),
        (
            'postgresql://postgres:postgres@localhost:5432/baseballos',
            {},
            False,
        ),
        (
            'postgresql://postgres:postgres@db.example.com:5432/baseballos_test',
            {},
            False,
        ),
        ('mysql://localhost/baseballos_test', {}, False),
        ('', {}, False),
    ],
)
def test_disposable_test_target_allow_list(url, env, expected):
    assert is_disposable_test_target(url, env=env) is expected


def test_session_guard_rejects_production_style_url():
    with pytest.raises(RuntimeError, match='non-disposable test database'):
        assert_disposable_test_target(
            'postgresql://postgres:secret@db.example.com:5432/baseballos',
            operation='pytest session',
        )


@pytest.mark.parametrize('helper', [create_test_schema, drop_test_schema])
def test_lifecycle_helper_rejects_unsafe_target_before_database_call(helper):
    app = SimpleNamespace(
        config={
            'SQLALCHEMY_DATABASE_URI': (
                'postgresql://postgres:secret@db.example.com:5432/baseballos'
            )
        }
    )

    with pytest.raises(RuntimeError, match='non-disposable test database') as exc:
        helper(app)

    assert 'secret' not in str(exc.value)
