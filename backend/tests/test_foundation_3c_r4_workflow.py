"""Foundation 3C — the R4 controlled write and immediate replay.

R4 is the first stage that writes. It may change exactly one thing: governed
ingestion control state. Five work items complete and publication completeness
moves 5/104 -> 10/99. No GameLog row, no Pitcher row, no appearance-team field,
no correction provenance, and no dead letter may change.

Authorization is a single hard-coded contract-4 fingerprint compared before the
first mutation. The contract-3 value R3 originally produced is stale after the
identity-coverage repair and must never authorize anything.

The canonical writer commits PER GAME, so partial completion is genuinely
reachable and is a FAILED result rather than something to paper over.
"""

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database, create_test_schema, drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from scripts import validate_r4_controlled_write as validator
from services import appearance_team_authority
from services import game_driven_ingestion
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as identity
from services import sync as sync_service
from services.roster_status import STATUS_ACTIVE, STATUS_MINORS
from tests.game_driven_fixtures import (
    AWAY_TEAM,
    HOME_TEAM,
    REFERENCE,
    BoxscoreClient,
    boxscore,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / '.github' / 'workflows'
    / 'foundation-3c-r4-controlled-write.yml'
)
APPROVED_GAME_PKS = (823110, 825055, 824004, 823438, 824408)
APPROVED_FINGERPRINT = (
    '08bf16bc730ffe4c5c024c8e1dbc000d017a1a4956878f49a988fb22a1e4adda'
)
STALE_FINGERPRINT = (
    '2a06f7e5b1aad853c6280ae3488a88f39ba0402cfb0b8044f0ba75d7be20c239'
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    # Declared in backend/requirements.txt. Imported here so a missing parser
    # can neither abort collection nor skip: these tests error loudly instead.
    import yaml

    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def job(workflow):
    jobs = workflow['jobs']
    assert len(jobs) == 1
    return next(iter(jobs.values()))


@pytest.fixture(scope='module')
def run_commands(job):
    lines = []
    for step in job['steps']:
        for line in (step.get('run') or '').splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                lines.append(stripped)
    return lines


@pytest.fixture(scope='module')
def ingestion_commands(run_commands):
    return [
        line for line in run_commands if 'game_driven_ingestion.py' in line
    ]


# ═══════════════ Parser-independent guards ══════════════════════════════════


PREFLIGHT_COMMAND = (
    'python backend/scripts/game_driven_ingestion.py '
    '--mode shadow --reference-date 2026-07-29 '
    '--only-game-pk 823110 --only-game-pk 825055 --only-game-pk 824004 '
    '--only-game-pk 823438 --only-game-pk 824408 '
    '--output "$PREFLIGHT_PATH"'
)
WRITE_COMMAND = (
    'python backend/scripts/game_driven_ingestion.py '
    '--mode write --reference-date 2026-07-29 '
    '--only-game-pk 823110 --only-game-pk 825055 --only-game-pk 824004 '
    '--only-game-pk 823438 --only-game-pk 824408 '
    f'--expected-plan-fingerprint {APPROVED_FINGERPRINT} '
    '--output "$WRITE_PATH"'
)
REPLAY_COMMAND = (
    'python backend/scripts/game_driven_ingestion.py '
    '--mode shadow --reference-date 2026-07-29 '
    '--only-game-pk 823110 --only-game-pk 825055 --only-game-pk 824004 '
    '--only-game-pk 823438 --only-game-pk 824408 '
    '--output "$REPLAY_PATH"'
)


@pytest.mark.parametrize('command', [
    PREFLIGHT_COMMAND, WRITE_COMMAND, REPLAY_COMMAND,
])
def test_each_pinned_command_appears_verbatim(workflow_text, command):
    assert command in workflow_text


def test_there_are_exactly_three_ingestion_invocations(workflow_text):
    assert workflow_text.count('game_driven_ingestion.py') == 3


def test_there_is_exactly_one_write_mode_invocation(workflow_text):
    assert workflow_text.count('--mode write') == 1


def test_the_approved_fingerprint_appears_once_as_the_authorization(
    workflow_text,
):
    assert workflow_text.count(APPROVED_FINGERPRINT) == 1
    assert f'--expected-plan-fingerprint {APPROVED_FINGERPRINT}' in workflow_text


def test_the_stale_contract_3_fingerprint_never_appears(workflow_text):
    """It cannot be a default, a fallback, or an alternate path."""
    assert STALE_FINGERPRINT not in workflow_text


def test_the_only_trigger_line_is_workflow_dispatch(workflow_text):
    triggers = workflow_text.split('\non:\n')[1].split('\nconcurrency:')[0]
    assert triggers.strip() == 'workflow_dispatch:'


@pytest.mark.parametrize('forbidden', [
    'schedule:', 'cron:', 'pull_request:', 'workflow_call:',
    'repository_dispatch:', 'inputs:',
])
def test_no_self_firing_or_editable_surface_exists(workflow_text, forbidden):
    assert forbidden not in workflow_text


def test_the_file_declares_read_only_permissions(workflow_text):
    assert '\npermissions:\n  contents: read\n' in workflow_text


@pytest.mark.parametrize('forbidden', [
    '--mode authoritative', '--max-games', '--include-backfill',
    '--time-budget-seconds', '--plan-only',
])
def test_no_widening_or_authoritative_option_appears(workflow_text, forbidden):
    assert forbidden not in workflow_text


def test_no_additive_game_pk_flag_appears(workflow_text):
    assert '--game-pk ' not in workflow_text.replace('--only-game-pk ', '')


def test_the_automated_lane_stays_off_in_the_file(workflow_text):
    assert "GAME_DRIVEN_INGESTION_MODE: 'off'" in workflow_text
    assert "AUTO_SYNC: 'false'" in workflow_text


# ═══════════════ Structural guards ══════════════════════════════════════════


def test_the_workflow_parses(workflow):
    assert workflow['name'] == 'Foundation 3C R4 Controlled Write and Replay'


def test_the_only_trigger_is_manual_dispatch(workflow):
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}
    assert not (triggers.get('workflow_dispatch') or {})


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


