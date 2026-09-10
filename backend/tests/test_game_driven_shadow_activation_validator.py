"""The activation validator's PASS and FAILED contracts.

The two cycles observe different moments and therefore get different contracts.
The single most important property here is that they are NOT the same rule:

* daily runs before its writer, so projected inserts and updates are normal and
  the question is whether the writer realized them;
* postgame runs after its writer, so any projection at all means the writer
  left canonical work behind.

A validator that applied one rule to both would either fail every useful day or
pass a postgame cycle that should have failed.
"""

import copy
import json

import pytest

from scripts import validate_game_driven_shadow_cycle as validator
from services import sync_metadata


PASS = validator.RESULT_PASS
FAILED = validator.RESULT_FAILED


def _lane(**overrides):
    lane = {
        'status': 'complete',
        'mode': 'shadow',
        'job_name': sync_metadata.JOB_DAILY_SYNC,
        'writes_enabled': False,
        'publication_authoritative': False,
        'allocated_budget_seconds': 180.0,
        'remaining_budget_seconds': 120.0,
        'games_discovered': 1,
        'games_planned': 1,
        'games_attempted': 1,
        'games_fetched': 1,
        'games_completed': 1,
        'games_failed': 0,
        'games_remaining': 0,
        'newly_final_count': 1,
        'corrected_final_count': 0,
        'retry_count': 0,
        'schedule_authority_missing': 0,
        'finality_conflicts': 0,
        'rows_expected': 2,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': 2,
        'rows_blocked': 0,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'canonical_outs_corrections': 0,
        'statistical_corrections': 0,
        'provenance_only_updates': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': 0,
        'corrections_applied': 0,
        'budget_stop_triggered': False,
        'failure_classes': {},
        'reconciliation_plan_fingerprint': 'a' * 64,
        'complete_reconciliation_fingerprint': 'a' * 64,
        'reconciliation_plan_version': '3',
        'parity_contract_version': '4',
        'innings_semantics_version': '2',
        'complete_plan_version': '1',
        'identity_plan_version': '1',
        'planner_seconds': 0.2,
        'fetch_seconds': 1.1,
        'persistence_seconds': 0.3,
        'elapsed_seconds': 2.0,
        'execution_effects': _effects(),
        'execution_scope': _base_scope(),
        'projected_differences': [],
        'games': [{
            'game_pk': 930001,
            'source_revision': 'rev-1',
            'reconciliation_plan_fingerprint': 'b' * 64,
            'status': 'projected',
        }],
        'realization': _realization(),
    }
    lane.update(overrides)
    return lane


def _base_scope():
    """A valid one-game exact scope, matching the base lane's single game."""
    return {
        'scope_source': validator.POSTGAME_SCOPE_SOURCE,
        'cycle_game_count': 1,
        'requested_game_pks': [930001],
        'requested_game_count': 1,
        'excluded_game_pks': [],
        'excluded_reason_counts': {},
        'execution_scope_mode': 'exclusive',
        'planned_game_pks': [930001],
        'planned_game_count': 1,
        'missing_requested_game_pks': [],
        'unexpected_planned_game_pks': [],
        'execution_scope_exact_match': True,
    }


def _diffs(count):
    """Safe diagnostics for ``count`` projected non-unchanged rows."""
    return [
        {
            'game_pk': 930001,
            'pitcher_mlb_id': 8000 + index,
            'action': 'update',
            'changed_fields': ['earned_runs'],
            'difference_classifications': ['statistical_correction'],
            'blocked_reason': None,
            'pitcher_identity_action': 'unchanged',
            'source_revision': 'rev-1',
            'reconciliation_plan_fingerprint': 'b' * 64,
            'target_state_digest': 'a' * 32,
            'stored_state_digest': 'c' * 32,
        }
        for index in range(count)
    ]


def _effects(**overrides):
    effects = {
        'writes_enabled': False,
        'publication_authoritative': False,
        'game_log_rows_written': 0,
        'pitcher_rows_written': 0,
        'appearance_team_rows_written': 0,
        'correction_provenance_rows_written': 0,
        'work_items_created': 0,
        'work_items_updated': 0,
        'work_items_completed': 0,
        'checkpoints_advanced': 0,
        'dead_letters_created': 0,
        'commits_performed': 0,
    }
    effects.update(overrides)
    return effects


def _realization(**overrides):
    realization = {
        'applicable': True,
        'available': True,
        'work_state': 'candidates_planned',
        'projected_rows': 2,
        'projected_inserts': 0,
        'projected_updates': 0,
        'projected_unchanged': 2,
        'projected_blocked': 0,
        'realized_rows': 0,
        'realized_inserts': 0,
        'realized_updates': 0,
        'already_matching_rows': 2,
        'unresolved_rows': 0,
        'divergent_rows': 0,
        'missing_rows': 0,
        'duplicate_rows': 0,
        'identity_creations_projected': 0,
        'identity_creations_realized': 0,
        'prohibited_identity_actions': 0,
        'current_state_mutations_refused': 0,
        'appearance_team_actions_projected': 0,
        'appearance_team_actions_realized': 0,
        'corrections_projected': 0,
        'corrections_realized': 0,
        'source_revision_match': True,
        'safe_digest_match': True,
        'all_projected_targets_realized': True,
        'unresolved_identities': [],
        'divergent_identities': [],
    }
    realization.update(overrides)
    return realization


