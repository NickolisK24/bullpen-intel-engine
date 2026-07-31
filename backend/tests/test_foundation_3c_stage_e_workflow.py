"""Foundation 3C — the Stage E1 bootstrap closeout and rollout retirement.

Stage E is the last independent verification of the completed 109-game
bootstrap. It authorizes nothing, writes nothing, and exists to prove that
production is where R6 left it and that replaying the whole bootstrap changes
nothing.

Three groups of guards carry the weight:

  RETIREMENT — the six R1–R6 workflows are gone, and no renamed, disabled, or
  archived copy survives under `.github/workflows`.

  PERMANENT BOUNDARY — the cleanup did not take production runtime, permanent
  regression coverage, or the unresolved forensic inspector with it.

  ACCURACY — the summary never claims the system has no dead letters. The
  governed bootstrap count is zero; the global count was already 1,389 at R6
  closeout and belongs to unrelated work.

TEMPORARY. This file is classified `retain_until_stage_e2`. Before E2 deletes
it, the permanent-runtime presence assertions below must move to a permanent
suite rather than disappearing with it.

The YAML parser is imported inside a fixture rather than via
`pytest.importorskip`, so a missing parser makes these tests ERROR loudly
instead of silently skipping the guards they exist to enforce.
"""

import json
import os
import subprocess
import tempfile
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
from models.sync_failure import SyncFailure
from scripts import build_stage_e_cleanup_manifest as manifest_builder
from scripts import stage_e_bootstrap_scope as scope
from scripts import validate_stage_e_bootstrap_closeout as validator
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
)
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / '.github' / 'workflows'
WORKFLOW_PATH = WORKFLOWS / 'foundation-3c-stage-e-bootstrap-closeout.yml'

CANONICAL_ORDER = scope.CANONICAL_ORDER
GOVERNED_SET = scope.SORTED_SET
TOTAL_ROWS = scope.EXPECTED_TOTAL_ROWS          # 946
TOTAL_IGNORED = scope.EXPECTED_TOTAL_IGNORED    # 323
FULL_SCOPE_DIGEST = scope.FULL_SCOPE_DIGEST
R6_GLOBAL_DEAD_LETTERS = scope.R6_GLOBAL_DEAD_LETTER_COUNT   # 1389

RETIRED_WORKFLOWS = (
    'foundation-3c-r1-shadow-validation.yml',
    'foundation-3c-r2-full-window-shadow.yml',
    'foundation-3c-r3-controlled-sample-shadow.yml',
    'foundation-3c-r4-controlled-write.yml',
    'foundation-3c-r5-remaining-window-shadow.yml',
    'foundation-3c-r6-full-remaining-window-write.yml',
)

PERMANENT_RUNTIME_FILES = (
    'backend/scripts/game_driven_ingestion.py',
    'backend/services/game_driven_ingestion.py',
    'backend/services/game_ingestion_planner.py',
    'backend/services/game_ingestion_completeness.py',
    'backend/services/game_log_reconciliation.py',
    'backend/services/pitcher_identity_reconciliation.py',
    'backend/models/game_ingestion_work_item.py',
)

PERMANENT_REGRESSION_FILES = (
    'backend/tests/test_game_driven_ingestion.py',
    'backend/tests/test_exclusive_game_scope.py',
    'backend/tests/test_pitcher_identity_authority.py',
    'backend/tests/test_canonical_innings_reconciliation.py',
    'backend/tests/test_shadow_write_reconciliation_parity.py',
    'backend/tests/test_game_ingestion_completeness.py',
)

FORENSIC_FILE = 'backend/scripts/inspect_first_write_pitcher_identity.py'


# 74 games of 9 rows + 35 of 8 == 946. 105 of 3 ignored + 4 of 2 == 323.
ROWS_BY_GAME = {
    pk: (9 if i < 74 else 8) for i, pk in enumerate(CANONICAL_ORDER)
}
IGNORED_BY_GAME = {
    pk: (3 if i < 105 else 2) for i, pk in enumerate(CANONICAL_ORDER)
}


def test_the_fixture_shape_matches_the_bootstrap_totals():
    assert sum(ROWS_BY_GAME.values()) == TOTAL_ROWS == 946
    assert sum(IGNORED_BY_GAME.values()) == TOTAL_IGNORED == 323
    assert all(IGNORED_BY_GAME[pk] <= ROWS_BY_GAME[pk] for pk in CANONICAL_ORDER)


# ═══════════════ Workflow retirement ════════════════════════════════════════


@pytest.mark.parametrize('name', RETIRED_WORKFLOWS)
def test_a_retired_rollout_workflow_is_absent(name):
    assert not (WORKFLOWS / name).exists(), name


def test_no_renamed_or_disabled_rollout_copy_survives():
    """A disabled copy is still a file someone can re-enable."""
    survivors = sorted(
        path.name for path in WORKFLOWS.iterdir()
        if path.is_file()
        and 'foundation-3c' in path.name.lower()
        and path.name != WORKFLOW_PATH.name
    )
    assert survivors == [], survivors


def test_no_archived_rollout_yaml_hides_under_the_workflows_directory():
    stray = sorted(
        str(path.relative_to(WORKFLOWS))
        for path in WORKFLOWS.rglob('*')
        if path.is_file()
        and path.suffix in {'.yml', '.yaml', '.disabled', '.bak'}
        and any(
            token in path.name.lower()
            for token in ('r1-', 'r2-', 'r3-', 'r4-', 'r5-', 'r6-')
        )
        and 'foundation-3c' in path.name.lower()
    )
    assert stray == [], stray


def test_stage_e_is_the_only_remaining_foundation_3c_workflow():
    foundation = sorted(
        path.name for path in WORKFLOWS.glob('foundation-3c-*.yml')
    )
    assert foundation == [WORKFLOW_PATH.name]


