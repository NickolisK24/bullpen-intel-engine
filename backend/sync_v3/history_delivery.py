"""Read-only HTTP adapter for a rehearsal-owned connection factory."""

from contextlib import closing, contextmanager

from flask import Flask, abort

from services.mlb_club_directory import MLB_CLUBS, MLB_TEAM_IDS
from sync_v3.product_delivery import product_routes
from sync_v3.product_reads import read_team_history
from sync_v3.readiness_history import UnknownAvailabilityEdition, read_availability_edition


def historical_history_app(connect, *, page_size=14):
    if type(page_size) is not int or not 1 <= page_size <= 30:
        raise ValueError('Expected a historical page size from 1 to 30')
    clubs = {club.abbreviation: club.team_id for club in MLB_CLUBS}
    app = Flask(__name__, static_folder=None)

    @contextmanager
    def reader():
        with closing(connect()) as connection:
            with connection, connection.cursor() as cur:
                cur.execute('SELECT current_database(), session_user, current_user, inet_server_addr()')
                if cur.fetchone() != ('sync_v3_rehearsal', 'sync_v3_reader', 'sync_v3_reader', None):
                    raise PermissionError('Historical HTTP reads require the dedicated rehearsal reader')
            yield connection

    @app.get('/api/sync-v3/history/teams/<club>/revisions/<int:revision>')
    def club_history(club, revision):
        if club not in clubs:
            abort(404)
        return team_history(clubs[club], revision)

    @app.get('/api/sync-v3/history/teams/<int:team>/revisions/<int:revision>')
    def team_history(team, revision):
        if team not in MLB_TEAM_IDS or not 0 < revision < 2**63:
            abort(404)
        with reader() as connection:
            page = read_team_history(connection, team, through_revision=revision, limit=page_size)
        return page, 404 if page['status'] == 'unknown_revision' else 200

    @app.get('/api/sync-v3/availability-editions/<digest>')
    def availability_edition(digest):
        if len(digest) != 64 or any(ch not in '0123456789abcdef' for ch in digest):
            abort(404)
        with reader() as connection:
            try:
                return read_availability_edition(connection, digest)
            except UnknownAvailabilityEdition:
                abort(404)

    app.register_blueprint(product_routes(reader, page_size))
    return app
