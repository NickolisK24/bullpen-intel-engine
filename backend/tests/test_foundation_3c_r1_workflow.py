"""Foundation 3C — the manual R1 shadow validation workflow.

R1 is a rollout gate that will be run from a phone, with no inputs. These tests
pin what that means: one manual trigger, read-only permissions, exactly five
hard-coded games, shadow mode only, no path to a write or a deployment, a
validation that fails closed, and artifacts that survive a failure without
carrying a secret.
"""

import json
from pathlib import Path

import pytest

from scripts import validate_r1_shadow_report as validator


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / '.github' / 'workflows' / 'foundation-3c-r1-shadow-validation.yml'
)
APPROVED_GAME_PKS = (823518, 824735, 823761, 824083, 824327)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    # PyYAML is a declared dependency in backend/requirements.txt. It is
    # imported here rather than at module scope for two reasons: a missing
    # parser must not abort collection of the whole suite, and it must not
    # quietly skip these guards either. importorskip would turn a rollout gate
    # into a green no-op, so an absent parser fails loudly instead.
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
#
# The invariants below are the ones whose failure would be most costly: a
# trigger that fires itself, a mode that writes, a scope that widens. They are
# asserted against the raw file so they hold even if the structural guards
# above cannot run at all.


PINNED_INGESTION_COMMAND = (
    'python backend/scripts/game_driven_ingestion.py '
    '--mode shadow --reference-date 2026-07-29 '
    '--only-game-pk 823518 --only-game-pk 824735 --only-game-pk 823761 '
    '--only-game-pk 824083 --only-game-pk 824327 '
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
    '--max-games', '--include-backfill',
])
def test_no_write_or_widening_option_appears_in_the_file(
    workflow_text, forbidden,
):
    assert forbidden not in workflow_text


def test_the_automated_lane_is_off_in_the_file(workflow_text):
    assert "GAME_DRIVEN_INGESTION_MODE: 'off'" in workflow_text
    assert "AUTO_SYNC: 'false'" in workflow_text


# ═══════════════ 1. Manual only ═════════════════════════════════════════════


def test_the_workflow_parses(workflow):
    assert workflow['name'] == 'Foundation 3C R1 Shadow Validation'


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
    'actions', 'pull-requests', 'deployments', 'packages', 'id-token',
    'issues', 'checks', 'statuses',
])
def test_no_additional_permission_is_requested(workflow, scope):
    assert scope not in workflow['permissions']


def test_no_write_permission_appears_anywhere(workflow_text):
    assert 'write' not in workflow_text.split('permissions:')[1].split('jobs:')[0]


# ═══════════════ 3. The command is pinned ═══════════════════════════════════


@pytest.fixture(scope='module')
def ingestion_command(run_commands):
    matches = [
        line for line in run_commands
        if 'game_driven_ingestion.py' in line
    ]
    assert len(matches) == 1, 'exactly one ingestion invocation'
    return matches[0]


def test_the_command_runs_shadow_mode(ingestion_command):
    assert '--mode shadow' in ingestion_command


def test_the_command_pins_the_reference_date(ingestion_command):
    assert '--reference-date 2026-07-29' in ingestion_command


def test_the_command_requests_exactly_the_five_approved_games(ingestion_command):
    requested = [
        int(part) for part in ingestion_command.split()
        if part.isdigit()
    ]
    assert sorted(requested) == sorted(APPROVED_GAME_PKS)
    assert ingestion_command.count('--only-game-pk') == 5


def test_the_command_uses_exclusive_scope_not_additive(ingestion_command):
    assert '--game-pk ' not in ingestion_command.replace('--only-game-pk ', '')


@pytest.mark.parametrize('forbidden', [
    '--max-games', '--include-backfill', '--mode write',
    '--mode authoritative', '--expected-plan-fingerprint',
])
def test_the_command_carries_no_widening_or_write_option(
    ingestion_command, forbidden,
):
    assert forbidden not in ingestion_command


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


# ═══════════════ 6. No deployment or publication ════════════════════════════


