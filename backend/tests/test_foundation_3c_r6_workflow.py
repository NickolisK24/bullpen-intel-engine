"""Foundation 3C — the R6 full remaining-window write and closeout.

R6 completes the bootstrap. It applies the plan R5 reviewed across the entire
remaining 99-game scope and may change exactly one thing: governed ingestion
control state. Ninety-nine work items are created and completed, completeness
moves 10/99 -> 109/0, and publication becomes complete. No baseball-data row may
change.

Three properties carry most of the weight here and are tested hardest:

  AUTHORIZATION — the write is unreachable unless the preflight validator
  authorized it, and authorization is re-proven from the write REPORT rather
  than inferred from an exit code. Three historical 64-character values must
  never authorize it, including the scope digest, which is a scope proof and
  not a plan fingerprint at all.

  SINGLE USE — the before-state requires 10/99 and no work item on any selected
  game. After a successful run those are false, so a second dispatch stops.

  PARTIAL COMPLETION IS FAILED — the writer commits per game, so a failure at
  game 50 leaves 49 durable checkpoints. That is reported honestly and never
  retried or compensated.

The YAML parser is imported inside a fixture rather than via
`pytest.importorskip`, so a missing parser makes these tests ERROR loudly
instead of silently skipping the rollout guards they exist to enforce.
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
from scripts import r5_remaining_window_scope as scope
from scripts import validate_r6_full_write as validator
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
    / 'foundation-3c-r6-full-remaining-window-write.yml'
)

APPROVED_ORDER = scope.CANONICAL_ORDER
APPROVED_SET = scope.SORTED_SET
COMPLETED = scope.COMPLETED_GAME_PKS
TOTAL_ROWS = scope.EXPECTED_TOTAL_ROWS        # 865
TOTAL_IGNORED = scope.EXPECTED_TOTAL_IGNORED  # 291
SCOPE_DIGEST = scope.SCOPE_DIGEST

APPROVED_FINGERPRINT = validator.APPROVED_FINGERPRINT
STALE_CONTRACT_3 = validator.STALE_CONTRACT_3_FINGERPRINT
R4_FINGERPRINT = validator.R4_FIVE_GAME_FINGERPRINT


# 73 games of 9 rows + 26 of 8 == 865. 93 of 3 ignored + 6 of 2 == 291.
ROWS_BY_GAME = {
    pk: (9 if i < 73 else 8) for i, pk in enumerate(APPROVED_ORDER)
}
IGNORED_BY_GAME = {
    pk: (3 if i < 93 else 2) for i, pk in enumerate(APPROVED_ORDER)
}
COMPLETED_ROWS_BY_GAME = {
    pk: (8 if i < 3 else 7) for i, pk in enumerate(sorted(COMPLETED))
}   # 3*8 + 7*7 = 73 ... adjusted below to the real 81


def test_the_fixture_shape_matches_the_approved_totals():
    assert sum(ROWS_BY_GAME.values()) == TOTAL_ROWS == 865
    assert sum(IGNORED_BY_GAME.values()) == TOTAL_IGNORED == 291
    assert all(IGNORED_BY_GAME[pk] <= ROWS_BY_GAME[pk] for pk in APPROVED_ORDER)


# ═══════════════ Scope, reused from R5 ══════════════════════════════════════


def test_the_r6_scope_is_the_r5_module_not_a_second_copy():
    """One canonical Python scope authority, imported rather than restated.

    Asserted by value plus a source check rather than by identity: the
    validator adds its own directory to sys.path and imports the bare module
    name, so the same file can legitimately be loaded under two names. What
    must not exist is a second hand-written copy of the identifiers.
    """
    assert list(validator.APPROVED_ORDER) == list(scope.CANONICAL_ORDER)
    assert validator.SCOPE_DIGEST == scope.SCOPE_DIGEST
    source = Path(validator.__file__).read_text(encoding='utf-8')
    literals = [str(pk) for pk in scope.CANONICAL_ORDER if str(pk) in source]
    assert literals == [], literals


def test_the_scope_is_99_unique_positive_games():
    assert len(APPROVED_ORDER) == 99
    assert len(set(APPROVED_ORDER)) == 99
    assert all(isinstance(pk, int) and pk > 0 for pk in APPROVED_ORDER)


def test_no_completed_game_is_in_scope():
    assert not set(APPROVED_ORDER) & set(COMPLETED)


def test_the_union_with_the_completed_ten_is_109():
    assert len(set(APPROVED_ORDER) | set(COMPLETED)) == 109


def test_the_scope_digest_matches_the_approved_value():
    assert SCOPE_DIGEST == (
        '43b9333ad228c60846f1cd24ae8518273dc1017aefc98e7b7930974c40bdfd22'
    )


def test_the_approved_fingerprint_is_the_founder_value():
    assert APPROVED_FINGERPRINT == (
        '40659a4051226df40ef7cedbca7a6bc2689d5c2bfbdd4ccdb717fc6fc0c79343'
    )


def test_the_reconciled_appearance_total_is_grounded_arithmetic():
    """38 (original five) + 43 (R4 five) + 865 (R6 99) == 946."""
    assert validator.EXPECTED_RECONCILED_APPEARANCE_ROWS == 38 + 43 + 865 == 946


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

    The header comment names the values and options this workflow must never
    use, which is exactly the documentation worth keeping — but a flag or
    fingerprint inside a comment is not passed to anything, so the prohibition
    guards are asserted against executable content.
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


@pytest.fixture(scope='module')
def scope_arguments(job, tmp_path_factory):
    """The argv the scope guard ACTUALLY emits, by running its own shell block.

    The 99 identifiers live in a Bash array that is expanded into a file, so
    reading the YAML proves nothing about what the commands receive. This runs
    the real block.
    """
    step = next(
        s for s in job['steps']
        if (s.get('name') or '').startswith('Validate the hard-coded scope')
    )
    workdir = tmp_path_factory.mktemp('r6scope')
    (workdir / 'artifacts').mkdir()
    script = (
        f'APPROVED_SCOPE_DIGEST={SCOPE_DIGEST}\n' + step['run']
    )
    (workdir / 'scope.sh').write_text(script)
    result = subprocess.run(
        ['bash', 'scope.sh'], cwd=workdir, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = [
        line.strip()
        for line in (workdir / 'artifacts' / 'r6-scope-args.txt').read_text()
        .splitlines() if line.strip()
    ]
    return lines


# ═══════════════ Parser-independent guards ══════════════════════════════════


def test_the_workflow_file_exists():
    assert WORKFLOW_PATH.is_file()


def test_no_forbidden_option_appears_in_executable_content(executable_text):
    for option in (
        '--game-pk ', '--max-games', '--time-budget-seconds',
        '--include-backfill', '--plan-only',
    ):
        assert option not in executable_text, option


def test_no_authoritative_mode_appears(executable_text):
    assert '--mode authoritative' not in executable_text
    assert 'authoritative' not in executable_text.lower().replace(
        'authoritative_mode', ''
    ) or '--mode authoritative' not in executable_text


def test_exactly_one_write_mode_and_two_shadow_modes(executable_text):
    assert executable_text.count('--mode write') == 1
    assert executable_text.count('--mode shadow') == 2


def test_the_stale_fingerprints_appear_nowhere_in_the_workflow(workflow_text):
    """Not even in a comment. There is no reason for them to be here at all."""
    assert STALE_CONTRACT_3 not in workflow_text
    assert R4_FINGERPRINT not in workflow_text


def test_the_scope_digest_is_never_passed_as_a_plan_fingerprint(executable_text):
    index = executable_text.find('--expected-plan-fingerprint')
    assert index != -1
    following = executable_text[index:index + 200]
    assert APPROVED_FINGERPRINT in following
    assert SCOPE_DIGEST not in following


def test_the_approved_fingerprint_appears_exactly_once_in_commands(
    executable_text,
):
    assert executable_text.count(APPROVED_FINGERPRINT) == 1


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


def test_the_scope_cannot_be_populated_from_a_dynamic_source(job):
    step = next(
        s for s in job['steps']
        if (s.get('name') or '').startswith('Validate the hard-coded scope')
    )
    array = step['run'].split('R6_GAME_PKS=(')[1].split(')')[0]
    for construct in ('$(', '`', 'curl', 'psql', 'python', 'http', '${'):
        assert construct not in array, construct
    entries = [line.strip() for line in array.splitlines() if line.strip()]
    assert len(entries) == 99
    assert all(entry.isdigit() for entry in entries)
    assert [int(entry) for entry in entries] == list(APPROVED_ORDER)


def test_the_scope_cannot_be_altered_by_a_workflow_input(executable_text):
    assert 'inputs' not in executable_text
    assert 'github.event.inputs' not in executable_text


# ═══════════════ Structural contract ════════════════════════════════════════


def test_the_workflow_name_is_the_agreed_one(workflow):
    assert workflow['name'] == (
        'Foundation 3C R6 Full Remaining Window Write and Closeout'
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


def test_the_timeout_is_finite_and_sixty_minutes(job):
    assert job['timeout-minutes'] == 60


def test_concurrency_joins_the_production_write_group(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_concurrency_does_not_cancel_in_progress(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_the_runner_is_pinned(job):
    assert job['runs-on'] == 'ubuntu-latest'


# ═══════════════ Command construction ═══════════════════════════════════════


def test_exactly_three_ingestion_invocations_exist(run_commands):
    invocations = [
        line for line in run_commands if 'game_driven_ingestion.py' in line
    ]
    assert len(invocations) == 3


def test_exactly_one_write_invocation_exists(run_commands):
    assert len([line for line in run_commands if '--mode write' in line]) == 1


def test_the_preflight_and_replay_are_shadow(run_commands):
    assert len([line for line in run_commands if '--mode shadow' in line]) == 2


def test_only_the_write_carries_an_expected_fingerprint(job):
    steps = {
        (s.get('name') or ''): (s.get('run') or '') for s in job['steps']
    }
    write = next(v for k, v in steps.items() if k.startswith('Run the R6 full'))
    preflight = next(
        v for k, v in steps.items() if k.startswith('Run the R6 preflight')
    )
    replay = next(
        v for k, v in steps.items() if k.startswith('Run the post-write')
    )
    assert '--expected-plan-fingerprint' in write
    assert '--expected-plan-fingerprint' not in preflight
    assert '--expected-plan-fingerprint' not in replay


def test_the_scope_guard_emits_exactly_99_only_game_pk_flags(scope_arguments):
    assert scope_arguments.count('--only-game-pk') == 99


def test_the_scope_guard_emits_the_exact_approved_order(scope_arguments):
    ids = [
        int(scope_arguments[i + 1]) for i, a in enumerate(scope_arguments)
        if a == '--only-game-pk'
    ]
    assert ids == list(APPROVED_ORDER)
    assert sorted(ids) == list(APPROVED_SET)
    assert len(set(ids)) == 99
    assert not set(ids) & set(COMPLETED)


def test_the_shell_digest_equals_the_python_digest(scope_arguments):
    ids = [
        int(scope_arguments[i + 1]) for i, a in enumerate(scope_arguments)
        if a == '--only-game-pk'
    ]
    assert scope.scope_digest(ids) == SCOPE_DIGEST


def test_all_three_invocations_consume_the_same_validated_scope(job):
    """Each command reads the one file the guard wrote, not its own copy."""
    ingestion_steps = [
        s.get('run') or '' for s in job['steps']
        if 'game_driven_ingestion.py' in (s.get('run') or '')
    ]
    assert len(ingestion_steps) == 3
    for script in ingestion_steps:
        assert 'mapfile -t scope_args < artifacts/r6-scope-args.txt' in script
        assert '"${scope_args[@]}"' in script


@pytest.mark.parametrize('mutation,expected_message', [
    ('drop', 'exactly 99 games'),
    ('duplicate', 'duplicate game identifiers'),
    ('completed', 'already-completed game'),
    ('nonnumeric', 'non-numeric entry'),
])
def test_the_scope_guard_refuses_a_tampered_array(
    job, tmp_path, mutation, expected_message,
):
    """The guard is not decoration: prove each branch actually fires."""
    step = next(
        s for s in job['steps']
        if (s.get('name') or '').startswith('Validate the hard-coded scope')
    )
    # Locate the last array entry in the PARSED block. YAML strips the block
    # indent, so matching the file's own indentation would silently no-op and
    # the guard would look like it accepted a tampered array.
    lines = step['run'].splitlines()
    index = max(i for i, line in enumerate(lines) if line.strip() == '823924')
    indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
    if mutation == 'drop':
        del lines[index]
    elif mutation == 'duplicate':
        lines[index] = f'{indent}823519'
    elif mutation == 'completed':
        lines[index] = f'{indent}{COMPLETED[0]}'
    else:
        lines[index] = f'{indent}8239x4'
    script = '\n'.join(lines) + '\n'

    (tmp_path / 'artifacts').mkdir()
    (tmp_path / 'scope.sh').write_text(
        f'APPROVED_SCOPE_DIGEST={SCOPE_DIGEST}\n' + script
    )
    result = subprocess.run(
        ['bash', 'scope.sh'], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 1
    assert expected_message in result.stdout + result.stderr


def test_the_scope_guard_refuses_a_wrong_digest(job, tmp_path):
    step = next(
        s for s in job['steps']
        if (s.get('name') or '').startswith('Validate the hard-coded scope')
    )
    (tmp_path / 'artifacts').mkdir()
    (tmp_path / 'scope.sh').write_text(
        'APPROVED_SCOPE_DIGEST=' + ('0' * 64) + '\n' + step['run']
    )
    result = subprocess.run(
        ['bash', 'scope.sh'], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 1
    assert 'digest does not match' in result.stdout + result.stderr


# ═══════════════ Step order ═════════════════════════════════════════════════


def _step_index(job, prefix):
    for index, step in enumerate(job['steps']):
        if (step.get('name') or '').startswith(prefix):
            return index
    raise AssertionError(prefix)


def test_the_scope_guard_runs_before_any_database_step(job):
    assert _step_index(job, 'Validate the hard-coded scope') < _step_index(
        job, 'Capture the before state'
    )


def test_the_before_state_precedes_the_preflight(job):
    assert _step_index(job, 'Capture the before state') < _step_index(
        job, 'Run the R6 preflight'
    )


def test_the_prewrite_state_is_after_preflight_and_before_authorization(job):
    assert _step_index(job, 'Run the R6 preflight') < _step_index(
        job, 'Capture the prewrite state'
    ) < _step_index(job, 'Authorize the write')


def test_authorization_precedes_the_write(job):
    assert _step_index(job, 'Authorize the write') < _step_index(
        job, 'Run the R6 full'
    )


def test_the_write_cannot_run_on_failed_authorization(job):
    step = job['steps'][_step_index(job, 'Run the R6 full')]
    assert step['if'] == "${{ steps.authorize.outputs.authorize_exit == '0' }}"


def test_the_preflight_cannot_run_on_a_failed_before_state(job):
    step = job['steps'][_step_index(job, 'Run the R6 preflight')]
    assert "steps.before.outputs.before_exit == '0'" in step['if']


def test_the_after_write_snapshot_follows_the_write_under_always(job):
    index = _step_index(job, 'Capture the after-write state')
    assert _step_index(job, 'Run the R6 full') < index
    step = job['steps'][index]
    assert 'always()' in step['if']
    assert "steps.authorize.outputs.authorize_exit == '0'" in step['if']


def test_the_replay_follows_the_write_attempt_under_always(job):
    index = _step_index(job, 'Run the post-write')
    assert _step_index(job, 'Run the R6 full') < index
    assert 'always()' in job['steps'][index]['if']


def test_the_final_snapshot_follows_the_replay(job):
    assert _step_index(job, 'Run the post-write') < _step_index(
        job, 'Capture the final state'
    )
    assert 'always()' in job['steps'][_step_index(job, 'Capture the final')]['if']


def test_validation_follows_the_final_snapshot(job):
    assert _step_index(job, 'Capture the final state') < _step_index(
        job, 'Validate the complete R6 closeout'
    )


def test_the_credential_scan_precedes_upload(job):
    assert _step_index(job, 'Scan artifacts') < _step_index(
        job, 'Upload the R6 artifacts'
    )


def test_the_upload_runs_under_always_with_ninety_day_retention(job):
    step = job['steps'][_step_index(job, 'Upload the R6 artifacts')]
    assert 'always()' in step['if']
    assert step['with']['retention-days'] == 90
    assert step['with']['if-no-files-found'] == 'warn'
    assert step['with']['name'] == (
        'foundation-3c-r6-full-remaining-window-write'
    )


def test_the_final_gate_follows_upload(job):
    assert _step_index(job, 'Upload the R6 artifacts') < _step_index(
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
    (artifacts / 'r6-closeout.json').write_text(json.dumps({'note': poison}))
    (tmp_path / 'scan.py').write_text(scanner_script)
    result = subprocess.run(
        ['python', 'scan.py'], cwd=tmp_path, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 1
    assert poison not in result.stdout
    assert not (artifacts / 'r6-closeout.json').exists()


def test_the_scanner_passes_a_clean_artifact(scanner_script, tmp_path):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'r6-closeout.json').write_text(
        json.dumps({'result': 'pass', 'rows_unchanged': 865})
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


def _game(game_pk, index, *, status='projected', attempt=1):
    rows = ROWS_BY_GAME[game_pk]
    ignored = IGNORED_BY_GAME[game_pk]
    return {
        'game_pk': game_pk,
        'represented_date': '2026-07-29',
        'candidate_reason': GameIngestionWorkItem.REASON_EXPLICIT_REPAIR,
        'criticality': GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        'attempt_number': attempt,
        'status': status,
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


def _shadow(**overrides):
    report = {
        'status': 'complete', 'mode': 'shadow',
        'reference_date': '2026-07-29', 'execution_scope_mode': 'exclusive',
        'reconciliation_plan_version':
            reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        'requested_game_count': 99, 'planned_game_count': 99,
        'duplicate_requested_count': 0, 'execution_scope_exact_match': True,
        'requested_game_pks': list(APPROVED_SET),
        'planned_game_pks': list(APPROVED_SET),
        'unexpected_planned_game_pks': [], 'missing_requested_game_pks': [],
        'games_attempted': 99, 'games_fetched': 99, 'games_completed': 99,
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
        'complete_reconciliation_fingerprint': APPROVED_FINGERPRINT,
        'games': [
            _game(pk, i) for i, pk in enumerate(APPROVED_ORDER)
        ],
    }
    report.update(overrides)
    return report


def _write_report(**overrides):
    report = {
        'status': 'complete', 'mode': 'write',
        'reference_date': '2026-07-29', 'execution_scope_mode': 'exclusive',
        'reconciliation_plan_version':
            reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        'expected_plan_fingerprint': APPROVED_FINGERPRINT,
        'authorized_plan_fingerprint': APPROVED_FINGERPRINT,
        'requested_game_count': 99, 'planned_game_count': 99,
        'execution_scope_exact_match': True,
        'requested_game_pks': list(APPROVED_SET),
        'planned_game_pks': list(APPROVED_SET),
        'games_attempted': 99, 'games_completed': 99, 'games_failed': 0,
        'games_remaining': 0, 'budget_stop_triggered': False,
        'rows_expected': TOTAL_ROWS, 'rows_inserted': 0, 'rows_updated': 0,
        'rows_unchanged': TOTAL_ROWS, 'rows_blocked': 0,
        'changed_fields_counts': {},
        'pitcher_identity_mutations': 0, 'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0, 'pitcher_identity_blocked': 0,
        'appearance_team_mutations': 0, 'complete_mutation_count': 0,
        'canonical_outs_corrections': 0, 'statistical_corrections': 0,
        'provenance_only_updates': 0, 'authority_reconciliations': 0,
        'corrections_applied': 0, 'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': TOTAL_IGNORED,
        'games': [
            {'game_pk': pk,
             'status': GameIngestionWorkItem.STATUS_COMPLETED}
            for pk in APPROVED_ORDER
        ],
    }
    report.update(overrides)
    return report


def _state(phase, *, after=False, **overrides):
    completeness = (
        {
            'expected_final_games': 109, 'completed_final_games': 109,
            'unresolved_final_games': 0, 'terminal_failure_games': 0,
            'correction_pending_games': 0,
            'critical_appearance_rows_expected': 946,
            'critical_appearance_rows_reconciled': 946,
            'publication_complete': True,
        } if after else {
            'expected_final_games': 109, 'completed_final_games': 10,
            'unresolved_final_games': 99, 'terminal_failure_games': 0,
            'correction_pending_games': 0,
            'critical_appearance_rows_expected': 81,
            'critical_appearance_rows_reconciled': 81,
            'publication_complete': False,
        }
    )
    work_items = {
        str(pk): {
            'status': GameIngestionWorkItem.STATUS_COMPLETED,
            'attempt_count': 1, 'error_class': None,
            'rows_expected': ROWS_BY_GAME[pk],
            'rows_reconciled': ROWS_BY_GAME[pk], 'completed': True,
        } for pk in APPROVED_SET
    } if after else {}
    state = {
        'phase': phase, 'reference_date': '2026-07-29',
        'read_only': {'write_probe_refused': True},
        'read_only_after': {'write_probe_refused': True},
        'selected_game_pks': list(APPROVED_SET), 'selected_game_count': 99,
        'selected_scope_digest': SCOPE_DIGEST,
        'approved_completed_game_pks': list(COMPLETED),
        'game_log_row_count': TOTAL_ROWS,
        'game_log_content_hash': 'a' * 64, 'canonical_outs_hash': 'b' * 64,
        'correction_provenance_hash': 'c' * 64,
        'appearance_team_hash': 'd' * 64, 'pitcher_state_hash': 'e' * 64,
        'pitcher_count': 400, 'pitcher_mlb_ids': [1, 2, 3],
        'selected_work_items': work_items,
        'selected_work_item_count': 99 if after else 0,
        'duplicate_selected_game_pks': [],
        'selected_completed_set': list(APPROVED_SET) if after else [],
        'selected_unresolved_set': [], 'selected_terminal_set': [],
        'all_work_items_hash': ('9' * 64) if after else ('f' * 64),
        'all_work_item_count': 109 if after else 10,
        'completed_work_item_set': (
            sorted(set(COMPLETED) | set(APPROVED_SET)) if after
            else list(COMPLETED)
        ),
        'terminal_work_item_set': [],
        'unresolved_set': [] if after else list(APPROVED_SET),
        'non_critical_selected_game_pks': [],
        'unplanned_selected_game_pks': [],
        'non_final_selected_game_pks': [],
        'selected_game_pks_with_prior_status': [],
        'selected_game_pks_with_prior_attempts': [],
        'finality_conflicts': 0, 'schedule_authority_missing': 0,
        'dead_letter_count': 0, 'all_dead_letter_count': 0,
        'publication_completeness': completeness,
    }
    state.update(overrides)
    return state


def _closeout(**kwargs):
    args = {
        'before_state': _state('before'),
        'preflight': _shadow(),
        'prewrite_state': _state('prewrite'),
        'write': _write_report(),
        'after_write_state': _state('after_write', after=True),
        'replay': _shadow(games=[
            _game(pk, i, attempt=2) for i, pk in enumerate(APPROVED_ORDER)
        ]),
        'final_state': _state('final', after=True),
        'write_exit': 0,
    }
    args.update(kwargs)
    return validator.validate_closeout(**args)


def _fails(fragment, **kwargs):
    with pytest.raises(validator.ValidationFailure) as caught:
        _closeout(**kwargs)
    assert fragment in caught.value.invariant, caught.value.invariant
    return caught.value


# ═══════════════ Happy path ═════════════════════════════════════════════════


def test_the_exact_clean_closeout_passes():
    decision = _closeout()
    assert decision['result'] == validator.RESULT_PASS
    assert decision['write']['games_completed'] == 99
    assert decision['write']['partial_completion'] is False
    assert decision['replay']['fingerprint'] == APPROVED_FINGERPRINT
    assert decision['transition']['completed_after'] == 109
    assert decision['transition']['unresolved_after'] == 0


def test_the_clean_preflight_authorizes_the_write():
    result = validator.validate_preflight(
        _state('before'), _shadow(), _state('prewrite'),
    )
    assert result['authorized'] is True
    assert result['fingerprint'] == APPROVED_FINGERPRINT
    assert result['scope_digest'] == SCOPE_DIGEST


# ═══════════════ Scope failures ═════════════════════════════════════════════


@pytest.mark.parametrize('count', [98, 100])
def test_a_wrong_scope_count_fails(count):
    _fails('requested_game_count', preflight=_shadow(requested_game_count=count))


def test_a_missing_game_fails():
    report = _shadow()
    report['requested_game_pks'] = list(APPROVED_SET)[:-1]
    _fails('requested_game_pks', preflight=report)


def test_an_extra_game_fails():
    report = _shadow()
    report['requested_game_pks'] = list(APPROVED_SET) + [999999]
    _fails('requested_game_pks', preflight=report)


def test_a_duplicate_game_fails():
    _fails('duplicate_requested_count',
           preflight=_shadow(duplicate_requested_count=1))


def test_a_wrong_canonical_order_fails():
    report = _shadow()
    report['games'][0], report['games'][1] = (
        report['games'][1], report['games'][0]
    )
    _fails('canonical_processing_order', preflight=report)


def test_a_completed_game_in_scope_fails():
    report = _shadow()
    report['games'][0]['game_pk'] = COMPLETED[0]
    failure = _fails('excludes_completed_games', preflight=report)
    assert failure.observed == [COMPLETED[0]]


def test_an_unknown_game_fails():
    report = _shadow()
    report['games'][5]['game_pk'] = 999999
    _fails('canonical_processing_order', preflight=report)


def test_a_wrong_scope_digest_fails():
    _fails('scope_digest',
           before_state=_state('before', selected_scope_digest='0' * 64))


def test_a_non_exclusive_scope_fails():
    _fails('execution_scope_mode',
           preflight=_shadow(execution_scope_mode='window'))


def test_exact_match_false_fails():
    _fails('execution_scope_exact_match',
           preflight=_shadow(execution_scope_exact_match=False))


# ═══════════════ Starting state ═════════════════════════════════════════════


def test_starting_completeness_not_10_99_fails():
    state = _state('before')
    state['publication_completeness']['completed_final_games'] = 11
    _fails('completeness_completed_final_games', before_state=state)


def test_a_completed_set_mismatch_fails():
    _fails('completed_work_item_set',
           before_state=_state('before',
                               completed_work_item_set=list(COMPLETED)[:-1]))


def test_an_unresolved_set_mismatch_fails():
    _fails('unresolved_set',
           before_state=_state('before',
                               unresolved_set=list(APPROVED_SET)[:-1]))


def test_an_existing_selected_work_item_fails():
    """This is also what makes R6 single-use."""
    state = _state('before', selected_work_items={
        '823519': {'status': 'completed', 'completed': True},
    })
    _fails('selected_games_have_no_work_item', before_state=state)


def test_a_second_dispatch_is_refused_by_the_after_state():
    """The state a successful R6 leaves behind cannot start another one."""
    after = _state('after_write', after=True)
    after['phase'] = 'before'
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate_before_state(after)
    assert caught.value.invariant.startswith('before_state_')


def test_a_selected_prior_attempt_fails():
    _fails('selected_game_pks_with_prior_attempts',
           before_state=_state('before',
                               selected_game_pks_with_prior_attempts=[823519]))


def test_a_terminal_selected_game_fails():
    _fails('selected_terminal_set',
           before_state=_state('before', selected_terminal_set=[823519]))


def test_a_non_final_selected_game_fails():
    _fails('non_final_selected_game_pks',
           before_state=_state('before', non_final_selected_game_pks=[823519]))


def test_a_schedule_authority_gap_fails():
    _fails('schedule_authority_missing',
           before_state=_state('before', schedule_authority_missing=1))


def test_a_finality_conflict_fails():
    _fails('finality_conflicts',
           before_state=_state('before', finality_conflicts=1))


def test_a_starting_total_work_item_count_other_than_ten_fails():
    _fails('total_work_item_count',
           before_state=_state('before', all_work_item_count=11))


# ═══════════════ Preflight report ═══════════════════════════════════════════


@pytest.mark.parametrize('field,value', [
    ('rows_expected', 864), ('rows_expected', 866),
    ('rows_inserted', 1), ('rows_updated', 1), ('rows_blocked', 1),
    ('pitcher_identity_mutations', 1), ('pitcher_identity_creations', 1),
    ('pitcher_identity_reactivations', 1),
    ('pitcher_identity_metadata_updates', 1), ('pitcher_identity_blocked', 1),
    ('appearance_team_mutations', 1), ('complete_mutation_count', 1),
    ('canonical_outs_corrections', 1), ('statistical_corrections', 1),
    ('provenance_only_updates', 1), ('authority_reconciliations', 1),
    ('derived_companion_fields_applied', 1),
    ('derived_companion_differences_ignored', 290),
    ('derived_companion_differences_ignored', 292),
])
def test_a_preflight_counter_violation_fails(field, value):
    _fails(field, preflight=_shadow(**{field: value}))


def test_a_short_row_list_fails():
    report = _shadow()
    report['games'][0]['rows'] = report['games'][0]['rows'][:-1]
    _fails('appearances_match_rows', preflight=report)


def test_a_short_row_list_with_matching_appearances_fails():
    report = _shadow()
    report['games'][0]['rows'] = report['games'][0]['rows'][:-1]
    report['games'][0]['appearances_extracted'] -= 1
    _fails('recomputed_row_total', preflight=report)


def test_a_duplicate_appearance_identity_fails():
    report = _shadow()
    rows = report['games'][0]['rows']
    rows[1]['pitcher_mlb_id'] = rows[0]['pitcher_mlb_id']
    _fails('duplicate_appearance_identity', preflight=report)


def test_a_semantic_innings_correction_fails():
    report = _shadow()
    report['games'][0]['rows'][0]['semantic_changed_fields'] = [
        'innings_pitched'
    ]
    _fails('semantic_changed_fields', preflight=report)


def test_a_row_level_ignored_disagreement_fails():
    report = _shadow()
    report['games'][0]['rows'][0]['derived_companion_differences_ignored'] = []
    _fails('ignored_reconciles', preflight=report)


def test_an_attempt_number_above_one_fails_in_preflight():
    report = _shadow()
    report['games'][3]['attempt_number'] = 2
    _fails('attempt_number', preflight=report)


def test_the_replay_may_report_a_later_attempt_number():
    """The write leaves work items behind. That is the point."""
    decision = _closeout()
    assert decision['result'] == validator.RESULT_PASS


# ═══════════════ Fingerprint authorization ══════════════════════════════════


def test_a_missing_preflight_fingerprint_fails():
    _fails('complete_reconciliation_fingerprint',
           preflight=_shadow(complete_reconciliation_fingerprint=None))


def test_an_invalid_fingerprint_fails():
    _fails('complete_reconciliation_fingerprint',
           preflight=_shadow(complete_reconciliation_fingerprint='c' * 63))


def test_a_preflight_fingerprint_mismatch_fails():
    _fails('fingerprint_matches_the_approved_plan',
           preflight=_shadow(complete_reconciliation_fingerprint='c' * 64))


@pytest.mark.parametrize('rejected', [
    validator.STALE_CONTRACT_3_FINGERPRINT,
    validator.R4_FIVE_GAME_FINGERPRINT,
    validator.SCOPE_DIGEST,
])
def test_a_rejected_authorization_value_cannot_authorize_the_write(rejected):
    """Contract-3, the R4 five-game value, and the scope digest are refused."""
    _fails('expected_fingerprint_is_not_stale',
           write=_write_report(expected_plan_fingerprint=rejected,
                               authorized_plan_fingerprint=rejected))


def test_the_scope_digest_is_explicitly_a_rejected_authorization_value():
    """It is 64 hex characters and proves scope, not a plan. Different thing."""
    assert SCOPE_DIGEST in validator.REJECTED_AUTHORIZATION_VALUES
    assert SCOPE_DIGEST != APPROVED_FINGERPRINT


def test_missing_authorization_evidence_fails():
    _fails('authorized_plan_fingerprint_present',
           write=_write_report(authorized_plan_fingerprint=None))


def test_missing_expected_fingerprint_evidence_fails():
    _fails('expected_plan_fingerprint_present',
           write=_write_report(expected_plan_fingerprint=None))


def test_a_write_that_exited_zero_without_authorization_evidence_fails():
    """Exit zero is not evidence the comparison happened."""
    report = _write_report()
    del report['authorized_plan_fingerprint']
    _fails('authorized_plan_fingerprint_present', write=report)


def test_an_authorized_fingerprint_that_differs_from_expected_fails():
    _fails('write_authorized_plan_fingerprint',
           write=_write_report(authorized_plan_fingerprint='a' * 64))


def test_a_wrong_parity_contract_fails():
    _fails('parity_contract_version', preflight=_shadow(
        parity_contract_version='3'))


# ═══════════════ Write report ═══════════════════════════════════════════════


def test_a_nonzero_write_exit_fails():
    _fails('write_exit_code', write_exit=1)


def test_a_write_game_failure_fails():
    _fails('write_games_failed', write=_write_report(games_failed=1))


def test_partial_completion_fails():
    """49 durable checkpoints is a stop, not a partial success."""
    report = _write_report()
    report['games'] = [
        {'game_pk': pk, 'status': GameIngestionWorkItem.STATUS_COMPLETED}
        for pk in APPROVED_ORDER[:49]
    ]
    report['games_completed'] = 49
    failure = _fails('write_completed_every_selected_game', write=report)
    assert failure.expected == 99
    assert failure.observed == 49


def test_a_partial_write_is_summarized_honestly():
    report = _write_report()
    report['games'] = [
        {'game_pk': pk, 'status': GameIngestionWorkItem.STATUS_COMPLETED}
        for pk in APPROVED_ORDER[:49]
    ]
    partial = validator.summarize_partial_write(report, write_exit=1)
    assert partial['completed_subset_count'] == 49
    assert partial['unresolved_subset_count'] == 50
    assert partial['partial_completion'] is True
    assert 'per_game' in partial['transaction_boundary']


@pytest.mark.parametrize('field,value', [
    ('rows_inserted', 1), ('rows_updated', 1), ('rows_blocked', 1),
    ('pitcher_identity_mutations', 1), ('pitcher_identity_creations', 1),
    ('appearance_team_mutations', 1), ('complete_mutation_count', 1),
    ('canonical_outs_corrections', 1), ('statistical_corrections', 1),
    ('provenance_only_updates', 1),
])
def test_a_write_mutation_fails(field, value):
    _fails(f'write_{field}', write=_write_report(**{field: value}))


def test_the_writer_must_still_ignore_decimal_differences():
    _fails('write_derived_companion_differences_ignored',
           write=_write_report(derived_companion_differences_ignored=0))


# ═══════════════ Control-state transition ═══════════════════════════════════


def test_a_missing_selected_work_item_fails():
    after = _state('after_write', after=True)
    after['selected_work_items'].pop(str(APPROVED_SET[0]))
    _fails('selected_work_item_keys', after_write_state=after)


def test_a_duplicate_selected_work_item_fails():
    _fails('duplicate_selected_game_pks',
           after_write_state=_state('after_write', after=True,
                                    duplicate_selected_game_pks=[823519]))


def test_an_unresolved_selected_work_item_fails():
    _fails('selected_unresolved_set',
           after_write_state=_state('after_write', after=True,
                                    selected_unresolved_set=[823519]))


def test_a_terminal_selected_work_item_fails():
    _fails('selected_terminal_set',
           after_write_state=_state('after_write', after=True,
                                    selected_terminal_set=[823519]))


def test_an_unexpected_work_item_fails():
    _fails('after_write_total_work_item_count',
           after_write_state=_state('after_write', after=True,
                                    all_work_item_count=110))


def test_a_completed_count_other_than_109_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['completed_final_games'] = 108
    _fails('after_write_completeness_completed_final_games',
           after_write_state=after)


def test_a_nonzero_unresolved_count_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['unresolved_final_games'] = 1
    _fails('after_write_completeness_unresolved_final_games',
           after_write_state=after)


def test_publication_complete_false_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['publication_complete'] = False
    _fails('after_write_completeness_publication_complete',
           after_write_state=after)


def test_an_expected_final_count_change_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['expected_final_games'] = 110
    _fails('after_write_completeness_expected_final_games',
           after_write_state=after)


def test_a_terminal_failure_after_write_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['terminal_failure_games'] = 1
    _fails('after_write_completeness_terminal_failure_games',
           after_write_state=after)


def test_a_correction_pending_game_after_write_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['correction_pending_games'] = 1
    _fails('after_write_completeness_correction_pending_games',
           after_write_state=after)


def test_a_wrong_reconciled_appearance_total_fails():
    after = _state('after_write', after=True)
    after['publication_completeness']['critical_appearance_rows_reconciled'] = 945
    _fails('critical_appearance_rows_reconciled', after_write_state=after)


def test_a_work_item_that_did_not_reconcile_its_rows_fails():
    after = _state('after_write', after=True)
    after['selected_work_items'][str(APPROVED_SET[0])]['rows_reconciled'] = 0
    _fails('rows_reconciled', after_write_state=after)


# ═══════════════ Baseball-data integrity ════════════════════════════════════


@pytest.mark.parametrize('field', list(validator.IMMUTABLE_STATE_HASHES))
def test_a_baseball_data_hash_change_fails(field):
    _fails(f'after_write_{field}_unchanged',
           after_write_state=_state('after_write', after=True,
                                    **{field: '0' * 64}))


def test_a_pitcher_identity_set_change_fails():
    _fails('pitcher_mlb_ids_unchanged',
           after_write_state=_state('after_write', after=True,
                                    pitcher_mlb_ids=[1, 2, 3, 4]))


def test_a_dead_letter_increase_fails():
    _fails('dead_letter_count_unchanged',
           after_write_state=_state('after_write', after=True,
                                    dead_letter_count=1))


def test_a_gamelog_row_count_change_fails():
    _fails('game_log_row_count_unchanged',
           after_write_state=_state('after_write', after=True,
                                    game_log_row_count=866))


# ═══════════════ Preflight caused no drift ══════════════════════════════════


@pytest.mark.parametrize('field', list(validator.IMMUTABLE_STATE_HASHES))
def test_preflight_drift_fails(field):
    _fails(f'prewrite_{field}_unchanged',
           prewrite_state=_state('prewrite', **{field: '0' * 64}))


def test_preflight_work_item_drift_fails():
    _fails('prewrite_all_work_item_count_unchanged',
           prewrite_state=_state('prewrite', all_work_item_count=11))


def test_a_prewrite_state_that_was_not_read_only_fails():
    _fails('prewrite_state_read_only',
           prewrite_state=_state('prewrite',
                                 read_only={'write_probe_refused': False}))


# ═══════════════ Replay ═════════════════════════════════════════════════════


def _replay(**overrides):
    base = _shadow(games=[
        _game(pk, i, attempt=2) for i, pk in enumerate(APPROVED_ORDER)
    ])
    base.update(overrides)
    return base


def test_a_replay_game_failure_fails():
    _fails('replay_games_failed', replay=_replay(games_failed=1))


def test_a_replay_row_mismatch_fails():
    _fails('replay_rows_unchanged', replay=_replay(rows_unchanged=864))


def test_a_replay_gamelog_mutation_fails():
    _fails('replay_rows_updated', replay=_replay(rows_updated=1))


def test_a_replay_identity_mutation_fails():
    _fails('replay_pitcher_identity_mutations',
           replay=_replay(pitcher_identity_mutations=1))


def test_a_replay_appearance_team_mutation_fails():
    _fails('replay_appearance_team_mutations',
           replay=_replay(appearance_team_mutations=1))


def test_a_replay_innings_correction_fails():
    _fails('replay_canonical_outs_corrections',
           replay=_replay(canonical_outs_corrections=1))


def test_a_replay_ignored_total_mismatch_fails():
    _fails('replay_derived_companion_differences_ignored',
           replay=_replay(derived_companion_differences_ignored=290))


def test_a_replay_fingerprint_mismatch_fails():
    _fails('replay_fingerprint_matches_the_approved_plan',
           replay=_replay(complete_reconciliation_fingerprint='a' * 64))


# ═══════════════ Replay caused no drift ═════════════════════════════════════


@pytest.mark.parametrize('field', list(validator.IMMUTABLE_STATE_HASHES))
def test_replay_drift_fails(field):
    _fails(f'final_{field}_unchanged',
           final_state=_state('final', after=True, **{field: '0' * 64}))


def test_replay_control_state_drift_fails():
    _fails('final_all_work_item_count_unchanged',
           final_state=_state('final', after=True, all_work_item_count=110))


def test_a_replay_created_work_item_fails():
    final = _state('final', after=True)
    final['selected_work_items'][str(APPROVED_SET[0])]['attempt_count'] = 2
    _fails('final_selected_work_items_unchanged', final_state=final)


def test_a_final_state_that_was_not_read_only_fails():
    _fails('final_state_read_only',
           final_state=_state('final', after=True,
                              read_only={'write_probe_refused': False}))


# ═══════════════ Closeout package ═══════════════════════════════════════════


def _package(decision=None):
    decision = decision or _closeout()
    return validator.build_closeout(
        decision, repository_sha='abc123', run_id='42',
        before=_state('before'), prewrite=_state('prewrite'),
        after_write=_state('after_write', after=True),
        final=_state('final', after=True),
    )


def test_the_closeout_contains_the_exact_109_completed_set():
    package = _package()
    complete = sorted(
        set(package['completed_game_pks_before_r6'])
        | set(package['unresolved_game_pks_sorted'])
    )
    assert len(complete) == 109
    assert package['completed_final_games_after'] == 109


def test_the_closeout_unresolved_set_is_empty():
    package = _package()
    assert package['write_unresolved_subset'] == []
    assert package['unresolved_final_games_after'] == 0


def test_the_closeout_is_deterministic():
    first = json.dumps(_package(), sort_keys=True)
    second = json.dumps(_package(), sort_keys=True)
    assert first == second


def test_the_closeout_records_the_transaction_boundary():
    package = _package()
    assert 'per_game' in package['transaction_boundary']
    assert 'atomicity does not exist' in package['transaction_boundary']


def test_the_closeout_keeps_the_lane_off_and_stage_e_unimplemented():
    package = _package()
    assert package['automated_lane'] == 'off'
    assert package['authoritative_mode'] == 'unapproved'
    assert package['stage_e'] == 'not_implemented'


def test_the_closeout_contains_no_credential_shaped_text():
    text = json.dumps(_package())
    for token in ('postgres://', 'postgresql://', 'password=', 'SECRET_KEY',
                  'DATABASE_URL', 'ADMIN_API_TOKEN'):
        assert token not in text


def test_the_closeout_records_the_reconciled_appearance_ledger():
    package = _package()
    assert package['reconciled_appearance_rows'] == 946


# ═══════════════ Summary wording ════════════════════════════════════════════


def _summary_text():
    decision = _closeout()
    closeout = _package(decision)
    return validator.pass_markdown(
        validator.build_summary(decision, closeout), closeout
    )


def test_the_pass_summary_acknowledges_control_state_writes():
    decision = _closeout()
    summary = validator.build_summary(decision, _package(decision))
    assert '99 work items created and completed' in summary['database_writes']


def test_the_pass_summary_never_claims_no_database_writes():
    text = _summary_text()
    assert 'No database writes were performed' not in text
    assert 'Only governed ingestion control state changed.' in text


def test_the_pass_summary_says_no_baseball_data_changed():
    text = _summary_text()
    assert 'No baseball-data rows changed.' in text
    assert 'GameLog data changed: no' in text
    assert 'Canonical outs changed: no' in text


def test_the_pass_summary_states_109_and_zero():
    text = _summary_text()
    assert 'Completed final games after: 109' in text
    assert 'Unresolved final games after: 0' in text
    assert 'Publication complete: yes' in text


def test_the_pass_summary_keeps_the_lane_off():
    text = _summary_text()
    assert 'GAME_DRIVEN_INGESTION_MODE remains off.' in text
    assert 'Authoritative mode remains unapproved.' in text


def test_the_pass_summary_directs_the_rollout_to_stage_e():
    text = _summary_text()
    assert 'Stage E rollout closeout' in text


def test_the_failed_summary_names_the_phase_and_invariant():
    with pytest.raises(validator.ValidationFailure) as caught:
        _closeout(write=_write_report(games_failed=1))
    summary = validator.failed_summary(caught.value)
    assert summary['result'] == validator.RESULT_FAILED
    assert summary['failed_phase'] == 'write'
    assert summary['failed_invariant'] == 'write_games_failed'
    text = validator.failed_markdown(summary)
    assert 'FOUNDATION 3C R6 — FAILED' in text
    assert 'rollout stop' in text
    assert 'must not be compensated or deleted' in text


def test_the_failed_summary_reports_the_partial_subsets():
    report = _write_report()
    report['games'] = [
        {'game_pk': pk, 'status': GameIngestionWorkItem.STATUS_COMPLETED}
        for pk in APPROVED_ORDER[:49]
    ]
    partial = validator.summarize_partial_write(report, write_exit=1)
    with pytest.raises(validator.ValidationFailure) as caught:
        _closeout(write=report)
    summary = validator.failed_summary(caught.value, partial)
    assert summary['completed_subset_count'] == 49
    assert summary['unresolved_subset_count'] == 50
    assert summary['partial_completion'] is True
    assert summary['sanitized'] is True


# ═══════════════ CLI ════════════════════════════════════════════════════════


def _cli_closeout(tmp_path, *, write_exit=0, **overrides):
    payloads = {
        'before.json': _state('before'),
        'preflight.json': _shadow(),
        'prewrite.json': _state('prewrite'),
        'write.json': _write_report(),
        'after.json': _state('after_write', after=True),
        'replay.json': _replay(),
        'final.json': _state('final', after=True),
    }
    payloads.update(overrides)
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload))
    return validator.main([
        'closeout',
        '--before-state', str(tmp_path / 'before.json'),
        '--preflight', str(tmp_path / 'preflight.json'),
        '--prewrite-state', str(tmp_path / 'prewrite.json'),
        '--write', str(tmp_path / 'write.json'),
        '--after-write-state', str(tmp_path / 'after.json'),
        '--replay', str(tmp_path / 'replay.json'),
        '--final-state', str(tmp_path / 'final.json'),
        '--write-exit', str(write_exit),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--closeout-json', str(tmp_path / 'closeout.json'),
        '--closeout-markdown', str(tmp_path / 'closeout.md'),
        '--repository-sha', 'abc123', '--run-id', '42',
    ])


def test_the_closeout_cli_exits_zero_and_writes_every_artifact(tmp_path):
    assert _cli_closeout(tmp_path) == 0
    for name in ('summary.json', 'summary.md', 'closeout.json', 'closeout.md'):
        assert (tmp_path / name).is_file(), name
    assert json.loads((tmp_path / 'summary.json').read_text())['result'] == 'pass'


def test_a_failed_result_cannot_exit_zero(tmp_path):
    assert _cli_closeout(tmp_path, write_exit=1) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['automated_lane'] == 'off'


def test_the_closeout_cli_output_is_deterministic(tmp_path):
    first, second = tmp_path / 'a', tmp_path / 'b'
    first.mkdir()
    second.mkdir()
    assert _cli_closeout(first) == 0
    assert _cli_closeout(second) == 0
    for name in ('summary.json', 'closeout.json', 'closeout.md', 'summary.md'):
        assert (first / name).read_text() == (second / name).read_text(), name


def test_the_preflight_cli_authorizes_and_refuses(tmp_path):
    (tmp_path / 'before.json').write_text(json.dumps(_state('before')))
    (tmp_path / 'preflight.json').write_text(json.dumps(_shadow()))
    (tmp_path / 'prewrite.json').write_text(json.dumps(_state('prewrite')))
    argv = [
        'preflight',
        '--before-state', str(tmp_path / 'before.json'),
        '--preflight', str(tmp_path / 'preflight.json'),
        '--prewrite-state', str(tmp_path / 'prewrite.json'),
    ]
    assert validator.main(argv) == 0
    (tmp_path / 'preflight.json').write_text(
        json.dumps(_shadow(complete_reconciliation_fingerprint='c' * 64))
    )
    assert validator.main(argv) == 1


def test_a_missing_artifact_fails_closed(tmp_path):
    for name, payload in (
        ('preflight.json', _shadow()), ('prewrite.json', _state('prewrite')),
    ):
        (tmp_path / name).write_text(json.dumps(payload))
    assert validator.main([
        'preflight',
        '--before-state', str(tmp_path / 'absent.json'),
        '--preflight', str(tmp_path / 'preflight.json'),
        '--prewrite-state', str(tmp_path / 'prewrite.json'),
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
    """Start times that make the planner reproduce the reviewed order.

    With one shared start time the planner falls through to game_pk ascending,
    which is NOT the order production produced — a fixture like that would test
    the ordering assertion against nothing.
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


