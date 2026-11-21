"""Replay archived pitcher reads over a fully evidenced, exclusively postseason workload window."""

from datetime import date, timedelta

from services.availability import ACTIVE_WINDOW_DAYS
from services.club_competition_status import COMPETITIVE_GAME_TYPES, POSTSEASON_GAME_TYPES
from services.game_finality import classify_status
from sync_v3.competition_calendar import competition_status
from sync_v3.discovery import calendar_requests, pitcher_requests
from sync_v3.evidence import latest_qualified_source, replay
from sync_v3.readiness import _represented_arm, verified_quiet_arm
from sync_v3.season_deployment import BaselineWithheld, _count, _counts
from sync_v3.rosters import roster_on
from sync_v3.workload import _game_workload


def _game_scope(game):
    return (game['gameType'], game['officialDate'], classify_status(game['status']).state,
            game['teams']['away']['team']['id'], game['teams']['home']['team']['id'])


def _compare_arm(player, splits, lines, availability, evidence):
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
                return dict(evidence, reason='duplicate_game_log_appearance')
            if pk in stages and split['gameType'] != stages[pk]:
                return dict(evidence, reason='round_and_final_disagree')
            games.add(pk)
            window.append(split)
            stats = split['stat']
            _counts(stats)
            _count(stats, 'numberOfPitches')
    except (BaselineWithheld, KeyError, TypeError, ValueError):
        return dict(evidence, reason='invalid_round_game_log')
    arm, reason = _represented_arm(player, window, lines, availability)
    if arm is None:
        return dict(evidence, reason=reason, replay=None)
    return dict(evidence, reason=None, availability_status=arm['availability']['availability_status'], replay=arm['arm_read'], matches=arm['arm_read'] == evidence['archived'],
                games_compared=arm['games_compared'])


def _method_replay(membership, arms, through, archive_receipt):
    from services.availability import AVAILABILITY_METHOD_VERSION
    from services.team_readiness_coverage import assess_team_coverage
    from services.team_state_public_vocabulary import is_publishable_state, public_state_for
    from team_operations.bullpen_readiness import (
        _availability_distribution, _contract_a_decision, _coverage_inventory, _handedness_coverage,
        _normalize_pitcher_record, _team_state_partition,
    )
    from team_operations.contracts import TeamOperationsFreshnessMetadata, TeamOperationsTrustMetadata

    stamp = archive_receipt.get('availability_method_version')
    result = dict(method=AVAILABILITY_METHOD_VERSION, archive_method=stamp, current_serving_eligible=False,
                  same_method_comparable=stamp == AVAILABILITY_METHOD_VERSION, quiet_arms={})
    if membership['status'] != 'matched' or set(membership['candidate']) != set(arms):
        return dict(result, status='withheld', reason='independent_membership_required')
    reference = through + timedelta(days=1)
    records = []
    for player, arm in arms.items():
        status = arm.get('availability_status')
        current = arm['reason'] is None
        if arm['reason'] == 'no_recent_verified_workload':
            latest = membership['samples'][player]['latest_workload']
            quiet = verified_quiet_arm(player, latest, reference)
            if quiet is not None:
                availability = quiet['availability']
                status = availability['availability_status']
                result['quiet_arms'][player] = dict(latest_workload=latest, data_state=availability['data_state'],
                                                    replay=quiet['arm_read'], archive=arm['archived'])
        if status is None:
            return dict(result, status='withheld', reason=arm['reason'], player=player)
        records.append(_normalize_pitcher_record(dict(availability_status=status, has_availability=True,
                                                      has_current_workload=current)))
    coverage = assess_team_coverage(authority_complete=True, source_current=True, active_bullpen_count=len(records),
                                    usable_record_count=len(records), unresolved_record_count=0)
    partition = _team_state_partition(_availability_distribution(records))
    code, rule, inputs = _contract_a_decision(
        partition, _coverage_inventory(records), _handedness_coverage(records),
        TeamOperationsFreshnessMetadata('current', data_through=str(through)),
        TeamOperationsTrustMetadata(coverage.confidence, data_state=coverage.data_state, governance_state='internal_uncertified'))
    return dict(result, status='historical_method_replay', partition=partition, decisive_rule=rule,
                decisive_inputs=inputs, team_state=public_state_for(code) if is_publishable_state(code) else None,
                archived_label=archive_receipt['value'].get('public_label'))


