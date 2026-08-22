"""The real-mutation candidate audit's classification contract.

Nothing is eligible because a failure is absent. Every eligibility condition is
positively observed, and the mutation shape must be exactly the v1 contract:
one update, one row, one field, resolved source authority.

Finding zero eligible candidates is a COMPLETED audit, not a failure — that
distinction is asserted here, because it is the one an operator is most likely
to misread under pressure.
"""

import pytest

from models.game_ingestion_work_item import GameIngestionWorkItem
from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from services import real_mutation_candidate_audit as audit
from services import real_mutation_qualification as qualification


GAME_PK = 954001
OTHER_GAME_PK = 954002
PITCHER_MLB_ID = 7701
FIELD = 'earned_runs'
FINGERPRINT = 'a' * 64


def work_item(status=GameIngestionWorkItem.STATUS_COMPLETED):
    return {
        'mlb_game_pk': GAME_PK,
        'status': status,
        'represented_date': '2026-08-10',
    }


def unchanged_row(pitcher_mlb_id=7702, **overrides):
    base = {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': pitcher_mlb_id,
        'action': reconciliation.ACTION_UNCHANGED,
        'changed_fields': [],
        'semantic_changed_fields': [],
        'mutation_categories': [reconciliation.CATEGORY_UNCHANGED],
        'is_statistical_correction': False,
        'pitcher_identity_action': pitcher_identity.ACTION_UNCHANGED,
        'target_fields': [],
        'target_state_digest': '',
        'stored_state_digest': '',
        'difference_classifications': [],
    }
    base.update(overrides)
    return base


def update_row(field=FIELD, **overrides):
    base = {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': PITCHER_MLB_ID,
        'action': reconciliation.ACTION_UPDATE,
        'changed_fields': [field],
        'semantic_changed_fields': [field],
        'mutation_categories': [
            reconciliation.CATEGORY_STATISTICAL_CORRECTION,
            reconciliation.CATEGORY_PROVENANCE_ONLY,
        ],
        'is_statistical_correction': True,
        'is_provenance_only': False,
        'pitcher_identity_action': pitcher_identity.ACTION_UNCHANGED,
        'target_fields': [field],
        'target_state_digest': 'target-1',
        'stored_state_digest': 'stored-1',
        'mutation_digest': 'mutation-1',
        'difference_classifications': [reconciliation.DIFFERENCE_STATISTICAL],
    }
    base.update(overrides)
    return base


def report(*, rows=None, status='complete', **overrides):
    rows = [update_row(), unchanged_row()] if rows is None else rows
    updates = len([
        entry for entry in rows
        if entry.get('action') == reconciliation.ACTION_UPDATE
    ])
    base = {
        'status': status,
        'mode': lane.MODE_SHADOW,
        'requested_game_pks': [GAME_PK],
        'planned_game_pks': [GAME_PK],
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'duplicate_requested_count': 0,
        'execution_scope_mode': 'exclusive',
        'execution_scope_exact_match': True,
        'games_fetched': 1,
        'games_attempted': 1,
        'games_completed': 1,
        'budget_stop_triggered': False,
        'reconciliation_plan_fingerprint': FINGERPRINT,
        'games': [{
            'game_pk': GAME_PK,
            'source_revision': 'rev-1',
            'rows': rows,
        }],
    }
    for field in qualification.PROHIBITED_PLAN_COUNTERS:
        base.setdefault(field, 0)
    base.setdefault('rows_updated', updates)
    base.setdefault('statistical_corrections', updates)
    base['rows_unchanged'] = len(rows) - updates
    base.update(overrides)
    return base


def reader(*, readable=True, match_count=1, value=2):
    def _read(*, game_pk, pitcher_mlb_id, field):
        return {
            'readable': readable,
            'match_count': match_count,
            'stored_value': value,
        }
    return _read