def test_the_retired_validators_and_inspectors_are_absent():
    scripts = REPO_ROOT / 'backend' / 'scripts'
    for name in (
        'validate_r1_shadow_report.py', 'validate_r2_shadow_report.py',
        'validate_r3_shadow_report.py', 'validate_r4_controlled_write.py',
        'validate_r5_remaining_shadow.py', 'validate_r6_full_write.py',
        'inspect_r4_controlled_state.py', 'inspect_r5_remaining_state.py',
        'inspect_r6_full_write_state.py',
    ):
        assert not (scripts / name).exists(), name


def test_the_retired_workflow_test_files_are_absent():
    tests = REPO_ROOT / 'backend' / 'tests'
    for stage in ('r1', 'r2', 'r3', 'r4', 'r5', 'r6'):
        assert not (
            tests / f'test_foundation_3c_{stage}_workflow.py'
        ).exists(), stage


# ═══════════════ Permanent boundary ═════════════════════════════════════════


@pytest.mark.parametrize('path', PERMANENT_RUNTIME_FILES)
def test_permanent_runtime_survives_the_cleanup(path):
    """Bootstrap completion is not a reason to delete production behaviour."""
    assert (REPO_ROOT / path).exists(), path


@pytest.mark.parametrize('path', PERMANENT_REGRESSION_FILES)
def test_permanent_regression_coverage_survives_the_cleanup(path):
    assert (REPO_ROOT / path).exists(), path


def test_the_unresolved_forensic_inspector_survives():
    """The first-write provenance question is still open."""
    assert (REPO_ROOT / FORENSIC_FILE).exists()


def test_the_permanent_runtime_modules_still_import_and_expose_their_contract():
    """Presence is not enough — the authority constants must still be there."""
    assert reconciliation.RECONCILIATION_PLAN_VERSION == '3'
    assert reconciliation.PARITY_CONTRACT_VERSION == '4'
    assert reconciliation.INNINGS_SEMANTICS_VERSION == '2'
    assert reconciliation.COMPLETE_PLAN_VERSION == '1'
    assert identity.IDENTITY_PLAN_VERSION == '1'
    assert callable(reconciliation.plan_fingerprint)
    assert callable(identity.fingerprint_component)
    assert callable(game_driven_ingestion.run_game_driven_ingestion)
    assert game_driven_ingestion.MODE_SHADOW == 'shadow'
    assert game_driven_ingestion.MODE_WRITE == 'write'


def test_the_extracted_per_game_boundary_coverage_landed_permanently():
    """The R4/R6 transaction-boundary proof survives its source files."""
    body = (
        REPO_ROOT / 'backend' / 'tests' / 'test_game_driven_ingestion.py'
    ).read_text(encoding='utf-8')
    for name in (
        'test_a_failure_partway_leaves_earlier_games_durably_committed',
        'test_a_partial_run_never_reports_itself_as_complete',
        'test_a_completed_game_replays_without_mutating_baseball_data',
    ):
        assert name in body, name


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
def executable_text(workflow_text):
    """The workflow with comment lines removed.

    The header documents what this workflow must never do, which is worth
    keeping — but a flag inside a comment is not passed to anything, so the
    prohibition guards are asserted against executable content.
    """
    return '\n'.join(
        line for line in workflow_text.splitlines()
        if not line.strip().startswith('#')
    )


@pytest.fixture(scope='module')
def run_commands(job):
    lines = []
    for step in job['steps']:
        for line in (step.get('run') or '').splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                lines.append(stripped)
    return lines


# ═══════════════ Structural contract ════════════════════════════════════════


def test_the_workflow_name_is_the_agreed_one(workflow):
    assert workflow['name'] == 'Foundation 3C Stage E Bootstrap Closeout'


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
    for value in workflow['permissions'].values():
        assert value == 'read'


def test_the_timeout_is_finite(job):
    assert isinstance(job['timeout-minutes'], int)
    assert 0 < job['timeout-minutes'] <= 60


