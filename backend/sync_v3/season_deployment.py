"""Retrospective regular-season deployment on official game dates."""

from collections import defaultdict
from datetime import date, timedelta
from types import SimpleNamespace

from services.mlb_club_directory import MLB_TEAM_IDS
from services.pitcher_role import ROLE_WINDOW_DAYS, classify_usage_role
from services.sync import _extract_leverage_index
from services.team_board_public_deployment_context import _recorded_li
from sync_v3.dependencies import consult
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.pitching_credit import uncredited_pitching_line
from sync_v3.workload import _game_workload
from sync_v3.evidence import latest_qualified_source, replay
from utils.innings import parse_mlb_innings_to_outs


COUNT_FIELDS = ('gamesPitched', 'gamesStarted', 'outs', 'saves', 'holds', 'saveOpportunities', 'gamesFinished')


class BaselineWithheld(ValueError):
    def __init__(self, reason, *, game_evidence=None):
        super().__init__(reason)
        self.game_evidence = game_evidence


def _splits(body, kind):
    groups = body.get('stats')
    if (not isinstance(groups, list) or len(groups) != 1
            or groups[0].get('type', {}).get('displayName') != kind
            or groups[0].get('group', {}).get('displayName') != 'pitching'
            or not isinstance(groups[0].get('splits'), list)):
        raise BaselineWithheld('missing_scoped_pitching_stats')
    return groups[0]['splits']


def _count(stats, key):
    value = stats.get(key)
    if type(value) is not int or value < 0:
        raise BaselineWithheld(f'missing_or_invalid_{key}')
    return value


def _counts(stats):
    counts = {key: _count(stats, key) for key in COUNT_FIELDS}
    ip = stats.get('inningsPitched')
    if ip is None or not str(ip).strip() or parse_mlb_innings_to_outs(ip) != counts['outs']:
        raise BaselineWithheld('official_outs_disagree')
    return counts


def _sum(rows):
    return {field: sum(row['counts'][field] for row in rows) for field in COUNT_FIELDS}


def _relief_sample(rows):
    relief = [r for r in rows if r['counts']['gamesStarted'] == 0]
    return {'relief_appearances': len(relief), 'official_starts_excluded': len(rows) - len(relief),
            'outs': sum(r['counts']['outs'] for r in relief),
            'saves': sum(r['counts']['saves'] for r in relief), 'holds': sum(r['counts']['holds'] for r in relief),
            'games_finished': sum(r['counts']['gamesFinished'] for r in relief),
            'games': sorted(r['pk'] for r in relief)}


def _observed_role(rows, through):
    reference = through + timedelta(days=1)
    start = reference - timedelta(days=ROLE_WINDOW_DAYS)
    logs = []
    for row in rows:
        counts = row['counts']
        if row['day'] >= start and counts['gamesStarted'] == 0:
            logs.append(SimpleNamespace(game_date=row['day'], innings_pitched_outs=counts['outs'],
                                        save=bool(counts['saves']), hold=bool(counts['holds']),
                                        save_situation=bool(counts['saveOpportunities']), leverage_index=row['li']))
    return {'window_start': start.isoformat(), 'through': through.isoformat(), 'reference': reference.isoformat(),
            'relief_appearances': len(logs), 'recorded_li_appearances': sum(log.leverage_index is not None for log in logs),
            'reason': None if start.year == through.year else 'role_window_precedes_season_source',
            'role': classify_usage_role(logs, reference_date=reference) if start.year == through.year else None}


