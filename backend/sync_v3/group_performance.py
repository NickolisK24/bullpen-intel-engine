"""Retrospective active-bullpen samples on the represented club and baseball date."""

from collections import defaultdict
from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services.performance_intelligence import AppearanceComponents, _exact_ratio
from services.performance_metrics import CURRENT_ACTIVE_PEN_ERA, CURRENT_ACTIVE_PEN_WHIP
from services.pitcher_performance import _rate
from services.pitcher_role import ROLE_WINDOW_DAYS
from services.public_team_performance import k_bb_from_official_inputs
from services.roster_status_sync import _two_way_eligible
from services.team_performance_evidence import DOMAINS, display
from sync_v3.evidence import replay
from sync_v3.performance import SOURCE_FIELDS, performance_line
from sync_v3.roster_scope import NON_PITCHING_POSITIONS
from sync_v3.rosters import roster_on
from sync_v3.season_deployment import pitcher_season_deployment
from sync_v3.workload import regular_day


def _role_logs(splits, start, through):
    rows = []
    for split in splits:
        day = date.fromisoformat(split['date'])
        if start <= day <= through:
            stats = split['stat']
            rows.append(SimpleNamespace(game_date=day, games_started=stats['gamesStarted'],
                                        innings_pitched_outs=stats['outs'], save=stats['saves'],
                                        hold=stats['holds'], save_situation=stats['saveOpportunities']))
    return rows


def _aggregate(rows):
    metrics = {}
    for definition in (CURRENT_ACTIVE_PEN_ERA, CURRENT_ACTIVE_PEN_WHIP):
        names = definition.required_row_components
        complete = [row for row in rows if all(row.get(k) is not None for k in names)]
        metric = {'covered': len(complete), 'value': None, 'minimum': definition.minimum_sample,
                  'unit': definition.minimum_sample_unit, 'sample': None, 'reason': 'incomplete_official_sample'}
        if rows and len(complete) == len(rows):
            totals = {k: sum(row[k] for row in rows) for k in names}
            components = AppearanceComponents(outs=totals['innings_pitched_outs'],
                                              earned_runs=totals.get('earned_runs', 0),
                                              hits=totals.get('hits_allowed', 0), walks=totals.get('walks', 0))
            metric['sample'] = definition.sample_measure(components)
            if metric['sample'] >= definition.minimum_sample:
                metric.update(value=definition.formatter(_exact_ratio(definition.numerator(components),
                              definition.denominator(components), definition.display_precision)), reason=None)
            else:
                metric['reason'] = 'below_minimum_sample'
        metrics[definition.metric_id] = metric
    for domain, fields in DOMAINS.items():
        covered = [row for row in rows if all(row.get(k) is not None for k in fields)]
        metric = {'covered': len(covered), 'value': None, 'inputs': None, 'reason': 'incomplete_official_sample'}
        if rows and len(covered) == len(rows):
            inputs = {f: sum(row[f] for row in rows) for f in fields}
            metric.update(inputs=inputs, reason=None)
            if domain == 'k_bb_percent':
                checked = k_bb_from_official_inputs(inputs)
                metric.update(value=checked['value'], reason=checked['reason_code'], minimum=checked['minimum_sample'])
            else:
                metric['value'] = display(domain, inputs)
        metrics[domain] = metric
    hr_rows = [row for row in rows if row.get('home_runs_allowed') is not None
               and row.get('innings_pitched_outs') is not None]
    hr9 = {'covered': len(hr_rows), 'outs': None, 'value': None}
    if rows and len(hr_rows) == len(rows):
        hr9['outs'] = sum(row['innings_pitched_outs'] for row in rows)
        hr9['value'] = _rate(sum(row['home_runs_allowed'] for row in rows), hr9['outs'], 27)
    return {'appearances': len(rows), 'metrics': metrics, 'descriptive_hr9': hr9}