def test_concurrency_joins_the_production_group_without_cancelling(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'
    assert workflow['concurrency']['cancel-in-progress'] is False


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


# ═══════════════ Command construction ═══════════════════════════════════════


def test_exactly_one_ingestion_invocation_exists(run_commands):
    invocations = [
        line for line in run_commands if 'game_driven_ingestion.py' in line
    ]
    assert len(invocations) == 1


def test_the_only_mode_is_shadow(executable_text):
    assert executable_text.count('--mode shadow') == 1
    assert '--mode write' not in executable_text
    assert '--mode authoritative' not in executable_text


def test_no_forbidden_option_appears_in_executable_content(executable_text):
    for option in (
        '--game-pk ', '--max-games', '--time-budget-seconds',
        '--include-backfill', '--plan-only', '--expected-plan-fingerprint',
    ):
        assert option not in executable_text, option


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


def test_the_scope_is_pinned_and_digest_gated(workflow_text):
    assert 'stage_e_bootstrap_scope.py' in workflow_text
    assert '--expected-digest' in workflow_text
    assert FULL_SCOPE_DIGEST in workflow_text


def test_the_scope_cannot_come_from_an_input_or_the_database(executable_text):
    assert 'inputs' not in executable_text
    assert 'github.event.inputs' not in executable_text
    assert 'psql' not in executable_text


def test_the_ingestion_command_consumes_the_pinned_scope_file(job):
    step = next(
        s for s in job['steps']
        if 'game_driven_ingestion.py' in (s.get('run') or '')
    )
    assert 'mapfile -t scope_args < "$SCOPE_ARGS_PATH"' in step['run']
    assert '"${scope_args[@]}"' in step['run']


# ── The scope emitter, executed for real ───────────────────────────────────


def test_the_scope_emitter_produces_exactly_109_ordered_games(tmp_path):
    target = tmp_path / 'args.txt'
    facts = scope.emit_arguments(target)
    tokens = [line for line in target.read_text().splitlines() if line.strip()]
    assert tokens.count('--only-game-pk') == 109
    ids = [
        int(tokens[i + 1]) for i, token in enumerate(tokens)
        if token == '--only-game-pk'
    ]
    assert ids == list(CANONICAL_ORDER)
    assert len(set(ids)) == 109
    assert facts['full_scope_digest'] == FULL_SCOPE_DIGEST


def test_the_scope_emitter_refuses_a_wrong_digest(tmp_path):
    assert scope._main([
        '--emit-arguments', str(tmp_path / 'args.txt'),
        '--expected-digest', '0' * 64,
    ]) == 1


def test_the_scope_emitter_accepts_the_approved_digest(tmp_path):
    assert scope._main([
        '--emit-arguments', str(tmp_path / 'args.txt'),
        '--expected-digest', FULL_SCOPE_DIGEST,
    ]) == 0


def test_the_full_scope_is_the_union_of_the_reviewed_sets():
    assert len(CANONICAL_ORDER) == 109
    assert len(set(CANONICAL_ORDER)) == 109
    assert set(CANONICAL_ORDER) == (
        set(scope.COMPLETED_BEFORE_R6) | set(scope.REMAINING_GAME_PKS)
    )
    assert len(scope.COMPLETED_BEFORE_R6) == 10
    assert len(scope.REMAINING_GAME_PKS) == 99


def test_the_full_scope_digest_differs_from_the_r6_ninety_nine_digest():
    """Different populations must not share an identity."""
    assert FULL_SCOPE_DIGEST != scope.R6_SCOPE_DIGEST


# ═══════════════ Step order ═════════════════════════════════════════════════


def _step_index(job, prefix):
    for index, step in enumerate(job['steps']):
        if (step.get('name') or '').startswith(prefix):
            return index
    raise AssertionError(prefix)


def test_the_scope_is_built_before_any_database_step(job):
    assert _step_index(job, 'Build and validate the pinned') < _step_index(
        job, 'Capture the before state'
    )


def test_the_before_state_precedes_the_replay(job):
    assert _step_index(job, 'Capture the before state') < _step_index(
        job, 'Run the exact 109-game'
    )


def test_the_after_state_runs_under_always(job):
    step = job['steps'][_step_index(job, 'Capture the after state')]
    assert 'always()' in step['if']


def test_validation_follows_the_after_state(job):
    assert _step_index(job, 'Capture the after state') < _step_index(
        job, 'Validate the complete Stage E'
    )


def test_the_credential_scan_precedes_upload(job):
    assert _step_index(job, 'Scan artifacts') < _step_index(
        job, 'Upload the Stage E artifacts'
    )


def test_the_upload_runs_under_always_with_ninety_day_retention(job):
    step = job['steps'][_step_index(job, 'Upload the Stage E artifacts')]
    assert 'always()' in step['if']
    assert step['with']['retention-days'] == 90
    assert step['with']['if-no-files-found'] == 'warn'
    assert step['with']['name'] == 'foundation-3c-stage-e-bootstrap-closeout'


def test_the_final_gate_follows_upload(job):
    assert _step_index(job, 'Upload the Stage E artifacts') < _step_index(
        job, 'Fail the job unless'
    )


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
    'postgresql://user:pw@host/db', 'postgres://user:pw@host/db',
    'password=hunter2', 'Authorization: Bearer abc', 'X-Admin-Token: abc',
    'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
    'BASEBALLOS_ADMIN_API_TOKEN', 'token=abc', 'api_key=abc', 'api-key=abc',
    'secret=abc',
])
def test_the_scanner_rejects_credential_shaped_content(
    scanner_script, tmp_path, poison,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'stage-e-closeout.json').write_text(json.dumps({'n': poison}))
    (tmp_path / 'scan.py').write_text(scanner_script)
    result = subprocess.run(
        ['python', 'scan.py'], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 1
    assert poison not in result.stdout
    assert not (artifacts / 'stage-e-closeout.json').exists()


def test_the_scanner_passes_a_clean_artifact(scanner_script, tmp_path):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'stage-e-closeout.json').write_text(
        json.dumps({'result': 'pass', 'rows_unchanged': 946})
    )
    (tmp_path / 'scan.py').write_text(scanner_script)
    result = subprocess.run(
        ['python', 'scan.py'], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0


# ═══════════════ Synthetic reports ══════════════════════════════════════════


def _row(game_pk, index, *, ignored=False, **overrides):
    row = {
        'game_pk': game_pk,
        'pitcher_mlb_id': game_pk * 100 + index,
        'action': reconciliation.ACTION_UNCHANGED,
        'changed_fields': [], 'semantic_changed_fields': [],
        'applied_changed_fields': [], 'derived_companion_fields': [],
        'changed_field_count': 0,
        'derived_companion_differences_ignored': (
            ['innings_pitched'] if ignored else []
        ),
        'governed_and_safe': True, 'blocked_reason': None,
        'affects_published_evidence': False,
        'is_statistical_correction': False, 'is_provenance_only': False,
        'mutation_digest': '',
        'appearance_team_reason': None, 'appearance_team_decision': None,
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
        'attempt_number': 2,
        'status': 'projected',
        'error_class': None,
        'source_revision': f'rev-{game_pk}',
        'appearances_extracted': rows,
        'inserted': 0, 'updated': 0, 'unchanged': rows, 'blocked': 0,
        'complete_mutation_count': 0,
        'pitcher_identity_mutations': 0, 'appearance_team_mutations': 0,
        'canonical_outs_corrections': 0, 'statistical_corrections': 0,
        'derived_companion_differences_ignored': ignored,
        'complete_reconciliation_fingerprint': f'{index:064x}',
        'rows': [
            _row(game_pk, position, ignored=position < ignored)
            for position in range(rows)
        ],
    }


def _replay(**overrides):
    report = {
        'status': 'complete', 'mode': 'shadow',
        'reference_date': '2026-07-29', 'execution_scope_mode': 'exclusive',
        'reconciliation_plan_version':
            reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        'requested_game_count': 109, 'planned_game_count': 109,
        'duplicate_requested_count': 0, 'execution_scope_exact_match': True,
        'requested_game_pks': list(GOVERNED_SET),
        'planned_game_pks': list(GOVERNED_SET),
        'unexpected_planned_game_pks': [], 'missing_requested_game_pks': [],
        'games_attempted': 109, 'games_fetched': 109, 'games_completed': 109,
        'games_failed': 0, 'games_remaining': 0,
        'budget_stop_triggered': False, 'budget_stop': None,
        'finality_conflicts': 0, 'schedule_authority_missing': 0,
        'failure_classes': {}, 'critical_games_unresolved': 0,
        'best_effort_games_deferred': 0,
        'rows_expected': TOTAL_ROWS, 'rows_inserted': 0, 'rows_updated': 0,
        'rows_unchanged': TOTAL_ROWS, 'rows_blocked': 0,
        'changed_fields_counts': {},
        'pitcher_identity_changed_fields_counts': {},
        'pitcher_identity_rows_examined': TOTAL_ROWS,
        'pitcher_identity_mutations': 0, 'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0, 'pitcher_identity_blocked': 0,
        'appearance_team_mutations': 0, 'complete_mutation_count': 0,
        'canonical_outs_corrections': 0, 'statistical_corrections': 0,
        'authority_reconciliations': 0, 'provenance_only_updates': 0,
        'corrections_applied': 0, 'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': TOTAL_IGNORED,
        'decimal_only_updates_suppressed': TOTAL_IGNORED,
        'complete_reconciliation_fingerprint': 'f' * 64,
        'games': [_game(pk, i) for i, pk in enumerate(CANONICAL_ORDER)],
    }
    report.update(overrides)
    return report


def _state(phase, **overrides):
    work_items = {
        str(pk): {
            'status': GameIngestionWorkItem.STATUS_COMPLETED,
            'attempt_count': 1, 'criticality':
                GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            'error_class': None, 'rows_expected': ROWS_BY_GAME[pk],
            'rows_reconciled': ROWS_BY_GAME[pk], 'completed': True,
        } for pk in GOVERNED_SET
    }
    state = {
        'phase': phase, 'reference_date': '2026-07-29',
        'read_only': {'write_probe_refused': True},
        'read_only_after': {'write_probe_refused': True},
        'governed_game_pks': list(GOVERNED_SET), 'governed_game_count': 109,
        'full_scope_digest': FULL_SCOPE_DIGEST,
        'game_log_row_count': TOTAL_ROWS,
        'game_log_content_hash': 'a' * 64, 'canonical_outs_hash': 'b' * 64,
        'correction_provenance_hash': 'c' * 64,
        'appearance_team_hash': 'd' * 64, 'pitcher_state_hash': 'e' * 64,
        'pitcher_count': 450, 'pitcher_mlb_ids': [1, 2, 3],
        'governed_work_items': work_items,
        'governed_work_item_count': 109,
        'governed_work_items_hash': '7' * 64,
        'governed_completed_set': list(GOVERNED_SET),
        'governed_unresolved_set': [], 'governed_terminal_set': [],
        'duplicate_governed_game_pks': [],
        'completed_work_item_set': list(GOVERNED_SET),
        'terminal_work_item_set': [], 'unresolved_set': [],
        'governed_dead_letter_count': 0,
        'global_dead_letter_count': R6_GLOBAL_DEAD_LETTERS,
        'r6_global_dead_letter_count': R6_GLOBAL_DEAD_LETTERS,
        'global_dead_letter_delta': 0,
        'version_constants': {
            'reconciliation_plan_version': '3',
            'parity_contract_version': '4',
            'innings_semantics_version': '2',
            'complete_plan_version': '1',
            'identity_plan_version': '1',
        },
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'publication_completeness': {
            'expected_final_games': 109, 'completed_final_games': 109,
            'unresolved_final_games': 0, 'terminal_failure_games': 0,
            'correction_pending_games': 0,
            'critical_appearance_rows_expected': 946,
            'critical_appearance_rows_reconciled': 946,
            'publication_complete': True,
        },
    }
    state.update(overrides)
    return state


def _closeout(**kwargs):
    args = {
        'before_state': _state('before'),
        'replay': _replay(),
        'after_state': _state('after'),
    }
    args.update(kwargs)
    return validator.validate_closeout(**args)


def _fails(fragment, **kwargs):
    with pytest.raises(validator.ValidationFailure) as caught:
        _closeout(**kwargs)
    assert fragment in caught.value.invariant, caught.value.invariant
    return caught.value


# ═══════════════ Happy path ═════════════════════════════════════════════════


def test_the_exact_109_0_production_state_passes():
    decision = _closeout()
    assert decision['result'] == validator.RESULT_PASS
    assert decision['replay']['total_rows'] == 946
    assert decision['replay']['total_ignored'] == 323
    assert decision['drift']['database_drift'] == 'none'
    assert decision['before_state']['completed_final_games'] == 109
    assert decision['before_state']['unresolved_final_games'] == 0


# ═══════════════ Bootstrap state failures ═══════════════════════════════════


@pytest.mark.parametrize('field,value', [
    ('expected_final_games', 108),
    ('completed_final_games', 108),
    ('unresolved_final_games', 1),
    ('terminal_failure_games', 1),
    ('correction_pending_games', 1),
    ('critical_appearance_rows_reconciled', 945),
    ('publication_complete', False),
])
def test_a_wrong_completeness_value_fails(field, value):
    state = _state('before')
    state['publication_completeness'][field] = value
    _fails(f'completeness_{field}', before_state=state)


def test_a_completed_set_mismatch_fails():
    _fails('governed_completed_set',
           before_state=_state('before',
                               governed_completed_set=list(GOVERNED_SET)[:-1]))


def test_a_nonempty_unresolved_set_fails():
    _fails('unresolved_set',
           before_state=_state('before', unresolved_set=[CANONICAL_ORDER[0]]))


def test_a_work_item_count_other_than_109_fails():
    _fails('governed_work_item_count',
           before_state=_state('before', governed_work_item_count=108))


def test_an_unresolved_work_item_fails():
    _fails('governed_unresolved_set',
           before_state=_state('before',
                               governed_unresolved_set=[CANONICAL_ORDER[0]]))


def test_a_terminal_work_item_fails():
    _fails('governed_terminal_set',
           before_state=_state('before',
                               governed_terminal_set=[CANONICAL_ORDER[0]]))


def test_a_duplicate_work_item_fails():
    _fails('duplicate_governed_game_pks',
           before_state=_state('before',
                               duplicate_governed_game_pks=[CANONICAL_ORDER[0]]))


def test_a_governed_game_dead_letter_fails():
    _fails('governed_dead_letter_count',
           before_state=_state('before', governed_dead_letter_count=1))


def test_a_lane_that_is_not_off_fails():
    _fails('automated_lane', before_state=_state('before',
                                                 automated_lane='shadow'))


def test_a_state_that_was_not_read_only_fails():
    _fails('state_read_only',
           before_state=_state('before',
                               read_only={'write_probe_refused': False}))


def test_a_wrong_scope_digest_fails():
    _fails('full_scope_digest',
           before_state=_state('before', full_scope_digest='0' * 64))


# ── Dead-letter accounting ─────────────────────────────────────────────────


def test_the_unchanged_global_dead_letter_count_passes():
    decision = _closeout()
    advisory = decision['dead_letters']
    assert advisory['r6_closeout_global_dead_letters'] == 1389
    assert advisory['current_global_dead_letters'] == 1389
    assert advisory['delta'] == 0
    assert advisory['governed_bootstrap_dead_letters'] == 0


def test_a_changed_global_dead_letter_count_is_advisory_not_a_failure():
    """Unrelated global movement must not fail a governed verification."""
    after = _state('after', global_dead_letter_count=1402)
    decision = _closeout(after_state=after)
    assert decision['result'] == validator.RESULT_PASS
    advisory = decision['dead_letters']
    assert advisory['current_global_dead_letters'] == 1402
    assert advisory['delta'] == 13
    assert advisory['governed_bootstrap_dead_letters'] == 0
    assert advisory['foundation_3c_created_new_dead_letters'] is False
    assert 'unrelated work' in advisory['advisory']


def test_a_governed_dead_letter_fails_even_when_the_global_count_is_stable():
    _fails('governed_dead_letter_count',
           after_state=_state('after', governed_dead_letter_count=1))


# ═══════════════ Replay failures ════════════════════════════════════════════


@pytest.mark.parametrize('count', [108, 110])
def test_a_wrong_requested_game_count_fails(count):
    _fails('requested_game_count', replay=_replay(requested_game_count=count))


def test_a_missing_game_fails():
    report = _replay()
    report['requested_game_pks'] = list(GOVERNED_SET)[:-1]
    _fails('requested_game_pks', replay=report)


def test_an_extra_game_fails():
    report = _replay()
    report['requested_game_pks'] = list(GOVERNED_SET) + [999999]
    _fails('requested_game_pks', replay=report)


def test_a_duplicate_game_fails():
    _fails('duplicate_requested_count', replay=_replay(duplicate_requested_count=1))


def test_a_wrong_processing_order_fails():
    report = _replay()
    report['games'][0], report['games'][1] = (
        report['games'][1], report['games'][0]
    )
    _fails('canonical_processing_order', replay=report)


@pytest.mark.parametrize('field,value', [
    ('rows_expected', 945), ('rows_expected', 947),
    ('rows_inserted', 1), ('rows_updated', 1), ('rows_blocked', 1),
    ('pitcher_identity_mutations', 1), ('pitcher_identity_creations', 1),
    ('pitcher_identity_reactivations', 1),
    ('pitcher_identity_metadata_updates', 1), ('pitcher_identity_blocked', 1),
    ('appearance_team_mutations', 1), ('complete_mutation_count', 1),
    ('canonical_outs_corrections', 1), ('statistical_corrections', 1),
    ('provenance_only_updates', 1), ('authority_reconciliations', 1),
    ('derived_companion_differences_ignored', 322),
    ('derived_companion_differences_ignored', 324),
])
def test_a_replay_counter_violation_fails(field, value):
    _fails(field, replay=_replay(**{field: value}))


def test_a_duplicate_appearance_identity_fails():
    report = _replay()
    rows = report['games'][0]['rows']
    rows[1]['pitcher_mlb_id'] = rows[0]['pitcher_mlb_id']
    _fails('duplicate_appearance_identity', replay=report)


def test_a_short_row_list_fails():
    report = _replay()
    report['games'][0]['rows'] = report['games'][0]['rows'][:-1]
    _fails('appearances_match_rows', replay=report)


def test_a_semantic_innings_correction_fails():
    report = _replay()
    report['games'][0]['rows'][0]['semantic_changed_fields'] = [
        'innings_pitched'
    ]
    _fails('semantic_changed_fields', replay=report)


def test_a_gamelog_mutation_on_a_row_fails():
    report = _replay()
    report['games'][0]['rows'][0]['action'] = 'update'
    _fails('_action', replay=report)


def test_an_identity_mutation_on_a_row_fails():
    report = _replay()
    report['games'][0]['rows'][0]['pitcher_identity_action'] = (
        identity.ACTION_CREATE_MINIMAL_IDENTITY
    )
    _fails('pitcher_identity_action', replay=report)


def test_an_appearance_team_mutation_on_a_row_fails():
    report = _replay()
    report['games'][0]['rows'][0]['appearance_team_decision'] = {
        'reason': 'backfill', 'fields': {},
    }
    _fails('appearance_team_decision', replay=report)


def test_a_wrong_parity_contract_fails():
    _fails('parity_contract_version', replay=_replay(parity_contract_version='3'))


def test_a_missing_full_bootstrap_fingerprint_fails():
    _fails('complete_reconciliation_fingerprint',
           replay=_replay(complete_reconciliation_fingerprint=None))


def test_an_invalid_full_bootstrap_fingerprint_fails():
    _fails('complete_reconciliation_fingerprint',
           replay=_replay(complete_reconciliation_fingerprint='f' * 63))


def test_a_missing_per_game_fingerprint_fails():
    report = _replay()
    report['games'][4]['complete_reconciliation_fingerprint'] = None
    _fails('complete_reconciliation_fingerprint', replay=report)


def test_suppressed_historical_differences_are_recorded_not_pinned():
    report = _replay()
    row = report['games'][0]['rows'][0]
    row['pitcher_identity_suppressed_fields'] = ['team_id', 'roster_status']
    row['pitcher_identity_current_authority_mutation_refused'] = True
    decision = _closeout(replay=report)
    assert decision['result'] == validator.RESULT_PASS
    assert decision['replay']['suppressed_rows'] == 1
    assert decision['replay']['suppressed_field_counts'] == {
        'roster_status': 1, 'team_id': 1,
    }


def test_an_unknown_suppressed_field_fails():
    report = _replay()
    row = report['games'][0]['rows'][0]
    row['pitcher_identity_suppressed_fields'] = ['earned_runs']
    row['pitcher_identity_current_authority_mutation_refused'] = True
    _fails('suppressed_field_is_approved', replay=report)


# ═══════════════ Drift ══════════════════════════════════════════════════════


@pytest.mark.parametrize('field', list(validator.IMMUTABLE_STATE_HASHES))
def test_a_baseball_data_hash_drift_fails(field):
    _fails(f'stage_e_{field}_unchanged',
           after_state=_state('after', **{field: '0' * 64}))


def test_a_work_item_hash_drift_fails():
    _fails('stage_e_governed_work_items_hash_unchanged',
           after_state=_state('after', governed_work_items_hash='0' * 64))


def test_a_work_item_count_drift_fails():
    """Caught by the after-state contract before the drift comparison."""
    _fails('governed_work_item_count',
           after_state=_state('after', governed_work_item_count=110))


def test_a_completeness_drift_fails():
    after = _state('after')
    after['publication_completeness']['critical_appearance_rows_expected'] = 900
    _fails('publication_completeness_unchanged', after_state=after)


def test_a_pitcher_identity_set_drift_fails():
    _fails('stage_e_pitcher_mlb_ids_unchanged',
           after_state=_state('after', pitcher_mlb_ids=[1, 2, 3, 4]))


# ═══════════════ Closeout package and summary ═══════════════════════════════


def _package(decision=None):
    decision = decision or _closeout()
    return validator.build_closeout(
        decision, repository_sha='abc123', run_id='42',
        before=_state('before'), after=_state('after'),
    )


def test_the_closeout_never_approves_a_write():
    package = _package()
    assert package['write_approved'] is False
    assert package['future_write_authorized'] is False
    assert package['database_writes'] == 'none'
    assert package['automated_lane'] == 'off'
    assert package['authoritative_mode'] == 'unapproved'
    assert package['stage_e2'] == 'not_implemented'


def test_the_closeout_records_all_109_per_game_fingerprints():
    package = _package()
    assert len(package['per_game_fingerprints']) == 109
    assert package['full_scope_sha256'] == FULL_SCOPE_DIGEST
    assert package['parity_contract_version'] == '4'


def test_the_closeout_records_the_r6_historical_evidence():
    package = _package()
    assert package['r6_repository_sha'] == (
        '81271e0671b9391b4297f3b438e2a8b836bf94d7'
    )
    assert package['r6_workflow_run_id'] == '30664706174'
    assert package['r6_approved_fingerprint'] == (
        '40659a4051226df40ef7cedbca7a6bc2689d5c2bfbdd4ccdb717fc6fc0c79343'
    )


def test_the_closeout_is_deterministic():
    assert json.dumps(_package(), sort_keys=True) == json.dumps(
        _package(), sort_keys=True
    )


def test_the_closeout_contains_no_credential_shaped_text():
    text = json.dumps(_package())
    for token in ('postgres://', 'postgresql://', 'password=', 'SECRET_KEY',
                  'DATABASE_URL', 'ADMIN_API_TOKEN'):
        assert token not in text


def _summary_text():
    decision = _closeout()
    return validator.pass_markdown(
        validator.build_summary(decision, _package(decision))
    )


def test_the_summary_says_stage_e_performed_no_database_writes():
    assert 'No database writes were performed by Stage E.' in _summary_text()


def test_the_summary_never_claims_the_system_has_no_dead_letters():
    """Every dead-letter statement must say WHICH population it counts.

    "Governed-game dead letters: 0" is true and required. A bare
    "dead letters: 0" would be a false claim about the whole system, which
    still holds 1,389 from unrelated work.
    """
    text = _summary_text()
    for false_claim in (
        'the system has no dead letters', 'no dead letters',
        'free of dead letters', 'zero dead letters',
    ):
        assert false_claim.lower() not in text.lower(), false_claim

    qualifiers = ('governed-game', 'global')
    for line in text.splitlines():
        if 'dead letter' not in line.lower():
            continue
        assert any(word in line.lower() for word in qualifiers), line


def test_the_summary_reports_both_dead_letter_counts():
    text = _summary_text()
    assert 'Governed-game dead letters: 0' in text
    assert 'Global dead letters at R6 closeout: 1389' in text
    assert 'Current global dead letters: 1389' in text


def test_the_summary_states_the_verified_bootstrap():
    text = _summary_text()
    assert 'Completed final games: 109' in text
    assert 'Unresolved final games: 0' in text
    assert 'Reconciled appearance rows: 946' in text
    assert 'Rows unchanged: 946' in text
    assert 'Decimal-only differences safely ignored: 323' in text


def test_the_summary_records_the_workflow_retirement():
    text = _summary_text()
    for stage in ('R1', 'R2', 'R3', 'R4', 'R5', 'R6'):
        assert f'- {stage} workflow removed: yes' in text


def test_the_summary_keeps_every_lane_closed():
    text = _summary_text()
    assert 'GAME_DRIVEN_INGESTION_MODE remains off.' in text
    assert 'Authoritative mode remains unapproved.' in text
    assert 'Stage E may proceed to E2 final cleanup.' in text


def test_a_failed_result_names_the_phase_and_blocks_e2():
    with pytest.raises(validator.ValidationFailure) as caught:
        _closeout(replay=_replay(rows_expected=945))
    summary = validator.failed_summary(caught.value)
    assert summary['result'] == validator.RESULT_FAILED
    assert summary['failed_phase'] == 'replay'
    text = validator.failed_markdown(summary)
    assert 'Do not enable any lane' in text
    assert 'Do not proceed to E2' in text


# ═══════════════ CLI ════════════════════════════════════════════════════════


def _cli(tmp_path, **overrides):
    payloads = {
        'before.json': _state('before'),
        'replay.json': _replay(),
        'after.json': _state('after'),
    }
    payloads.update(overrides)
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload))
    return validator.main([
        '--before-state', str(tmp_path / 'before.json'),
        '--replay', str(tmp_path / 'replay.json'),
        '--after-state', str(tmp_path / 'after.json'),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--closeout-json', str(tmp_path / 'closeout.json'),
        '--closeout-markdown', str(tmp_path / 'closeout.md'),
        '--repository-sha', 'abc123', '--run-id', '42',
    ])


