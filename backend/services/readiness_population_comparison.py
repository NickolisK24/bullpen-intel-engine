"""Same-moment comparison of the two Team State populations. READ-ONLY.

Two populations decide Team State, and nothing has ever proven they are the same
set:

* the **board population** — the governed current-availability population the
  canonical Team Board builder freezes as
  ``trusted_team_boards.default_pitcher_ids``;
* the **readiness population** — the canonical active bullpen that
  ``resolve_active_bullpen_membership`` resolves and
  ``resolve_readiness_population`` feeds to the readiness distributions.

This module is pure arithmetic over sets and already-governed availability
statuses. It issues no query, touches no session, and reaches no model. The
caller resolves both populations inside one application context at one captured
moment and hands the results here.

Nothing here is a classifier. The shadow Contract A calculation below re-derives
a state offline so a population difference can be judged for consequence, and it
is written nowhere: no snapshot, no artifact, no response, no table. Production
Team State semantics, thresholds, vocabulary, and classifier are untouched.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping, Optional, Sequence


COMPARISON_VERSION = 'team_state_population_comparison_v1'

# Governed availability statuses, normalised case-insensitively. These are the
# published values from ``services.availability`` (Available / Monitor /
# Limited / Avoid / Unavailable); no new status is defined here.
CLEAN_STATUSES = frozenset({'available'})
MODERATE_MONITOR_STATUSES = frozenset({'monitor'})
MODERATE_LIMITED_STATUSES = frozenset({'limited'})
SEVERE_AVOID_STATUSES = frozenset({'avoid'})
SEVERE_UNAVAILABLE_STATUSES = frozenset({'unavailable'})

DIFFERENCE_CLEAN = 'CLEAN'
DIFFERENCE_MODERATE_MONITOR = 'MODERATE_MONITOR'
DIFFERENCE_MODERATE_LIMITED = 'MODERATE_LIMITED'
DIFFERENCE_SEVERE_AVOID = 'SEVERE_AVOID'
DIFFERENCE_SEVERE_UNAVAILABLE = 'SEVERE_UNAVAILABLE'
DIFFERENCE_UNKNOWN = 'UNKNOWN'

MODERATE_CLASSES = frozenset({DIFFERENCE_MODERATE_MONITOR, DIFFERENCE_MODERATE_LIMITED})

# Founder-approved Contract A, held as exact rationals so a boundary case is
# decided by arithmetic rather than by float representation. Shares are also
# emitted as floats for readability, but never compared as floats.
CONTRACT_A = {
    'contract': 'team_state_contract_a',
    'basis': 'status_only',
    'clean_definition': 'Available',
    'moderate_definition': 'Monitor + Limited',
    'severe_definition': 'Avoid + Unavailable',
    'clean_share_fresh_min': (3, 5),          # >= 0.60
    'clean_count_fresh_min': 5,
    'severe_count_fresh_max': 1,
    'clean_count_vulnerable_max': 2,
    'severe_share_vulnerable_min': (1, 3),
}

# Pre-registered mechanical readings, fixed before any production figure exists.
PASS_A_MIN_EXACT_MATCHES = 28
PASS_B_MAX_ARM_DIFFERENCE = 1
FAIL_MIN_CLEAN_AXIS_TEAMS = 2  # "repeated/systematic" == two or more teams

EXPECTED_TEAM_COUNT = 30


def _normalise(status) -> str:
    return str(status or '').strip().lower()


def classify_difference(status) -> str:
    """Class of one arm from its governed availability status.

    An absent, blank, or ungoverned status is ``UNKNOWN``. It is never treated
    as clean — a population difference whose status we cannot read must not be
    dismissed as harmless.
    """
    normalised = _normalise(status)
    if normalised in CLEAN_STATUSES:
        return DIFFERENCE_CLEAN
    if normalised in MODERATE_MONITOR_STATUSES:
        return DIFFERENCE_MODERATE_MONITOR
    if normalised in MODERATE_LIMITED_STATUSES:
        return DIFFERENCE_MODERATE_LIMITED
    if normalised in SEVERE_AVOID_STATUSES:
        return DIFFERENCE_SEVERE_AVOID
    if normalised in SEVERE_UNAVAILABLE_STATUSES:
        return DIFFERENCE_SEVERE_UNAVAILABLE
    return DIFFERENCE_UNKNOWN


def _share(count: int, denominator: int) -> Optional[float]:
    """Ratio guarded against an absent denominator. Never invents a value."""
    if not denominator:
        return None
    return count / denominator


def shadow_partition(statuses: Sequence[Any]) -> dict:
    """Clean / moderate / severe / unknown tally over governed statuses.

    A straight count of values the availability authority already published.
    Nothing is classified, escalated, or recomputed, and no raw score is read.
    """
    counts = {'clean': 0, 'moderate': 0, 'severe': 0, 'unknown': 0}
    for status in statuses:
        difference_class = classify_difference(status)
        if difference_class == DIFFERENCE_CLEAN:
            counts['clean'] += 1
        elif difference_class in MODERATE_CLASSES:
            counts['moderate'] += 1
        elif difference_class == DIFFERENCE_UNKNOWN:
            counts['unknown'] += 1
        else:
            counts['severe'] += 1
    total = sum(counts.values())
    return {
        'basis': 'status_only',
        'population_count': total,
        'clean_count': counts['clean'],
        'moderate_count': counts['moderate'],
        'severe_count': counts['severe'],
        'unknown_count': counts['unknown'],
        'clean_share': _share(counts['clean'], total),
        'moderate_share': _share(counts['moderate'], total),
        'severe_share': _share(counts['severe'], total),
        'unknown_share': _share(counts['unknown'], total),
    }


def shadow_state(partition: Mapping[str, Any]) -> Optional[str]:
    """Offline Contract A state for one partition, or ``None`` for no population.

    A zero-arm population has no Team State. Contract A's clean-count floor
    would nominally read it as Vulnerable, but reporting a state for a team with
    no arms would convert a data condition into a classification. That guard is
    declared here, ahead of any production figure, and applies only to the empty
    case — every non-empty population is decided by Contract A exactly as
    approved.
    """
    total = partition['population_count']
    if not total:
        return None

    clean = partition['clean_count']
    severe = partition['severe_count']
    severe_share = Fraction(severe, total)
    clean_share = Fraction(clean, total)

    vulnerable_clean_max = CONTRACT_A['clean_count_vulnerable_max']
    severe_share_min = Fraction(*CONTRACT_A['severe_share_vulnerable_min'])
    if clean <= vulnerable_clean_max or severe_share >= severe_share_min:
        return 'Vulnerable'

    if (
        clean_share >= Fraction(*CONTRACT_A['clean_share_fresh_min'])
        and clean >= CONTRACT_A['clean_count_fresh_min']
        and severe <= CONTRACT_A['severe_count_fresh_max']
    ):
        return 'Fresh'

    return 'Stretched'


def _population_block(pitcher_ids, statuses: Mapping[Any, Any]) -> dict:
    """Partition plus shadow state for one population.

    An id the availability authority never scored contributes an ``unknown``
    status rather than being dropped, so the denominator stays the population
    actually resolved.
    """
    ordered = sorted(pitcher_ids)
    block = shadow_partition([statuses.get(pitcher_id) for pitcher_id in ordered])
    block['shadow_state'] = shadow_state(block)
    block['shadow_contract'] = CONTRACT_A['contract']
    return block


def _arm_row(pitcher_id, direction, statuses, arm_details) -> dict:
    """One differing arm, carrying only facts the caller actually resolved."""
    status = statuses.get(pitcher_id)
    detail = arm_details.get(pitcher_id) or {}
    reason = (
        'in_board_population_not_in_roster_authority'
        if direction == 'only_in_board'
        else 'in_roster_authority_not_in_board_population'
    )
    return {
        'pitcher_id': pitcher_id,
        'difference_direction': direction,
        'difference_class': classify_difference(status),
        'membership_reason': reason,
        'availability_status': status if status else None,
        'availability_data_state': detail.get('availability_data_state'),
        'raw_score': detail.get('raw_score'),
        'active': detail.get('active'),
        'team_id': detail.get('team_id'),
        'roster_status': detail.get('roster_status'),
    }


def compare_team(
    *,
    club,
    reference_date,
    board_ids,
    readiness_ids,
    statuses: Mapping[Any, Any],
    arm_details: Mapping[Any, Mapping[str, Any]],
    authority_complete: bool,
    consumed_ids,
    published_board_ids=None,
) -> dict:
    """Compare both populations for one club at one moment.

    ``consumed_ids`` is what ``resolve_readiness_population`` actually returned,
    passed in so the runtime contract is measured rather than assumed: the
    records the readiness pipeline consumes should be exactly the board records
    inside the resolved membership.
    """
    board = frozenset(board_ids)
    readiness = frozenset(readiness_ids)
    only_board = board - readiness
    only_readiness = readiness - board
    intersection = board & readiness

    differing = [
        _arm_row(pitcher_id, 'only_in_board', statuses, arm_details)
        for pitcher_id in sorted(only_board)
    ] + [
        _arm_row(pitcher_id, 'only_in_readiness', statuses, arm_details)
        for pitcher_id in sorted(only_readiness)
    ]
    clean_axis = [
        arm for arm in differing if arm['difference_class'] == DIFFERENCE_CLEAN
    ]

    board_block = _population_block(board, statuses)
    readiness_block = _population_block(readiness, statuses)

    runtime_consistent = frozenset(consumed_ids) == intersection

    flags = []
    if not authority_complete:
        flags.append('readiness_authority_incomplete')
    if not board:
        flags.append('board_population_empty')
    if not readiness:
        flags.append('readiness_population_empty')
    if not runtime_consistent:
        flags.append('runtime_population_mismatch')

    row = {
        'team_id': club.team_id,
        'team_abbreviation': club.abbreviation,
        'reference_date': str(reference_date),

        'board_population_count': len(board),
        'readiness_population_count': len(readiness),
        'board_pitcher_ids': sorted(board),
        'readiness_pitcher_ids': sorted(readiness),

        'intersection_pitcher_ids': sorted(intersection),
        'only_in_board': sorted(only_board),
        'only_in_readiness': sorted(only_readiness),
        'symmetric_difference_count': len(only_board) + len(only_readiness),
        'exact_match': board == readiness,
        'count_match': len(board) == len(readiness),

        'clean_axis_difference': bool(clean_axis),
        'clean_axis_difference_count': len(clean_axis),
        'differing_arms': differing,

        'board': board_block,
        'readiness': readiness_block,
        'shadow_state_match': board_block['shadow_state'] == readiness_block['shadow_state'],

        'readiness_authority_complete': bool(authority_complete),
        'runtime_population_consistent': runtime_consistent,
        'integrity': {'ok': not flags, 'flags': flags},
    }

    # Reference only: the membership the currently published board froze, when
    # it is eligible for same-moment comparison. Never used as Population A.
    if published_board_ids is not None:
        published = frozenset(published_board_ids)
        row['published_board_pitcher_ids'] = sorted(published)
        row['published_board_matches_candidate'] = published == board
    else:
        row['published_board_pitcher_ids'] = None
        row['published_board_matches_candidate'] = None

    return row


def _rule_evaluation(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Mechanical evaluation of the pre-registered rules.

    This reports metrics. It does not authorise an implementation — the founder
    makes the gate decision from these numbers.
    """
    exact = sum(1 for row in rows if row['exact_match'])
    clean_axis_teams = [row for row in rows if row['clean_axis_difference']]
    shadow_mismatch_teams = [row for row in rows if not row['shadow_state_match']]
    non_matching = [row for row in rows if not row['exact_match']]

    non_matching_moderate_only = all(
        all(arm['difference_class'] in MODERATE_CLASSES for arm in row['differing_arms'])
        for row in non_matching
    )
    within_one_arm = all(
        row['symmetric_difference_count'] <= PASS_B_MAX_ARM_DIFFERENCE for row in rows
    )

    pass_a = (
        exact >= PASS_A_MIN_EXACT_MATCHES
        and non_matching_moderate_only
        and not clean_axis_teams
    )
    pass_b = within_one_arm and not clean_axis_teams and not shadow_mismatch_teams
    fail = (
        len(clean_axis_teams) >= FAIL_MIN_CLEAN_AXIS_TEAMS
        or bool(shadow_mismatch_teams)
    )

    return {
        'pre_registered': True,
        'declares_authorization': False,
        'note': (
            'Metrics only. The implementation gate decision belongs to the '
            'founder/reviewer, not to this script.'
        ),
        'pass_a_min_exact_matches': PASS_A_MIN_EXACT_MATCHES,
        'pass_b_max_arm_difference': PASS_B_MAX_ARM_DIFFERENCE,
        'fail_min_clean_axis_teams': FAIL_MIN_CLEAN_AXIS_TEAMS,
        'exact_match_count': exact,
        'non_matching_teams_differ_only_by_moderate_arms': non_matching_moderate_only,
        'every_team_within_one_arm': within_one_arm,
        'pass_a_met': pass_a,
        'pass_b_met': pass_b,
        'fail_triggered': fail,
        'no_rule_met': not pass_a and not pass_b and not fail,
    }


