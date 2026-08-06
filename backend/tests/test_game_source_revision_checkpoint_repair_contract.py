"""Game 824487 source-revision checkpoint repair — package contract.

The reviewed workflow source is the authority for how this package can be
invoked; the reducer is the authority for what its outcome means. These tests
own the properties that keep it manual-only, exact-scope, two-operation, and
incapable of reaching a success result from evidence it did not observe.

They also own the negative space: the permitted changed-column set, the
prohibited-mutation manifest, the absence of any widening permission on the
workflow, and the absence of any external attribution in the package's own
source.
"""

import re
from pathlib import Path

import pytest
import yaml

from services import game_source_revision_audit as audit
from services import game_source_revision_checkpoint_repair as repair


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT
    / '.github/workflows'
    / 'manual-game-824487-source-revision-checkpoint-repair.yml'
)
SERVICE_PATH = (
    REPO_ROOT / 'backend/services/game_source_revision_checkpoint_repair.py'
)
RUNNER_PATH = (
    REPO_ROOT
    / 'backend/scripts/run_game_source_revision_checkpoint_repair.py'
)
DOC_PATH = (
    REPO_ROOT
    / 'docs/current/GAME_824487_SOURCE_REVISION_CHECKPOINT_REPAIR.md'
)

JOB = 'source-revision-checkpoint-repair'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'

# PyYAML parses the unquoted `on:` key as the boolean True. The reviewed source
# is the authority, so the key is read as YAML actually produces it rather than
# the workflow being rewritten to make a test convenient.
ON = True

EXPRESSION = re.compile(r'\$\{\{')


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def job(workflow):
    return workflow['jobs'][JOB]


@pytest.fixture(scope='module')
def steps(job):
    return job['steps']


def _step(steps, needle):
    for step in steps:
        if needle.lower() in str(step.get('name', '')).lower():
            return step
    raise AssertionError(f'no step matching {needle!r}')


# ── 1. The exact governed scope, as reviewed literals ───────────────────────

def test_the_governed_scope_is_exactly_one_game_one_table_one_column():
    assert repair.GAME_PK == 824487
    assert repair.REPRESENTED_DATE.isoformat() == '2026-07-29'
    assert repair.TARGET_TABLE == 'game_ingestion_work_items'
    assert repair.TARGET_IDENTITY_COLUMN == 'mlb_game_pk'
    assert repair.TARGET_COLUMN == 'source_revision'


def test_the_two_revisions_are_the_reviewed_literals_and_they_differ():
    assert repair.EXPECTED_EXISTING_SOURCE_REVISION == (
        '90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0'
    )
    assert repair.INTENDED_SOURCE_REVISION == (
        'a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4'
    )
    assert repair.EXPECTED_EXISTING_SOURCE_REVISION != (
        repair.INTENDED_SOURCE_REVISION
    )
    # Both are the audit's own observed values, not values this package
    # invented for itself.
    assert repair.EXPECTED_EXISTING_SOURCE_REVISION == (
        audit.PRIOR_SOURCE_REVISION
    )
    assert repair.INTENDED_SOURCE_REVISION == audit.LATER_SOURCE_REVISION


def test_the_target_column_is_a_real_column_on_the_real_model():
    from models.game_ingestion_work_item import GameIngestionWorkItem

    columns = {
        column.key for column in GameIngestionWorkItem.__table__.columns
    }
    assert repair.TARGET_COLUMN in columns
    assert repair.TARGET_IDENTITY_COLUMN in columns
    assert GameIngestionWorkItem.__tablename__ == repair.TARGET_TABLE


def test_the_identity_column_carries_a_unique_constraint():
    """Multiple candidate rows are impossible AND still guarded."""
    from models.game_ingestion_work_item import GameIngestionWorkItem

    unique = [
        constraint
        for constraint in GameIngestionWorkItem.__table__.constraints
        if getattr(constraint, 'columns', None) is not None
        and {column.key for column in constraint.columns} == {
            repair.TARGET_IDENTITY_COLUMN
        }
    ]
    assert unique, 'mlb_game_pk must be unique'


# ── 2. The permitted changed-column set ─────────────────────────────────────

def test_the_permitted_changed_columns_are_exactly_two_and_declared():
    assert repair.PERMITTED_CHANGED_COLUMNS == {
        'source_revision', 'updated_at',
    }
    assert repair.GOVERNED_CHANGED_COLUMNS == {'source_revision'}
    assert repair.AUTOMATIC_BOOKKEEPING_COLUMNS == {'updated_at'}
    assert repair.GOVERNED_CHANGED_COLUMNS | (
        repair.AUTOMATIC_BOOKKEEPING_COLUMNS
    ) == repair.PERMITTED_CHANGED_COLUMNS


def test_updated_at_is_permitted_because_the_model_declares_onupdate():
    """The disclosure is checked against the schema, not a comment."""
    from models.game_ingestion_work_item import GameIngestionWorkItem

    column = GameIngestionWorkItem.__table__.columns['updated_at']
    assert column.onupdate is not None, (
        'updated_at is declared permitted because onupdate fires on every '
        'UPDATE. If that stopped being true, the disclosure would be wrong.'
    )


def test_the_prohibited_mutation_manifest_names_every_forbidden_action():
    for prohibited in (
        'insert_a_game_ingestion_work_item',
        'create_a_missing_checkpoint',
        'update_more_than_one_work_item',
        'update_any_other_work_item_column',
        'update_game_log',
        'update_scheduled_game',
        'update_sync_run',
        'write_correction_provenance',
        'write_or_clear_dead_letters',
        'generate_or_publish_a_snapshot',
        'change_serving_or_publication_state',
        'change_team_intelligence',
        'change_player_intelligence',
        'change_ingestion_mode',
        'change_publication_authority',
        'trigger_sync_backfill_or_replay',
        'rerun_a_historical_workflow',
        'modify_source_data',
        'modify_a_canonical_appearance_row',
        'run_a_migration_or_schema_change',
        'weaken_a_validator',
    ):
        assert prohibited in repair.PROHIBITED_MUTATIONS


# ── 3. Operations and confirmations ─────────────────────────────────────────

