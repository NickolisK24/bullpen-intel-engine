"""Minimal Flask application context for read-only production commands.

Operational scripts that only inspect already-published rows must not import the
full API application: doing so registers write endpoints and correctly activates
the production ``ADMIN_API_TOKEN`` startup guard.  This context initializes only
the database extension.  It has no routes, scheduler, sync service, or write
credential and therefore cannot expose an operational endpoint.
"""

from __future__ import annotations

import os

from flask import Flask

from config import _configure_database
from utils.db import db


def create_read_only_app(config_name=None):
    """Return a database-only app for immutable publication inspection.

    ``APP_ENV`` still controls database safety: non-production modes retain the
    repository's local-database restriction, while production may use the
    configured managed database.  ``ADMIN_API_TOKEN`` and ``SECRET_KEY`` are not
    read because this app registers neither HTTP routes nor write operations.
    """
    environment = config_name or os.environ.get('APP_ENV', 'development')
    if environment not in {'development', 'test', 'production'}:
        environment = 'development'

    app = Flask('baseballos-read-only-publication')
    app.config['APP_ENV'] = environment
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    _configure_database(app, environment)
    db.init_app(app)
    return app