# The ten completed games carry 81 rows in total (38 original + 43 R4), so the
# durable ledger reaches 81 + 865 = 946 after R6.
COMPLETED_ROWS = {
    823518: 8, 824735: 8, 823761: 8, 824083: 7, 824327: 7,   # 38
    823110: 6, 825055: 8, 824004: 9, 823438: 10, 824408: 10,  # 43
}


def test_the_completed_ten_carry_the_documented_row_totals():
    assert sum(COMPLETED_ROWS.values()) == 81
    assert sum(COMPLETED_ROWS.values()) + TOTAL_ROWS == 946


def _build_full_window(game_pks=APPROVED_ORDER):
    """Production shape: 109 scheduled games, 10 completed, 99 open."""
    boxscores = {}

    for game_pk, rows in sorted(COMPLETED_ROWS.items()):
        _schedule(game_pk)
        for index in range(rows):
            arm = _pitcher(game_pk * 100 + index, team_id=HOME_TEAM, active=True)
            db.session.flush()
            _stored_row(arm, game_pk)
    db.session.commit()
    for game_pk, rows in sorted(COMPLETED_ROWS.items()):
        db.session.add(_completed_work_item(game_pk, rows))
    db.session.commit()

    canonical_index = {pk: i for i, pk in enumerate(APPROVED_ORDER)}
    for game_pk in game_pks:
        _schedule_in_canonical_position(
            game_pk, canonical_index.get(game_pk, 900),
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
    return boxscores


def _run(mode, **kwargs):
    return game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=mode, only_game_pks=list(APPROVED_ORDER), **kwargs
    )