def test_the_operation_vocabulary_is_closed_at_two():
    assert repair.OPERATIONS == ('verify', 'apply')


def test_each_operation_carries_its_own_distinct_confirmation_phrase():
    assert set(repair.CONFIRMATIONS) == set(repair.OPERATIONS)
    phrases = set(repair.CONFIRMATIONS.values())
    assert len(phrases) == len(repair.OPERATIONS)
    assert repair.CONFIRMATIONS['verify'] != repair.CONFIRMATIONS['apply']
    assert repair.CONFIRMATIONS['apply'].startswith('APPLY_')
    assert repair.CONFIRMATIONS['verify'].startswith('VERIFY_')


# ── 4. Results and exit codes ───────────────────────────────────────────────

def test_the_exit_code_contract_is_exactly_three_codes():
    """Exit 0 only when the repair is eligible, applied, or already applied."""
    assert set(repair.EXIT_CODES) == set(repair.RESULTS)
    assert repair.EXIT_CODES[repair.RESULT_APPLIED] == 0
    assert repair.EXIT_CODES[repair.RESULT_NOT_REQUIRED] == 0
    assert repair.EXIT_CODES[repair.RESULT_VERIFIED_REQUIRED_AND_SAFE] == 0
    assert repair.EXIT_CODES[repair.RESULT_FAILED] == 1
    assert repair.EXIT_CODES[repair.RESULT_UNPROVEN] == 2
    # A refused run is not eligible, so it must not be distinguishable from
    # UNPROVEN by exit status: anything reading only the exit code must treat
    # both identically, which is to say "do not proceed".
    assert repair.EXIT_CODES[repair.RESULT_REFUSED] == 2
    assert sorted(set(repair.EXIT_CODES.values())) == [0, 1, 2]


def test_a_refusal_is_still_distinguishable_where_a_reviewer_reads_it():
    """The exit code is flattened; the result name and reasons are not."""
    checks = [
        repair.precondition(
            identifier, requirement='r',
            state=(
                repair.PRECONDITION_VIOLATED
                if identifier == repair.PRE_CURRENT_REVISION
                else repair.PRECONDITION_SATISFIED
            ),
        )
        for identifier in repair.PRECONDITION_IDS
    ]
    refused = repair.decide(
        operation='apply', preconditions={'preconditions': checks},
    )
    unproven = repair.decide(operation='apply')
    assert refused['exit_code'] == unproven['exit_code'] == 2
    assert refused['result'] != unproven['result']
    assert refused['refusal_reasons'] and not refused['unproven_reasons']
    assert unproven['unproven_reasons'] and not unproven['refusal_reasons']


def test_failed_is_reserved_for_this_packages_own_contract_violations():
    """No platform-shaped condition may reach the FAILED family."""
    platform_shaped = {
        repair.REFUSED_WORK_ITEM_MISSING,
        repair.REFUSED_EXISTING_REVISION_UNEXPECTED,
        repair.REFUSED_GOVERNED_FIELD_DIFFERS,
        repair.REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
        repair.REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    }
    assert not platform_shaped & set(repair.FAILED_REASONS)


def test_the_three_reason_families_do_not_overlap():
    families = (
        set(repair.FAILED_REASONS),
        set(repair.UNPROVEN_REASONS),
        set(repair.REFUSED_REASONS),
    )
    for index, left in enumerate(families):
        for right in families[index + 1:]:
            assert not left & right


def test_every_specified_condition_maps_to_a_code_this_package_emits():
    """Traceability to the governing specification, checked not claimed."""
    for condition, code in repair.SPECIFIED_REASON_CODES.items():
        assert code in repair.ALL_REASON_CODES, condition


def test_the_specification_map_covers_every_named_condition():
    for condition in (
        'unauthorized_invocation', 'expected_main_sha_mismatch',
        'target_work_item_missing', 'target_work_item_ambiguous',
        'target_status_unexpected', 'target_checkpoint_missing',
        'target_checkpoint_malformed', 'target_checkpoint_unexpected',
        'repair_already_applied', 'current_source_unavailable',
        'current_source_empty', 'current_source_count_unexpected',
        'current_source_revision_unexpected', 'official_membership_mismatch',
        'duplicate_official_identity', 'duplicate_stored_identity',
        'stored_appearance_count_unexpected', 'reconciliation_plan_changed',
        'reconciliation_proposes_insert', 'reconciliation_proposes_update',
        'reconciliation_proposes_delete', 'reconciliation_has_blocked_rows',
        'governed_field_difference_detected', 'advisory_lock_unavailable',
        'advisory_lock_release_failed', 'transaction_read_only_proof_failed',
        'mutation_row_count_zero', 'mutation_row_count_multiple',
        'concurrent_precondition_change', 'prohibited_scope_changed',
        'post_commit_verification_failed', 'artifact_generation_failed',
    ):
        assert condition in repair.SPECIFIED_REASON_CODES, condition


def test_zero_and_multiple_affected_rows_are_different_outcomes():
    """Zero is a concurrency refusal; more than one is a contract violation."""
    assert repair.REFUSED_MUTATION_ROW_COUNT_ZERO in repair.REFUSED_REASONS
    assert repair.FAILED_MUTATION_ROW_COUNT_MULTIPLE in repair.FAILED_REASONS
    assert repair.REFUSED_MUTATION_ROW_COUNT_ZERO != (
        repair.FAILED_MUTATION_ROW_COUNT_MULTIPLE
    )


