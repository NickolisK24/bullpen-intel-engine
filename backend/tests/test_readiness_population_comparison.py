"""Same-moment Team State population comparison.

The comparator answers one question: at a single moment, does the Team Board
population match the readiness population the Team State classifier actually
consumes? These tests pin the properties that make that answer trustworthy —
the difference sets are exact, a differing arm's governed status decides its
class, an unknown status never becomes a clean one, and the shadow Contract A
calculation stays status-only.

Nothing here changes Team State semantics. No threshold, status meaning, public
mapping, classifier, or population rule is altered. The shadow calculation is
offline arithmetic over already-governed statuses and is written nowhere.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from services.mlb_club_directory import EXPECTED_CLUB_COUNT, MLB_CLUBS
from services.readiness_population_comparison import (
    CONTRACT_A,
    DIFFERENCE_CLEAN,
    DIFFERENCE_MODERATE_LIMITED,
    DIFFERENCE_MODERATE_MONITOR,
    DIFFERENCE_SEVERE_AVOID,
    DIFFERENCE_SEVERE_UNAVAILABLE,
    DIFFERENCE_UNKNOWN,
    build_comparison,
    classify_difference,
    compare_team,
    shadow_partition,
    shadow_state,
)


CLUB = MLB_CLUBS[26]  # NYY, 147


def statuses(**kwargs):
    """Map pitcher_id -> governed availability status, as the records supply it."""
    return {int(key.lstrip('p')): value for key, value in kwargs.items()}


def team_row(board_ids, readiness_ids, status_map, *, authority_complete=True,
             arm_details=None, consumed_ids=None):
    return compare_team(
        club=CLUB,
        reference_date=date(2026, 8, 17),
        board_ids=frozenset(board_ids),
        readiness_ids=frozenset(readiness_ids),
        statuses=status_map,
        arm_details=arm_details or {},
        authority_complete=authority_complete,
        consumed_ids=(
            frozenset(consumed_ids)
            if consumed_ids is not None
            else frozenset(board_ids) & frozenset(readiness_ids)
        ),
    )


def clean_team(count, *, severe=0, moderate=0):
    """A status map with an explicit clean/moderate/severe composition."""
    result, next_id = {}, 1
    for _ in range(count):
        result[next_id] = 'Available'
        next_id += 1
    for _ in range(moderate):
        result[next_id] = 'Monitor'
        next_id += 1
    for _ in range(severe):
        result[next_id] = 'Unavailable'
        next_id += 1
    return result


# ── the canonical 30-club denominator is required ────────────────────────────

def test_all_thirty_clubs_are_required():
    assert EXPECTED_CLUB_COUNT == 30
    rows = [team_row([1], [1], statuses(p1='Available')) for _ in range(30)]
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    assert comparison['team_count'] == 30


def test_fewer_than_thirty_teams_is_a_loud_failure():
    rows = [team_row([1], [1], statuses(p1='Available')) for _ in range(29)]
    with pytest.raises(ValueError, match='30'):
        build_comparison(
            rows, generated_at='g', comparison_started_at='s',
            reference_date='2026-08-17', repository_sha='sha',
            board_population_source='candidate', readiness_population_source='authority',
            published_board_reference={},
        )


def test_zero_teams_is_a_loud_failure():
    with pytest.raises(ValueError):
        build_comparison(
            [], generated_at='g', comparison_started_at='s',
            reference_date='2026-08-17', repository_sha='sha',
            board_population_source='candidate', readiness_population_source='authority',
            published_board_reference={},
        )


# ── set comparison is exact ──────────────────────────────────────────────────

def test_exact_set_match_is_detected():
    row = team_row([1, 2, 3], [3, 2, 1], clean_team(3))

    assert row['exact_match'] is True
    assert row['count_match'] is True
    assert row['symmetric_difference_count'] == 0
    assert row['only_in_board'] == []
    assert row['only_in_readiness'] == []
    assert row['intersection_pitcher_ids'] == [1, 2, 3]


def test_equal_counts_with_different_members_is_not_a_match():
    """A count-only comparison would call this identical. It is not."""
    row = team_row([1, 2, 3], [1, 2, 9], clean_team(3))

    assert row['count_match'] is True
    assert row['exact_match'] is False
    assert row['only_in_board'] == [3]
    assert row['only_in_readiness'] == [9]
    assert row['symmetric_difference_count'] == 2


def test_only_in_board_and_only_in_readiness_are_directional():
    row = team_row([1, 2, 5], [1, 2, 7, 8], clean_team(2))

    assert row['only_in_board'] == [5]
    assert row['only_in_readiness'] == [7, 8]
    assert row['board_population_count'] == 3
    assert row['readiness_population_count'] == 4
    directions = {
        arm['pitcher_id']: arm['difference_direction'] for arm in row['differing_arms']
    }
    assert directions == {
        5: 'only_in_board', 7: 'only_in_readiness', 8: 'only_in_readiness',
    }


def test_difference_ids_are_sorted_for_stable_diffing():
    row = team_row([9, 3, 5], [], {})
    assert row['only_in_board'] == [3, 5, 9]


# ── difference classification ────────────────────────────────────────────────

@pytest.mark.parametrize('status,expected', [
    ('Available', DIFFERENCE_CLEAN),
    ('available', DIFFERENCE_CLEAN),
    ('  AVAILABLE ', DIFFERENCE_CLEAN),
    ('Monitor', DIFFERENCE_MODERATE_MONITOR),
    ('Limited', DIFFERENCE_MODERATE_LIMITED),
    ('Avoid', DIFFERENCE_SEVERE_AVOID),
    ('Unavailable', DIFFERENCE_SEVERE_UNAVAILABLE),
])
def test_governed_status_decides_the_difference_class(status, expected):
    assert classify_difference(status) == expected


@pytest.mark.parametrize('status', [None, '', '   ', 'Probable', 'unknown', 'fresh'])
def test_absent_or_ungoverned_status_is_unknown_never_clean(status):
    assert classify_difference(status) == DIFFERENCE_UNKNOWN


def test_clean_axis_difference_is_flagged():
    row = team_row([1, 2], [1], statuses(p1='Available', p2='Available'))

    assert row['clean_axis_difference'] is True
    assert row['clean_axis_difference_count'] == 1
    assert row['differing_arms'][0]['difference_class'] == DIFFERENCE_CLEAN


def test_moderate_only_difference_is_not_a_clean_axis_difference():
    row = team_row([1, 2, 3], [1], statuses(p1='Available', p2='Monitor', p3='Limited'))

    assert row['clean_axis_difference'] is False
    assert row['clean_axis_difference_count'] == 0
    classes = sorted(arm['difference_class'] for arm in row['differing_arms'])
    assert classes == [DIFFERENCE_MODERATE_LIMITED, DIFFERENCE_MODERATE_MONITOR]


def test_severe_only_difference_is_not_a_clean_axis_difference():
    row = team_row([1, 2, 3], [1], statuses(p1='Available', p2='Avoid', p3='Unavailable'))

    assert row['clean_axis_difference'] is False
    classes = sorted(arm['difference_class'] for arm in row['differing_arms'])
    assert classes == [DIFFERENCE_SEVERE_AVOID, DIFFERENCE_SEVERE_UNAVAILABLE]


def test_readiness_only_arm_without_a_governed_status_is_unknown():
    """An arm the roster authority claims but the board population never scored
    has no governed status. It must not be counted clean by default."""
    row = team_row([1], [1, 42], statuses(p1='Available'))

    arm = next(item for item in row['differing_arms'] if item['pitcher_id'] == 42)
    assert arm['availability_status'] is None
    assert arm['difference_class'] == DIFFERENCE_UNKNOWN
    assert row['clean_axis_difference'] is False


# ── differing-arm detail ─────────────────────────────────────────────────────

def test_differing_arm_carries_the_requested_facts():
    row = team_row(
        [1, 5], [1], statuses(p1='Available', p5='Monitor'),
        arm_details={5: {
            'availability_data_state': 'fresh', 'raw_score': 41.5,
            'active': True, 'team_id': 147, 'roster_status': 'active',
        }},
    )

    arm = next(item for item in row['differing_arms'] if item['pitcher_id'] == 5)
    assert arm['availability_status'] == 'Monitor'
    assert arm['availability_data_state'] == 'fresh'
    assert arm['raw_score'] == 41.5
    assert arm['active'] is True
    assert arm['team_id'] == 147
    assert arm['roster_status'] == 'active'
    assert arm['membership_reason'] == 'in_board_population_not_in_roster_authority'


def test_missing_arm_detail_stays_null_and_is_never_invented():
    row = team_row([1, 5], [1], statuses(p1='Available', p5='Monitor'))

    arm = next(item for item in row['differing_arms'] if item['pitcher_id'] == 5)
    for field in ('availability_data_state', 'raw_score', 'active', 'team_id', 'roster_status'):
        assert arm[field] is None, f'{field} must stay null when unavailable'


def test_matching_teams_emit_no_arm_detail():
    """Arm facts are queried only for differences, so a matching team is silent."""
    row = team_row([1, 2], [1, 2], clean_team(2))
    assert row['differing_arms'] == []


# ── shadow Contract A: partition ─────────────────────────────────────────────

def test_shadow_partition_counts_status_only():
    partition = shadow_partition(['Available'] * 6 + ['Monitor', 'Limited', 'Avoid'])

    assert partition['population_count'] == 9
    assert partition['clean_count'] == 6
    assert partition['moderate_count'] == 2
    assert partition['severe_count'] == 1
    assert partition['unknown_count'] == 0
    assert partition['clean_share'] == pytest.approx(6 / 9)
    assert partition['severe_share'] == pytest.approx(1 / 9)


def test_shadow_partition_guards_an_empty_denominator():
    partition = shadow_partition([])

    assert partition['population_count'] == 0
    assert partition['clean_count'] == 0
    assert partition['clean_share'] is None  # guarded, not 0.0
    assert partition['severe_share'] is None


def test_unknown_status_is_counted_as_unknown_not_clean():
    partition = shadow_partition(['Available', None, 'Probable'])

    assert partition['clean_count'] == 1
    assert partition['unknown_count'] == 2
    assert partition['clean_share'] == pytest.approx(1 / 3)


# ── shadow Contract A: state ─────────────────────────────────────────────────

def test_contract_a_constants_are_the_founder_approved_values():
    assert CONTRACT_A['clean_share_fresh_min'] == (3, 5)
    assert CONTRACT_A['clean_count_fresh_min'] == 5
    assert CONTRACT_A['severe_count_fresh_max'] == 1
    assert CONTRACT_A['clean_count_vulnerable_max'] == 2
    assert CONTRACT_A['severe_share_vulnerable_min'] == (1, 3)
    assert CONTRACT_A['basis'] == 'status_only'


@pytest.mark.parametrize('clean,moderate,severe,expected', [
    (6, 2, 0, 'Fresh'),          # 6/8 = 0.75 clean, 0 severe
    (5, 2, 1, 'Fresh'),          # 5/8 = 0.625, exactly 1 severe -> still Fresh
    (3, 5, 0, 'Stretched'),      # 3/8 = 0.375 < 0.60, clean_count 3 > 2
    (5, 4, 0, 'Stretched'),      # 5/9 = 0.556 < 0.60
    (4, 4, 0, 'Stretched'),      # clean_count 4 < 5
    (2, 6, 0, 'Vulnerable'),     # clean_count <= 2
    (0, 3, 0, 'Vulnerable'),
    (6, 0, 3, 'Vulnerable'),     # 3/9 = 1/3 severe share
])
def test_contract_a_shadow_state(clean, moderate, severe, expected):
    partition = shadow_partition(
        ['Available'] * clean + ['Monitor'] * moderate + ['Unavailable'] * severe
    )
    assert shadow_state(partition) == expected


def test_clean_share_boundary_is_exact_not_floating_point():
    """3/5 must satisfy >= 0.60 exactly; a float comparison can lose this."""
    partition = shadow_partition(['Available'] * 6 + ['Monitor'] * 4)
    assert partition['clean_share'] == pytest.approx(0.6)
    assert shadow_state(partition) == 'Fresh'


def test_severe_share_boundary_is_exact_not_floating_point():
    """Exactly one third severe must trip Vulnerable, at a size where the float
    ratio is not exactly representable."""
    partition = shadow_partition(['Available'] * 8 + ['Monitor'] * 2 + ['Unavailable'] * 5)
    assert partition['population_count'] == 15
    assert partition['severe_count'] == 5
    assert shadow_state(partition) == 'Vulnerable'


def test_two_severe_below_the_share_threshold_is_not_vulnerable_by_count():
    """Contract A has no absolute severe-count Vulnerable trigger; only the
    share and the clean-count floor. Pinned so the shadow cannot drift."""
    partition = shadow_partition(['Available'] * 7 + ['Monitor'] * 3 + ['Unavailable'] * 2)
    assert partition['severe_count'] == 2
    assert shadow_state(partition) == 'Stretched'


def test_raw_score_never_escalates_a_status():
    """STATUS ONLY. A high raw score on an Available arm stays clean."""
    row = team_row(
        [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6], clean_team(6),
        arm_details={1: {'raw_score': 95.0}},
    )
    assert row['board']['clean_count'] == 6
    assert row['board']['shadow_state'] == 'Fresh'


def test_empty_population_has_no_shadow_state():
    """Zero arms is a data condition, not a Team State. Declared up front so it
    is never mistaken for a classification."""
    partition = shadow_partition([])
    assert shadow_state(partition) is None


# ── shadow state comparison across the two populations ───────────────────────

def test_shadow_state_match_when_populations_agree():
    row = team_row([1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6], clean_team(6))

    assert row['board']['shadow_state'] == 'Fresh'
    assert row['readiness']['shadow_state'] == 'Fresh'
    assert row['shadow_state_match'] is True


def test_shadow_state_mismatch_is_detected():
    """Dropping one clean arm from an 8-arm board takes 5/8 clean to 4/7."""
    status_map = clean_team(5, moderate=3)
    row = team_row(list(status_map), [key for key in status_map if key != 1], status_map)

    assert row['board']['shadow_state'] == 'Fresh'
    assert row['readiness']['shadow_state'] == 'Stretched'
    assert row['shadow_state_match'] is False
    assert row['clean_axis_difference'] is True


def test_readiness_shadow_counts_unscored_arms_as_unknown():
    status_map = clean_team(6)
    row = team_row(list(status_map), list(status_map) + [99], status_map)

    assert row['readiness']['population_count'] == 7
    assert row['readiness']['clean_count'] == 6
    assert row['readiness']['unknown_count'] == 1


# ── integrity ────────────────────────────────────────────────────────────────

def test_incomplete_roster_authority_is_flagged_not_silently_empty():
    row = team_row([1, 2, 3], [], clean_team(3), authority_complete=False)

    assert row['readiness_authority_complete'] is False
    assert 'readiness_authority_incomplete' in row['integrity']['flags']
    assert row['integrity']['ok'] is False


def test_runtime_population_inconsistency_is_flagged():
    """The records the readiness pipeline consumes must be exactly the board
    records inside the resolved membership. Anything else is reported."""
    consistent = team_row([1, 2, 3], [2, 3, 4], clean_team(3), consumed_ids=[2, 3])
    assert consistent['runtime_population_consistent'] is True

    drifted = team_row([1, 2, 3], [2, 3, 4], clean_team(3), consumed_ids=[2])
    assert drifted['runtime_population_consistent'] is False
    assert 'runtime_population_mismatch' in drifted['integrity']['flags']


def test_empty_board_population_is_flagged():
    row = team_row([], [1], {})
    assert 'board_population_empty' in row['integrity']['flags']


def test_wholesale_readiness_withholding_is_visible_in_the_summary():
    """Observed live: when ``public_roster_readiness`` withholds counts, the
    roster authority publishes no ``bullpen_arms`` and
    ``resolve_active_bullpen_membership`` fails closed to an empty set. That must
    surface as 30 incomplete authorities, never as 30 quiet zero-arm teams."""
    rows = [
        team_row([1, 2, 3], [], clean_team(3), authority_complete=False)
        for _ in range(30)
    ]
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )

    assert comparison['summary']['teams_with_incomplete_readiness_authority'] == 30
    assert comparison['summary']['exact_match_count'] == 0
    assert all(not row['integrity']['ok'] for row in comparison['rows'])


def test_script_refuses_a_comparison_with_no_readiness_population_anywhere():
    """The script's own guard, pinned: an all-empty Population B is a resolution
    failure, not a comparison result."""
    text = script_source()

    assert 'Population B cannot be resolved' in text
    assert 'cannot be resolved fairly' in text  # the Population A guard


# ── envelope and summary ─────────────────────────────────────────────────────

def full_rows(*overrides):
    """Thirty rows, all matching, with the leading rows replaced."""
    rows = list(overrides)
    while len(rows) < 30:
        rows.append(team_row([1], [1], statuses(p1='Available')))
    return rows


def test_summary_counts_are_mechanical():
    mismatch = clean_team(5, moderate=3)
    rows = full_rows(
        team_row([1, 2], [1], statuses(p1='Available', p2='Monitor')),
        team_row(list(mismatch), [key for key in mismatch if key != 1], mismatch),
    )
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    summary = comparison['summary']

    assert summary['exact_match_count'] == 28
    assert summary['teams_with_differences'] == 2
    assert summary['teams_with_clean_axis_differences'] == 1
    assert summary['teams_with_shadow_state_differences'] == 1
    assert summary['total_symmetric_difference_members'] == 2
    assert summary['max_symmetric_difference'] == 1


def test_rule_evaluation_is_mechanical_and_pre_registered():
    rows = full_rows(team_row([1, 2], [1], statuses(p1='Available', p2='Monitor')))
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    rules = comparison['rule_evaluation']

    # 29/30 exact, the one difference is a Monitor arm, no clean-axis mismatch.
    assert rules['pass_a_met'] is True
    assert rules['pass_b_met'] is True
    assert rules['fail_triggered'] is False
    assert rules['declares_authorization'] is False


def test_one_clean_axis_difference_fails_both_pass_rules_without_triggering_fail():
    """A single clean-axis difference is not "repeated/systematic". It clears no
    PASS rule and trips no FAIL rule — the founder-review middle zone."""
    rows = full_rows(team_row([1, 2], [1], statuses(p1='Available', p2='Available')))
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    rules = comparison['rule_evaluation']

    assert rules['pass_a_met'] is False
    assert rules['pass_b_met'] is False
    assert rules['fail_triggered'] is False
    assert rules['no_rule_met'] is True


def test_repeated_clean_axis_difference_triggers_fail():
    """Two or more teams is the pre-registered mechanical reading of "repeated"."""
    rows = full_rows(
        team_row([1, 2], [1], statuses(p1='Available', p2='Available')),
        team_row([1, 2], [1], statuses(p1='Available', p2='Available')),
    )
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    rules = comparison['rule_evaluation']

    assert rules['pass_a_met'] is False
    assert rules['pass_b_met'] is False
    assert rules['fail_triggered'] is True


def test_shadow_state_disagreement_fails_pass_b():
    mismatch = clean_team(5, moderate=3)
    rows = full_rows(
        team_row(list(mismatch), [key for key in mismatch if key != 1], mismatch),
    )
    comparison = build_comparison(
        rows, generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )

    assert comparison['rule_evaluation']['pass_b_met'] is False
    assert comparison['rule_evaluation']['fail_triggered'] is True


def test_envelope_records_the_same_moment_provenance():
    comparison = build_comparison(
        full_rows(), generated_at='2026-08-17T12:00:01+00:00',
        comparison_started_at='2026-08-17T12:00:00+00:00',
        reference_date='2026-08-17', repository_sha='abc123',
        board_population_source='current_candidate_board_population',
        readiness_population_source='resolve_active_bullpen_membership',
        published_board_reference={'snapshot_id': 427, 'eligible_for_comparison': False},
    )

    assert comparison['export_version'] == 'team_state_population_comparison_v1'
    assert comparison['read_only'] is True
    assert comparison['reference_date'] == '2026-08-17'
    assert comparison['comparison_started_at'] == '2026-08-17T12:00:00+00:00'
    assert comparison['repository_sha'] == 'abc123'
    assert comparison['board_population_source'] == 'current_candidate_board_population'
    assert comparison['published_board_reference']['snapshot_id'] == 427


def test_output_is_deterministic_apart_from_timestamps():
    first = build_comparison(
        full_rows(), generated_at='A', comparison_started_at='A',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    second = build_comparison(
        full_rows(), generated_at='B', comparison_started_at='B',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    for payload in (first, second):
        payload.pop('generated_at')
        payload.pop('comparison_started_at')

    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        second, sort_keys=True, default=str
    )


def test_output_carries_no_credentials():
    comparison = build_comparison(
        full_rows(), generated_at='g', comparison_started_at='s',
        reference_date='2026-08-17', repository_sha='sha',
        board_population_source='candidate', readiness_population_source='authority',
        published_board_reference={},
    )
    text = json.dumps(comparison, default=str).lower()

    for secret in ('password', 'database_url', 'postgres://', 'admin_token', 'secret_key'):
        assert secret not in text


def test_comparison_does_not_mutate_its_inputs():
    status_map = clean_team(3)
    before = json.dumps(status_map, sort_keys=True)
    compare_team(
        club=CLUB, reference_date=date(2026, 8, 17),
        board_ids=frozenset(status_map), readiness_ids=frozenset({1}),
        statuses=status_map, arm_details={}, authority_complete=True,
        consumed_ids=frozenset({1}),
    )
    assert json.dumps(status_map, sort_keys=True) == before


# ── the comparator performs no writes ────────────────────────────────────────

def test_comparator_module_contains_no_mutation_calls():
    source = (
        Path(__file__).resolve().parents[1]
        / 'services' / 'readiness_population_comparison.py'
    )
    text = source.read_text()

    for forbidden in (
        'session.add(', 'session.delete(', 'session.commit(', 'session.merge(',
        'session.flush(', '.insert(', 'publish_', 'db.session',
    ):
        assert forbidden not in text, f'comparator must not contain {forbidden}'


def script_source():
    return (
        Path(__file__).resolve().parents[1]
        / 'scripts' / 'compare_team_state_populations.py'
    ).read_text()


def script_code():
    """Script text with comment-only lines removed, so prose never satisfies —
    or trips — a scan."""
    return '\n'.join(
        '' if line.lstrip().startswith('#') else line
        for line in script_source().splitlines()
    )


def test_comparator_script_issues_no_mutations():
    text = script_code()

    # Call syntax, so the read-only inspection attributes the script uses to
    # assert cleanliness (session.new / dirty / deleted) are not mistaken for
    # mutations. ``.update(`` and ``.delete(`` are forbidden outright — the
    # script merges dictionaries by unpacking — so no bulk ORM write can hide
    # behind a call that reads like a dictionary operation.
    for forbidden in (
        'session.add(', 'session.delete(', 'session.commit(', 'session.merge(',
        'session.flush(', 'session.execute(', 'bulk_',
        '.update(', '.delete(',
        'publish_dashboard_snapshot', 'run_intraday_repair',
    ):
        assert forbidden not in text, f'script must not contain {forbidden}'
    assert 'db.session.rollback()' in text


def test_the_only_insert_in_the_script_is_the_import_path():
    """``.insert(`` is otherwise a write; pin the single legitimate use."""
    inserts = [line.strip() for line in script_code().splitlines() if '.insert(' in line]
    assert inserts == ['sys.path.insert(0, str(BACKEND_DIR))']


def test_comparator_script_asserts_session_cleanliness():
    text = script_source()

    for required in ('db.session.new', 'db.session.dirty', 'db.session.deleted'):
        assert required in text, f'script must assert {required} is empty'
