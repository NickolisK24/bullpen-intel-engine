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
            'SHADOW_STATUS_COMPLETE', 'SHADOW_STATUS_INCOMPLETE',
            'UNPROVEN_PROBE_EVIDENCE_MISSING', 'UNPROVEN_PROBE_NOT_ATTEMPTED',
            'UNPROVEN_PROBE_COUNT_UNKNOWN', 'FAILED_PROBE_COUNT_UNEXPECTED',
            'FAILED_PROBE_STATEMENT_CLASS_UNEXPECTED',
            'FAILED_PROBE_NOT_BOUNDED', 'FAILED_PROBE_ACCEPTED',
            'FAILED_DURABLE_WRITE_ATTEMPTED',
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
        # A COMPLETE result now requires positively proven probe evidence.
        **audit.EXPECTED_PROBE_EVIDENCE,
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


# ── Blocker 1: the complete shared governance pass is required ─────────────


def test_an_unknown_action_is_never_eligible():
    result = classify(shadow_report=shadow_report(
        rows=[row(action='teleport')]))
    assert result['eligible'] is False
    assert audit.PLAN_UNKNOWN_ACTION in result['reason_codes']


def test_a_future_action_type_fails_closed():
    """A type nobody has written yet must not read as unchanged."""
    for future in ('merge', 'archive', 'supersede', 'rewrite', ''):
        result = classify(shadow_report=shadow_report(
            rows=[row(action=future)]))
        assert result['eligible'] is False, future


def test_an_unchanged_row_carrying_changed_fields_is_never_eligible():
    result = classify(shadow_report=shadow_report(
        rows=[row(changed_fields=['strikeouts'])]))
    assert result['eligible'] is False
    assert audit.PLAN_CHANGED_FIELDS_ON_UNCHANGED_ROW in (
        result['reason_codes']
    )


def test_unchanged_coverage_below_planned_row_count_is_never_eligible():
    result = classify(shadow_report=shadow_report(rows=[
        row(), row(pitcher_mlb_id=4002, action=reconciliation.ACTION_UPDATE),
    ]))
    assert result['eligible'] is False
    assert audit.PLAN_UNCHANGED_COVERAGE_INCOMPLETE in result['reason_codes']


def test_prohibited_actions_above_zero_is_never_eligible():
    result = classify(shadow_report=shadow_report(
        rows=[row(pitcher_identity_action='create_minimal_identity')]))
    governance = qualification.evaluate_plan_governance(
        shadow_report(rows=[
            row(pitcher_identity_action='create_minimal_identity')])
    )
    assert governance['prohibited_actions'] > 0
    assert result['eligible'] is False
    assert audit.PLAN_PROHIBITED_ACTION in result['reason_codes']


def test_all_rows_already_matching_false_is_never_eligible():
    report = shadow_report(rows=[row(action=reconciliation.ACTION_UPDATE)])
    assert qualification.evaluate_plan_governance(report)[
        'all_rows_already_matching'
    ] is False
    assert classify(shadow_report=report)['eligible'] is False


def test_the_positive_predicate_lists_every_required_condition():
    result = classify()
    conditions = result['eligibility_conditions']
    for required in (
        'work_item_present', 'work_item_completed', 'represented_date_present',
        'shadow_status_complete', 'no_budget_stop', 'exact_scope',
        'planned_is_exactly_target', 'requested_is_exactly_target',
        'no_duplicate_request', 'planned_rows_present', 'all_rows_unchanged',
        'no_unknown_actions', 'no_prohibited_actions',
        'no_nonzero_mutation_counters',
        'governance_all_rows_already_matching',
        'exactly_one_valid_source_revision', 'plan_fingerprint_present',
    ):
        assert required in conditions, required
    assert all(conditions.values())
    assert result['unmet_eligibility_conditions'] == []


def test_eligibility_is_never_granted_from_absence_of_a_reason_code():
    """Force the predicate to fail while no reason code fires."""
    import services.noop_qualification_candidate_audit as service

    original = service.positive_eligibility
    try:
        service.positive_eligibility = lambda **kwargs: {
            'conditions': {'forced': False},
            'unmet_conditions': ['forced'],
            'all_conditions_met': False,
        }
        result = classify()
        assert result['eligible'] is False
        assert result['primary_classification'] == audit.PLAN_GOVERNANCE_FAILED
    finally:
        service.positive_eligibility = original


# ── Blocker 2: the canonical successful status is required ─────────────────


def test_the_canonical_successful_status_is_complete():
    assert audit.SHADOW_STATUS_COMPLETE == 'complete'


def test_a_complete_status_is_required_for_eligibility():
    result = classify()
    assert result['shadow_status'] == 'complete'
    assert result['shadow_status_is_complete'] is True
    assert result['eligible'] is True