@pytest.mark.parametrize('scope', [
    'actions', 'checks', 'statuses', 'pull-requests', 'issues', 'deployments',
    'packages', 'id-token',
])
def test_no_additional_permission_is_requested(workflow, scope):
    assert scope not in workflow['permissions']


def test_the_job_is_bounded(job):
    assert isinstance(job['timeout-minutes'], int)
    assert 0 < job['timeout-minutes'] <= 30


def test_it_serializes_against_the_production_write_group(workflow):
    """R4 writes production state, so it must not race the scheduled sync."""
    assert workflow['concurrency']['group'] == 'baseballos-sync'
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_the_workflow_uses_the_established_production_secrets(job):
    env = job['env']
    assert env['DATABASE_URL'] == '${{ secrets.DATABASE_URL }}'
    assert env['SECRET_KEY'] == '${{ secrets.SECRET_KEY }}'
    assert env['ADMIN_API_TOKEN'] == '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'
    assert env['GAME_DRIVEN_INGESTION_MODE'] == 'off'
    assert env['AUTO_SYNC'] == 'false'


@pytest.mark.parametrize('forbidden', [
    'render', 'vercel', 'deploy', 'run_daily_sync', 'run_postgame_refresh',
    'refresh_slate_schedule', 'publish', 'snapshot', 'cache_warm',
    'share_artifact',
])
def test_no_deployment_or_publication_command_is_executed(run_commands, forbidden):
    for line in run_commands:
        assert forbidden not in line.lower(), line


def test_the_workflow_calls_only_the_three_approved_scripts(run_commands):
    scripts = {
        part for line in run_commands for part in line.split()
        if part.endswith('.py')
    }
    assert scripts == {
        'backend/scripts/game_driven_ingestion.py',
        'backend/scripts/inspect_r4_controlled_state.py',
        'backend/scripts/validate_r4_controlled_write.py',
    }


def _step_index(steps, predicate):
    return next(i for i, step in enumerate(steps) if predicate(step))


def test_the_step_order_puts_authorization_before_the_write(job):
    steps = job['steps']
    before = _step_index(steps, lambda s: s.get('id') == 'before')
    preflight = _step_index(steps, lambda s: s.get('id') == 'preflight')
    authorize = _step_index(steps, lambda s: s.get('id') == 'authorize')
    write = _step_index(steps, lambda s: s.get('id') == 'write')
    after = _step_index(steps, lambda s: s.get('id') == 'after')
    replay = _step_index(steps, lambda s: s.get('id') == 'replay')
    assert before < preflight < authorize < write < after < replay


def test_the_write_cannot_run_unless_authorization_succeeded(job):
    write = next(step for step in job['steps'] if step.get('id') == 'write')
    assert write['if'] == "${{ steps.authorize.outputs.authorize_exit == '0' }}"


def test_the_preflight_cannot_run_unless_the_before_state_succeeded(job):
    step = next(s for s in job['steps'] if s.get('id') == 'preflight')
    assert step['if'] == "${{ steps.before.outputs.before_exit == '0' }}"


@pytest.mark.parametrize('step_id', ['after', 'replay'])
def test_state_capture_and_replay_survive_a_failed_write(job, step_id):
    step = next(s for s in job['steps'] if s.get('id') == step_id)
    assert step['if'].startswith('${{ always() &&')
    assert 'authorize' in step['if']


def test_the_scan_runs_before_the_upload_and_the_gate_after_it(job):
    steps = job['steps']
    scan = _step_index(steps, lambda s: 'credential-shaped' in (s.get('name') or ''))
    upload = _step_index(
        steps, lambda s: str(s.get('uses') or '').startswith('actions/upload-artifact')
    )
    gate = len(steps) - 1
    assert scan < upload < gate
    assert steps[gate]['if'] == '${{ always() }}'


def test_artifacts_upload_even_when_the_run_fails(job):
    upload = next(
        step for step in job['steps']
        if str(step.get('uses') or '').startswith('actions/upload-artifact')
    )
    assert upload['if'] == '${{ always() }}'
    assert upload['with']['name'] == (
        'foundation-3c-r4-controlled-write-and-replay'
    )
    assert upload['with']['retention-days'] == 30
    assert upload['with']['if-no-files-found'] == 'warn'


