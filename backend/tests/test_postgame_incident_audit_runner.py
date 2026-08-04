"""Orchestration contract for the incident audit runner.

Requirements 115-126.

The runner is what actually produces the evidence document. These tests own the
properties that make that document trustworthy without a database: every
workflow gate is re-validated in code, the eight questions are built from
observations rather than assumed, classification names only what an authority
reported, and a refusal still writes a complete, scannable artifact.
"""

import json

import pytest

from services import postgame_publication_incident_audit as audit
import scripts.run_postgame_publication_incident_audit as runner


VALID_SHA = 'a' * 40


def _context(**overrides):
    context = {
        'event_name': 'workflow_dispatch',
        'repository': 'NickolisK24/bullpen-intel-engine',
        'actor': 'NickolisK24',
        'ref': 'refs/heads/main',
        'github_sha': VALID_SHA,
        'expected_head_sha': VALID_SHA,
        'confirmation': audit.CONFIRMATION,
    }
    context.update(overrides)
    return context


def _observations(**overrides):
    observations = {
        'stored_schedule': {
            'row_count': 2,
            'rows': [
                {'game_date': '2026-08-03', 'status_state': 'final'},
                {'game_date': '2026-08-03', 'status_state': 'final'},
            ],
            'distinct_status_states': ['final'],
            'rows_agree': True,
            'stored_status_state': 'final',
            'counts_as_ledger_final': True,
            'unresolved_resumed_linkage': False,
        },
        'official_status': {
            'game_found_in_source': True,
            'raw_status_code': 'C',
            'raw_detailed_state': 'Cancelled',
            'finality_state': 'cancelled',
            'finality_reason': 'cancelled_status',
            'mapped_status_state': 'other',
        },
        'baseball_state': {
            'appearance_row_count': 0,
            'distinct_pitcher_mlb_ids': [],
            'postgame_marker': None,
            'work_item': None,
            'team_pitching_split_rows': 0,
            'completed_game_context_rows': 0,
            'play_by_play_event_rows': 0,
        },
        'appearance_ledger': {
            'complete': False,
            'reasons': ['final_games_without_appearance_rows'],
            'deficit_game_pks': [audit.INCIDENT_GAME_PK],
        },
        'completeness': {
            'plan': {
                'incident_game_planned': False,
                'incident_game_exclusion_reason': 'cancelled',
                'finality_conflicts': [],
            },
            'completeness': {'unresolved_final_games': 60},
            'unresolved_attribution': {
                'attributed_game_count': 60,
                'authority_unresolved_final_games': 60,
                'reconciles_with_authority': True,
                'unattributed_count': 0,
                'classification_counts': {'work_item_retryable_failure': 60},
            },
        },
        'player_mismatches': {
            'reported_mismatch_count': 9,
            'attributed_count': 9,
            'unattributed_count': 0,
            'all_attributed': True,
            'classification_counts': {'no_stored_appearance_row_for_game': 9},
        },
        'snapshot_gate': {
            'candidate_snapshot': {
                'id': 344, 'status': 'pending', 'is_published': False,
                'error_message': 'appearance_ledger_incomplete',
                'unavailable_reason': 'appearance_ledger_incomplete',
            },
            'prior_snapshot': {'id': 343, 'status': 'ready'},
            'currently_served_snapshot_id': 343,
            'publication_proof_from_incident_artifact': {
                'verified': False,
                'reason_codes': ['candidate_snapshot_not_ready'],
            },
        },
    }
    observations.update(overrides)
    return observations


# ── 115-118 The runner re-validates every workflow gate ────────────────────

def test_115_a_fully_authorized_context_passes():
    assert runner.validate_authorization(_context()) == []


@pytest.mark.parametrize('field,value,reason', [
    ('event_name', 'schedule', 'event_not_workflow_dispatch'),
    ('repository', 'someone/else', 'repository_not_authorized'),
    ('actor', 'someone-else', 'actor_not_authorized'),
    ('ref', 'refs/heads/feature', 'ref_not_main'),
])
def test_116_each_workflow_gate_is_re_validated_in_code(field, value, reason):
    assert reason in runner.validate_authorization(_context(**{field: value}))


@pytest.mark.parametrize('expected,actual,reason', [
    ('nope', VALID_SHA, 'expected_head_sha_malformed'),
    (VALID_SHA, 'b' * 40, 'expected_head_sha_mismatch'),
    (VALID_SHA, '', 'expected_head_sha_mismatch'),
])
def test_117_the_head_sha_must_match_the_resolved_commit(
    expected, actual, reason,
):
    failures = runner.validate_authorization(
        _context(expected_head_sha=expected, github_sha=actual)
    )
    assert reason in failures


def test_118_a_wrong_confirmation_is_refused():
    failures = runner.validate_authorization(
        _context(confirmation='AUDIT_SOMETHING_ELSE')
    )
    assert 'confirmation_mismatch' in failures


# ── 119-122 Questions and classification ───────────────────────────────────

def test_119_eight_questions_are_built_in_the_declared_order():
    questions = runner.build_questions(_observations())
    assert [entry['question_id'] for entry in questions] == list(
        audit.QUESTION_IDS
    )


def test_120_an_unobserved_official_record_leaves_question_one_unanswered():
    observations = _observations(official_status={
        'game_found_in_source': False, 'source_calls_refused': True,
    })
    questions = {
        entry['question_id']: entry
        for entry in runner.build_questions(observations)
    }
    first = questions[audit.QUESTION_OFFICIAL_STATUS]
    assert first['answered'] is False
    assert first['unproven_reason'] == 'official_record_not_observed'


