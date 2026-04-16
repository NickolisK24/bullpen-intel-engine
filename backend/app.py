import atexit
import logging
import os
from datetime import datetime

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate

from config import config
from utils.db import db

migrate = Migrate()

# Module-level so it isn't GC'd — scheduled jobs die if the scheduler
# is collected.
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
        app.logger.info('AUTO_SYNC disabled — daily scheduler not started.')
        return

    # In Flask debug mode the reloader forks a child process. Only start the
    # scheduler in the child (WERKZEUG_RUN_MAIN=true) to avoid double-firing.
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        app.logger.warning('APScheduler not installed — daily scheduler disabled.')
        return

    from services.sync import run_daily_sync

    # Lazy import to avoid a hard dependency during migrations.
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        eastern = ZoneInfo('America/New_York')
    except Exception:
        eastern = None  # APScheduler will fall back to system TZ

    _scheduler = BackgroundScheduler(daemon=True)
    trigger = CronTrigger(hour=6, minute=0, timezone=eastern) if eastern else CronTrigger(hour=6, minute=0)

    _scheduler.add_job(
        func=lambda: run_daily_sync(app),
        trigger=trigger,
        id='daily_bullpen_sync',
        name='Daily bullpen sync (06:00 ET)',
        replace_existing=True,
        misfire_grace_time=60 * 60,  # 1h grace if the host was asleep
    )
    _scheduler.start()
    app.logger.info('Daily bullpen sync scheduled at 06:00 ET.')

    # Shut down cleanly when the Flask process exits.
    atexit.register(lambda: _scheduler and _scheduler.shutdown(wait=False))


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://localhost:3000"]}})

    # Import models so Migrate picks them up
    from models.pitcher import Pitcher
    from models.game_log import GameLog
    from models.prospect import Prospect
    from models.fatigue_score import FatigueScore

    # Register blueprints
    from api.bullpen import bullpen_bp
    from api.prospects import prospects_bp
    from api.portfolio import portfolio_bp

    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(prospects_bp, url_prefix='/api/prospects')
    app.register_blueprint(portfolio_bp, url_prefix='/api/portfolio')

    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'message': 'BaseballOS API is live'}

    # Ensure logs/ directory exists so the scheduler can write its audit file.
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Kick off the scheduler (guarded by AUTO_SYNC env var).
    _init_scheduler(app)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
