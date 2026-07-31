"""Foundation 3C — the R5 full remaining-window shadow authorization.

R5 is the last read-only gate before a 99-game production write. It runs the
entire remaining bootstrap window in one pass, proves the run changed nothing at
all, and produces the reviewed package R6 will be built from.

Two properties carry most of the weight here and are tested hardest:

  EXACT SCOPE — exactly the 99 approved games, in canonical order, with none of
  the ten completed games present and nothing else added. Counts alone are not
  trusted; sets and ordered sequences are compared.

  ZERO DRIFT — the before and after snapshots must be identical across every
  hashed family. A shadow that wrote anything fails.

The YAML parser is imported inside a fixture rather than via
`pytest.importorskip`, so a missing parser makes these tests ERROR loudly
instead of silently skipping the rollout guards they exist to enforce.
"""

import ast
import inspect as inspect_module
import json
import subprocess
import tempfile
import os
from datetime import datetime, timedelta
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
from models.scheduled_game import ScheduledGame
from scripts import r5_remaining_window_scope as scope
from scripts import validate_r5_remaining_shadow as validator
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
    / 'foundation-3c-r5-remaining-window-shadow.yml'
)

APPROVED_ORDER = scope.CANONICAL_ORDER
APPROVED_SET = scope.SORTED_SET
COMPLETED = scope.COMPLETED_GAME_PKS
TOTAL_ROWS = scope.EXPECTED_TOTAL_ROWS        # 865
TOTAL_IGNORED = scope.EXPECTED_TOTAL_IGNORED  # 291


# ── Deterministic per-game shape ────────────────────────────────────────────
# 73 games of 9 rows + 26 of 8 == 865. 93 games of 3 ignored + 6 of 2 == 291.
# Chosen so every game's ignored count stays well below its row count.
def _rows_for(index):
    return 9 if index < 73 else 8


def _ignored_for(index):
    return 3 if index < 93 else 2


ROWS_BY_GAME = {
    game_pk: _rows_for(index) for index, game_pk in enumerate(APPROVED_ORDER)
}
IGNORED_BY_GAME = {
    game_pk: _ignored_for(index) for index, game_pk in enumerate(APPROVED_ORDER)
}


def test_the_test_fixture_shape_matches_the_approved_totals():
    assert sum(ROWS_BY_GAME.values()) == TOTAL_ROWS == 865
    assert sum(IGNORED_BY_GAME.values()) == TOTAL_IGNORED == 291
    assert all(
        IGNORED_BY_GAME[pk] <= ROWS_BY_GAME[pk] for pk in APPROVED_ORDER
    )


# ═══════════════ Scope module ═══════════════════════════════════════════════


def test_the_scope_contains_exactly_99_unique_positive_games():
    assert len(APPROVED_ORDER) == 99
    assert len(set(APPROVED_ORDER)) == 99
    assert all(isinstance(pk, int) and pk > 0 for pk in APPROVED_ORDER)


def test_the_completed_set_is_exactly_ten_and_held_separately():
    assert len(COMPLETED) == 10
    assert len(set(COMPLETED)) == 10
    assert set(COMPLETED) == {
        823518, 824735, 823761, 824083, 824327,
        823110, 825055, 824004, 823438, 824408,
    }


def test_no_completed_game_appears_in_the_r5_scope():
    assert not set(APPROVED_ORDER) & set(COMPLETED)


def test_the_union_is_exactly_the_109_game_governed_window():
    assert len(set(APPROVED_ORDER) | set(COMPLETED)) == 109


def test_the_sorted_set_and_canonical_order_hold_the_same_games():
    assert APPROVED_SET == tuple(sorted(APPROVED_ORDER))
    assert set(APPROVED_SET) == set(APPROVED_ORDER)


def test_the_expected_shape_is_derived_arithmetic_not_a_guess():
    assert scope.FULL_WINDOW_GAMES - 5 - 5 == 99
    assert (
        scope.FULL_WINDOW_ROWS - scope.ORIGINAL_COMPLETED_ROWS
        - scope.R4_COMPLETED_ROWS
    ) == 865
    assert (
        scope.FULL_WINDOW_IGNORED - scope.ORIGINAL_COMPLETED_IGNORED
        - scope.R4_COMPLETED_IGNORED
    ) == 291


def test_the_scope_digest_is_deterministic_and_order_independent():
    first = scope.scope_digest(APPROVED_ORDER)
    second = scope.scope_digest(tuple(reversed(APPROVED_ORDER)))
    assert first == second == scope.SCOPE_DIGEST
    assert len(scope.SCOPE_DIGEST) == 64


def test_the_scope_digest_changes_when_the_set_changes():
    mutated = list(APPROVED_ORDER)[:-1] + [999999]
    assert scope.scope_digest(mutated) != scope.SCOPE_DIGEST


def test_the_only_game_pk_arguments_cover_every_game_in_order():
    arguments = scope.only_game_pk_arguments()
    assert arguments.count('--only-game-pk') == 99
    assert len(arguments) == 198
    ids = [int(arguments[i + 1]) for i, a in enumerate(arguments)
           if a == '--only-game-pk']
    assert ids == list(APPROVED_ORDER)


# ═══════════════ Workflow fixtures ══════════════════════════════════════════


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    # Declared in backend/requirements.txt. Imported here so a missing parser
    # can neither abort collection nor silently skip: these tests error loudly.
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
def executable_text(workflow_text):
    """The workflow with comment lines removed.

    The header comment names the options this workflow must never pass, which
    is exactly the documentation worth keeping — but a flag inside a comment is
    not passed to anything, so the prohibition guards are asserted against
    executable content instead of raw text.
    """
    return '\n'.join(
        line for line in workflow_text.splitlines()
        if not line.strip().startswith('#')
    )


@pytest.fixture(scope='module')
def shadow_argv(job):
    """The argv the workflow ACTUALLY builds, by running its own shell block.

    The scope lives in a Bash array that is expanded into repeated flags, so
    reading the YAML text proves nothing about what the command receives.
    This executes the real block with the python call replaced by an echo.
    """
    step = next(
        s for s in job['steps']
        if (s.get('name') or '').startswith('Run the exact')
    )
    script = step['run'].replace(
        'python backend/scripts/game_driven_ingestion.py',
        'printf "%s\\n"',
    )
    script = script.replace('set +e', ':').replace('shadow_exit=$?', ':')
    script = script.replace(
        'echo "shadow_exit=$shadow_exit" >> "$GITHUB_OUTPUT"', ':'
    )
    prelude = 'REFERENCE_DATE=2026-07-29\nSHADOW_PATH=out.json\n'
    with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as handle:
        handle.write(prelude + script)
        path = handle.name
    try:
        result = subprocess.run(
            ['bash', path], capture_output=True, text=True, check=False,
        )
    finally:
        os.unlink(path)
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.split('\n') if line.strip()]


# ═══════════════ Parser-independent guards ══════════════════════════════════


def test_the_workflow_file_exists():
    assert WORKFLOW_PATH.is_file()


def test_no_forbidden_option_appears_in_executable_content(executable_text):
    for option in (
        '--game-pk ', '--max-games', '--time-budget-seconds',
        '--include-backfill', '--expected-plan-fingerprint', '--plan-only',
    ):
        assert option not in executable_text, option


def test_no_write_or_authoritative_mode_appears(executable_text):
    assert '--mode write' not in executable_text
    assert '--mode authoritative' not in executable_text
    assert executable_text.count('--mode shadow') == 1


def test_no_other_pipeline_entry_point_is_invoked(workflow_text):
    for script in (
        'run_daily_sync.py', 'run_postgame_refresh.py',
        'refresh_slate_schedule.py', 'publish_snapshot', 'share_artifact',
        'warm_cache',
    ):
        assert script not in workflow_text, script


def test_no_deployment_command_appears(executable_text):
    lowered = executable_text.lower()
    for command in ('render', 'vercel', 'deploy', 'curl ', 'wget '):
        assert command not in lowered, command


def test_the_automated_lane_stays_off(workflow_text):
    assert "GAME_DRIVEN_INGESTION_MODE: 'off'" in workflow_text
    assert "AUTO_SYNC: 'false'" in workflow_text


