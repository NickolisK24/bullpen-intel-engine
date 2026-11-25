"""Populate empty schedule dates or verify exact repeats in the isolated publication target."""
from datetime import timezone

from psycopg2.extras import Json
from sqlalchemy import or_, text

from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from services.mlb_api import ScheduleGames, schedule_response_shape
from services.schedule_absence import response_integrity
from services.schedule_authority import slate_fields_from_game
from services.schedule_ingestion import _ingest_games, _parse_game
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import latest_qualified_source, replay
from utils.db import db


def pinned_schedule(cur, generation, day):
    request = calendar_requests(day)[0]
    cur.execute("""SELECT f.id, f.sha256 FROM candidate.generation_sources s
                   JOIN candidate.fetches f ON f.id=s.source
                   WHERE s.generation=%s AND f.endpoint=%s AND f.parameters=%s""",
                (generation, request.endpoint, Json(request.params())))
    rows = cur.fetchall()
    if len(rows) != 1 or rows[0][0] != latest_qualified_source(cur, request.endpoint, request.params()):
        raise ValueError(f'Missing or superseded selected schedule for {day}')
    source, digest = rows[0]
    observation = replay(cur, source)
    return dict(source=source, sha256=digest, acquired_at=observation.retrieved_at.astimezone(timezone.utc).isoformat()), observation


def reconcile_schedule(day, observation, *, verify_only=False):
    target = db.session.execute(text(
        "SELECT current_database(), inet_server_addr(), current_setting('listen_addresses')"
    )).one()
    if not target[0].endswith('_rehearsal_test') or tuple(target[1:]) != (None, ''):
        raise ValueError('Schedule replay requires a socket-only rehearsal database')
    db.session.execute(text('LOCK TABLE scheduled_games, slate_games IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
    body = observation.body
    games = ScheduleGames()
    games.response_shape = schedule_response_shape(body, start_date=str(day), end_date=str(day))
    if not response_integrity(games)['consistent'] or observation.retrieved_at.utcoffset() is None:
        raise ValueError(f'Incomplete schedule observation for {day}')
    stamp = observation.retrieved_at.astimezone(timezone.utc).replace(tzinfo=None)
    slate, teams = {}, {}
    for entry in body['dates']:
        for game in entry['games']:
            fields = slate_fields_from_game(game, synced_at=stamp)
            parsed = _parse_game(game)
            if not fields or not parsed or fields['game_pk'] in slate:
                raise ValueError(f'Incomplete or conflicting schedule identity for {day}')
            pk = fields['game_pk']
            slate[pk] = fields
            home = parsed.pop('home_team_id')
            away = parsed.pop('away_team_id')
            if home == away:
                raise ValueError(f'Duplicate schedule participant for {pk}')
            for team, opponent, side in ((home, away, 'home'), (away, home, 'away')):
                teams[pk, team] = dict(parsed, opponent_team_id=opponent, home_away=side,
                                       schedule_absent_since=None)
            games.append(game)

    def inventory():
        slates = SlateGame.query.filter(or_(SlateGame.game_date_et == day, SlateGame.game_pk.in_(slate))).all()
        sides = ScheduledGame.query.filter(or_(ScheduledGame.game_date == day, ScheduledGame.game_pk.in_(slate))).all()
        return {row.game_pk: row for row in slates}, {(row.game_pk, row.team_id): row for row in sides}

    stored, sides = inventory()
    if games and not stored and not sides and not verify_only:
        audit_since = db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        result = _ingest_games(games, source='v3_retained_schedule_rehearsal', commit=False,
                               synced_at=stamp, audit_since=audit_since, atomic=True)
        if (result['errors'] or result['games_ingested'] != len(games) or result['rows_suppressed'] != 0
                or result['rows_created'] != len(teams) or result['slate_games_created'] != len(slate)):
            raise ValueError(f'Incomplete schedule write or unavailable ownership audit for {day}')
        db.session.expire_all()
        stored, sides = inventory()
    for expected, actual in ((slate, stored), (teams, sides)):
        if expected.keys() != actual.keys():
            raise ValueError(f'Target has a different schedule population for {day}')
        for key, fields in expected.items():
            if any(getattr(actual[key], field) != value for field, value in fields.items()):
                raise ValueError(f'Target already carries different schedule evidence for {day}, game {key}')
