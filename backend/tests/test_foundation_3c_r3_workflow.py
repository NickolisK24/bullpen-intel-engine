"""Foundation 3C — the manual R3 controlled-sample shadow review.

R3 is the last read-only gate before a controlled write is proposed. It runs
exactly five hard-coded games, proves they are still the next unresolved
sample, proves zero mutations across GameLog, pitcher identity, and
appearance-team authority, and captures the complete reconciliation fingerprint
a later R4 write would have to match.

There is no `review_required` here. This sample is expected to be clean, and
any projected mutation means it is not eligible for the controlled write. PASS
produces a reviewed package; it authorizes nothing.

The parser import lives inside the fixture that needs it. PyYAML is a declared
dependency, so a missing parser is a defect — but it must not abort collection
of the whole suite, and it must not silently skip these guards either.
"""

import hashlib
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
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from scripts import validate_r3_shadow_report as validator
from services import appearance_team_authority
from services import game_driven_ingestion
from services import game_ingestion_completeness
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
    / 'foundation-3c-r3-controlled-sample-shadow.yml'
)
APPROVED_GAME_PKS = (823110, 825055, 824004, 823438, 824408)


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


# ═══════════════ 0. Parser-independent guards ═══════════════════════════════


PINNED_INGESTION_COMMAND = (
    'python backend/scripts/game_driven_ingestion.py '
    '--mode shadow --reference-date 2026-07-29 '
    '--only-game-pk 823110 --only-game-pk 825055 --only-game-pk 824004 '
    '--only-game-pk 823438 --only-game-pk 824408 '
    '--output "$REPORT_PATH"'
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
    '--max-games', '--include-backfill', '--time-budget-seconds', '--plan-only',
])
def test_no_write_widening_or_narrowing_option_appears_in_the_file(
    workflow_text, forbidden,
):
    assert forbidden not in workflow_text


def test_the_automated_lane_is_off_in_the_file(workflow_text):
    assert "GAME_DRIVEN_INGESTION_MODE: 'off'" in workflow_text
    assert "AUTO_SYNC: 'false'" in workflow_text


# ═══════════════ 1-3. Trigger, inputs, permissions ══════════════════════════


def test_the_workflow_parses(workflow):
    assert workflow['name'] == 'Foundation 3C R3 Controlled Sample Shadow'


def test_the_only_trigger_is_manual_dispatch(workflow):
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}


@pytest.mark.parametrize('forbidden', ['schedule', 'push', 'pull_request',
                                       'workflow_call', 'repository_dispatch'])
def test_no_automatic_trigger_exists(workflow, forbidden):
    triggers = workflow.get('on', workflow.get(True))
    assert forbidden not in triggers


def test_there_are_no_editable_inputs(workflow):
    triggers = workflow.get('on', workflow.get(True))
    assert not (triggers.get('workflow_dispatch') or {})


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


@pytest.mark.parametrize('scope', [
    'actions', 'checks', 'statuses', 'pull-requests', 'issues', 'deployments',
    'packages', 'id-token',
])
def test_no_additional_permission_is_requested(workflow, scope):
    assert scope not in workflow['permissions']


def test_no_write_permission_appears_anywhere(workflow_text):
    block = workflow_text.split('permissions:')[1].split('jobs:')[0]
    assert 'write' not in block


# ═══════════════ 4-12. The command is pinned ════════════════════════════════


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


def test_the_command_requests_exactly_the_five_approved_games(ingestion_command):
    assert ingestion_command.count('--only-game-pk') == 5
    requested = [int(part) for part in ingestion_command.split() if part.isdigit()]
    assert sorted(requested) == sorted(APPROVED_GAME_PKS)
    for game_pk in APPROVED_GAME_PKS:
        assert ingestion_command.count(str(game_pk)) == 1


def test_the_command_uses_exclusive_scope_not_additive(ingestion_command):
    assert '--game-pk ' not in ingestion_command.replace('--only-game-pk ', '')


@pytest.mark.parametrize('forbidden', [
    '--max-games', '--include-backfill', '--expected-plan-fingerprint',
    '--mode write', '--mode authoritative',
])
def test_the_command_carries_no_widening_or_write_option(
    ingestion_command, forbidden,
):
    assert forbidden not in ingestion_command


def test_the_command_flag_set_is_exactly_the_approved_shape(ingestion_command):
    tokens = [t for t in ingestion_command.split() if t.startswith('--')]
    assert tokens == (
        ['--mode', '--reference-date'] + ['--only-game-pk'] * 5 + ['--output']
    )


# ═══════════════ 13-16. Lane, secrets, no side effects ══════════════════════


def test_the_automated_lane_is_explicitly_off(job):
    assert job['env']['GAME_DRIVEN_INGESTION_MODE'] == 'off'
    assert job['env']['AUTO_SYNC'] == 'false'
    assert job['env']['APP_ENV'] == 'production'


def test_the_workflow_uses_the_established_production_secrets(job):
    env = job['env']
    assert env['DATABASE_URL'] == '${{ secrets.DATABASE_URL }}'
    assert env['SECRET_KEY'] == '${{ secrets.SECRET_KEY }}'
    assert env['ADMIN_API_TOKEN'] == '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'


def test_the_workflow_fails_when_a_secret_is_absent(run_commands):
    assert [line for line in run_commands if 'Missing required production' in line]


def test_no_secret_value_is_echoed(run_commands):
    for line in run_commands:
        if line.startswith('echo') and '$' in line:
            assert 'DATABASE_URL' not in line
            assert 'SECRET_KEY' not in line
            assert 'ADMIN_API_TOKEN' not in line


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
        'backend/scripts/validate_r3_shadow_report.py',
    }