def test_the_established_secret_names_are_used(workflow_text):
    for secret in (
        'secrets.DATABASE_URL', 'secrets.SECRET_KEY',
        'secrets.BASEBALLOS_ADMIN_API_TOKEN',
    ):
        assert secret in workflow_text, secret


def test_the_reference_date_is_hard_coded(workflow_text):
    assert "REFERENCE_DATE: '2026-07-29'" in workflow_text


def test_the_scope_is_not_populated_from_a_dynamic_source(job):
    """No command substitution, network call, or query may build the scope."""
    step = next(
        s for s in job['steps']
        if (s.get('name') or '').startswith('Run the exact')
    )
    script = step['run']
    array = script.split('R5_GAME_PKS=(')[1].split(')')[0]
    for construct in ('$(', '`', 'curl', 'psql', 'python', 'http', '${'):
        assert construct not in array, construct
    # Every array entry is a bare integer literal.
    entries = [line.strip() for line in array.splitlines() if line.strip()]
    assert len(entries) == 99
    assert all(entry.isdigit() for entry in entries)
    assert [int(entry) for entry in entries] == list(APPROVED_ORDER)


def test_the_scope_cannot_be_altered_by_a_workflow_input(executable_text):
    assert 'inputs' not in executable_text
    assert 'github.event.inputs' not in executable_text
    assert 'env.R5_GAME_PKS' not in executable_text


# ═══════════════ Structural contract ════════════════════════════════════════


def test_the_workflow_name_is_the_agreed_one(workflow):
    assert workflow['name'] == (
        'Foundation 3C R5 Remaining Window Shadow Authorization'
    )


def test_the_trigger_is_manual_only(workflow):
    triggers = workflow.get(True, workflow.get('on'))
    assert set(triggers) == {'workflow_dispatch'}


def test_the_workflow_declares_no_inputs(workflow):
    triggers = workflow.get(True, workflow.get('on'))
    assert not (triggers['workflow_dispatch'] or {})


def test_no_automatic_trigger_exists(workflow):
    triggers = workflow.get(True, workflow.get('on'))
    for automatic in (
        'schedule', 'push', 'pull_request', 'workflow_call',
        'repository_dispatch', 'workflow_run',
    ):
        assert automatic not in triggers, automatic


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_no_write_permission_is_requested(workflow):
    for value in workflow['permissions'].values():
        assert value == 'read'


def test_the_timeout_is_finite(job):
    assert isinstance(job['timeout-minutes'], int)
    assert 0 < job['timeout-minutes'] <= 60


