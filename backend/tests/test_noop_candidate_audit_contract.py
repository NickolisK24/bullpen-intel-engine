"""The candidate-audit contract, executed rather than described.

Eligibility must come from positive canonical evidence. These tests pin the
bounds, the deterministic ordering, the classification precedence, the verdict
semantics, and — separately — the corrected finality evidence for the manual
no-op write qualification, including a regression fixture reproducing
production run 30862655470.
"""

import pytest

from models.game_ingestion_work_item import GameIngestionWorkItem
from services import game_log_reconciliation as reconciliation
from services import noop_qualification_candidate_audit as audit
from services import noop_write_qualification as qualification


GAME_PK = 951777


def row(**overrides):
    base = {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': 4001,
        'action': reconciliation.ACTION_UNCHANGED,
        'changed_fields': [],
        'pitcher_identity_action': 'unchanged',
        'target_fields': ['innings_pitched_outs'],
    }
    base.update(overrides)
    return base


def shadow_report(*, rows=None, **overrides):
    rows = [row()] if rows is None else rows
    base = {
        'status': 'complete',
        'mode': 'shadow',
        'requested_game_pks': [GAME_PK],
        'planned_game_pks': [GAME_PK],
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'duplicate_requested_count': 0,
        'execution_scope_exact_match': True,
        'games_fetched': 1,
        'games_attempted': 1,
        'games_completed': 1,
        'budget_stop_triggered': False,
        'reconciliation_plan_fingerprint': 'f' * 32,
        'games': [{
            'game_pk': GAME_PK, 'source_revision': 'rev-1', 'rows': rows,
        }],
    }
    for field in qualification.PROJECTED_MUTATION_COUNTERS:
        base.setdefault(field, 0)
    base['rows_unchanged'] = len(rows)
    base.update(overrides)
    return base


def work_item(**overrides):
    base = {
        'game_pk': GAME_PK,
        'status': GameIngestionWorkItem.STATUS_COMPLETED,
        'represented_date': '2026-07-29',
        'completed_at_present': True,
        'attempt_count': 1,
        'source_revision_present': True,
    }
    base.update(overrides)
    return base


def classify(**overrides):
    kwargs = {
        'game_pk': GAME_PK,
        'shadow_report': shadow_report(),
        'planner_executed': True,
        'work_item_before': work_item(),
        'work_item_after': work_item(),
    }
    kwargs.update(overrides)
    return audit.classify_candidate(**kwargs)


# ── Bounds ──────────────────────────────────────────────────────────────────


def test_the_declared_defaults_and_bounds():
    assert (audit.LOOKBACK_DAYS_DEFAULT, audit.LOOKBACK_DAYS_MIN,
            audit.LOOKBACK_DAYS_MAX) == (30, 1, 120)
    assert (audit.CANDIDATE_LIMIT_DEFAULT, audit.CANDIDATE_LIMIT_MIN,
            audit.CANDIDATE_LIMIT_MAX) == (20, 1, 50)
    assert (audit.ELIGIBLE_TARGET_DEFAULT, audit.ELIGIBLE_TARGET_MIN,
            audit.ELIGIBLE_TARGET_MAX) == (5, 1, 10)


def test_omitted_bounds_take_their_defaults():
    assert audit.resolve_bounds() == {
        'lookback_days': 30, 'candidate_limit': 20, 'eligible_target_count': 5,
    }


@pytest.mark.parametrize('field,value', [
    ('lookback_days', '0'), ('lookback_days', '121'),
    ('candidate_limit', '0'), ('candidate_limit', '51'),
    ('eligible_target_count', '0'), ('eligible_target_count', '11'),
])
def test_out_of_bounds_inputs_are_refused(field, value):
    with pytest.raises(audit.AuditInputError) as excinfo:
        audit.resolve_bounds(**{field: value})
    assert excinfo.value.reason == f'{field}_out_of_bounds'


@pytest.mark.parametrize('value', ['abc', '1.5', '-3', '1e3', '  x  '])
def test_non_integer_bounds_are_refused(value):
    with pytest.raises(audit.AuditInputError):
        audit.resolve_bounds(lookback_days=value)