@pytest.mark.parametrize('artifact', [
    'r4-before-state.json', 'r4-preflight-shadow.json',
    'r4-controlled-write.json', 'r4-after-state.json',
    'r4-postwrite-replay.json', 'r4-validation-summary.json',
    'r4-validation-summary.md', 'r4-closeout.json', 'r4-closeout.md',
])
def test_every_required_artifact_is_produced(job, artifact):
    assert any(artifact in str(value) for value in job['env'].values())


def test_every_shell_block_is_valid_bash(job):
    for step in job['steps']:
        script = step.get('run')
        if not script:
            continue
        result = subprocess.run(
            ['bash', '-n'], input=script, text=True, capture_output=True,
        )
        assert result.returncode == 0, step.get('name')


def test_the_summary_fallback_never_claims_no_database_writes(workflow_text):
    """R4 writes checkpoint state; saying otherwise would be a lie."""
    assert 'No database writes were performed' not in workflow_text


# ═══════════════ The inline credential scanner ══════════════════════════════


def _run_scanner(workflow_text, directory, monkeypatch):
    body = workflow_text.split("<<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    monkeypatch.chdir(directory)
    try:
        exec(compile(textwrap.dedent(body), 'scan', 'exec'), {})
    except SystemExit as exit_signal:
        return int(exit_signal.code or 0)
    return 0


def test_the_scanner_passes_a_clean_artifact_set(
    workflow_text, tmp_path, monkeypatch,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'r4-closeout.json').write_text(json.dumps({
        'result': 'pass', 'baseball_data_rows_changed': False,
        'approved_fingerprint': APPROVED_FINGERPRINT,
    }))
    assert _run_scanner(workflow_text, tmp_path, monkeypatch) == 0
    assert (artifacts / 'r4-closeout.json').exists()


@pytest.mark.parametrize('poison', [
    'postgresql://user:pw@host/db', 'password=hunter2',
    'X-Admin-Token: abc', 'api_key=abc123',
])
def test_the_scanner_deletes_and_fails_on_credential_content(
    workflow_text, tmp_path, monkeypatch, poison,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    unsafe = artifacts / 'r4-after-state.json'
    unsafe.write_text(poison)
    assert _run_scanner(workflow_text, tmp_path, monkeypatch) == 1
    assert not unsafe.exists()


# ═══════════════ Report builders ════════════════════════════════════════════


def _row(game_pk, pitcher, *, ignored=0, suppressed=()):
    return {
        'game_pk': game_pk,
        'pitcher_mlb_id': pitcher,
        'action': 'unchanged',
        'changed_fields': [],
        'changed_field_count': 0,
        'mutation_categories': ['unchanged_row'],
        'is_statistical_correction': False,
        'affects_published_evidence': False,
        'is_provenance_only': False,
        'governed_and_safe': True,
        'blocked_reason': None,
        'mutation_digest': '',
        'semantic_changed_fields': [],
        'applied_changed_fields': [],
        'derived_companion_fields': [],
        'derived_companion_differences_ignored': (
            ['innings_pitched'] if ignored else []
        ),
        'appearance_team_reason': None,
        'pitcher_identity_action': identity.ACTION_UNCHANGED,
        'pitcher_identity_changed_fields': [],
        'pitcher_identity_applied_fields': [],
        'pitcher_identity_suppressed_fields': sorted(suppressed),
        'pitcher_identity_governed_and_safe': True,
        'pitcher_identity_blocked_reason': None,
        'pitcher_identity_mutation_digest': '',
        'pitcher_identity_requires_creation': False,
        'pitcher_identity_current_authority_mutation_refused': bool(suppressed),
    }


def _game(game_pk, *, status='projected', attempt=1):
    rows_expected = validator.EXPECTED_ROWS_BY_GAME[game_pk]
    ignored = validator.EXPECTED_IGNORED_BY_GAME[game_pk]
    rows = [
        _row(game_pk, game_pk * 10 + index,
             ignored=1 if index < ignored else 0,
             suppressed=['team_id'] if index == 0 else ())
        for index in range(rows_expected)
    ]
    return {
        'game_pk': game_pk,
        'represented_date': '2026-07-28',
        'candidate_reason': 'explicit_repair',
        'criticality': 'publication_critical',
        'attempt_number': attempt,
        'status': status,
        'source_revision': f'rev{game_pk}',
        'appearances_extracted': rows_expected,
        'inserted': 0,
        'updated': 0,
        'unchanged': rows_expected,
        'blocked': 0,
        'derived_companion_differences_ignored': ignored,
        'canonical_outs_corrections': 0,
        'pitcher_identity_mutations': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'complete_reconciliation_fingerprint': 'f' * 64,
        'rows': rows,
        'error_class': None,
    }


def _shadow_report(*, mode='shadow', attempt=1, status='projected',
                   fingerprint=APPROVED_FINGERPRINT):
    games = [_game(pk, status=status, attempt=attempt) for pk in APPROVED_GAME_PKS]
    approved = sorted(APPROVED_GAME_PKS)
    return {
        'status': 'complete',
        'mode': mode,
        'reference_date': '2026-07-29',
        'execution_scope_mode': 'exclusive',
        'requested_game_pks': approved,
        'requested_game_count': 5,
        'duplicate_requested_count': 0,
        'planned_game_pks': approved,
        'planned_game_count': 5,
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'execution_scope_exact_match': True,
        'games_attempted': 5,
        'games_fetched': 5,
        'games_completed': 5,
        'games_failed': 0,
        'games_remaining': 0,
        'budget_stop_triggered': False,
        'budget_stop': None,
        'failure_classes': {},
        'finality_conflicts': 0,
        'schedule_authority_missing': 0,
        'rows_expected': 43,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': 43,
        'rows_blocked': 0,
        'changed_fields_counts': {},
        'derived_companion_differences_ignored': 18,
        'decimal_only_updates_suppressed': 18,
        'derived_companion_fields_applied': 0,
        'canonical_outs_corrections': 0,
        'statistical_corrections': 0,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_changed_fields_counts': {},
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'reconciliation_plan_version': reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        'complete_reconciliation_fingerprint': fingerprint,
        'games': games,
    }


def _write_report(*, completed=APPROVED_GAME_PKS,
                  supplied=APPROVED_FINGERPRINT,
                  authorized=APPROVED_FINGERPRINT):
    report = _shadow_report(mode='write', status='completed')
    report['expected_plan_fingerprint'] = supplied
    report['authorized_plan_fingerprint'] = authorized
    report['corrections_applied'] = 0
    report['games'] = [
        _game(pk, status='completed' if pk in completed else 'retryable_failure')
        for pk in APPROVED_GAME_PKS
    ]
    return report


def _state(phase, *, completed=False, **overrides):
    work_items = {}
    if completed:
        work_items = {
            str(pk): {
                'status': 'completed', 'attempt_count': 1,
                'candidate_reason': 'explicit_repair',
                'criticality': 'publication_critical',
                'rows_expected': validator.EXPECTED_ROWS_BY_GAME[pk],
                'rows_reconciled': validator.EXPECTED_ROWS_BY_GAME[pk],
                'correction_count': 0, 'error_class': None, 'completed': True,
            }
            for pk in APPROVED_GAME_PKS
        }
    completeness = (
        validator.AFTER_COMPLETENESS if completed
        else validator.BEFORE_COMPLETENESS
    )
    state = {
        'phase': phase,
        'read_only': {'write_probe_refused': True},
        'selected_game_pks': sorted(APPROVED_GAME_PKS),
        'game_log_row_count': 43,
        'game_log_content_hash': 'a' * 64,
        'correction_provenance_hash': 'b' * 64,
        'appearance_team_hash': 'c' * 64,
        'pitcher_state_hash': 'd' * 64,
        'pitcher_count': 43,
        'pitcher_mlb_ids': list(range(43)),
        'selected_work_items': work_items,
        'selected_completed_count': 5 if completed else 0,
        'all_work_items_hash': 'e' * 64,
        'all_work_item_count': 105 if completed else 100,
        'dead_letter_count': 0,
        'publication_completeness': dict(completeness),
    }
    state.update(overrides)
    return state


def _closeout(**overrides):
    kwargs = {
        'before_state': _state('before'),
        'preflight': _shadow_report(),
        'write': _write_report(),
        'after_state': _state('after', completed=True),
        'replay': _shadow_report(attempt=2),
        'write_exit': 0,
    }
    kwargs.update(overrides)
    return kwargs


def _failure(**overrides):
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_closeout(**_closeout(**overrides))
    return caught.value


# ═══════════════ Authorization ══════════════════════════════════════════════


def test_the_exact_contract_4_preflight_authorizes_the_write():
    result = validator.validate_preflight(_state('before'), _shadow_report())
    assert result['result'] == validator.RESULT_PASS
    assert result['authorized'] is True
    assert result['observed_fingerprint'] == APPROVED_FINGERPRINT
    assert result['stale_contract_3_fingerprint_rejected'] is True


def test_a_fingerprint_mismatch_refuses_before_the_write():
    report = _shadow_report(fingerprint='0' * 64)
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), report)
    assert caught.value.invariant == 'preflight_complete_reconciliation_fingerprint'