def test_concurrency_joins_the_production_write_group(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_concurrency_does_not_cancel_in_progress(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_the_runner_is_pinned(job):
    assert job['runs-on'] == 'ubuntu-latest'


# ═══════════════ Command construction, proven at runtime ════════════════════


def test_exactly_one_ingestion_invocation_exists(run_commands):
    invocations = [
        line for line in run_commands if 'game_driven_ingestion.py' in line
    ]
    assert len(invocations) == 1


def test_the_runtime_argv_carries_exactly_99_only_game_pk_flags(shadow_argv):
    assert shadow_argv.count('--only-game-pk') == 99


def test_the_runtime_argv_carries_the_exact_approved_ids(shadow_argv):
    ids = [
        int(shadow_argv[i + 1]) for i, a in enumerate(shadow_argv)
        if a == '--only-game-pk'
    ]
    assert ids == list(APPROVED_ORDER)
    assert sorted(ids) == list(APPROVED_SET)


def test_the_runtime_argv_ids_are_unique(shadow_argv):
    ids = [
        int(shadow_argv[i + 1]) for i, a in enumerate(shadow_argv)
        if a == '--only-game-pk'
    ]
    assert len(set(ids)) == 99


def test_the_runtime_argv_excludes_every_completed_game(shadow_argv):
    ids = {
        int(shadow_argv[i + 1]) for i, a in enumerate(shadow_argv)
        if a == '--only-game-pk'
    }
    assert not ids & set(COMPLETED)


def test_the_runtime_argv_requests_shadow_mode(shadow_argv):
    assert shadow_argv[shadow_argv.index('--mode') + 1] == 'shadow'


def test_the_runtime_argv_uses_the_pinned_reference_date(shadow_argv):
    assert shadow_argv[shadow_argv.index('--reference-date') + 1] == '2026-07-29'


def test_the_runtime_argv_carries_no_forbidden_option(shadow_argv):
    for option in (
        '--game-pk', '--max-games', '--time-budget-seconds',
        '--include-backfill', '--expected-plan-fingerprint', '--plan-only',
    ):
        assert option not in shadow_argv, option


def test_the_scope_ordering_is_deterministic(shadow_argv):
    """Two expansions of the same block produce the same sequence."""
    ids = [
        int(shadow_argv[i + 1]) for i, a in enumerate(shadow_argv)
        if a == '--only-game-pk'
    ]
    assert ids == list(APPROVED_ORDER)
    assert scope.scope_digest(ids) == scope.SCOPE_DIGEST


# ═══════════════ Step order ═════════════════════════════════════════════════


def _step_index(job, prefix):
    for index, step in enumerate(job['steps']):
        if (step.get('name') or '').startswith(prefix):
            return index
    raise AssertionError(prefix)


def test_the_before_state_is_captured_before_the_shadow(job):
    assert _step_index(job, 'Capture the before state') < _step_index(
        job, 'Run the exact'
    )


def test_the_after_state_runs_under_always(job):
    step = job['steps'][_step_index(job, 'Capture the after state')]
    assert 'always()' in step['if']


def test_validation_occurs_after_the_after_state(job):
    assert _step_index(job, 'Capture the after state') < _step_index(
        job, 'Validate the complete'
    )


def test_the_credential_scan_occurs_before_upload(job):
    assert _step_index(job, 'Scan artifacts') < _step_index(
        job, 'Upload the R5 artifacts'
    )


def test_the_upload_runs_under_always(job):
    step = job['steps'][_step_index(job, 'Upload the R5 artifacts')]
    assert 'always()' in step['if']
    assert step['with']['retention-days'] == 30
    assert step['with']['if-no-files-found'] == 'warn'
    assert step['with']['name'] == 'foundation-3c-r5-remaining-window-shadow'


def test_the_final_gate_runs_after_upload(job):
    assert _step_index(job, 'Upload the R5 artifacts') < _step_index(
        job, 'Fail the job unless'
    )


def test_the_shadow_only_runs_when_the_before_state_succeeded(job):
    step = job['steps'][_step_index(job, 'Run the exact')]
    assert "steps.before.outputs.before_exit == '0'" in step['if']


def test_every_shell_block_is_syntactically_valid(job):
    for step in job['steps']:
        script = step.get('run')
        if not script:
            continue
        with tempfile.NamedTemporaryFile(
            'w', suffix='.sh', delete=False,
        ) as handle:
            handle.write(script)
            path = handle.name
        try:
            result = subprocess.run(
                ['bash', '-n', path], capture_output=True, text=True,
                check=False,
            )
        finally:
            os.unlink(path)
        assert result.returncode == 0, (step.get('name'), result.stderr)


# ═══════════════ Credential scanner ═════════════════════════════════════════


@pytest.fixture(scope='module')
def scanner_script(job):
    step = job['steps'][_step_index(job, 'Scan artifacts')]
    body = step['run'].split("python - <<'PY'")[1].split('PY')[0]
    return '\n'.join(line[10:] if line.startswith(' ' * 10) else line
                     for line in body.splitlines())


@pytest.mark.parametrize('poison', [
    'postgresql://user:pw@host/db',
    'postgres://user:pw@host/db',
    'password=hunter2',
    'Authorization: Bearer abc',
    'X-Admin-Token: abc',
    'ADMIN_API_TOKEN',
    'SECRET_KEY',
    'DATABASE_URL',
    'BASEBALLOS_ADMIN_API_TOKEN',
    'token=abc',
    'api_key=abc',
    'api-key=abc',
    'secret=abc',
])
def test_the_scanner_rejects_credential_shaped_content(
    scanner_script, tmp_path, poison,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'r5-validation-summary.json').write_text(
        json.dumps({'note': poison})
    )
    script = tmp_path / 'scan.py'
    script.write_text(scanner_script)
    result = subprocess.run(
        ['python', str(script)], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 1
    assert poison not in result.stdout
    assert not (artifacts / 'r5-validation-summary.json').exists()


def test_the_scanner_passes_a_clean_artifact(scanner_script, tmp_path):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'r5-validation-summary.json').write_text(
        json.dumps({'result': 'pass', 'rows_unchanged': 865})
    )
    script = tmp_path / 'scan.py'
    script.write_text(scanner_script)
    result = subprocess.run(
        ['python', str(script)], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0


# ═══════════════ Synthetic reports ══════════════════════════════════════════


def _row(game_pk, index, *, ignored=False, **overrides):
    row = {
        'game_pk': game_pk,
        'pitcher_mlb_id': game_pk * 100 + index,
        'action': reconciliation.ACTION_UNCHANGED,
        'changed_fields': [],
        'semantic_changed_fields': [],
        'applied_changed_fields': [],
        'derived_companion_fields': [],
        'changed_field_count': 0,
        'derived_companion_differences_ignored': (
            ['innings_pitched'] if ignored else []
        ),
        'governed_and_safe': True,
        'blocked_reason': None,
        'affects_published_evidence': False,
        'is_statistical_correction': False,
        'is_provenance_only': False,
        'mutation_digest': '',
        'appearance_team_reason': None,
        'appearance_team_decision': None,
        'pitcher_identity_action': identity.ACTION_UNCHANGED,
        'pitcher_identity_changed_fields': [],
        'pitcher_identity_applied_fields': [],
        'pitcher_identity_suppressed_fields': [],
        'pitcher_identity_governed_and_safe': True,
        'pitcher_identity_blocked_reason': None,
        'pitcher_identity_mutation_digest': '',
        'pitcher_identity_requires_creation': False,
        'pitcher_identity_current_authority_mutation_refused': False,
    }
    row.update(overrides)
    return row


def _game(game_pk, index):
    rows = ROWS_BY_GAME[game_pk]
    ignored = IGNORED_BY_GAME[game_pk]
    return {
        'game_pk': game_pk,
        'represented_date': '2026-07-29',
        'candidate_reason': GameIngestionWorkItem.REASON_EXPLICIT_REPAIR,
        'criticality': GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        'attempt_number': 1,
        'status': 'projected',
        'error_class': None,
        'source_revision': f'rev-{game_pk}',
        'appearances_extracted': rows,
        'inserted': 0,
        'updated': 0,
        'unchanged': rows,
        'blocked': 0,
        'complete_mutation_count': 0,
        'pitcher_identity_mutations': 0,
        'appearance_team_mutations': 0,
        'canonical_outs_corrections': 0,
        'statistical_corrections': 0,
        'derived_companion_differences_ignored': ignored,
        'complete_reconciliation_fingerprint': f'{index:064x}',
        'rows': [
            _row(game_pk, position, ignored=position < ignored)
            for position in range(rows)
        ],
    }


def _shadow_report(**overrides):
    report = {
        'status': 'complete',
        'mode': 'shadow',
        'reference_date': '2026-07-29',
        'execution_scope_mode': 'exclusive',
        'reconciliation_plan_version':
            reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        'requested_game_count': 99,
        'planned_game_count': 99,
        'duplicate_requested_count': 0,
        'execution_scope_exact_match': True,
        'requested_game_pks': list(APPROVED_SET),
        'planned_game_pks': list(APPROVED_SET),
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'games_attempted': 99,
        'games_fetched': 99,
        'games_completed': 99,
        'games_failed': 0,
        'games_remaining': 0,
        'budget_stop_triggered': False,
        'budget_stop': None,
        'finality_conflicts': 0,
        'schedule_authority_missing': 0,
        'failure_classes': {},
        'critical_games_unresolved': 0,
        'best_effort_games_deferred': 0,
        'rows_expected': TOTAL_ROWS,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': TOTAL_ROWS,
        'rows_blocked': 0,
        'changed_fields_counts': {},
        'pitcher_identity_changed_fields_counts': {},
        'pitcher_identity_rows_examined': TOTAL_ROWS,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'canonical_outs_corrections': 0,
        'statistical_corrections': 0,
        'authority_reconciliations': 0,
        'provenance_only_updates': 0,
        'corrections_applied': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': TOTAL_IGNORED,
        'decimal_only_updates_suppressed': TOTAL_IGNORED,
        'complete_reconciliation_fingerprint': 'c' * 64,
        'games': [
            _game(game_pk, index)
            for index, game_pk in enumerate(APPROVED_ORDER)
        ],
    }
    report.update(overrides)
    return report


def _state(phase, **overrides):
    state = {
        'phase': phase,
        'reference_date': '2026-07-29',
        'read_only': {'write_probe_refused': True},
        'read_only_after': {'write_probe_refused': True},
        'selected_game_pks': list(APPROVED_SET),
        'selected_game_count': 99,
        'selected_scope_digest': scope.SCOPE_DIGEST,
        'approved_completed_game_pks': list(COMPLETED),
        'game_log_row_count': TOTAL_ROWS,
        'game_log_content_hash': 'a' * 64,
        'canonical_outs_hash': 'b' * 64,
        'correction_provenance_hash': 'c' * 64,
        'appearance_team_hash': 'd' * 64,
        'pitcher_state_hash': 'e' * 64,
        'pitcher_count': 400,
        'pitcher_mlb_ids': [1, 2, 3],
        'selected_work_items': {},
        'selected_work_item_count': 0,
        'all_work_items_hash': 'f' * 64,
        'all_work_item_count': 10,
        'completed_work_item_set': list(COMPLETED),
        'terminal_work_item_set': [],
        'unresolved_set': list(APPROVED_SET),
        'non_critical_selected_game_pks': [],
        'unplanned_selected_game_pks': [],
        'non_final_selected_game_pks': [],
        'selected_game_pks_with_prior_status': [],
        'selected_game_pks_with_prior_attempts': [],
        'finality_conflicts': 0,
        'schedule_authority_missing': 0,
        'dead_letter_count': 0,
        'publication_completeness': {
            'expected_final_games': 109,
            'completed_final_games': 10,
            'unresolved_final_games': 99,
            'terminal_failure_games': 0,
            'correction_pending_games': 0,
            'critical_appearance_rows_expected': 81,
            'critical_appearance_rows_reconciled': 81,
            'publication_complete': False,
        },
    }
    state.update(overrides)
    return state


def _validate(shadow=None, before=None, after=None):
    return validator.validate_r5(
        before_state=before if before is not None else _state('before'),
        shadow=shadow if shadow is not None else _shadow_report(),
        after_state=after if after is not None else _state('after'),
    )


def _fails(invariant_fragment, **kwargs):
    with pytest.raises(validator.ValidationFailure) as caught:
        _validate(**kwargs)
    assert invariant_fragment in caught.value.invariant, caught.value.invariant
    return caught.value


# ═══════════════ Happy path ═════════════════════════════════════════════════


def test_the_exact_clean_99_game_report_passes():
    decision = _validate()
    assert decision['result'] == validator.RESULT_PASS
    assert decision['shadow']['total_rows'] == 865
    assert decision['shadow']['total_ignored'] == 291
    assert decision['failed_invariant'] is None


# ═══════════════ Scope failures ═════════════════════════════════════════════


def test_requested_count_98_fails():
    _fails('requested_game_count',
           shadow=_shadow_report(requested_game_count=98))


def test_requested_count_100_fails():
    _fails('requested_game_count',
           shadow=_shadow_report(requested_game_count=100))


def test_a_missing_approved_game_fails():
    report = _shadow_report()
    report['games'] = report['games'][:-1]
    report['requested_game_pks'] = list(APPROVED_SET)[:-1]
    _fails('requested_game_pks', shadow=report)


def test_an_extra_game_fails():
    report = _shadow_report()
    report['requested_game_pks'] = list(APPROVED_SET) + [999999]
    _fails('requested_game_pks', shadow=report)


def test_a_duplicate_requested_game_fails():
    _fails('duplicate_requested_count',
           shadow=_shadow_report(duplicate_requested_count=1))


def test_a_completed_game_inside_the_scope_fails():
    report = _shadow_report()
    report['requested_game_pks'] = sorted(
        list(APPROVED_SET)[:-1] + [COMPLETED[0]]
    )
    _fails('requested_game_pks', shadow=report)


def test_a_completed_game_inside_the_per_game_list_fails():
    report = _shadow_report()
    report['games'][0]['game_pk'] = COMPLETED[0]
    _fails('excludes_completed_games', shadow=report)


def test_an_unknown_game_fails():
    report = _shadow_report()
    report['games'][5]['game_pk'] = 999999
    _fails('canonical_processing_order', shadow=report)


def test_wrong_canonical_order_fails():
    report = _shadow_report()
    report['games'][0], report['games'][1] = (
        report['games'][1], report['games'][0]
    )
    _fails('canonical_processing_order', shadow=report)


def test_a_planned_set_mismatch_fails():
    report = _shadow_report()
    report['planned_game_pks'] = list(APPROVED_SET)[:-1] + [999999]
    _fails('planned_game_pks', shadow=report)


def test_a_non_exclusive_scope_fails():
    _fails('execution_scope_mode',
           shadow=_shadow_report(execution_scope_mode='window'))


def test_scope_exact_match_false_fails():
    _fails('execution_scope_exact_match',
           shadow=_shadow_report(execution_scope_exact_match=False))


def test_a_missing_requested_game_list_fails():
    _fails('missing_requested_game_pks',
           shadow=_shadow_report(missing_requested_game_pks=[823519]))


def test_an_unexpected_planned_game_fails():
    _fails('unexpected_planned_game_pks',
           shadow=_shadow_report(unexpected_planned_game_pks=[999999]))


def test_the_completed_games_are_explicitly_excluded_from_the_report():
    """A completed game gets its own named failure, not a generic one."""
    report = _shadow_report()
    report['games'][0]['game_pk'] = COMPLETED[0]
    failure = _fails('excludes_completed_games', shadow=report)
    assert failure.observed == [COMPLETED[0]]


# ═══════════════ Report identity ════════════════════════════════════════════


def test_a_wrong_parity_contract_fails():
    _fails('parity_contract_version',
           shadow=_shadow_report(parity_contract_version='3'))


def test_a_wrong_reference_date_fails():
    _fails('reference_date', shadow=_shadow_report(reference_date='2026-07-28'))


def test_a_non_shadow_mode_fails():
    _fails('mode', shadow=_shadow_report(mode='write'))


def test_an_incomplete_status_fails():
    _fails('status', shadow=_shadow_report(status='incomplete'))


@pytest.mark.parametrize('field', [
    'reconciliation_plan_version', 'innings_semantics_version',
    'complete_plan_version', 'identity_plan_version',
])
def test_a_wrong_version_constant_fails(field):
    _fails(field, shadow=_shadow_report(**{field: '99'}))


# ═══════════════ Before state ═══════════════════════════════════════════════


def test_before_completeness_not_10_99_fails():
    state = _state('before')
    state['publication_completeness']['completed_final_games'] = 9
    _fails('completeness_completed_final_games', before=state)


def test_a_completed_set_mismatch_fails():
    _fails('completed_work_item_set',
           before=_state('before', completed_work_item_set=list(COMPLETED)[:-1]))


def test_an_unresolved_set_mismatch_fails():
    _fails('unresolved_set',
           before=_state('before', unresolved_set=list(APPROVED_SET)[:-1]))


def test_a_terminal_failure_present_fails():
    _fails('terminal_work_item_set',
           before=_state('before', terminal_work_item_set=[823519]))


def test_a_prior_work_item_on_a_selected_game_fails():
    state = _state('before', selected_work_items={
        '823519': {'status': 'planned', 'completed': False},
    })
    _fails('selected_games_have_no_work_item', before=state)


def test_a_selected_game_with_a_prior_status_fails():
    _fails('selected_game_pks_with_prior_status',
           before=_state('before',
                         selected_game_pks_with_prior_status=[823519]))


def test_a_selected_game_with_prior_attempts_fails():
    _fails('selected_game_pks_with_prior_attempts',
           before=_state('before',
                         selected_game_pks_with_prior_attempts=[823519]))


def test_a_non_publication_critical_selected_game_fails():
    _fails('non_critical_selected_game_pks',
           before=_state('before', non_critical_selected_game_pks=[823519]))


def test_a_non_final_selected_game_fails():
    _fails('non_final_selected_game_pks',
           before=_state('before', non_final_selected_game_pks=[823519]))


def test_an_unplanned_selected_game_fails():
    _fails('unplanned_selected_game_pks',
           before=_state('before', unplanned_selected_game_pks=[823519]))


def test_a_correction_pending_game_fails():
    state = _state('before')
    state['publication_completeness']['correction_pending_games'] = 1
    _fails('completeness_correction_pending_games', before=state)


def test_a_finality_conflict_fails():
    _fails('before_state_finality_conflicts',
           before=_state('before', finality_conflicts=1))


def test_missing_schedule_authority_fails():
    _fails('before_state_schedule_authority_missing',
           before=_state('before', schedule_authority_missing=1))


def test_a_before_state_that_was_not_read_only_fails():
    _fails('before_state_read_only',
           before=_state('before', read_only={'write_probe_refused': False}))


def test_a_before_state_missing_an_eligibility_field_fails():
    state = _state('before')
    del state['non_final_selected_game_pks']
    _fails('non_final_selected_game_pks_present', before=state)


def test_a_before_state_scope_digest_mismatch_fails():
    _fails('scope_digest', before=_state('before', selected_scope_digest='x' * 64))


# ═══════════════ Games ══════════════════════════════════════════════════════


def test_a_budget_stop_fails():
    _fails('budget_stop_triggered',
           shadow=_shadow_report(budget_stop_triggered=True))


def test_a_budget_stop_payload_fails():
    _fails('budget_stop_is_null',
           shadow=_shadow_report(budget_stop={'remaining': 3}))


def test_a_failed_game_fails():
    _fails('games_failed', shadow=_shadow_report(games_failed=1))


def test_games_remaining_nonzero_fails():
    _fails('games_remaining', shadow=_shadow_report(games_remaining=1))


def test_a_failure_class_fails():
    _fails('failure_classes',
           shadow=_shadow_report(failure_classes={'fetch': 1}))


def test_an_unresolved_critical_game_fails():
    _fails('critical_games_unresolved',
           shadow=_shadow_report(critical_games_unresolved=1))


def test_a_game_error_class_fails():
    report = _shadow_report()
    report['games'][3]['error_class'] = 'game_fetch_failed'
    _fails('error_class', shadow=report)


def test_a_non_projected_game_status_fails():
    report = _shadow_report()
    report['games'][3]['status'] = 'reconciled'
    _fails('status', shadow=report)


def test_an_attempt_number_above_one_fails():
    report = _shadow_report()
    report['games'][3]['attempt_number'] = 2
    _fails('attempt_number', shadow=report)


def test_a_best_effort_game_fails():
    report = _shadow_report()
    report['games'][3]['criticality'] = (
        GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    )
    _fails('criticality', shadow=report)


def test_an_unexpected_candidate_reason_fails():
    report = _shadow_report()
    report['games'][3]['candidate_reason'] = (
        GameIngestionWorkItem.REASON_CORRECTED_FINAL
    )
    _fails('candidate_reason', shadow=report)


def test_the_expected_candidate_reason_is_the_exclusive_scope_one():
    """Exclusive scope short-circuits to explicit_repair; newly_final never."""
    assert validator.EXPECTED_CANDIDATE_REASON == 'explicit_repair'


# ═══════════════ Rows ═══════════════════════════════════════════════════════


def test_row_total_864_fails():
    _fails('rows_expected', shadow=_shadow_report(rows_expected=864))


def test_row_total_866_fails():
    _fails('rows_expected', shadow=_shadow_report(rows_expected=866))


def test_correct_aggregate_with_short_row_lists_fails():
    """The aggregate is right and the detail is not. Recomputation catches it."""
    report = _shadow_report()
    report['games'][0]['rows'] = report['games'][0]['rows'][:-1]
    _fails('appearances_match_rows', shadow=report)


def test_correct_aggregate_and_appearances_but_short_rows_fails():
    report = _shadow_report()
    report['games'][0]['rows'] = report['games'][0]['rows'][:-1]
    report['games'][0]['appearances_extracted'] -= 1
    _fails('recomputed_row_total', shadow=report)


def test_a_duplicate_appearance_identity_fails():
    report = _shadow_report()
    rows = report['games'][0]['rows']
    rows[1]['pitcher_mlb_id'] = rows[0]['pitcher_mlb_id']
    _fails('duplicate_appearance_identity', shadow=report)


def test_the_row_total_identity_holds_on_a_clean_report():
    """inserted + updated + unchanged + blocked == 865.

    A backstop rather than an independently reachable failure: each term is
    already pinned individually above, so any deviation trips the specific
    check first. Asserted here so the identity itself is covered and cannot be
    quietly dropped from the validator.
    """
    report = _shadow_report()
    assert (
        report['rows_inserted'] + report['rows_updated']
        + report['rows_unchanged'] + report['rows_blocked']
    ) == report['rows_expected'] == 865
    assert _validate(shadow=report)['result'] == validator.RESULT_PASS


def test_a_gamelog_insert_fails():
    _fails('rows_inserted', shadow=_shadow_report(rows_inserted=1))


def test_a_gamelog_update_fails():
    _fails('rows_updated', shadow=_shadow_report(rows_updated=1))


def test_a_blocked_row_fails():
    _fails('rows_blocked', shadow=_shadow_report(rows_blocked=1))


def test_a_blocked_row_at_game_level_fails():
    report = _shadow_report()
    report['games'][2]['blocked'] = 1
    _fails('_blocked', shadow=report)


def test_a_row_with_changed_fields_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['changed_fields'] = ['earned_runs']
    _fails('changed_fields', shadow=report)


def test_a_row_with_a_nonzero_changed_field_count_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['changed_field_count'] = 1
    _fails('changed_field_count', shadow=report)


def test_a_semantic_innings_change_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['semantic_changed_fields'] = [
        'innings_pitched'
    ]
    _fails('semantic_changed_fields', shadow=report)


def test_a_non_unchanged_row_action_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['action'] = 'update'
    _fails('_action', shadow=report)


def test_a_row_that_affects_published_evidence_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['affects_published_evidence'] = True
    _fails('affects_published_evidence', shadow=report)


def test_a_statistical_correction_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['is_statistical_correction'] = True
    _fails('is_statistical_correction', shadow=report)


def test_a_provenance_only_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['is_provenance_only'] = True
    _fails('is_provenance_only', shadow=report)


def test_a_mutation_digest_on_an_unchanged_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['mutation_digest'] = 'deadbeef'
    _fails('mutation_digest', shadow=report)


def test_a_row_that_is_not_governed_and_safe_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['governed_and_safe'] = False
    _fails('governed_and_safe', shadow=report)


def test_a_blocked_reason_on_a_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['blocked_reason'] = 'conflict'
    _fails('blocked_reason', shadow=report)


# ═══════════════ Identity ═══════════════════════════════════════════════════


def test_a_pitcher_identity_mutation_fails():
    _fails('pitcher_identity_mutations',
           shadow=_shadow_report(pitcher_identity_mutations=1))


def test_a_pitcher_creation_fails():
    _fails('pitcher_identity_creations',
           shadow=_shadow_report(pitcher_identity_creations=1))


def test_a_pitcher_reactivation_fails():
    _fails('pitcher_identity_reactivations',
           shadow=_shadow_report(pitcher_identity_reactivations=1))


def test_a_pitcher_metadata_update_fails():
    _fails('pitcher_identity_metadata_updates',
           shadow=_shadow_report(pitcher_identity_metadata_updates=1))


def test_a_blocked_identity_entry_fails():
    _fails('pitcher_identity_blocked',
           shadow=_shadow_report(pitcher_identity_blocked=1))


@pytest.mark.parametrize('action', sorted(validator.FORBIDDEN_IDENTITY_ACTIONS))
def test_a_forbidden_identity_action_on_a_row_fails(action):
    report = _shadow_report()
    report['games'][0]['rows'][0]['pitcher_identity_action'] = action
    _fails('pitcher_identity_action', shadow=report)


def test_an_identity_digest_on_an_unchanged_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['pitcher_identity_mutation_digest'] = 'abc'
    _fails('identity_mutation_digest', shadow=report)


def test_identity_changed_fields_on_a_row_fail():
    report = _shadow_report()
    report['games'][0]['rows'][0]['pitcher_identity_changed_fields'] = ['team_id']
    _fails('pitcher_identity_changed_fields', shadow=report)


def test_a_row_requiring_identity_creation_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['pitcher_identity_requires_creation'] = True
    _fails('identity_requires_creation', shadow=report)


def test_an_identity_changed_fields_count_map_fails():
    _fails('pitcher_identity_changed_fields_counts',
           shadow=_shadow_report(
               pitcher_identity_changed_fields_counts={'team_id': 1}))


def test_rows_examined_must_equal_the_row_total():
    _fails('pitcher_identity_rows_examined',
           shadow=_shadow_report(pitcher_identity_rows_examined=864))


# ── Suppressed historical current-state evidence ───────────────────────────


def test_suppressed_historical_differences_are_accepted():
    report = _shadow_report()
    row = report['games'][0]['rows'][0]
    row['pitcher_identity_suppressed_fields'] = ['team_id', 'roster_status']
    row['pitcher_identity_current_authority_mutation_refused'] = True
    decision = _validate(shadow=report)
    assert decision['result'] == validator.RESULT_PASS
    assert decision['shadow']['suppressed_rows'] == 1
    assert decision['shadow']['suppressed_field_counts'] == {
        'roster_status': 1, 'team_id': 1,
    }


def test_an_unknown_suppressed_field_fails():
    report = _shadow_report()
    row = report['games'][0]['rows'][0]
    row['pitcher_identity_suppressed_fields'] = ['earned_runs']
    row['pitcher_identity_current_authority_mutation_refused'] = True
    _fails('suppressed_field_is_approved', shadow=report)


def test_a_suppressed_difference_that_does_not_say_it_was_refused_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['pitcher_identity_suppressed_fields'] = [
        'team_id'
    ]
    _fails('current_authority_mutation_refused', shadow=report)


def test_suppressed_differences_do_not_affect_the_fingerprint():
    """Evidence, not mutation: the reviewed fingerprint must not move."""
    clean = _validate()
    report = _shadow_report()
    row = report['games'][0]['rows'][0]
    row['pitcher_identity_suppressed_fields'] = ['team_id']
    row['pitcher_identity_current_authority_mutation_refused'] = True
    suppressed = _validate(shadow=report)
    assert suppressed['shadow']['fingerprint'] == clean['shadow']['fingerprint']


def test_the_approved_suppressible_set_matches_the_real_planner():
    """Probe the actual function rather than trusting a copied literal."""
    source = inspect_module.getsource(identity.suppressed_current_state_fields)
    tree = ast.parse(source.strip())
    emitted = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'append'):
            for argument in node.args:
                if isinstance(argument, ast.Constant):
                    emitted.add(argument.value)
    assert emitted == set(validator.APPROVED_SUPPRESSIBLE_FIELDS)


# ═══════════════ Appearance team ════════════════════════════════════════════


def test_an_appearance_team_mutation_fails():
    _fails('appearance_team_mutations',
           shadow=_shadow_report(appearance_team_mutations=1))


def test_an_appearance_team_reason_on_a_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['appearance_team_reason'] = 'backfilled'
    _fails('appearance_team_reason', shadow=report)


def test_an_appearance_team_decision_on_a_row_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['appearance_team_decision'] = {
        'reason': 'backfill', 'fields': {'appearance_team_id': 147},
    }
    _fails('appearance_team_decision', shadow=report)


def test_a_nonzero_complete_mutation_count_fails():
    _fails('complete_mutation_count',
           shadow=_shadow_report(complete_mutation_count=1))


def test_a_game_level_complete_mutation_count_fails():
    report = _shadow_report()
    report['games'][7]['complete_mutation_count'] = 1
    _fails('complete_mutation_count', shadow=report)


# ═══════════════ Canonical innings ══════════════════════════════════════════


def test_ignored_decimal_count_290_fails():
    _fails('derived_companion_differences_ignored',
           shadow=_shadow_report(derived_companion_differences_ignored=290))


def test_ignored_decimal_count_292_fails():
    _fails('derived_companion_differences_ignored',
           shadow=_shadow_report(derived_companion_differences_ignored=292))


def test_a_suppressed_count_that_disagrees_with_the_ignored_count_fails():
    _fails('decimal_only_updates_suppressed',
           shadow=_shadow_report(decimal_only_updates_suppressed=290))


def test_a_correct_aggregate_with_disagreeing_rows_fails():
    """The run-level 291 is right; the row detail is not."""
    report = _shadow_report()
    report['games'][0]['rows'][0]['derived_companion_differences_ignored'] = []
    _fails('ignored_reconciles', shadow=report)


def test_a_canonical_outs_correction_fails():
    _fails('canonical_outs_corrections',
           shadow=_shadow_report(canonical_outs_corrections=1))


def test_a_statistical_correction_fails():
    _fails('statistical_corrections',
           shadow=_shadow_report(statistical_corrections=1))


def test_a_provenance_only_update_fails():
    _fails('provenance_only_updates',
           shadow=_shadow_report(provenance_only_updates=1))


def test_an_authority_reconciliation_fails():
    _fails('authority_reconciliations',
           shadow=_shadow_report(authority_reconciliations=1))


def test_an_applied_companion_field_fails():
    _fails('derived_companion_fields_applied',
           shadow=_shadow_report(derived_companion_fields_applied=1))


def test_a_changed_fields_count_map_fails():
    _fails('changed_fields_counts',
           shadow=_shadow_report(changed_fields_counts={'earned_runs': 1}))


def test_an_unknown_ignored_companion_field_fails():
    report = _shadow_report()
    report['games'][0]['rows'][0]['derived_companion_differences_ignored'] = [
        'earned_runs'
    ]
    _fails('ignored_difference_is_a_known_companion', shadow=report)


def test_innings_pitched_is_a_known_companion_not_a_semantic_field():
    assert 'innings_pitched' in validator.PROHIBITED_SEMANTIC_FIELDS


# ═══════════════ Fingerprint ════════════════════════════════════════════════


def test_a_missing_run_fingerprint_fails():
    _fails('complete_reconciliation_fingerprint',
           shadow=_shadow_report(complete_reconciliation_fingerprint=None))


def test_an_invalid_fingerprint_length_fails():
    _fails('complete_reconciliation_fingerprint',
           shadow=_shadow_report(complete_reconciliation_fingerprint='c' * 63))


def test_invalid_fingerprint_characters_fail():
    _fails('complete_reconciliation_fingerprint',
           shadow=_shadow_report(
               complete_reconciliation_fingerprint='Z' + 'c' * 63))


def test_a_missing_per_game_fingerprint_fails():
    report = _shadow_report()
    report['games'][4]['complete_reconciliation_fingerprint'] = None
    _fails('complete_reconciliation_fingerprint', shadow=report)


def test_every_one_of_the_99_per_game_fingerprints_is_required():
    decision = _validate()
    fingerprints = [
        game['complete_reconciliation_fingerprint']
        for game in decision['shadow']['per_game']
    ]
    assert len(fingerprints) == 99
    assert all(len(value) == 64 for value in fingerprints)


def test_the_validator_preserves_the_planner_fingerprint():
    """It must not recompute one of its own."""
    report = _shadow_report(complete_reconciliation_fingerprint='9' * 64)
    decision = _validate(shadow=report)
    assert decision['shadow']['fingerprint'] == '9' * 64


# ═══════════════ No-drift proof ═════════════════════════════════════════════


@pytest.mark.parametrize('field', list(validator.IMMUTABLE_STATE_HASHES))
def test_a_state_hash_mismatch_fails(field):
    _fails(f'state_{field}_unchanged', after=_state('after', **{field: '0' * 64}))


def test_a_work_item_count_change_fails():
    _fails('state_all_work_item_count_unchanged',
           after=_state('after', all_work_item_count=11))


def test_a_work_item_hash_change_fails():
    _fails('state_all_work_items_hash_unchanged',
           after=_state('after', all_work_items_hash='0' * 64))


def test_a_completed_set_change_fails():
    _fails('state_completed_work_item_set_unchanged',
           after=_state('after',
                        completed_work_item_set=list(COMPLETED) + [823519]))


def test_a_dead_letter_increase_fails():
    _fails('state_dead_letter_count_unchanged',
           after=_state('after', dead_letter_count=1))


def test_a_completeness_change_fails():
    after = _state('after')
    after['publication_completeness']['completed_final_games'] = 11
    _fails('publication_completeness_unchanged', after=after)


def test_a_work_item_created_for_a_selected_game_fails():
    after = _state('after', selected_work_items={
        '823519': {'status': 'completed', 'completed': True},
    })
    _fails('no_selected_work_item_created', after=after)


def test_a_pitcher_identity_set_change_fails():
    _fails('state_pitcher_mlb_ids_unchanged',
           after=_state('after', pitcher_mlb_ids=[1, 2, 3, 4]))


def test_a_gamelog_row_count_change_fails():
    _fails('state_game_log_row_count_unchanged',
           after=_state('after', game_log_row_count=866))


def test_an_after_state_that_was_not_read_only_fails():
    _fails('after_state_read_only',
           after=_state('after', read_only={'write_probe_refused': False}))


def test_an_unresolved_set_change_fails():
    _fails('state_unresolved_set_unchanged',
           after=_state('after', unresolved_set=list(APPROVED_SET)[:-1]))


# ═══════════════ Authorization package ══════════════════════════════════════


def _package(decision=None):
    decision = decision or _validate()
    decision['_before'] = _state('before')
    decision['_after'] = _state('after')
    return validator.build_authorization(
        decision, repository_sha='abc123', run_id='42',
    )


def test_the_authorization_package_includes_all_99_games():
    package = _package()
    assert len(package['games']) == 99
    assert [g['game_pk'] for g in package['games']] == list(APPROVED_ORDER)


def test_the_authorization_package_order_is_deterministic():
    first = _package()
    second = _package()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert [g['canonical_index'] for g in first['games']] == list(range(99))


def test_the_authorization_package_carries_the_scope_digest():
    package = _package()
    assert package['scope_set_sha256'] == scope.SCOPE_DIGEST
    assert package['canonical_processing_order'] == list(APPROVED_ORDER)
    assert package['unresolved_game_pks_sorted'] == list(APPROVED_SET)
    assert package['completed_game_pks'] == list(COMPLETED)


def test_the_authorization_package_never_approves_a_write():
    package = _package()
    assert package['write_approved'] is False
    assert package['r6_status'] == 'blocked_pending_founder_review'
    assert package['database_writes'] == 'none'
    assert package['authoritative_mode'] == 'unapproved'
    assert package['automated_lane'] == 'off'


def test_the_authorization_package_records_zero_mutations():
    package = _package()
    assert package['mutations_by_target'] == {
        'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
    }
    assert package['complete_mutation_count'] == 0
    assert package['total_appearance_rows'] == 865
    assert package['total_ignored_decimal_differences'] == 291


def test_the_authorization_markdown_lists_every_game():
    package = _package()
    text = validator.authorization_markdown(package)
    for game_pk in APPROVED_ORDER:
        assert str(game_pk) in text
    assert text.count('|') > 99


def test_the_authorization_package_contains_no_credential_shaped_text():
    text = json.dumps(_package())
    for token in ('postgres://', 'postgresql://', 'password=', 'SECRET_KEY',
                  'DATABASE_URL', 'ADMIN_API_TOKEN'):
        assert token not in text


# ═══════════════ R6 command manifest ════════════════════════════════════════


def test_the_r6_manifest_contains_all_99_arguments():
    manifest = validator.build_r6_manifest(_validate())
    arguments = manifest['required_only_game_pk_arguments']
    assert arguments.count('--only-game-pk') == 99
    ids = [int(arguments[i + 1]) for i, a in enumerate(arguments)
           if a == '--only-game-pk']
    assert ids == list(APPROVED_ORDER)


def test_the_r6_manifest_write_approved_is_always_false():
    manifest = validator.build_r6_manifest(_validate())
    assert manifest['write_approved'] is False
    assert manifest['founder_review_required'] is True
    assert manifest['r6_implemented'] is False
    assert manifest['r6_executed'] is False


def test_the_r6_manifest_status_is_always_blocked():
    manifest = validator.build_r6_manifest(_validate())
    assert manifest['r6_status'] == 'blocked_pending_founder_review'


def test_the_r6_manifest_is_not_executable():
    manifest = validator.build_r6_manifest(_validate())
    assert manifest['executable'] is False
    text = json.dumps(manifest)
    for construct in ('#!/', 'bash', 'sh -c', 'subprocess', 'eval('):
        assert construct not in text, construct


def test_the_r6_manifest_carries_the_expected_shape():
    manifest = validator.build_r6_manifest(_validate())
    assert manifest['expected_rows'] == 865
    assert manifest['expected_ignored_decimal_differences'] == 291
    assert manifest['scope_set_sha256'] == scope.SCOPE_DIGEST
    assert manifest['versions']['parity_contract_version'] == '4'
    assert manifest['required_expected_plan_fingerprint'] == 'c' * 64


def test_the_r6_manifest_markdown_lists_every_game():
    manifest = validator.build_r6_manifest(_validate())
    text = validator.r6_manifest_markdown(manifest)
    for game_pk in APPROVED_ORDER:
        assert str(game_pk) in text
    assert 'not an executable' in text


# ═══════════════ Summary ════════════════════════════════════════════════════


def test_the_pass_summary_says_no_database_writes():
    text = validator.pass_markdown(validator.build_summary(_validate()))
    assert 'No database writes were performed.' in text


def test_the_pass_summary_says_completeness_remains_10_99():
    text = validator.pass_markdown(validator.build_summary(_validate()))
    assert 'Completed final games: 10' in text
    assert 'Unresolved final games: 99' in text
    assert (
        'Production completeness remains 10 completed / 99 unresolved.' in text
    )


def test_the_pass_summary_blocks_r6():
    text = validator.pass_markdown(validator.build_summary(_validate()))
    assert 'R6 status: blocked pending founder review' in text
    assert 'Write approved: no' in text


def test_the_pass_summary_cannot_authorize_r6():
    summary = validator.build_summary(_validate())
    assert summary['write_approved'] is False
    assert summary['r6_status'] == 'blocked_pending_founder_review'


def test_the_pass_summary_reports_the_real_totals():
    summary = validator.build_summary(_validate())
    assert summary['rows_unchanged'] == 865
    assert summary['ignored_decimal_differences'] == 291
    assert summary['games_completed'] == 99


def test_the_failed_summary_names_the_invariant_and_blocks_r6():
    with pytest.raises(validator.ValidationFailure) as caught:
        _validate(shadow=_shadow_report(rows_expected=864))
    summary = validator.failed_summary(caught.value)
    assert summary['result'] == validator.RESULT_FAILED
    assert summary['failed_invariant'] == 'shadow_rows_expected'
    assert summary['r6_blocked'] is True
    text = validator.failed_markdown(summary)
    assert 'FOUNDATION 3C R5 — FAILED' in text
    assert 'R6 is blocked pending founder review' in text


def test_the_failed_summary_carries_the_affected_game_and_pitcher():
    report = _shadow_report()
    report['games'][0]['rows'][0]['action'] = 'update'
    with pytest.raises(validator.ValidationFailure) as caught:
        _validate(shadow=report)
    summary = validator.failed_summary(caught.value)
    assert summary['game_pk'] == APPROVED_ORDER[0]
    assert summary['pitcher_mlb_id'] is not None
    assert summary['sanitized'] is True


# ═══════════════ CLI ════════════════════════════════════════════════════════


def _cli(tmp_path, *, shadow=None, before=None, after=None):
    (tmp_path / 'before.json').write_text(
        json.dumps(before if before is not None else _state('before'))
    )
    (tmp_path / 'shadow.json').write_text(
        json.dumps(shadow if shadow is not None else _shadow_report())
    )
    (tmp_path / 'after.json').write_text(
        json.dumps(after if after is not None else _state('after'))
    )
    return validator.main([
        '--before-state', str(tmp_path / 'before.json'),
        '--shadow', str(tmp_path / 'shadow.json'),
        '--after-state', str(tmp_path / 'after.json'),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--authorization-json', str(tmp_path / 'auth.json'),
        '--authorization-markdown', str(tmp_path / 'auth.md'),
        '--manifest-json', str(tmp_path / 'manifest.json'),
        '--manifest-markdown', str(tmp_path / 'manifest.md'),
        '--repository-sha', 'abc123',
        '--run-id', '42',
    ])


def test_the_cli_exits_zero_and_writes_every_artifact(tmp_path):
    assert _cli(tmp_path) == 0
    for name in ('summary.json', 'summary.md', 'auth.json', 'auth.md',
                 'manifest.json', 'manifest.md'):
        assert (tmp_path / name).is_file(), name
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'pass'


def test_the_cli_output_is_deterministic(tmp_path):
    first = tmp_path / 'a'
    second = tmp_path / 'b'
    first.mkdir()
    second.mkdir()
    assert _cli(first) == 0
    assert _cli(second) == 0
    for name in ('summary.json', 'auth.json', 'manifest.json', 'auth.md'):
        assert (first / name).read_text() == (second / name).read_text(), name


def test_a_failed_result_cannot_exit_zero(tmp_path):
    assert _cli(tmp_path, shadow=_shadow_report(rows_expected=864)) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['r6_blocked'] is True


def test_a_failed_result_writes_no_authorization_package(tmp_path):
    assert _cli(tmp_path, shadow=_shadow_report(rows_expected=864)) == 1
    assert not (tmp_path / 'auth.json').exists()
    assert not (tmp_path / 'manifest.json').exists()


def test_a_missing_artifact_fails_closed(tmp_path):
    (tmp_path / 'shadow.json').write_text(json.dumps(_shadow_report()))
    (tmp_path / 'after.json').write_text(json.dumps(_state('after')))
    assert validator.main([
        '--before-state', str(tmp_path / 'absent.json'),
        '--shadow', str(tmp_path / 'shadow.json'),
        '--after-state', str(tmp_path / 'after.json'),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--authorization-json', str(tmp_path / 'auth.json'),
        '--authorization-markdown', str(tmp_path / 'auth.md'),
        '--manifest-json', str(tmp_path / 'manifest.json'),
        '--manifest-markdown', str(tmp_path / 'manifest.md'),
    ]) == 1


# ═══════════════ Real pipeline on PostgreSQL ════════════════════════════════


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


def _schedule_in_canonical_position(game_pk, index):
    """Schedule a final game whose start time fixes its planner ordering.

    The planner sorts by (retry rank, criticality, represented date, game
    start time, game id). Every game in this window shares the first three, so
    the start time is the only lever that reproduces a realistic canonical
    order — with one shared start time the planner would fall through to
    game_pk ascending, which is NOT the order production produced.
    """
    start = datetime(
        REFERENCE.year, REFERENCE.month, REFERENCE.day, 12, 0,
    ) + timedelta(minutes=index)
    for team_id, opponent_id, side in (
        (HOME_TEAM, AWAY_TEAM, 'home'),
        (AWAY_TEAM, HOME_TEAM, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=REFERENCE,
            game_datetime=start, opponent_team_id=opponent_id,
            home_away=side, game_type='R', status_code='F',
            status_state=ScheduledGame.STATE_FINAL,
        ))


def _completed_work_item(game_pk, rows):
    return GameIngestionWorkItem(
        mlb_game_pk=game_pk, represented_date=REFERENCE, game_date=REFERENCE,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        status=GameIngestionWorkItem.STATUS_COMPLETED,
        attempt_count=1, rows_expected=rows, rows_reconciled=rows,
        completed_at=datetime(2026, 7, 29, 23, 0, 0),
        completion_proof={'rows_reconciled': rows},
        source_revision=f'rev-{game_pk}',
    )


def _build_remaining_window(game_pks=APPROVED_ORDER):
    """Production shape: 109 scheduled games, 10 completed, the rest open."""
    boxscores = {}

    # The ten already-completed games: scheduled, stored, checkpointed.
    for game_pk in COMPLETED:
        _schedule(game_pk)
        arm = _pitcher(game_pk * 100, team_id=HOME_TEAM, active=True)
        db.session.flush()
        _stored_row(arm, game_pk)
    db.session.commit()
    for game_pk in COMPLETED:
        db.session.add(_completed_work_item(game_pk, 1))
    db.session.commit()

    # The remaining window under test, scheduled so the planner reproduces the
    # reviewed canonical processing order rather than plain id order.
    canonical_index = {pk: i for i, pk in enumerate(APPROVED_ORDER)}
    for game_pk in game_pks:
        _schedule_in_canonical_position(
            game_pk, canonical_index.get(game_pk, 900 + len(canonical_index)),
        )
        rows = ROWS_BY_GAME[game_pk]
        drifted = IGNORED_BY_GAME[game_pk]
        lines = []
        for index in range(rows):
            mlb_id = game_pk * 100 + index + 1
            arm = _pitcher(
                mlb_id, team_id=AWAY_TEAM if index % 2 else HOME_TEAM,
                active=index % 3 != 0,
            )
            arm.roster_status = STATUS_MINORS if index % 2 else STATUS_ACTIVE
            db.session.flush()
            if index < drifted:
                # Same canonical outs, different decimal representation: the
                # difference R5 must ignore rather than correct.
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


def _run_shadow(game_pks=APPROVED_ORDER):
    return game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        only_game_pks=list(game_pks),
    )


def test_the_real_99_game_shadow_projects_no_mutation(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_remaining_window()),
        )
        from scripts import inspect_r5_remaining_state as inspector

        before = inspector.collect_state()
        assert before['publication_completeness']['completed_final_games'] == 10
        assert before['publication_completeness']['unresolved_final_games'] == 99
        assert before['publication_completeness']['expected_final_games'] == 109
        assert before['selected_work_items'] == {}

        report = _run_shadow()
        db.session.rollback()

        assert report['status'] == 'complete'
        assert report['games_completed'] == 99
        assert report['rows_unchanged'] == 865
        assert report['rows_inserted'] == 0
        assert report['rows_updated'] == 0
        assert report['rows_blocked'] == 0
        assert report['derived_companion_differences_ignored'] == 291
        assert report['complete_mutation_count'] == 0
        assert report['pitcher_identity_mutations'] == 0
        assert report['appearance_team_mutations'] == 0
        assert report['canonical_outs_corrections'] == 0
        assert report['parity_contract_version'] == '4'
        assert len(report['complete_reconciliation_fingerprint']) == 64

        after = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['all_work_item_count'] == before['all_work_item_count']
        assert after['selected_work_items'] == {}
        assert (
            after['publication_completeness']
            == before['publication_completeness']
        )

        decision = validator.validate_r5(
            before_state={**before, 'phase': 'before',
                          'read_only': {'write_probe_refused': True}},
            shadow=report,
            after_state={**after, 'phase': 'after',
                         'read_only': {'write_probe_refused': True}},
        )
        assert decision['result'] == validator.RESULT_PASS
        assert decision['shadow']['total_rows'] == 865
        assert decision['shadow']['total_ignored'] == 291


