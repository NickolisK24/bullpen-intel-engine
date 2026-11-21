"""Edition-bound GET routes for the disposable product rehearsal."""

from contextlib import closing

from flask import Blueprint, abort, request

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.editorial_reads import read_event_evidence, read_story_observations, read_trust
from sync_v3.product_reads import (
    read_game_cards, read_league, read_pitcher, read_pitcher_history, read_search, read_team_board, read_team_events,
)


def product_routes(connect, page_size):
    routes = Blueprint('historical_products', __name__, url_prefix='/api/sync-v3/revisions/<int:revision>')

    @routes.before_request
    def validate_identities():
        ids = request.view_args
        if any(not 0 < value < 2**63 for field, value in ids.items() if field != 'event_id'):
            abort(404)
        if 'team' in ids and ids['team'] not in MLB_TEAM_IDS:
            abort(404)

    def deliver(reader, *args, **kwargs):
        with closing(connect()) as connection:
            payload = reader(connection, *args, **kwargs)
        outcome = payload.get('status', payload.get('qualification'))
        return payload, 404 if outcome in {
            'unknown_revision', 'missing_event', 'game_outside_represented_slate', 'outside_represented_bullpens',
        } else 200

    @routes.get('/league')
    def league(revision):
        return deliver(read_league, revision=revision)

    @routes.get('/tonight')
    def tonight(revision):
        return deliver(read_game_cards, revision=revision)

    @routes.get('/matchups/<int:game>')
    def matchup(revision, game):
        return deliver(read_game_cards, revision=revision, game_pk=game)

    @routes.get('/teams/<int:team>/board')
    def board(revision, team):
        return deliver(read_team_board, team, revision=revision)

    @routes.get('/teams/<int:team>/changes')
    def changes(revision, team):
        return deliver(read_team_events, team, revision=revision)

    @routes.get('/teams/<int:team>/stories')
    def stories(revision, team):
        return deliver(read_story_observations, team, revision=revision)

    @routes.get('/teams/<int:team>/events/<path:event_id>')
    def event(revision, team, event_id):
        return deliver(read_event_evidence, team, event_id, revision=revision)

    @routes.get('/pitchers/<int:player>')
    def pitcher(revision, player):
        return deliver(read_pitcher, player, revision=revision)

    @routes.get('/pitchers/<int:player>/history')
    def pitcher_history(revision, player):
        return deliver(read_pitcher_history, player, through_revision=revision, limit=page_size)

    @routes.get('/search')
    def search(revision):
        if len(request.args.getlist('q')) > 1:
            abort(400)
        return deliver(read_search, request.args.get('q', ''), revision=revision)

    @routes.get('/trust')
    def trust(revision):
        return deliver(read_trust, revision=revision)

    return routes