def test_the_eligible_target_cannot_exceed_the_candidate_limit():
    with pytest.raises(audit.AuditInputError) as excinfo:
        audit.resolve_bounds(candidate_limit='3', eligible_target_count='5')
    assert excinfo.value.reason == (
        'eligible_target_count_exceeds_candidate_limit'
    )


def test_the_target_may_equal_the_candidate_limit():
    assert audit.resolve_bounds(
        candidate_limit='5', eligible_target_count='5',
    )['eligible_target_count'] == 5


# ── Eligibility requires positive evidence ─────────────────────────────────


def test_a_fully_unchanged_candidate_is_eligible():
    result = classify()
    assert result['eligible'] is True
    assert result['primary_classification'] == audit.ELIGIBLE
    assert result['reason_codes'] == []
    assert result['finality_positively_proven'] is True


@pytest.mark.parametrize('action,expected', [
    (reconciliation.ACTION_INSERT, audit.PLAN_PROPOSES_INSERT),
    (reconciliation.ACTION_UPDATE, audit.PLAN_PROPOSES_UPDATE),
    (reconciliation.ACTION_BLOCKED, audit.PLAN_CONTAINS_BLOCKED_ROW),
])
def test_a_mutating_plan_is_ineligible(action, expected):
    result = classify(shadow_report=shadow_report(rows=[row(action=action)]))
    assert result['eligible'] is False
    assert expected in result['reason_codes']


@pytest.mark.parametrize('identity_action', [
    'create_minimal_identity', 'reactivate', 'metadata_update', 'blocked',
])
def test_an_identity_mutation_is_ineligible(identity_action):
    result = classify(shadow_report=shadow_report(
        rows=[row(pitcher_identity_action=identity_action)]))
    assert result['eligible'] is False
    assert audit.PLAN_PROPOSES_IDENTITY_MUTATION in result['reason_codes']


@pytest.mark.parametrize('counter', [
    'canonical_outs_corrections', 'statistical_corrections',
    'authority_reconciliations', 'appearance_team_mutations',
    'complete_mutation_count', 'provenance_only_updates', 'rows_blocked',
])
def test_a_baseball_mutation_counter_is_ineligible(counter):
    result = classify(shadow_report=shadow_report(**{counter: 1}))
    assert result['eligible'] is False
    assert audit.PLAN_PROPOSES_BASEBALL_MUTATION in result['reason_codes']


@pytest.mark.parametrize('counter', [
    'pitcher_identity_creations', 'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates', 'pitcher_identity_blocked',
    'pitcher_identity_mutations',
])
def test_an_identity_counter_is_ineligible(counter):
    result = classify(shadow_report=shadow_report(**{counter: 1}))
    assert audit.PLAN_PROPOSES_IDENTITY_MUTATION in result['reason_codes']


def test_a_missing_work_item_is_ineligible():
    result = classify(work_item_before=None)
    assert result['primary_classification'] == audit.TARGET_WORK_ITEM_MISSING


def test_a_non_completed_work_item_is_ineligible():
    result = classify(work_item_before=work_item(status='in_progress'))
    assert result['primary_classification'] == (
        audit.TARGET_WORK_ITEM_NOT_COMPLETED
    )


def test_a_work_item_that_disappears_during_shadow_is_ineligible():
    result = classify(work_item_after=None)
    assert audit.TARGET_WORK_ITEM_MISSING in result['reason_codes']


def test_a_missing_represented_date_is_ineligible():
    result = classify(work_item_before=work_item(represented_date=None))
    assert audit.REPRESENTED_DATE_UNAVAILABLE in result['reason_codes']


def test_an_unplannable_game_is_ineligible():
    result = classify(shadow_report=shadow_report(
        planned_game_pks=[], missing_requested_game_pks=[GAME_PK],
        execution_scope_exact_match=False, rows=[]))
    assert result['primary_classification'] == audit.GAME_NOT_PLANNABLE
    assert result['finality_positively_proven'] is False


def test_an_unexpected_planned_game_is_ineligible():
    result = classify(shadow_report=shadow_report(
        planned_game_pks=[GAME_PK, 999], unexpected_planned_game_pks=[999],
        execution_scope_exact_match=False))
    assert audit.UNEXPECTED_PLANNED_GAME in result['reason_codes']


def test_an_empty_plan_is_ineligible():
    result = classify(shadow_report=shadow_report(rows=[]))
    assert audit.PLANNED_ROW_COUNT_ZERO in result['reason_codes']
    assert result['eligible'] is False