def _summary(cycle_kind='daily', *, lane=None, proof=None, status='success'):
    lane = lane if lane is not None else _lane(
        job_name=(
            sync_metadata.JOB_DAILY_SYNC if cycle_kind == 'daily'
            else sync_metadata.JOB_POSTGAME_REFRESH
        ),
    )
    if proof is None:
        proof = {'verified': True}
    return {
        'status': status,
        'publication_proof': proof,
        'sync': {'status': status, 'game_driven_ingestion': lane},
    }


def _validate(summary, cycle_kind='daily', runner_exit_code=0):
    return validator.validate_cycle(
        summary, cycle_kind=cycle_kind, runner_exit_code=runner_exit_code,
    )


def _invariants(decision):
    return {failure['invariant'] for failure in decision['failed_invariants']}


# ── Clean cycles ────────────────────────────────────────────────────────────


def test_a_clean_daily_work_cycle_passes():
    assert _validate(_summary('daily'))['result'] == PASS


def test_a_clean_daily_no_work_cycle_passes():
    lane = _lane(
        games_discovered=0, games_planned=0, games_attempted=0,
        games_fetched=0, games_completed=0, newly_final_count=0,
        rows_expected=0, rows_unchanged=0, games=[],
        reconciliation_plan_fingerprint=None,
        execution_scope={
            **_base_scope(),
            'cycle_game_count': 0, 'requested_game_pks': [],
            'requested_game_count': 0, 'planned_game_pks': [],
            'planned_game_count': 0, 'execution_scope_exact_match': None,
        },
        realization=_realization(
            applicable=False, work_state='no_candidates', projected_rows=0,
            projected_unchanged=0, already_matching_rows=0,
        ),
    )
    decision = _validate(_summary('daily', lane=lane))
    assert decision['result'] == PASS
    assert decision['work_state'] == validator.WORK_STATE_NO_CANDIDATES


def test_a_clean_postgame_work_cycle_passes():
    assert _validate(_summary('postgame'), 'postgame')['result'] == PASS


def test_a_clean_postgame_no_work_cycle_passes():
    lane = _lane(
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        games_discovered=0, games_planned=0, games_attempted=0,
        games_fetched=0, games_completed=0, newly_final_count=0,
        rows_expected=0, rows_unchanged=0, games=[],
        reconciliation_plan_fingerprint=None, realization=None,
        execution_scope={
            **_base_scope(),
            'cycle_game_count': 0, 'requested_game_pks': [],
            'requested_game_count': 0, 'planned_game_pks': [],
            'planned_game_count': 0, 'execution_scope_exact_match': None,
        },
    )
    assert _validate(_summary('postgame', lane=lane), 'postgame')['result'] == PASS


# ── The cycle-semantics correction ──────────────────────────────────────────


def test_a_daily_cycle_with_projected_inserts_and_updates_passes():
    """The whole point of the daily contract: finding work is not a failure."""
    lane = _lane(
        rows_expected=5, rows_inserted=3, rows_updated=1, rows_unchanged=1,
        statistical_corrections=1, canonical_outs_corrections=1,
        complete_mutation_count=4, projected_differences=_diffs(4),
        realization=_realization(
            projected_rows=5, projected_inserts=3, projected_updates=1,
            projected_unchanged=1, realized_rows=4, realized_inserts=3,
            realized_updates=1, already_matching_rows=1,
            corrections_projected=1, corrections_realized=1,
        ),
    )
    assert _validate(_summary('daily', lane=lane))['result'] == PASS


def test_the_same_projection_fails_the_postgame_contract():
    """Identical numbers, opposite verdict — the cycles are not one rule."""
    lane = _lane(
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        rows_expected=5, rows_inserted=3, rows_updated=1, rows_unchanged=1,
        statistical_corrections=1, canonical_outs_corrections=1,
        complete_mutation_count=4, realization=None,
    )
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    assert 'postgame_projected.rows_inserted' in _invariants(decision)


def test_a_daily_projected_insert_is_not_reported_as_a_shadow_write():
    lane = _lane(
        rows_inserted=3, rows_expected=3, rows_unchanged=0,
        projected_differences=_diffs(3),
        realization=_realization(
            projected_rows=3, projected_inserts=3, projected_unchanged=0,
            realized_rows=3, realized_inserts=3, already_matching_rows=0,
        ),
    )
    decision = _validate(_summary('daily', lane=lane))
    assert decision['projected']['rows_inserted'] == 3
    assert decision['execution_effects']['game_log_rows_written'] == 0
    assert decision['result'] == PASS


# ── Production outcome ──────────────────────────────────────────────────────


def test_a_nonzero_runner_exit_fails():
    decision = _validate(_summary('daily'), runner_exit_code=1)
    assert decision['result'] == FAILED
    assert 'runner_exit_code' in _invariants(decision)


def test_an_unsuccessful_sync_status_fails():
    decision = _validate(_summary('daily', status='failed'))
    assert decision['result'] == FAILED
    assert 'sync_status' in _invariants(decision)


def test_a_partial_sync_status_is_still_an_established_success():
    assert _validate(_summary('daily', status='partial'))['result'] == PASS


def test_a_daily_publication_failure_fails():
    decision = _validate(_summary('daily', proof={'verified': False}))
    assert decision['result'] == FAILED
    assert 'daily_publication_proof' in _invariants(decision)