def build_comparison(
    rows: Sequence[Mapping[str, Any]],
    *,
    generated_at,
    comparison_started_at,
    reference_date,
    repository_sha,
    board_population_source,
    readiness_population_source,
    published_board_reference,
) -> dict:
    """Envelope for the full 30-club comparison.

    Raises when the canonical denominator is not covered: a partial comparison
    must never be uploaded as a successful one.
    """
    rows = list(rows)
    if len(rows) != EXPECTED_TEAM_COUNT:
        raise ValueError(
            f'comparison must cover all {EXPECTED_TEAM_COUNT} canonical clubs; '
            f'got {len(rows)}'
        )

    ordered = sorted(rows, key=lambda row: row['team_id'])
    differences = [row for row in ordered if not row['exact_match']]
    symmetric = [row['symmetric_difference_count'] for row in ordered]

    return {
        'export_version': COMPARISON_VERSION,
        'generated_at': generated_at,
        'comparison_started_at': comparison_started_at,
        'reference_date': reference_date,
        'repository_sha': repository_sha,
        'read_only': True,

        'board_population_source': board_population_source,
        'readiness_population_source': readiness_population_source,
        'published_board_reference': dict(published_board_reference or {}),
        'shadow_contract': dict(CONTRACT_A),

        'team_count': len(ordered),
        'summary': {
            'exact_match_count': sum(1 for row in ordered if row['exact_match']),
            'count_match_count': sum(1 for row in ordered if row['count_match']),
            'teams_with_differences': len(differences),
            'teams_with_clean_axis_differences': sum(
                1 for row in ordered if row['clean_axis_difference']
            ),
            'teams_with_shadow_state_differences': sum(
                1 for row in ordered if not row['shadow_state_match']
            ),
            'teams_with_incomplete_readiness_authority': sum(
                1 for row in ordered if not row['readiness_authority_complete']
            ),
            'teams_with_runtime_population_mismatch': sum(
                1 for row in ordered if not row['runtime_population_consistent']
            ),
            'total_symmetric_difference_members': sum(symmetric),
            'max_symmetric_difference': max(symmetric) if symmetric else 0,
        },
        'rule_evaluation': _rule_evaluation(ordered),
        'rows': ordered,
    }