def test_the_real_shadow_creates_no_work_item(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_remaining_window()),
        )
        before = GameIngestionWorkItem.query.count()
        _run_shadow()
        db.session.rollback()
        assert GameIngestionWorkItem.query.count() == before == 10
        assert GameIngestionWorkItem.query.filter(
            GameIngestionWorkItem.mlb_game_pk.in_(list(APPROVED_ORDER))
        ).count() == 0


def test_a_selected_game_that_is_already_completed_stops_before_the_shadow(
    app, monkeypatch,
):
    """Scenario A: the before-state fails and the shadow must not run."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_remaining_window()),
        )
        from scripts import inspect_r5_remaining_state as inspector

        intruder = APPROVED_ORDER[0]
        db.session.add(_completed_work_item(intruder, ROWS_BY_GAME[intruder]))
        db.session.commit()

        before = inspector.collect_state()
        assert str(intruder) in before['selected_work_items']
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_before_state(
                {**before, 'phase': 'before',
                 'read_only': {'write_probe_refused': True}}
            )
        assert 'have_no_work_item' in caught.value.invariant


def test_an_omitted_game_fails_exact_scope(app, monkeypatch):
    """Scenario B: 98 games planned where 99 were approved."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_remaining_window()),
        )
        report = _run_shadow(APPROVED_ORDER[:-1])
        db.session.rollback()
        assert report['requested_game_count'] == 98
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_shadow_report(report)
        assert 'requested_game_count' in caught.value.invariant