def test_121_an_unreconciled_game_count_leaves_question_seven_unanswered():
    observations = _observations()
    observations['completeness']['unresolved_attribution'].update({
        'reconciles_with_authority': False,
    })
    questions = {
        entry['question_id']: entry
        for entry in runner.build_questions(observations)
    }
    seventh = questions[audit.QUESTION_UNRESOLVED_GAME_CLASSIFICATION]
    assert seventh['answered'] is False
    assert seventh['unproven_reason'] == (
        'unresolved_game_classification_incomplete'
    )


def test_122_classification_names_only_what_an_authority_reported():
    found = runner.classify(_observations())
    assert audit.CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE in (
        found
    )
    assert audit.CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER in found
    assert audit.CLASSIFICATION_APPEARANCE_ROWS_MISSING_FOR_FINAL_GAME in found
    assert audit.CLASSIFICATION_POSTGAME_MARKER_MISSING in found
    assert (
        audit.CLASSIFICATION_SNAPSHOT_WITHHELD_BY_APPEARANCE_LEDGER_GATE in found
    )
    assert audit.CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING in found
    assert set(found) <= set(audit.CLASSIFICATION_PRECEDENCE)


# ── 123-126 The evidence document ──────────────────────────────────────────

def test_123_a_refusal_still_produces_a_complete_document(tmp_path):
    document = runner.build_document(
        context=_context(confirmation='WRONG'),
        note='', observations={}, questions=[], read_only={},
        artifact_ingestion={},
        budget_state=audit.SourceCallBudget().state(),
        decision=runner._refuse(failed=['confirmation_mismatch']),
    )
    for key in (
        'identity', 'incident', 'request', 'evidence_artifacts',
        'source_call_budget', 'read_only_proof', 'observations',
        'questions', 'root_cause', 'verdict',
    ):
        assert key in document
    assert document['verdict']['result'] == audit.RESULT_FAILED
    assert document['verdict']['exit_code'] == 1
    assert document['incident']['workflow_run_id'] == audit.INCIDENT_RUN_ID


def test_124_the_document_renders_to_markdown_and_metadata(tmp_path):
    observations = _observations()
    questions = runner.build_questions(observations)
    proof = {
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        **audit.EXPECTED_PROBE_EVIDENCE,
    }
    decision = audit.decide(
        questions=questions,
        classifications=runner.classify(observations),
        read_only_proof=proof,
        artifact_ingestion={
            'missing_required': [], 'unreadable_required': [],
            'missing_optional': [audit.ARTIFACT_SHADOW_HANDOFF],
            'all_required_present': True,
        },
        budget_state=audit.SourceCallBudget().state(),
    )
    document = runner.build_document(
        context=_context(), note='note', observations=observations,
        questions=questions, read_only=proof,
        artifact_ingestion={
            'expectations': audit.artifact_expectations(),
            'artifacts': {},
            'missing_required': [], 'unreadable_required': [],
            'missing_optional': [audit.ARTIFACT_SHADOW_HANDOFF],
            'all_required_present': True,
        },
        budget_state=audit.SourceCallBudget().state(),
        decision=decision,
    )
    metadata = runner.write_artifacts(document, tmp_path)

    assert (tmp_path / runner.SUMMARY_JSON).exists()
    assert (tmp_path / runner.SUMMARY_MARKDOWN).exists()
    assert (tmp_path / runner.METADATA_JSON).exists()
    assert metadata['incident_run_id'] == audit.INCIDENT_RUN_ID
    assert metadata['result'] == audit.RESULT_ROOT_CAUSE_IDENTIFIED
    assert metadata['non_authorization_statement'] == (
        audit.NON_AUTHORIZATION_STATEMENT
    )

    rendered = (tmp_path / runner.SUMMARY_MARKDOWN).read_text(encoding='utf-8')
    assert audit.NON_AUTHORIZATION_STATEMENT in rendered
    assert 'Write accounting' in rendered
    assert audit.ARTIFACT_SHADOW_HANDOFF in rendered


def test_125_the_document_never_claims_a_repair_or_a_publication(tmp_path):
    document = runner.build_document(
        context=_context(), note='', observations=_observations(),
        questions=runner.build_questions(_observations()),
        read_only={}, artifact_ingestion={},
        budget_state=audit.SourceCallBudget().state(),
        decision=runner._refuse(unproven=['audit_execution_error']),
    )
    rendered = json.dumps(document, default=str).lower() + runner.render_markdown(
        document
    ).lower()
    for phrase in (
        'snapshot 344 was published', 'snapshot published',
        'marked ready', 'game repaired', 'backfill enabled',
        'authoritative mode enabled', 'incident is fixed',
    ):
        assert phrase not in rendered


def test_126_the_written_artifact_carries_no_forbidden_content(tmp_path):
    import scripts.scan_forbidden_artifact_content as scanner

    document = runner.build_document(
        context=_context(), note='operator note', observations=_observations(),
        questions=runner.build_questions(_observations()),
        read_only={
            'advisory_guard_acquired': True,
            'transaction_read_only_enabled': True,
            'fingerprints_match': True,
            **audit.EXPECTED_PROBE_EVIDENCE,
        },
        artifact_ingestion={
            'expectations': audit.artifact_expectations(), 'artifacts': {},
            'missing_required': [], 'unreadable_required': [],
            'missing_optional': [], 'all_required_present': True,
        },
        budget_state=audit.SourceCallBudget().state(),
        decision=runner._refuse(unproven=['audit_execution_error']),
    )
    runner.write_artifacts(document, tmp_path)
    assert scanner.main(['--directory', str(tmp_path)]) == scanner.EXIT_SAFE
