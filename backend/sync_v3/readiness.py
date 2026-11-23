"""Represented competitive readiness. All outputs are isolated research candidates."""

from datetime import date, timedelta
from types import SimpleNamespace

from services.availability import ACTIVE_WINDOW_DAYS, AVAILABILITY_METHOD_VERSION, classify_availability
from services.availability_reference_date import trusted_slate_reference_dates
from services.fatigue import calculate_fatigue
from services.pitcher_public_labels import build_public_arm_read
from services.team_readiness_coverage import assess_team_coverage
from services.team_state_public_vocabulary import is_publishable_state, public_state_for
from sync_v3.competitive_workload import _represented_arm, competitive_pitcher_weeks, competitive_window, round_game_logs, round_workload
from sync_v3.rosters import roster_on
from sync_v3.membership_usage import represented_membership
from sync_v3.competition_calendar import competition_status
from sync_v3.group_performance import active_group_population
from sync_v3.workload import regular_day
from team_operations.bullpen_readiness import (
    _availability_distribution, _contract_a_decision, _coverage_inventory, _handedness_coverage,
    _normalize_pitcher_record, _team_state_partition,
)
from team_operations.contracts import TeamOperationsFreshnessMetadata, TeamOperationsTrustMetadata


def verified_quiet_arm(player, latest, reference):
    """Use only after reconciling the complete competitive workload window to the dated player log."""
    if not latest or date.fromisoformat(latest['game_date']) >= reference - timedelta(days=ACTIVE_WINDOW_DAYS):
        return None
    if (type(latest['game_pk']) is not int or latest['game_pk'] <= 0 or type(latest['outs']) is not int
            or latest['outs'] < 0 or type(latest['pitches']) is not int or latest['pitches'] < 0
            or not (latest['outs'] or latest['pitches'])):
        return None
    day = date.fromisoformat(latest['game_date'])
    log = SimpleNamespace(game_date=day, pitches_thrown=latest['pitches'], innings_pitched_outs=latest['outs'])
    score = calculate_fatigue(SimpleNamespace(id=player), [log], reference_date=reference)
    availability = classify_availability(score, [], reference_date=reference, latest_game_date=day)
    return dict(availability=availability, arm_read=build_public_arm_read(availability), last_workload=str(day),
                games_compared=[], verified_prior_outing=latest, availability_method=AVAILABILITY_METHOD_VERSION)


def represented_readiness(cur, team, through):
    membership, reference = trusted_slate_reference_dates(through)
    return _club_readiness(cur, team, membership, reference, competition_status(cur, reference))