def test_the_stale_contract_3_fingerprint_is_named_and_refused():
    report = _shadow_report(fingerprint=STALE_FINGERPRINT)
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), report)
    assert 'stale_contract_3' in caught.value.invariant


def test_a_stale_fingerprint_supplied_to_the_write_is_refused():
    failure = _failure(write=_write_report(supplied=STALE_FINGERPRINT))
    assert 'stale_contract_3' in failure.invariant


def test_an_unproven_authorization_fails_even_on_a_zero_exit():
    """Exit zero is not evidence that the fingerprint was ever compared."""
    write = _write_report()
    del write['authorized_plan_fingerprint']
    failure = _failure(write=write)
    assert failure.invariant == 'write_authorized_plan_fingerprint'


def test_the_parity_contract_must_be_version_four():
    report = _shadow_report()
    report['parity_contract_version'] = '3'
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), report)
    assert 'parity_contract_version' in caught.value.invariant


# ═══════════════ Single use ═════════════════════════════════════════════════


def test_an_existing_work_item_refuses_the_write():
    """A second dispatch after a successful R4 stops here."""
    before = _state('before', completed=True)
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(before, _shadow_report())
    assert caught.value.invariant == 'before_state_no_selected_work_item_exists'


def test_a_second_attempt_in_the_preflight_refuses_the_write():
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), _shadow_report(attempt=2))
    assert 'attempt_number' in caught.value.invariant