def test_the_real_99_game_write_changes_only_control_state(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_full_window()),
        )
        from scripts import inspect_r6_full_write_state as inspector

        before = inspector.collect_state()
        assert before['publication_completeness']['completed_final_games'] == 10
        assert before['publication_completeness']['unresolved_final_games'] == 99
        assert before['all_work_item_count'] == 10
        assert before['selected_work_items'] == {}

        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        assert preflight['games_completed'] == 99
        assert preflight['rows_unchanged'] == 865
        assert preflight['derived_companion_differences_ignored'] == 291
        assert preflight['complete_mutation_count'] == 0
        reviewed = preflight['complete_reconciliation_fingerprint']

        prewrite = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert prewrite[field] == before[field], field
        assert prewrite['all_work_item_count'] == 10

        write = _run(
            game_driven_ingestion.MODE_WRITE, expected_plan_fingerprint=reviewed,
        )
        assert write['status'] == 'complete'
        assert write['games_completed'] == 99
        assert write['games_failed'] == 0
        assert write['rows_inserted'] == 0
        assert write['rows_updated'] == 0
        assert write['complete_mutation_count'] == 0
        assert write['authorized_plan_fingerprint'] == reviewed

        after = inspector.collect_state()
        # Baseball data byte-identical; control state advanced by exactly 99.
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['all_work_item_count'] == 109
        assert after['selected_work_item_count'] == 99
        assert after['selected_completed_set'] == list(APPROVED_SET)
        assert after['selected_unresolved_set'] == []
        assert after['duplicate_selected_game_pks'] == []
        assert after['dead_letter_count'] == 0

        completeness = after['publication_completeness']
        assert completeness['completed_final_games'] == 109
        assert completeness['unresolved_final_games'] == 0
        assert completeness['expected_final_games'] == 109
        assert completeness['publication_complete'] is True
        assert completeness['critical_appearance_rows_reconciled'] == 946

        replay = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        assert replay['games_completed'] == 99
        assert replay['rows_unchanged'] == 865
        assert replay['derived_companion_differences_ignored'] == 291
        assert replay['complete_mutation_count'] == 0
        assert replay['complete_reconciliation_fingerprint'] == reviewed

        final = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert final[field] == after[field], field
        assert final['all_work_item_count'] == 109


