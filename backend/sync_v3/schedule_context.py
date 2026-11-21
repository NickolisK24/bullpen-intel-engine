"""Retrospective calendar context from complete dated league schedule observations."""

from datetime import timedelta
from types import SimpleNamespace

from psycopg2.extras import Json

from services.mlb_club_directory import MLB_TEAM_IDS
from services.schedule_absence import is_unplayed_terminal_schedule_row
from services.schedule_context import LOOKAHEAD_DAYS, LOOKBACK_DAYS, build_team_schedule_context
from services.schedule_ingestion import _parse_game
from sync_v3.dependencies import consult
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import latest_qualified_source, replay


def _club_rows(games, team, day):
    rows = []
    for game in games:
        parsed = _parse_game(game)
        if team not in (parsed['home_team_id'], parsed['away_team_id']):
            continue
        terminal = is_unplayed_terminal_schedule_row(parsed['status_state'], parsed['status_code'])
        official_date = parsed['game_date']
        if terminal:
            # A postponed listing may already carry its makeup game's official date.
            parsed['game_date'] = day
        elif official_date != day or any(game.get(k) for k in ('resumeDate', 'resumeGameDate',
                                                               'resumedFrom', 'resumedFromDate')):
            return [], 'game_date_or_resumption_unresolved'
        home = parsed['home_team_id'] == team
        opponent = game['teams']['away' if home else 'home']['team']
        venue = game.get('venue') or {}
        if game['status'].get('startTimeTBD'):
            parsed['game_datetime'] = None
        rows.append(SimpleNamespace(**parsed, official_date=official_date, opponent_team_id=opponent['id'], opponent_name=opponent.get('name'),
                                    home_away='home' if home else 'away', venue_id=venue.get('id')))
    return rows, None


def missing_listings(cur, params, present, *, game_types=None):
    # A game disappearing from a subsequent league response is governed by a
    # separate retirement proof. Preserve the uncertainty in an offline read.
    cur.execute("""SELECT DISTINCT ON (split_part(c.identity,'/',1)) f.id,r.facts
                   FROM candidate.fetches f JOIN candidate.confirmations c ON c.source_id=f.id
                   JOIN candidate.revisions r ON r.id=c.revision_id
                   WHERE f.endpoint='/schedule' AND f.parameters=%s AND c.domain='schedule' AND NOT (split_part(c.identity,'/',1)=ANY(%s))
                   ORDER BY split_part(c.identity,'/',1), f.received_at DESC, f.id DESC""", (Json(params), [str(pk) for pk in present]))
    missing = {}
    for source, game in cur:
        if game_types and game['gameType'] not in game_types:
            continue
        row = _parse_game(game)
        if not is_unplayed_terminal_schedule_row(row['status_state'], row['status_code']):
            consult(cur, '/schedule', params, source)
            for side in game['teams'].values():
                missing.setdefault(side['team']['id'], set()).add(source)
    return missing


def club_schedule_context(cur, team, reference):
    if team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB club identity')
    result = {'team': team, 'reference': reference.isoformat(), 'basis': 'retrospective_mlb_calendar',
              'dates': {}, 'gaps': {}, 'context': None, 'scheduled_venue_changes': []}
    rows = []
    previous_venue = None
    for offset in range(-LOOKBACK_DAYS, LOOKAHEAD_DAYS + 1):
        day = reference + timedelta(days=offset)
        key = day.isoformat()
        request = calendar_requests(day)[0]
        source = latest_qualified_source(cur, request.endpoint, request.params())
        info = {'source': source, 'games': []}
        result['dates'][key] = info
        reason = 'missing_complete_schedule'
        dated = []
        if source is not None:
            games = [g for entry in replay(cur, source).body['dates'] for g in entry['games']]
            dated, reason = _club_rows(games, team, day)
            if team in missing_listings(cur, request.params(), {g['gamePk'] for g in games}):
                reason = 'previous_listing_requires_absence_proof'
        if reason:
            result['gaps'][key] = reason
            previous_venue = None
            continue
        rows.extend(dated)
        venues = set()
        for row in dated:
            info['games'].append({'game_pk': row.game_pk, 'status': row.status_state, 'status_code': row.status_code,
                                  'official_date': row.official_date.isoformat(), 'opponent': row.opponent_team_id, 'home_away': row.home_away,
                                  'series_game': row.series_game_number, 'series_length': row.games_in_series,
                                  'game_number': row.game_number, 'venue': row.venue_id})
            if not is_unplayed_terminal_schedule_row(row.status_state, row.status_code):
                venues.add(row.venue_id)
        if venues:
            current = next(iter(venues)) if len(venues) == 1 else None
            if previous_venue and current and previous_venue[1] != current:
                result['scheduled_venue_changes'].append({'from_date': previous_venue[0], 'from_venue': previous_venue[1],
                                                          'to_date': key, 'to_venue': current})
            previous_venue = (key, current) if current else None
    if not result['gaps']:
        names = {r.opponent_team_id: r.opponent_name for r in rows}
        result['context'] = build_team_schedule_context(team, reference, rows=rows, team_name_resolver=names.get)
    return result