@pytest.mark.parametrize('field,value', [
    ('expected_final_games', 110),
    ('completed_final_games', 10),
    ('unresolved_final_games', 99),
    ('terminal_failure_games', 1),
])
def test_a_changed_bootstrap_population_refuses_the_write(field, value):
    before = _state('before')
    before['publication_completeness'][field] = value
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(before, _shadow_report())
    assert caught.value.invariant == f'before_state_completeness_{field}'


def test_a_before_state_without_read_only_proof_refuses_the_write():
    before = _state('before')
    before['read_only'] = {'write_probe_refused': False}
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(before, _shadow_report())
    assert caught.value.invariant == 'before_state_read_only'


# ═══════════════ Preflight scope and data ═══════════════════════════════════


@pytest.mark.parametrize('mutate,invariant', [
    (lambda r: r.update({'planned_game_pks': [1, 2, 3, 4, 5]}),
     'preflight_planned_game_pks'),
    (lambda r: r.update({'requested_game_pks': [1, 2, 3, 4, 5]}),
     'preflight_requested_game_pks'),
    (lambda r: r.update({'unexpected_planned_game_pks': [9]}),
     'preflight_unexpected_planned_game_pks'),
    (lambda r: r.update({'missing_requested_game_pks': [823110]}),
     'preflight_missing_requested_game_pks'),
    (lambda r: r.update({'duplicate_requested_count': 1}),
     'preflight_duplicate_requested_count'),
    (lambda r: r.update({'execution_scope_mode': 'window'}),
     'preflight_execution_scope_mode'),
    (lambda r: r.update({'rows_expected': 44}), 'preflight_rows_expected'),
    (lambda r: r.update({'rows_updated': 1}), 'preflight_rows_updated'),
    (lambda r: r.update({'rows_inserted': 1}), 'preflight_rows_inserted'),
    (lambda r: r.update({'rows_blocked': 1}), 'preflight_rows_blocked'),
    (lambda r: r.update({'derived_companion_differences_ignored': 17}),
     'preflight_derived_companion_differences_ignored'),
    (lambda r: r.update({'pitcher_identity_mutations': 1}),
     'preflight_pitcher_identity_mutations'),
    (lambda r: r.update({'appearance_team_mutations': 1}),
     'preflight_appearance_team_mutations'),
    (lambda r: r.update({'complete_mutation_count': 1}),
     'preflight_complete_mutation_count'),
    (lambda r: r.update({'changed_fields_counts': {'earned_runs': 1}}),
     'preflight_changed_fields_counts'),
    (lambda r: r.update({'games_failed': 1}), 'preflight_games_failed'),
    (lambda r: r.update({'budget_stop_triggered': True}),
     'preflight_budget_stop_triggered'),
])
def test_a_broken_preflight_invariant_refuses_the_write(mutate, invariant):
    report = _shadow_report()
    mutate(report)
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), report)
    assert caught.value.invariant == invariant


def test_a_wrong_per_game_row_count_refuses_the_write():
    report = _shadow_report()
    report['games'][0]['appearances_extracted'] = 7
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), report)
    assert caught.value.invariant == 'preflight_game_823110_appearances'


@pytest.mark.parametrize('action', [
    'create_minimal_identity', 'reactivate', 'update_metadata', 'blocked',
])
def test_a_row_level_identity_write_refuses_the_write(action):
    report = _shadow_report()
    report['games'][0]['rows'][0]['pitcher_identity_action'] = action
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_preflight(_state('before'), report)
    assert 'pitcher_identity_action' in caught.value.invariant


def test_suppressed_historical_differences_are_permitted():
    result = validator.validate_preflight(_state('before'), _shadow_report())
    assert result['suppressed_historical_differences'] == 5


# ═══════════════ Write and state transition ═════════════════════════════════


def test_the_exact_closeout_passes():
    decision = validator.validate_closeout(**_closeout())
    assert decision['result'] == validator.RESULT_PASS
    assert decision['write']['completed_games'] == sorted(APPROVED_GAME_PKS)
    assert decision['transition']['newly_completed_checkpoints'] == 5
    assert decision['transition']['completed_after'] == 10
    assert decision['transition']['unresolved_after'] == 99


def test_a_nonzero_write_exit_fails():
    assert _failure(write_exit=1).invariant == 'write_command_exit_code'


def test_partial_completion_fails():
    """The writer commits per game, so this is genuinely reachable."""
    failure = _failure(write=_write_report(completed=APPROVED_GAME_PKS[:3]))
    assert 'completed' in failure.invariant


def test_a_write_game_failure_fails():
    write = _write_report()
    write['games_failed'] = 1
    assert _failure(write=write).invariant == 'write_games_failed'


@pytest.mark.parametrize('field', [
    'game_log_content_hash', 'correction_provenance_hash',
    'appearance_team_hash', 'pitcher_state_hash',
])
def test_any_baseball_data_hash_change_fails(field):
    after = _state('after', completed=True)
    after[field] = 'x' * 64
    assert _failure(after_state=after).invariant == f'state_{field}_unchanged'


