"""Evidence contract for the read-only postgame publication incident audit.

Requirements 1-56.

The audit reconstructs exactly one failed cycle (run 30873422601, postgame,
slate 2026-08-03). These tests own the properties that make its verdict
trustworthy: the incident scope is locked, the classification vocabulary is
closed, absence of evidence is UNPROVEN rather than a pass, FAILED outranks
everything, and nothing in the module can widen an authority it does not own.
"""

import inspect

import pytest

from services import postgame_publication_incident_audit as audit


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_proof():
    return {
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        **audit.EXPECTED_PROBE_EVIDENCE,
    }


@pytest.fixture
def answered_questions():
    return [
        {'question_id': question_id, 'answered': True}
        for question_id in audit.QUESTION_IDS
    ]


@pytest.fixture
def clean_ingestion():
    return {
        'missing_required': [],
        'unreadable_required': [],
        'missing_optional': [],
        'all_required_present': True,
    }


@pytest.fixture
def clean_budget():
    return audit.SourceCallBudget().state()


def _decide(**overrides):
    kwargs = {
        'questions': [
            {'question_id': question_id, 'answered': True}
            for question_id in audit.QUESTION_IDS
        ],
        'classifications': [],
        'read_only_proof': {
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': True,
            **audit.EXPECTED_PROBE_EVIDENCE,
        },
        'artifact_ingestion': {
            'missing_required': [], 'unreadable_required': [],
            'all_required_present': True,
        },
        'budget_state': audit.SourceCallBudget().state(),
    }
    kwargs.update(overrides)
    return audit.decide(**kwargs)


# ── 1-10 Incident identity is locked ────────────────────────────────────────

def test_001_incident_run_id_is_the_reported_incident():
    assert audit.INCIDENT_RUN_ID == '30873422601'


def test_002_incident_head_sha_is_the_reported_head():
    assert audit.INCIDENT_HEAD_SHA == (
        '9f9f640799af973f0a39cdafb1db83fba473b10c'
    )


def test_003_incident_cycle_is_postgame():
    assert audit.INCIDENT_CYCLE == 'postgame'


def test_004_incident_slate_is_the_reported_slate():
    assert audit.INCIDENT_SLATE_DATE.isoformat() == '2026-08-03'


def test_005_incident_game_is_822867():
    assert audit.INCIDENT_GAME_PK == 822867


def test_006_incident_snapshot_ids_are_344_and_343():
    assert audit.INCIDENT_CANDIDATE_SNAPSHOT_ID == 344
    assert audit.INCIDENT_SERVING_SNAPSHOT_ID == 343


def test_007_incident_sync_run_is_596():
    assert audit.INCIDENT_SYNC_RUN_ID == 596


def test_008_incident_identity_exposes_every_locked_field():
    identity = audit.incident_identity()
    assert identity['workflow_run_id'] == audit.INCIDENT_RUN_ID
    assert identity['head_sha'] == audit.INCIDENT_HEAD_SHA
    assert identity['cycle'] == audit.INCIDENT_CYCLE
    assert identity['slate_date'] == audit.INCIDENT_SLATE_DATE.isoformat()
    assert identity['game_pk'] == audit.INCIDENT_GAME_PK
    assert identity['candidate_snapshot_id'] == 344
    assert identity['serving_snapshot_id'] == 343
    assert identity['sync_run_id'] == 596


def test_009_incident_scope_accepts_only_the_locked_scope():
    assert audit.validate_incident_scope(
        run_id=audit.INCIDENT_RUN_ID,
        cycle=audit.INCIDENT_CYCLE,
        slate_date=audit.INCIDENT_SLATE_DATE,
    ) == []


@pytest.mark.parametrize('kwargs,expected', [
    ({'run_id': '1', 'cycle': 'postgame', 'slate_date': '2026-08-03'},
     'incident_run_id_mismatch'),
    ({'run_id': '30873422601', 'cycle': 'daily',
      'slate_date': '2026-08-03'}, 'incident_cycle_mismatch'),
    ({'run_id': '30873422601', 'cycle': 'postgame',
      'slate_date': '2026-08-04'}, 'incident_slate_date_mismatch'),
    ({'run_id': '30873422601', 'cycle': 'postgame', 'slate_date': 'garbage'},
     'incident_slate_date_mismatch'),
])
def test_010_incident_scope_refuses_any_other_scope(kwargs, expected):
    assert expected in audit.validate_incident_scope(**kwargs)


# ── 11-16 Confirmation and non-authorization ────────────────────────────────