def test_a_planner_that_never_executed_is_ineligible():
    result = classify(planner_executed=False, shadow_report=None)
    assert result['primary_classification'] == audit.PLANNER_NOT_EXECUTED
    assert result['finality_positively_proven'] is False


def test_a_missing_source_revision_is_ineligible():
    result = classify(shadow_report=shadow_report(games=[
        {'game_pk': GAME_PK, 'source_revision': None, 'rows': [row()]}]))
    assert audit.SOURCE_REVISION_MISSING in result['reason_codes']


def test_multiple_source_revisions_are_ineligible():
    result = classify(shadow_report=shadow_report(games=[
        {'game_pk': GAME_PK, 'source_revision': 'a', 'rows': [row()]},
        {'game_pk': GAME_PK, 'source_revision': 'b', 'rows': []}]))
    assert audit.SOURCE_REVISION_MULTIPLE in result['reason_codes']


def test_a_wrong_game_revision_is_ineligible():
    result = classify(shadow_report=shadow_report(games=[
        {'game_pk': 4242, 'source_revision': 'a', 'rows': [row()]}]))
    assert audit.SOURCE_REVISION_WRONG_GAME in result['reason_codes']


def test_a_missing_plan_fingerprint_is_ineligible():
    result = classify(shadow_report=shadow_report(
        reconciliation_plan_fingerprint=None))
    assert audit.PLAN_FINGERPRINT_MISSING in result['reason_codes']


def test_a_budget_stop_is_ineligible():
    result = classify(shadow_report=shadow_report(budget_stop_triggered=True))
    assert result['primary_classification'] == audit.SHADOW_BUDGET_STOP


def test_a_shadow_error_is_ineligible():
    result = classify(shadow_error=True)
    assert result['primary_classification'] == audit.SHADOW_EXECUTION_ERROR


def test_a_read_only_violation_outranks_everything():
    result = classify(tables_changed=('game_logs',), shadow_error=True)
    assert result['primary_classification'] == (
        audit.READ_ONLY_CONTRACT_VIOLATED
    )


# ── Classification determinism ─────────────────────────────────────────────


def test_every_declared_classification_appears_in_the_precedence():
    declared = {
        value for name, value in vars(audit).items()
        if name.isupper() and isinstance(value, str)
        and name not in (
            'SCHEMA_VERSION', 'AUDIT_TYPE', 'CONFIRMATION',
            'NON_AUTHORIZATION_STATEMENT', 'RESULT_ELIGIBLE_FOUND',
            'RESULT_NO_ELIGIBLE_CANDIDATE', 'RESULT_FAILED', 'RESULT_UNPROVEN',
            'STOP_REASON_TARGET_REACHED', 'STOP_REASON_CANDIDATE_LIMIT',
            'STOP_REASON_POOL_EXHAUSTED', 'PERMITTED_INGESTION_MODE',
        )
    }
    assert declared <= set(audit.CLASSIFICATION_PRECEDENCE)


def test_the_precedence_has_no_duplicates_and_ends_with_eligible():
    assert len(set(audit.CLASSIFICATION_PRECEDENCE)) == len(
        audit.CLASSIFICATION_PRECEDENCE
    )
    assert audit.CLASSIFICATION_PRECEDENCE[-1] == audit.ELIGIBLE
    assert audit.CLASSIFICATION_PRECEDENCE[0] == (
        audit.READ_ONLY_CONTRACT_VIOLATED
    )


def test_the_primary_classification_is_deterministic_across_many_reasons():
    result = classify(
        work_item_before=None,
        shadow_report=shadow_report(rows=[
            row(action=reconciliation.ACTION_UPDATE)],
            reconciliation_plan_fingerprint=None),
    )
    # durable-work-item invalidity outranks mutation and fingerprint failures
    assert result['primary_classification'] == audit.TARGET_WORK_ITEM_MISSING


def test_reason_codes_are_bounded_and_deduplicated():
    result = classify(
        work_item_before=None, work_item_after=None,
        shadow_report=shadow_report(
            rows=[row(action=reconciliation.ACTION_UPDATE)],
            planned_game_pks=[], execution_scope_exact_match=False,
            reconciliation_plan_fingerprint=None, games=[]),
    )
    assert len(result['reason_codes']) <= audit.MAX_REASON_CODES
    assert len(result['reason_codes']) == len(set(result['reason_codes']))