def test_an_unapproved_game_fails_exact_scope(app, monkeypatch):
    """Scenario C: a game outside the reviewed 99 enters the run."""
    with app.app_context():
        intruder = 909090
        boxscores = _build_remaining_window()
        _schedule(intruder)
        arm = _pitcher(intruder * 10, team_id=HOME_TEAM, active=True)
        db.session.flush()
        _stored_row(arm, intruder)
        db.session.commit()
        boxscores[intruder] = boxscore([(intruder * 10, 'home', pitching_stats())])
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        report = _run_shadow(list(APPROVED_ORDER) + [intruder])
        db.session.rollback()
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_shadow_report(report)
        assert 'game_count' in caught.value.invariant


def test_an_identity_creation_is_detected_and_moves_the_fingerprint(
    app, monkeypatch,
):
    """Scenario D: a missing Pitcher forces a creation. R5 must fail.

    The clean baseline and the mutated run are both executed against a patched
    client — an unpatched run would reach the real MLB client and hang.
    """
    with app.app_context():
        boxscores = _build_remaining_window()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        clean = _run_shadow()
        db.session.rollback()
        clean_fingerprint = clean['complete_reconciliation_fingerprint']
        assert clean['pitcher_identity_creations'] == 0

        # Add a pitching line for an arm that has no local Pitcher row. The
        # planner must plan a minimal identity creation for it.
        target = APPROVED_ORDER[0]
        unknown = 7777777
        lines = [
            (target * 100 + index + 1, 'home', pitching_stats())
            for index in range(ROWS_BY_GAME[target])
        ]
        lines.append((unknown, 'home', pitching_stats()))
        boxscores[target] = boxscore(lines)
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        report = _run_shadow()
        db.session.rollback()

        assert report['pitcher_identity_creations'] >= 1
        assert report['complete_mutation_count'] >= 1
        assert (
            report['complete_reconciliation_fingerprint'] != clean_fingerprint
        )
        with pytest.raises(validator.ValidationFailure):
            validator.validate_shadow_report(report)