def classify(**overrides):
    base = {
        'game_pk': GAME_PK,
        'shadow_report': report(),
        'planner_executed': True,
        'work_item_before': work_item(),
        'work_item_after': work_item(),
        'stored_value_reader': reader(),
    }
    base.update(overrides)
    return audit.classify_candidate(**base)


# ── Eligibility ─────────────────────────────────────────────────────────────


def test_a_single_field_correction_is_eligible():
    entry = classify()
    assert entry['eligible'] is True
    assert entry['classification'] == audit.ELIGIBLE
    assert entry['reasons'] == []


def test_an_eligible_candidate_reports_everything_an_operator_needs():
    entry = classify()
    assert entry['game_pk'] == GAME_PK
    assert entry['pitcher_mlb_id'] == PITCHER_MLB_ID
    assert entry['field'] == FIELD
    assert entry['stored_value'] == 2
    assert entry['source_revision'] == 'rev-1'
    assert entry['plan_fingerprint'] == FINGERPRINT
    assert entry['work_item_status'] == GameIngestionWorkItem.STATUS_COMPLETED
    assert entry['reason_eligible']


def test_the_canonical_value_is_reported_as_a_digest_not_re_derived():
    """Re-deriving the intended value here would be a second comparator."""
    entry = classify()
    assert entry['canonical_target_state_digest'] == 'target-1'
    assert entry['stored_state_digest'] == 'stored-1'
    assert 'canonical_value' not in entry


# ── Structural refusals ─────────────────────────────────────────────────────


def test_a_missing_work_item_is_refused():
    entry = classify(work_item_before=None, work_item_after=None)
    assert entry['eligible'] is False
    assert audit.TARGET_WORK_ITEM_MISSING in entry['reasons']


@pytest.mark.parametrize('status', [
    GameIngestionWorkItem.STATUS_PLANNED,
    GameIngestionWorkItem.STATUS_IN_PROGRESS,
    GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
    GameIngestionWorkItem.STATUS_TERMINAL_FAILURE,
])
def test_a_work_item_that_is_not_completed_is_refused(status):
    entry = classify(
        work_item_before=work_item(status), work_item_after=work_item(status),
    )
    assert audit.TARGET_WORK_ITEM_NOT_COMPLETED in entry['reasons']


def test_a_work_item_that_moves_during_the_audit_is_a_failure():
    """The audit is read-only. If the row moved, something wrote."""
    entry = classify(
        work_item_after=work_item(GameIngestionWorkItem.STATUS_IN_PROGRESS),
    )
    assert audit.WORK_ITEM_CHANGED_DURING_AUDIT in entry['reasons']
    assert audit.WORK_ITEM_CHANGED_DURING_AUDIT in audit.FAILED_CLASSIFICATIONS


def test_a_planner_that_did_not_run_is_refused():
    entry = classify(planner_executed=False, shadow_report=None)
    assert audit.PLANNER_NOT_EXECUTED in entry['reasons']
    assert audit.PLANNER_NOT_EXECUTED in audit.UNPROVEN_CLASSIFICATIONS


def test_a_shadow_execution_error_is_refused():
    entry = classify(shadow_error=True)
    assert audit.SHADOW_EXECUTION_ERROR in entry['reasons']


def test_a_read_only_violation_is_refused():
    entry = classify(tables_changed=('game_logs',))
    assert audit.READ_ONLY_CONTRACT_VIOLATED in entry['reasons']
    assert entry['classification'] == audit.READ_ONLY_CONTRACT_VIOLATED


def test_a_budget_stop_is_refused():
    entry = classify(shadow_report=report(budget_stop_triggered=True))
    assert audit.SHADOW_BUDGET_STOP in entry['reasons']


def test_an_incomplete_shadow_status_is_refused():
    entry = classify(shadow_report=report(status='incomplete'))
    assert audit.SHADOW_STATUS_NOT_COMPLETE in entry['reasons']