@pytest.mark.parametrize('status,expected', [
    ('incomplete', audit.SHADOW_BUDGET_STOP),
    ('scope_mismatch', audit.SCOPE_NOT_EXACT),
    ('scope_invalid', audit.SCOPE_NOT_EXACT),
    ('plan_authorization_required', audit.EVIDENCE_UNPROVEN),
    ('plan_fingerprint_mismatch', audit.PLAN_FINGERPRINT_MISSING),
    ('disabled', audit.SHADOW_EXECUTION_ERROR),
    ('planned', audit.SHADOW_STATUS_NOT_COMPLETE),
])
def test_every_known_non_success_status_is_classified(status, expected):
    result = classify(shadow_report=shadow_report(status=status))
    assert result['eligible'] is False
    assert expected in result['reason_codes']


@pytest.mark.parametrize('status', [
    'partial', 'future_status', 'degraded', 'retrying', '', None,
])
def test_an_unknown_or_missing_status_fails_closed(status):
    result = classify(shadow_report=shadow_report(status=status))
    assert result['eligible'] is False
    assert audit.SHADOW_EXECUTION_ERROR in result['reason_codes']


def test_unchanged_rows_do_not_rescue_a_non_success_status():
    """Rows can look perfect while the run refused."""
    result = classify(shadow_report=shadow_report(status='scope_mismatch'))
    governance = qualification.evaluate_plan_governance(
        shadow_report(status='scope_mismatch')
    )
    assert governance['all_rows_already_matching'] is True
    assert result['eligible'] is False


# ── Blocker 4: honest probe evidence ───────────────────────────────────────


def test_the_probe_evidence_fields_are_declared():
    """The audit issues one SQL write statement; it must say so."""
    import inspect

    source = inspect.getsource(audit.enforce_read_only)
    for field in (
        'read_only_probe_attempted', 'read_only_probe_count',
        'read_only_probe_statement_class',
        'read_only_probe_bounded_to_zero_rows', 'read_only_probe_refused',
        'durable_write_attempts',
    ):
        assert field in source, field


def test_the_probe_is_never_reported_as_zero_sql_write_attempts():
    import inspect

    source = inspect.getsource(audit)
    assert 'writes_attempted_by_audit' not in source


# ── Markdown evidence (defect 2) ───────────────────────────────────────────


def _document(**overrides):
    """A successful audit document, shaped as the script builds it."""
    proof = {
        'advisory_guard_acquired': True,
        'advisory_guard_release_attempted': True,
        'advisory_guard_released': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        'changed_tables': [],
        'fingerprint_tables': list(audit.FINGERPRINT_TABLES),
        'read_only_probe_attempted': True,
        'read_only_probe_count': 1,
        'read_only_probe_statement_class': 'UPDATE',
        'read_only_probe_bounded_to_zero_rows': True,
        'read_only_probe_refused': True,
        'durable_write_attempts': 0,
        'durable_rows_created': 0,
        'durable_rows_updated': 0,
        'durable_rows_deleted': 0,
        'commits_performed_by_audit': 0,
    }
    base = {
        'identity': {
            'audit_type': audit.AUDIT_TYPE, 'schema_version': '1',
            'repository': 'NickolisK24/bullpen-intel-engine',
            'workflow_run_id': '1', 'workflow_run_attempt': '1',
            'commit_sha': 'a' * 40, 'ref': 'refs/heads/main',
            'actor': 'NickolisK24', 'executed_at': '2026-08-04T00:00:00Z',
        },
        'request': {
            'lookback_days': 30, 'candidate_limit': 20,
            'eligible_target_count': 5,
        },
        'read_only_proof': proof,
        'discovery': {
            'completed_work_items_found': 3, 'duplicate_count': 0,
            'candidates_selected': 3, 'candidates_evaluated': 2,
            'deterministic_ordering': 'completed_at DESC',
            'bounded_stop_reason': 'eligible_target_reached',
        },
        'candidate_summary': {
            'eligible_count': 1, 'ineligible_count': 1, 'unproven_count': 0,
            'ordered_eligible_game_pks': [111],
            'suggested_candidate_game_pk': 111,
            'suggestion_note': 'informational only',
        },
        'candidates': [],
        'verdict': {
            'result': audit.RESULT_ELIGIBLE_FOUND, 'exit_code': 0,
            'failed_reasons': [], 'unproven_reasons': [],
            'explanation': 'ok',
            'non_authorization_statement': (
                audit.NON_AUTHORIZATION_STATEMENT
            ),
        },
    }
    base.update(overrides)
    return base


def _render():
    import scripts.run_noop_qualification_candidate_audit as script

    return script.render_markdown(_document())


def test_the_markdown_never_mentions_the_removed_field():
    assert 'writes_attempted_by_audit' not in _render()
    assert 'writes attempted by audit' not in _render()


