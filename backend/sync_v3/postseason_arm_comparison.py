"""Replay archived pitcher reads over a fully evidenced, competitive workload window."""

from datetime import timedelta

from services.club_competition_status import POSTSEASON_GAME_TYPES
from sync_v3.competition_calendar import competition_status
from sync_v3.evidence import replay
from sync_v3.readiness import verified_quiet_arm
from sync_v3.competitive_workload import competitive_window, round_game_logs, round_workload
from sync_v3.rosters import roster_on


def _compare_arm(player, splits, lines, availability, evidence):
    arm, reason = round_workload(player, splits, lines, availability)
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
    window = competitive_window(cur, through, season)
    if window['reason']:
        return dict(result, **window)
    rounds, lines = window['rounds'], window['lines']
    result['sources'] = dict(window['sources'], roster=roster[1])
    calendar = replay(cur, season['calendar_source']).body
    for row in group['records']:
        player = row['mlb_id']
        evidence = dict(archived=row['public_read'], public_id=row['pitcher_id'], game_logs={})
        result['arms'][player] = evidence
        if player not in members:
            evidence['reason'] = 'dated_active_pitcher_unconfirmed'
            continue
        splits, evidence['game_logs'] = round_game_logs(cur, player, through, rounds)
        if splits is None:
            evidence['reason'] = 'missing_round_game_log'
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