def test_a_postgame_expected_active_slate_pending_passes():
    proof = {
        'verified': False,
        'league_publication_status': (
            validator.LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE
        ),
    }
    assert _validate(
        _summary('postgame', proof=proof), 'postgame',
    )['result'] == PASS


def test_a_postgame_genuine_withhold_fails():
    proof = {'verified': False, 'league_publication_status': 'failed'}
    decision = _validate(_summary('postgame', proof=proof), 'postgame')
    assert decision['result'] == FAILED
    assert 'postgame_publication_proof' in _invariants(decision)


def test_the_expected_pending_constant_is_imported_not_spelled_out():
    from services import sync_publication_proof

    assert validator.LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE is (
        sync_publication_proof.LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE
    )


# ── Report presence and identity ────────────────────────────────────────────


def test_a_missing_report_fails():
    summary = {'status': 'success', 'publication_proof': {'verified': True},
               'sync': {'status': 'success'}}
    decision = _validate(summary)
    assert decision['result'] == FAILED
    assert 'game_driven_report_missing' in _invariants(decision)


def test_a_disabled_lane_fails():
    lane = {'status': 'disabled', 'mode': 'off'}
    decision = _validate(_summary('daily', lane=lane))
    assert decision['result'] == FAILED
    assert 'game_driven_lane_disabled' in _invariants(decision)


def test_a_wrong_cycle_kind_fails():
    lane = _lane(job_name=sync_metadata.JOB_POSTGAME_REFRESH)
    decision = _validate(_summary('daily', lane=lane), 'daily')
    assert decision['result'] == FAILED
    assert 'cycle_kind_mismatch' in _invariants(decision)


@pytest.mark.parametrize('mode', ['off', 'write', 'authoritative'])
def test_a_non_shadow_mode_fails(mode):
    decision = _validate(_summary('daily', lane=_lane(mode=mode)))
    assert decision['result'] == FAILED
    assert 'configured_mode' in _invariants(decision)


def test_writes_enabled_fails():
    decision = _validate(_summary('daily', lane=_lane(writes_enabled=True)))
    assert decision['result'] == FAILED
    assert 'writes_enabled' in _invariants(decision)


def test_publication_authoritative_fails():
    decision = _validate(
        _summary('daily', lane=_lane(publication_authoritative=True))
    )
    assert decision['result'] == FAILED
    assert 'publication_authoritative' in _invariants(decision)


@pytest.mark.parametrize('field,bad', [
    ('reconciliation_plan_version', '2'),
    ('parity_contract_version', '3'),
    ('innings_semantics_version', '1'),
    ('complete_plan_version', '2'),
    ('identity_plan_version', '2'),
])
def test_a_wrong_version_fails(field, bad):
    decision = _validate(_summary('daily', lane=_lane(**{field: bad})))
    assert decision['result'] == FAILED
    assert field in _invariants(decision)


def test_the_expected_versions_come_from_the_live_constants():
    from services import game_log_reconciliation as reconciliation
    from services import pitcher_identity_reconciliation as identity

    assert validator.EXPECTED_VERSIONS == {
        'reconciliation_plan_version': reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
    }


# ── Planning ────────────────────────────────────────────────────────────────


def test_an_incomplete_status_fails():
    decision = _validate(_summary('daily', lane=_lane(status='incomplete')))
    assert decision['result'] == FAILED
    assert 'report_status' in _invariants(decision)


@pytest.mark.parametrize('status', ['scope_mismatch', 'scope_invalid',
                                    'plan_authorization_required',
                                    'plan_fingerprint_mismatch'])
def test_a_scope_or_authorization_status_fails(status):
    decision = _validate(_summary('daily', lane=_lane(status=status)))
    assert decision['result'] == FAILED
    assert 'report_status' in _invariants(decision)


def test_a_schedule_authority_gap_fails():
    decision = _validate(
        _summary('daily', lane=_lane(schedule_authority_missing=1))
    )
    assert decision['result'] == FAILED
    assert 'schedule_authority_missing' in _invariants(decision)


def test_a_finality_conflict_fails():
    decision = _validate(_summary('daily', lane=_lane(finality_conflicts=1)))
    assert decision['result'] == FAILED
    assert 'finality_conflicts' in _invariants(decision)


def test_a_failure_class_fails():
    decision = _validate(
        _summary('daily', lane=_lane(failure_classes={'game_fetch_failed': 1}))
    )
    assert decision['result'] == FAILED
    assert 'failure_classes' in _invariants(decision)


def test_a_budget_stop_fails():
    decision = _validate(
        _summary('daily', lane=_lane(budget_stop_triggered=True))
    )
    assert decision['result'] == FAILED
    assert 'budget_stop_triggered' in _invariants(decision)


@pytest.mark.parametrize('field', [
    'expected_plan_fingerprint', 'observed_plan_fingerprint',
    'authorized_plan_fingerprint',
])
def test_an_authorization_path_in_an_observation_cycle_fails(field):
    decision = _validate(_summary('daily', lane=_lane(**{field: 'c' * 64})))
    assert decision['result'] == FAILED
    assert f'authorization_path_present:{field}' in _invariants(decision)


# ── Game accounting ─────────────────────────────────────────────────────────


@pytest.mark.parametrize('field', [
    'games_attempted', 'games_fetched', 'games_completed',
])
def test_a_planned_count_mismatch_fails(field):
    decision = _validate(_summary('daily', lane=_lane(**{field: 0})))
    assert decision['result'] == FAILED
    assert field in _invariants(decision)