@pytest.mark.parametrize('label', [
    'read-only probe attempted', 'read-only probe count',
    'read-only probe statement class',
    'read-only probe bounded to zero rows', 'read-only probe refused',
    'durable write attempts', 'durable rows created', 'durable rows updated',
    'durable rows deleted', 'commits performed by audit',
])
def test_the_markdown_renders_every_probe_field(label):
    assert label in _render()


def test_no_none_probe_value_appears_in_a_successful_document():
    rendered = _render()
    for line in rendered.splitlines():
        if 'probe' in line.lower() or 'durable' in line.lower():
            assert 'None' not in line, line


def test_the_markdown_states_the_bounded_statement_and_zero_durable_writes():
    rendered = _render()
    assert 'exactly one bounded proof statement' in rendered
    assert 'zero durable writes' in rendered
    assert '| durable write attempts | 0 |' in rendered
    assert '| read-only probe count | 1 |' in rendered
    assert '| read-only probe refused | True |' in rendered


def test_the_markdown_does_not_reproduce_the_probe_sql():
    rendered = _render()
    assert 'WHERE 1 = 0' not in rendered
    assert 'stat_correction_count' not in rendered


# ── Probe evidence is part of the verdict (defect 3) ───────────────────────


def _proof(**overrides):
    base = {
        'read_only_enabled': True,
        'guard_acquired': True,
        'guard_release_attempted': True,
        'guard_released': True,
        'before_fingerprints': {'game_logs': 'x'},
        'after_fingerprints': {'game_logs': 'x'},
        'fingerprints_match': True,
        **audit.EXPECTED_PROBE_EVIDENCE,
    }
    base.update(overrides)
    return base


def test_a_complete_audit_requires_the_full_probe_evidence():
    decision = audit.decide(candidates=[], read_only_proof=_proof())
    assert decision['result'] == audit.RESULT_NO_ELIGIBLE_CANDIDATE
    assert decision['probe_evidence_valid'] is True
    assert decision['probe_evidence_complete'] is True


@pytest.mark.parametrize('field', audit.PROBE_EVIDENCE_FIELDS)
def test_missing_probe_evidence_is_unproven(field):
    proof = _proof()
    proof.pop(field)
    decision = audit.decide(candidates=[], read_only_proof=proof)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_PROBE_EVIDENCE_MISSING in (
        decision['unproven_reasons']
    )
    assert decision['probe_evidence_complete'] is False


def test_a_probe_that_was_not_attempted_is_unproven():
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        read_only_probe_attempted=False))
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_PROBE_NOT_ATTEMPTED in decision['unproven_reasons']


@pytest.mark.parametrize('count', [0, 2, 5])
def test_a_wrong_probe_count_is_failed(count):
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        read_only_probe_count=count))
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_PROBE_COUNT_UNEXPECTED in decision['failed_reasons']


@pytest.mark.parametrize('count', [None, 'one', 1.0])
def test_an_unknown_probe_count_is_unproven(count):
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        read_only_probe_count=count))
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_PROBE_COUNT_UNKNOWN in decision['unproven_reasons']


@pytest.mark.parametrize('statement_class', ['DELETE', 'INSERT', 'SELECT', ''])
def test_a_wrong_statement_class_is_failed(statement_class):
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        read_only_probe_statement_class=statement_class))
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_PROBE_STATEMENT_CLASS_UNEXPECTED in (
        decision['failed_reasons']
    )


def test_a_probe_not_bounded_to_zero_rows_is_failed():
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        read_only_probe_bounded_to_zero_rows=False))
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_PROBE_NOT_BOUNDED in decision['failed_reasons']


def test_a_probe_that_was_accepted_rather_than_refused_is_failed():
    """If the write succeeded, the transaction was never read-only."""
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        read_only_probe_refused=False))
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_PROBE_ACCEPTED in decision['failed_reasons']


@pytest.mark.parametrize('attempts', [1, 3])
def test_any_durable_write_attempt_is_failed(attempts):
    decision = audit.decide(candidates=[], read_only_proof=_proof(
        durable_write_attempts=attempts))
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_DURABLE_WRITE_ATTEMPTED in decision['failed_reasons']


def test_no_complete_result_is_reachable_without_probe_proof():
    """Neither COMPLETE result may be returned on unproven probe evidence."""
    eligible = classify()
    for broken in (
        {'read_only_probe_attempted': False},
        {'read_only_probe_refused': False},
        {'read_only_probe_count': 7},
        {'durable_write_attempts': 2},
    ):
        decision = audit.decide(
            candidates=[eligible], read_only_proof=_proof(**broken),
        )
        assert decision['result'] not in (
            audit.RESULT_ELIGIBLE_FOUND, audit.RESULT_NO_ELIGIBLE_CANDIDATE
        ), broken


