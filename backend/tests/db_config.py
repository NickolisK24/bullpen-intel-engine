import os
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_TEST_DATABASE_URL = 'sqlite:///:memory:'
LOCAL_POSTGRES_HOSTS = {'localhost', '127.0.0.1', '::1'}
CI_POSTGRES_HOSTS = {'postgres'}


def test_database_url():
    explicit = os.environ.get('TEST_DATABASE_URL')
    if explicit:
        return explicit
    if os.environ.get('APP_ENV') == 'test' and os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    return (
        DEFAULT_TEST_DATABASE_URL
    )


def _env_value(env, key):
    if env is None:
        return os.environ.get(key)
    return env.get(key)


def _sqlite_path_is_disposable(path, env):
    if not path:
        return True

    if path.startswith('/') and len(path) > 3 and path[2] == ':':
        path = path[1:]

    candidate = Path(unquote(path)).expanduser()
    try:
        candidate = candidate.resolve()
    except OSError:
        return False

    safe_roots = [
        _env_value(env, 'TMPDIR'),
        _env_value(env, 'TEMP'),
        _env_value(env, 'TMP'),
        tempfile.gettempdir(),
    ]
    for root in safe_roots:
        if not root:
            continue
        try:
            candidate.relative_to(Path(root).expanduser().resolve())
            return True
        except (OSError, ValueError):
            continue

    safe_parts = {'tmp', 'temp', 'pytest', 'test', 'tests'}
    return any(part.lower() in safe_parts for part in candidate.parts)


def is_disposable_test_target(url, env=None):
    if not url:
        return False

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme == 'sqlite':
        if url in ('sqlite://', 'sqlite:///:memory:'):
            return True
        if parsed.path in ('', '/:memory:', ':memory:'):
            return True
        return _sqlite_path_is_disposable(parsed.path, env)

    if scheme in ('postgres', 'postgresql'):
        host = (parsed.hostname or '').lower()
        database = (parsed.path or '').lstrip('/').lower()
        ci_host_allowed = (
            _env_value(env, 'CI') in ('1', 'true', 'True')
            and host in CI_POSTGRES_HOSTS
        )
        host_allowed = host in LOCAL_POSTGRES_HOSTS or ci_host_allowed
        return host_allowed and 'test' in database

    return False


def assert_disposable_test_target(url, *, operation):
    if is_disposable_test_target(url):
        return
    raise RuntimeError(
        'Refusing to run '
        f'{operation} against non-disposable test database: {_redacted_url(url)!r}'
    )


def _redacted_url(url):
    parsed = urlparse(url or '')
    if not parsed.scheme or parsed.scheme == 'sqlite':
        return url
    host = parsed.hostname or ''
    port = f':{parsed.port}' if parsed.port else ''
    database = parsed.path or ''
    if parsed.username:
        auth = f'{parsed.username}:***@'
    else:
        auth = ''
    return f'{parsed.scheme}://{auth}{host}{port}{database}'


def configure_test_database(app):
    database_url = test_database_url()
    assert_disposable_test_target(database_url, operation='configure test database')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    return app


def _app_database_url(app):
    return app.config.get('SQLALCHEMY_DATABASE_URI')


def create_test_schema(app):
    assert_disposable_test_target(
        _app_database_url(app),
        operation='create test schema',
    )
    # Several optional test import paths load sync-failure/snapshot tables before
    # the durable sync run model. Import it here so FK metadata is complete
    # regardless of pytest collection order.
    import models.evidence_contract  # noqa: F401
    import models.fatigue_score  # noqa: F401
    import models.game_log  # noqa: F401
    import models.pitcher  # noqa: F401
    import models.play_by_play_foundation  # noqa: F401
    import models.postgame_processed_game  # noqa: F401
    import models.roster_status_snapshot  # noqa: F401
    import models.scheduled_game  # noqa: F401
    import models.sync_failure  # noqa: F401
    import models.sync_run  # noqa: F401
    from utils.db import db
    db.create_all()


def drop_test_schema(app):
    assert_disposable_test_target(
        _app_database_url(app),
        operation='drop test schema',
    )
    from utils.db import db
    db.drop_all()
