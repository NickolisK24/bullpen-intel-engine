"""Read-only HTTP adapter for a rehearsal-owned connection factory."""

from contextlib import closing

from flask import Flask, abort

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.product_reads import read_team_history


def historical_history_app(connect):
    app = Flask(__name__, static_folder=None)

    @app.get('/api/sync-v3/history/teams/<int:team>/revisions/<int:revision>')
    def team_history(team, revision):
        if team not in MLB_TEAM_IDS or not 0 < revision < 2**63:
            abort(404)
        with closing(connect()) as connection:
            page = read_team_history(connection, team, through_revision=revision)
        return page, 404 if page['status'] == 'unknown_revision' else 200

    return app
