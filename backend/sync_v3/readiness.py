"""Represented regular-season readiness. All outputs are isolated research candidates."""

from datetime import date, timedelta
from types import SimpleNamespace

from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services.availability_reference_date import trusted_slate_reference_dates
from services.fatigue import calculate_fatigue
from services.pitcher_public_labels import build_public_arm_read
from services.team_readiness_coverage import assess_team_coverage
from services.team_state_public_vocabulary import is_publishable_state, public_state_for
from services.workload_appearance import is_workload_appearance_log
from sync_v3.competition_calendar import competition_status
from sync_v3.group_performance import active_group_population
from sync_v3.workload import regular_day
from team_operations.bullpen_readiness import (
    _availability_distribution, _contract_a_decision, _coverage_inventory, _handedness_coverage,
    _normalize_pitcher_record, _team_state_partition,
)
from team_operations.contracts import TeamOperationsFreshnessMetadata, TeamOperationsTrustMetadata


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


def represented_readiness(cur, team, through):
    membership, reference = trusted_slate_reference_dates(through)
    league = competition_status(cur, reference)
    club = league['clubs'][team]
    result = {'team': team, 'membership_date': membership.isoformat(), 'reference_date': reference.isoformat(),
              'mode': 'retrospective_candidate', 'current_serving_eligible': False, 'competition': club,
              'calendar_source': league['calendar_source'], 'decision_sources': league['decision_sources'],
              'missing_decisions': league['missing_decisions'], 'reference_slate_source': league['reference_slate_source'],
              'team_state': None, 'arms': {}, 'reason': None}
    if club['status'] != 'active':
        result['reason'] = club['basis']
        return result
    if club['last_final_game_type'] != 'R' or league['postseason_started']:
        result['reason'] = 'regular_season_workload_scope_required'
        return result
    population, splits = active_group_population(cur, team, membership)
    result.update(roster_source=population['roster_source'], profiles=population['profiles'])
    if population['reason']:
        result['reason'] = population['reason']
        return result
    lines, sources = [], set()
    for offset in range(ACTIVE_WINDOW_DAYS):
        day = through - timedelta(days=offset)
        sample, gap = regular_day(cur, day)
        if gap or (day == through and not sample['lines']):
            result.update(reason=gap or 'slate_has_no_verified_relief_workload', gap_date=day.isoformat())
            return result
        sources.update(sample['sources'])
        lines.extend(sample['official_lines'])
    result['workload_sources'] = sorted(sources)
    records = []
    for member in population['members']:
        player = member['player']
        arm, reason = _represented_arm(player, splits[player], lines, reference)
        result['arms'][player] = {'read': arm, 'reason': reason}
        records.append(_normalize_pitcher_record({
            'availability_status': arm['availability']['availability_status'] if arm else 'unknown',
            'has_availability': bool(arm), 'has_current_workload': bool(arm),
        }))
    usable = sum(record['has_availability'] for record in records)
    reasons = {arm['reason'] for arm in result['arms'].values()}
    coverage = assess_team_coverage(authority_complete=True, source_current=True, active_bullpen_count=len(records),
                                    usable_record_count=usable, unresolved_record_count=len(records)-usable,
                                    source_conflict=bool(reasons - {None, 'no_recent_verified_workload'}))
    partition = _team_state_partition(_availability_distribution(records))
    # Freshness here is relative to the represented slate. No trusted snapshot exists in this path.
    code, rule, inputs = _contract_a_decision(
        partition, _coverage_inventory(records), _handedness_coverage(records),
        TeamOperationsFreshnessMetadata('current', data_through=through.isoformat()),
        TeamOperationsTrustMetadata(coverage.confidence, data_state=coverage.data_state,
                                   governance_state='internal_uncertified'))
    result.update(partition=partition, rule=rule, decisive_inputs=inputs, coverage_reason=coverage.reason_code)
    if is_publishable_state(code):
        result['team_state'] = public_state_for(code)
    else:
        result['reason'] = coverage.reason_code
    return result