def test_a_failed_game_fails():
    decision = _validate(_summary('daily', lane=_lane(games_failed=1)))
    assert decision['result'] == FAILED
    assert 'games_failed' in _invariants(decision)


def test_a_remaining_game_fails():
    decision = _validate(_summary('daily', lane=_lane(games_remaining=1)))
    assert decision['result'] == FAILED
    assert 'games_remaining' in _invariants(decision)


def test_a_duplicate_game_fails():
    games = [
        {'game_pk': 930001, 'source_revision': 'r', 'reconciliation_plan_fingerprint': 'b' * 64},
        {'game_pk': 930001, 'source_revision': 'r', 'reconciliation_plan_fingerprint': 'b' * 64},
    ]
    lane = _lane(
        games=games, games_planned=2, games_attempted=2, games_fetched=2,
        games_completed=2,
    )
    decision = _validate(_summary('daily', lane=lane))
    assert decision['result'] == FAILED
    assert 'duplicate_game' in _invariants(decision)


def test_a_no_work_cycle_with_row_counts_fails():
    lane = _lane(
        games_planned=0, games_attempted=0, games_fetched=0, games_completed=0,
        games=[], rows_expected=4,
    )
    decision = _validate(_summary('daily', lane=lane))
    assert decision['result'] == FAILED
    assert 'no_work_cycle:rows_expected' in _invariants(decision)


# ── Fingerprints ────────────────────────────────────────────────────────────


def test_a_missing_run_fingerprint_with_work_fails():
    decision = _validate(
        _summary('daily', lane=_lane(reconciliation_plan_fingerprint=None))
    )
    assert decision['result'] == FAILED
    assert 'run_fingerprint' in _invariants(decision)


@pytest.mark.parametrize('bad', ['A' * 64, 'a' * 63, 'zz' + 'a' * 62, ''])
def test_an_invalid_run_fingerprint_fails(bad):
    decision = _validate(
        _summary('daily', lane=_lane(reconciliation_plan_fingerprint=bad))
    )
    assert decision['result'] == FAILED
    assert 'run_fingerprint' in _invariants(decision)


def test_a_missing_per_game_fingerprint_fails():
    games = [{'game_pk': 930001, 'source_revision': 'r'}]
    decision = _validate(_summary('daily', lane=_lane(games=games)))
    assert decision['result'] == FAILED
    assert 'per_game_fingerprint_missing' in _invariants(decision)


def test_a_missing_source_revision_fails():
    games = [{'game_pk': 930001, 'reconciliation_plan_fingerprint': 'b' * 64}]
    decision = _validate(_summary('daily', lane=_lane(games=games)))
    assert decision['result'] == FAILED
    assert 'source_revision_missing' in _invariants(decision)


# ── Runtime and budget ──────────────────────────────────────────────────────


def test_a_missing_allocated_budget_fails():
    decision = _validate(
        _summary('daily', lane=_lane(allocated_budget_seconds=None))
    )
    assert decision['result'] == FAILED
    assert 'allocated_budget_missing' in _invariants(decision)


def test_a_missing_headroom_fails():
    decision = _validate(
        _summary('daily', lane=_lane(remaining_budget_seconds=None))
    )
    assert decision['result'] == FAILED
    assert 'budget_headroom_missing' in _invariants(decision)


def test_negative_headroom_fails():
    decision = _validate(
        _summary('daily', lane=_lane(remaining_budget_seconds=-1.0))
    )
    assert decision['result'] == FAILED
    assert 'budget_headroom_negative' in _invariants(decision)


def test_a_missing_planner_runtime_fails():
    decision = _validate(_summary('daily', lane=_lane(planner_seconds=None)))
    assert decision['result'] == FAILED
    assert 'runtime_missing:planner_seconds' in _invariants(decision)


def test_a_missing_fetch_runtime_with_work_fails():
    decision = _validate(_summary('daily', lane=_lane(fetch_seconds=None)))
    assert decision['result'] == FAILED
    assert 'runtime_missing:fetch_seconds' in _invariants(decision)


# ── Actual execution effects ────────────────────────────────────────────────


def test_missing_execution_effects_fails():
    decision = _validate(_summary('daily', lane=_lane(execution_effects=None)))
    assert decision['result'] == FAILED
    assert 'execution_effects_missing' in _invariants(decision)


@pytest.mark.parametrize('field', validator.EXECUTION_EFFECT_FIELDS)
def test_any_actual_shadow_write_fails(field):
    decision = _validate(
        _summary('daily', lane=_lane(execution_effects=_effects(**{field: 1})))
    )
    assert decision['result'] == FAILED
    assert f'execution_effects.{field}' in _invariants(decision)


def test_execution_effects_claiming_writes_enabled_fails():
    decision = _validate(
        _summary('daily', lane=_lane(
            execution_effects=_effects(writes_enabled=True),
        ))
    )
    assert decision['result'] == FAILED
    assert 'execution_effects.writes_enabled' in _invariants(decision)


def test_every_execution_effect_field_is_checked():
    """A field added to the report but not to the contract would be unchecked."""
    from services import game_driven_ingestion

    reported = set(game_driven_ingestion._empty_execution_effects('shadow'))
    covered = set(validator.EXECUTION_EFFECT_FIELDS) | {
        'writes_enabled', 'publication_authoritative',
    }
    assert reported == covered


# ── Daily realization ───────────────────────────────────────────────────────