def compare_postseason_arms(cur, club, through, reference):
    """Check the published arm cohort independently of eligibility and Team State selection."""
    availability = through + timedelta(days=1)
    result = dict(scope='archived_postseason_arm_reads', team=club, through=str(through),
                  availability_reference=str(availability), archive=reference.provenance,
                  current_serving_eligible=False, arms={}, sources={}, status='withheld')
    if (reference.provenance['data_through'] != str(through) or reference.membership_reference != str(through)
            or reference.availability_reference != str(availability)):
        return dict(result, reason='edition_dates_differ')
    inputs = reference.available_inputs.get(str(club))
    if not inputs:
        return dict(result, reason='archived_arm_inputs_unavailable')
    group = inputs['arm_reads']
    public_ids = [r['pitcher_id'] for r in group['records']]
    if (not public_ids or len(set(public_ids)) != len(public_ids) or sorted(public_ids) != sorted(group['member_pitcher_ids'])
            or group.get('missing_record_pitcher_ids') != []):
        return dict(result, reason='incomplete_archived_arm_inputs')
    season = competition_status(cur, availability)
    if not season['calendar_source'] or season['clubs'][club]['status'] != 'active':
        return dict(result, reason='active_competition_unconfirmed')
    roster = roster_on(cur, club, 'active', through)
    if not roster:
        return dict(result, reason='missing_dated_active_roster')
    members = {m['id'] for m in roster[0]['members'] if m['status'] == 'A' and m['position'] == '1'}
    calendar = replay(cur, season['calendar_source']).body
    expected = {s['date']: {g['gamePk']: _game_scope(g) for g in s['games']} for s in calendar['dates']}
    sources = result['sources']
    sources.update(calendar=season['calendar_source'], roster=roster[1], dates={}, decisions={})
    lines, rounds = [], set()
    for offset in range(ACTIVE_WINDOW_DAYS):
        day = through - timedelta(days=offset)
        request = calendar_requests(day)[0]
        source = latest_qualified_source(cur, request.endpoint, request.params())
        if not source or day.year != through.year:
            return dict(result, reason='missing_dated_schedule', gap_date=str(day))
        daily = {g['gamePk']: g for slate in replay(cur, source).body['dates'] for g in slate['games']
                 if g['gameType'] in COMPETITIVE_GAME_TYPES}
        if {pk: _game_scope(g) for pk, g in daily.items()} != expected.get(str(day), {}):
            return dict(result, reason='competitive_calendars_disagree', gap_date=str(day))
        sources['dates'][str(day)] = source
        for pk, game in daily.items():
            if classify_status(game['status']).state in ('postponed', 'cancelled'):
                continue
            if game['gameType'] not in POSTSEASON_GAME_TYPES or pk not in season['decision_sources']:
                return dict(result, reason='verified_postseason_final_required', game_pk=pk)
            final, gap = _game_workload(cur, game, day, source)
            if gap or final is None:
                return dict(result, reason=gap or 'missing_compatible_final', game_pk=pk)
            lines.extend(dict(line, round=game['gameType']) for line in final[0])
            rounds.add(game['gameType'])
            sources['decisions'][pk] = season['decision_sources'][pk]
    if not rounds:
        return dict(result, reason='no_verified_postseason_games')
    for row in group['records']:
        player = row['mlb_id']
        evidence = dict(archived=row['public_read'], public_id=row['pitcher_id'], game_logs={})
        result['arms'][player] = evidence
        if player not in members:
            evidence['reason'] = 'dated_active_pitcher_unconfirmed'
            continue
        splits = []
        for request in pitcher_requests(through, [player], postseason_rounds=rounds):
            kind = request.params()['gameType']
            if kind not in rounds:
                continue
            source = latest_qualified_source(cur, request.endpoint, request.params())
            if source is None:
                evidence['reason'] = 'missing_round_game_log'
                break
            evidence['game_logs'][kind] = source
            groups = replay(cur, source).body['stats']
            if groups:
                splits.extend(groups[0]['splits'])
        else:
            result['arms'][player] = _compare_arm(player, splits, lines, availability, evidence)
    from sync_v3.membership_usage import represented_membership
    from sync_v3.competition_calendar import calendar_games
    from sync_v3.discovery import competition_calendar_request

    season_games = calendar_games(competition_calendar_request(through.year).params(), calendar)
    prior_rounds = {row['game_type'] for day, row, _ in season_games.values()
                    if day <= through and row['game_type'] in POSTSEASON_GAME_TYPES}
    membership = represented_membership(cur, club, through, roster, prior_rounds)
    result['membership_comparison'] = membership
    if membership['status'] == 'represented':
        published = {row['mlb_id'] for row in group['records']}
        candidate = set(membership['candidate'])
        membership.update(status='matched' if candidate == published else 'membership_differs',
                          archive=sorted(published), only_candidate=sorted(candidate-published),
                          only_archive=sorted(published-candidate))
    result['availability_method_replay'] = _method_replay(membership, result['arms'], through, reference.team_receipts[str(club)])
    matches = sum(arm.get('matches') is True for arm in result['arms'].values())
    differences = sum(arm.get('matches') is False for arm in result['arms'].values())
    return dict(result, status='compared_archived_cohort' if matches + differences else 'no_comparable_arm_reads',
                matched=matches, different=differences, withheld=len(public_ids)-matches-differences, rounds=sorted(rounds))