def test_a_dead_letter_increase_fails():
    after = _state('after', completed=True)
    after['dead_letter_count'] = 1
    assert _failure(after_state=after).invariant == (
        'state_dead_letter_count_unchanged'
    )


def test_an_unexpected_work_item_fails():
    after = _state('after', completed=True)
    after['all_work_item_count'] = 106
    assert _failure(after_state=after).invariant == (
        'state_no_unexpected_work_item_created'
    )


def test_a_missing_selected_checkpoint_fails():
    after = _state('after', completed=True)
    after['selected_work_items'].pop(str(APPROVED_GAME_PKS[0]))
    assert _failure(after_state=after).invariant == (
        'state_selected_work_item_set'
    )


@pytest.mark.parametrize('field,value', [
    ('completed_final_games', 9),
    ('unresolved_final_games', 100),
    ('expected_final_games', 110),
    ('terminal_failure_games', 1),
])
def test_a_wrong_completeness_transition_fails(field, value):
    after = _state('after', completed=True)
    after['publication_completeness'][field] = value
    assert _failure(after_state=after).invariant == (
        f'after_state_completeness_{field}'
    )


# ═══════════════ Replay ═════════════════════════════════════════════════════


def test_the_replay_may_report_a_later_attempt_number():
    """The write leaves work items behind; that is the point."""
    decision = validator.validate_closeout(**_closeout(
        replay=_shadow_report(attempt=3),
    ))
    assert decision['result'] == validator.RESULT_PASS


@pytest.mark.parametrize('mutate,fragment', [
    (lambda r: r.update({'rows_updated': 1}), 'replay_rows_updated'),
    (lambda r: r.update({'rows_inserted': 1}), 'replay_rows_inserted'),
    (lambda r: r.update({'rows_blocked': 1}), 'replay_rows_blocked'),
    (lambda r: r.update({'rows_expected': 42}), 'replay_rows_expected'),
    (lambda r: r.update({'pitcher_identity_mutations': 1}),
     'replay_pitcher_identity_mutations'),
    (lambda r: r.update({'appearance_team_mutations': 1}),
     'replay_appearance_team_mutations'),
    (lambda r: r.update({'canonical_outs_corrections': 1}),
     'replay_canonical_outs_corrections'),
    (lambda r: r.update({'derived_companion_differences_ignored': 17}),
     'replay_derived_companion_differences_ignored'),
    (lambda r: r.update({'changed_fields_counts': {'innings_pitched': 1}}),
     'replay_changed_fields_counts'),
])
def test_a_replay_mutation_fails(mutate, fragment):
    replay = _shadow_report(attempt=2)
    mutate(replay)
    assert _failure(replay=replay).invariant == fragment


def test_a_missing_replay_fingerprint_fails():
    replay = _shadow_report(attempt=2)
    replay['complete_reconciliation_fingerprint'] = None
    assert _failure(replay=replay).invariant == (
        'replay_complete_reconciliation_fingerprint'
    )


def test_the_replay_fingerprint_must_reproduce_the_approved_plan():
    """The fingerprint covers the PLAN, not the checkpoint, so it converges."""
    replay = _shadow_report(attempt=2, fingerprint='9' * 64)
    assert _failure(replay=replay).invariant == (
        'replay_fingerprint_matches_the_approved_plan'
    )


def test_the_fingerprint_is_checkpoint_state_independent():
    """Grounded in the planner: nothing in plan_fingerprint reads a work item."""
    import inspect as _inspect

    source = _inspect.getsource(reconciliation.plan_fingerprint)
    for token in ('work_item', 'checkpoint', 'attempt'):
        assert token not in source


# ═══════════════ Closeout output ════════════════════════════════════════════


def _run_closeout_cli(tmp_path, **overrides):
    kwargs = _closeout(**overrides)
    paths = {}
    for name, payload in (
        ('before', kwargs['before_state']), ('preflight', kwargs['preflight']),
        ('write', kwargs['write']), ('after', kwargs['after_state']),
        ('replay', kwargs['replay']),
    ):
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps(payload))
        paths[name] = str(path)
    return validator.main([
        'closeout',
        '--before-state', paths['before'],
        '--preflight', paths['preflight'],
        '--write', paths['write'],
        '--after-state', paths['after'],
        '--replay', paths['replay'],
        '--write-exit', str(kwargs['write_exit']),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--closeout-json', str(tmp_path / 'closeout.json'),
        '--closeout-markdown', str(tmp_path / 'closeout.md'),
        '--repository-sha', 'abc123',
        '--run-id', '42',
    ])


