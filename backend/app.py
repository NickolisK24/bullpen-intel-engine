import atexit
import logging
import os
from datetime import datetime

from flask import Flask, app
from flask_cors import CORS
from flask_migrate import Migrate

from config import config
from utils.db import db

migrate = Migrate()

_scheduler = None


def _init_scheduler(app):
    """
    Wire up the daily sync scheduler. Only activates when AUTO_SYNC=true
    is set in the environment — so migrations and test runs don't kick
    off background jobs.
    """
    global _scheduler
    if _scheduler is not None:
        return

    if os.environ.get('AUTO_SYNC', '').lower() not in ('1', 'true', 'yes'):
        print('[scheduler] AUTO_SYNC disabled — daily scheduler not started.', flush=True)
        return

    # Skip the WERKZEUG_RUN_MAIN guard when not running under Flask's dev server.
    is_under_werkzeug_reloader = (
        app.debug
        and os.environ.get('WERKZEUG_RUN_MAIN') is not None
        and os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    )
    if is_under_werkzeug_reloader:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print('[scheduler] APScheduler not installed — daily scheduler disabled.', flush=True)
        return

    try:
        from services.sync import run_daily_sync

        try:
            from zoneinfo import ZoneInfo
            eastern = ZoneInfo('America/New_York')
        except Exception as e:
            print(f'[scheduler] ZoneInfo failed: {e!r}', flush=True)
            eastern = None

        _scheduler = BackgroundScheduler(daemon=True)
        trigger = CronTrigger(hour=6, minute=0, timezone=eastern) if eastern else CronTrigger(hour=6, minute=0)

        _scheduler.add_job(
            func=lambda: run_daily_sync(app),
            trigger=trigger,
            id='daily_bullpen_sync',
            name='Daily bullpen sync (06:00 ET)',
            replace_existing=True,
            misfire_grace_time=60 * 60,
        )

        # Daily team digest job — only registered when explicitly enabled, so
        # turning on AUTO_SYNC alone never starts emailing. Per-user opt-in is
        # still required for any individual digest to send.
        if app.config.get('DIGEST_SEND_ENABLED'):
            from services.digest_delivery import register_digest_job
            digest_hour = int(app.config.get('DIGEST_SEND_HOUR_ET', 7))
            register_digest_job(_scheduler, app, hour=digest_hour, minute=0, timezone=eastern)
            print(f'[scheduler] Daily team digest scheduled at {digest_hour:02d}:00 ET.', flush=True)

        _scheduler.start()
        print('[scheduler] Daily bullpen sync scheduled at 06:00 ET.', flush=True)

        atexit.register(lambda: _scheduler and _scheduler.shutdown(wait=False))
    except Exception as e:
        import traceback
        print(f'[scheduler] FAILED to start: {e!r}', flush=True)
        print(traceback.format_exc(), flush=True)


def create_app(config_name=None):
    # Select config from APP_ENV (development | test | production), defaulting
    # to development. Pass an explicit config_name to override (e.g. in scripts).
    if config_name is None:
        config_name = os.environ.get('APP_ENV', 'development')
    if config_name not in config:
        config_name = 'development'

    app = Flask(__name__)
    cfg = config[config_name]
    app.config.from_object(cfg)
    app.config['APP_ENV'] = config_name
    # Per-environment validation (production fails fast on unsafe config).
    cfg.init_app(app)

    db.init_app(app)
    migrate.init_app(app, db)
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        # Production frontends: the canonical custom domain and the legacy Vercel
        # domain (kept during the transition). Further origins can be added
        # without a deploy via the CORS_ORIGINS env var (comma-separated).
        "https://baseballos.app",
        "https://baseballos.vercel.app",
    ]

    extra_origins = os.environ.get("CORS_ORIGINS", "")
    if extra_origins:
        allowed_origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    from models.pitcher import Pitcher
    from models.game_log import GameLog
    from models.prospect import Prospect
    from models.fatigue_score import FatigueScore
    from models.sync_run import SyncRun
    from models.sync_failure import SyncFailure
    from models.dashboard_snapshot import DashboardSnapshot
    from models.availability_backtest_result import AvailabilityBacktestResult
    from models.postgame_processed_game import PostgameProcessedGame
    from models.user import User, UserFollowedTeam
    from models.digest_metrics import DigestRun, DigestDelivery

    from api.bullpen import bullpen_bp
    from api.prospects import prospects_bp
    from api.methodology import methodology_bp
    from api.recommendations import recommendations_bp
    from api.team_operations import team_operations_bp
    from api.explanations import explanations_bp
    from api.observations import observations_bp
    from api.pitchers import pitchers_bp
    from api.system import system_bp
    from api.auth import auth_bp
    from api.me import me_bp
    from api.digest import digest_bp

    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(prospects_bp, url_prefix='/api/prospects')
    app.register_blueprint(methodology_bp, url_prefix='/api/methodology')
    app.register_blueprint(recommendations_bp, url_prefix='/api/recommendations')
    app.register_blueprint(team_operations_bp, url_prefix='/api/team-operations')
    app.register_blueprint(explanations_bp, url_prefix='/api/explanations')
    app.register_blueprint(observations_bp, url_prefix='/api/observations')
    app.register_blueprint(pitchers_bp, url_prefix='/api/pitchers')
    app.register_blueprint(system_bp, url_prefix='/api/system')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(me_bp, url_prefix='/api/me')
    app.register_blueprint(digest_bp, url_prefix='/api/digest')

    @app.route('/api/health')
    def health():
        return {
            'status':      'ok',
            'environment': app.config.get('APP_ENV', 'development'),
            'debug':       bool(app.config.get('DEBUG', False)),
            'message':     'BaseballOS API is live',
        }

    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    _init_scheduler(app)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False))