def test_an_unplannable_game_is_refused():
    entry = classify(shadow_report=report(
        planned_game_pks=[], missing_requested_game_pks=[GAME_PK],
        execution_scope_exact_match=False,
    ))
    assert audit.GAME_NOT_PLANNABLE in entry['reasons']


def test_an_inexact_scope_is_refused():
    entry = classify(shadow_report=report(execution_scope_exact_match=False))
    assert audit.SCOPE_NOT_EXACT in entry['reasons']


# ── Mutation-shape refusals ─────────────────────────────────────────────────


def test_a_clean_game_is_not_a_candidate_and_is_not_a_defect():
    entry = classify(shadow_report=report(
        rows=[unchanged_row()], rows_updated=0, statistical_corrections=0,
    ))
    assert entry['eligible'] is False
    assert entry['classification'] == audit.NO_MUTATION_CANDIDATE
    assert audit.NO_MUTATION_CANDIDATE not in audit.FAILED_CLASSIFICATIONS
    assert audit.NO_MUTATION_CANDIDATE not in audit.UNPROVEN_CLASSIFICATIONS


def test_two_updated_rows_are_refused():
    entry = classify(shadow_report=report(
        rows=[update_row(), update_row(pitcher_mlb_id=7703)],
        rows_updated=2, statistical_corrections=2,
    ))
    assert audit.MULTI_ROW_MUTATION in entry['reasons']


def test_two_changed_fields_are_refused():
    entry = classify(shadow_report=report(rows=[update_row(
        changed_fields=['earned_runs', 'walks'],
        semantic_changed_fields=['earned_runs', 'walks'],
    )]))
    assert audit.MULTI_FIELD_MUTATION in entry['reasons']


def test_an_insert_is_refused():
    entry = classify(shadow_report=report(
        rows=[update_row(action=reconciliation.ACTION_INSERT)],
        rows_updated=0, statistical_corrections=0, rows_inserted=1,
    ))
    assert audit.PLAN_PROPOSES_INSERT in entry['reasons']


def test_a_blocked_row_is_refused():
    entry = classify(shadow_report=report(
        rows=[update_row(), unchanged_row(
            action=reconciliation.ACTION_BLOCKED,
        )],
        rows_blocked=1,
    ))
    assert audit.PLAN_CONTAINS_BLOCKED_ROW in entry['reasons']


def test_an_identity_mutation_is_refused():
    entry = classify(shadow_report=report(rows=[update_row(
        pitcher_identity_action=(
            pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY
        ),
    )]))
    assert audit.PLAN_PROPOSES_IDENTITY_MUTATION in entry['reasons']


def test_an_appearance_team_repair_is_refused():
    entry = classify(shadow_report=report(rows=[update_row(
        mutation_categories=[
            reconciliation.CATEGORY_STATISTICAL_CORRECTION,
            reconciliation.CATEGORY_APPEARANCE_TEAM_AUTHORITY,
        ],
    )]))
    assert audit.PLAN_PROHIBITED_CATEGORY in entry['reasons']


# ── Field authority ─────────────────────────────────────────────────────────


def test_an_unresolved_authority_field_is_refused():
    entry = classify(shadow_report=report(
        rows=[update_row(field='inherited_runners')],
    ))
    assert entry['eligible'] is False
    assert audit.FIELD_AUTHORITY_UNRESOLVED in entry['reasons']


def test_the_unresolved_authority_field_is_reported_with_its_state():
    entry = classify(shadow_report=report(
        rows=[update_row(field='inherited_runners')],
    ))
    assert entry['field_authority']['authority_resolved'] is False
    assert entry['field_authority']['authority_state'] == (
        qualification.FIELD_AUTHORITY_UNRESOLVED
    )


def test_a_non_statistical_field_is_refused():
    entry = classify(shadow_report=report(
        rows=[update_row(field='appearance_team_id')],
    ))
    assert audit.FIELD_NOT_GOVERNED_STATISTICAL in entry['reasons']