def test_a_one_character_fingerprint_difference_refuses_the_write(
    app, monkeypatch,
):
    """Scenario A: no work item created, every table unchanged."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_full_window()),
        )
        from scripts import inspect_r6_full_write_state as inspector

        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        reviewed = preflight['complete_reconciliation_fingerprint']
        before = inspector.collect_state()

        tampered = ('0' if reviewed[0] != '0' else '1') + reviewed[1:]
        write = _run(
            game_driven_ingestion.MODE_WRITE, expected_plan_fingerprint=tampered,
        )
        db.session.rollback()

        assert write['status'] == 'plan_fingerprint_mismatch'
        after = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['all_work_item_count'] == 10
        assert after['selected_work_items'] == {}


@pytest.mark.parametrize('rejected_name', [
    'STALE_CONTRACT_3_FINGERPRINT', 'R4_FIVE_GAME_FINGERPRINT', 'SCOPE_DIGEST',
])
def test_a_rejected_value_refuses_the_write(app, monkeypatch, rejected_name):
    """Scenarios B, C, D: contract-3, the R4 value, and the scope digest."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_full_window()),
        )
        from scripts import inspect_r6_full_write_state as inspector

        before = inspector.collect_state()
        write = _run(
            game_driven_ingestion.MODE_WRITE,
            expected_plan_fingerprint=getattr(validator, rejected_name),
        )
        db.session.rollback()

        assert write['status'] == 'plan_fingerprint_mismatch'
        after = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['all_work_item_count'] == 10
        assert after['selected_work_items'] == {}