# ═══════════════ 17-24. Bounds and step order ═══════════════════════════════


def test_the_job_is_bounded_and_serialized(workflow, job):
    assert isinstance(job['timeout-minutes'], int)
    assert 0 < job['timeout-minutes'] <= 30
    assert workflow['concurrency']['group'] == (
        'foundation-3c-r3-controlled-sample-shadow'
    )
    assert workflow['concurrency']['cancel-in-progress'] is False


@pytest.mark.parametrize('other', [
    'foundation-3c-r1-shadow-validation',
    'foundation-3c-r2-full-window-shadow',
])
def test_the_concurrency_group_is_distinct(workflow, other):
    assert workflow['concurrency']['group'] != other


def test_validation_runs_always_and_after_the_shadow_step(job):
    steps = job['steps']
    shadow = next(i for i, s in enumerate(steps) if s.get('id') == 'shadow')
    validate = next(i for i, s in enumerate(steps) if s.get('id') == 'validate')
    assert shadow < validate
    assert steps[validate]['if'] == '${{ always() }}'


def test_the_credential_scan_runs_before_the_upload(job):
    steps = job['steps']
    scan = next(i for i, s in enumerate(steps)
                if 'credential-shaped' in (s.get('name') or ''))
    upload = next(i for i, s in enumerate(steps)
                  if str(s.get('uses') or '').startswith('actions/upload-artifact'))
    assert scan < upload
    assert steps[scan]['if'] == '${{ always() }}'


def test_the_final_gate_runs_after_the_upload(job):
    steps = job['steps']
    upload = next(i for i, s in enumerate(steps)
                  if str(s.get('uses') or '').startswith('actions/upload-artifact'))
    gate = len(steps) - 1
    assert upload < gate
    assert steps[gate]['if'] == '${{ always() }}'
    assert 'R4 remains blocked' in steps[gate]['run']


def test_the_step_order_matches_the_approved_sequence(job):
    names = [
        (step.get('name') or step.get('uses') or '').lower()
        for step in job['steps']
    ]
    assert 'checkout' in names[0]
    assert 'setup-python' in names[1]
    assert 'install' in names[2]
    assert 'secret' in names[3]
    assert 'artifacts directory' in names[4]
    assert 'shadow reconciliation' in names[5]
    assert 'validate' in names[6]
    assert 'credential-shaped' in names[7]
    assert 'job summary' in names[8]
    assert 'upload' in names[9]
    assert names[10].startswith('fail the job')


def test_artifacts_upload_even_when_the_run_fails(job):
    upload = next(step for step in job['steps']
                  if str(step.get('uses') or '').startswith('actions/upload-artifact'))
    assert upload['if'] == '${{ always() }}'
    assert upload['with']['name'] == 'foundation-3c-r3-controlled-sample-shadow'
    assert upload['with']['retention-days'] == 14
    assert upload['with']['if-no-files-found'] == 'warn'


@pytest.mark.parametrize('artifact', [
    'r3-controlled-five-shadow.json',
    'r3-validation-summary.json',
    'r3-validation-summary.md',
    'r3-reviewed-authorization.json',
    'r3-reviewed-authorization.md',
])
def test_every_required_artifact_is_produced(job, artifact):
    assert any(artifact in str(value) for value in job['env'].values())


def test_a_failed_validation_cannot_produce_a_successful_job(run_commands):
    assert [line for line in run_commands if 'VALIDATION_EXIT' in line]
    assert any('exit 1' in line for line in run_commands)


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


# ═══════════════ 25. The inline credential scanner ══════════════════════════


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
    (artifacts / 'r3-reviewed-authorization.json').write_text(json.dumps({
        'result': 'pass', 'write_approved': False, 'database_writes': 'none',
        'complete_reconciliation_fingerprint': 'a' * 64,
    }))
    assert _run_scanner(workflow_text, tmp_path, monkeypatch) == 0
    assert (artifacts / 'r3-reviewed-authorization.json').exists()


@pytest.mark.parametrize('poison', [
    'postgresql://user:pw@host/db', 'password=hunter2',
    'X-Admin-Token: abc', 'api_key=abc123',
])
def test_the_scanner_deletes_and_fails_on_credential_content(
    workflow_text, tmp_path, monkeypatch, poison,
):
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    unsafe = artifacts / 'r3-validation-summary.json'
    unsafe.write_text(poison)
    assert _run_scanner(workflow_text, tmp_path, monkeypatch) == 1
    assert not unsafe.exists()


# ═══════════════ Report builders ════════════════════════════════════════════


def _fingerprint(seed):
    return hashlib.sha256(str(seed).encode()).hexdigest()


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
        'pitcher_identity_status': 'resolved',
        'pitcher_identity_changed_fields': [],
        'pitcher_identity_applied_fields': [],
        'pitcher_identity_suppressed_fields': sorted(suppressed),
        'pitcher_identity_governed_and_safe': True,
        'pitcher_identity_blocked_reason': None,
        'pitcher_identity_mutation_digest': '',
        'pitcher_identity_requires_creation': False,
        'pitcher_identity_current_authority_mutation_refused': bool(suppressed),
    }