# ── Row readability ─────────────────────────────────────────────────────────


def test_an_unreadable_target_row_is_refused():
    entry = classify(stored_value_reader=reader(readable=False))
    assert audit.TARGET_ROW_NOT_READABLE in entry['reasons']


def test_an_absent_target_row_is_refused():
    entry = classify(stored_value_reader=reader(match_count=0))
    assert audit.TARGET_ROW_ABSENT in entry['reasons']


def test_a_duplicated_target_row_is_refused():
    entry = classify(stored_value_reader=reader(match_count=2))
    assert audit.TARGET_ROW_DUPLICATE in entry['reasons']


# ── Source revision and fingerprint ─────────────────────────────────────────


def test_a_missing_source_revision_is_refused():
    shadow = report()
    shadow['games'][0]['source_revision'] = None
    entry = classify(shadow_report=shadow)
    assert audit.SOURCE_REVISION_MISSING in entry['reasons']


def test_a_source_revision_for_the_wrong_game_is_refused():
    shadow = report()
    shadow['games'][0]['game_pk'] = OTHER_GAME_PK
    entry = classify(shadow_report=shadow)
    assert audit.SOURCE_REVISION_WRONG_GAME in entry['reasons']


def test_a_missing_plan_fingerprint_is_refused():
    entry = classify(shadow_report=report(
        reconciliation_plan_fingerprint=None,
    ))
    assert audit.PLAN_FINGERPRINT_MISSING in entry['reasons']


# ── Verdicts ────────────────────────────────────────────────────────────────


def _proof(**overrides):
    base = {'failed_reasons': [], 'unproven_reasons': []}
    base.update(overrides)
    return base


def test_zero_candidates_is_a_completed_audit():
    decision = audit.decide(candidates=[], read_only_proof=_proof())
    assert decision['result'] == audit.RESULT_NO_ELIGIBLE_CANDIDATE
    assert decision['exit_code'] == 0


def test_an_eligible_candidate_completes_with_its_game_id():
    decision = audit.decide(
        candidates=[classify()], read_only_proof=_proof(),
    )
    assert decision['result'] == audit.RESULT_ELIGIBLE_FOUND
    assert decision['exit_code'] == 0
    assert decision['eligible_game_pks'] == [GAME_PK]


def test_an_ineligible_candidate_still_completes():
    decision = audit.decide(
        candidates=[classify(shadow_report=report(
            rows=[unchanged_row()], rows_updated=0, statistical_corrections=0,
        ))],
        read_only_proof=_proof(),
    )
    assert decision['result'] == audit.RESULT_NO_ELIGIBLE_CANDIDATE


def test_a_read_only_violation_fails_the_whole_audit():
    decision = audit.decide(
        candidates=[],
        read_only_proof=_proof(failed_reasons=['durable_write_attempted']),
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['exit_code'] == 1


def test_an_untrustworthy_candidate_makes_the_audit_unproven():
    decision = audit.decide(
        candidates=[classify(shadow_error=True)], read_only_proof=_proof(),
    )
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2


def test_unavailable_discovery_is_unproven():
    decision = audit.decide(
        candidates=[], read_only_proof=_proof(), discovery_available=False,
    )
    assert decision['result'] == audit.RESULT_UNPROVEN


def test_the_verdict_names_the_refused_authority_fields():
    decision = audit.decide(candidates=[], read_only_proof=_proof())
    assert 'inherited_runners' in decision['unresolved_authority_fields']


def test_the_audit_only_ever_runs_shadow_mode():
    assert audit.PERMITTED_INGESTION_MODE == lane.MODE_SHADOW


def test_the_audit_authorizes_nothing():
    decision = audit.decide(
        candidates=[classify()], read_only_proof=_proof(),
    )
    statement = decision['non_authorization_statement'].lower()
    assert 'authorizes nothing' in statement
    assert 'no write' in statement