def active_group_population(cur, team, through):
    result = {'team': team, 'through': through.isoformat(), 'roster_source': None, 'profiles': {},
              'members': [], 'windows': None, 'reason': None}
    roster = roster_on(cur, team, 'active', through)
    if not roster:
        result['reason'] = 'missing_dated_active_roster'
        return result, {}
    facts, result['roster_source'] = roster
    raw_roster = replay(cur, result['roster_source']).body['roster']
    if any((entry.get('position') or {}).get('code') == 'Y' or
           (_two_way_eligible(entry) and (entry.get('position') or {}).get('code') != '1')
           for entry in raw_roster):
        result['reason'] = 'two_way_role_evidence_unresolved'
        return result, {}
    start = through - timedelta(days=ROLE_WINDOW_DAYS)
    if start.year != through.year:
        result['reason'] = 'role_window_precedes_season_source'
        return result, {}
    arms, logs, splits = [], {}, {}
    for member in facts['members']:
        position = member['position']
        if position in NON_PITCHING_POSITIONS:
            continue
        if position != '1' or member['status'] != 'A':
            result['reason'] = 'active_pitching_population_unresolved'
            return result, {}
        player = member['id']
        profile = pitcher_season_deployment(cur, player, through)
        result['profiles'][player] = {'sources': profile['sources'], 'reason': profile['reason']}
        if profile['reason']:
            result['reason'] = 'incomplete_roster_role_evidence'
            return result, {}
        uncredited = set(profile['facts'].get('uncredited_games', []))
        splits[player] = [split for split in replay(cur, profile['sources']['gameLog']).body['stats'][0]['splits']
                          if date.fromisoformat(split['date']) <= through and split['game']['gamePk'] not in uncredited]
        logs[player] = _role_logs(splits[player], start, through)
        arms.append(SimpleNamespace(id=player, mlb_id=player, position='P', active=True, full_name=member['name'],
                                    roster_status='active', roster_status_source='mlb_stats_api:roster_sync:active'))
    contexts = eligible_bullpen_pitcher_contexts(arms, reference_date=through, logs_by_pitcher=logs,
                                                  use_role_authority=True)
    result['members'] = [{'player': context['pitcher'].id, 'role': context['eligibility']['role']}
                         for context in contexts]
    if not contexts:
        result['reason'] = 'active_group_empty'
    return result, splits


def active_group_performance(cur, team, through):
    result, splits = active_group_population(cur, team, through)
    if result['reason']:
        return result
    expected = defaultdict(dict)
    for member in result['members']:
        player = member['player']
        for split in splits[player]:
            day = date.fromisoformat(split['date'])
            if day <= through and split['team']['id'] == team and split['stat']['gamesStarted'] == 0:
                expected[day][split['game']['gamePk'], player] = split['stat']
    members = {m['player'] for m in result['members']}
    return _club_windows(cur, team, through, members, expected, result)


def _club_windows(cur, team, through, members, expected, result):
    season, recent = [], []
    result['dates'] = {}
    day = through.replace(month=1, day=1)
    while day <= through:
        due = expected.get(day, {})
        observed, reason = regular_day(cur, day, team=team)
        finals = {(r['game_pk'], r['pitcher_mlb_id']): r for r in (observed or {}).get('official_lines', [])
                  if r['team_id'] == team and r['pitcher_mlb_id'] in members and r['games_started'] == 0}
        if observed and set(finals) != set(due):
            result.update(reason='official_game_log_and_final_population_conflict', conflict_date=day.isoformat())
            return result
        if due:
            result['dates'][day.isoformat()] = {'sources': observed['sources'] if observed else [],
                                                'reason': reason, 'outings': [list(key) for key in sorted(due)]}
        for key, stats in due.items():
            final = finals.get(key, {})
            counts = {field: final.get(field) for field in SOURCE_FIELDS}
            counts['outs'] = final.get('outs_recorded')
            row, official = performance_line(day, counts, stats)
            values = {**official, 'innings_pitched_outs': row.innings_pitched_outs, 'hits_allowed': row.hits_allowed,
                      'walks': row.walks}
            # WHIP needs the walk count even if strikeout or batter coverage is missing.
            season.append(values)
            if day >= through - timedelta(days=29):
                recent.append(values)
        day += timedelta(days=1)
    season_start = through.replace(month=1, day=1)
    result['windows'] = {
        'recent_30': {'start': max(season_start, through - timedelta(days=29)).isoformat(), **_aggregate(recent)},
        'season': {'start': season_start.isoformat(), **_aggregate(season)},
    }
    return result