def _game(game_pk):
    rows_expected = validator.EXPECTED_ROWS_BY_GAME[game_pk]
    ignored_expected = validator.EXPECTED_IGNORED_BY_GAME[game_pk]
    rows = [
        _row(
            game_pk, game_pk * 10 + index,
            ignored=1 if index < ignored_expected else 0,
            # Half the sample carries a historical/current difference, which is
            # exactly the D-009 evidence that must stay a non-mutation.
            suppressed=['team_id'] if index % 2 == 0 else (),
        )
        for index in range(rows_expected)
    ]
    return {
        'game_pk': game_pk,
        'represented_date': '2026-07-28',
        'candidate_reason': validator.EXPECTED_CANDIDATE_REASON,
        'criticality': validator.EXPECTED_CRITICALITY,
        'attempt_number': 1,
        'status': 'projected',
        'source_revision': f'rev{game_pk}',
        'appearances_extracted': rows_expected,
        'relief_appearances': rows_expected - 1,
        'inserted': 0,
        'updated': 0,
        'unchanged': rows_expected,
        'blocked': 0,
        'changed_fields_counts': {},
        'mutation_category_counts': {'unchanged_row': rows_expected},
        'statistical_corrections': 0,
        'authority_reconciliations': 0,
        'provenance_only_updates': 0,
        'canonical_outs_corrections': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': ignored_expected,
        'pitcher_identity_rows_examined': rows_expected,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_unchanged': rows_expected,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_action_counts': {
            identity.ACTION_UNCHANGED: rows_expected,
        },
        'pitcher_identity_changed_fields_counts': {},
        'suppressed_current_state_field_counts': {},
        'pitcher_identity_unique_pitchers_affected': 0,
        'historical_current_state_changes_suppressed': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'reconciliation_plan_fingerprint': _fingerprint(game_pk),
        'complete_reconciliation_fingerprint': _fingerprint(game_pk),
        'rows': rows,
        'elapsed_seconds': 0.4,
        'error_class': None,
    }


def clean_report():
    games = [_game(game_pk) for game_pk in APPROVED_GAME_PKS]
    approved = sorted(APPROVED_GAME_PKS)
    return {
        'status': 'complete',
        'mode': 'shadow',
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
        'games_discovered': 109,
        'games_planned': 5,
        'retry_count': 0,
        'corrected_final_count': 0,
        'newly_final_count': 0,
        'games_attempted': 5,
        'games_fetched': 5,
        'games_completed': 5,
        'games_failed': 0,
        'games_remaining': 0,
        'critical_games_unresolved': 0,
        'schedule_authority_missing': 0,
        'finality_conflicts': 0,
        'budget_stop_triggered': False,
        'budget_stop': None,
        'failure_classes': {},
        'rows_expected': 43,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': 43,
        'rows_blocked': 0,
        'changed_fields_counts': {},
        'mutation_category_counts': {'unchanged_row': 43},
        'statistical_corrections': 0,
        'authority_reconciliations': 0,
        'provenance_only_updates': 0,
        'canonical_outs_corrections': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': 18,
        'decimal_only_updates_suppressed': 18,
        'pitcher_identity_rows_examined': 43,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_unchanged': 43,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_action_counts': {identity.ACTION_UNCHANGED: 43},
        'pitcher_identity_changed_fields_counts': {},
        'suppressed_current_state_field_counts': {},
        'pitcher_identity_unique_pitchers_affected': 0,
        'historical_current_state_changes_suppressed': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'reconciliation_plan_version': reconciliation.RECONCILIATION_PLAN_VERSION,
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        'reconciliation_plan_fingerprint': _fingerprint('run'),
        'complete_reconciliation_fingerprint': _fingerprint('run'),
        'games': games,
        'publication_completeness': {
            'represented_date': '2026-07-29',
            'expected_final_games': 109,
            'completed_final_games': 5,
            'unresolved_final_games': 104,
            'correction_pending_games': 0,
            'terminal_failure_games': 0,
            'critical_appearance_rows_expected': 38,
            'critical_appearance_rows_reconciled': 38,
            'finality_conflicts': 0,
            'schedule_authority_missing': 0,
            'publication_complete': False,
            'decision_reasons': ['unresolved_final_games'],
        },
    }


def _failure(report):
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    return caught.value


# ═══════════════ 1. The clean sample ════════════════════════════════════════


def test_the_expected_production_shape_passes():
    result = validator.validate(clean_report())
    summary = result['summary']
    assert summary['result'] == validator.RESULT_PASS
    assert summary['rows_expected'] == 43
    assert summary['rows_unchanged'] == 43
    assert summary['derived_companion_differences_ignored'] == 18
    assert summary['complete_mutation_count'] == 0
    assert summary['write_approved'] is False
    assert summary['r4_status'] == 'blocked_pending_founder_review'
    assert len(result['games']) == 5


def test_the_expected_totals_match_the_reviewed_sample():
    assert validator.EXPECTED_TOTAL_ROWS == 43
    assert validator.EXPECTED_TOTAL_IGNORED == 18
    assert sorted(validator.APPROVED_GAME_PKS) == sorted(APPROVED_GAME_PKS)


# ═══════════════ 2-8. Scope ═════════════════════════════════════════════════


def test_a_wrong_requested_set_fails():
    report = clean_report()
    report['requested_game_pks'] = [1, 2, 3, 4, 5]
    assert _failure(report).invariant == 'requested_game_pks'


def test_a_wrong_planned_set_fails():
    report = clean_report()
    report['planned_game_pks'] = [1, 2, 3, 4, 5]
    assert _failure(report).invariant == 'planned_game_pks'


def test_an_extra_game_fails():
    report = clean_report()
    report['unexpected_planned_game_pks'] = [999999]
    assert _failure(report).invariant == 'unexpected_planned_game_pks'


def test_a_missing_game_fails():
    report = clean_report()
    report['missing_requested_game_pks'] = [823110]
    assert _failure(report).invariant == 'missing_requested_game_pks'


def test_a_duplicate_requested_game_fails():
    report = clean_report()
    report['duplicate_requested_count'] = 1
    assert _failure(report).invariant == 'duplicate_requested_count'