def test_exactly_one_primary_classification_is_always_selected():
    for kwargs in (
        {}, {'work_item_before': None}, {'shadow_error': True},
        {'planner_executed': False, 'shadow_report': None},
    ):
        result = classify(**kwargs)
        assert result['primary_classification'] in (
            audit.CLASSIFICATION_PRECEDENCE
        )


# ── Verdict ─────────────────────────────────────────────────────────────────


def proof(**overrides):
    base = {
        'read_only_enabled': True,
        'guard_acquired': True,
        'guard_release_attempted': True,
        'guard_released': True,
        'before_fingerprints': {'game_logs': 'x'},
        'after_fingerprints': {'game_logs': 'x'},
        'fingerprints_match': True,
    }
    base.update(overrides)
    return base


def test_an_eligible_candidate_completes_successfully():
    decision = audit.decide(candidates=[classify()], read_only_proof=proof())
    assert decision['result'] == audit.RESULT_ELIGIBLE_FOUND
    assert decision['exit_code'] == 0
    assert decision['suggested_candidate_game_pk'] == GAME_PK


def test_zero_eligible_candidates_is_a_completed_audit_not_a_failure():
    decision = audit.decide(
        candidates=[classify(work_item_before=None)], read_only_proof=proof(),
    )
    assert decision['result'] == audit.RESULT_NO_ELIGIBLE_CANDIDATE
    assert decision['exit_code'] == 0
    assert decision['suggested_candidate_game_pk'] is None


def test_an_empty_candidate_set_is_a_completed_audit():
    decision = audit.decide(candidates=[], read_only_proof=proof())
    assert decision['result'] == audit.RESULT_NO_ELIGIBLE_CANDIDATE
    assert decision['exit_code'] == 0


def test_a_fingerprint_mismatch_is_failed():
    decision = audit.decide(candidates=[], read_only_proof=proof(
        after_fingerprints={'game_logs': 'CHANGED'}, fingerprints_match=False))
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['exit_code'] == 1


@pytest.mark.parametrize('override,reason', [
    ({'read_only_enabled': False}, 'read_only_transaction_unavailable'),
    ({'guard_acquired': False}, 'writer_guard_unavailable'),
    ({'guard_released': False}, 'writer_guard_release_unproven'),
    ({'guard_release_attempted': False}, 'writer_guard_release_unproven'),
    ({'before_fingerprints': None}, 'table_fingerprints_unavailable'),
    ({'after_fingerprints': None}, 'table_fingerprints_unavailable'),
])
def test_missing_read_only_evidence_is_unproven(override, reason):
    decision = audit.decide(candidates=[], read_only_proof=proof(**override))
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2
    assert reason in decision['unproven_reasons']


def test_unavailable_discovery_is_unproven():
    decision = audit.decide(
        candidates=[], read_only_proof=proof(), discovery_available=False,
    )
    assert decision['result'] == audit.RESULT_UNPROVEN


def test_a_candidate_read_only_violation_fails_the_whole_audit():
    decision = audit.decide(
        candidates=[classify(tables_changed=('pitchers',))],
        read_only_proof=proof(),
    )
    assert decision['result'] == audit.RESULT_FAILED


def test_the_suggested_candidate_is_the_first_eligible_in_order():
    first = classify()
    second = classify(game_pk=GAME_PK)
    second = dict(second, game_pk=GAME_PK + 1)
    decision = audit.decide(
        candidates=[first, second], read_only_proof=proof(),
    )
    assert decision['ordered_eligible_game_pks'][0] == GAME_PK
    assert decision['suggested_candidate_game_pk'] == GAME_PK
    assert decision['suggestion_is_informational_only'] is True


def test_the_verdict_carries_the_non_authorization_statement():
    decision = audit.decide(candidates=[], read_only_proof=proof())
    assert 'does not authorize' in decision['non_authorization_statement']


def test_exit_codes_are_declared_for_every_result():
    assert audit.EXIT_CODES == {
        'COMPLETE_ELIGIBLE_FOUND': 0,
        'COMPLETE_NO_ELIGIBLE_CANDIDATE': 0,
        'FAILED': 1,
        'UNPROVEN': 2,
    }