def _club_readiness(cur, team, through, reference, league, date_evidence=None):
    membership = through
    club = league['clubs'][team]
    result = {'team': team, 'membership_date': membership.isoformat(), 'reference_date': reference.isoformat(),
              'mode': 'retrospective_candidate', 'current_serving_eligible': False, 'competition': club,
              'calendar_source': league['calendar_source'], 'decision_sources': league['decision_sources'],
              'missing_decisions': league['missing_decisions'], 'reference_slate_source': league['reference_slate_source'],
              'team_state': None, 'arms': {}, 'reason': None}
    if club['status'] != 'active':
        result['reason'] = club['basis']
        return result
    postseason = club['last_final_game_type'] != 'R' or league['postseason_started']
    result['availability_method'] = AVAILABILITY_METHOD_VERSION
    if postseason:
        result['workload_scope'] = 'competitive_postseason_window'
        roster = roster_on(cur, team, 'active', membership)
        if not roster:
            return dict(result, reason='missing_dated_active_roster')
        window = competitive_window(cur, through, league)
        if window['reason']:
            return dict(result, **window)
        evidence = represented_membership(cur, team, membership, roster)
        if evidence['status'] != 'represented':
            return dict(result, reason=evidence.get('reason') or 'incomplete_eligibility_sample',
                        eligibility_gaps=evidence['withheld'])
        members = evidence['candidate']
        result.update(roster_source=roster[1], population_method=evidence['basis'],
                      eligibility_games={p: s['games'] for p, s in evidence['samples'].items()},
                      workload_rounds=sorted(window['rounds']))
        latest = {p: evidence['samples'][p]['latest_workload'] for p in members}
    else:
        population, splits = active_group_population(cur, team, membership)
        result.update(roster_source=population['roster_source'], profiles=population['profiles'])
        for key in ('population_method', 'eligibility_games', 'eligibility_gaps'):
            if key in population:
                result[key] = population[key]
        if population['reason']:
            result['reason'] = population['reason']
            return result
        members = [member['player'] for member in population['members']]
        latest = population['latest_membership_work']
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
    arm_lines = window['lines'] if postseason else lines
    if reference > through + timedelta(days=1):
        # The membership and season totals still belong to the workload date.
        # Drop outings that have aged out of the arm classifier's shifted window.
        start = (reference - timedelta(days=ACTIVE_WINDOW_DAYS)).isoformat()
        arm_lines = [line for line in arm_lines if line['game_date'] >= start]
    records = []
    for player in members:
        if postseason:
            splits, _ = round_game_logs(cur, player, through, window['rounds'])
            if splits is None:
                return dict(result, arms={}, reason='missing_round_game_log')
            arm, reason = round_workload(player, splits, arm_lines, reference)
            if reason not in (None, 'no_recent_verified_workload'):
                return dict(result, arms={}, reason=reason)
        else:
            arm, reason = _represented_arm(player, splits[player], arm_lines, reference)
        current = arm is not None
        if reason == 'no_recent_verified_workload':
            arm = verified_quiet_arm(player, latest[player], reference)
            if arm is not None:
                reason = None
        result['arms'][player] = {'read': arm, 'reason': reason}
        records.append(_normalize_pitcher_record({
            'availability_status': arm['availability']['availability_status'] if arm else 'unknown',
            'has_availability': bool(arm), 'has_current_workload': current,
        }))
    if postseason:
        result['competitive_pitcher_weeks'] = competitive_pitcher_weeks(window, members, through, roster[1], date_evidence=date_evidence)
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


def review_availability_facts(cur, through, as_of, *, team=None, pitcher=None):
    """Recalculate isolated facts using a product date established by retained schedules."""
    from sync_v3.comparison import compare_readiness
    from sync_v3.rosters import dated_pitcher_sources
    from sync_v3.schedule_context import retrospective_availability_date
    from sync_v3.workload import load_calendar, rest_from_calendar

    if (team is not None and pitcher is not None) or as_of < through:
        raise ValueError('Specify at most one subject and a product day on or after coverage')
    evidence = retrospective_availability_date(cur, through, as_of)
    report = dict(scope='historical_availability_facts', date_evidence=evidence, team=team, pitcher=pitcher,
                  current_serving_eligible=False)
    if evidence['availability_reference'] is None:
        return dict(report, status='withheld', reason='schedule_evidence_incomplete')
    if pitcher is None:
        reference = date.fromisoformat(evidence['availability_reference'])
        competition = competition_status(cur, reference)
        clubs = {}
        for club in ([team] if team is not None else sorted(competition['clubs'])):
            facts = _club_readiness(cur, club, through, reference, competition, evidence)
            clubs[club] = dict(status='calculated' if facts['team_state'] else 'withheld',
                               reason=facts['reason'], readiness=facts, comparison=compare_readiness(facts))
        if team is not None:
            return dict(report, **clubs[team])
        return dict(report, clubs=clubs)
    calendar = load_calendar(cur, through)
    sources = dated_pitcher_sources(cur, pitcher, through)
    rest = rest_from_calendar(calendar, pitcher, through, identity_sources=sources, date_evidence=evidence)
    return dict(report, status='calculated' if rest['facts'] else 'withheld',
                workload_scope='regular_season', rest=rest)