@pytest.mark.parametrize('forbidden', [
    'render', 'vercel', 'deploy', 'run_daily_sync', 'run_postgame_refresh',
    'publish', 'authoritative',
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
        'backend/scripts/validate_r1_shadow_report.py',
    }


# ═══════════════ 7. Validation covers every critical invariant ══════════════


@pytest.mark.parametrize('invariant', [
    'execution_scope_exact_match',
    'requested_game_count',
    'planned_game_count',
    'rows_expected',
    'rows_updated',
    'rows_unchanged',
    'rows_blocked',
    'rows_inserted',
    'derived_companion_differences_ignored',
    'decimal_only_updates_suppressed',
    'canonical_outs_corrections',
    'statistical_corrections',
    'games_failed',
    'innings_semantics_version',
])
def test_the_validator_asserts_the_invariant(invariant):
    source = Path(validator.__file__).read_text(encoding='utf-8')
    assert invariant in source


def test_the_validator_pins_the_expected_totals():
    assert validator.EXPECTED_APPEARANCE_ROWS == 38
    assert validator.EXPECTED_IGNORED_COMPANION_DIFFERENCES == 14
    assert sorted(validator.APPROVED_GAME_PKS) == sorted(APPROVED_GAME_PKS)
    assert validator.REFERENCE_DATE == '2026-07-29'


def test_the_validator_matches_the_merged_innings_semantics_version():
    from services import game_log_reconciliation

    assert validator.EXPECTED_INNINGS_SEMANTICS_VERSION == (
        game_log_reconciliation.INNINGS_SEMANTICS_VERSION
    )


# ═══════════════ 8-10. Artifacts, scan order, bounds ════════════════════════


def test_artifacts_upload_even_when_the_run_fails(job):
    upload = [
        step for step in job['steps']
        if str(step.get('uses', '')).startswith('actions/upload-artifact')
    ]
    assert len(upload) == 1
    assert upload[0]['if'] == '${{ always() }}'
    assert upload[0]['with']['name'] == 'foundation-3c-r1-shadow-validation'
    assert upload[0]['with']['retention-days'] == 14


def test_the_credential_scan_runs_before_the_upload(job):
    names = [str(step.get('name') or step.get('uses') or '') for step in job['steps']]
    scan = next(i for i, name in enumerate(names) if 'credential-shaped' in name)
    upload = next(i for i, name in enumerate(names) if 'upload' in name.lower())
    assert scan < upload


@pytest.mark.parametrize('pattern', [
    'postgresql://', 'postgres://', 'password=', 'Authorization:',
    'X-Admin-Token', 'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
])
def test_the_credential_scan_covers_the_required_patterns(workflow_text, pattern):
    scan = workflow_text.split('credential-shaped content')[1]
    assert pattern in scan


def test_the_job_is_bounded_and_serialized(workflow, job):
    assert job['timeout-minutes'] == 15
    assert workflow['concurrency']['group'] == 'foundation-3c-r1-shadow-validation'
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_a_failed_validation_cannot_produce_a_successful_job(run_commands):
    gate = [line for line in run_commands if 'VALIDATION_EXIT' in line]
    assert any('exit 1' in line for line in run_commands)
    assert gate, 'the final gate must read the validation exit code'


# ═══════════════ Validator behaviour ════════════════════════════════════════


def _passing_report():
    games = []
    rows_per_game = {823518: 9, 824735: 6, 823761: 9, 824083: 7, 824327: 7}
    drifted_per_game = {823518: 4, 824735: 2, 823761: 4, 824083: 2, 824327: 2}
    for game_pk, count in rows_per_game.items():
        rows = []
        for index in range(count):
            rows.append({
                'game_pk': game_pk,
                'pitcher_mlb_id': 600000 + index,
                'action': 'unchanged',
                'changed_fields': [],
                'changed_field_count': 0,
                'mutation_categories': ['unchanged_row'],
                'governed_and_safe': True,
                'blocked_reason': None,
                'derived_companion_differences_ignored': (
                    ['innings_pitched'] if index < drifted_per_game[game_pk] else []
                ),
                'pitcher_identity_action': 'unchanged',
                'pitcher_identity_changed_fields': [],
                'pitcher_identity_applied_fields': [],
                # Historical/current differences are expected here and are NOT
                # mutations: this is exactly the population that used to become
                # 940 metadata updates.
                'pitcher_identity_suppressed_fields': (
                    ['team_id'] if index % 2 == 0 else []
                ),
                'pitcher_identity_governed_and_safe': True,
                'pitcher_identity_blocked_reason': None,
                'pitcher_identity_mutation_digest': '',
            })
        games.append({
            'game_pk': game_pk,
            'status': 'projected',
            'inserted': 0,
            'updated': 0,
            'unchanged': count,
            'blocked': 0,
            'error_class': None,
            'rows': rows,
        })
    return {
        'status': 'complete',
        'mode': 'shadow',
        'reference_date': '2026-07-29',
        'execution_scope_mode': 'exclusive',
        'requested_game_pks': list(APPROVED_GAME_PKS),
        'requested_game_count': 5,
        'planned_game_pks': list(APPROVED_GAME_PKS),
        'planned_game_count': 5,
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'execution_scope_exact_match': True,
        'games_attempted': 5,
        'games_fetched': 5,
        'games_completed': 5,
        'games_failed': 0,
        'games_remaining': 0,
        'rows_expected': 38,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': 38,
        'rows_blocked': 0,
        'canonical_outs_corrections': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': 14,
        'decimal_only_updates_suppressed': 14,
        'innings_semantics_version': '2',
        'statistical_corrections': 0,
        'authority_reconciliations': 0,
        'provenance_only_updates': 0,
        'changed_fields_counts': {},
        'pitcher_identity_rows_examined': 38,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_unchanged': 38,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'pitcher_identity_action_counts': {'unchanged': 38},
        'pitcher_identity_changed_fields_counts': {},
        'pitcher_identity_unique_pitchers_affected': 0,
        'historical_current_state_changes_suppressed': 21,
        'suppressed_current_state_field_counts': {'team_id': 21},
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'games': games,
    }


def test_the_expected_r1_shape_passes():
    summary = validator.validate(_passing_report())
    assert summary['result'] == 'PASS'
    assert summary['failed_invariant'] is None


@pytest.mark.parametrize('mutate,invariant', [
    (lambda r: r.update(rows_updated=1), 'rows_updated'),
    (lambda r: r.update(rows_inserted=1), 'rows_inserted'),
    (lambda r: r.update(rows_blocked=1), 'rows_blocked'),
    (lambda r: r.update(rows_unchanged=37), 'rows_unchanged'),
    (lambda r: r.update(rows_expected=37), 'rows_expected'),
    (lambda r: r.update(games_failed=1), 'games_failed'),
    (lambda r: r.update(execution_scope_exact_match=False),
     'execution_scope_exact_match'),
    (lambda r: r.update(planned_game_count=6), 'planned_game_count'),
    (lambda r: r.update(unexpected_planned_game_pks=[999]),
     'unexpected_planned_game_pks'),
    (lambda r: r.update(missing_requested_game_pks=[823518]),
     'missing_requested_game_pks'),
    (lambda r: r.update(derived_companion_differences_ignored=13),
     'derived_companion_differences_ignored'),
    (lambda r: r.update(statistical_corrections=1), 'statistical_corrections'),
    (lambda r: r.update(canonical_outs_corrections=1),
     'canonical_outs_corrections'),
    (lambda r: r.update(innings_semantics_version='1'),
     'innings_semantics_version'),
    (lambda r: r.update(mode='write'), 'mode'),
    (lambda r: r.update(status='incomplete'), 'status'),
])
def test_each_broken_invariant_fails_closed(mutate, invariant):
    report = _passing_report()
    mutate(report)
    with pytest.raises(validator.ValidationFailure) as excinfo:
        validator.validate(report)
    assert excinfo.value.invariant == invariant


@pytest.mark.parametrize('field', [
    'innings_pitched', 'innings_pitched_outs', 'earned_runs', 'hits_allowed',
])
def test_a_changed_field_of_any_kind_fails_closed(field):
    report = _passing_report()
    report['changed_fields_counts'] = {field: 1}
    with pytest.raises(validator.ValidationFailure) as excinfo:
        validator.validate(report)
    assert field in excinfo.value.invariant


def test_a_row_level_update_fails_even_when_the_totals_pass():
    """A passing aggregate over a miscounted row set is not a pass."""
    report = _passing_report()
    report['games'][0]['rows'][0]['action'] = 'update'
    with pytest.raises(validator.ValidationFailure) as excinfo:
        validator.validate(report)
    assert excinfo.value.invariant.endswith('_action')


def test_a_row_count_mismatch_fails_even_when_the_totals_pass():
    report = _passing_report()
    report['games'][0]['rows'].pop()
    with pytest.raises(validator.ValidationFailure) as excinfo:
        validator.validate(report)
    assert excinfo.value.invariant == 'per_row_total'


def test_an_unrelated_game_fails_the_scope():
    report = _passing_report()
    report['planned_game_pks'] = list(APPROVED_GAME_PKS)[:-1] + [999999]
    with pytest.raises(validator.ValidationFailure) as excinfo:
        validator.validate(report)
    assert excinfo.value.invariant == 'planned_game_pks'


def test_a_missing_report_file_fails(tmp_path):
    code = validator.main([
        '--report', str(tmp_path / 'absent.json'),
        '--summary-json', str(tmp_path / 's.json'),
        '--summary-markdown', str(tmp_path / 's.md'),
    ])
    assert code == validator.EXIT_FAIL
    summary = json.loads((tmp_path / 's.json').read_text())
    assert summary['failed_invariant'] == 'report_file_exists'


def test_unparsable_json_fails(tmp_path):
    report = tmp_path / 'r.json'
    report.write_text('{not json')
    code = validator.main([
        '--report', str(report),
        '--summary-json', str(tmp_path / 's.json'),
        '--summary-markdown', str(tmp_path / 's.md'),
    ])
    assert code == validator.EXIT_FAIL
    assert 'FAILED' in (tmp_path / 's.md').read_text()


def test_the_passing_run_writes_both_summaries(tmp_path):
    report = tmp_path / 'r.json'
    report.write_text(json.dumps(_passing_report()))
    code = validator.main([
        '--report', str(report),
        '--summary-json', str(tmp_path / 's.json'),
        '--summary-markdown', str(tmp_path / 's.md'),
    ])
    assert code == validator.EXIT_PASS
    markdown = (tmp_path / 's.md').read_text()
    assert 'FOUNDATION 3C R1 — PASS' in markdown
    assert 'No database writes were performed.' in markdown
    assert 'Decimal-only differences safely ignored: 14' in markdown


def test_no_summary_output_can_carry_a_credential(tmp_path):
    report = tmp_path / 'r.json'
    report.write_text(json.dumps(_passing_report()))
    validator.main([
        '--report', str(report),
        '--summary-json', str(tmp_path / 's.json'),
        '--summary-markdown', str(tmp_path / 's.md'),
    ])
    for name in ('s.json', 's.md'):
        text = (tmp_path / name).read_text().lower()
        for pattern in ('postgres', 'password', 'authorization', 'token',
                        'secret_key'):
            assert pattern not in text


# ═══════════════ Pitcher identity (D-009) ═══════════════════════════════════
#
# The original production R1 passed on GameLog convergence alone. Those same
# rows carried identity actions write mode would have applied, so R1 now
# requires complete database convergence.


def test_the_repaired_production_shape_passes():
    summary = validator.validate(_passing_report())
    assert summary['result'] == 'PASS'
    assert summary['pitcher_identity_mutations'] == 0
    assert summary['complete_mutation_count'] == 0
    # Suppressed historical differences are refused evidence, not mutations.
    assert summary['historical_current_state_changes_suppressed'] == 21
    assert summary['suppressed_current_state_fields_observed'] == 21


@pytest.mark.parametrize('counter', [
    'pitcher_identity_mutations',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'appearance_team_mutations',
    'complete_mutation_count',
])
def test_a_hidden_identity_mutation_fails_r1(counter):
    """GameLog totals still pass; the run is not clean and R1 must say so."""
    report = _passing_report()
    report[counter] = 1
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    assert caught.value.invariant == counter


@pytest.mark.parametrize('action', ['reactivate', 'update_metadata', 'create',
                                    'create_minimal_identity'])
def test_a_row_carrying_an_identity_write_action_fails_r1(action):
    report = _passing_report()
    report['games'][0]['rows'][0]['pitcher_identity_action'] = action
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    assert 'pitcher_identity_action' in caught.value.invariant


def test_an_identity_changed_field_fails_r1():
    report = _passing_report()
    report['games'][0]['rows'][0]['pitcher_identity_changed_fields'] = ['active']
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    assert 'identity_changed_fields' in caught.value.invariant


def test_a_blocked_identity_fails_r1():
    report = _passing_report()
    report['games'][0]['rows'][0]['pitcher_identity_blocked_reason'] = (
        'conflicting_player_identity'
    )
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    assert 'identity_blocked_reason' in caught.value.invariant


def test_an_identity_action_count_fails_r1():
    report = _passing_report()
    report['pitcher_identity_action_counts'] = {'update_metadata': 940}
    with pytest.raises(validator.ValidationFailure) as caught:
        validator.validate(report)
    assert 'update_metadata' in caught.value.invariant


def test_the_job_summary_reports_every_mutation_target(tmp_path):
    report = _passing_report()
    path = tmp_path / 'r.json'
    path.write_text(json.dumps(report))
    assert validator.main([
        '--report', str(path),
        '--summary-json', str(tmp_path / 's.json'),
        '--summary-markdown', str(tmp_path / 's.md'),
    ]) == 0
    markdown = (tmp_path / 's.md').read_text()
    assert '### Mutations by target' in markdown
    assert '- Pitcher identity: 0' in markdown
    assert '- Reactivations: 0' in markdown
    assert '- Metadata updates: 0' in markdown
    assert '- Minimal identity creations: 0' in markdown
    assert '- Blocked identity entries: 0' in markdown
    assert 'Suppressed historical current-state differences: 21' in markdown