def test_a_non_exclusive_scope_fails():
    report = clean_report()
    report['execution_scope_mode'] = 'window'
    assert _failure(report).invariant == 'execution_scope_mode'


def test_a_false_exact_match_fails():
    report = clean_report()
    report['execution_scope_exact_match'] = False
    assert _failure(report).invariant == 'execution_scope_exact_match'


def test_an_unordered_plan_fails():
    report = clean_report()
    report['planned_game_pks'] = list(reversed(sorted(APPROVED_GAME_PKS)))
    assert _failure(report).invariant == 'planned_game_pks_are_canonically_ordered'


# ═══════════════ 9-13. Sample eligibility ═══════════════════════════════════


@pytest.mark.parametrize('reason', validator.FORBIDDEN_CANDIDATE_REASONS)
def test_a_game_that_is_not_newly_final_fails(reason):
    report = clean_report()
    report['games'][0]['candidate_reason'] = reason
    failure = _failure(report)
    assert 'candidate_reason' in failure.invariant


def test_a_second_attempt_fails():
    """A completed checkpoint before this run would show as attempt 2."""
    report = clean_report()
    report['games'][0]['attempt_number'] = 2
    assert _failure(report).invariant == 'game_823110_attempt_number'


def test_a_best_effort_game_fails():
    report = clean_report()
    report['games'][0]['criticality'] = (
        GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    )
    assert _failure(report).invariant == 'game_823110_criticality'


@pytest.mark.parametrize('field,value', [
    ('expected_final_games', 110),
    ('completed_final_games', 10),
    ('unresolved_final_games', 99),
    ('terminal_failure_games', 1),
    ('publication_complete', True),
])
def test_a_changed_bootstrap_population_fails(field, value):
    report = clean_report()
    report['publication_completeness'][field] = value
    assert _failure(report).invariant == f'completeness_{field}'


def test_a_missing_completeness_object_fails():
    report = clean_report()
    report['publication_completeness'] = None
    assert _failure(report).invariant == 'publication_completeness_is_an_object'


# ═══════════════ 14-17. Run health ══════════════════════════════════════════


def test_a_game_failure_fails():
    report = clean_report()
    report['games_failed'] = 1
    assert _failure(report).invariant == 'games_failed'


def test_a_game_error_class_fails():
    report = clean_report()
    report['games'][0]['error_class'] = 'game_fetch_failed'
    assert _failure(report).invariant == 'game_823110_error_class'


def test_a_budget_stop_fails():
    report = clean_report()
    report['budget_stop_triggered'] = True
    assert _failure(report).invariant == 'budget_stop_triggered'


def test_a_finality_conflict_fails():
    report = clean_report()
    report['finality_conflicts'] = 1
    assert _failure(report).invariant == 'finality_conflicts'


def test_missing_schedule_authority_fails():
    report = clean_report()
    report['schedule_authority_missing'] = 1
    assert _failure(report).invariant == 'schedule_authority_missing'


# ═══════════════ 18-20. Row accounting ══════════════════════════════════════


def test_a_wrong_per_game_row_count_fails():
    report = clean_report()
    report['games'][0]['appearances_extracted'] = 7
    assert _failure(report).invariant == 'game_823110_appearances_extracted'


def test_a_wrong_total_row_count_fails():
    report = clean_report()
    report['rows_expected'] = 44
    assert _failure(report).invariant == 'rows_expected'


def test_a_short_row_list_fails_even_when_totals_pass():
    report = clean_report()
    report['games'][0]['rows'] = report['games'][0]['rows'][:-1]
    assert _failure(report).invariant == 'game_823110_row_count'


def test_a_duplicate_row_fails():
    report = clean_report()
    rows = report['games'][0]['rows']
    rows[1] = _row(823110, rows[0]['pitcher_mlb_id'])
    assert 'row_appears_once' in _failure(report).invariant


# ═══════════════ 21-32. Mutations by target ═════════════════════════════════


def test_a_gamelog_update_fails():
    report = clean_report()
    report['rows_updated'] = 1
    report['rows_unchanged'] = 42
    assert _failure(report).invariant == 'rows_updated'


def test_a_gamelog_insert_fails():
    report = clean_report()
    report['rows_inserted'] = 1
    report['rows_unchanged'] = 42
    assert _failure(report).invariant == 'rows_inserted'


def test_a_blocked_row_fails():
    report = clean_report()
    report['rows_blocked'] = 1
    assert _failure(report).invariant == 'rows_blocked'


def test_a_row_level_update_fails_even_when_totals_pass():
    report = clean_report()
    report['games'][0]['rows'][0]['action'] = 'update'
    assert 'action' in _failure(report).invariant


@pytest.mark.parametrize('counter', [
    'pitcher_identity_mutations',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'appearance_team_mutations',
    'complete_mutation_count',
    'canonical_outs_corrections',
    'statistical_corrections',
    'derived_companion_fields_applied',
])
def test_any_nonzero_mutation_counter_fails(counter):
    report = clean_report()
    report[counter] = 1
    assert _failure(report).invariant == counter


@pytest.mark.parametrize('action', [
    'create_minimal_identity', 'reactivate', 'update_metadata', 'create',
    'blocked', 'something_unknown',
])
def test_any_identity_write_action_on_a_row_fails(action):
    report = clean_report()
    report['games'][0]['rows'][0]['pitcher_identity_action'] = action
    assert 'pitcher_identity_action' in _failure(report).invariant


def test_identity_changed_fields_fail():
    report = clean_report()
    report['games'][0]['rows'][0]['pitcher_identity_changed_fields'] = ['active']
    assert 'identity_changed_fields' in _failure(report).invariant