def _check_retained_finals(cur, player, rows):
    endpoints = [f"/game/{r['pk']}/boxscore" for r in rows]
    for endpoint in endpoints:
        consult(cur, endpoint, {})
    # A retained final cites the schedule seen at acquisition. Reconfirm the game on
    # the latest receipt for that same daily schedule before using the pitching line.
    cur.execute("""WITH boxes AS (
                       SELECT DISTINCT ON (endpoint) endpoint,id,outcome FROM candidate.fetches
                       WHERE endpoint=ANY(%s) ORDER BY endpoint,received_at DESC,id DESC
                   )
                   SELECT b.endpoint,b.outcome,r.facts,b.id,c.context_id,prior.parameters,
                          latest.id,latest.outcome,confirmed.revision_id
                   FROM boxes b LEFT JOIN candidate.confirmations c ON c.source_id=b.id AND c.domain='final'
                   LEFT JOIN candidate.revisions r ON r.id=c.revision_id
                   LEFT JOIN candidate.fetches prior ON prior.id=c.context_id AND prior.endpoint='/schedule'
                   LEFT JOIN LATERAL (
                       SELECT f.id,f.outcome FROM candidate.fetches f
                       WHERE f.endpoint='/schedule' AND f.parameters=prior.parameters
                       ORDER BY f.received_at DESC,f.id DESC LIMIT 1
                   ) latest ON true
                   LEFT JOIN candidate.confirmations original ON original.source_id=c.context_id
                       AND original.domain='schedule'
                       AND original.identity IN (c.identity,c.identity || '/' || (prior.parameters->>'startDate'))
                   LEFT JOIN candidate.confirmations confirmed ON confirmed.source_id=latest.id
                       AND confirmed.revision_id=original.revision_id
                   ORDER BY b.endpoint""", (endpoints,))
    finals = cur.fetchall()
    for endpoint, _, _, source, context, params, latest, _, _ in finals:
        consult(cur, endpoint, {}, source, context)
        if params is not None:
            consult(cur, '/schedule', params, latest)
    by_game = {r['pk']: r for r in rows}
    verified = []
    for endpoint, outcome, lines, _, _, _, _, schedule_outcome, revision in finals:
        pk = int(endpoint.split('/')[2])
        expected = by_game[pk]
        if outcome != 'received' or lines is None:
            raise BaselineWithheld('overlapping_boxscore_unconfirmed')
        if schedule_outcome != 'received' or revision is None:
            raise BaselineWithheld('overlapping_boxscore_schedule_unconfirmed')
        appearances = [r for r in lines if r['pitcher_mlb_id'] == player]
        if len(appearances) != 1:
            raise BaselineWithheld('game_log_and_boxscore_player_conflict')
        line, = appearances
        counts = expected['counts']
        if (line['team_id'] != expected['team'] or line['game_date'] != expected['day'].isoformat()
                or line['games_started'] != counts['gamesStarted'] or line['outs_recorded'] != counts['outs']
                or any(line[field] is not None and line[field] != counts[key]
                       for field, key in [('hold', 'holds'), ('save', 'saves'), ('games_finished', 'gamesFinished'),
                                          ('save_situation', 'saveOpportunities')])):
            raise BaselineWithheld('game_log_and_boxscore_line_conflict')
        verified.append(pk)
    return sorted(verified)


def _confirm_uncredited(cur, player, team, pk, day):
    scope = dict(game_pk=pk, game_date=day.isoformat(), team_id=team)

    def missing(stage):
        return BaselineWithheld('uncredited_game_requires_official_final', game_evidence=dict(scope, stage=stage))

    if cur is None:
        raise missing('isolated_final_check_required')
    schedule = calendar_requests(day)[0]
    receipt = latest_qualified_source(cur, schedule.endpoint, schedule.params())
    if receipt is None:
        raise missing('qualified_schedule_required')
    games = [game for entry in replay(cur, receipt).body['dates'] for game in entry['games']
             if game['gamePk'] == pk and game.get('gameType') == 'R']
    if len(games) != 1:
        raise missing('regular_game_listing_required')
    final, reason = _game_workload(cur, games[0], day, receipt)
    if final is None:
        raise missing(reason or 'official_final_required')
    lines, (box_receipt, _) = final
    box = replay(cur, box_receipt).body
    sides = [side for side in box['teams'].values() if player in side['pitchers']]
    if (len(sides) != 1 or sides[0]['team']['id'] != team
            or not uncredited_pitching_line(sides[0]['players'][f'ID{player}']['stats']['pitching'])
            or any(line['pitcher_mlb_id'] == player for line in lines)):
        raise BaselineWithheld('uncredited_game_and_boxscore_disagree', game_evidence=dict(scope, stage='boxscore_disagreement'))