def test_a_canonical_outs_correction_fails_r5(app, monkeypatch):
    """Scenario E: a genuine semantic innings difference must fail."""
    with app.app_context():
        boxscores = _build_remaining_window()
        target = APPROVED_ORDER[0]
        # Rewrite one stored row so its canonical outs genuinely disagree with
        # the official line — a correction, not a representation difference.
        row = (
            GameLog.query
            .filter(GameLog.mlb_game_pk == target)
            .order_by(GameLog.pitcher_id)
            .all()[-1]
        )
        row.innings_pitched_outs = 1
        row.innings_pitched = 0.1
        db.session.commit()

        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        report = _run_shadow()
        db.session.rollback()

        assert report['rows_updated'] >= 1
        with pytest.raises(validator.ValidationFailure):
            validator.validate_shadow_report(report)


def test_a_write_during_the_shadow_is_caught_by_the_state_hashes(
    app, monkeypatch,
):
    """Scenario F: drift between the snapshots is detected, not explained away."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_remaining_window()),
        )
        from scripts import inspect_r5_remaining_state as inspector

        before = inspector.collect_state()
        _run_shadow()
        db.session.rollback()

        # Simulate an unrelated write landing during the run.
        target = APPROVED_ORDER[0]
        row = GameLog.query.filter(GameLog.mlb_game_pk == target).first()
        row.earned_runs = (row.earned_runs or 0) + 1
        db.session.commit()

        after = inspector.collect_state()
        assert after['game_log_content_hash'] != before['game_log_content_hash']
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_state_transition(
                {**before, 'phase': 'before'},
                {**after, 'phase': 'after',
                 'read_only': {'write_probe_refused': True}},
            )
        assert 'game_log_content_hash_unchanged' in caught.value.invariant