def test_an_identity_mutation_digest_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['pitcher_identity_mutation_digest'] = 'abc'
    assert 'identity_mutation_digest' in _failure(report).invariant


def test_an_identity_blocked_reason_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['pitcher_identity_blocked_reason'] = (
        'conflicting_player_identity'
    )
    assert 'identity_blocked_reason' in _failure(report).invariant


def test_an_appearance_team_mutation_on_a_row_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['appearance_team_reason'] = 'resolved_boxscore'
    assert 'appearance_team_reason' in _failure(report).invariant


def test_an_identity_action_count_other_than_unchanged_fails():
    report = clean_report()
    report['pitcher_identity_action_counts'] = {'update_metadata': 43}
    assert 'update_metadata' in _failure(report).invariant


# ═══════════════ 33-34. Suppressed evidence is accepted ═════════════════════


def test_suppressed_historical_differences_are_accepted_and_counted():
    result = validator.validate(clean_report())
    summary = result['summary']
    assert summary['result'] == validator.RESULT_PASS
    # Half of each game's rows carry a suppressed difference.
    assert summary['historical_current_state_changes_suppressed'] > 0
    assert summary['suppressed_current_state_field_counts'] == {
        'team_id': summary['historical_current_state_changes_suppressed'],
    }
    # Refused evidence is never a mutation.
    assert summary['complete_mutation_count'] == 0


def test_suppressed_differences_do_not_change_the_fingerprint():
    plain = clean_report()
    for game in plain['games']:
        for row in game['rows']:
            row['pitcher_identity_suppressed_fields'] = []
            row['pitcher_identity_current_authority_mutation_refused'] = False
    with_suppression = clean_report()
    assert (
        validator.validate(plain)['summary'][
            'complete_reconciliation_fingerprint'
        ]
        == validator.validate(with_suppression)['summary'][
            'complete_reconciliation_fingerprint'
        ]
    )


def test_a_suppressed_difference_must_be_reported_as_refused():
    report = clean_report()
    report['games'][0]['rows'][0][
        'pitcher_identity_current_authority_mutation_refused'
    ] = False
    assert 'current_authority_mutation_refused' in _failure(report).invariant


def test_an_unknown_suppressed_field_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['pitcher_identity_suppressed_fields'] = [
        'mystery_column',
    ]
    assert 'suppressed_field_mystery_column_is_known' in _failure(report).invariant


# ═══════════════ 35-39. Canonical innings ═══════════════════════════════════


def test_a_wrong_total_ignored_count_fails():
    report = clean_report()
    report['derived_companion_differences_ignored'] = 17
    assert _failure(report).invariant == 'derived_companion_differences_ignored'


def test_a_wrong_per_game_ignored_count_fails():
    report = clean_report()
    report['games'][0]['derived_companion_differences_ignored'] = 3
    assert _failure(report).invariant == (
        'game_823110_derived_companion_differences_ignored'
    )


def test_a_suppressed_counter_mismatch_fails():
    report = clean_report()
    report['decimal_only_updates_suppressed'] = 17
    assert _failure(report).invariant == 'decimal_only_updates_suppressed'


def test_a_decimal_companion_applied_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['derived_companion_fields'] = [
        'innings_pitched',
    ]
    assert 'derived_companion_fields' in _failure(report).invariant


def test_a_semantic_innings_pitched_correction_fails():
    report = clean_report()
    report['changed_fields_counts'] = {'innings_pitched': 1}
    assert _failure(report).invariant == 'changed_fields_counts'


def test_a_row_level_semantic_innings_change_fails():
    report = clean_report()
    report['games'][0]['rows'][0]['semantic_changed_fields'] = [
        'innings_pitched',
    ]
    assert 'semantic_changed_fields' in _failure(report).invariant


# ═══════════════ 40-44. Fingerprints and versions ═══════════════════════════


def test_a_missing_run_fingerprint_fails():
    report = clean_report()
    report['complete_reconciliation_fingerprint'] = None
    assert _failure(report).invariant == 'complete_reconciliation_fingerprint'


@pytest.mark.parametrize('bad', ['abc', 'a' * 63, 'a' * 65, 'A' * 64,
                                 'z' * 64, 12345])
def test_an_invalid_fingerprint_shape_fails(bad):
    report = clean_report()
    report['complete_reconciliation_fingerprint'] = bad
    assert _failure(report).invariant == 'complete_reconciliation_fingerprint'


def test_a_missing_per_game_fingerprint_fails():
    report = clean_report()
    report['games'][0]['complete_reconciliation_fingerprint'] = None
    failure = _failure(report)
    assert failure.invariant == (
        'game_823110_complete_reconciliation_fingerprint'
    )


def test_collapsed_per_game_fingerprints_fail():
    """Five distinct game plans must not share one identity."""
    report = clean_report()
    shared = _fingerprint('shared')
    for game in report['games']:
        game['complete_reconciliation_fingerprint'] = shared
    assert _failure(report).invariant == 'per_game_fingerprints_are_distinct'


@pytest.mark.parametrize('field', [
    'reconciliation_plan_version', 'parity_contract_version',
    'innings_semantics_version', 'complete_plan_version',
    'identity_plan_version',
])
def test_a_wrong_version_fails(field):
    report = clean_report()
    report[field] = '99'
    assert _failure(report).invariant == field