def test_011_confirmation_names_the_incident_run():
    assert audit.CONFIRMATION == (
        'AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601'
    )


def test_012_non_authorization_statement_is_exact():
    assert audit.NON_AUTHORIZATION_STATEMENT == (
        'This audit is read-only. It does not authorize backfill, repair, '
        'schedule-status mutation, appearance-row creation, marker reset, '
        'snapshot publication, automated writes, authoritative mode, or any '
        'future production mutation.'
    )


@pytest.mark.parametrize('phrase', [
    'backfill', 'repair', 'schedule-status mutation',
    'appearance-row creation', 'marker reset', 'snapshot publication',
    'automated writes', 'authoritative mode', 'future production mutation',
])
def test_013_non_authorization_statement_names_every_prohibition(phrase):
    assert phrase in audit.NON_AUTHORIZATION_STATEMENT


def test_014_every_decision_carries_the_non_authorization_statement():
    assert _decide()['non_authorization_statement'] == (
        audit.NON_AUTHORIZATION_STATEMENT
    )


def test_015_failed_decision_still_carries_the_statement():
    decision = _decide(read_only_proof={
        **audit.EXPECTED_PROBE_EVIDENCE,
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': False,
    })
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['non_authorization_statement'] == (
        audit.NON_AUTHORIZATION_STATEMENT
    )


def test_016_module_never_claims_the_incident_is_fixed():
    source = inspect.getsource(audit).lower()
    for phrase in ('incident is fixed', 'now fixed', 'has been repaired'):
        assert phrase not in source


# ── 17-24 Results and exit codes ────────────────────────────────────────────

def test_017_three_complete_results_exist():
    assert audit.COMPLETE_RESULTS == {
        audit.RESULT_ROOT_CAUSE_IDENTIFIED,
        audit.RESULT_NO_PLATFORM_DEFECT_PROVEN,
        audit.RESULT_INCIDENT_NOT_REPRODUCIBLE,
    }


@pytest.mark.parametrize('result', [
    'COMPLETE_ROOT_CAUSE_IDENTIFIED',
    'COMPLETE_NO_PLATFORM_DEFECT_PROVEN',
    'COMPLETE_INCIDENT_NOT_REPRODUCIBLE',
])
def test_018_complete_results_exit_zero(result):
    assert audit.EXIT_CODES[result] == 0


def test_019_failed_exits_one():
    assert audit.EXIT_CODES[audit.RESULT_FAILED] == 1


def test_020_unproven_exits_two():
    assert audit.EXIT_CODES[audit.RESULT_UNPROVEN] == 2


def test_021_every_result_has_exactly_one_exit_code():
    assert set(audit.EXIT_CODES) == audit.COMPLETE_RESULTS | {
        audit.RESULT_FAILED, audit.RESULT_UNPROVEN,
    }


def test_022_root_cause_identified_requires_a_platform_defect():
    decision = _decide(classifications=[
        audit.CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE,
    ])
    assert decision['result'] == audit.RESULT_ROOT_CAUSE_IDENTIFIED
    assert decision['platform_defect_proven'] is True


def test_023_fail_closed_only_is_no_platform_defect_proven():
    decision = _decide(classifications=[
        audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
        audit.CLASSIFICATION_SNAPSHOT_WITHHELD_BY_APPEARANCE_LEDGER_GATE,
    ])
    assert decision['result'] == audit.RESULT_NO_PLATFORM_DEFECT_PROVEN
    assert decision['platform_defect_proven'] is False


def test_024_no_classification_is_incident_not_reproducible():
    assert _decide()['result'] == audit.RESULT_INCIDENT_NOT_REPRODUCIBLE


# ── 25-34 Twelve named classifications, closed vocabulary ───────────────────

def test_025_exactly_twelve_classifications_exist():
    assert len(audit.CLASSIFICATION_PRECEDENCE) == 12


def test_026_classification_names_are_unique():
    assert len(set(audit.CLASSIFICATION_PRECEDENCE)) == 12


def test_027_every_classification_is_platform_defect_or_fail_closed():
    assert (
        audit.PLATFORM_DEFECT_CLASSIFICATIONS
        | audit.FAIL_CLOSED_CLASSIFICATIONS
    ) == set(audit.CLASSIFICATION_PRECEDENCE)


def test_028_no_classification_is_both():
    assert not (
        audit.PLATFORM_DEFECT_CLASSIFICATIONS
        & audit.FAIL_CLOSED_CLASSIFICATIONS
    )