def test_a_missing_daily_realization_fails():
    decision = _validate(_summary('daily', lane=_lane(realization=None)))
    assert decision['result'] == FAILED
    assert 'daily_realization_missing' in _invariants(decision)


def test_an_unavailable_daily_realization_fails():
    realization = {'available': False, 'reason': 'realization_proof_unavailable'}
    decision = _validate(_summary('daily', lane=_lane(realization=realization)))
    assert decision['result'] == FAILED
    assert 'daily_realization_unavailable' in _invariants(decision)


@pytest.mark.parametrize('field', [
    'unresolved_rows', 'divergent_rows', 'missing_rows', 'duplicate_rows',
    'prohibited_identity_actions',
])
def test_a_daily_realization_defect_fails(field):
    realization = _realization(
        **{field: 1, 'all_projected_targets_realized': False}
    )
    decision = _validate(_summary('daily', lane=_lane(realization=realization)))
    assert decision['result'] == FAILED
    assert f'daily_realization.{field}' in _invariants(decision)


def test_a_daily_source_revision_change_fails():
    realization = _realization(
        source_revision_match=False, all_projected_targets_realized=False,
    )
    decision = _validate(_summary('daily', lane=_lane(realization=realization)))
    assert decision['result'] == FAILED
    assert 'daily_realization.source_revision_match' in _invariants(decision)


def test_a_daily_digest_mismatch_fails():
    realization = _realization(
        safe_digest_match=False, all_projected_targets_realized=False,
    )
    decision = _validate(_summary('daily', lane=_lane(realization=realization)))
    assert decision['result'] == FAILED
    assert 'daily_realization.safe_digest_match' in _invariants(decision)


def test_partial_realization_fails():
    realization = _realization(
        projected_rows=4, projected_inserts=4, realized_rows=2,
        realized_inserts=2, missing_rows=2,
        all_projected_targets_realized=False,
    )
    decision = _validate(_summary('daily', lane=_lane(realization=realization)))
    assert decision['result'] == FAILED
    assert 'daily_realization.missing_rows' in _invariants(decision)


def test_a_daily_projected_blocked_row_fails():
    decision = _validate(_summary('daily', lane=_lane(rows_blocked=1)))
    assert decision['result'] == FAILED
    assert 'daily_projected_blocked' in _invariants(decision)


def test_a_safe_realized_minimal_identity_creation_passes():
    realization = _realization(
        identity_creations_projected=1, identity_creations_realized=1,
        projected_inserts=1, projected_rows=2, realized_rows=1,
        realized_inserts=1, already_matching_rows=1,
    )
    lane = _lane(
        rows_inserted=1, rows_unchanged=1, rows_expected=2,
        pitcher_identity_creations=1, pitcher_identity_mutations=1,
        complete_mutation_count=2, realization=realization,
        projected_differences=_diffs(1),
    )
    assert _validate(_summary('daily', lane=lane))['result'] == PASS


def test_an_unrealized_identity_creation_fails():
    realization = _realization(
        identity_creations_projected=1, identity_creations_realized=0,
        missing_rows=1, all_projected_targets_realized=False,
    )
    decision = _validate(_summary('daily', lane=_lane(realization=realization)))
    assert decision['result'] == FAILED


# ── Postgame convergence ────────────────────────────────────────────────────


def _postgame_lane(**overrides):
    base = dict(job_name=sync_metadata.JOB_POSTGAME_REFRESH, realization=None)
    base.update(overrides)
    return _lane(**base)


@pytest.mark.parametrize('field', ['rows_inserted', 'rows_updated', 'rows_blocked'])
def test_a_postgame_projected_row_action_fails(field):
    lane = _postgame_lane(**{field: 1})
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    assert f'postgame_projected.{field}' in _invariants(decision)


@pytest.mark.parametrize('field', validator.PROJECTED_MUTATION_TARGETS)
def test_a_postgame_projected_mutation_target_fails(field):
    lane = _postgame_lane(**{field: 1})
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    assert f'postgame_projected.{field}' in _invariants(decision)


def test_a_postgame_row_that_is_not_unchanged_fails():
    lane = _postgame_lane(rows_expected=3, rows_unchanged=2)
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    assert 'postgame_rows_all_unchanged' in _invariants(decision)


def test_a_postgame_identity_creation_fails():
    lane = _postgame_lane(pitcher_identity_creations=1)
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED


def test_a_postgame_cycle_needs_no_realization_section():
    lane = _postgame_lane()
    assert _validate(_summary('postgame', lane=lane), 'postgame')['result'] == PASS


def test_every_mutation_target_the_report_publishes_is_policed():
    """A new mutation counter must not be able to slip past the contract."""
    from services import game_driven_ingestion

    for field in game_driven_ingestion._IDENTITY_COUNTER_FIELDS:
        if field in (
            'pitcher_identity_rows_examined', 'pitcher_identity_unchanged',
            'historical_current_state_changes_suppressed',
        ):
            # Observations, not mutations.
            continue
        assert field in validator.PROJECTED_MUTATION_TARGETS, (
            f'{field} is a mutation target the postgame contract does not check'
        )


# ── Decision, artifacts, exit semantics ─────────────────────────────────────


def test_a_pass_records_that_it_is_not_authorization():
    decision = _validate(_summary('daily'))
    assert decision['result'] == PASS
    assert decision['write_approved'] is False
    assert decision['future_write_authorized'] is False