def test_the_expected_versions_come_from_the_merged_modules():
    assert validator.EXPECTED_RECONCILIATION_PLAN_VERSION == '3'
    assert validator.EXPECTED_PARITY_CONTRACT_VERSION == '3'
    assert validator.EXPECTED_INNINGS_SEMANTICS_VERSION == '2'
    assert validator.EXPECTED_COMPLETE_PLAN_VERSION == '1'
    assert validator.EXPECTED_IDENTITY_PLAN_VERSION == '1'
    assert validator.EXPECTED_RECONCILIATION_PLAN_VERSION == (
        reconciliation.RECONCILIATION_PLAN_VERSION
    )
    assert validator.EXPECTED_IDENTITY_PLAN_VERSION == (
        identity.IDENTITY_PLAN_VERSION
    )


@pytest.mark.parametrize('field,value', [
    ('status', 'incomplete'), ('mode', 'write'),
    ('reference_date', '2026-07-30'),
])
def test_execution_identity_is_pinned(field, value):
    report = clean_report()
    report[field] = value
    assert _failure(report).invariant == field


# ═══════════════ 45-50. Authorization package and CLI ═══════════════════════


def _run_main(tmp_path, report):
    if report is not None:
        (tmp_path / 'report.json').write_text(json.dumps(report))
    return validator.main([
        '--report', str(tmp_path / 'report.json'),
        '--summary-json', str(tmp_path / 'summary.json'),
        '--summary-markdown', str(tmp_path / 'summary.md'),
        '--authorization-json', str(tmp_path / 'auth.json'),
        '--authorization-markdown', str(tmp_path / 'auth.md'),
        '--repository-sha', 'abc123',
        '--run-id', '42',
    ])


def test_a_clean_run_exits_zero_and_writes_every_artifact(tmp_path):
    assert _run_main(tmp_path, clean_report()) == 0
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'pass'
    assert summary['repository_sha'] == 'abc123'
    assert summary['workflow_run_id'] == '42'
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'FOUNDATION 3C R3 — PASS' in markdown
    assert '- 823110: 6 rows' in markdown
    assert '- Total complete-plan mutations: 0' in markdown
    assert '- Write approved: no' in markdown
    assert 'R4 status: blocked pending founder review' in markdown
    assert (tmp_path / 'auth.json').exists()
    assert (tmp_path / 'auth.md').exists()


def test_the_authorization_package_preserves_the_reviewed_game_order(tmp_path):
    _run_main(tmp_path, clean_report())
    package = json.loads((tmp_path / 'auth.json').read_text())
    assert [entry['game_pk'] for entry in package['games']] == list(
        APPROVED_GAME_PKS
    )
    assert package['planned_game_pks'] == list(APPROVED_GAME_PKS)


def test_the_authorization_package_is_deterministic(tmp_path):
    first = tmp_path / 'a'
    second = tmp_path / 'b'
    first.mkdir()
    second.mkdir()
    report = clean_report()
    _run_main(first, report)
    shuffled = clean_report()
    shuffled['games'] = list(reversed(shuffled['games']))
    _run_main(second, shuffled)
    assert (first / 'auth.json').read_text() == (second / 'auth.json').read_text()


def test_the_authorization_package_never_approves_a_write(tmp_path):
    _run_main(tmp_path, clean_report())
    package = json.loads((tmp_path / 'auth.json').read_text())
    assert package['write_approved'] is False
    assert package['r4_status'] == 'blocked_pending_founder_review'
    assert package['database_writes'] == 'none'
    assert package['complete_mutation_count'] == 0
    assert package['mutations_by_target'] == {
        'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
    }
    markdown = (tmp_path / 'auth.md').read_text()
    assert 'Write approved: **no**' in markdown
    assert 'blocked pending founder review' in markdown


def test_a_failed_run_cannot_exit_zero(tmp_path):
    report = clean_report()
    report['rows_updated'] = 1
    assert _run_main(tmp_path, report) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['result'] == 'failed'
    assert summary['failed_invariant']
    assert summary['next_action'] == (
        'Stop Foundation 3C rollout. Do not create or run R4.'
    )
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'FOUNDATION 3C R3 — FAILED' in markdown
    assert 'R4 is blocked' in markdown
    # The package is still written, empty, so nothing looks withheld.
    package = json.loads((tmp_path / 'auth.json').read_text())
    assert package['games'] == []
    assert package['write_approved'] is False


def test_a_missing_report_fails(tmp_path):
    assert _run_main(tmp_path, None) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['failed_invariant'] == 'report_file_exists'


def test_unparsable_json_fails(tmp_path):
    (tmp_path / 'report.json').write_text('{not json')
    assert _run_main(tmp_path, None) == 1
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['failed_invariant'] == 'report_is_valid_json'


def test_the_pass_summary_never_claims_write_approval(tmp_path):
    _run_main(tmp_path, clean_report())
    markdown = (tmp_path / 'summary.md').read_text()
    assert 'write approved: yes' not in markdown.lower()
    assert 'authorized' not in markdown.lower()
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['write_approved'] is False


@pytest.mark.parametrize('forbidden', [
    'postgresql://', 'postgres://', 'password=', 'Authorization:',
    'X-Admin-Token', 'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
    'Traceback', 'File "', os.sep + 'home' + os.sep,
])
def test_no_output_can_carry_a_credential_or_a_raw_error(tmp_path, forbidden):
    _run_main(tmp_path, clean_report())
    for name in ('summary.json', 'summary.md', 'auth.json', 'auth.md'):
        assert forbidden not in (tmp_path / name).read_text()


# ═══════════════ Real pipeline ══════════════════════════════════════════════
#
# Everything above validates a report this module builds. These tests run the
# real planner, the real canonical writer in planning mode, and the real
# completeness builder — assembled exactly as
# backend/scripts/game_driven_ingestion.py assembles them — and hand the result
# to the real validator untouched.


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


