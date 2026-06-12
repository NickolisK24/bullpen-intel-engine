import os
from dotenv import load_dotenv

load_dotenv()

# Default local development database. Overridden by DATABASE_URL in any real
# environment (see ProductionConfig, which refuses to fall back to this).
_DEFAULT_DEV_DB = 'postgresql://postgres:password@localhost:5432/baseballos'
_DEV_SECRET = 'dev-secret-key'


def _normalize_db_url(url):
    """
    Some managed hosts (Render, Heroku, Supabase) hand out `postgres://` URLs,
    which SQLAlchemy 2.x no longer accepts. Normalize them to `postgresql://`
    so the same DATABASE_URL works locally and in production unchanged.
    """
    if url and url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', _DEV_SECRET)
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get('DATABASE_URL', _DEFAULT_DEV_DB)
    )
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
    DEBUG = False
    TESTING = False

    @staticmethod
    def init_app(app):
        """Per-environment validation/setup hook. No-op by default."""
        pass


class DevelopmentConfig(Config):
    DEBUG = True


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
        if not os.environ.get('DATABASE_URL'):
            raise RuntimeError(
                'DATABASE_URL must be set when APP_ENV=production — refusing to '
                'fall back to the localhost development database.'
            )
        if not app.config.get('ADMIN_API_TOKEN'):
            raise RuntimeError(
                'ADMIN_API_TOKEN must be set when APP_ENV=production so that '
                'operational write endpoints (sync, recalculate) are not exposed '
                'to anonymous callers.'
            )


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