def season_deployment_facts(player, through, log, dated_totals, *, cur=None):
    """Check complete per-club totals before separating starts and relief."""
    by_club = defaultdict(list)
    seen = set()
    uncredited = []
    for item in _splits(log, 'gameLog'):
        if (item.get('sport', {}).get('id') != 1 or item.get('player', {}).get('id') != player
                or item.get('gameType') != 'R'
                or str(item.get('season')) != str(through.year)):
            raise BaselineWithheld('game_log_identity_or_season_conflict')
        day = date.fromisoformat(item['date'])
        if day.year != through.year:
            raise BaselineWithheld('game_log_date_conflict')
        if day > through:
            continue
        team = item.get('team', {}).get('id')
        pk = item.get('game', {}).get('gamePk')
        if team not in MLB_TEAM_IDS or type(pk) is not int or pk <= 0 or pk in seen:
            raise BaselineWithheld('game_log_club_or_game_conflict')
        seen.add(pk)
        counts = _counts(item['stat'])
        try:
            no_appearance = uncredited_pitching_line(item['stat'])
        except ValueError as exc:
            raise BaselineWithheld(str(exc)) from exc
        if no_appearance:
            _confirm_uncredited(cur, player, team, pk, day)
            uncredited.append(pk)
            continue
        if counts['gamesPitched'] != 1 or any(counts[k] > 1 for k in ('gamesStarted', 'saves', 'holds', 'saveOpportunities', 'gamesFinished')):
            raise BaselineWithheld('invalid_single_game_stat')
        by_club[team].append({'pk': pk, 'day': day, 'team': team, 'counts': counts,
                              'li': _recorded_li(_extract_leverage_index(item['stat']))})
    if not by_club:
        raise BaselineWithheld('no_supported_season_sample')
    totals = {}
    for item in _splits(dated_totals, 'byDateRange'):
        sport = item.get('sport', {}).get('id')
        if type(sport) is not int:
            raise BaselineWithheld('missing_dated_stats_sport')
        if sport != 1:
            # The provider also returns an all-sports aggregate, sometimes
            # carrying the same team ID. Only MLB splits establish MLB totals.
            continue
        if item.get('player') and item['player'].get('id') != player:
            raise BaselineWithheld('dated_stats_player_conflict')
        team = item['team']['id'] if item.get('team') else None
        if team in totals or (team is not None and team not in MLB_TEAM_IDS):
            raise BaselineWithheld('dated_stats_club_conflict')
        totals[team] = _counts(item['stat'])
    all_rows = [r for rows in by_club.values() for r in rows]
    if ({k for k in totals if k is not None} != set(by_club)
            or any(_sum(rows) != totals[team] for team, rows in by_club.items())
            or (None in totals and _sum(all_rows) != totals[None])):
        raise BaselineWithheld('log_and_dated_totals_disagree')
    recent_start = through - timedelta(days=13)
    checked = _check_retained_finals(cur, player, all_rows) if cur is not None else []
    return {**({'uncredited_games': sorted(uncredited)} if uncredited else {}),
            'overlapping_finals_checked': checked, 'season': _relief_sample(all_rows),
            'recent_14': _relief_sample([r for r in all_rows if r['day'] >= recent_start]),
            'by_club': {team: _relief_sample(rows) for team, rows in sorted(by_club.items())},
            'observed_role': _observed_role(all_rows, through)}


def pitcher_season_deployment(cur, player, through):
    result = {'mlb_player_id': player, 'through': through.isoformat(),
              'basis': 'official_regular_season_game_dates', 'sources': {}, 'facts': None, 'reason': None}
    bodies = []
    for request in pitcher_requests(through, [player]):
        source = latest_qualified_source(cur, request.endpoint, request.params())
        kind = request.params()['stats']
        result['sources'][kind] = source
        if source is not None:
            bodies.append(replay(cur, source).body)
    if len(bodies) < 2:
        result['reason'] = 'missing_game_log_or_dated_totals'
    else:
        try:
            result['facts'] = season_deployment_facts(player, through, *bodies, cur=cur)
        except BaselineWithheld as exc:
            result['reason'] = str(exc)
            if exc.game_evidence is not None:
                result['game_evidence'] = exc.game_evidence
        except (AttributeError, KeyError, TypeError, ValueError):
            result['reason'] = 'invalid_official_stat_shape'
    return result