def test_the_cli_exits_zero_and_writes_every_artifact(tmp_path):
    assert _cli(tmp_path) == 0
    for name in ('summary.json', 'summary.md', 'closeout.json', 'closeout.md'):
        assert (tmp_path / name).is_file(), name
    assert json.loads((tmp_path / 'summary.json').read_text())['result'] == 'pass'


def test_a_failed_result_cannot_exit_zero(tmp_path):
    assert _cli(tmp_path, **{'replay.json': _replay(rows_expected=945)}) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['automated_lane'] == 'off'


def test_the_cli_output_is_deterministic(tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    first.mkdir()
    second.mkdir()
    assert _cli(first) == 0
    assert _cli(second) == 0
    for name in ('summary.json', 'closeout.json', 'closeout.md', 'summary.md'):
        assert (first / name).read_text() == (second / name).read_text(), name


def test_a_missing_artifact_fails_closed(tmp_path):
    (tmp_path / 'replay.json').write_text(json.dumps(_replay()))
    (tmp_path / 'after.json').write_text(json.dumps(_state('after')))
    assert validator.main([
        '--before-state', str(tmp_path / 'absent.json'),
        '--replay', str(tmp_path / 'replay.json'),
        '--after-state', str(tmp_path / 'after.json'),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--closeout-json', str(tmp_path / 'closeout.json'),
        '--closeout-markdown', str(tmp_path / 'closeout.md'),
    ]) == 1


# ═══════════════ Cleanup manifest ═══════════════════════════════════════════


def test_the_cleanup_manifest_verifies_against_the_working_tree():
    """It checks the tree rather than describing it from memory."""
    manifest = manifest_builder.build_manifest()
    assert manifest['all_entries_verified'], manifest['verification_mismatches']
    assert manifest['verification_mismatches'] == []


def test_the_cleanup_manifest_classifies_every_required_family():
    manifest = manifest_builder.build_manifest()
    by_path = {entry['path']: entry for entry in manifest['entries']}

    for name in RETIRED_WORKFLOWS:
        entry = by_path[f'.github/workflows/{name}']
        assert entry['classification'] == 'removed_rollout_only'
        assert entry['retained'] is False

    stage_e = by_path[
        '.github/workflows/foundation-3c-stage-e-bootstrap-closeout.yml'
    ]
    assert stage_e['classification'] == 'retain_until_stage_e2'
    assert stage_e['retained'] is True

    for path in (
        'backend/scripts/stage_e_bootstrap_scope.py',
        'backend/scripts/inspect_stage_e_bootstrap_state.py',
        'backend/scripts/validate_stage_e_bootstrap_closeout.py',
        'backend/tests/test_foundation_3c_stage_e_workflow.py',
        'backend/scripts/r5_remaining_window_scope.py',
    ):
        assert by_path[path]['classification'] == 'retain_until_stage_e2', path

    assert by_path[FORENSIC_FILE]['classification'] == (
        'unresolved_forensic_support'
    )
    assert by_path[FORENSIC_FILE]['retained'] is True

    for path in PERMANENT_RUNTIME_FILES:
        assert by_path[path]['classification'] == 'permanent_runtime', path


def test_the_cleanup_manifest_records_no_remaining_rollout_workflow():
    manifest = manifest_builder.build_manifest()
    assert manifest['rollout_workflows_remaining'] == [WORKFLOW_PATH.name]


def test_every_removed_entry_names_where_its_behavior_went_or_why_not():
    manifest = manifest_builder.build_manifest()
    for entry in manifest['entries']:
        if entry['classification'] != 'removed_rollout_only':
            continue
        assert entry['reason'], entry['path']


def test_the_manifest_cli_writes_both_artifacts(tmp_path):
    assert manifest_builder.main([
        '--json', str(tmp_path / 'manifest.json'),
        '--markdown', str(tmp_path / 'manifest.md'),
    ]) == 0
    payload = json.loads((tmp_path / 'manifest.json').read_text())
    assert payload['all_entries_verified'] is True
    text = (tmp_path / 'manifest.md').read_text()
    assert 'removed_rollout_only' in text
    assert 'retain_until_stage_e2' in text
    assert 'unresolved_forensic_support' in text


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
    """Start times that make the planner reproduce the reviewed order.

    With one shared start time the planner falls through to game_pk ascending,
    which is not the order the bootstrap produced — a fixture like that would
    test the ordering assertion against nothing.
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


def _build_completed_bootstrap():
    """The final production shape: 109 games complete, 946 rows reconciled."""
    boxscores = {}
    canonical_index = {pk: i for i, pk in enumerate(CANONICAL_ORDER)}
    for game_pk in CANONICAL_ORDER:
        _schedule_in_canonical_position(game_pk, canonical_index[game_pk])
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
                # Same canonical outs, different decimal representation.
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
    for game_pk in CANONICAL_ORDER:
        db.session.add(_completed_work_item(game_pk, ROWS_BY_GAME[game_pk]))
    db.session.commit()
    return boxscores


def _run_replay():
    return game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        only_game_pks=list(CANONICAL_ORDER),
    )


def test_the_real_109_game_replay_verifies_the_bootstrap(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_build_completed_bootstrap()),
        )
        from scripts import inspect_stage_e_bootstrap_state as inspector

        before = inspector.collect_state()
        completeness = before['publication_completeness']
        assert completeness['expected_final_games'] == 109
        assert completeness['completed_final_games'] == 109
        assert completeness['unresolved_final_games'] == 0
        assert completeness['critical_appearance_rows_reconciled'] == 946
        assert completeness['publication_complete'] is True
        assert before['governed_work_item_count'] == 109
        assert before['governed_unresolved_set'] == []
        assert before['governed_dead_letter_count'] == 0

        report = _run_replay()
        db.session.rollback()

        assert report['status'] == 'complete'
        assert report['games_completed'] == 109
        assert report['rows_unchanged'] == 946
        assert report['rows_inserted'] == 0
        assert report['rows_updated'] == 0
        assert report['derived_companion_differences_ignored'] == 323
        assert report['complete_mutation_count'] == 0
        assert report['pitcher_identity_mutations'] == 0
        assert report['appearance_team_mutations'] == 0
        assert report['canonical_outs_corrections'] == 0
        assert report['parity_contract_version'] == '4'
        assert len(report['complete_reconciliation_fingerprint']) == 64

        after = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['governed_work_items_hash'] == (
            before['governed_work_items_hash']
        )
        assert after['publication_completeness'] == (
            before['publication_completeness']
        )

        decision = validator.validate_closeout(
            before_state={**before, 'phase': 'before',
                          'read_only': {'write_probe_refused': True}},
            replay=report,
            after_state={**after, 'phase': 'after',
                         'read_only': {'write_probe_refused': True}},
        )
        assert decision['result'] == validator.RESULT_PASS
        assert decision['replay']['total_rows'] == 946
        assert decision['replay']['total_ignored'] == 323


def test_the_real_replay_creates_no_work_item_or_checkpoint(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_build_completed_bootstrap()),
        )
        before = GameIngestionWorkItem.query.count()
        _run_replay()
        db.session.rollback()
        assert GameIngestionWorkItem.query.count() == before == 109


def test_an_unresolved_work_item_is_detected_in_production_shape(
    app, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_build_completed_bootstrap()),
        )
        from scripts import inspect_stage_e_bootstrap_state as inspector

        target = CANONICAL_ORDER[0]
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=target).one()
        item.status = GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE
        item.completed_at = None
        item.completion_proof = None
        db.session.commit()

        state = inspector.collect_state()
        assert target in state['governed_unresolved_set']
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_bootstrap_state(
                {**state, 'phase': 'before',
                 'read_only': {'write_probe_refused': True}}, phase='before',
            )
        assert caught.value.invariant.startswith('before_state_')


def test_a_gamelog_correction_breaks_the_replay(app, monkeypatch):
    with app.app_context():
        boxscores = _build_completed_bootstrap()
        target = CANONICAL_ORDER[0]
        row = (
            GameLog.query.filter(GameLog.mlb_game_pk == target)
            .order_by(GameLog.pitcher_id).all()[-1]
        )
        row.earned_runs = (row.earned_runs or 0) + 3
        db.session.commit()

        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient(boxscores))
        report = _run_replay()
        db.session.rollback()

        assert report['rows_updated'] >= 1
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_full_replay(report)
        assert 'rows_updated' in caught.value.invariant


def test_an_identity_creation_breaks_the_replay(app, monkeypatch):
    with app.app_context():
        boxscores = _build_completed_bootstrap()
        target = CANONICAL_ORDER[0]
        lines = [
            (target * 100 + index + 1, 'home', pitching_stats())
            for index in range(ROWS_BY_GAME[target])
        ]
        lines.append((6666666, 'home', pitching_stats()))
        boxscores[target] = boxscore(lines)
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient(boxscores))

        report = _run_replay()
        db.session.rollback()

        assert report['pitcher_identity_creations'] >= 1
        with pytest.raises(validator.ValidationFailure):
            validator.validate_full_replay(report)


def test_a_governed_game_dead_letter_is_detected(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_build_completed_bootstrap()),
        )
        from scripts import inspect_stage_e_bootstrap_state as inspector

        target = CANONICAL_ORDER[0]
        db.session.add(SyncFailure(
            job_name='game_driven_ingestion',
            entity_type=game_driven_ingestion.GAME_INGESTION_FAILURE_ENTITY_TYPE,
            entity_ref=str(target),
            error='injected for the Stage E guard',
        ))
        db.session.commit()

        state = inspector.collect_state()
        assert state['governed_dead_letter_count'] == 1
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_bootstrap_state(
                {**state, 'phase': 'before',
                 'read_only': {'write_probe_refused': True}}, phase='before',
            )
        assert 'governed_dead_letter_count' in caught.value.invariant


def test_an_unrelated_global_dead_letter_does_not_fail_the_closeout(
    app, monkeypatch,
):
    """A dead letter on something outside the bootstrap is not a Stage E failure."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_build_completed_bootstrap()),
        )
        from scripts import inspect_stage_e_bootstrap_state as inspector

        db.session.add(SyncFailure(
            job_name='some_other_workstream',
            entity_type='some_other_entity',
            entity_ref='not-a-governed-game',
            error='belongs to a different workstream',
        ))
        db.session.commit()

        state = inspector.collect_state()
        assert state['governed_dead_letter_count'] == 0
        assert state['global_dead_letter_count'] == 1
        # Governed is clean, so the bootstrap contract still holds.
        validator.validate_bootstrap_state(
            {**state, 'phase': 'before',
             'read_only': {'write_probe_refused': True}}, phase='before',
        )
        advisory = validator.dead_letter_advisory(state)
        assert advisory['governed_bootstrap_dead_letters'] == 0
        assert advisory['foundation_3c_created_new_dead_letters'] is False


def test_a_write_during_the_replay_is_caught_by_the_after_state(
    app, monkeypatch,
):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_build_completed_bootstrap()),
        )
        from scripts import inspect_stage_e_bootstrap_state as inspector

        before = inspector.collect_state()
        _run_replay()
        db.session.rollback()

        target = CANONICAL_ORDER[0]
        row = GameLog.query.filter(GameLog.mlb_game_pk == target).first()
        row.earned_runs = (row.earned_runs or 0) + 1
        db.session.commit()

        after = inspector.collect_state()
        assert after['game_log_content_hash'] != before['game_log_content_hash']
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_no_drift(before, after)
        assert 'game_log_content_hash_unchanged' in caught.value.invariant
