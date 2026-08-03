"""The no-op write qualification contract, executed rather than described.

Every refusal condition in the contract has a test here. The failure matrix is
the point: a gate that is only asserted by reading prose is a gate nobody has
run.

Split-contract note. PASS requires every BASEBALL DATA effect to be zero and
enforces that strictly. The lane's own completion ledger — work item,
checkpoint, commit — advances on the canonical write path whenever writes are
enabled, independently of whether the plan mutates anything. Those counters are
reported with their real values and are deliberately NOT required to be zero.
Tests below pin both halves so neither can drift into the other.
"""

import pytest

from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import noop_write_qualification as qualification
from services import pitcher_identity_reconciliation as pitcher_identity


GAME_PK = 824488
SHA = 'a' * 40
OTHER_SHA = 'b' * 40
FINGERPRINT = 'f' * 32


def context(**overrides):
    base = {
        'event_name': 'workflow_dispatch',
        'repository': 'NickolisK24/bullpen-intel-engine',
        'actor': 'NickolisK24',
        'ref': 'refs/heads/main',
        'github_sha': SHA,
        'expected_head_sha': SHA,
        'confirmation': f'QUALIFY_NOOP_GAME_{GAME_PK}',
    }
    base.update(overrides)
    return base


def row(**overrides):
    base = {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': 5001,
        'action': reconciliation.ACTION_UNCHANGED,
        'changed_fields': [],
        'pitcher_identity_action': pitcher_identity.ACTION_UNCHANGED,
        'target_fields': ['innings_pitched_outs'],
    }
    base.update(overrides)
    return base


def report(*, rows=None, mode=lane.MODE_WRITE, status='complete', **overrides):
    rows = [row()] if rows is None else rows
    base = {
        'status': status,
        'mode': mode,
        'requested_game_pks': [GAME_PK],
        'planned_game_pks': [GAME_PK],
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'duplicate_requested_count': 0,
        'execution_scope_mode': 'exclusive',
        'execution_scope_exact_match': True,
        'games_fetched': 2,
        'games_attempted': 1,
        'games_completed': 1,
        'reconciliation_plan_fingerprint': FINGERPRINT,
        'authorized_plan_fingerprint': FINGERPRINT,
        'games': [{
            'game_pk': GAME_PK,
            'source_revision': 'rev-1',
            'rows': rows,
        }],
        'execution_effects': effects(),
    }
    for field in qualification.PROJECTED_MUTATION_COUNTERS:
        base.setdefault(field, 0)
    base['rows_unchanged'] = len(rows)
    base.update(overrides)
    return base


def effects(**overrides):
    base = {
        'writes_enabled': True,
        'publication_authoritative': False,
        'game_log_rows_written': 0,
        'pitcher_rows_written': 0,
        'appearance_team_rows_written': 0,
        'correction_provenance_rows_written': 0,
        'dead_letters_created': 0,
        # The canonical lane's real no-op values, not zeros.
        'work_items_created': 0,
        'work_items_updated': 1,
        'work_items_completed': 1,
        'checkpoints_advanced': 1,
        'commits_performed': 1,
    }
    base.update(overrides)
    return base


def state(digest='digest-1', available=True):
    return {
        'available': available,
        'digest': digest,
        'row_count': 1,
        'identity_count': 1,
        'projected_row_count': 1,
    }


def realization(**overrides):
    base = {
        'applicable': True,
        'already_matching_rows': 1,
        'divergent_rows': 0,
        'missing_rows': 0,
        'duplicate_rows': 0,
        'unresolved_rows': 0,
        'prohibited_identity_actions': 0,
        'all_projected_targets_realized': True,
    }
    base.update(overrides)
    return base


def assess(**overrides):
    kwargs = {
        'context': context(),
        'game_pk': GAME_PK,
        'shadow_report': report(mode=lane.MODE_SHADOW),
        'write_report': report(),
        'before_state': state(),
        'after_state': state(),
        'realization': realization(),
    }
    kwargs.update(overrides)
    return qualification.assess(**kwargs)


# ── The clean baseline ──────────────────────────────────────────────────────


def test_a_clean_one_game_noop_passes():
    decision = assess()
    assert decision['result'] == qualification.RESULT_PASS
    assert decision['exit_code'] == 0
    assert decision['failed_reasons'] == []
    assert decision['unproven_reasons'] == []