# ── Fingerprint helpers ─────────────────────────────────────────────────────


def test_matching_fingerprints_are_reported_as_matching():
    assert audit.fingerprints_match({'a': '1'}, {'a': '1'}) is True


@pytest.mark.parametrize('before,after', [
    (None, {'a': '1'}), ({'a': '1'}, None), (None, None), ({}, {}),
])
def test_absent_fingerprints_never_count_as_matching(before, after):
    assert audit.fingerprints_match(before, after) is False


@pytest.mark.parametrize('table', audit.FINGERPRINT_TABLES)
def test_a_change_in_any_fingerprinted_table_is_detected(table):
    before = {name: 'same' for name in audit.FINGERPRINT_TABLES}
    after = dict(before, **{table: 'moved'})
    assert audit.fingerprints_match(before, after) is False
    assert audit.changed_tables(before, after) == [table]


def test_every_table_the_shadow_path_can_reach_is_fingerprinted():
    assert set(audit.FINGERPRINT_TABLES) == {
        'game_logs', 'pitchers', 'game_ingestion_work_items',
        'postgame_processed_games', 'scheduled_games', 'sync_failures',
    }


# ── Finality evidence correction (Deliverable 8) ───────────────────────────
# Regression fixture for production run 30862655470: the qualification refused
# at the missing-work-item precondition before the planner ran, and the
# artifact still reported finality as proven.


def test_run_30862655470_reports_no_finality_claim():
    state = qualification.execution_state(
        work_item_precondition_checked=True,
        work_item_precondition_passed=False,
        planner_phase_entered=False,
        shadow_report=None,
        game_pk=824488,
    )
    assert state['work_item_precondition_checked'] is True
    assert state['work_item_precondition_passed'] is False
    assert state['planner_phase_entered'] is False
    assert state['finality_check_executed'] is False
    assert state['finality_proven_by_planner'] is not True
    assert state['finality_proven_by_planner'] is None


def test_run_30862655470_renders_not_executed():
    state = qualification.execution_state(
        work_item_precondition_checked=True,
        work_item_precondition_passed=False,
        planner_phase_entered=False,
    )
    assert qualification.render_finality(state) == 'not executed'


def test_a_planned_final_game_reports_finality_proven():
    state = qualification.execution_state(
        work_item_precondition_checked=True,
        work_item_precondition_passed=True,
        planner_phase_entered=True,
        shadow_report={'planned_game_pks': [824488]},
        game_pk=824488,
    )
    assert state['finality_check_executed'] is True
    assert state['finality_proven_by_planner'] is True
    assert qualification.render_finality(state) == 'proven'


def test_a_planner_executed_non_final_game_reports_finality_false():
    state = qualification.execution_state(
        work_item_precondition_checked=True,
        work_item_precondition_passed=True,
        planner_phase_entered=True,
        shadow_report={'planned_game_pks': []},
        game_pk=824488,
    )
    assert state['finality_check_executed'] is True
    assert state['finality_proven_by_planner'] is False
    assert qualification.render_finality(state) == 'not proven'


def test_finality_is_never_inferred_from_an_absent_failure_reason():
    """The old defect: no FAILED_GAME_NOT_PLANNABLE therefore 'proven'."""
    state = qualification.execution_state(
        work_item_precondition_checked=True,
        work_item_precondition_passed=False,
        planner_phase_entered=False,
    )
    # There is no failure reason here at all, and finality is still not claimed.
    assert state['finality_proven_by_planner'] is None


def test_a_planner_that_planned_a_different_game_does_not_prove_finality():
    state = qualification.execution_state(
        work_item_precondition_checked=True,
        work_item_precondition_passed=True,
        planner_phase_entered=True,
        shadow_report={'planned_game_pks': [999999]},
        game_pk=824488,
    )
    assert state['finality_proven_by_planner'] is False


def test_the_default_execution_state_claims_nothing():
    state = qualification.execution_state()
    assert state['work_item_precondition_checked'] is False
    assert state['planner_phase_entered'] is False
    assert state['finality_check_executed'] is False
    assert state['finality_proven_by_planner'] is None
    assert qualification.render_finality(state) == 'not executed'
