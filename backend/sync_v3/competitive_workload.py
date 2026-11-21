"""Confirm represented competitive workload across regular-season and playoff games."""

from collections import defaultdict
from datetime import date, timedelta
from types import SimpleNamespace

from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services.club_competition_status import COMPETITIVE_GAME_TYPES, POSTSEASON_GAME_TYPES
from services.fatigue import calculate_fatigue
from services.game_finality import classify_status
from services.pitcher_public_labels import build_public_arm_read
from services.workload_appearance import is_workload_appearance_log
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.evidence import latest_qualified_source, replay
from sync_v3.season_deployment import BaselineWithheld, _count, _counts
from sync_v3.workload import _game_workload, rest_from_calendar, windows_from_calendar, workload_lines


def _represented_arm(player, splits, official, reference):
    start = reference - timedelta(days=ACTIVE_WINDOW_DAYS)
    expected = {split['game']['gamePk']: split for split in splits
                if start <= date.fromisoformat(split['date']) < reference}
    rows = {row['game_pk']: row for row in official if row['pitcher_mlb_id'] == player}
    if rows.keys() != expected.keys():
        return None, 'game_log_and_final_population_conflict'
    logs = []
    for pk, row in rows.items():
        split = expected[pk]
        stats = split['stat']
        pitches = row['pitches_thrown']
        if (row['team_id'] != split['team']['id'] or row['game_date'] != split['date']
                or row['outs_recorded'] != stats['outs'] or pitches is None
                or pitches != stats.get('numberOfPitches')):
            return None, 'missing_or_conflicting_workload'
        log = SimpleNamespace(game_date=date.fromisoformat(row['game_date']), pitches_thrown=pitches,
                              innings_pitched_outs=row['outs_recorded'])
        if is_workload_appearance_log(log):
            logs.append(log)
    logs.sort(key=lambda log: log.game_date, reverse=True)
    if not logs:
        return None, 'no_recent_verified_workload'
    score = calculate_fatigue(SimpleNamespace(id=player), logs, reference_date=reference)
    availability = classify_availability(score, [log for log in logs if log.game_date >= reference - timedelta(days=4)],
                                         reference_date=reference, latest_game_date=logs[0].game_date)
    return {'availability': availability, 'arm_read': build_public_arm_read(availability),
            'last_workload': logs[0].game_date.isoformat(), 'games_compared': sorted(expected)}, None


def _game_scope(game):
    return (game['gameType'], game['officialDate'], classify_status(game['status']).state,
            game['teams']['away']['team']['id'], game['teams']['home']['team']['id'])


def round_workload(player, splits, lines, availability):
    games = set()
    window = []
    stages = {r['game_pk']: r['round'] for r in lines if r['pitcher_mlb_id'] == player}
    try:
        for split in splits:
            day = date.fromisoformat(split['date'])
            if not availability - timedelta(days=ACTIVE_WINDOW_DAYS) <= day < availability:
                continue
            pk = split['game']['gamePk']
            if (type(pk) is not int or pk <= 0 or day.year != availability.year
                    or type(split['team']['id']) is not int or split['team']['id'] < 1):
                raise ValueError('Invalid game log identity')
            if pk in games:
                return None, 'duplicate_game_log_appearance'
            if pk in stages and split['gameType'] != stages[pk]:
                return None, 'round_and_final_disagree'
            games.add(pk)
            window.append(split)
            stats = split['stat']
            _counts(stats)
            _count(stats, 'numberOfPitches')
    except (BaselineWithheld, KeyError, TypeError, ValueError):
        return None, 'invalid_round_game_log'
    return _represented_arm(player, window, lines, availability)


def competitive_window(cur, through, season):
    calendar = replay(cur, season['calendar_source']).body
    expected = {s['date']: {g['gamePk']: _game_scope(g) for g in s['games']} for s in calendar['dates']}
    sources = dict(calendar=season['calendar_source'], dates={}, decisions={})
    lines, rounds = [], set()
    for offset in range(ACTIVE_WINDOW_DAYS):
        day = through - timedelta(days=offset)
        request = calendar_requests(day)[0]
        source = latest_qualified_source(cur, request.endpoint, request.params())
        if not source or day.year != through.year:
            return dict(reason='missing_dated_schedule', gap_date=str(day))
        daily = {g['gamePk']: g for slate in replay(cur, source).body['dates'] for g in slate['games']
                 if g['gameType'] in COMPETITIVE_GAME_TYPES}
        if {pk: _game_scope(g) for pk, g in daily.items()} != expected.get(str(day), {}):
            return dict(reason='competitive_calendars_disagree', gap_date=str(day))
        sources['dates'][str(day)] = source
        for pk, game in daily.items():
            if classify_status(game['status']).state in ('postponed', 'cancelled'):
                continue
            if game['gameType'] in POSTSEASON_GAME_TYPES and pk not in season['decision_sources']:
                return dict(reason='verified_postseason_final_required', game_pk=pk)
            final, gap = _game_workload(cur, game, day, source)
            if gap or final is None:
                return dict(reason=gap or 'missing_compatible_final', game_pk=pk)
            lines.extend(dict(line, round=game['gameType']) for line in final[0])
            rounds.add(game['gameType'])
            if pk in season['decision_sources']:
                sources['decisions'][pk] = season['decision_sources'][pk]
    if not rounds.intersection(POSTSEASON_GAME_TYPES):
        return dict(reason='no_verified_postseason_games')
    return dict(reason=None, lines=lines, rounds=rounds, sources=sources)


def round_game_logs(cur, player, through, rounds):
    splits, receipts = [], {}
    for request in pitcher_requests(through, [player], postseason_rounds=rounds - {'R'}):
        params = request.params()
        kind = params['gameType']
        if params['stats'] != 'gameLog' or kind not in rounds:
            continue
        source = latest_qualified_source(cur, request.endpoint, params)
        if source is None:
            return None, receipts
        receipts[kind] = source
        groups = replay(cur, source).body['stats']
        if groups:
            splits.extend(groups[0]['splits'])
    return splits, receipts


def competitive_pitcher_weeks(window, members, through, roster_source):
    """Apply the Board's relief-workload rule game by game, including qualifying openers."""
    calendar = {date.fromisoformat(day): (dict(lines=[], sources=[receipt]), None)
                for day, receipt in window['sources']['dates'].items()}
    games = defaultdict(list)
    for line in window['lines']:
        games[line['game_date'], line['game_pk']].append(line)
    for (day, _), staff in games.items():
        calendar[date.fromisoformat(day)][0]['lines'].extend(workload_lines(staff))
    result = {}
    for player in members:
        week = windows_from_calendar(calendar, player, through, identity_sources=[roster_source], sizes=(7,))[7]
        result[player] = {k: v for k, v in week.items() if k not in ('sources', 'identity_sources')}
        rest = rest_from_calendar(calendar, player, through, identity_sources=[roster_source])
        result[player]['rest'] = {k: v for k, v in rest.items() if k not in ('sources', 'identity_sources')}
    return result
