print('[boot] app.py module loading', flush=True)

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
    global _scheduler
    print(f'[scheduler] _init_scheduler called, _scheduler={_scheduler}, AUTO_SYNC={os.environ.get("AUTO_SYNC")!r}', flush=True)

    if _scheduler is not None:
        return

    if os.environ.get('AUTO_SYNC', '').lower() not in ('1', 'true', 'yes'):
        print('[scheduler] AUTO_SYNC disabled — daily scheduler not started.', flush=True)
        return

    print(f'[scheduler] checkpoint: app.debug={app.debug}, AUTO_SYNC ok, about to import APScheduler', flush=True)

    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print('[scheduler] EXITING: debug mode without WERKZEUG_RUN_MAIN', flush=True)
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        print('[scheduler] APScheduler imports succeeded', flush=True)
    except ImportError:
        print('[scheduler] APScheduler not installed — daily scheduler disabled.', flush=True)
        return

    try:
        from services.sync import run_daily_sync
        print('[scheduler] services.sync imported', flush=True)

        try:
            from zoneinfo import ZoneInfo
            eastern = ZoneInfo('America/New_York')
            print('[scheduler] ZoneInfo loaded', flush=True)
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
        _scheduler.start()
        print('[scheduler] Daily bullpen sync scheduled at 06:00 ET.', flush=True)

        atexit.register(lambda: _scheduler and _scheduler.shutdown(wait=False))
    except Exception as e:
        import traceback
        print(f'[scheduler] FAILED to start: {e!r}', flush=True)
        print(traceback.format_exc(), flush=True)


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
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

    from api.bullpen import bullpen_bp
    from api.prospects import prospects_bp
    from api.portfolio import portfolio_bp

    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(prospects_bp, url_prefix='/api/prospects')
    app.register_blueprint(portfolio_bp, url_prefix='/api/portfolio')

    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'message': 'BaseballOS API is live'}

    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    _init_scheduler(app)

    print('[boot] create_app finished', flush=True)
    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)