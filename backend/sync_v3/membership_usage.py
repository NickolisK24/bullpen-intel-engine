"""Reproduce the Board's ten-appearance eligibility sample at a historical cutoff."""

from datetime import date
from types import SimpleNamespace

from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services.club_competition_status import POSTSEASON_GAME_TYPES
from services.roster_status_sync import _two_way_eligible
from sync_v3.depth import _pitchers
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.evidence import latest_qualified_source, replay
from sync_v3.season_deployment import BaselineWithheld, check_pitcher_final, qualified_game_rows
from sync_v3.workload import _game_workload


def _most_recent(rows):
    ordered = sorted(rows, key=lambda r: (r['day'], r['pk']), reverse=True)
    if len({r['pk'] for r in ordered}) != len(ordered):
        raise BaselineWithheld('duplicate_eligibility_game')
    # Production breaks date ties with its local GameLog.id. A public gamePk
    # cannot reproduce that tiebreaker at the tenth appearance.
    if len(ordered) > 10 and ordered[9]['day'] == ordered[10]['day']:
        raise BaselineWithheld('eligibility_sample_boundary_ambiguous')
    return ordered[:10]


def _debut(cur, team, through, player, listed):
    endpoint = f'/teams/{team}/roster'
    params = dict(date=str(through), rosterType='active', hydrate='person')
    source = latest_qualified_source(cur, endpoint, params)
    if source is None:
        raise BaselineWithheld('missing_mlb_debut_evidence')
    body = replay(cur, source).body
    pitchers, reason = _pitchers(body, team, team, 'active')
    if reason or pitchers.keys() != listed.keys() or any(
            pitchers[p]['status_codes'] != listed[p]['status_codes'] for p in listed):
        raise BaselineWithheld('dated_pitcher_rosters_disagree')
    values = {r['person'].get('mlbDebutDate') for r in body['roster'] if r['person']['id'] == player}
    if len(values) != 1 or not all(values):
        raise BaselineWithheld('missing_mlb_debut_evidence')
    day = date.fromisoformat(values.pop())
    if day > through:
        raise BaselineWithheld('mlb_debut_after_membership_date')
    return day, source


def _eligibility_sample(cur, team, player, through, listed, rounds, final_cache):
    rows, sources = [], []
    debut = None
    end = through
    while True:
        bodies = {}
        for req in pitcher_requests(end, [player], postseason_rounds=rounds, round_totals=True):
            params = req.params()
            source = latest_qualified_source(cur, req.endpoint, params)
            if source is None:
                raise BaselineWithheld('missing_eligibility_stats', game_evidence=dict(year=end.year, round=params['gameType'], stats=params['stats']))
            sources.append(source)
            bodies[params['gameType'], params['stats']] = replay(cur, source).body
        for stage in ('R', *sorted(rounds)):
            clubs, _ = qualified_game_rows(player, end, bodies[stage, 'gameLog'], bodies[stage, 'byDateRange'],
                                           cur=cur, game_type=stage, allow_empty=True)
            rows.extend(dict(row, game_type=stage) for club_rows in clubs.values() for row in club_rows)
        if len(rows) >= 10:
            break
        if debut is None:
            debut, source = _debut(cur, team, through, player, listed)
            sources.append(source)
        if end.year == debut.year:
            break
        end = date(end.year-1, 12, 31)
        rounds = POSTSEASON_GAME_TYPES
    if debut and any(row['day'] < debut for row in rows):
        raise BaselineWithheld('appearance_predates_mlb_debut')
    selected = _most_recent(rows)
    latest = None
    for row in selected:
        day, pk = row['day'], row['pk']
        key = day, pk, row['game_type']
        if key not in final_cache:
            request = calendar_requests(day)[0]
            receipt = latest_qualified_source(cur, request.endpoint, request.params())
            games = [g for slate in replay(cur, receipt).body['dates'] for g in slate['games']
                     if g['gamePk'] == pk and g['gameType'] == row['game_type']] if receipt else []
            final, reason = _game_workload(cur, games[0], day, receipt) if len(games) == 1 else (None, 'missing_scoped_game')
            if not final:
                raise BaselineWithheld('eligibility_game_not_confirmed', game_evidence=dict(game_pk=pk, reason=reason))
            final_cache[key] = final[0], (receipt, *final[1])
        lines, receipts = final_cache[key]
        line = check_pitcher_final(player, row, lines, for_membership=True)
        if row is selected[0] and (line['outs_recorded'] > 0 or (line['pitches_thrown'] or 0) > 0):
            latest = dict(game_pk=pk, game_date=str(day), pitches=line['pitches_thrown'], outs=line['outs_recorded'])
        sources.extend(receipts)
    return selected, sorted(set(sources)), latest


def represented_membership(cur, team, through, roster, rounds=None):
    from sync_v3.competition_calendar import calendar_games
    from sync_v3.discovery import competition_calendar_request
    raw = replay(cur, roster[1]).body
    listed, reason = _pitchers(raw, team, team, 'active')
    result = dict(basis='latest_ten_official_pitching_appearances', through=str(through), roster_source=roster[1],
                  samples={}, withheld={}, status='withheld')
    if rounds is None:
        calendar = competition_calendar_request(through.year)
        source = latest_qualified_source(cur, calendar.endpoint, calendar.params())
        if source is None:
            return dict(result, reason='missing_competition_calendar')
        season = calendar_games(calendar.params(), replay(cur, source).body)
        rounds = {game['game_type'] for day, game, _ in season.values()
                  if day <= through and game['game_type'] in POSTSEASON_GAME_TYPES}
    if reason or any(row['position']['code'] == 'Y' or
                     (_two_way_eligible(row) and row['position']['code'] != '1') for row in raw['roster']):
        return dict(result, reason=reason or 'two_way_role_evidence_unresolved')
    arms, logs, final_cache = [], {}, {}
    for player, fields in sorted(listed.items()):
        if fields['status_codes'] != ['A']:
            result['withheld'][player] = dict(reason='active_pitching_population_unresolved')
            continue
        try:
            sample, sources, latest = _eligibility_sample(cur, team, player, through, listed, rounds, final_cache)
        except BaselineWithheld as exc:
            result['withheld'][player] = dict(reason=str(exc), evidence=exc.game_evidence)
            continue
        except (KeyError, ValueError, TypeError, AttributeError):
            result['withheld'][player] = dict(reason='invalid_official_eligibility_input')
            continue
        result['samples'][player] = dict(games=[row['pk'] for row in sample], sources=sources, latest_workload=latest,
                                         starts=sum(row['counts']['gamesStarted'] for row in sample))
        arms.append(SimpleNamespace(id=player, mlb_id=player, position='P', active=True,
                                    full_name=next(m['name'] for m in roster[0]['members'] if m['id'] == player),
                                    roster_status='active', roster_status_source='mlb_stats_api:roster_sync:active'))
        logs[player] = [SimpleNamespace(game_date=row['day'], games_started=row['counts']['gamesStarted'],
                                        innings_pitched_outs=row['counts']['outs'], save=row['counts']['saves'],
                                        hold=row['counts']['holds'], save_situation=row['counts']['saveOpportunities'])
                        for row in sample]
    if result['withheld']:
        return result
    contexts = eligible_bullpen_pitcher_contexts(arms, reference_date=through, logs_by_pitcher=logs,
                                                  use_role_authority=True)
    roles = {c['pitcher'].id: c['eligibility']['role'] for c in contexts}
    return dict(result, status='represented', candidate=sorted(roles), roles=roles)