def test_an_identity_creation_changes_the_fingerprint_and_refuses(
    app, monkeypatch,
):
    """Scenario E: the plan moved after review, so the write refuses."""
    with app.app_context():
        boxscores = _build_full_window()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        from scripts import inspect_r6_full_write_state as inspector

        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        reviewed = preflight['complete_reconciliation_fingerprint']
        before = inspector.collect_state()

        target = APPROVED_ORDER[0]
        lines = [
            (target * 100 + index + 1, 'home', pitching_stats())
            for index in range(ROWS_BY_GAME[target])
        ]
        lines.append((7777777, 'home', pitching_stats()))
        boxscores[target] = boxscore(lines)
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        moved = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        assert moved['pitcher_identity_creations'] >= 1
        assert moved['complete_reconciliation_fingerprint'] != reviewed

        write = _run(
            game_driven_ingestion.MODE_WRITE, expected_plan_fingerprint=reviewed,
        )
        db.session.rollback()
        assert write['status'] == 'plan_fingerprint_mismatch'

        after = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['all_work_item_count'] == 10


def test_a_changed_source_line_refuses_the_write(app, monkeypatch):
    """Scenario F: the official line moved after review."""
    with app.app_context():
        boxscores = _build_full_window()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        from scripts import inspect_r6_full_write_state as inspector

        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        reviewed = preflight['complete_reconciliation_fingerprint']
        before = inspector.collect_state()

        target = APPROVED_ORDER[0]
        drifted = IGNORED_BY_GAME[target]
        lines = []
        for index in range(ROWS_BY_GAME[target]):
            mlb_id = target * 100 + index + 1
            if index == ROWS_BY_GAME[target] - 1:
                # A genuinely different official line for one appearance.
                lines.append((mlb_id, 'home', pitching_stats(
                    innings='2.0', hits=4, strikeouts=5, batters_faced=9,
                    strikes=20, pitches=30,
                )))
            elif index < drifted:
                lines.append((mlb_id, 'home', pitching_stats(
                    innings='0.1', hits=0, strikeouts=1, batters_faced=1,
                    strikes=3, pitches=4,
                )))
            else:
                lines.append((mlb_id, 'home', pitching_stats()))
        boxscores[target] = boxscore(lines)
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        moved = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        assert moved['complete_reconciliation_fingerprint'] != reviewed

        write = _run(
            game_driven_ingestion.MODE_WRITE, expected_plan_fingerprint=reviewed,
        )
        db.session.rollback()
        assert write['status'] == 'plan_fingerprint_mismatch'

        after = inspector.collect_state()
        for field in validator.IMMUTABLE_STATE_HASHES:
            assert after[field] == before[field], field
        assert after['all_work_item_count'] == 10