def test_a_failed_result_also_records_no_authorization():
    decision = _validate(_summary('daily', lane=_lane(games_failed=1)))
    assert decision['result'] == FAILED
    assert decision['write_approved'] is False
    assert decision['future_write_authorized'] is False


def test_the_decision_is_deterministic():
    summary = _summary('daily')
    first = _validate(copy.deepcopy(summary))
    second = _validate(copy.deepcopy(summary))
    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
        second, sort_keys=True, default=str
    )


def test_the_decision_serializes_safely():
    decision = _validate(_summary('daily'))
    body = json.dumps(decision, sort_keys=True, default=str)
    for forbidden in (
        'postgresql://', 'password=', 'Authorization:', 'ADMIN_API_TOKEN',
        'SECRET_KEY', 'DATABASE_URL', 'Traceback', '/home/',
    ):
        assert forbidden not in body


def test_an_unsupported_cycle_kind_cannot_run():
    with pytest.raises(validator.ValidationError):
        _validate(_summary('daily'), 'weekly')


def test_a_failed_result_cannot_exit_zero(tmp_path):
    summary_path = tmp_path / 'sync.json'
    summary_path.write_text(
        json.dumps(_summary('daily', lane=_lane(games_failed=1))),
        encoding='utf-8',
    )
    code = validator.main([
        '--sync-summary', str(summary_path),
        '--cycle-kind', 'daily',
        '--runner-exit-code', '0',
        '--summary-json', str(tmp_path / 'activation.json'),
        '--summary-markdown', str(tmp_path / 'activation.md'),
    ])
    assert code == validator.EXIT_FAILED


def test_a_pass_exits_zero_and_writes_both_artifacts(tmp_path):
    summary_path = tmp_path / 'sync.json'
    summary_path.write_text(json.dumps(_summary('daily')), encoding='utf-8')
    json_path = tmp_path / 'out' / 'activation.json'
    markdown_path = tmp_path / 'out' / 'activation.md'
    code = validator.main([
        '--sync-summary', str(summary_path),
        '--cycle-kind', 'daily',
        '--runner-exit-code', '0',
        '--summary-json', str(json_path),
        '--summary-markdown', str(markdown_path),
    ])
    assert code == validator.EXIT_PASS
    assert json.loads(json_path.read_text())['result'] == PASS
    assert 'DAILY PASS' in markdown_path.read_text()


def test_a_malformed_summary_is_unusable_not_a_pass(tmp_path):
    summary_path = tmp_path / 'sync.json'
    summary_path.write_text('not json', encoding='utf-8')
    code = validator.main([
        '--sync-summary', str(summary_path),
        '--cycle-kind', 'daily',
        '--runner-exit-code', '0',
        '--summary-json', str(tmp_path / 'a.json'),
        '--summary-markdown', str(tmp_path / 'a.md'),
    ])
    assert code == validator.EXIT_UNUSABLE


def test_a_missing_summary_file_is_unusable_not_a_pass(tmp_path):
    code = validator.main([
        '--sync-summary', str(tmp_path / 'absent.json'),
        '--cycle-kind', 'daily',
        '--runner-exit-code', '0',
        '--summary-json', str(tmp_path / 'a.json'),
        '--summary-markdown', str(tmp_path / 'a.md'),
    ])
    assert code == validator.EXIT_UNUSABLE


def test_an_unexpected_summary_shape_is_unusable(tmp_path):
    summary_path = tmp_path / 'sync.json'
    summary_path.write_text('[1, 2, 3]', encoding='utf-8')
    code = validator.main([
        '--sync-summary', str(summary_path),
        '--cycle-kind', 'daily',
        '--runner-exit-code', '0',
        '--summary-json', str(tmp_path / 'a.json'),
        '--summary-markdown', str(tmp_path / 'a.md'),
    ])
    assert code == validator.EXIT_UNUSABLE


def test_the_validator_queries_no_database_and_calls_no_mlb():
    source = validator.__file__
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    for forbidden in (
        '.query.', 'db.session', 'mlb_client', 'run_game_driven_ingestion',
        'plan_game_work', 'requests.',
    ):
        assert forbidden not in text, (
            f'the validator must not {forbidden!r} — it validates evidence, it '
            f'does not re-derive it'
        )


# ── Rendering ───────────────────────────────────────────────────────────────


def test_the_daily_pass_summary_states_the_realization_result():
    decision = _validate(_summary('daily'))
    rendered = validator.render_markdown(decision)
    assert 'DAILY PASS' in rendered
    assert 'Realization after legacy writer' in rendered
    assert 'Projected targets realized: yes' in rendered
    assert 'Shadow itself performed no database write.' in rendered
    assert 'does not authorize automated write' in rendered


def test_the_postgame_pass_summary_states_convergence():
    decision = _validate(_summary('postgame'), 'postgame')
    rendered = validator.render_markdown(decision)
    assert 'POSTGAME PASS' in rendered
    assert 'Convergence after postgame writer' in rendered
    assert 'converged to zero projected canonical mutations' in rendered


def test_the_failed_summary_states_the_standing_prohibitions():
    decision = _validate(_summary('daily', lane=_lane(games_failed=1)))
    rendered = validator.render_markdown(decision)
    assert 'FAILED' in rendered
    assert 'Current publication authority remains unchanged.' in rendered
    assert 'Automated write mode remains prohibited.' in rendered
    assert 'Authoritative mode remains prohibited.' in rendered
    assert 'Review the activation artifact' in rendered