def test_an_artifact_that_cannot_be_written_is_a_contract_violation(
    monkeypatch, tmp_path,
):
    """A run whose evidence could not be written is not a successful run."""
    from scripts import run_game_source_revision_checkpoint_repair as runner

    monkeypatch.setattr(
        runner, 'run',
        lambda args: {'verdict': repair.decide(operation='verify')},
    )

    def _explode(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(runner, 'write_artifacts', _explode)
    code = runner.main([
        '--operation', 'verify',
        '--expected-main-sha', 'f' * 40,
        '--confirmation', repair.CONFIRMATIONS['verify'],
        '--artifact-dir', str(tmp_path / 'out'),
    ])
    assert code == repair.EXIT_CODES[repair.RESULT_FAILED] == 1


# ── 5. Precondition model ───────────────────────────────────────────────────

def test_every_precondition_id_maps_to_both_a_refusal_and_an_unproven_reason():
    assert set(repair.PRECONDITION_REFUSAL_REASONS) == set(
        repair.PRECONDITION_IDS
    )
    assert set(repair.PRECONDITION_UNPROVEN_REASONS) == set(
        repair.PRECONDITION_IDS
    )


def test_precondition_refusal_reasons_are_all_declared_refusal_codes():
    for reason in repair.PRECONDITION_REFUSAL_REASONS.values():
        assert reason in repair.REFUSED_REASONS


def test_precondition_unproven_reasons_are_all_declared_unproven_codes():
    for reason in repair.PRECONDITION_UNPROVEN_REASONS.values():
        assert reason in repair.UNPROVEN_REASONS


def test_a_refusal_reason_and_an_unproven_reason_are_never_the_same_code():
    """"Observed to be wrong" and "never observed" must never share a code."""
    for identifier in repair.PRECONDITION_IDS:
        assert repair.PRECONDITION_REFUSAL_REASONS[identifier] != (
            repair.PRECONDITION_UNPROVEN_REASONS[identifier]
        )


def test_precondition_state_is_three_way_never_boolean():
    assert repair.PRECONDITION_STATES == (
        'satisfied', 'violated', 'not_observed',
    )


def test_an_unobserved_precondition_is_never_satisfied_by_a_true_comparison():
    check = repair.precondition(
        repair.PRE_ROW_EXISTS, requirement='x',
        state=repair._state(False, satisfied=True),
    )
    assert check['state'] == repair.PRECONDITION_NOT_OBSERVED
    assert check['satisfied'] is False
    assert check['unproven_reason'] is not None
    assert check['refusal_reason'] is None


def test_an_unrecognised_state_degrades_to_not_observed_never_to_satisfied():
    check = repair.precondition(
        repair.PRE_ROW_EXISTS, requirement='x', state='probably_fine',
    )
    assert check['state'] == repair.PRECONDITION_NOT_OBSERVED
    assert check['satisfied'] is False


# ── 6. The completion gate ──────────────────────────────────────────────────

def _satisfied_evaluation(overrides=None):
    """A fully-covered evaluation, so a test can move exactly one thing."""
    overrides = overrides or {}
    checks = [
        repair.precondition(
            identifier, requirement='r',
            state=overrides.get(identifier, repair.PRECONDITION_SATISFIED),
        )
        for identifier in repair.PRECONDITION_IDS
    ]
    return {'preconditions': checks}


def _proven_post_commit(overrides=None):
    """A post-commit lifecycle where every step was positively established."""
    lifecycle = {
        field: True for field, _ in repair.POST_COMMIT_PROOF_SEQUENCE
    }
    lifecycle.update(overrides or {})
    return lifecycle


def test_an_empty_evaluation_can_never_reach_a_success_result():
    for operation in repair.OPERATIONS:
        decision = repair.decide(operation=operation)
        assert decision['result'] == repair.RESULT_UNPROVEN
        assert repair.UNPROVEN_PRECONDITION_NOT_OBSERVED in (
            decision['unproven_reasons']
        )


def test_a_partial_evaluation_can_never_reach_a_success_result():
    partial = {'preconditions': [
        repair.precondition(
            repair.PRE_ROW_EXISTS, requirement='r',
            state=repair.PRECONDITION_SATISFIED,
        )
    ]}
    decision = repair.decide(operation='verify', preconditions=partial)
    assert decision['result'] == repair.RESULT_UNPROVEN
    assert decision['precondition_coverage']['coverage_complete'] is False
    assert decision['precondition_coverage']['missing_ids']


def test_a_malformed_evaluation_object_can_never_reach_a_success_result():
    for malformed in ({}, {'preconditions': None}, {'preconditions': 'yes'},
                      {'preconditions': [1, 2, 3]},
                      {'preconditions': {}, 'all_satisfied': True}):
        decision = repair.decide(operation='verify', preconditions=malformed)
        assert decision['result'] == repair.RESULT_UNPROVEN


def test_a_forged_all_satisfied_flag_cannot_override_the_evaluated_checks():
    """The reducer reads the evidence, not the summary claim about it."""
    forged = _satisfied_evaluation({
        repair.PRE_CURRENT_REVISION: repair.PRECONDITION_VIOLATED,
    })
    forged['all_satisfied'] = True
    forged['refusal_reasons'] = []
    decision = repair.decide(operation='verify', preconditions=forged)
    assert decision['result'] == repair.RESULT_REFUSED
    assert repair.REFUSED_CURRENT_REVISION_NOT_INTENDED in (
        decision['refusal_reasons']
    )
    assert decision['preconditions_all_satisfied'] is False


def test_a_fully_satisfied_verify_evaluation_reaches_the_verified_result():
    decision = repair.decide(
        operation='verify', preconditions=_satisfied_evaluation(),
    )
    assert decision['result'] == repair.RESULT_VERIFIED_REQUIRED_AND_SAFE
    assert decision['exit_code'] == 0
    assert decision['mutation_performed'] is False


def test_a_verify_run_never_reports_a_mutation():
    decision = repair.decide(
        operation='verify', preconditions=_satisfied_evaluation(),
    )
    assert decision['mutation_performed'] is False
    assert decision['apply_attempted'] is False


# ── 7. Reducer precedence ───────────────────────────────────────────────────

def test_failed_outranks_everything_including_a_committed_apply():
    decision = repair.decide(
        operation='apply', preconditions=_satisfied_evaluation(),
        failed_reasons=[repair.FAILED_MUTATION_SCOPE_EXCEEDED],
        apply_attempted=True, apply_committed=True,
    )
    assert decision['result'] == repair.RESULT_FAILED
    # The verdict is FAILED, and the commit still happened. Reporting
    # mutation_performed False here would under-report a durable production
    # change in the most safety-critical field of the verdict.
    assert decision['mutation_performed'] is True
    assert decision['apply_committed'] is True


def test_mutation_performed_reports_the_commit_not_the_verdict():
    for reasons, expected in (
        ({'failed_reasons': [repair.FAILED_MUTATION_SCOPE_EXCEEDED]},
         repair.RESULT_FAILED),
        ({'unproven_reasons': [repair.UNPROVEN_READ_ONLY_UNAVAILABLE]},
         repair.RESULT_UNPROVEN),
    ):
        decision = repair.decide(
            operation='apply', preconditions=_satisfied_evaluation(),
            apply_attempted=True, apply_committed=True,
            post_commit=_proven_post_commit(), **reasons,
        )
        assert decision['result'] == expected
        assert decision['mutation_performed'] is True

    # No commit means no mutation, whatever else happened.
    for committed in (None, False):
        decision = repair.decide(
            operation='apply', preconditions=_satisfied_evaluation(),
            apply_attempted=True, apply_committed=committed,
        )
        assert decision['mutation_performed'] is False


def test_unproven_outranks_refused_and_success():
    decision = repair.decide(
        operation='verify', preconditions=_satisfied_evaluation(),
        unproven_reasons=[repair.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE],
        refusal_reasons=[repair.REFUSED_WORK_ITEM_MISSING],
    )
    assert decision['result'] == repair.RESULT_UNPROVEN


def _already_applied(extra=None):
    """The precondition shape a row already at the intended value produces.

    PRE_EXISTING_REVISION is violated too, and unavoidably so: the two
    governed revisions differ by contract, so a row holding the intended value
    cannot also hold the expected old value.
    """
    states = {
        identifier: repair.PRECONDITION_VIOLATED
        for identifier in repair.ALREADY_APPLIED_TOLERATED_VIOLATIONS
    }
    if extra:
        states[extra] = repair.PRECONDITION_VIOLATED
    return _satisfied_evaluation(states)


def test_the_tolerated_already_applied_violations_are_exactly_two():
    assert repair.ALREADY_APPLIED_TOLERATED_VIOLATIONS == {
        repair.PRE_INTENDED_DIFFERS, repair.PRE_EXISTING_REVISION,
    }


def test_a_clean_already_applied_state_is_not_required_not_refused():
    evaluation = _already_applied()
    assert repair.precondition_coverage(evaluation)[
        'already_applied_is_clean'
    ] is True
    for operation in repair.OPERATIONS:
        decision = repair.decide(operation=operation, preconditions=evaluation)
        assert decision['result'] == repair.RESULT_NOT_REQUIRED
        assert decision['exit_code'] == 0
        assert decision['mutation_performed'] is False
        # A clean no-op carries no refusal reasons at all.
        assert decision['refusal_reasons'] == []


@pytest.mark.parametrize('extra', [
    identifier for identifier in repair.PRECONDITION_IDS
    if identifier not in (
        repair.PRE_INTENDED_DIFFERS, repair.PRE_EXISTING_REVISION,
    )
])
def test_already_applied_never_masks_another_violated_precondition(extra):
    """Exit 0 must never be reachable while the surrounding state is wrong."""
    evaluation = _already_applied(extra)
    coverage = repair.precondition_coverage(evaluation)
    assert coverage['already_at_intended_revision'] is True
    assert coverage['already_applied_is_clean'] is False
    assert coverage['blocking_violations'] == [extra]

    for operation in repair.OPERATIONS:
        decision = repair.decide(operation=operation, preconditions=evaluation)
        assert decision['result'] == repair.RESULT_REFUSED, extra
        assert decision['exit_code'] == 2
        assert decision['mutation_performed'] is False
        assert repair.PRECONDITION_REFUSAL_REASONS[extra] in (
            decision['refusal_reasons']
        )


def test_already_applied_with_an_unobserved_precondition_is_unproven():
    """A no-op is not clean when part of the state was never read."""
    states = {
        identifier: repair.PRECONDITION_VIOLATED
        for identifier in repair.ALREADY_APPLIED_TOLERATED_VIOLATIONS
    }
    states[repair.PRE_CANONICAL_PLAN_CLEAN] = repair.PRECONDITION_NOT_OBSERVED
    evaluation = _satisfied_evaluation(states)
    assert repair.precondition_coverage(evaluation)[
        'already_applied_is_clean'
    ] is False
    decision = repair.decide(operation='apply', preconditions=evaluation)
    assert decision['result'] == repair.RESULT_UNPROVEN


def test_a_failed_or_unproven_reason_defeats_a_clean_already_applied_state():
    evaluation = _already_applied()
    assert repair.decide(
        operation='apply', preconditions=evaluation,
        failed_reasons=[repair.FAILED_MUTATION_SCOPE_EXCEEDED],
    )['result'] == repair.RESULT_FAILED
    assert repair.decide(
        operation='apply', preconditions=evaluation,
        unproven_reasons=[repair.UNPROVEN_READ_ONLY_UNAVAILABLE],
    )['result'] == repair.RESULT_UNPROVEN


def test_any_other_violated_precondition_refuses(  # noqa: D103
):
    for identifier in repair.PRECONDITION_IDS:
        if identifier == repair.PRE_INTENDED_DIFFERS:
            continue
        evaluation = _satisfied_evaluation({
            identifier: repair.PRECONDITION_VIOLATED,
        })
        decision = repair.decide(operation='apply', preconditions=evaluation)
        assert decision['result'] == repair.RESULT_REFUSED, identifier
        assert decision['exit_code'] == 2
        assert decision['mutation_performed'] is False
        assert repair.PRECONDITION_REFUSAL_REASONS[identifier] in (
            decision['refusal_reasons']
        )


def test_an_unexpected_third_revision_still_refuses_on_its_own():
    """Tolerance is regime-scoped, and this is the primary refusal case.

    PRE_EXISTING_REVISION is forgiven only when the row is already at the
    intended value. When it is not, the same violation means the checkpoint
    holds some third unexpected value, and it must stay blocking.
    """
    evaluation = _satisfied_evaluation({
        repair.PRE_EXISTING_REVISION: repair.PRECONDITION_VIOLATED,
    })
    coverage = repair.precondition_coverage(evaluation)
    assert coverage['already_at_intended_revision'] is False
    assert coverage['tolerated_violations'] == []
    assert coverage['blocking_violations'] == [repair.PRE_EXISTING_REVISION]

    decision = repair.decide(operation='apply', preconditions=evaluation)
    assert decision['result'] == repair.RESULT_REFUSED
    assert repair.REFUSED_EXISTING_REVISION_UNEXPECTED in (
        decision['refusal_reasons']
    )


def test_any_unobserved_precondition_is_unproven_never_refused():
    for identifier in repair.PRECONDITION_IDS:
        evaluation = _satisfied_evaluation({
            identifier: repair.PRECONDITION_NOT_OBSERVED,
        })
        decision = repair.decide(operation='apply', preconditions=evaluation)
        assert decision['result'] == repair.RESULT_UNPROVEN, identifier
        assert repair.PRECONDITION_UNPROVEN_REASONS[identifier] in (
            decision['unproven_reasons']
        )


def test_an_apply_that_never_committed_is_unproven_never_applied():
    decision = repair.decide(
        operation='apply', preconditions=_satisfied_evaluation(),
        apply_attempted=True, apply_committed=None,
    )
    assert decision['result'] == repair.RESULT_UNPROVEN
    assert repair.UNPROVEN_APPLY_OUTCOME_UNKNOWN in (
        decision['unproven_reasons']
    )
    assert decision['mutation_performed'] is False


def test_an_apply_whose_gate_never_opened_is_not_reported_as_applied():
    decision = repair.decide(
        operation='apply', preconditions=_satisfied_evaluation(),
        apply_attempted=False, apply_committed=None,
    )
    assert decision['result'] == repair.RESULT_UNPROVEN
    assert decision['mutation_performed'] is False


def test_a_committed_apply_with_a_clean_evaluation_reports_applied():
    decision = repair.decide(
        operation='apply', preconditions=_satisfied_evaluation(),
        apply_attempted=True, apply_committed=True,
        post_commit=_proven_post_commit(),
    )
    assert decision['result'] == repair.RESULT_APPLIED
    assert decision['exit_code'] == 0
    assert decision['mutation_performed'] is True


def test_an_unknown_operation_is_a_failed_contract_violation():
    decision = repair.decide(
        operation='repair-everything', preconditions=_satisfied_evaluation(),
    )
    assert decision['result'] == repair.RESULT_FAILED
    assert repair.FAILED_OPERATION_UNKNOWN in decision['failed_reasons']


def test_every_verdict_carries_the_non_authorization_statement():
    decision = repair.decide(operation='verify')
    assert 'authorizes nothing' in decision['non_authorization_statement']
    assert decision['prohibited_mutations']
    assert decision['permitted_changed_columns'] == [
        'source_revision', 'updated_at',
    ]


def test_the_dead_letter_backlog_is_never_reported_as_zero():
    decision = repair.decide(operation='verify')
    assert '1,389' in decision['dead_letter_backlog_note'] or (
        '1389' in decision['dead_letter_backlog_note']
    )


# ── 7b. The post-commit proof gate ──────────────────────────────────────────
#
# Once COMMIT returns, rollback is no longer available as a remedy. Everything
# this package can still do is evidential, so failing to produce that evidence
# is the package breaking its own contract — not merely lacking evidence about
# someone else's. These tests own that distinction and the gate enforcing it.

def _committed_apply(post_commit, **kwargs):
    return repair.decide(
        operation='apply', preconditions=_satisfied_evaluation(),
        apply_attempted=True, apply_committed=True,
        post_commit=post_commit, **kwargs,
    )


def test_the_dedicated_post_commit_reason_is_failed_not_unproven():
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF in repair.FAILED_REASONS
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF not in (
        repair.UNPROVEN_REASONS
    )
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF == (
        'post_commit_read_only_proof_failed'
    )
    # It is its own code precisely so an artifact reader can tell a
    # post-commit contract failure from ordinary pre-mutation evidence gaps.
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF not in {
        repair.UNPROVEN_READ_ONLY_UNAVAILABLE,
        repair.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
        repair.UNPROVEN_APPLY_OUTCOME_UNKNOWN,
    }


def test_a_proven_post_commit_lifecycle_leaves_repair_applied_reachable():
    decision = _committed_apply(_proven_post_commit())
    assert decision['result'] == repair.RESULT_APPLIED
    assert decision['exit_code'] == 0
    assert not decision['failed_reasons']


def test_post_commit_read_only_false_after_commit_is_failed_at_exit_one():
    decision = _committed_apply(_proven_post_commit({
        'post_commit_transaction_read_only': False,
        'post_commit_read_only_reason': 'read_only_setup_failed',
        'post_commit_verification_completed': False,
    }))
    assert decision['result'] == repair.RESULT_FAILED
    assert decision['exit_code'] == 1
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF in (
        decision['failed_reasons']
    )
    # The commit is a durable fact and survives the verdict intact.
    assert decision['apply_committed'] is True
    assert decision['mutation_performed'] is True
    assert repair.UNPROVEN_APPLY_OUTCOME_UNKNOWN not in (
        decision['unproven_reasons']
    )


def test_post_commit_read_only_never_attempted_after_commit_is_failed():
    decision = _committed_apply(_proven_post_commit({
        'post_commit_read_only_attempted': False,
    }))
    assert decision['result'] == repair.RESULT_FAILED
    assert repair.FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE in (
        decision['failed_reasons']
    )


def test_post_commit_verification_never_attempted_after_commit_is_failed():
    decision = _committed_apply(_proven_post_commit({
        'post_commit_verification_attempted': False,
    }))
    assert decision['result'] == repair.RESULT_FAILED
    assert decision['exit_code'] == 1


def test_post_commit_read_only_left_none_after_commit_is_failed():
    """Unset is not permission. None never satisfies the gate."""
    decision = _committed_apply(_proven_post_commit({
        'post_commit_transaction_read_only': None,
    }))
    assert decision['result'] == repair.RESULT_FAILED
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF in (
        decision['failed_reasons']
    )


def test_post_commit_verification_not_completed_after_commit_is_failed():
    for value in (False, None):
        decision = _committed_apply(_proven_post_commit({
            'post_commit_verification_completed': value,
        }))
        assert decision['result'] == repair.RESULT_FAILED
        assert repair.FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE in (
            decision['failed_reasons']
        )


def test_a_committed_apply_with_no_post_commit_evidence_at_all_is_failed():
    """Silence is the condition the gate exists to catch, not an exemption."""
    for absent in (None, {}):
        decision = _committed_apply(absent)
        assert decision['result'] == repair.RESULT_FAILED
        assert decision['exit_code'] == 1
        assert decision['mutation_performed'] is True


def test_every_post_commit_lifecycle_flag_is_individually_load_bearing():
    for field, _ in repair.POST_COMMIT_PROOF_SEQUENCE:
        decision = _committed_apply(_proven_post_commit({field: False}))
        assert decision['result'] == repair.RESULT_FAILED, field
        assert decision['exit_code'] == 1, field
        assert decision['apply_committed'] is True, field


def test_post_commit_proof_failure_preserves_a_failed_lock_release_reason():
    decision = _committed_apply(
        _proven_post_commit({'post_commit_transaction_read_only': False}),
        failed_reasons=[repair.FAILED_LOCK_RELEASE_FAILED],
    )
    assert decision['result'] == repair.RESULT_FAILED
    assert repair.FAILED_LOCK_RELEASE_FAILED in decision['failed_reasons']
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF in (
        decision['failed_reasons']
    )


def test_post_commit_proof_failure_composes_with_another_scope_failure():
    decision = _committed_apply(
        _proven_post_commit({
            'post_commit_transaction_read_only': False,
            'post_commit_verification_completed': False,
        }),
        failed_reasons=[repair.FAILED_MUTATION_SCOPE_EXCEEDED],
    )
    assert decision['result'] == repair.RESULT_FAILED
    for reason in (
        repair.FAILED_MUTATION_SCOPE_EXCEEDED,
        repair.FAILED_POST_COMMIT_READ_ONLY_PROOF,
    ):
        assert reason in decision['failed_reasons']
    assert decision['mutation_performed'] is True


def test_repair_applied_is_unreachable_without_the_full_lifecycle():
    """Exhaustive over the gate's own inputs, so no combination sneaks past."""
    import itertools

    fields = [field for field, _ in repair.POST_COMMIT_PROOF_SEQUENCE]
    for combination in itertools.product((True, False, None), repeat=len(
        fields
    )):
        lifecycle = dict(zip(fields, combination))
        decision = _committed_apply(lifecycle)
        if all(value is True for value in combination):
            assert decision['result'] == repair.RESULT_APPLIED, lifecycle
        else:
            assert decision['result'] == repair.RESULT_FAILED, lifecycle
            assert decision['exit_code'] == 1, lifecycle


def test_the_post_commit_gate_does_not_touch_uncommitted_or_verify_runs():
    """The gate is about protecting a landed commit, and nothing else."""
    verify = repair.decide(
        operation='verify', preconditions=_satisfied_evaluation(),
    )
    assert verify['result'] == repair.RESULT_VERIFIED_REQUIRED_AND_SAFE

    for committed in (None, False):
        decision = repair.decide(
            operation='apply', preconditions=_satisfied_evaluation(),
            apply_attempted=True, apply_committed=committed,
        )
        assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF not in (
            decision['failed_reasons']
        )
        assert repair.FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE not in (
            decision['failed_reasons']
        )


# ── 8. Advisory-lock lifecycle ──────────────────────────────────────────────

def test_a_lock_that_was_never_acquired_is_unproven():
    lifecycle = repair.lock_lifecycle({'acquire_attempted': True})
    assert repair.UNPROVEN_ADVISORY_LOCK_UNAVAILABLE in (
        lifecycle['unproven_reasons']
    )


def test_a_lock_whose_release_raised_is_a_contract_violation():
    lifecycle = repair.lock_lifecycle({
        'acquire_attempted': True, 'guard_acquired': True,
        'guard_release_attempted': True, 'guard_released': False,
    })
    assert repair.FAILED_LOCK_RELEASE_FAILED in lifecycle['failed_reasons']


def test_a_lock_that_was_never_released_is_a_contract_violation():
    lifecycle = repair.lock_lifecycle({
        'acquire_attempted': True, 'guard_acquired': True,
    })
    assert repair.FAILED_LOCK_RELEASE_NOT_ATTEMPTED in (
        lifecycle['failed_reasons']
    )


def test_a_release_whose_outcome_was_never_established_is_unproven():
    lifecycle = repair.lock_lifecycle({
        'acquire_attempted': True, 'guard_acquired': True,
        'guard_release_attempted': True, 'guard_released': None,
    })
    assert repair.UNPROVEN_LOCK_RELEASE_UNKNOWN in (
        lifecycle['unproven_reasons']
    )


def test_a_clean_lifecycle_contributes_nothing():
    lifecycle = repair.lock_lifecycle({
        'acquire_attempted': True, 'guard_acquired': True,
        'guard_release_attempted': True, 'guard_released': True,
    })
    assert lifecycle['failed_reasons'] == []
    assert lifecycle['unproven_reasons'] == []
    assert lifecycle['lifecycle_complete'] is True


# ── 9. Workflow: invocation ─────────────────────────────────────────────────

def test_the_workflow_is_manual_dispatch_only(workflow):
    assert set(workflow[ON]) == {'workflow_dispatch'}


def test_the_workflow_exposes_exactly_four_inputs_and_no_governed_value(
    workflow,
):
    inputs = workflow[ON]['workflow_dispatch']['inputs']
    assert set(inputs) == {
        'operation', 'expected_main_sha', 'confirmation', 'operator_note',
    }
    # Neither revision, the game, the table, nor the column is selectable.
    serialized = str(inputs)
    assert repair.EXPECTED_EXISTING_SOURCE_REVISION not in serialized
    assert repair.INTENDED_SOURCE_REVISION not in serialized
    assert 'game_pk' not in serialized
    assert 'table' not in serialized


def test_the_operation_input_is_a_closed_choice_of_exactly_two(workflow):
    operation = workflow[ON]['workflow_dispatch']['inputs']['operation']
    assert operation['type'] == 'choice'
    assert operation['options'] == ['verify', 'apply']
    assert operation['default'] == 'verify'


def test_the_workflow_grants_only_contents_read(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_the_workflow_adds_no_widening_permission(workflow_text):
    for forbidden in (
        'actions: write', 'contents: write', 'pull-requests: write',
        'deployments: write', 'id-token:', 'packages: write',
        'issues: write', 'security-events: write',
    ):
        assert forbidden not in workflow_text


def test_the_workflow_shares_the_production_sync_concurrency_group(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_the_job_refuses_a_wrong_repository_ref_or_actor(job):
    condition = job['if']
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_authorization_is_the_first_step_before_checkout(steps):
    assert 'refuse an unauthorized invocation' in steps[0]['name'].lower()
    assert 'uses' not in steps[0]
    checkout = next(
        index for index, step in enumerate(steps)
        if str(step.get('uses', '')).startswith('actions/checkout')
    )
    assert checkout > 0


def test_no_run_script_interpolates_a_github_expression(steps):
    """The shell boundary: operator input crosses through env: only."""
    for step in steps:
        script = step.get('run')
        if script:
            assert not EXPRESSION.search(script), step.get('name')


def test_both_confirmation_phrases_are_enforced_in_the_preflight(
    workflow_text,
):
    assert repair.CONFIRMATIONS['verify'] in workflow_text
    assert repair.CONFIRMATIONS['apply'] in workflow_text
    preflight = workflow_text.split('Check out the reviewed commit')[0]
    assert repair.CONFIRMATIONS['verify'] in preflight
    assert repair.CONFIRMATIONS['apply'] in preflight
    assert 'operation must be exactly verify or apply' in preflight


def test_the_preflight_refuses_before_any_secret_is_used(steps):
    script = steps[0]['run']
    for secret in ('DATABASE_URL', 'SECRET_KEY', 'ADMIN_TOKEN'):
        assert f'SECRET_{secret.replace("SECRET_", "")}' in script or (
            secret in script
        )
    assert 'exit 1' in script


# ── 10. Workflow: what it can never do ──────────────────────────────────────

def test_the_workflow_dispatches_nothing_and_publishes_nothing(workflow_text):
    # Comment lines are stripped first. The workflow deliberately NAMES the
    # things it does not do — "No BASEBALLOS_SYNC_URL and no publication
    # token" — and a scan that could not tell a prohibition from a use would
    # force that documentation out of the file.
    executable = '\n'.join(
        line for line in workflow_text.splitlines()
        if not line.lstrip().startswith('#')
    )
    workflow_text = executable
    for forbidden in (
        'workflow_dispatch --ref', 'gh workflow run', 'gh api', 'gh pr merge',
        'auto-merge', 'BASEBALLOS_SYNC_URL', 'PUBLICATION_TOKEN',
        'flask db upgrade', 'alembic', 'curl ', 'schedule:',
        'repository_dispatch', 'run_daily_sync', 'run_backfill',
    ):
        assert forbidden not in workflow_text, forbidden


def test_the_workflow_scans_before_it_uploads(steps):
    names = [str(step.get('name', '')).lower() for step in steps]
    assert names.index('scan the evidence artifact') < (
        names.index('upload the evidence artifact')
    )
    upload = _step(steps, 'upload the evidence artifact')
    assert upload['if'] == "${{ steps.scan.outcome == 'success' }}"


def test_the_final_gate_preserves_every_non_zero_result(steps):
    gate = _step(steps, 'final repair gate')
    assert 'continue-on-error' not in gate
    script = gate['run']
    # Exactly the three codes the package can return, and no branch for a
    # code it cannot.
    for code in ('1', '2'):
        assert f'= "{code}"' in script
    assert '= "3"' not in script
    assert 'FAILED' in script
    assert 'UNPROVEN' in script
    assert 'REPAIR_REFUSED' in script
    assert 'NOT ELIGIBLE' in script


def test_the_final_gate_restates_what_the_run_did_not_do(steps):
    script = _step(steps, 'final repair gate')['run']
    for phrase in (
        'created no work item', 'created no checkpoint',
        'updated no other', 'published nothing',
    ):
        assert phrase in script


def test_the_runner_is_invoked_with_the_operation_and_confirmation(steps):
    script = _step(steps, 'run the checkpoint repair')['run']
    assert 'run_game_source_revision_checkpoint_repair.py' in script
    assert '--operation "$INPUT_OPERATION"' in script
    assert '--confirmation "$INPUT_CONFIRMATION"' in script
    assert '--expected-main-sha "$INPUT_EXPECTED_MAIN_SHA"' in script


# ── 11. Package hygiene ─────────────────────────────────────────────────────

FORBIDDEN_ATTRIBUTION = (
    'claude', 'anthropic', 'copilot', 'chatgpt', 'openai', 'gpt-',
    'generated by', 'generated with', 'co-authored-by', 'assisted by',
    'ai-generated', 'llm', 'gemini',
)


@pytest.mark.parametrize('path', [
    SERVICE_PATH, RUNNER_PATH, WORKFLOW_PATH, DOC_PATH,
])
def test_the_package_carries_no_external_attribution(path):
    text = path.read_text(encoding='utf-8').lower()
    for needle in FORBIDDEN_ATTRIBUTION:
        assert needle not in text, f'{path.name} contains {needle!r}'


def test_the_package_never_serializes_exception_text():
    """Safe summaries only: a closed reason code, never a caught message."""
    for path in (SERVICE_PATH, RUNNER_PATH):
        source = path.read_text(encoding='utf-8')
        for forbidden in (
            'str(exc', 'str(error', 'repr(exc', 'traceback.format',
            '.args[0]', "'message': str(",
        ):
            assert forbidden not in source, f'{path.name}: {forbidden}'


def test_the_package_issues_no_delete_or_insert_statement():
    for path in (SERVICE_PATH, RUNNER_PATH):
        source = path.read_text(encoding='utf-8')
        for forbidden in (
            'session.delete(', 'session.add(', 'session.add_all(',
            'DELETE FROM', 'INSERT INTO', 'TRUNCATE TABLE', 'DROP TABLE',
            'ALTER TABLE', 'session.bulk_',
        ):
            assert forbidden not in source, f'{path.name}: {forbidden}'


def test_the_only_orm_write_is_the_single_governed_column():
    source = RUNNER_PATH.read_text(encoding='utf-8')
    assert source.count('setattr(row, repair.TARGET_COLUMN,') == 1
    assert source.count('db.session.commit()') == 1


def _called_names(path):
    """Every callable name invoked in a module, from the AST.

    Prose-immune on purpose. The package's own comments and documentation
    name the things it must never do — "triggers no sync, backfill, or
    replay" — and a scan that could not tell a prohibition from a call would
    force that documentation out of the file.
    """
    import ast

    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        while isinstance(target, ast.Attribute):
            names.add(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


def test_no_bulk_or_unguarded_update_call_exists_anywhere_in_the_package():
    """The shape of the write, proven statically as well as at runtime."""
    for path in (SERVICE_PATH, RUNNER_PATH):
        called = _called_names(path)
        # ``insert`` is deliberately absent from this list: it is the name
        # of ``sys.path.insert``, and a scan that flagged that would have to
        # be silenced rather than believed. The session-level writes are
        # what matter, and they are all named here.
        for forbidden in (
            'update', 'bulk_update_mappings', 'bulk_save_objects',
            'bulk_insert_mappings', 'execute_values', 'delete', 'add',
            'add_all', 'merge', 'expunge',
        ):
            assert forbidden not in called, f'{path.name}: {forbidden}()'


def test_no_workflow_dispatch_backfill_replay_or_publication_call_exists():
    for path in (SERVICE_PATH, RUNNER_PATH):
        called = _called_names(path)
        for forbidden in (
            'run_game_driven_ingestion', 'run_daily_sync', 'run_backfill',
            'replay_game', 'publish_snapshot', 'generate_snapshot',
            'select_snapshot', 'dispatch_workflow', 'post', 'urlopen',
            'set_mode', 'set_authority', 'create_sync_run',
            'acquire_sync_writer_guard',
        ):
            assert forbidden not in called, f'{path.name}: {forbidden}()'


def test_the_only_lock_this_package_takes_is_the_acquire_only_read_lock():
    runner_called = _called_names(RUNNER_PATH)
    assert 'acquire_public_sync_read_lock' in runner_called
    assert 'acquire_sync_writer_guard' not in runner_called


def test_no_second_source_client_or_extra_call_budget_exists():
    """One counting guard over the canonical client, and one budget."""
    runner_source = RUNNER_PATH.read_text(encoding='utf-8')
    assert runner_source.count('audit.CountedMLBClient(') == 1
    assert runner_source.count('audit.SourceCallBudget()') == 1
    for path in (SERVICE_PATH, RUNNER_PATH):
        called = _called_names(path)
        # No client is constructed here, and none is reached directly.
        assert 'MLBClient' not in called
        assert 'get_game_boxscore' not in called
        assert 'get_schedule' not in called


def test_the_single_row_lock_is_taken_without_waiting():
    source = RUNNER_PATH.read_text(encoding='utf-8')
    assert 'with_for_update(nowait=True)' in source
    assert 'with_for_update()' not in source
    assert 'skip_locked' not in source


def test_the_package_reuses_the_canonical_authorities_rather_than_forking():
    source = SERVICE_PATH.read_text(encoding='utf-8')
    # The audit's own row builder, validator, and materiality classifier.
    assert 'audit.matrix_row(' in source
    assert 'audit.validate_matrix(' in source
    assert 'extraction.FINGERPRINT_FIELDS' in source
    runner_source = RUNNER_PATH.read_text(encoding='utf-8')
    assert 'audit_runner.observe_current_source' in runner_source
    assert 'audit_runner.observe_stored_state' in runner_source
    assert 'sync_metadata.acquire_public_sync_read_lock' in runner_source
    assert 'audit.enforce_read_only' in runner_source
    assert 'audit.scoped_fingerprints' in runner_source
    # No second client, parser, planner, or reconciler.
    for forbidden in ('class MLBClient', 'def get_game_boxscore',
                      'def plan_game_work', 'def reconcile'):
        assert forbidden not in source
        assert forbidden not in runner_source


DOC_SECTIONS = (
    '## 1. Incident summary',
    '## 2. Audit evidence',
    '## 3. Why GameLog is not being repaired',
    '## 4. Why only the checkpoint is stale',
    '## 5. Exact old and new revision',
    '## 6. Exact target model and field',
    '## 7. Verify mode',
    '## 8. Apply mode',
    '## 9. Authorization contract',
    '## 10. Live preconditions',
    '## 11. Refusal conditions',
    '## 12. Concurrency control',
    '## 13. Mutation scope',
    '## 14. Before/after proof',
    '## 15. Artifact schema',
    '## 16. Result vocabulary',
    '## 17. Test coverage',
    '## 18. Rollout plan',
    '## 19. Rollback and containment',
    '## 20. Status boundary',
)


def test_the_documentation_carries_every_required_section():
    text = DOC_PATH.read_text(encoding='utf-8')
    for section in DOC_SECTIONS:
        assert section in text, section


def test_the_documentation_states_the_status_boundary():
    # Whitespace-normalized: a claim about content must not depend on where
    # markdown happened to wrap the line.
    text = ' '.join(DOC_PATH.read_text(encoding='utf-8').split())
    for claim in (
        'The repair has NOT been executed',
        'No production database session has been opened by this package',
        'No production row has been mutated',
        'No workflow has been dispatched',
        'No production mutation occurred',
        'Separate independent review is required before any dispatch',
        'Verify mode must be dispatched before apply mode',
        'no migration was added',
    ):
        assert claim.lower() in text.lower(), claim


def test_the_documentation_publishes_every_governed_literal():
    text = DOC_PATH.read_text(encoding='utf-8')
    assert repair.EXPECTED_EXISTING_SOURCE_REVISION in text
    assert repair.INTENDED_SOURCE_REVISION in text
    assert repair.EXPECTED_PLAN_FINGERPRINT in text
    assert str(repair.EXPECTED_APPEARANCE_COUNT) in text
    for identifier in repair.PRECONDITION_IDS:
        assert identifier in text, identifier