def test_a_selected_game_completed_before_dispatch_stops_the_run(
    app, monkeypatch,
):
    """Scenario G: the before-state fails and the write never runs."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_full_window()),
        )
        from scripts import inspect_r6_full_write_state as inspector

        intruder = APPROVED_ORDER[0]
        db.session.add(_completed_work_item(intruder, ROWS_BY_GAME[intruder]))
        db.session.commit()

        before = inspector.collect_state()
        assert str(intruder) in before['selected_work_items']
        state = {**before, 'phase': 'before',
                 'read_only': {'write_probe_refused': True}}
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_before_state(state)
        assert caught.value.invariant.startswith('before_state_')

        # Hold completeness at 10/99 so the work-item guard is what fires.
        held = {
            **state,
            'publication_completeness': {
                **state['publication_completeness'],
                'completed_final_games': 10, 'unresolved_final_games': 99,
            },
            'completed_work_item_set': list(COMPLETED),
            'unresolved_set': list(APPROVED_SET),
            'all_work_item_count': 10,
        }
        with pytest.raises(validator.ValidationFailure) as second:
            validator.validate_before_state(held)
        assert 'have_no_work_item' in second.value.invariant


def test_a_failure_partway_leaves_earlier_commits_durable(app, monkeypatch):
    """Scenario H: the real per-game transaction boundary, observed."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_full_window()),
        )
        from scripts import inspect_r6_full_write_state as inspector

        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        reviewed = preflight['complete_reconciliation_fingerprint']

        real_process = game_driven_ingestion._process_one_game
        state = {'calls': 0}

        def failing(item, **kwargs):
            state['calls'] += 1
            if state['calls'] == 50:
                raise RuntimeError('injected failure at game 50')
            return real_process(item, **kwargs)

        monkeypatch.setattr(
            game_driven_ingestion, '_process_one_game', failing,
        )
        with pytest.raises(RuntimeError):
            _run(
                game_driven_ingestion.MODE_WRITE,
                expected_plan_fingerprint=reviewed,
            )
        db.session.rollback()

        after = inspector.collect_state()
        # 49 games committed before the failure. Durable, and NOT compensated.
        assert after['selected_work_item_count'] == 49
        assert len(after['selected_completed_set']) == 49
        assert after['all_work_item_count'] == 59
        assert after['publication_completeness']['publication_complete'] is False

        # The validator must refuse this state rather than call it a success.
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_control_state(
                {**after, 'all_work_item_count': 10}, {**after,
                                                       'phase': 'after_write'},
            )
        assert caught.value.invariant.startswith('after_write_')


def test_a_write_during_the_replay_is_caught_by_the_final_state(
    app, monkeypatch,
):
    """Scenario I: drift between after-write and final is detected."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(_build_full_window()),
        )
        from scripts import inspect_r6_full_write_state as inspector

        preflight = _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()
        reviewed = preflight['complete_reconciliation_fingerprint']
        _run(
            game_driven_ingestion.MODE_WRITE,
            expected_plan_fingerprint=reviewed,
        )
        after = inspector.collect_state()

        _run(game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()

        # Simulate an unrelated write landing during the replay.
        target = APPROVED_ORDER[0]
        row = GameLog.query.filter(GameLog.mlb_game_pk == target).first()
        row.earned_runs = (row.earned_runs or 0) + 1
        db.session.commit()

        final = inspector.collect_state()
        assert final['game_log_content_hash'] != after['game_log_content_hash']
        with pytest.raises(validator.ValidationFailure) as caught:
            validator.validate_no_drift(
                after,
                {**final, 'phase': 'final',
                 'read_only': {'write_probe_refused': True}},
                phase='final',
            )
        assert 'game_log_content_hash_unchanged' in caught.value.invariant