def _all_tables():
    return {
        'pitchers': [
            (
                row.id, row.mlb_id, row.full_name, row.position, row.active,
                row.team_id, row.team_name, row.team_abbreviation,
                row.team_assignment_status, row.team_assignment_source,
                row.team_assignment_updated_at, row.roster_status,
                row.roster_status_source, row.roster_status_raw_code,
                row.roster_status_raw_description, row.roster_status_updated_at,
                row.updated_at,
            )
            for row in Pitcher.query.order_by(Pitcher.id).all()
        ],
        'pitcher_count': Pitcher.query.count(),
        'pitcher_max_id': db.session.query(db.func.max(Pitcher.id)).scalar(),
        'game_logs': [
            (
                row.id, row.pitcher_id, row.mlb_game_pk,
                row.innings_pitched_outs, row.innings_pitched, row.earned_runs,
                row.appearance_team_id, row.appearance_team_source,
                row.appearance_team_status, row.appearance_team_reason,
                row.stat_correction_count, row.last_stat_correction_at,
                row.last_stat_correction_source,
            )
            for row in GameLog.query.order_by(GameLog.id).all()
        ],
        'work_items': [
            row.to_dict()
            for row in GameIngestionWorkItem.query.order_by(
                GameIngestionWorkItem.id
            ).all()
        ],
        'postgame': [
            row.to_dict()
            for row in PostgameProcessedGame.query.order_by(
                PostgameProcessedGame.id
            ).all()
        ],
        'schedule': [
            row.to_dict()
            for row in ScheduledGame.query.order_by(ScheduledGame.id).all()
        ],
        'failures': SyncFailure.query.count(),
    }


def _build_controlled_sample():
    """The production shape, modelled from its underlying conditions."""
    boxscores = {}
    for game_pk in APPROVED_GAME_PKS:
        _schedule(game_pk)
        rows_expected = validator.EXPECTED_ROWS_BY_GAME[game_pk]
        drifted = validator.EXPECTED_IGNORED_BY_GAME[game_pk]
        lines = []
        for index in range(rows_expected):
            mlb_id = game_pk * 10 + index
            arm = _pitcher(
                mlb_id,
                # Historical/current differences that D-009 must suppress.
                team_id=AWAY_TEAM if index % 2 else HOME_TEAM,
                active=index % 3 != 0,
            )
            arm.roster_status = STATUS_MINORS if index % 2 else STATUS_ACTIVE
            arm.roster_status_source = 'mlb_stats_api:roster_sync:fullRoster'
            db.session.flush()
            if index < drifted:
                # Representation drift inside the CHECK constraint tolerance.
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


def _real_r3_report():
    """Exactly what the pinned R3 command writes to disk."""
    report = game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        only_game_pks=list(APPROVED_GAME_PKS),
    )
    report['publication_completeness'] = (
        game_ingestion_completeness.build_game_ingestion_completeness(REFERENCE)
    )
    return report


def test_the_real_controlled_sample_produces_the_expected_shape(app, monkeypatch):
    with app.app_context():
        boxscores = _build_controlled_sample()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        before = _all_tables()
        report = _real_r3_report()
        db.session.rollback()

        assert report['execution_scope_mode'] == 'exclusive'
        assert sorted(report['planned_game_pks']) == sorted(APPROVED_GAME_PKS)
        assert report['rows_expected'] == 43
        assert report['rows_unchanged'] == 43
        assert report['rows_inserted'] == 0
        assert report['rows_updated'] == 0
        assert report['rows_blocked'] == 0
        assert report['derived_companion_differences_ignored'] == 18
        assert report['pitcher_identity_mutations'] == 0
        assert report['appearance_team_mutations'] == 0
        assert report['complete_mutation_count'] == 0
        assert report['historical_current_state_changes_suppressed'] > 0
        assert report['complete_reconciliation_fingerprint']

        for game in report['games']:
            game_pk = game['game_pk']
            assert game['appearances_extracted'] == (
                validator.EXPECTED_ROWS_BY_GAME[game_pk]
            )
            assert game['derived_companion_differences_ignored'] == (
                validator.EXPECTED_IGNORED_BY_GAME[game_pk]
            )

        # Shadow must leave every table byte-identical.
        assert _all_tables() == before


def test_the_real_report_passes_the_real_validator(app, monkeypatch):
    with app.app_context():
        boxscores = _build_controlled_sample()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        report = _real_r3_report()
        db.session.rollback()

        # The fixture cannot reproduce the production bootstrap population, so
        # only that pinned expectation is substituted. Every other invariant is
        # asserted against the untouched report.
        report['publication_completeness'].update({
            'expected_final_games': 109,
            'completed_final_games': 5,
            'unresolved_final_games': 104,
            'terminal_failure_games': 0,
            'publication_complete': False,
        })

        result = validator.validate(report)
        summary = result['summary']

        assert summary['result'] == validator.RESULT_PASS
        assert summary['rows_unchanged'] == 43
        assert summary['derived_companion_differences_ignored'] == 18
        assert summary['complete_mutation_count'] == 0
        assert summary['write_approved'] is False
        assert validator.FINGERPRINT_PATTERN.match(
            summary['complete_reconciliation_fingerprint']
        )
        assert [entry['game_pk'] for entry in result['games']] == list(
            APPROVED_GAME_PKS
        )
        for entry in result['games']:
            assert validator.FINGERPRINT_PATTERN.match(
                entry['complete_reconciliation_fingerprint']
            )