def test_a_passing_closeout_exits_zero_and_states_what_changed(tmp_path):
    assert _run_closeout_cli(tmp_path) == 0
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'FOUNDATION 3C R4 — PASS' in markdown
    # It must acknowledge the checkpoint write, and must not deny writing.
    assert 'Only governed checkpoint/work-item state changed.' in markdown
    assert 'No baseball-data rows were changed.' in markdown
    assert 'No database writes were performed' not in markdown
    assert 'Completed final games after: 10' in markdown
    assert 'Unresolved final games after: 99' in markdown
    assert 'remaining 99 unresolved games' in markdown

    closeout = json.loads((tmp_path / 'closeout.json').read_text())
    assert closeout['result'] == 'pass'
    assert closeout['baseball_data_rows_changed'] is False
    assert closeout['checkpoint_state_written'] is True
    assert closeout['authoritative_mode'] == 'unapproved'
    assert closeout['automated_lane'] == 'off'
    assert closeout['stale_contract_3_fingerprint_rejected'] is True
    assert closeout['next_action'].startswith('Implement R5')
    assert 'per_game' in closeout['transaction_boundary']


def test_a_failed_closeout_cannot_exit_zero(tmp_path):
    assert _run_closeout_cli(tmp_path, write_exit=1) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['failed_invariant'] == 'write_command_exit_code'
    assert summary['next_action'].startswith('Stop Foundation 3C')
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'FOUNDATION 3C R4 — FAILED' in markdown
    assert 'rollout stop' in markdown


def test_the_closeout_is_deterministic(tmp_path):
    first = tmp_path / 'a'
    second = tmp_path / 'b'
    first.mkdir()
    second.mkdir()
    _run_closeout_cli(first)
    _run_closeout_cli(second)
    assert (first / 'closeout.json').read_text() == (
        (second / 'closeout.json').read_text()
    )


@pytest.mark.parametrize('forbidden', [
    'postgresql://', 'postgres://', 'password=', 'Authorization:',
    'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL', 'Traceback',
    os.sep + 'home' + os.sep,
])
def test_no_output_can_carry_a_credential_or_a_raw_error(tmp_path, forbidden):
    _run_closeout_cli(tmp_path)
    for name in ('summary.json', 'summary.md', 'closeout.json', 'closeout.md'):
        assert forbidden not in (tmp_path / name).read_text()


def test_the_preflight_cli_refuses_a_stale_fingerprint(tmp_path):
    (tmp_path / 'before.json').write_text(json.dumps(_state('before')))
    (tmp_path / 'pre.json').write_text(
        json.dumps(_shadow_report(fingerprint=STALE_FINGERPRINT))
    )
    assert validator.main([
        'preflight',
        '--before-state', str(tmp_path / 'before.json'),
        '--preflight', str(tmp_path / 'pre.json'),
    ]) == 1


def test_the_preflight_cli_authorizes_the_approved_plan(tmp_path):
    (tmp_path / 'before.json').write_text(json.dumps(_state('before')))
    (tmp_path / 'pre.json').write_text(json.dumps(_shadow_report()))
    assert validator.main([
        'preflight',
        '--before-state', str(tmp_path / 'before.json'),
        '--preflight', str(tmp_path / 'pre.json'),
    ]) == 0


# ═══════════════ Real pipeline ══════════════════════════════════════════════


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _stored_row(pitcher_row, game_pk, **overrides):
    values = {
        'pitcher_id': pitcher_row.id, 'mlb_game_pk': game_pk,
        'game_date': REFERENCE, 'game_type': 'R', 'opponent': 'Away Club',
        'opponent_abbreviation': 'AWY', 'games_started': 0,
        'innings_pitched': 1.0, 'innings_pitched_outs': 3, 'pitches_thrown': 15,
        'strikes': 10, 'hits_allowed': 1, 'runs_allowed': 0, 'earned_runs': 0,
        'walks': 0, 'strikeouts': 2, 'home_runs_allowed': 0, 'batters_faced': 4,
        'appearance_team_id': HOME_TEAM,
        'appearance_team_source': appearance_team_authority.SOURCE_BOXSCORE,
        'appearance_team_status': GameLog.APPEARANCE_TEAM_RESOLVED,
        'appearance_team_reason': (
            appearance_team_authority.REASON_RESOLVED_BOXSCORE
        ),
        'stat_correction_count': 0,
    }
    values.update(overrides)
    row = GameLog(**values)
    db.session.add(row)
    return row


def _build_sample():
    boxscores = {}
    for game_pk in APPROVED_GAME_PKS:
        _schedule(game_pk)
        rows = validator.EXPECTED_ROWS_BY_GAME[game_pk]
        drifted = validator.EXPECTED_IGNORED_BY_GAME[game_pk]
        lines = []
        for index in range(rows):
            mlb_id = game_pk * 10 + index
            arm = _pitcher(
                mlb_id, team_id=AWAY_TEAM if index % 2 else HOME_TEAM,
                active=index % 3 != 0,
            )
            arm.roster_status = STATUS_MINORS if index % 2 else STATUS_ACTIVE
            db.session.flush()
            if index < drifted:
                _stored_row(
                    arm, game_pk, innings_pitched_outs=1,
                    innings_pitched=0.333333, hits_allowed=0, strikeouts=1,
                    batters_faced=1, strikes=3, pitches_thrown=4,
                )
                lines.append((mlb_id, 'home', pitching_stats(
                    innings='0.1', hits=0, strikeouts=1, batters_faced=1,
                    strikes=3, pitches=4,
                )))
            else:
                _stored_row(arm, game_pk)
                lines.append((mlb_id, 'home', pitching_stats()))
        boxscores[game_pk] = boxscore(lines)
    db.session.commit()
    return boxscores