def test_the_failed_summary_names_the_failed_invariant():
    decision = _validate(_summary('daily', lane=_lane(games_failed=1)))
    assert 'games_failed' in validator.render_markdown(decision)


def test_the_rendered_summary_carries_no_forbidden_content():
    decision = _validate(_summary('daily', lane=_lane(games_failed=1)))
    rendered = validator.render_markdown(decision)
    for forbidden in (
        'postgresql://', 'password=', 'Authorization:', 'ADMIN_API_TOKEN',
        'SECRET_KEY', 'DATABASE_URL', 'Traceback', '/home/',
    ):
        assert forbidden not in rendered


def test_both_pass_summaries_report_zero_actual_writes():
    for cycle in ('daily', 'postgame'):
        decision = _validate(_summary(cycle), cycle)
        rendered = validator.render_markdown(decision)
        assert 'GameLog rows written: 0' in rendered
        assert 'Checkpoints advanced: 0' in rendered
        assert 'Game-driven dead letters created: 0' in rendered
        assert 'Write approved: no' in rendered
        assert 'Future write authorized: no' in rendered


# ── Postgame exact-cycle scope ──────────────────────────────────────────────
# The first postgame cycle passed every check it had and still planned the
# wrong 112 games, because nothing checked scope. These are those checks.


def _scope(**overrides):
    scope = {
        'scope_source': validator.POSTGAME_SCOPE_SOURCE,
        'cycle_game_count': 1,
        'requested_game_pks': [930001],
        'requested_game_count': 1,
        'excluded_game_pks': [],
        'excluded_reason_counts': {},
        'slate_dates': ['2026-06-20'],
        'execution_scope_mode': 'exclusive',
        'planned_game_pks': [930001],
        'planned_game_count': 1,
        'missing_requested_game_pks': [],
        'unexpected_planned_game_pks': [],
        'execution_scope_exact_match': True,
    }
    scope.update(overrides)
    return scope


def _scoped_postgame(**lane_overrides):
    base = dict(
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        realization=None,
        execution_scope=_scope(),
    )
    base.update(lane_overrides)
    return _lane(**base)


def test_a_clean_exact_scope_postgame_cycle_passes():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame()), 'postgame',
    )
    assert decision['result'] == PASS


def test_a_clean_multi_game_exact_scope_cycle_passes():
    scope = _scope(
        cycle_game_count=3, requested_game_pks=[930001, 930002, 930003],
        requested_game_count=3, planned_game_pks=[930001, 930002, 930003],
        planned_game_count=3,
    )
    games = [
        {'game_pk': pk, 'source_revision': f'r{pk}',
         'reconciliation_plan_fingerprint': 'b' * 64}
        for pk in (930001, 930002, 930003)
    ]
    lane = _scoped_postgame(
        execution_scope=scope, games=games, games_planned=3,
        games_attempted=3, games_fetched=3, games_completed=3,
        rows_expected=6, rows_unchanged=6,
    )
    assert _validate(_summary('postgame', lane=lane), 'postgame')['result'] == PASS


def test_a_missing_scope_section_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(execution_scope={})),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_missing' in _invariants(decision)


def test_a_wrong_scope_source_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(scope_source='seven_day_horizon'),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_source' in _invariants(decision)


def test_a_correction_horizon_fan_out_fails():
    """The exact production failure, as a validator case."""
    scope = _scope(
        cycle_game_count=25, requested_game_pks=[930001],
        requested_game_count=1, planned_game_count=112,
        planned_game_pks=list(range(930001, 930113)),
        unexpected_planned_game_pks=list(range(930002, 930113)),
        execution_scope_exact_match=False,
    )
    lane = _scoped_postgame(
        execution_scope=scope, games_planned=112, games_attempted=98,
        games_fetched=98, games_completed=98, games_remaining=14,
        budget_stop_triggered=True,
    )
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    failed = _invariants(decision)
    assert 'postgame_scope_fan_out' in failed
    assert 'postgame_scope_unexpected_planned_game' in failed
    assert 'postgame_scope_exact_match' in failed


def test_a_missing_requested_game_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(
                missing_requested_game_pks=[930009],
                execution_scope_exact_match=False,
            ),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_missing_requested_game' in _invariants(decision)


def test_an_unexpected_planned_game_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(
                unexpected_planned_game_pks=[930099],
                execution_scope_exact_match=False,
            ),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_unexpected_planned_game' in _invariants(decision)


def test_exact_scope_match_false_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(execution_scope_exact_match=False),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_exact_match' in _invariants(decision)


def test_a_duplicate_requested_game_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(
                requested_game_pks=[930001, 930001], requested_game_count=2,
                cycle_game_count=2,
            ),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_duplicate_request' in _invariants(decision)


def test_a_non_deterministic_scope_order_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(
                requested_game_pks=[930003, 930001], requested_game_count=2,
                cycle_game_count=2, planned_game_count=2,
            ),
            games_planned=2, games_attempted=2, games_fetched=2,
            games_completed=2,
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_not_deterministic' in _invariants(decision)


def test_a_scope_count_mismatch_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(requested_game_count=7),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_count_mismatch' in _invariants(decision)


def test_a_scope_larger_than_the_cycle_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(
                cycle_game_count=1, requested_game_pks=[930001, 930002],
                requested_game_count=2, planned_game_count=2,
            ),
            games_planned=2, games_attempted=2, games_fetched=2,
            games_completed=2,
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_exceeds_cycle' in _invariants(decision)


