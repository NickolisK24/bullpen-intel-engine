"""Foundation 3C — the manual R2 full-window shadow review workflow.

R2 is a rollout gate that will be run from a phone, with no inputs. These tests
pin what that means: one manual trigger, read-only permissions, the complete
governed window rather than a bounded sample, shadow mode only, no path to a
write or a deployment, a validator that fails closed, a three-way result model
where `review_required` approves nothing, and artifacts that survive a failure
without carrying a secret.

The parser import lives inside the fixture that needs it. PyYAML is a declared
dependency, so a missing parser is a defect — but it must not abort collection
of the whole suite, and it must not silently skip these guards either. The
highest-value invariants are additionally asserted against the raw file so they
hold with no parser at all.
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
from models.game_log import GameLog
from scripts import validate_r2_shadow_report as validator
from services import appearance_team_authority
from services import game_driven_ingestion
from services import game_ingestion_completeness
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from services import sync as sync_service
from tests.game_driven_fixtures import (
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
    REPO_ROOT / '.github' / 'workflows' / 'foundation-3c-r2-full-window-shadow.yml'
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    # Declared in backend/requirements.txt. Imported here rather than at module
    # scope so a missing parser can neither abort collection nor skip: these
    # tests error loudly instead.
    import yaml

    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def job(workflow):
    jobs = workflow['jobs']
    assert len(jobs) == 1, 'one job only'
    return next(iter(jobs.values()))


@pytest.fixture(scope='module')
def run_commands(job):
    """Only the executable shell of the workflow, never its comments."""
    lines = []
    for step in job['steps']:
        for line in (step.get('run') or '').splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                lines.append(stripped)
    return lines


@pytest.fixture(scope='module')
def step_names(job):
    return [step.get('name') or step.get('uses') for step in job['steps']]


# ═══════════════ 0. Parser-independent guards ═══════════════════════════════
#
# The invariants whose failure would be costliest: a trigger that fires itself,
# a mode that writes, a scope that narrows to a sample.


PINNED_INGESTION_COMMAND = (
    'python backend/scripts/game_driven_ingestion.py '
    '--mode shadow --reference-date 2026-07-29 --output "$REPORT_PATH"'
)


def test_the_pinned_command_appears_verbatim(workflow_text):
    assert PINNED_INGESTION_COMMAND in workflow_text


def test_the_pinned_command_is_the_only_ingestion_invocation(workflow_text):
    assert workflow_text.count('game_driven_ingestion.py') == 1


def test_the_only_trigger_line_is_workflow_dispatch(workflow_text):
    triggers = workflow_text.split('\non:\n')[1].split('\nconcurrency:')[0]
    assert triggers.strip() == 'workflow_dispatch:'


@pytest.mark.parametrize('forbidden', [
    'schedule:', 'cron:', 'pull_request:', 'workflow_call:',
    'repository_dispatch:', 'inputs:',
])
def test_no_self_firing_or_editable_surface_exists_in_the_file(
    workflow_text, forbidden,
):
    assert forbidden not in workflow_text


def test_the_file_declares_read_only_permissions(workflow_text):
    assert '\npermissions:\n  contents: read\n' in workflow_text
    assert 'permissions: write-all' not in workflow_text


@pytest.mark.parametrize('forbidden', [
    '--mode write', '--mode authoritative', '--expected-plan-fingerprint',
    '--max-games', '--include-backfill', '--game-pk', '--only-game-pk',
    '--time-budget-seconds', '--plan-only',
])
def test_no_write_widening_or_narrowing_option_appears_in_the_file(
    workflow_text, forbidden,
):
    assert forbidden not in workflow_text


def test_the_automated_lane_is_off_in_the_file(workflow_text):
    assert "GAME_DRIVEN_INGESTION_MODE: 'off'" in workflow_text
    assert "AUTO_SYNC: 'false'" in workflow_text


# ═══════════════ 1. Manual only ═════════════════════════════════════════════


def test_the_workflow_parses(workflow):
    assert workflow['name'] == 'Foundation 3C R2 Full-Window Shadow Review'


def test_the_only_trigger_is_manual_dispatch(workflow):
    # PyYAML resolves a bare `on:` key to True.
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}


@pytest.mark.parametrize('forbidden', ['schedule', 'push', 'pull_request',
                                       'workflow_call', 'repository_dispatch'])
def test_no_automatic_trigger_exists(workflow, forbidden):
    triggers = workflow.get('on', workflow.get(True))
    assert forbidden not in triggers


def test_there_are_no_editable_inputs(workflow):
    """Nothing to type from a phone means nothing to get wrong."""
    triggers = workflow.get('on', workflow.get(True))
    assert not (triggers.get('workflow_dispatch') or {})


# ═══════════════ 2. Read-only permissions ═══════════════════════════════════


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


@pytest.mark.parametrize('scope', [
    'actions', 'pull-requests', 'issues', 'deployments', 'packages',
    'id-token', 'checks', 'statuses',
])
def test_no_additional_permission_is_requested(workflow, scope):
    assert scope not in workflow['permissions']


def test_no_write_permission_appears_anywhere(workflow_text):
    block = workflow_text.split('permissions:')[1].split('jobs:')[0]
    assert 'write' not in block


# ═══════════════ 3. The command is pinned ═══════════════════════════════════


@pytest.fixture(scope='module')
def ingestion_command(run_commands):
    matches = [
        line for line in run_commands if 'game_driven_ingestion.py' in line
    ]
    assert len(matches) == 1, 'exactly one ingestion invocation'
    return matches[0]


def test_the_command_runs_shadow_mode(ingestion_command):
    assert '--mode shadow' in ingestion_command


def test_the_command_pins_the_reference_date(ingestion_command):
    assert '--reference-date 2026-07-29' in ingestion_command


@pytest.mark.parametrize('forbidden', [
    '--game-pk', '--only-game-pk', '--max-games', '--include-backfill',
    '--expected-plan-fingerprint', '--mode write', '--mode authoritative',
])
def test_the_command_carries_no_scope_or_write_option(
    ingestion_command, forbidden,
):
    assert forbidden not in ingestion_command


def test_the_command_evaluates_the_normal_governed_window(ingestion_command):
    """R2 is the whole window, so nothing may bound or widen the plan."""
    tokens = [token for token in ingestion_command.split() if token.startswith('--')]
    assert tokens == ['--mode', '--reference-date', '--output']


# ═══════════════ 4. The automated lane stays off ════════════════════════════


def test_the_automated_lane_is_explicitly_off(job):
    assert job['env']['GAME_DRIVEN_INGESTION_MODE'] == 'off'
    assert job['env']['AUTO_SYNC'] == 'false'
    assert job['env']['APP_ENV'] == 'production'


# ═══════════════ 5. Established secret names ════════════════════════════════


def test_the_workflow_uses_the_established_production_secrets(job):
    env = job['env']
    assert env['DATABASE_URL'] == '${{ secrets.DATABASE_URL }}'
    assert env['SECRET_KEY'] == '${{ secrets.SECRET_KEY }}'
    assert env['ADMIN_API_TOKEN'] == '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'


def test_the_workflow_fails_when_a_secret_is_absent(run_commands):
    guard = [line for line in run_commands if 'Missing required production' in line]
    assert guard


def test_no_secret_value_is_echoed(run_commands):
    for line in run_commands:
        if line.startswith('echo') and '$' in line:
            assert 'DATABASE_URL' not in line
            assert 'SECRET_KEY' not in line
            assert 'ADMIN_API_TOKEN' not in line


# ═══════════════ 6. No deployment, publication, or normal sync ══════════════


@pytest.mark.parametrize('forbidden', [
    'render', 'vercel', 'deploy', 'run_daily_sync', 'run_postgame_refresh',
    'refresh_slate_schedule', 'publish', 'authoritative', 'snapshot',
    'cache_warm', 'warm_cache', 'share_artifact',
])
def test_no_deployment_or_publication_command_is_executed(run_commands, forbidden):
    for line in run_commands:
        assert forbidden not in line.lower(), line


def test_the_workflow_calls_only_the_two_approved_scripts(run_commands):
    scripts = {
        part for line in run_commands for part in line.split()
        if part.endswith('.py')
    }
    assert scripts == {
        'backend/scripts/game_driven_ingestion.py',
        'backend/scripts/validate_r2_shadow_report.py',
    }


# ═══════════════ 7-9. Bounds, ordering, artifacts ═══════════════════════════


def test_the_job_is_bounded_and_serialized(workflow, job):
    assert isinstance(job['timeout-minutes'], int)
    assert 0 < job['timeout-minutes'] <= 30
    assert workflow['concurrency']['group'] == 'foundation-3c-r2-full-window-shadow'
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_the_concurrency_group_is_distinct_from_r1(workflow):
    assert workflow['concurrency']['group'] != 'foundation-3c-r1-shadow-validation'


def test_validation_runs_always_and_after_the_shadow_step(job):
    steps = job['steps']
    shadow = next(i for i, s in enumerate(steps) if s.get('id') == 'shadow')
    validate = next(i for i, s in enumerate(steps) if s.get('id') == 'validate')
    assert shadow < validate
    assert steps[validate]['if'] == '${{ always() }}'


def test_the_credential_scan_runs_before_the_upload(job):
    steps = job['steps']
    scan = next(
        i for i, s in enumerate(steps)
        if 'credential-shaped' in (s.get('name') or '')
    )
    upload = next(
        i for i, s in enumerate(steps)
        if str(s.get('uses') or '').startswith('actions/upload-artifact')
    )
    assert scan < upload
    assert steps[scan]['if'] == '${{ always() }}'


def test_the_final_gate_runs_after_the_upload(job):
    steps = job['steps']
    upload = next(
        i for i, s in enumerate(steps)
        if str(s.get('uses') or '').startswith('actions/upload-artifact')
    )
    gate = len(steps) - 1
    assert upload < gate
    assert steps[gate]['if'] == '${{ always() }}'
    assert 'R3/R4 remain blocked until review' in steps[gate]['run']


def test_artifacts_upload_even_when_the_run_fails(job):
    upload = next(
        step for step in job['steps']
        if str(step.get('uses') or '').startswith('actions/upload-artifact')
    )
    assert upload['if'] == '${{ always() }}'
    assert upload['with']['name'] == 'foundation-3c-r2-full-window-shadow-review'
    assert upload['with']['retention-days'] == 14
    assert upload['with']['if-no-files-found'] == 'warn'


@pytest.mark.parametrize('artifact', [
    'r2-full-window-shadow.json',
    'r2-validation-summary.json',
    'r2-validation-summary.md',
    'r2-update-review.json',
    'r2-update-review.md',
])
def test_every_required_artifact_is_produced(job, artifact):
    assert any(artifact in str(value) for value in job['env'].values())


def test_a_failed_validation_cannot_produce_a_successful_job(run_commands):
    gate = [line for line in run_commands if 'VALIDATION_EXIT' in line]
    assert any('exit 1' in line for line in run_commands)
    assert gate


@pytest.mark.parametrize('pattern', [
    'postgresql://', 'postgres://', 'password', 'Authorization',
    'X-Admin-Token', 'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
    'BASEBALLOS_ADMIN_API_TOKEN', 'token', 'api', 'secret',
])
def test_the_credential_scan_covers_the_required_patterns(workflow_text, pattern):
    scan = workflow_text.split('credential-shaped content')[1]
    assert pattern in scan


def test_every_shell_block_is_valid_bash(job):
    for step in job['steps']:
        script = step.get('run')
        if not script:
            continue
        result = subprocess.run(
            ['bash', '-n'], input=script, text=True, capture_output=True,
        )
        assert result.returncode == 0, step.get('name')


# ═══════════════ The inline credential scanner ══════════════════════════════


def _scanner_source(workflow_text):
    body = workflow_text.split("<<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    return textwrap.dedent(body)


def _run_scanner(workflow_text, directory, monkeypatch):
    monkeypatch.chdir(directory)
    try:
        exec(compile(_scanner_source(workflow_text), 'scan', 'exec'), {})
    except SystemExit as exit_signal:
        return int(exit_signal.code or 0)
    return 0


def test_the_scanner_passes_a_clean_artifact_set(
    workflow_text, tmp_path, monkeypatch,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'r2-validation-summary.json').write_text(json.dumps({
        'result': 'review_required',
        'rows_updated': 3,
        'changed_fields_counts': {'earned_runs': 3},
        'write_approved': False,
        'database_writes': 'none',
    }))
    assert _run_scanner(workflow_text, tmp_path, monkeypatch) == 0
    assert (artifacts / 'r2-validation-summary.json').exists()


@pytest.mark.parametrize('poison', [
    'postgresql://user:pw@host/db',
    'password=hunter2',
    'X-Admin-Token: abc',
    'api_key=abc123',
])
def test_the_scanner_deletes_and_fails_on_credential_content(
    workflow_text, tmp_path, monkeypatch, poison,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    unsafe = artifacts / 'r2-update-review.json'
    unsafe.write_text(poison)
    assert _run_scanner(workflow_text, tmp_path, monkeypatch) == 1
    assert not unsafe.exists()


# ═══════════════ Report builders ════════════════════════════════════════════


def _identity(action='unchanged', *, changed=(), suppressed=(), digest=''):
    changed = sorted(changed)
    return {
        'pitcher_identity_action': action,
        'pitcher_identity_status': 'resolved',
        'pitcher_identity_changed_fields': changed,
        'pitcher_identity_applied_fields': changed,
        'pitcher_identity_suppressed_fields': sorted(suppressed),
        'pitcher_identity_governed_and_safe': True,
        'pitcher_identity_blocked_reason': None,
        'pitcher_identity_mutation_digest': digest,
        'pitcher_identity_requires_creation': action == (
            pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY
        ),
        'pitcher_identity_current_authority_mutation_refused': bool(suppressed),
    }


def _row(game_pk, pitcher, *, changed=(), companions=(), ignored=(),
         identity=None):
    changed = sorted(changed)
    companions = sorted(companions)
    identity = identity if identity is not None else _identity()
    if not changed:
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
            'derived_companion_differences_ignored': sorted(ignored),
            'appearance_team_reason': None,
            **identity,
        }
    categories = sorted({
        reconciliation.field_category(field) for field in changed
    })
    if any(
        reconciliation.field_category(field) in (
            reconciliation.CATEGORY_STATISTICAL_CORRECTION,
            reconciliation.CATEGORY_ROLE_SIGNAL,
            reconciliation.CATEGORY_GAME_METADATA,
        )
        for field in changed
    ):
        categories.append(reconciliation.CATEGORY_PROVENANCE_ONLY)
    return {
        'game_pk': game_pk,
        'pitcher_mlb_id': pitcher,
        'action': 'update',
        'changed_fields': changed,
        'changed_field_count': len(changed),
        'mutation_categories': sorted(set(categories)),
        'is_statistical_correction': any(
            reconciliation.field_category(field)
            == reconciliation.CATEGORY_STATISTICAL_CORRECTION
            for field in changed
        ),
        'affects_published_evidence': True,
        'is_provenance_only': False,
        'governed_and_safe': True,
        'blocked_reason': None,
        'mutation_digest': f'digest{game_pk}{pitcher}',
        'semantic_changed_fields': changed,
        'applied_changed_fields': sorted(set(changed) | set(companions)),
        'derived_companion_fields': companions,
        'derived_companion_differences_ignored': sorted(ignored),
        'appearance_team_reason': None,
        **identity,
    }


def _game(game_pk, rows, *, represented_date='2026-07-28'):
    actions = {'insert': 0, 'update': 0, 'unchanged': 0, 'blocked': 0}
    changed_counts = {}
    category_counts = {}
    ignored = outs = applied = statistical = authority = provenance = 0
    identity_actions = {}
    identity_changed = {}
    suppressed_counts = {}
    identity_mutations = identity_unchanged = suppressed_rows = 0
    identity_pitchers = set()
    for row in rows:
        action = row['pitcher_identity_action']
        identity_actions[action] = identity_actions.get(action, 0) + 1
        for field in row['pitcher_identity_changed_fields']:
            identity_changed[field] = identity_changed.get(field, 0) + 1
        for field in row['pitcher_identity_suppressed_fields']:
            suppressed_counts[field] = suppressed_counts.get(field, 0) + 1
        if row['pitcher_identity_suppressed_fields']:
            suppressed_rows += 1
        if action in pitcher_identity.MUTATING_ACTIONS:
            identity_mutations += 1
            identity_pitchers.add(row['pitcher_mlb_id'])
        else:
            identity_unchanged += 1
        actions[row['action']] += 1
        for field in row['changed_fields']:
            changed_counts[field] = changed_counts.get(field, 0) + 1
        for category in row['mutation_categories']:
            category_counts[category] = category_counts.get(category, 0) + 1
        if row['derived_companion_differences_ignored']:
            ignored += 1
        if any(
            field in reconciliation.SEMANTIC_AUTHORITY_BY_COMPANION.values()
            for field in row['semantic_changed_fields']
        ):
            outs += 1
        if row['derived_companion_fields']:
            applied += 1
        if row['is_statistical_correction']:
            statistical += 1
        if row['appearance_team_reason']:
            authority += 1
        if row['is_provenance_only']:
            provenance += 1
    return {
        'game_pk': game_pk,
        'represented_date': represented_date,
        'candidate_reason': 'newly_final',
        'criticality': 'publication_critical',
        'attempt_number': 1,
        'status': 'projected',
        'source_revision': f'rev{game_pk}',
        'appearances_extracted': len(rows),
        'relief_appearances': max(len(rows) - 1, 0),
        'inserted': actions['insert'],
        'updated': actions['update'],
        'unchanged': actions['unchanged'],
        'blocked': actions['blocked'],
        'changed_fields_counts': dict(sorted(changed_counts.items())),
        'mutation_category_counts': dict(sorted(category_counts.items())),
        'statistical_corrections': statistical,
        'authority_reconciliations': authority,
        'provenance_only_updates': provenance,
        'canonical_outs_corrections': outs,
        'derived_companion_fields_applied': applied,
        'derived_companion_differences_ignored': ignored,
        'pitcher_identity_rows_examined': len(rows),
        'pitcher_identity_mutations': identity_mutations,
        'pitcher_identity_unchanged': identity_unchanged,
        'pitcher_identity_creations': identity_mutations,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_action_counts': dict(sorted(identity_actions.items())),
        'pitcher_identity_changed_fields_counts': dict(
            sorted(identity_changed.items())
        ),
        'suppressed_current_state_field_counts': dict(
            sorted(suppressed_counts.items())
        ),
        'pitcher_identity_unique_pitchers_affected': len(identity_pitchers),
        'historical_current_state_changes_suppressed': suppressed_rows,
        'appearance_team_mutations': authority,
        'complete_mutation_count': (
            actions['insert'] + actions['update'] + actions['blocked']
            + identity_mutations
        ),
        'reconciliation_plan_fingerprint': f'fp{game_pk}',
        'rows': rows,
        'elapsed_seconds': 0.4,
        'error_class': None,
    }


def _report(games, *, discovered=None):
    totals = {'insert': 0, 'update': 0, 'unchanged': 0, 'blocked': 0}
    changed_counts = {}
    category_counts = {}
    rows_expected = ignored = outs = applied = statistical = authority = 0
    provenance = 0
    identity_actions = {}
    identity_changed = {}
    suppressed_counts = {}
    identity_rows = identity_mutations = identity_unchanged = 0
    suppressed_rows = complete_mutations = 0
    identity_pitchers = set()
    for game in games:
        identity_rows += game['pitcher_identity_rows_examined']
        identity_mutations += game['pitcher_identity_mutations']
        identity_unchanged += game['pitcher_identity_unchanged']
        suppressed_rows += game['historical_current_state_changes_suppressed']
        complete_mutations += game['complete_mutation_count']
        for row in game['rows']:
            if row['pitcher_identity_action'] in pitcher_identity.MUTATING_ACTIONS:
                identity_pitchers.add(row['pitcher_mlb_id'])
        for key, source in (
            (identity_actions, 'pitcher_identity_action_counts'),
            (identity_changed, 'pitcher_identity_changed_fields_counts'),
            (suppressed_counts, 'suppressed_current_state_field_counts'),
        ):
            for name, count in game[source].items():
                key[name] = key.get(name, 0) + count
        totals['insert'] += game['inserted']
        totals['update'] += game['updated']
        totals['unchanged'] += game['unchanged']
        totals['blocked'] += game['blocked']
        rows_expected += game['appearances_extracted']
        ignored += game['derived_companion_differences_ignored']
        outs += game['canonical_outs_corrections']
        applied += game['derived_companion_fields_applied']
        statistical += game['statistical_corrections']
        authority += game['authority_reconciliations']
        provenance += game['provenance_only_updates']
        for field, count in game['changed_fields_counts'].items():
            changed_counts[field] = changed_counts.get(field, 0) + count
        for category, count in game['mutation_category_counts'].items():
            category_counts[category] = category_counts.get(category, 0) + count

    planned = len(games)
    game_pks = sorted(game['game_pk'] for game in games)
    return {
        'status': 'complete',
        'mode': 'shadow',
        'reference_date': '2026-07-29',
        'execution_scope_mode': 'window',
        'requested_game_pks': [],
        'requested_game_count': 0,
        'duplicate_requested_count': 0,
        'planned_game_pks': game_pks,
        'planned_game_count': planned,
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'execution_scope_exact_match': True,
        'games_discovered': discovered if discovered is not None else planned,
        'games_planned': planned,
        'games_attempted': planned,
        'games_fetched': planned,
        'games_completed': planned,
        'games_failed': 0,
        'games_remaining': 0,
        'critical_games_unresolved': 0,
        'best_effort_games_deferred': 0,
        'schedule_authority_missing': 0,
        'finality_conflicts': 0,
        'budget_stop_triggered': False,
        'budget_stop': None,
        'failure_classes': {},
        'rows_expected': rows_expected,
        'rows_inserted': totals['insert'],
        'rows_updated': totals['update'],
        'rows_unchanged': totals['unchanged'],
        'rows_blocked': totals['blocked'],
        'changed_fields_counts': dict(sorted(changed_counts.items())),
        'mutation_category_counts': dict(sorted(category_counts.items())),
        'statistical_corrections': statistical,
        'authority_reconciliations': authority,
        'provenance_only_updates': provenance,
        'canonical_outs_corrections': outs,
        'derived_companion_fields_applied': applied,
        'derived_companion_differences_ignored': ignored,
        'decimal_only_updates_suppressed': ignored,
        'pitcher_identity_rows_examined': identity_rows,
        'pitcher_identity_mutations': identity_mutations,
        'pitcher_identity_unchanged': identity_unchanged,
        'pitcher_identity_creations': identity_mutations,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_action_counts': dict(sorted(identity_actions.items())),
        'pitcher_identity_changed_fields_counts': dict(
            sorted(identity_changed.items())
        ),
        'suppressed_current_state_field_counts': dict(
            sorted(suppressed_counts.items())
        ),
        'pitcher_identity_unique_pitchers_affected': len(identity_pitchers),
        'historical_current_state_changes_suppressed': suppressed_rows,
        'appearance_team_mutations': authority,
        'complete_mutation_count': complete_mutations,
        'innings_semantics_version': '2',
        'reconciliation_plan_version': reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'identity_plan_version': pitcher_identity.IDENTITY_PLAN_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'reconciliation_plan_fingerprint': 'run-fingerprint',
        'complete_reconciliation_fingerprint': 'run-fingerprint',
        'games': games,
        'publication_completeness': {
            'represented_date': '2026-07-29',
            'window_start': '2026-07-22',
            'horizon_days': 7,
            'expected_final_games': planned,
            'completed_final_games': 0,
            'unresolved_final_games': planned,
            'correction_pending_games': 0,
            'terminal_failure_games': 0,
            'corrected_games_reconciled': 0,
            'critical_appearance_rows_expected': 0,
            'critical_appearance_rows_reconciled': 0,
            'finality_conflicts': 0,
            'schedule_authority_missing': 0,
            'best_effort_games_planned': 0,
            'publication_complete': False,
            'decision_reasons': ['unresolved_final_games'],
        },
    }


def clean_report():
    """Every row already reconciled, with real decimal drift safely ignored."""
    return _report([
        _game(900001, [
            _row(900001, 111),
            _row(900001, 112, ignored=['innings_pitched']),
            _row(900001, 113),
        ]),
        _game(900002, [
            _row(900002, 221, ignored=['innings_pitched']),
            _row(900002, 222),
        ]),
        _game(900003, [
            _row(900003, 331),
            _row(900003, 332),
        ]),
    ])


def _resync(report):
    """Rebuild every aggregate from the rows after a test mutates them."""
    return _report(
        [_game(game['game_pk'], game['rows']) for game in report['games']]
    )


def _failure(report):
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    return caught.value


# ═══════════════ 1-6. Passing and reviewable shapes ═════════════════════════


def test_a_clean_report_passes():
    result = validator.validate(clean_report())
    assert result['summary']['result'] == validator.RESULT_PASS
    assert result['summary']['rows_updated'] == 0
    assert result['summary']['derived_companion_differences_ignored'] == 2
    assert result['manifest']['updates'] == []


def test_earned_runs_updates_are_review_required():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['earned_runs'])
    report = _resync(report)
    result = validator.validate(report)
    assert result['summary']['result'] == validator.RESULT_REVIEW_REQUIRED
    assert result['summary']['rows_updated'] == 1
    assert result['manifest']['updated_row_count'] == 1
    assert result['manifest']['updates'][0]['semantic_changed_fields'] == [
        'earned_runs'
    ]


def test_hits_allowed_updates_are_review_required():
    report = clean_report()
    report['games'][1]['rows'][1] = _row(900002, 222, changed=['hits_allowed'])
    report = _resync(report)
    result = validator.validate(report)
    assert result['summary']['result'] == validator.RESULT_REVIEW_REQUIRED
    assert result['summary']['changed_fields_counts'] == {'hits_allowed': 1}


def test_multiple_legitimate_fields_are_one_update_row():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['earned_runs', 'hits_allowed', 'runs_allowed'],
    )
    report = _resync(report)
    result = validator.validate(report)
    assert result['summary']['rows_updated'] == 1
    assert result['manifest']['updated_row_count'] == 1
    assert result['summary']['changed_fields_counts'] == {
        'earned_runs': 1, 'hits_allowed': 1, 'runs_allowed': 1,
    }


def test_overlapping_changed_fields_never_inflate_the_row_count():
    """Field totals are not row totals — three fields on two rows is two rows."""
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['earned_runs', 'hits_allowed'],
    )
    report['games'][0]['rows'][2] = _row(
        900001, 113, changed=['earned_runs', 'runs_allowed'],
    )
    report = _resync(report)
    result = validator.validate(report)
    assert result['summary']['changed_fields_counts'] == {
        'earned_runs': 2, 'hits_allowed': 1, 'runs_allowed': 1,
    }
    assert result['summary']['rows_updated'] == 2
    assert result['manifest']['updated_row_count'] == 2
    assert result['manifest']['updated_game_count'] == 1


def test_ignored_decimal_differences_leave_rows_unchanged():
    result = validator.validate(clean_report())
    summary = result['summary']
    assert summary['rows_unchanged'] == 7
    assert summary['derived_companion_differences_ignored'] == 2
    assert summary['decimal_only_updates_suppressed'] == 2
    assert summary['canonical_outs_corrections'] == 0


# ═══════════════ 7-10. Canonical innings semantics ══════════════════════════


def test_innings_pitched_as_a_semantic_change_fails():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['innings_pitched'])
    report = _resync(report)
    failure = _failure(report)
    assert 'innings_pitched' in failure.invariant


def test_innings_pitched_as_a_derived_companion_is_accepted():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['innings_pitched_outs', 'earned_runs'],
        companions=['innings_pitched'],
    )
    report = _resync(report)
    result = validator.validate(report)
    assert result['summary']['result'] == validator.RESULT_REVIEW_REQUIRED
    assert result['summary']['canonical_outs_corrections'] == 1
    assert result['summary']['derived_companion_fields_applied'] == 1
    entry = result['manifest']['updates'][0]
    assert entry['derived_companion_fields'] == ['innings_pitched']
    assert 'innings_pitched' not in entry['semantic_changed_fields']


def test_a_companion_applied_without_its_authority_fails():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['earned_runs'], companions=['innings_pitched'],
    )
    report = _resync(report)
    failure = _failure(report)
    assert 'requires_innings_pitched_outs' in failure.invariant


def test_a_canonical_outs_correction_is_highlighted_as_material():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['innings_pitched_outs'],
        companions=['innings_pitched'],
    )
    report = _resync(report)
    result = validator.validate(report)
    assert result['summary']['result'] == validator.RESULT_REVIEW_REQUIRED
    assert result['summary']['canonical_outs_corrections'] == 1
    # The decimal is applied WITH the outs change, never as its own correction.
    assert result['summary']['changed_fields_counts'] == {'innings_pitched_outs': 1}
    assert result['manifest']['updated_row_count'] == 1


def test_a_decimal_only_difference_that_became_an_update_fails():
    """The exact pre-PR-571 regression: drift promoted to a correction."""
    report = clean_report()
    row = _row(900001, 111)
    row.update({
        'action': 'update',
        'changed_fields': ['innings_pitched'],
        'semantic_changed_fields': ['innings_pitched'],
        'applied_changed_fields': ['innings_pitched'],
        'changed_field_count': 1,
        'mutation_categories': ['official_statistical_correction'],
        'affects_published_evidence': True,
        'is_statistical_correction': True,
        'mutation_digest': 'd',
    })
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    failure = _failure(report)
    assert 'innings_pitched' in failure.invariant


def test_an_update_with_no_semantic_change_fails():
    report = clean_report()
    row = _row(900001, 111)
    row.update({'action': 'update', 'mutation_digest': 'd'})
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    failure = _failure(report)
    assert 'update_has_a_semantic_change' in failure.invariant


def test_an_ignored_difference_that_is_also_applied_fails():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['innings_pitched_outs'],
        companions=['innings_pitched'], ignored=['innings_pitched'],
    )
    report = _resync(report)
    failure = _failure(report)
    assert 'ignored_and_applied_are_disjoint' in failure.invariant


# ═══════════════ 11-19. Foundational failures ═══════════════════════════════


def test_a_projected_insert_fails():
    report = clean_report()
    row = _row(900001, 111)
    row['action'] = 'insert'
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    report['rows_inserted'] = 1
    report['rows_unchanged'] = 6
    failure = _failure(report)
    assert failure.invariant == 'rows_inserted'


def test_a_blocked_row_fails():
    report = clean_report()
    row = _row(900001, 111)
    row.update({
        'action': 'blocked',
        'governed_and_safe': False,
        'blocked_reason': 'partial_source_line',
        'mutation_categories': ['unsafe_or_blocked_mutation'],
    })
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    report['rows_blocked'] = 1
    report['rows_unchanged'] = 6
    failure = _failure(report)
    assert failure.invariant == 'rows_blocked'


def test_an_unsafe_update_row_fails():
    report = clean_report()
    row = _row(900001, 111, changed=['earned_runs'])
    row['governed_and_safe'] = False
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    failure = _failure(report)
    assert 'governed_and_safe' in failure.invariant


def test_a_row_carrying_a_blocked_reason_fails():
    report = clean_report()
    row = _row(900001, 111, changed=['earned_runs'])
    row['blocked_reason'] = 'partial_source_line'
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    failure = _failure(report)
    assert 'blocked_reason' in failure.invariant


def test_an_unknown_changed_field_fails():
    report = clean_report()
    row = _row(900001, 111, changed=['earned_runs'])
    row['changed_fields'] = ['earned_runs', 'mystery_column']
    row['semantic_changed_fields'] = ['earned_runs', 'mystery_column']
    row['applied_changed_fields'] = ['earned_runs', 'mystery_column']
    row['changed_field_count'] = 2
    report['games'][0]['rows'][0] = row
    report = _resync(report)
    failure = _failure(report)
    assert 'mystery_column_is_governed' in failure.invariant


def test_an_unresolved_pitcher_identity_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['pitcher_mlb_id'] = None
    report = _resync(report)
    failure = _failure(report)
    assert 'pitcher_mlb_id_present' in failure.invariant


def test_a_game_failure_fails():
    report = clean_report()
    report['games_failed'] = 1
    failure = _failure(report)
    assert failure.invariant == 'games_failed'


def test_a_game_error_class_fails():
    report = clean_report()
    report['games'][0]['error_class'] = 'game_fetch_failed'
    failure = _failure(report)
    assert 'error_class' in failure.invariant


def test_a_budget_stop_fails():
    report = clean_report()
    report['budget_stop_triggered'] = True
    failure = _failure(report)
    assert failure.invariant == 'budget_stop_triggered'


def test_a_budget_stop_payload_fails():
    report = clean_report()
    report['budget_stop'] = {'games_remaining': 4}
    failure = _failure(report)
    assert failure.invariant == 'budget_stop_is_null'


def test_a_finality_conflict_fails():
    report = clean_report()
    report['finality_conflicts'] = 2
    failure = _failure(report)
    assert failure.invariant == 'finality_conflicts'


def test_missing_schedule_authority_fails():
    report = clean_report()
    report['schedule_authority_missing'] = 1
    failure = _failure(report)
    assert failure.invariant == 'schedule_authority_missing'


def test_a_recorded_failure_class_fails():
    report = clean_report()
    report['failure_classes'] = {'game_fetch_failed': 1}
    failure = _failure(report)
    assert failure.invariant == 'failure_classes_is_empty'


# ═══════════════ 20-22. Accounting cannot be faked by aggregates ════════════


def test_a_bad_row_fails_even_when_every_aggregate_agrees():
    """Totals reconcile perfectly; one row is still an illegal mutation."""
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['innings_pitched'])
    report = _resync(report)
    # Prove the aggregates really are self-consistent before asserting.
    assert report['rows_updated'] == 1
    assert report['changed_fields_counts'] == {'innings_pitched': 1}
    failure = _failure(report)
    assert 'innings_pitched' in failure.invariant


def test_per_game_totals_that_disagree_with_the_row_list_fail():
    report = clean_report()
    report['games'][0]['updated'] = 1
    report['games'][0]['unchanged'] = 2
    failure = _failure(report)
    assert 'updated_matches_rows' in failure.invariant


def test_a_game_row_count_that_disagrees_with_appearances_fails():
    report = clean_report()
    report['games'][0]['appearances_extracted'] = 4
    failure = _failure(report)
    assert 'row_count_matches_appearances' in failure.invariant


def test_top_level_totals_that_disagree_with_the_games_fail():
    report = clean_report()
    report['rows_unchanged'] = 6
    report['rows_expected'] = 6
    failure = _failure(report)
    assert 'matches_per_row_total' in failure.invariant


def test_row_actions_that_do_not_sum_to_rows_expected_fail():
    report = clean_report()
    report['rows_expected'] = 9
    failure = _failure(report)
    assert failure.invariant == 'rows_expected_equals_row_actions'


def test_changed_field_counts_that_disagree_with_the_rows_fail():
    report = clean_report()
    report['changed_fields_counts'] = {'earned_runs': 3}
    failure = _failure(report)
    assert failure.invariant == 'changed_fields_counts_match_rows'


def test_a_counter_that_disagrees_with_the_rows_fails():
    report = clean_report()
    report['derived_companion_differences_ignored'] = 5
    report['decimal_only_updates_suppressed'] = 5
    failure = _failure(report)
    assert 'derived_companion_differences_ignored_matches_rows' in failure.invariant


def test_suppressed_and_ignored_counters_must_agree():
    report = clean_report()
    report['decimal_only_updates_suppressed'] = 1
    failure = _failure(report)
    assert failure.invariant == 'decimal_only_updates_suppressed_equals_ignored'


def test_a_duplicate_row_fails():
    report = clean_report()
    report['games'][0]['rows'][1] = _row(900001, 111)
    report = _resync(report)
    failure = _failure(report)
    assert 'row_appears_once' in failure.invariant


# ═══════════════ Scope ══════════════════════════════════════════════════════


def test_an_exclusive_scope_fails():
    report = clean_report()
    report['execution_scope_mode'] = 'exclusive'
    failure = _failure(report)
    assert failure.invariant == 'execution_scope_mode'


def test_a_requested_game_subset_fails():
    report = clean_report()
    report['requested_game_pks'] = [900001]
    report['requested_game_count'] = 1
    failure = _failure(report)
    assert failure.invariant == 'requested_game_pks_is_empty'


def test_a_bounded_subset_of_the_plan_fails():
    """--max-games would truncate the executed items below the planned set."""
    report = clean_report()
    report['planned_game_count'] = 5
    failure = _failure(report)
    assert failure.invariant == 'planned_game_count_equals_games_planned'


def test_games_discovered_below_games_planned_fails():
    report = clean_report()
    report['games_discovered'] = 1
    failure = _failure(report)
    assert failure.invariant == 'games_discovered_at_least_games_planned'


def test_an_unattempted_game_fails():
    report = clean_report()
    report['games_attempted'] = 2
    failure = _failure(report)
    assert failure.invariant == 'games_attempted_equals_games_planned'


def test_remaining_games_fail():
    report = clean_report()
    report['games_remaining'] = 3
    failure = _failure(report)
    assert failure.invariant == 'games_remaining'


@pytest.mark.parametrize('field,value', [
    ('status', 'incomplete'),
    ('mode', 'write'),
    ('reference_date', '2026-07-30'),
    ('innings_semantics_version', '1'),
    ('reconciliation_plan_version', '1'),
    ('parity_contract_version', '1'),
])
def test_execution_identity_is_pinned(field, value):
    report = clean_report()
    report[field] = value
    failure = _failure(report)
    assert failure.invariant == field


def test_the_expected_versions_come_from_the_merged_planner():
    assert validator.EXPECTED_INNINGS_SEMANTICS_VERSION == (
        reconciliation.INNINGS_SEMANTICS_VERSION
    )
    assert validator.EXPECTED_RECONCILIATION_PLAN_VERSION == (
        reconciliation.RECONCILIATION_PLAN_VERSION
    )
    assert validator.EXPECTED_PARITY_CONTRACT_VERSION == (
        reconciliation.PARITY_CONTRACT_VERSION
    )


def test_innings_pitched_is_prohibited_even_though_it_is_canonical():
    """The registry accepts it; R2 refuses it by name anyway."""
    assert reconciliation.field_category('innings_pitched') != (
        reconciliation.CATEGORY_BLOCKED
    )
    assert 'innings_pitched' in validator.PROHIBITED_SEMANTIC_FIELDS


# ═══════════════ 23. Publication completeness ═══════════════════════════════


def test_incomplete_publication_is_accepted_when_internally_consistent():
    report = clean_report()
    assert report['publication_completeness']['publication_complete'] is False
    result = validator.validate(report)
    assert result['summary']['result'] == validator.RESULT_PASS
    assert result['summary']['publication_completeness'][
        'publication_complete'
    ] is False


def test_a_terminal_failure_game_fails():
    report = clean_report()
    report['publication_completeness']['terminal_failure_games'] = 1
    failure = _failure(report)
    assert failure.invariant == 'completeness_terminal_failure_games'


def test_completeness_accounting_that_exceeds_expected_fails():
    report = clean_report()
    report['publication_completeness']['completed_final_games'] = 3
    failure = _failure(report)
    assert 'completed_plus_unresolved_within_expected' in failure.invariant


def test_completeness_reconciled_rows_above_expected_fail():
    report = clean_report()
    report['publication_completeness']['critical_appearance_rows_reconciled'] = 5
    failure = _failure(report)
    assert 'reconciled_rows_within_expected' in failure.invariant


def test_a_missing_completeness_object_fails():
    report = clean_report()
    report['publication_completeness'] = None
    failure = _failure(report)
    assert failure.invariant == 'publication_completeness_is_an_object'


def test_completeness_without_a_decision_reason_fails():
    report = clean_report()
    report['publication_completeness']['decision_reasons'] = []
    failure = _failure(report)
    assert failure.invariant == 'completeness_states_a_decision_reason'


# ═══════════════ 24-26. Manifest shape ══════════════════════════════════════


def test_an_empty_manifest_is_produced_when_nothing_changes():
    result = validator.validate(clean_report())
    manifest = result['manifest']
    assert manifest['updates'] == []
    assert manifest['updated_row_count'] == 0
    assert manifest['updated_game_count'] == 0
    assert manifest['write_approved'] is False


def test_manifest_ordering_is_deterministic():
    report = clean_report()
    report['games'] = list(reversed(report['games']))
    report['games'][0]['rows'][1] = _row(900003, 332, changed=['earned_runs'])
    report['games'][1]['rows'][0] = _row(900002, 221, changed=['earned_runs'])
    report['games'][2]['rows'][2] = _row(900001, 113, changed=['earned_runs'])
    report['games'][2]['rows'][0] = _row(900001, 111, changed=['hits_allowed'])
    report = _resync(report)
    manifest = validator.validate(report)['manifest']
    keys = [
        (entry['game_pk'], entry['pitcher_mlb_id'])
        for entry in manifest['updates']
    ]
    assert keys == sorted(keys)
    assert keys == [(900001, 111), (900001, 113), (900002, 221), (900003, 332)]


def test_manifest_changed_fields_are_ordered_deterministically():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['walks', 'earned_runs', 'strikeouts'],
    )
    report = _resync(report)
    manifest = validator.validate(report)['manifest']
    entry = manifest['updates'][0]
    assert entry['semantic_changed_fields'] == [
        'earned_runs', 'strikeouts', 'walks',
    ]


def test_the_manifest_carries_only_safe_fields():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['earned_runs'])
    report = _resync(report)
    manifest = validator.validate(report)['manifest']
    assert set(manifest['updates'][0]) == {
        'mutation_target', 'suppressed_current_state_fields',
        'game_pk', 'represented_date', 'pitcher_mlb_id', 'action',
        'semantic_changed_fields', 'applied_changed_fields',
        'derived_companion_fields', 'derived_companion_differences_ignored',
        'mutation_categories', 'changed_field_count',
        'affects_published_evidence', 'governed_and_safe', 'blocked_reason',
        'is_statistical_correction', 'is_provenance_only',
        'appearance_team_reason', 'source_revision', 'mutation_digest',
    }


def test_the_manifest_reports_aggregates_without_summing_categories_as_rows():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, changed=['earned_runs', 'hits_allowed'],
    )
    report = _resync(report)
    manifest = validator.validate(report)['manifest']
    # Two changed fields and two categories on ONE row.
    assert manifest['updated_row_count'] == 1
    assert sum(manifest['mutation_category_counts'].values()) > 1


# ═══════════════ 27-30. CLI behaviour ═══════════════════════════════════════


def _run_main(tmp_path, report):
    if report is not None:
        (tmp_path / 'report.json').write_text(json.dumps(report))
    return validator.main([
        '--report', str(tmp_path / 'report.json'),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--manifest-json', str(tmp_path / 'manifest.json'),
        '--manifest-markdown', str(tmp_path / 'manifest.md'),
        '--repository-sha', 'abc123',
        '--run-id', '42',
    ])


def test_a_clean_run_exits_zero_and_writes_every_artifact(tmp_path):
    assert _run_main(tmp_path, clean_report()) == 0
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'pass'
    assert summary['repository_sha'] == 'abc123'
    assert summary['workflow_run_id'] == '42'
    assert 'FOUNDATION 3C R2 — PASS' in (tmp_path / 'summary.md').read_text()
    assert json.loads((tmp_path / 'manifest.json').read_text())['updates'] == []
    assert (tmp_path / 'manifest.md').exists()


def test_a_review_required_run_exits_zero_but_approves_nothing(tmp_path):
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['earned_runs'])
    report = _resync(report)
    assert _run_main(tmp_path, report) == 0
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'review_required'
    assert summary['write_approved'] is False
    assert summary['database_writes'] == 'none'
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'REVIEW REQUIRED' in markdown
    assert 'No write is approved.' in markdown
    assert 'R3/R4 must not begin until Nickolis reviews the update manifest.' in markdown


def test_a_failed_run_cannot_exit_zero(tmp_path):
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['innings_pitched'])
    report = _resync(report)
    assert _run_main(tmp_path, report) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['failed_invariant']
    assert 'FOUNDATION 3C R2 — FAILED' in (tmp_path / 'summary.md').read_text()
    # The artifact set stays complete so a reviewer never wonders what was held.
    assert json.loads((tmp_path / 'manifest.json').read_text())['updates'] == []


def test_a_missing_report_fails(tmp_path):
    assert _run_main(tmp_path, None) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['failed_invariant'] == 'report_file_exists'


def test_unparsable_json_fails(tmp_path):
    (tmp_path / 'report.json').write_text('{not json')
    assert _run_main(tmp_path, None) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['failed_invariant'] == 'report_is_valid_json'


def test_a_non_object_report_fails(tmp_path):
    (tmp_path / 'report.json').write_text('[]')
    assert _run_main(tmp_path, None) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['failed_invariant'] == 'report_is_an_object'


def test_the_summary_limits_how_many_updates_it_prints(tmp_path):
    report = clean_report()
    rows = [
        _row(900001, 1000 + index, changed=['earned_runs'])
        for index in range(14)
    ]
    report['games'][0]['rows'] = rows
    report = _resync(report)
    assert _run_main(tmp_path, report) == 0
    markdown = (tmp_path / 'summary.md').read_text()
    assert '10 of 14 shown' in markdown
    assert 'The remaining 4 updates are in `r2-update-review.json`.' in markdown
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['updated_row_count'] == 14


@pytest.mark.parametrize('forbidden', [
    'postgresql://', 'postgres://', 'password=', 'Authorization:',
    'X-Admin-Token', 'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
    'Traceback', 'File "', os.sep + 'home' + os.sep,
])
def test_no_output_can_carry_a_credential_or_a_raw_error(tmp_path, forbidden):
    report = clean_report()
    report['games'][0]['rows'][0] = _row(900001, 111, changed=['earned_runs'])
    report = _resync(report)
    _run_main(tmp_path, report)
    for name in ('summary.json', 'summary.md', 'manifest.json', 'manifest.md'):
        assert forbidden not in (tmp_path / name).read_text()


def test_a_failed_summary_carries_no_raw_error_text(tmp_path):
    report = clean_report()
    report['games'][0]['error_class'] = 'game_fetch_failed'
    _run_main(tmp_path, report)
    text = (tmp_path / 'summary.json').read_text()
    assert 'Traceback' not in text
    assert 'postgresql://' not in text
    summary = json.loads(text)
    assert summary['next_action'] == 'Rollout stops. R3/R4 must not begin.'


# ═══════════════ End to end against the real pipeline ═══════════════════════
#
# Everything above validates a report this module builds. That proves the
# validator is internally consistent, not that it agrees with the shape the
# merged pipeline actually emits. These tests run the real planner, the real
# canonical writer in planning mode, and the real completeness builder — exactly
# as backend/scripts/game_driven_ingestion.py assembles them — and hand the
# result to the validator untouched.

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
        'pitcher_id': pitcher_row.id,
        'mlb_game_pk': game_pk,
        'game_date': REFERENCE,
        'game_type': 'R',
        'opponent': 'Away Club',
        'opponent_abbreviation': 'AWY',
        'games_started': 0,
        'innings_pitched': 1.0,
        'innings_pitched_outs': 3,
        'pitches_thrown': 15,
        'strikes': 10,
        'hits_allowed': 1,
        'runs_allowed': 0,
        'earned_runs': 0,
        'walks': 0,
        'strikeouts': 2,
        'home_runs_allowed': 0,
        'batters_faced': 4,
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


def _real_shadow_report():
    """Exactly what backend/scripts/game_driven_ingestion.py writes to disk."""
    report = game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
    )
    report['publication_completeness'] = (
        game_ingestion_completeness.build_game_ingestion_completeness(REFERENCE)
    )
    return report


def test_a_real_fully_reconciled_window_validates_as_pass(app, monkeypatch):
    with app.app_context():
        _schedule(950001)
        _schedule(950002)
        first = _pitcher(7001)
        second = _pitcher(7002)
        db.session.flush()
        _stored_row(first, 950001)
        _stored_row(second, 950002)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            950001: boxscore([(7001, 'home', pitching_stats())]),
            950002: boxscore([(7002, 'home', pitching_stats())]),
        }))

        report = _real_shadow_report()
        assert report['rows_updated'] == 0

        result = validator.validate(report)
        assert result['summary']['result'] == validator.RESULT_PASS
        assert result['summary']['rows_unchanged'] == 2
        assert result['manifest']['updates'] == []


def test_a_real_official_correction_validates_as_review_required(app, monkeypatch):
    with app.app_context():
        _schedule(950003)
        arm = _pitcher(7003)
        db.session.flush()
        _stored_row(arm, 950003, earned_runs=0, runs_allowed=0)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            950003: boxscore([
                (7003, 'home', pitching_stats(earned_runs=2, runs=2)),
            ]),
        }))

        report = _real_shadow_report()
        result = validator.validate(report)

        assert result['summary']['result'] == validator.RESULT_REVIEW_REQUIRED
        assert result['summary']['rows_updated'] == 1
        assert result['summary']['write_approved'] is False
        entry = result['manifest']['updates'][0]
        assert entry['game_pk'] == 950003
        assert entry['pitcher_mlb_id'] == 7003
        assert 'earned_runs' in entry['semantic_changed_fields']
        assert entry['mutation_digest']


def test_real_decimal_drift_validates_as_pass(app, monkeypatch):
    """The pre-PR-571 regression, end to end: drift must stay a non-change."""
    with app.app_context():
        _schedule(950004)
        arm = _pitcher(7004)
        db.session.flush()
        # One recorded out. The stored decimal differs from a freshly derived
        # 1/3 in representation only, inside the CHECK constraint's tolerance.
        _stored_row(
            arm, 950004, innings_pitched_outs=1, innings_pitched=0.333333,
            hits_allowed=0, strikeouts=1, batters_faced=1, strikes=3,
            pitches_thrown=4,
        )
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            950004: boxscore([(7004, 'home', pitching_stats(
                innings='0.1', hits=0, strikeouts=1, batters_faced=1,
                strikes=3, pitches=4,
            ))]),
        }))

        report = _real_shadow_report()
        assert report['rows_updated'] == 0
        assert report['derived_companion_differences_ignored'] == 1

        result = validator.validate(report)
        assert result['summary']['result'] == validator.RESULT_PASS
        assert result['summary']['derived_companion_differences_ignored'] == 1
        assert result['summary']['decimal_only_updates_suppressed'] == 1
        assert 'innings_pitched' not in result['summary']['changed_fields_counts']


def test_a_real_blocked_row_is_a_rollout_stop(app, monkeypatch):
    """An incomplete official line cannot be presented as reviewable."""
    with app.app_context():
        _schedule(950005)
        arm = _pitcher(7005)
        db.session.flush()
        _stored_row(arm, 950005)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            950005: boxscore([
                (7005, 'home', pitching_stats(complete=False)),
            ]),
        }))

        report = _real_shadow_report()
        assert report['rows_blocked'] == 1

        failure = _failure(report)
        assert failure.invariant == 'rows_blocked'


def test_a_real_new_appearance_is_a_rollout_stop(app, monkeypatch):
    """A projected insert needs investigation, not automatic review."""
    with app.app_context():
        _schedule(950006)
        _pitcher(7006)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            950006: boxscore([(7006, 'home', pitching_stats())]),
        }))

        report = _real_shadow_report()
        assert report['rows_inserted'] == 1

        failure = _failure(report)
        assert failure.invariant == 'rows_inserted'


def test_the_real_report_carries_every_key_the_validator_requires(app, monkeypatch):
    """Guards against the merged report shape drifting away from this gate."""
    with app.app_context():
        _schedule(950007)
        arm = _pitcher(7007)
        db.session.flush()
        _stored_row(arm, 950007)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            950007: boxscore([(7007, 'home', pitching_stats())]),
        }))

        report = _real_shadow_report()

        for key in (
            'status', 'mode', 'reference_date', 'execution_scope_mode',
            'requested_game_pks', 'requested_game_count',
            'duplicate_requested_count', 'planned_game_pks',
            'planned_game_count', 'unexpected_planned_game_pks',
            'missing_requested_game_pks', 'execution_scope_exact_match',
            'games_discovered', 'games_planned', 'games_attempted',
            'games_fetched', 'games_completed', 'games_failed',
            'games_remaining', 'budget_stop_triggered', 'budget_stop',
            'failure_classes', 'finality_conflicts',
            'schedule_authority_missing', 'critical_games_unresolved',
            'rows_expected', 'rows_inserted', 'rows_updated', 'rows_unchanged',
            'rows_blocked', 'changed_fields_counts', 'mutation_category_counts',
            'statistical_corrections', 'authority_reconciliations',
            'provenance_only_updates', 'canonical_outs_corrections',
            'derived_companion_fields_applied',
            'derived_companion_differences_ignored',
            'decimal_only_updates_suppressed', 'innings_semantics_version',
            'reconciliation_plan_version', 'parity_contract_version',
            'reconciliation_plan_fingerprint', 'games',
            'publication_completeness',
        ):
            assert key in report, key

        row = report['games'][0]['rows'][0]
        for key in (
            'game_pk', 'pitcher_mlb_id', 'action', 'changed_fields',
            'changed_field_count', 'mutation_categories', 'governed_and_safe',
            'blocked_reason', 'mutation_digest', 'semantic_changed_fields',
            'applied_changed_fields', 'derived_companion_fields',
            'derived_companion_differences_ignored',
            'affects_published_evidence', 'is_statistical_correction',
            'is_provenance_only', 'appearance_team_reason',
        ):
            assert key in row, key


# ═══════════════ Pitcher identity (D-009) ═══════════════════════════════════
#
# The hidden-mutation class: production R2 reported 946 unchanged rows, an
# empty update manifest, and PASS, while carrying 942 identity actions write
# mode would have applied.


def _hidden_identity_report(action='update_metadata', count=3):
    """A report whose GameLog half is spotless and whose identity half is not."""
    report = clean_report()
    rows = report['games'][0]['rows']
    for index in range(min(count, len(rows))):
        rows[index].update({
            'pitcher_identity_action': action,
            'pitcher_identity_changed_fields': ['active', 'team_id'],
            'pitcher_identity_applied_fields': ['active', 'team_id'],
            'pitcher_identity_mutation_digest': f'identity{index}',
        })
    return _resync(report)


def test_the_pre_repair_production_population_cannot_pass():
    report = _hidden_identity_report()
    # The GameLog half is genuinely clean, exactly as production reported.
    assert report['rows_updated'] == 0
    assert report['changed_fields_counts'] == {}
    failure = _failure(report)
    assert 'retired' in failure.invariant or 'identity' in failure.invariant


@pytest.mark.parametrize('action', ['update_metadata', 'reactivate', 'create'])
def test_a_retired_identity_action_is_failed_not_review_required(action):
    failure = _failure(_hidden_identity_report(action))
    assert 'retired' in failure.invariant


def test_a_current_state_identity_mutation_fails():
    report = clean_report()
    report['games'][0]['rows'][0].update({
        'pitcher_identity_action': 'unchanged',
        'pitcher_identity_changed_fields': ['team_id'],
        'pitcher_identity_applied_fields': ['team_id'],
        'pitcher_identity_mutation_digest': 'd',
    })
    report = _resync(report)
    failure = _failure(report)
    assert 'never_writes_current_state_team_id' in failure.invariant


def test_a_blocked_identity_fails():
    report = clean_report()
    report['games'][0]['rows'][0].update({
        'pitcher_identity_action': pitcher_identity.ACTION_BLOCKED,
    })
    report = _resync(report)
    failure = _failure(report)
    assert 'identity_is_not_blocked' in failure.invariant


def test_an_unknown_identity_field_fails():
    report = clean_report()
    report['games'][0]['rows'][0].update({
        'pitcher_identity_action': (
            pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY
        ),
        'pitcher_identity_changed_fields': ['mystery_identity_column'],
        'pitcher_identity_applied_fields': ['mystery_identity_column'],
        'pitcher_identity_mutation_digest': 'd',
    })
    report = _resync(report)
    failure = _failure(report)
    assert 'mystery_identity_column_is_governed' in failure.invariant


def test_a_row_without_an_identity_action_fails():
    """An unrepaired report omits the field entirely; that is not a pass."""
    report = _resync(clean_report())
    report['games'][0]['rows'][0]['pitcher_identity_action'] = None
    failure = _failure(report)
    assert 'reports_a_pitcher_identity_action' in failure.invariant


def _creation_report(count=2):
    report = clean_report()
    creation = _identity(
        pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
        changed=sorted(pitcher_identity.MINIMAL_CREATION_FIELDS),
        digest='createdigest',
    )
    for index in range(count):
        report['games'][0]['rows'][index] = _row(
            900001, 111 + index, identity=creation,
        )
    return _resync(report)


def test_a_safe_minimal_creation_is_review_required_not_pass():
    report = _creation_report()
    result = validator.validate(report)
    summary = result['summary']
    assert summary['result'] == validator.RESULT_REVIEW_REQUIRED
    assert summary['pitcher_identity_creations'] == 2
    assert summary['complete_mutation_count'] == 2
    assert summary['write_approved'] is False
    # GameLog is untouched, so this is purely the identity class.
    assert summary['rows_updated'] == 0


def test_the_manifest_cannot_stay_empty_while_identity_mutations_exist():
    manifest = validator.validate(_creation_report())['manifest']
    assert manifest['updated_row_count'] == 2
    assert manifest['updates']
    assert manifest['mutation_target_counts']['pitcher_identity'] == 2
    for entry in manifest['updates']:
        assert entry['mutation_target'] == 'pitcher_identity'
        assert entry['mutation_digest'] == 'createdigest'


def test_the_manifest_orders_by_target_then_game_then_pitcher():
    report = _creation_report(count=1)
    report['games'][1]['rows'][0] = _row(900002, 221, changed=['earned_runs'])
    report = _resync(report)
    manifest = validator.validate(report)['manifest']
    keys = [
        (entry['mutation_target'], entry['game_pk'], entry['pitcher_mlb_id'])
        for entry in manifest['updates']
    ]
    assert keys == [
        ('game_log', 900002, 221),
        ('pitcher_identity', 900001, 111),
    ]


def test_top_level_identity_counts_must_agree_with_the_rows():
    report = clean_report()
    report['pitcher_identity_mutations'] = 5
    failure = _failure(report)
    assert 'pitcher_identity_mutations_matches_rows' in failure.invariant


def test_the_unique_pitcher_count_is_deterministic():
    report = _creation_report(count=2)
    # The same pitcher appearing in two games counts once.
    report['games'][1]['rows'][0] = _row(
        900002, 111,
        identity=_identity(
            pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
            changed=sorted(pitcher_identity.MINIMAL_CREATION_FIELDS),
            digest='createdigest',
        ),
    )
    report = _resync(report)
    summary = validator.validate(report)['summary']
    assert summary['pitcher_identity_creations'] == 3
    assert summary['pitcher_identity_unique_pitchers_affected'] == 2


def test_suppressed_field_counts_reconcile():
    report = clean_report()
    report['games'][0]['rows'][0] = _row(
        900001, 111, identity=_identity(suppressed=['active', 'team_id']),
    )
    report = _resync(report)
    summary = validator.validate(report)['summary']
    assert summary['result'] == validator.RESULT_PASS
    assert summary['historical_current_state_changes_suppressed'] == 1
    assert summary['suppressed_current_state_field_counts'] == {
        'active': 1, 'team_id': 1,
    }
    # Refused evidence is never a mutation.
    assert summary['complete_mutation_count'] == 0


def test_a_suppressed_field_count_mismatch_fails():
    report = clean_report()
    report['suppressed_current_state_field_counts'] = {'team_id': 9}
    failure = _failure(report)
    assert 'suppressed_current_state_field_counts_match_rows' in failure.invariant


def test_the_complete_mutation_count_must_match_its_targets():
    report = clean_report()
    report['complete_mutation_count'] = 4
    failure = _failure(report)
    assert failure.invariant == 'complete_mutation_count_matches_targets'


def test_the_pass_summary_never_claims_no_mutations_over_a_pending_write(tmp_path):
    assert _run_main(tmp_path, _creation_report()) == 0
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'projects no mutations' not in markdown
    assert 'REVIEW REQUIRED' in markdown
    assert '- Pitcher identity: 2' in markdown
    assert 'No write is approved.' in markdown


def test_the_pass_summary_reports_every_target(tmp_path):
    assert _run_main(tmp_path, clean_report()) == 0
    markdown = (tmp_path / 'summary.md').read_text()
    assert '### Mutations by target' in markdown
    assert '- Pitcher identity: 0' in markdown
    assert '- Total complete-plan mutations: 0' in markdown
    assert 'no mutations to any database target' in markdown


def test_a_hidden_identity_mutation_cannot_exit_zero(tmp_path):
    assert _run_main(tmp_path, _hidden_identity_report()) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['failed_invariant']
