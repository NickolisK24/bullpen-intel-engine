import os
from urllib.parse import urlparse

from dotenv import load_dotenv

if os.environ.get('PYTHON_DOTENV_DISABLED', '').lower() not in {'1', 'true', 'yes', 'on'}:
    load_dotenv()

_DEV_SECRET = 'dev-secret-key'
_LOCAL_DB_HOSTS = {'localhost', '127.0.0.1', '::1', 'host.docker.internal'}
_CI_DB_HOSTS = {'postgres'}


def _normalize_db_url(url):
    """
    Some managed hosts (Render, Heroku, Supabase) hand out `postgres://` URLs,
    which SQLAlchemy 2.x no longer accepts. Normalize them to `postgresql://`
    so hosted production DATABASE_URL values work when APP_ENV=production.
    """
    if url and url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


def _is_local_database_url(url):
    parsed = urlparse(url or '')
    scheme = parsed.scheme.lower()
    if scheme == 'sqlite':
        return True
    if scheme not in {'postgres', 'postgresql'}:
        return False

    host = (parsed.hostname or '').lower()
    if host in _LOCAL_DB_HOSTS:
        return True

    database = (parsed.path or '').lstrip('/').lower()
    return (
        os.environ.get('CI') in {'1', 'true', 'True'}
        and host in _CI_DB_HOSTS
        and 'test' in database
    )


def _database_url_for_env(app_env):
    if app_env == 'test':
        return (
            os.environ.get('TEST_DATABASE_URL')
            or os.environ.get('DATABASE_URL')
        )
    return os.environ.get('DATABASE_URL')


def _engine_options_for_url(database_url):
    """SQLAlchemy engine options tuned for the resolved database.

    Postgres (production/CI) gets stale-connection protection and bounded
    timeouts: ``pool_pre_ping`` validates a pooled connection before use so a
    connection the server has closed (e.g. Render's ``SSL SYSCALL error: EOF
    detected`` on an idle connection) is detected and replaced instead of
    failing a query mid-flight; ``pool_recycle`` proactively retires
    connections before the host's idle cutoff; and the psycopg2 ``connect_args``
    add a connect timeout, a server-side ``statement_timeout`` (well under the
    Gunicorn worker timeout so a stuck query fails fast instead of being
    SIGKILLed), and TCP keepalives so dead sockets surface promptly.

    SQLite (local/test) keeps the existing default behavior — the psycopg2
    connect_args do not apply there — so test environments are unaffected.
    """
    scheme = urlparse(database_url or '').scheme.lower()
    if scheme in {'postgres', 'postgresql'}:
        return {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'options': '-c statement_timeout=15000',
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            },
        }
    return {}