def _run(mode, **kwargs):
    return game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=mode, only_game_pks=list(APPROVED_GAME_PKS), **kwargs
    )


def test_the_real_write_changes_only_control_state(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_sample()),
        )
        from scripts import inspect_r4_controlled_state as inspector

        before = inspector.collect_state(APPROVED_GAME_PKS)
        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        assert preflight['rows_unchanged'] == 43
        assert preflight['complete_mutation_count'] == 0
        reviewed = preflight['complete_reconciliation_fingerprint']

        write = _run(
            game_driven_ingestion.MODE_WRITE,
            expected_plan_fingerprint=reviewed,
        )
        assert write['status'] == 'complete'
        assert write['games_completed'] == 5
        assert write['rows_inserted'] == 0
        assert write['rows_updated'] == 0
        assert write['authorized_plan_fingerprint'] == reviewed

        after = inspector.collect_state(APPROVED_GAME_PKS)

        # Baseball data byte-identical; control state advanced by exactly five.
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['dead_letter_count'] == before['dead_letter_count']
        assert after['selected_completed_count'] == 5
        assert after['all_work_item_count'] == before['all_work_item_count'] + 5

        replay = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        assert replay['rows_unchanged'] == 43
        assert replay['complete_mutation_count'] == 0
        assert replay['derived_companion_differences_ignored'] == 18
        # Convergence: the plan fingerprint does not read checkpoint state.
        assert replay['complete_reconciliation_fingerprint'] == reviewed


def test_a_wrong_fingerprint_refuses_the_write_and_changes_nothing(
    app, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_sample()),
        )
        from scripts import inspect_r4_controlled_state as inspector

        before = inspector.collect_state(APPROVED_GAME_PKS)
        refused = _run(
            game_driven_ingestion.MODE_WRITE,
            expected_plan_fingerprint='0' * 64,
        )
        assert refused['status'] == (
            game_driven_ingestion.STATUS_PLAN_FINGERPRINT_MISMATCH
        )
        assert inspector.collect_state(APPROVED_GAME_PKS) == before
        assert GameIngestionWorkItem.query.count() == 0


def test_the_stale_contract_3_fingerprint_refuses_the_real_write(
    app, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_sample()),
        )
        from scripts import inspect_r4_controlled_state as inspector

        before = inspector.collect_state(APPROVED_GAME_PKS)
        refused = _run(
            game_driven_ingestion.MODE_WRITE,
            expected_plan_fingerprint=STALE_FINGERPRINT,
        )
        assert refused['status'] == (
            game_driven_ingestion.STATUS_PLAN_FINGERPRINT_MISMATCH
        )
        assert inspector.collect_state(APPROVED_GAME_PKS) == before
        assert Pitcher.query.count() == before['pitcher_count']


def test_a_changed_identity_digest_moves_the_authorization(app, monkeypatch):
    """A creation reviewed for one pitcher must not authorize another."""
    with app.app_context():
        one = identity.plan_identity(
            existing=None, player_mlb_id=111, line_name='Arm One',
        )
        two = identity.plan_identity(
            existing=None, player_mlb_id=222, line_name='Arm Two',
        )
        values = {'innings_pitched_outs': 3, 'mlb_game_pk': 1}
        rows = [
            game_driven_ingestion._safe_row_entries([
                reconciliation.plan_row(
                    existing=None, values=values, stats={}, game_pk=1,
                    pitcher_mlb_id=99, identity_plan=plan,
                )
            ])
            for plan in (one, two)
        ]
        assert reconciliation.plan_fingerprint(rows[0]) != (
            reconciliation.plan_fingerprint(rows[1])
        )


def test_the_writer_commits_per_game(app, monkeypatch):
    """Documents the real transaction boundary rather than assuming atomicity."""
    import inspect as _inspect

    source = _inspect.getsource(game_driven_ingestion._process_one_game)
    assert source.count('db.session.commit()') == 1
    assert 'per_game' in validator.TRANSACTION_BOUNDARY


def test_a_failure_partway_through_leaves_earlier_games_committed(
    app, monkeypatch,
):
    """Per-game commits mean partial completion is real. R4 treats it FAILED."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_sample()),
        )
        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        reviewed = preflight['complete_reconciliation_fingerprint']

        real_verify = game_driven_ingestion._verify_game_completeness
        seen = []

        def _fail_on_third(item, appearances):
            seen.append(item.game_pk)
            if len(seen) == 3:
                raise RuntimeError('failure partway through')
            return real_verify(item, appearances)

        monkeypatch.setattr(
            game_driven_ingestion, '_verify_game_completeness', _fail_on_third,
        )
        report = _run(
            game_driven_ingestion.MODE_WRITE,
            expected_plan_fingerprint=reviewed,
        )

        assert report['games_failed'] == 1
        completed = GameIngestionWorkItem.query.filter_by(
            status=GameIngestionWorkItem.STATUS_COMPLETED
        ).count()
        assert completed == 4
        # The validator refuses this, which is the whole point.
        write_report = dict(report)
        with pytest.raises(validator.ValidationFailure):
            validator.validate_write(write_report, write_exit=0)