def test_029_read_only_violation_has_highest_precedence():
    assert audit.CLASSIFICATION_PRECEDENCE[0] == (
        audit.CLASSIFICATION_READ_ONLY_CONTRACT_VIOLATED
    )


def test_030_classifications_are_reported_in_precedence_order():
    decision = _decide(classifications=[
        audit.CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING,
        audit.CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT,
    ])
    assert decision['classifications'] == [
        audit.CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT,
        audit.CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING,
    ]


def test_031_primary_classification_is_the_highest_precedence_one():
    decision = _decide(classifications=[
        audit.CLASSIFICATION_SNAPSHOT_WITHHELD_BY_SLATE_COVERAGE,
        audit.CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER,
    ])
    assert decision['primary_classification'] == (
        audit.CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER
    )


def test_032_duplicate_classifications_collapse():
    decision = _decide(classifications=[
        audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
        audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
    ])
    assert decision['classifications'] == [
        audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
    ]


def test_033_unknown_classifications_are_reported_last_not_dropped():
    decision = _decide(classifications=[
        'made_up_condition',
        audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
    ])
    assert decision['classifications'] == [
        audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
        'made_up_condition',
    ]


def test_034_classification_vocabulary_covers_the_incident_surface():
    for name in (
        'schedule_row_finality_conflict',
        'stored_schedule_state_diverges_from_source',
        'finality_authority_maps_game_out_of_planning_scope',
        'ledger_membership_diverges_from_planner_membership',
        'postgame_marker_incomplete',
        'postgame_marker_missing',
        'appearance_rows_missing_for_final_game',
        'work_item_backlog_unresolved',
        'snapshot_withheld_by_appearance_ledger_gate',
        'snapshot_withheld_by_slate_coverage',
        'publication_proof_candidate_not_serving',
    ):
        assert name in audit.CLASSIFICATION_PRECEDENCE


# ── 35-42 Verdict precedence: FAILED > UNPROVEN > COMPLETE ──────────────────