def _configure_database(app, app_env):
    database_url = _database_url_for_env(app_env)
    if not database_url:
        raise RuntimeError(
            'DATABASE_URL is not set. Set it to a local database to run locally.'
        )

    database_url = _normalize_db_url(database_url)
    if app_env != 'production' and not _is_local_database_url(database_url):
        parsed = urlparse(database_url)
        host = parsed.hostname or 'unknown'
        raise RuntimeError(
            'DATABASE_URL must point to a local database when APP_ENV is not '
            f'production; refusing to start with non-local database host {host!r}.'
        )

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _engine_options_for_url(database_url)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', _DEV_SECRET)
    SQLALCHEMY_DATABASE_URI = None
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MLB_API_BASE = os.environ.get('MLB_API_BASE', 'https://statsapi.mlb.com/api/v1')

    # ── Resilient MLB Stats API client ───────────────────────────────────────
    # Per-request timeout (seconds) and retry policy for transient failures
    # (connection errors, timeouts, 429, 5xx). These are read by
    # services/mlb_api.MLBApiClient at call time so they can be tuned per
    # environment without touching code. Non-transient 4xx responses are never
    # retried.
    MLB_API_TIMEOUT = float(os.environ.get('MLB_API_TIMEOUT', '10'))
    MLB_API_MAX_RETRIES = int(os.environ.get('MLB_API_MAX_RETRIES', '3'))
    MLB_API_BACKOFF_BASE = float(os.environ.get('MLB_API_BACKOFF_BASE', '1.0'))
    MLB_API_BACKOFF_CAP = float(os.environ.get('MLB_API_BACKOFF_CAP', '30.0'))
    # Full jitter on the backoff delay. Disable (set false) only in tests that
    # need to assert exact sleep durations.
    MLB_API_BACKOFF_JITTER = (
        os.environ.get('MLB_API_BACKOFF_JITTER', 'true').lower()
        in ('1', 'true', 'yes', 'on')
    )

    # ── Freshness degradation thresholds (fail-closed) ───────────────────────
    # Data younger than the stale threshold is fresh; at/after it is stale; at
    # or beyond the unavailable threshold the platform fails closed and stops
    # presenting the domain as usable. Defaults keep the existing 14-day active
    # window as the stale boundary and add a hard 30-day unavailable boundary.
    FRESHNESS_STALE_AFTER_DAYS = int(os.environ.get('FRESHNESS_STALE_AFTER_DAYS', '14'))
    FRESHNESS_UNAVAILABLE_AFTER_DAYS = int(
        os.environ.get('FRESHNESS_UNAVAILABLE_AFTER_DAYS', '30')
    )

    # Shared admin token gating operational write endpoints (sync / recalculate).
    # Unset in development = those endpoints are allowed locally (with a warning).
    ADMIN_API_TOKEN = os.environ.get('ADMIN_API_TOKEN')

    # ── User identity / magic-link authentication (Phase D1C) ────────────────
    # Signing secret for stateless magic-link and bearer tokens. Reuses the
    # validated SECRET_KEY unless a dedicated USER_AUTH_SECRET is provided; in
    # production SECRET_KEY is already required to be strong (see
    # ProductionConfig), so token signing is safe by default there. No password
    # storage and no sessions table — tokens are signed and verified statelessly.
    USER_AUTH_SECRET = (
        os.environ.get('USER_AUTH_SECRET')
        or os.environ.get('SECRET_KEY', _DEV_SECRET)
    )
    # Short-lived magic link (default 15 minutes); longer-lived bearer token
    # (default 30 days). FRONTEND_BASE_URL is where the emailed link points.
    MAGIC_LINK_TTL_SECONDS = int(os.environ.get('MAGIC_LINK_TTL_SECONDS', '900'))
    AUTH_TOKEN_TTL_SECONDS = int(os.environ.get('AUTH_TOKEN_TTL_SECONDS', '2592000'))
    FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:5173')

    # ── Transactional email delivery (Phase D2B) ─────────────────────────────
    # The provider is only used in production; development and test always
    # capture to an in-memory outbox and never send. No secret is stored in the
    # repository — the API key and sender come from the environment. Missing
    # production config fails soft (logged, not sent) and is surfaced by the
    # email-delivery health check rather than crashing the app.
    EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'resend')
    EMAIL_FROM = os.environ.get('EMAIL_FROM')
    EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY')
    EMAIL_SEND_TIMEOUT = float(os.environ.get('EMAIL_SEND_TIMEOUT', '10'))
    # Signing secret for the provider deliverability webhook (Svix scheme). When
    # unset, the webhook is accepted in development (with a warning) and disabled
    # (403) in production, mirroring the admin-token gate. No secret in code.
    EMAIL_WEBHOOK_SECRET = os.environ.get('EMAIL_WEBHOOK_SECRET')

    # ── Team digest scheduling & delivery (Phase D2D) ────────────────────────
    # The daily digest job is registered only when DIGEST_SEND_ENABLED is true,
    # so turning on AUTO_SYNC alone never starts emailing. Per-user opt-in is
    # still required regardless of this flag. DIGEST_SEND_HOUR_ET is when the
    # daily job runs (Eastern). PUBLIC_API_BASE_URL is the backend's public
    # origin, used to build the absolute open/click tracking and one-click
    # unsubscribe links in the email. BACKEND_BASE_URL is accepted as an alias
    # (the operator-facing name on the host) so the origin still resolves when
    # only that variable is set; without it those links would be host-less and
    # render as the invalid http:///api/digest/click in mail clients.
    DIGEST_SEND_ENABLED = (
        os.environ.get('DIGEST_SEND_ENABLED', 'false').lower()
        in ('1', 'true', 'yes', 'on')
    )
    DIGEST_SEND_HOUR_ET = int(os.environ.get('DIGEST_SEND_HOUR_ET', '7'))
    PUBLIC_API_BASE_URL = (
        os.environ.get('PUBLIC_API_BASE_URL')
        or os.environ.get('BACKEND_BASE_URL', '')
    )

    # ── Story Quality contract (scoring + gating) ────────────────────────────
    # The Story Quality scorer always runs and annotates every generated story
    # with a rule-by-rule scorecard. Enforcement is opt-in and fail-open: with
    # STORY_QUALITY_GATE_ENABLED off (the default) the scorer is *report-only* —
    # it scores and annotates but never holds a story out of the feed, so feed
    # behavior is byte-for-byte identical to a build without the contract.
    # When enabled, stories scoring below STORY_QUALITY_GATE_THRESHOLD (a 0-100
    # quality score) are held out of the published feed into a separate held
    # list (never silently dropped). The threshold lives in config, not code.
    STORY_QUALITY_GATE_ENABLED = (
        os.environ.get('STORY_QUALITY_GATE_ENABLED', 'false').lower()
        in ('1', 'true', 'yes', 'on')
    )
    STORY_QUALITY_GATE_THRESHOLD = float(
        os.environ.get('STORY_QUALITY_GATE_THRESHOLD', '60')
    )

    DEBUG = False
    TESTING = False

    @staticmethod
    def init_app(app):
        """Per-environment validation/setup hook."""
        _configure_database(app, app.config.get('APP_ENV', 'development'))


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

    @staticmethod
    def init_app(app):
        """
        Fail fast on unsafe production configuration instead of silently
        booting with development defaults.
        """
        if app.config.get('SECRET_KEY') in (None, '', _DEV_SECRET):
            raise RuntimeError(
                'SECRET_KEY must be set to a strong, unique value when '
                'APP_ENV=production (the development default is not allowed).'
            )
        _configure_database(app, 'production')
        if not app.config.get('ADMIN_API_TOKEN'):
            raise RuntimeError(
                'ADMIN_API_TOKEN must be set when APP_ENV=production so that '
                'operational write endpoints (sync, recalculate) are not exposed '
                'to anonymous callers.'
            )


config = {
    'development': DevelopmentConfig,
    'test': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