def test_probe_evidence_is_lifted_without_defaulting_missing_fields():
    """A missing field must stay missing, never default to a passing value."""
    assert audit.probe_evidence({}) == {}
    assert audit.probe_evidence(None) == {}
    lifted = audit.probe_evidence({'read_only_probe_count': 1, 'other': 'x'})
    assert lifted == {'read_only_probe_count': 1}


def test_the_enforcement_detail_supplies_every_expected_probe_field():
    """What enforce_read_only returns must satisfy the contract it is checked
    against — otherwise a real successful run would report UNPROVEN."""
    import inspect

    source = inspect.getsource(audit.enforce_read_only)
    for field in audit.PROBE_EVIDENCE_FIELDS:
        assert f"'{field}'" in source, field


# ── Missing evidence must not mask a definite violation ────────────────────
# evaluate_probe_evidence used to return early on any missing field, so a run
# that was BOTH incompletely evidenced AND definitely in breach reported only
# UNPROVEN. The breach is the more important fact.


def _absent(field):
    proof = _proof()
    proof.pop(field)
    return proof


@pytest.mark.parametrize('missing,violation,expected_failed', [
    ('read_only_probe_count', {'durable_write_attempts': 1},
     audit.FAILED_DURABLE_WRITE_ATTEMPTED),
    ('read_only_probe_attempted',
     {'read_only_probe_statement_class': 'DELETE'},
     audit.FAILED_PROBE_STATEMENT_CLASS_UNEXPECTED),
    ('read_only_probe_bounded_to_zero_rows',
     {'read_only_probe_refused': False}, audit.FAILED_PROBE_ACCEPTED),
    ('read_only_probe_statement_class', {'read_only_probe_count': 2},
     audit.FAILED_PROBE_COUNT_UNEXPECTED),
])
def test_a_missing_field_does_not_hide_a_present_violation(
    missing, violation, expected_failed,
):
    proof = _absent(missing)
    proof.update(violation)
    decision = audit.decide(candidates=[], read_only_proof=proof)

    assert decision['result'] == audit.RESULT_FAILED
    assert expected_failed in decision['failed_reasons']
    # The absence is still reported, it just does not outrank the violation.
    assert audit.UNPROVEN_PROBE_EVIDENCE_MISSING in (
        decision['unproven_reasons']
    )
    assert decision['probe_evidence_complete'] is False
    assert missing in decision['probe_evidence_missing_fields']


def test_multiple_missing_fields_and_multiple_violations_are_all_reported():
    proof = _proof()
    proof.pop('read_only_probe_attempted')
    proof.pop('read_only_probe_count')
    proof['read_only_probe_refused'] = False
    proof['durable_write_attempts'] = 3

    decision = audit.decide(candidates=[], read_only_proof=proof)
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_PROBE_ACCEPTED in decision['failed_reasons']
    assert audit.FAILED_DURABLE_WRITE_ATTEMPTED in decision['failed_reasons']
    assert sorted(decision['probe_evidence_missing_fields']) == [
        'read_only_probe_attempted', 'read_only_probe_count',
    ]


@pytest.mark.parametrize('field', audit.PROBE_EVIDENCE_FIELDS)
def test_a_missing_field_alone_is_unproven_not_failed(field):
    """Absence never manufactures a failure for the field that is absent."""
    decision = audit.decide(candidates=[], read_only_proof=_absent(field))
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['failed_reasons'] == []


def test_failed_outranks_unproven_at_the_top_level():
    proof = _absent('read_only_probe_count')
    proof['read_only_probe_refused'] = False
    decision = audit.decide(candidates=[], read_only_proof=proof)
    assert decision['unproven_reasons']
    assert decision['failed_reasons']
    assert decision['result'] == audit.RESULT_FAILED


def test_probe_evidence_valid_is_false_when_anything_is_missing_or_invalid():
    assert audit.evaluate_probe_evidence(
        _proof()
    )['probe_evidence_valid'] is True
    assert audit.evaluate_probe_evidence(
        _absent('read_only_probe_count')
    )['probe_evidence_valid'] is False
    assert audit.evaluate_probe_evidence(
        _proof(read_only_probe_refused=False)
    )['probe_evidence_valid'] is False


def test_every_present_field_is_still_validated_when_others_are_absent():
    """The whole point: validation continues past the missing ones."""
    proof = {
        'read_only_probe_refused': False,
        'durable_write_attempts': 4,
        'read_only_probe_statement_class': 'DROP',
    }
    result = audit.evaluate_probe_evidence(proof)
    assert audit.FAILED_PROBE_ACCEPTED in result['failed_reasons']
    assert audit.FAILED_DURABLE_WRITE_ATTEMPTED in result['failed_reasons']
    assert audit.FAILED_PROBE_STATEMENT_CLASS_UNEXPECTED in (
        result['failed_reasons']
    )
    assert len(result['missing_fields']) == 3