def test_035_failed_outranks_unproven():
    decision = _decide(
        questions=[],
        read_only_proof={
            **audit.EXPECTED_PROBE_EVIDENCE,
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': False,
        },
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['unproven_reasons']


def test_036_unproven_outranks_complete():
    decision = _decide(
        classifications=[
            audit.CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE,
        ],
        questions=[],
    )
    assert decision['result'] == audit.RESULT_UNPROVEN


def test_037_unproven_never_reports_a_platform_defect_as_proven():
    decision = _decide(
        classifications=[
            audit.CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE,
        ],
        questions=[],
    )
    assert decision['platform_defect_proven'] is False


def test_038_missing_guard_is_unproven():
    decision = _decide(read_only_proof={
        **audit.EXPECTED_PROBE_EVIDENCE,
        'advisory_guard_acquired': False,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
    })
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_GUARD_NOT_ACQUIRED in decision['unproven_reasons']


def test_039_read_only_not_enforced_is_unproven():
    decision = _decide(read_only_proof={
        **audit.EXPECTED_PROBE_EVIDENCE,
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': False,
        'fingerprints_match': True,
    })
    assert audit.UNPROVEN_READ_ONLY_NOT_ENFORCED in (
        decision['unproven_reasons']
    )


def test_040_unavailable_fingerprints_are_unproven_not_a_pass():
    decision = _decide(read_only_proof={
        **audit.EXPECTED_PROBE_EVIDENCE,
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': None,
    })
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_FINGERPRINTS_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_041_changed_fingerprints_are_failed():
    decision = _decide(read_only_proof={
        **audit.EXPECTED_PROBE_EVIDENCE,
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': False,
    })
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_FINGERPRINTS_CHANGED in decision['failed_reasons']


def test_042_a_content_change_forces_the_read_only_violation_classification():
    decision = _decide(read_only_proof={
        **audit.EXPECTED_PROBE_EVIDENCE,
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': False,
    })
    assert audit.CLASSIFICATION_READ_ONLY_CONTRACT_VIOLATED in (
        decision['classifications']
    )


# ── 43-48 Probe evidence: absence never masks, and never manufactures ───────

def test_043_accepted_probe_is_failed_not_unproven():
    result = audit.evaluate_probe_evidence({
        **audit.EXPECTED_PROBE_EVIDENCE, 'read_only_probe_refused': False,
    })
    assert audit.FAILED_READ_ONLY_PROBE_ACCEPTED in result['failed_reasons']
    assert result['unproven_reasons'] == []


def test_044_missing_probe_evidence_is_unproven_only():
    result = audit.evaluate_probe_evidence({})
    assert result['failed_reasons'] == []
    assert audit.UNPROVEN_PROBE_EVIDENCE_MISSING in result['unproven_reasons']


def test_045_missing_fields_never_mask_a_present_violation():
    result = audit.evaluate_probe_evidence({'read_only_probe_refused': False})
    assert audit.FAILED_READ_ONLY_PROBE_ACCEPTED in result['failed_reasons']
    assert audit.UNPROVEN_PROBE_EVIDENCE_MISSING in result['unproven_reasons']


def test_046_a_durable_write_attempt_is_failed():
    result = audit.evaluate_probe_evidence({
        **audit.EXPECTED_PROBE_EVIDENCE, 'durable_write_attempts': 1,
    })
    assert audit.FAILED_DURABLE_WRITE_ATTEMPTED in result['failed_reasons']


@pytest.mark.parametrize('field,value,reason', [
    ('read_only_probe_count', 2, 'read_only_probe_count_unexpected'),
    ('read_only_probe_statement_class', 'DELETE',
     'read_only_probe_statement_class_unexpected'),
    ('read_only_probe_bounded_to_zero_rows', False,
     'read_only_probe_not_bounded_to_zero_rows'),
])
def test_047_each_present_probe_contradiction_is_failed(field, value, reason):
    result = audit.evaluate_probe_evidence({
        **audit.EXPECTED_PROBE_EVIDENCE, field: value,
    })
    assert reason in result['failed_reasons']


def test_048_expected_probe_evidence_matches_the_shared_contract():
    from services import noop_qualification_candidate_audit as shared

    assert audit.EXPECTED_PROBE_EVIDENCE == shared.EXPECTED_PROBE_EVIDENCE


# ── 49-52 Evidence artifacts ────────────────────────────────────────────────

def test_049_missing_required_artifact_is_unproven():
    decision = _decide(artifact_ingestion={
        'missing_required': [audit.ARTIFACT_LEDGER_AUDIT],
        'unreadable_required': [],
        'all_required_present': False,
    })
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_REQUIRED_ARTIFACT_MISSING in (
        decision['unproven_reasons']
    )


def test_050_unreadable_required_artifact_is_unproven():
    decision = _decide(artifact_ingestion={
        'missing_required': [],
        'unreadable_required': [audit.ARTIFACT_SHADOW],
        'all_required_present': False,
    })
    assert audit.UNPROVEN_REQUIRED_ARTIFACT_UNREADABLE in (
        decision['unproven_reasons']
    )


def test_051_missing_optional_artifact_does_not_change_the_verdict():
    decision = _decide(artifact_ingestion={
        'missing_required': [], 'unreadable_required': [],
        'missing_optional': [audit.ARTIFACT_SHADOW_HANDOFF],
        'all_required_present': True,
    })
    assert decision['result'] == audit.RESULT_INCIDENT_NOT_REPRODUCIBLE


def test_052_artifact_expectations_name_the_incident_run_exactly():
    expectations = audit.artifact_expectations()
    assert expectations['required'] == [
        'game-driven-shadow-30873422601',
        'appearance-ledger-audit-30873422601',
    ]
    assert expectations['optional'] == [
        'game-driven-shadow-handoff-30873422601',
    ]
    assert expectations['run_id'] == '30873422601'


# ── 53-56 Questions ─────────────────────────────────────────────────────────

def test_053_exactly_eight_questions_exist():
    assert len(audit.QUESTION_IDS) == 8
    assert len(set(audit.QUESTION_IDS)) == 8


def test_054_every_question_has_text():
    assert set(audit.QUESTION_TEXT) == set(audit.QUESTION_IDS)
    assert all(audit.QUESTION_TEXT[key].strip() for key in audit.QUESTION_IDS)


def test_055_one_unanswered_question_makes_the_audit_unproven():
    questions = [
        {'question_id': question_id, 'answered': True}
        for question_id in audit.QUESTION_IDS[:-1]
    ]
    decision = _decide(questions=questions)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_QUESTION_UNANSWERED in decision['unproven_reasons']
    assert decision['unanswered_question_ids'] == [audit.QUESTION_IDS[-1]]


def test_056_answered_counts_are_reported_honestly():
    questions = [
        {'question_id': question_id, 'answered': index < 5}
        for index, question_id in enumerate(audit.QUESTION_IDS)
    ]
    decision = _decide(questions=questions)
    assert decision['questions_answered'] == 5
    assert decision['questions_total'] == 8
