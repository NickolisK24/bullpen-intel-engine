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


def schedule_rows(game, stamp):
    fields = slate_fields_from_game(game, synced_at=stamp)
    parsed = _parse_game(game)
    if not fields or not parsed:
        raise ValueError('Incomplete retained schedule identity')
    pk = fields['game_pk']
    home = parsed.pop('home_team_id')
    away = parsed.pop('away_team_id')
    if home == away:
        raise ValueError(f'Duplicate schedule participant for {pk}')
    participants = {(pk, team): dict(parsed, opponent_team_id=opponent, home_away=side, schedule_absent_since=None)
                    for team, opponent, side in ((home, away, 'home'), (away, home, 'away'))}
    return pk, fields, participants


def retained_makeups(observations):
    """Bind both official time references, both clubs and the final to one canonical game."""
    from services.game_finality import classify_game_finality
    listings = {}
    for day, obs in observations.items():
        for entry in obs.body['dates']:
            for game in entry['games']:
                listings.setdefault(game['gamePk'], []).append((day, game, obs.retrieved_at))
    pairs = {}
    for pk, rows in listings.items():
        if len(rows) == 1:
            continue
        if len(rows) != 2:
            raise ValueError(f'Ambiguous dated schedule listings for {pk}')
        (earlier, old, old_stamp), (later, new, new_stamp) = sorted(rows, key=lambda row: row[0])
        if (earlier >= later or old['status'].get('detailedState') != 'Postponed'
                or not classify_game_finality(new).has_safe_final_status
                or old.get('rescheduleDate') != new['gameDate'] or new.get('rescheduledFrom') != old['gameDate']
                or new.get('rescheduledFromDate') != str(earlier) or new['officialDate'] != str(later)
                or any(old['teams'][s]['team']['id'] != new['teams'][s]['team']['id'] for s in ('home','away'))):
            raise ValueError(f'Conflicting dated schedule listings for {pk}')
        def fields(game, stamp):
            return schedule_rows(game, stamp.astimezone(timezone.utc).replace(tzinfo=None))[1:]
        pairs[pk] = (earlier, fields(old, old_stamp), later, fields(new, new_stamp))
    return pairs


def reconcile_schedule(day, observation, *, verify_only=False, private_staging=False, makeups=None):
    target = db.session.execute(text(
        "SELECT current_database(), inet_server_addr(), current_setting('listen_addresses')"
    )).one()
    if private_staging:
        from sync_v3.render_staging import HOST
        from sync_v3.staging_publication_target import TARGET
        url = db.engine.url
        role = db.session.execute(text('SELECT current_user')).scalar_one()
        if (url.host, url.database, target[0], role) != (HOST, TARGET, TARGET, 'sync_v3_staging_schedule'):
            raise ValueError('Unexpected private schedule target')
    elif not target[0].endswith('_rehearsal_test') or tuple(target[1:]) != (None, ''):
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
            pk, fields, participants = schedule_rows(game, stamp)
            if pk in slate:
                raise ValueError(f'Duplicate schedule identity for {day}')
            slate[pk] = fields
            teams.update(participants)
            games.append(game)

    def inventory():
        slates = SlateGame.query.filter(or_(SlateGame.game_date_et == day, SlateGame.game_pk.in_(slate))).all()
        sides = ScheduledGame.query.filter(or_(ScheduledGame.game_date == day, ScheduledGame.game_pk.in_(slate))).all()
        return {row.game_pk: row for row in slates}, {(row.game_pk, row.team_id): row for row in sides}

    stored, sides = inventory()
    previous = set()
    for pk, (old_day, old_rows, new_day, new_rows) in (makeups or {}).items():
        if pk not in stored or pk not in slate:
            continue
        alternate = new_rows if day == old_day else old_rows if day == new_day else None
        if alternate is None:
            continue
        other_slate, other_teams = alternate
        if (all(getattr(stored[pk], field) == value for field, value in other_slate.items())
                and all(key in sides and all(getattr(sides[key], field) == value for field, value in expected.items())
                        for key, expected in other_teams.items())):
            if day == old_day:
                slate[pk] = other_slate
                teams.update(other_teams)
            else:
                previous.add(pk)
    empty = not stored and not sides
    only_prior = previous and set(stored) == previous and {pk for pk, team in sides} == previous
    if games and (empty or only_prior) and not verify_only:
        audit_since = db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar_one()
        result = _ingest_games(games, source='v3_retained_schedule_rehearsal', commit=False,
                               synced_at=stamp, audit_since=audit_since, atomic=True)
        if (result['errors'] or result['games_ingested'] != len(games) or result['rows_suppressed'] != 0
                or result['rows_created'] != len(teams)-len(sides) or result['slate_games_created'] != len(slate)-len(stored)):
            raise ValueError(f'Incomplete schedule write or unavailable ownership audit for {day}')
        db.session.expire_all()
        stored, sides = inventory()
    for expected, actual in ((slate, stored), (teams, sides)):
        if expected.keys() != actual.keys():
            raise ValueError(f'Target has a different schedule population for {day}')
        for key, fields in expected.items():
            if any(getattr(actual[key], field) != value for field, value in fields.items()):
                raise ValueError(f'Target already carries different schedule evidence for {day}, game {key}')