def test_pass_carries_the_explicit_non_authorization_statement():
    decision = assess()
    assert decision['non_authorization_statement'] == (
        'This qualification does not authorize scheduled writes, automated '
        'writes, authoritative publication, backfill, or future mutations.'
    )


# ── Input validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize('raw,reason', [
    ('', qualification.FAILED_GAME_PK_EMPTY),
    ('   ', qualification.FAILED_GAME_PK_EMPTY),
    (None, qualification.FAILED_GAME_PK_EMPTY),
    ('0', qualification.FAILED_GAME_PK_NOT_POSITIVE),
    ('-5', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('abc', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('824488,824489', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('824488 824489', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('824488-824489', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('824488..824490', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('2026-08-03', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('*', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('824488.0', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('0x824488', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
    ('+824488', qualification.FAILED_GAME_PK_NOT_AN_INTEGER),
])
def test_only_one_positive_integer_game_is_accepted(raw, reason):
    with pytest.raises(qualification.QualificationInputError) as excinfo:
        qualification.parse_game_pk(raw)
    assert excinfo.value.reason == reason


def test_a_single_positive_integer_parses():
    assert qualification.parse_game_pk(' 824488 ') == 824488


def test_the_expected_confirmation_is_bound_to_the_game():
    assert qualification.expected_confirmation(824488) == (
        'QUALIFY_NOOP_GAME_824488'
    )
    assert qualification.expected_confirmation(1) != (
        qualification.expected_confirmation(2)
    )


# ── Authorization ───────────────────────────────────────────────────────────


@pytest.mark.parametrize('overrides,reason', [
    ({'event_name': 'schedule'}, qualification.FAILED_EVENT_NOT_WORKFLOW_DISPATCH),
    ({'event_name': 'push'}, qualification.FAILED_EVENT_NOT_WORKFLOW_DISPATCH),
    ({'repository': 'someone/else'}, qualification.FAILED_REPOSITORY_NOT_AUTHORIZED),
    ({'actor': 'someone-else'}, qualification.FAILED_ACTOR_NOT_AUTHORIZED),
    ({'ref': 'refs/heads/feature'}, qualification.FAILED_REF_NOT_MAIN),
    ({'ref': 'refs/tags/v1'}, qualification.FAILED_REF_NOT_MAIN),
    ({'ref': 'refs/pull/602/merge'}, qualification.FAILED_REF_NOT_MAIN),
    ({'expected_head_sha': 'abc'}, qualification.FAILED_EXPECTED_SHA_MALFORMED),
    ({'expected_head_sha': 'Z' * 40}, qualification.FAILED_EXPECTED_SHA_MALFORMED),
    ({'expected_head_sha': OTHER_SHA}, qualification.FAILED_EXPECTED_SHA_MISMATCH),
    ({'confirmation': 'QUALIFY_NOOP_GAME_999'},
     qualification.FAILED_CONFIRMATION_MISMATCH),
    ({'confirmation': 'yes'}, qualification.FAILED_CONFIRMATION_MISMATCH),
    ({'confirmation': ''}, qualification.FAILED_CONFIRMATION_MISMATCH),
])
def test_every_authorization_condition_refuses(overrides, reason):
    failures = qualification.validate_authorization(
        context(**overrides), game_pk=GAME_PK,
    )
    assert reason in failures


def test_an_unauthorized_run_is_failed_not_unproven():
    decision = assess(context=context(actor='someone-else'))
    assert decision['result'] == qualification.RESULT_FAILED
    assert decision['exit_code'] == 1


def test_authorization_reports_every_failure_not_only_the_first():
    failures = qualification.validate_authorization(
        context(actor='x', ref='refs/heads/f', repository='a/b'),
        game_pk=GAME_PK,
    )
    assert len(failures) >= 3


def test_a_confirmation_for_a_different_game_is_refused():
    failures = qualification.validate_authorization(
        context(confirmation='QUALIFY_NOOP_GAME_824489'), game_pk=GAME_PK,
    )
    assert qualification.FAILED_CONFIRMATION_MISMATCH in failures


# ── Scope ───────────────────────────────────────────────────────────────────


def test_a_second_planned_game_is_refused():
    decision = assess(write_report=report(
        planned_game_pks=[GAME_PK, 999999],
        unexpected_planned_game_pks=[999999],
        execution_scope_exact_match=False,
    ))
    assert decision['result'] == qualification.RESULT_FAILED
    assert qualification.FAILED_UNEXPECTED_PLANNED_GAME in decision['failed_reasons']


def test_a_missing_requested_game_is_refused():
    decision = assess(write_report=report(
        planned_game_pks=[],
        missing_requested_game_pks=[GAME_PK],
        execution_scope_exact_match=False,
    ))
    assert qualification.FAILED_MISSING_REQUESTED_GAME in decision['failed_reasons']


def test_a_game_that_cannot_be_planned_is_refused():
    """A non-final game is excluded by the canonical planner and never plans."""
    decision = assess(shadow_report=report(
        mode=lane.MODE_SHADOW, planned_game_pks=[], rows=[],
        missing_requested_game_pks=[GAME_PK],
        execution_scope_exact_match=False,
    ))
    assert qualification.FAILED_GAME_NOT_PLANNABLE in decision['failed_reasons']


def test_a_duplicate_requested_game_is_refused():
    decision = assess(write_report=report(duplicate_requested_count=1))
    assert qualification.FAILED_DUPLICATE_REQUESTED_GAME in decision['failed_reasons']


def test_more_than_one_requested_game_is_refused():
    decision = assess(write_report=report(
        requested_game_pks=[GAME_PK, 999999],
        planned_game_pks=[GAME_PK, 999999],
    ))
    assert qualification.FAILED_REQUESTED_COUNT_NOT_ONE in decision['failed_reasons']


def test_not_attempting_exactly_one_game_is_refused():
    decision = assess(write_report=report(games_attempted=0))
    assert qualification.FAILED_FETCHED_COUNT_NOT_ONE in decision['failed_reasons']


def test_a_second_fetch_for_drift_revalidation_is_not_a_scope_violation():
    """An authorized exclusive write re-fetches the SAME game before writing.

    Counting fetch operations instead of distinct games would refuse exactly the
    drift re-validation this contract requires.
    """
    decision = assess(write_report=report(games_fetched=2))
    assert decision['result'] == qualification.RESULT_PASS
    assert decision['scope']['fetch_operations'] == 2
    assert decision['scope']['distinct_games_fetched'] == 1


def test_not_completing_exactly_one_game_is_refused():
    decision = assess(write_report=report(games_completed=2))
    assert qualification.FAILED_COMPLETED_COUNT_NOT_ONE in decision['failed_reasons']


def test_an_inexact_scope_is_refused():
    decision = assess(write_report=report(execution_scope_exact_match=False))
    assert qualification.FAILED_SCOPE_NOT_EXACT in decision['failed_reasons']


# ── Plan governance ─────────────────────────────────────────────────────────


@pytest.mark.parametrize('action', [
    reconciliation.ACTION_INSERT,
    reconciliation.ACTION_UPDATE,
    reconciliation.ACTION_BLOCKED,
])
def test_any_non_unchanged_action_is_refused(action):
    decision = assess(write_report=report(rows=[row(action=action)]))
    assert qualification.FAILED_PLAN_PROPOSES_MUTATION in decision['failed_reasons']


def test_an_unrecognised_action_type_is_refused():
    decision = assess(write_report=report(rows=[row(action='delete')]))
    assert qualification.FAILED_PLAN_UNKNOWN_ACTION in decision['failed_reasons']


def test_an_unknown_action_is_also_a_proposed_mutation():
    governance = qualification.evaluate_plan_governance(
        report(rows=[row(action='teleport')])
    )
    assert governance['unknown_action_count'] == 1
    assert governance['all_rows_already_matching'] is False


@pytest.mark.parametrize('identity_action', [
    pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
    pitcher_identity.ACTION_BLOCKED,
    'reactivate',
    'metadata_update',
    'team_reassignment',
])
def test_any_identity_mutation_is_refused(identity_action):
    decision = assess(write_report=report(
        rows=[row(pitcher_identity_action=identity_action)]
    ))
    assert qualification.FAILED_PROHIBITED_IDENTITY_ACTION in (
        decision['failed_reasons']
    )


def test_a_changed_field_on_an_unchanged_row_is_refused():
    decision = assess(write_report=report(
        rows=[row(changed_fields=['innings_pitched_outs'])]
    ))
    assert qualification.FAILED_PLAN_PROPOSES_MUTATION in decision['failed_reasons']


@pytest.mark.parametrize('counter', qualification.PROJECTED_MUTATION_COUNTERS)
def test_every_projected_mutation_counter_must_be_zero(counter):
    decision = assess(write_report=report(**{counter: 1}))
    assert qualification.FAILED_PLAN_PROPOSES_MUTATION in decision['failed_reasons']


def test_a_canonical_outs_correction_is_refused():
    decision = assess(write_report=report(canonical_outs_corrections=1))
    assert decision['result'] == qualification.RESULT_FAILED


def test_a_correction_provenance_write_is_refused():
    decision = assess(write_report=report(provenance_only_updates=1))
    assert decision['result'] == qualification.RESULT_FAILED


def test_an_appearance_team_mutation_is_refused():
    decision = assess(write_report=report(appearance_team_mutations=1))
    assert decision['result'] == qualification.RESULT_FAILED


def test_a_mutation_in_the_shadow_phase_alone_still_refuses():
    """The write phase is never entered on a mutating plan."""
    decision = assess(shadow_report=report(
        mode=lane.MODE_SHADOW, rows=[row(action=reconciliation.ACTION_UPDATE)],
    ))
    assert qualification.FAILED_PLAN_PROPOSES_MUTATION in decision['failed_reasons']


# ── Drift ───────────────────────────────────────────────────────────────────


def test_a_missing_plan_fingerprint_is_unproven():
    decision = assess(
        shadow_report=report(
            mode=lane.MODE_SHADOW, reconciliation_plan_fingerprint=None,
        ),
    )
    assert decision['result'] == qualification.RESULT_UNPROVEN
    assert qualification.UNPROVEN_PLAN_FINGERPRINT_MISSING in (
        decision['unproven_reasons']
    )


def test_a_plan_fingerprint_change_before_execution_is_refused():
    decision = assess(write_report=report(
        status=lane.STATUS_PLAN_FINGERPRINT_MISMATCH,
    ))
    assert qualification.FAILED_PLAN_FINGERPRINT_CHANGED in (
        decision['failed_reasons']
    )


def test_a_missing_source_revision_is_unproven():
    decision = assess(shadow_report=report(
        mode=lane.MODE_SHADOW,
        games=[{'game_pk': GAME_PK, 'source_revision': None, 'rows': [row()]}],
    ))
    assert qualification.UNPROVEN_SOURCE_REVISION_MISSING in (
        decision['unproven_reasons']
    )


def test_a_source_revision_change_before_execution_is_refused():
    decision = assess(write_report=report(
        games=[{'game_pk': GAME_PK, 'source_revision': 'rev-2', 'rows': [row()]}],
    ))
    assert qualification.FAILED_SOURCE_REVISION_CHANGED in (
        decision['failed_reasons']
    )


def test_a_fingerprint_is_evidence_and_never_reusable_authorization():
    """A matching fingerprint alone cannot carry a run to PASS."""
    decision = assess(write_report=report(
        rows=[row(action=reconciliation.ACTION_UPDATE)],
        reconciliation_plan_fingerprint=FINGERPRINT,
        authorized_plan_fingerprint=FINGERPRINT,
    ))
    assert decision['plan_fingerprint_match'] is True
    assert decision['result'] == qualification.RESULT_FAILED


def test_a_lane_scope_refusal_status_is_failed():
    decision = assess(write_report=report(status=lane.STATUS_SCOPE_MISMATCH))
    assert qualification.FAILED_SCOPE_NOT_EXACT in decision['failed_reasons']


def test_a_missing_write_authorization_status_is_unproven_not_pass():
    decision = assess(write_report=report(
        status=lane.STATUS_PLAN_AUTHORIZATION_REQUIRED,
    ))
    assert decision['result'] != qualification.RESULT_PASS


def test_an_incomplete_lane_run_is_refused():
    decision = assess(write_report=report(status='incomplete'))
    assert qualification.FAILED_LANE_STATUS_NOT_COMPLETE in (
        decision['failed_reasons']
    )


# ── Execution effects: the split contract ───────────────────────────────────


@pytest.mark.parametrize('field', qualification.BASEBALL_DATA_EFFECT_FIELDS)
def test_any_baseball_data_write_fails_the_qualification(field):
    decision = assess(write_report=report(
        execution_effects=effects(**{field: 1}),
    ))
    assert decision['result'] == qualification.RESULT_FAILED
    assert qualification.FAILED_BASEBALL_DATA_MUTATED in decision['failed_reasons']


def test_the_lane_completion_ledger_is_reported_with_its_real_values():
    decision = assess()
    ledger = decision['execution_effects']['lane_bookkeeping']
    assert ledger['work_items_updated'] == 1
    assert ledger['checkpoints_advanced'] == 1
    assert ledger['commits_performed'] == 1


def test_the_ledger_advancing_does_not_by_itself_fail_the_qualification():
    """Measured canonical behaviour: a no-op write still advances the ledger."""
    decision = assess()
    assert decision['result'] == qualification.RESULT_PASS
    assert decision['execution_effects']['baseball_data_total'] == 0


def test_the_two_effect_groups_are_disjoint():
    overlap = (
        set(qualification.BASEBALL_DATA_EFFECT_FIELDS)
        & set(qualification.LANE_BOOKKEEPING_EFFECT_FIELDS)
    )
    assert overlap == set()


def test_the_artifact_distinguishes_transaction_boundary_from_row_mutation():
    split = qualification.split_execution_effects(report())
    assert split['transaction_boundary_entered'] is True
    assert split['baseball_row_mutation_performed'] is False


def test_not_entering_the_write_capable_path_is_refused():
    decision = assess(write_report=report(
        execution_effects=effects(writes_enabled=False),
    ))
    assert qualification.FAILED_WRITES_NOT_ENABLED in decision['failed_reasons']


def test_publication_authoritative_is_refused():
    decision = assess(write_report=report(
        execution_effects=effects(publication_authoritative=True),
    ))
    assert qualification.FAILED_PUBLICATION_AUTHORITATIVE in (
        decision['failed_reasons']
    )


def test_missing_effect_counters_are_unproven():
    decision = assess(write_report=report(execution_effects={}))
    assert decision['result'] == qualification.RESULT_UNPROVEN
    assert qualification.UNPROVEN_EFFECT_COUNTERS_MISSING in (
        decision['unproven_reasons']
    )


def test_a_partial_effect_block_is_unproven_not_pass():
    decision = assess(write_report=report(
        execution_effects={'writes_enabled': True},
    ))
    assert decision['result'] != qualification.RESULT_PASS


# ── Readback and realization ────────────────────────────────────────────────


def test_pass_requires_pre_execution_readback():
    decision = assess(before_state=None)
    assert decision['result'] == qualification.RESULT_UNPROVEN
    assert qualification.UNPROVEN_PRE_READBACK_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_pass_requires_post_execution_readback():
    decision = assess(after_state=None)
    assert decision['result'] == qualification.RESULT_UNPROVEN
    assert qualification.UNPROVEN_POST_READBACK_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_an_unavailable_readback_is_unproven_not_assumed_unchanged():
    decision = assess(after_state=state(available=False))
    assert decision['result'] == qualification.RESULT_UNPROVEN


def test_a_before_after_digest_mismatch_is_refused():
    decision = assess(after_state=state(digest='digest-2'))
    assert decision['result'] == qualification.RESULT_FAILED
    assert qualification.FAILED_STATE_DIGEST_MISMATCH in decision['failed_reasons']


def test_matching_digests_are_reported_as_matching():
    decision = assess()
    assert decision['state_digest_match'] is True


def test_missing_realization_is_unproven():
    decision = assess(realization=None)
    assert qualification.UNPROVEN_REALIZATION_UNAVAILABLE in (
        decision['unproven_reasons']
    )


@pytest.mark.parametrize('field', [
    'divergent_rows', 'missing_rows', 'duplicate_rows', 'unresolved_rows',
])
def test_any_unresolved_realization_row_is_refused(field):
    decision = assess(realization=realization(**{
        field: 1, 'all_projected_targets_realized': False,
    }))
    assert qualification.FAILED_REALIZATION_UNRESOLVED in (
        decision['failed_reasons']
    )


def test_a_prohibited_identity_action_in_realization_is_refused():
    decision = assess(realization=realization(
        prohibited_identity_actions=1, all_projected_targets_realized=False,
    ))
    assert qualification.FAILED_PROHIBITED_IDENTITY_ACTION in (
        decision['failed_reasons']
    )


# ── Artifact safety ─────────────────────────────────────────────────────────


def test_forbidden_artifact_content_fails_the_run():
    decision = assess(artifact_scan={'available': True, 'safe': False})
    assert decision['result'] == qualification.RESULT_FAILED
    assert qualification.FAILED_ARTIFACT_FORBIDDEN_CONTENT in (
        decision['failed_reasons']
    )


def test_an_unavailable_artifact_scan_is_unproven():
    decision = assess(artifact_scan={'available': False})
    assert decision['result'] == qualification.RESULT_UNPROVEN
    assert qualification.UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_a_safe_scan_leaves_the_verdict_untouched():
    decision = assess(artifact_scan={'available': True, 'safe': True})
    assert decision['result'] == qualification.RESULT_PASS


# ── Verdict semantics ───────────────────────────────────────────────────────


def test_failed_and_unproven_are_both_non_zero():
    assert qualification.EXIT_CODES[qualification.RESULT_FAILED] != 0
    assert qualification.EXIT_CODES[qualification.RESULT_UNPROVEN] != 0
    assert qualification.EXIT_CODES[qualification.RESULT_PASS] == 0


def test_failed_outranks_unproven():
    decision = qualification.decide({
        'failed_reasons': ['a'], 'unproven_reasons': ['b'],
    })
    assert decision['result'] == qualification.RESULT_FAILED


def test_unproven_is_never_softened_into_pass():
    decision = qualification.decide({
        'failed_reasons': [], 'unproven_reasons': ['b'],
    })
    assert decision['result'] == qualification.RESULT_UNPROVEN
    assert decision['exit_code'] == qualification.EXIT_UNPROVEN


def test_the_vocabulary_is_exactly_three_words():
    assert sorted(qualification.EXIT_CODES) == ['FAILED', 'PASS', 'UNPROVEN']


def test_reason_codes_are_deduplicated_and_ordered():
    decision = qualification.decide({
        'failed_reasons': ['b', 'a', 'b'], 'unproven_reasons': [],
    })
    assert decision['failed_reasons'] == ['a', 'b']


# ── Operator note cannot authorize or leak ──────────────────────────────────


def test_the_operator_note_is_stripped_of_anything_that_could_carry_a_secret():
    note = qualification.sanitize_note(
        'postgres://u:p@host/db?token=abc <script> $SECRET_KEY /etc/passwd'
    )
    for fragment in ('://', '@', '?', '<', '>', '$', '/'):
        assert fragment not in note


def test_the_operator_note_is_bounded():
    assert len(qualification.sanitize_note('x' * 5000)) <= 280


def test_the_operator_note_never_affects_authorization():
    baseline = qualification.validate_authorization(context(), game_pk=GAME_PK)
    assert baseline == []
    # The note is not part of the authorization context at all.
    assert 'operator_note' not in context()


# ── Canonical reuse ─────────────────────────────────────────────────────────


def test_the_permitted_action_set_is_only_unchanged():
    assert qualification.PERMITTED_ACTIONS == {
        reconciliation.ACTION_UNCHANGED
    }


def test_the_digest_fields_come_from_the_canonical_vocabulary():
    for field in qualification.STATE_DIGEST_FIELDS:
        assert (
            field in reconciliation.STATISTICAL_FIELDS
            or field in reconciliation.ROLE_SIGNAL_FIELDS
            or field in reconciliation.APPEARANCE_TEAM_FIELDS
        )


def test_the_digest_excludes_provenance_and_derived_companions():
    """A provenance timestamp or a decimal companion is never a baseball change."""
    for field in reconciliation.PROVENANCE_FIELDS:
        assert field not in qualification.STATE_DIGEST_FIELDS
    for field in reconciliation.DERIVED_COMPANION_FIELDS:
        assert field not in qualification.STATE_DIGEST_FIELDS


def test_innings_pitched_outs_is_in_the_compared_state():
    assert 'innings_pitched_outs' in qualification.STATE_DIGEST_FIELDS