def test_the_real_report_carries_every_key_the_validator_requires(
    app, monkeypatch,
):
    """Guards against the merged report shape drifting away from this gate."""
    with app.app_context():
        boxscores = _build_controlled_sample()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        report = _real_r3_report()
        db.session.rollback()

        for key in (
            'status', 'mode', 'reference_date', 'execution_scope_mode',
            'requested_game_pks', 'requested_game_count',
            'duplicate_requested_count', 'planned_game_pks',
            'planned_game_count', 'unexpected_planned_game_pks',
            'missing_requested_game_pks', 'execution_scope_exact_match',
            'games_attempted', 'games_fetched', 'games_completed',
            'games_failed', 'games_remaining', 'budget_stop_triggered',
            'budget_stop', 'failure_classes', 'finality_conflicts',
            'schedule_authority_missing', 'critical_games_unresolved',
            'rows_expected', 'rows_inserted', 'rows_updated', 'rows_unchanged',
            'rows_blocked', 'changed_fields_counts',
            'derived_companion_differences_ignored',
            'decimal_only_updates_suppressed', 'pitcher_identity_mutations',
            'pitcher_identity_creations', 'pitcher_identity_reactivations',
            'pitcher_identity_metadata_updates', 'pitcher_identity_blocked',
            'pitcher_identity_action_counts',
            'pitcher_identity_changed_fields_counts',
            'appearance_team_mutations', 'complete_mutation_count',
            'historical_current_state_changes_suppressed',
            'reconciliation_plan_version', 'parity_contract_version',
            'innings_semantics_version', 'complete_plan_version',
            'identity_plan_version', 'reconciliation_plan_fingerprint',
            'complete_reconciliation_fingerprint', 'games',
            'publication_completeness',
        ):
            assert key in report, key

        game = report['games'][0]
        for key in (
            'game_pk', 'represented_date', 'candidate_reason', 'criticality',
            'attempt_number', 'status', 'source_revision',
            'appearances_extracted', 'inserted', 'updated', 'unchanged',
            'blocked', 'derived_companion_differences_ignored',
            'canonical_outs_corrections', 'pitcher_identity_mutations',
            'appearance_team_mutations', 'complete_mutation_count',
            'complete_reconciliation_fingerprint', 'rows', 'error_class',
        ):
            assert key in game, key

        row = game['rows'][0]
        for key in (
            'game_pk', 'pitcher_mlb_id', 'action', 'changed_fields',
            'changed_field_count', 'governed_and_safe', 'blocked_reason',
            'semantic_changed_fields', 'applied_changed_fields',
            'derived_companion_fields',
            'derived_companion_differences_ignored', 'appearance_team_reason',
            'pitcher_identity_action', 'pitcher_identity_changed_fields',
            'pitcher_identity_applied_fields',
            'pitcher_identity_suppressed_fields',
            'pitcher_identity_governed_and_safe',
            'pitcher_identity_blocked_reason',
            'pitcher_identity_mutation_digest',
            'pitcher_identity_requires_creation',
            'pitcher_identity_current_authority_mutation_refused',
        ):
            assert key in row, key


# ═══════════════ Eligibility is grounded in the planner, not a label ════════


def test_the_expected_candidate_reason_is_the_exclusive_scope_value():
    """`newly_final` is unreachable here and must not be asserted.

    `game_ingestion_planner._candidate_decision` short-circuits on `explicit:`
    before it inspects any state, and exclusive scope marks every requested
    game explicit. Validating for `newly_final` would fail every R3 run while
    proving nothing about whether the sample is still unresolved.
    """
    assert validator.EXPECTED_CANDIDATE_REASON == (
        GameIngestionWorkItem.REASON_EXPLICIT_REPAIR
    )
    assert GameIngestionWorkItem.REASON_NEWLY_FINAL in (
        validator.FORBIDDEN_CANDIDATE_REASONS
    )


def test_a_retry_count_fails():
    report = clean_report()
    report['retry_count'] = 1
    assert _failure(report).invariant == 'retry_count'


def test_a_corrected_final_count_fails():
    report = clean_report()
    report['corrected_final_count'] = 1
    assert _failure(report).invariant == 'corrected_final_count'


def test_the_real_planner_reports_the_exclusive_scope_reason(app, monkeypatch):
    """The eligibility contract is asserted against the real planner output."""
    with app.app_context():
        boxscores = _build_controlled_sample()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        report = _real_r3_report()
        db.session.rollback()

        for game in report['games']:
            assert game['candidate_reason'] == (
                validator.EXPECTED_CANDIDATE_REASON
            )
            # The load-bearing proof: no work item exists for this game.
            assert game['attempt_number'] == 1
            assert game['criticality'] == validator.EXPECTED_CRITICALITY
        assert report['retry_count'] == 0
        assert report['corrected_final_count'] == 0


def test_a_game_with_a_prior_attempt_fails_eligibility(app, monkeypatch):
    """Any existing work item advances the attempt number, so R3 fails.

    This is what makes the attempt number the load-bearing eligibility
    proof: a completed checkpoint, a failed prior attempt, and a correction
    re-check all leave a work item behind, and none of them can report 1.
    """
    with app.app_context():
        boxscores = _build_controlled_sample()
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=APPROVED_GAME_PKS[0],
            represented_date=REFERENCE,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            attempt_count=1,
        ))
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        report = _real_r3_report()
        db.session.rollback()

        target = next(
            game for game in report['games']
            if game['game_pk'] == APPROVED_GAME_PKS[0]
        )
        assert target['attempt_number'] == 2

        report['publication_completeness'].update({
            'expected_final_games': 109, 'completed_final_games': 5,
            'unresolved_final_games': 104, 'terminal_failure_games': 0,
            'publication_complete': False,
        })
        failure = _failure(report)
        assert failure.invariant == f'game_{APPROVED_GAME_PKS[0]}_attempt_number'