def test_an_unaccounted_cycle_game_fails():
    """Every cycle game is requested or excluded. Vanishing is not allowed."""
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(cycle_game_count=5),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_accounting' in _invariants(decision)


def test_an_unnamed_exclusion_fails():
    decision = _validate(
        _summary('postgame', lane=_scoped_postgame(
            execution_scope=_scope(
                cycle_game_count=2,
                excluded_game_pks=[{'game_pk': 930002}],
            ),
        )),
        'postgame',
    )
    assert decision['result'] == FAILED
    assert 'postgame_scope_unnamed_exclusion' in _invariants(decision)


def test_named_exclusions_pass():
    lane = _scoped_postgame(
        execution_scope=_scope(
            cycle_game_count=3,
            excluded_game_pks=[
                {'game_pk': 930002, 'reason': 'incomplete_after_writer'},
                {'game_pk': 930003, 'reason': 'failed_marker'},
            ],
            excluded_reason_counts={
                'incomplete_after_writer': 1, 'failed_marker': 1,
            },
        ),
    )
    assert _validate(_summary('postgame', lane=lane), 'postgame')['result'] == PASS


def test_a_zero_candidate_postgame_cycle_passes_with_no_candidates():
    scope = _scope(
        cycle_game_count=0, requested_game_pks=[], requested_game_count=0,
        planned_game_pks=[], planned_game_count=0,
        execution_scope_exact_match=None,
    )
    lane = _scoped_postgame(
        execution_scope=scope, games_discovered=0, games_planned=0,
        games_attempted=0, games_fetched=0, games_completed=0,
        newly_final_count=0, rows_expected=0, rows_unchanged=0, games=[],
        reconciliation_plan_fingerprint=None,
    )
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == PASS
    assert decision['work_state'] == validator.WORK_STATE_NO_CANDIDATES


def test_the_scope_source_constant_is_imported_from_the_service():
    from services import sync as sync_service

    assert validator.POSTGAME_SCOPE_SOURCE is sync_service.POSTGAME_SCOPE_SOURCE


# ── Safe diagnostics are required for any nonzero projection ────────────────


def _difference(**overrides):
    entry = {
        'game_pk': 930001,
        'pitcher_mlb_id': 8001,
        'action': 'update',
        'changed_fields': ['earned_runs'],
        'difference_classifications': ['statistical_correction'],
        'blocked_reason': None,
        'pitcher_identity_action': 'unchanged',
        'source_revision': 'rev-1',
        'reconciliation_plan_fingerprint': 'b' * 64,
        'target_state_digest': 'a' * 32,
        'stored_state_digest': 'c' * 32,
    }
    entry.update(overrides)
    return entry


def test_a_nonzero_projection_without_diagnostics_fails():
    """The first cycle reported one update and nothing about which row."""
    lane = _scoped_postgame(rows_updated=1, rows_unchanged=1, rows_expected=2)
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    assert 'projected_difference_diagnostics_missing' in _invariants(decision)


def test_incomplete_diagnostics_fail():
    lane = _scoped_postgame(
        rows_updated=2, rows_unchanged=0, rows_expected=2,
        projected_differences=[_difference()],
    )
    decision = _validate(_summary('postgame', lane=lane), 'postgame')
    assert decision['result'] == FAILED
    assert 'projected_difference_diagnostics_incomplete' in _invariants(decision)


@pytest.mark.parametrize('field', validator.DIFFERENCE_REQUIRED_FIELDS)
def test_a_diagnostic_missing_a_required_field_fails(field):
    entry = _difference()
    entry.pop(field)
    lane = _lane(
        rows_updated=1, rows_unchanged=1, rows_expected=2,
        projected_differences=[entry],
        realization=_realization(
            projected_updates=1, projected_unchanged=1, projected_rows=2,
            realized_updates=1, realized_rows=1, already_matching_rows=1,
        ),
    )
    decision = _validate(_summary('daily', lane=lane))
    assert decision['result'] == FAILED
    assert f'projected_difference_missing_field:{field}' in _invariants(decision)


@pytest.mark.parametrize('field', validator.DIFFERENCE_FORBIDDEN_FIELDS)
def test_a_diagnostic_carrying_raw_values_fails(field):
    entry = _difference(**{field: 'anything at all'})
    lane = _lane(
        rows_updated=1, rows_unchanged=1, rows_expected=2,
        projected_differences=[entry],
        realization=_realization(
            projected_updates=1, projected_unchanged=1, projected_rows=2,
            realized_updates=1, realized_rows=1, already_matching_rows=1,
        ),
    )
    decision = _validate(_summary('daily', lane=lane))
    assert decision['result'] == FAILED
    assert f'projected_difference_carries_values:{field}' in _invariants(decision)


def test_a_clean_cycle_needs_no_diagnostics():
    """Nothing projected, nothing to explain."""
    assert _validate(
        _summary('postgame', lane=_scoped_postgame()), 'postgame',
    )['result'] == PASS


def test_a_daily_projection_with_full_diagnostics_passes():
    lane = _lane(
        rows_updated=1, rows_unchanged=1, rows_expected=2,
        projected_differences=[_difference()],
        realization=_realization(
            projected_updates=1, projected_unchanged=1, projected_rows=2,
            realized_updates=1, realized_rows=1, already_matching_rows=1,
        ),
    )
    assert _validate(_summary('daily', lane=lane))['result'] == PASS
