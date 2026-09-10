"""Read-only closeout verification of the COMMITTED official pitching-line repair (2026).

Covers the corrected mode-specific reconciliation vocabularies (local-only never requires an
official-validation reconciliation, and says so explicitly rather than failing), the corrected
skipped-check semantics (ran-and-failed is a failure, never a skip), the read-only closeout
service's proof of the execution ledger and the reviewed amendment row, its fail-closed
behaviour, and the guarantee that nothing in this path writes, re-applies, or rewrites the
historical apply artifact.
"""

from datetime import date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from flask import Flask

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.official_pitching_line_repair_execution import (
    OfficialPitchingLineRepairExecution as Ledger,
)
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as completeness
from services import official_pitching_line_repair_apply_2026 as apply_service
from services import official_pitching_line_repair_closeout_2026 as closeout
from services import season_bullpen_aggregation_2026 as aggregation
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = (REPO_ROOT / 'backend' / 'services'
                / 'official_pitching_line_repair_closeout_2026.py')
CLI_PATH = (REPO_ROOT / 'backend' / 'scripts'
            / 'run_official_pitching_line_repair_closeout_2026.py')
WORKFLOW_PATH = (REPO_ROOT / '.github' / 'workflows'
                 / 'official_pitching_line_repair_closeout.yml')
APPLY_WORKFLOW_PATH = (REPO_ROOT / '.github' / 'workflows'
                       / 'official_pitching_line_repair_apply.yml')

FINGERPRINT = '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b'
BR_LOG_ID = 43765
BR_GAME = 825058
BR_PERSON = 805299
BR_TEAM = 109
GDATE = date(2026, 6, 10)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.rollback()
            db.session.remove()
            drop_test_schema(flask_app)


# ── Fixtures for the committed state ──────────────────────────────────────────
def seed_ledger(**overrides):
    values = {
        'capability': 'official_pitching_line_repair_apply_2026_v1',
        'approved_manifest_fingerprint': FINGERPRINT,
        'regenerated_manifest_fingerprint': FINGERPRINT,
        'planner_git_sha': 'b0850719c7ab2c4e9ee232758cd57ba25030364b',
        'apply_git_sha': 'b0850719c7ab2c4e9ee232758cd57ba25030364b',
        'season': 2026,
        'as_of_date': date(2026, 7, 25),
        'accepted_baseline_version': 'v2',
        'amendment_id': 'defect_baseline_amendment_1_brandyn_garcia_hits_allowed',
        'status': Ledger.STATUS_COMPLETED,
        'identity_action_count': 70,
        'insert_action_count': 445,
        'update_action_count': 160,
        'total_action_count': 675,
        'started_at': datetime(2026, 7, 29, 3, 0, 0),
        'completed_at': datetime(2026, 7, 29, 3, 5, 0),
        'committed_at': datetime(2026, 7, 29, 3, 5, 0),
    }
    values.update(overrides)
    row = Ledger(**values)
    db.session.add(row)
    db.session.commit()
    return row


def seed_amendment_row(*, hits_allowed=0, stat_correction_count=1,
                       source=apply_service.CORRECTION_SOURCE,
                       corrected_at=datetime(2026, 7, 29, 3, 5, 0), operation_id=12345):
    pitcher = Pitcher(mlb_id=BR_PERSON, full_name='P', position='P', active=True)
    db.session.add(pitcher)
    db.session.commit()
    log = GameLog(
        id=BR_LOG_ID, pitcher_id=pitcher.id, mlb_game_pk=BR_GAME, game_date=GDATE,
        game_type='R', games_started=0, innings_pitched_outs=3, innings_pitched=1.0,
        runs_allowed=0, earned_runs=0, hits_allowed=hits_allowed, walks=0, strikeouts=1,
        home_runs_allowed=0, strikes=6, opponent='T110', opponent_abbreviation='T110',
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_id=BR_TEAM, appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
        stat_correction_count=stat_correction_count, last_stat_correction_at=corrected_at,
        last_stat_correction_source=source,
        last_stat_correction_sync_run_id=operation_id)
    db.session.add(log)
    db.session.commit()
    return log


def clean_diagnostic(**kwargs):  # noqa: ARG001 — deterministic fixture
    return {'result': 'pass', 'exit_code': 0, 'missing_local_line_count': 0,
            'stat_mismatch_count': 0, 'role_mismatch_count': 0,
            'extra_local_line_count': 0, 'duplicate_local_line_count': 0,
            'appearance_team_mismatch_count': 0}


def clean_aggregation(**kwargs):
    """A complete passing aggregation for whichever mode is requested.

    ``all_mandatory_metrics_match`` is false in local-only exactly as the real service
    computes it, so these tests exercise the production shape rather than a friendlier one.
    """
    official = kwargs['include_official_validation']
    return {
        'result': 'pass', 'exit_code': 0,
        'mode': 'official_validation' if official else 'local_only',
        'local_aggregation': {'teams_complete': 30, 'teams_partial': 0,
                              'teams_unavailable': 0},
        'official_validation': {
            'teams_matched': 30, 'teams_mismatched': 0,
            'mandatory_metric_mismatches': 0, 'unavailable_evidence_count': 0,
            'official_games_missing_unique_starter': 0,
            'official_games_with_multiple_starters': 0},
        'reconciliations': {
            'canonical_outs_match': True, 'team_totals_reconcile': True,
            'league_totals_reconcile': True, 'bullpen_outs_reconcile': True,
            'all_mandatory_metrics_match': bool(official),
            'canonical_game_grain_bullpen_outs': 12, 'teams_returned': 30},
    }


@pytest.fixture
def committed(app, monkeypatch):
    """The production outcome: the repair committed and live evidence is clean."""
    seed_ledger()
    seed_amendment_row()
    monkeypatch.setattr(completeness, 'run_diagnostic', clean_diagnostic)
    monkeypatch.setattr(aggregation, 'run_aggregation', clean_aggregation)
    return app


def _run():
    return closeout.run_closeout_verification(
        generated_at='2026-07-30T00:00:00Z', closeout_git_sha='testsha',
        client=object(), session=db.session)


def _recon(mapping, *, official):
    return apply_service.evaluate_mode_reconciliations(
        mapping, include_official_validation=official)


LOCAL_STRUCTURAL = ('canonical_outs_match', 'team_totals_reconcile',
                    'league_totals_reconcile', 'bullpen_outs_reconcile')


def _all_true(extra=None):
    mapping = {name: True for name in LOCAL_STRUCTURAL}
    mapping['all_mandatory_metrics_match'] = False
    if extra:
        mapping.update(extra)
    return mapping


# ═══════════════ 1. Mode-specific reconciliation vocabulary ═════════════════
def test_local_only_does_not_require_the_official_validation_reconciliation():
    result = _recon(_all_true(), official=False)
    assert 'all_mandatory_metrics_match' not in result['required']
    assert result['failed'] == []
    assert result['satisfied'] is True


def test_local_only_reports_the_official_reconciliation_as_not_applicable():
    result = _recon(_all_true(), official=False)
    item = result['non_applicable']['all_mandatory_metrics_match']
    assert item['applicable'] is False
    assert item['status'] == 'not_applicable_to_local_only'
    # Reported with the value the aggregation actually produced. It is never rewritten to
    # true merely to satisfy the wrapper.
    assert item['observed_value'] is False


def test_local_only_still_requires_every_local_structural_reconciliation():
    assert sorted(_recon(_all_true(), official=False)['required']) == sorted(
        LOCAL_STRUCTURAL)


@pytest.mark.parametrize('name', LOCAL_STRUCTURAL)
def test_a_false_local_structural_reconciliation_fails(name):
    result = _recon(_all_true({name: False}), official=False)
    assert result['failed'] == [name]
    assert result['satisfied'] is False


@pytest.mark.parametrize('name', LOCAL_STRUCTURAL)
def test_a_missing_local_structural_reconciliation_fails(name):
    mapping = _all_true()
    mapping.pop(name)
    result = _recon(mapping, official=False)
    assert result['missing'] == [name]
    assert result['satisfied'] is False


def test_an_unexpected_false_local_boolean_reconciliation_fails():
    # Not required, and not classified as governed non-applicable. It fails closed rather
    # than being excused for resembling one.
    result = _recon(_all_true({'some_future_reconciliation': False}), official=False)
    assert result['unexpected_false'] == ['some_future_reconciliation']
    assert result['satisfied'] is False


def test_official_mode_requires_the_mandatory_metric_reconciliation():
    assert 'all_mandatory_metrics_match' in _recon(
        _all_true(), official=True)['required']
    # The same map that satisfies local-only does NOT satisfy official validation.
    assert _recon(_all_true(), official=True)['failed'] == [
        'all_mandatory_metrics_match']


def test_official_mode_requires_every_structural_reconciliation():
    required = _recon(_all_true(), official=True)['required']
    for name in LOCAL_STRUCTURAL:
        assert name in required, name
    assert len(required) == len(LOCAL_STRUCTURAL) + 1


def test_the_reconciliation_vocabularies_are_pinned_exactly():
    assert apply_service.LOCAL_ONLY_REQUIRED_RECONCILIATIONS == (
        'bullpen_outs_reconcile', 'canonical_outs_match', 'league_totals_reconcile',
        'team_totals_reconcile')
    assert apply_service.OFFICIAL_VALIDATION_REQUIRED_RECONCILIATIONS == (
        'all_mandatory_metrics_match', 'bullpen_outs_reconcile', 'canonical_outs_match',
        'league_totals_reconcile', 'team_totals_reconcile')
    assert apply_service.LOCAL_ONLY_NON_APPLICABLE_RECONCILIATIONS == (
        'all_mandatory_metrics_match',)
    assert apply_service.OFFICIAL_VALIDATION_NON_APPLICABLE_RECONCILIATIONS == ()


# ═══════════════ 2. Official-mode evidence requirements ═════════════════════
def _official_agg(**overrides):
    def _run_agg(**kwargs):
        payload = clean_aggregation(**kwargs)
        if kwargs['include_official_validation']:
            payload['official_validation'].update(overrides)
        return payload
    return _run_agg


@pytest.mark.parametrize('override, failing_check', [
    ({'teams_matched': 29}, 'all_thirty_teams_matched'),
    ({'teams_mismatched': 1}, 'zero_teams_mismatched'),
    ({'mandatory_metric_mismatches': 1}, 'zero_mandatory_metric_mismatches'),
    ({'unavailable_evidence_count': 1}, 'zero_unavailable_official_evidence'),
    ({'official_games_missing_unique_starter': 1},
     'zero_official_games_missing_a_unique_starter'),
    ({'official_games_with_multiple_starters': 1},
     'zero_official_games_with_multiple_starters'),
])
def test_official_validation_requires_complete_matching_evidence(
        committed, monkeypatch, override, failing_check):
    monkeypatch.setattr(aggregation, 'run_aggregation', _official_agg(**override))
    payload = _run()
    assert payload['result'] == closeout.RESULT_FAIL
    official = payload['official_validation_aggregation_verification']
    assert official['checks'][failing_check] is False
    assert closeout.CLOSEOUT_CHECKS[4] in payload['failed_checks']
    for gate in closeout.DOWNSTREAM_GATES:
        assert payload[gate] == closeout.GATE_BLOCKED


# ═══════════════ 3. Executed / present / passed / skipped are distinct ══════
def test_a_check_that_ran_and_failed_is_not_classified_as_skipped(committed, monkeypatch):
    monkeypatch.setattr(completeness, 'run_diagnostic',
                        lambda **kwargs: dict(clean_diagnostic(), result='fail',
                                              exit_code=1, missing_local_line_count=3))
    payload = _run()
    assert payload['result'] == closeout.RESULT_FAIL
    state = payload['check_states'][closeout.CLOSEOUT_CHECKS[2]]
    assert state['present'] is True
    assert state['executed'] is True
    assert state['passed'] is False
    assert state['skipped'] is False
    assert payload['not_executed_checks'] == []


def test_a_check_that_could_not_run_is_classified_as_not_executed(committed, monkeypatch):
    def _explode(**kwargs):
        raise RuntimeError('official evidence unavailable')

    monkeypatch.setattr(aggregation, 'run_aggregation', _explode)
    payload = _run()
    # Evidence that could not be observed leaves the question open — never a pass, and not
    # a contradiction either.
    assert payload['result'] == closeout.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [closeout.DECISION_EVIDENCE_UNAVAILABLE]
    for name in closeout.CLOSEOUT_CHECKS[3:]:
        state = payload['check_states'][name]
        assert state['executed'] is False
        assert state['skipped'] is True
        assert payload['checks'][name]['error_type'] == 'RuntimeError'


def test_every_check_present_and_executed_reports_nothing_skipped(committed):
    payload = _run()
    assert payload['result'] == closeout.RESULT_PASS
    assert payload['not_executed_checks'] == []
    assert sorted(payload['executed_checks']) == sorted(closeout.CLOSEOUT_CHECKS)
    for name in closeout.CLOSEOUT_CHECKS:
        assert payload['check_states'][name] == {
            'present': True, 'executed': True, 'passed': True, 'skipped': False}


def test_the_apply_wrapper_no_longer_calls_a_failed_check_skipped():
    # The corrected apply-side reconciliation: a check that RAN and FAILED breaks
    # `every_governed_post_commit_check_passed` and nothing else.
    post = {
        'checks': {name: {'executed': True,
                          'execution_state': apply_service.CHECK_EXECUTED,
                          'checks': {'result_is_pass': name != 'x'},
                          'passed': name != apply_service.POST_COMMIT_CHECKS[0]}
                   for name in apply_service.POST_COMMIT_CHECKS},
        'passed': False, 'not_executed_checks': [],
        'failed_checks': [apply_service.POST_COMMIT_CHECKS[0]],
    }
    reconciliations = apply_service._post_commit_reconciliations(post)
    assert reconciliations['every_governed_post_commit_check_passed'] is False
    assert reconciliations['no_post_commit_check_was_skipped'] is True
    assert reconciliations['every_governed_post_commit_check_is_present'] is True
    assert reconciliations['post_commit_verification_was_executed'] is True


def test_the_apply_wrapper_calls_a_missing_check_skipped():
    post = {
        'checks': {name: {'executed': True,
                          'execution_state': apply_service.CHECK_EXECUTED,
                          'checks': {'result_is_pass': True}, 'passed': True}
                   for name in apply_service.POST_COMMIT_CHECKS[:-1]},
        'passed': True, 'failed_checks': [],
        'not_executed_checks': [apply_service.POST_COMMIT_CHECKS[-1]],
    }
    reconciliations = apply_service._post_commit_reconciliations(post)
    assert reconciliations['every_governed_post_commit_check_is_present'] is False
    assert reconciliations['no_post_commit_check_was_skipped'] is False


def test_the_apply_wrapper_calls_an_unexecuted_check_skipped():
    post = {
        'checks': {name: ({'executed': True,
                           'execution_state': apply_service.CHECK_EXECUTED,
                           'checks': {'result_is_pass': True}, 'passed': True}
                          if name != apply_service.POST_COMMIT_CHECKS[1] else
                          {'executed': False,
                           'execution_state': apply_service.CHECK_NOT_EXECUTED,
                           'checks': {}, 'passed': False, 'error_type': 'RuntimeError'})
                   for name in apply_service.POST_COMMIT_CHECKS},
        'passed': False, 'failed_checks': [apply_service.POST_COMMIT_CHECKS[1]],
        'not_executed_checks': [apply_service.POST_COMMIT_CHECKS[1]],
    }
    reconciliations = apply_service._post_commit_reconciliations(post)
    assert reconciliations['every_governed_post_commit_check_is_present'] is True
    assert reconciliations['no_post_commit_check_was_skipped'] is False


# ═══════════════ 4. The execution ledger ════════════════════════════════════
def test_the_exact_completed_ledger_row_passes(committed):
    payload = _run()
    assert payload['result'] == closeout.RESULT_PASS
    ledger = payload['execution_ledger_verification']
    assert ledger['passed'] is True
    assert ledger['observed']['observed_execution_ledger_id'] == 1
    assert ledger['observed']['execution_ledger_id_matches_expected'] is True
    assert ledger['observed']['completed_row_count'] == 1
    assert ledger['observed']['total_action_count'] == 675
    assert ledger['observed']['identity_action_count'] == 70
    assert ledger['observed']['insert_action_count'] == 445
    assert ledger['observed']['update_action_count'] == 160
    assert ledger['observed']['committed_at'] is not None
    assert all(ledger['checks'].values())


def test_a_missing_ledger_row_fails_closed(app, monkeypatch):
    seed_amendment_row()
    monkeypatch.setattr(completeness, 'run_diagnostic', clean_diagnostic)
    monkeypatch.setattr(aggregation, 'run_aggregation', clean_aggregation)
    payload = _run()
    assert payload['result'] == closeout.RESULT_FAIL
    assert closeout.DECISION_LEDGER_NOT_PROVEN in payload['decision_reasons']
    ledger = payload['execution_ledger_verification']
    assert ledger['passed'] is False
    assert ledger['observed']['completed_row_count'] == 0
    assert ledger['checks']['exactly_one_completed_ledger_row'] is False


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):  # noqa: ARG002
        return self

    def order_by(self, *args, **kwargs):  # noqa: ARG002
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Returns rows the database itself refuses to store, so the fail-closed branches for
    those states are still proven."""

    def __init__(self, rows):
        self._rows = rows

    def query(self, *args, **kwargs):  # noqa: ARG002
        return _FakeQuery(self._rows)


def _ledger_stub(**overrides):
    values = {
        'id': 1, 'status': Ledger.STATUS_COMPLETED,
        'approved_manifest_fingerprint': FINGERPRINT,
        'regenerated_manifest_fingerprint': FINGERPRINT,
        'season': 2026, 'as_of_date': date(2026, 7, 25),
        'accepted_baseline_version': 'v2',
        'amendment_id': 'defect_baseline_amendment_1_brandyn_garcia_hits_allowed',
        'identity_action_count': 70, 'insert_action_count': 445,
        'update_action_count': 160, 'total_action_count': 675,
        'committed_at': datetime(2026, 7, 29, 3, 5, 0),
        'capability': 'official_pitching_line_repair_apply_2026_v1',
    }
    values.update(overrides)
    return type('LedgerStub', (), values)()


def test_two_ledger_rows_fail_closed():
    # The unique constraint forbids storing a second row for the approved fingerprint; this
    # proves the verifier refuses the state rather than trusting the constraint alone.
    result = closeout.verify_execution_ledger(
        _FakeSession([_ledger_stub(), _ledger_stub(id=2)]))
    assert result['passed'] is False
    assert result['checks']['exactly_one_ledger_row_for_the_approved_fingerprint'] is False
    assert result['observed']['ledger_row_count'] == 2


def test_a_non_completed_ledger_row_fails():
    result = closeout.verify_execution_ledger(
        _FakeSession([_ledger_stub(status='rolled_back')]))
    assert result['passed'] is False
    assert result['checks']['exactly_one_completed_ledger_row'] is False


def test_a_regenerated_fingerprint_mismatch_fails():
    result = closeout.verify_execution_ledger(
        _FakeSession([_ledger_stub(regenerated_manifest_fingerprint='f' * 64)]))
    assert result['passed'] is False
    assert result['checks'][
        'regenerated_fingerprint_matches_the_approved_fingerprint'] is False


@pytest.mark.parametrize('field, value, failing_check', [
    ('identity_action_count', 69, 'identity_action_count_matches'),
    ('insert_action_count', 444, 'insert_action_count_matches'),
    ('update_action_count', 159, 'update_action_count_matches'),
    ('total_action_count', 674, 'total_action_count_matches'),
    ('season', 2025, 'season_matches'),
    ('as_of_date', date(2026, 7, 24), 'as_of_date_matches'),
    ('accepted_baseline_version', 'v1', 'accepted_baseline_version_matches'),
    ('amendment_id', 'other', 'amendment_id_matches'),
    ('committed_at', None, 'committed_at_is_populated'),
])
def test_any_ledger_contract_mismatch_fails(field, value, failing_check):
    result = closeout.verify_execution_ledger(
        _FakeSession([_ledger_stub(**{field: value})]))
    assert result['passed'] is False
    assert result['checks'][failing_check] is False


# ═══════════════ 5. The reviewed amendment row ══════════════════════════════
def test_the_reviewed_amendment_row_at_the_corrected_value_passes(committed):
    payload = _run()
    amendment = payload['reviewed_amendment_verification']
    assert amendment['passed'] is True
    assert amendment['observed']['hits_allowed'] == 0
    assert amendment['observed']['stat_correction_count'] == 1
    assert amendment['observed']['last_stat_correction_source'] == (
        'official_pitching_line_repair')
    assert amendment['observed']['mlb_game_pk'] == BR_GAME
    assert amendment['observed']['official_mlb_person_id'] == BR_PERSON
    assert amendment['observed']['appearance_team_id'] == BR_TEAM


def test_the_reviewed_amendment_row_at_the_uncorrected_value_fails(app, monkeypatch):
    seed_ledger()
    seed_amendment_row(hits_allowed=1)
    monkeypatch.setattr(completeness, 'run_diagnostic', clean_diagnostic)
    monkeypatch.setattr(aggregation, 'run_aggregation', clean_aggregation)
    payload = _run()
    assert payload['result'] == closeout.RESULT_FAIL
    assert closeout.DECISION_AMENDMENT_NOT_PROVEN in payload['decision_reasons']
    amendment = payload['reviewed_amendment_verification']
    assert amendment['checks']['hits_allowed_is_the_corrected_value'] is False


@pytest.mark.parametrize('kwargs, failing_check', [
    ({'stat_correction_count': 0}, 'stat_correction_count_is_exactly_one'),
    ({'stat_correction_count': 2}, 'stat_correction_count_is_exactly_one'),
    ({'source': None}, 'correction_source_is_the_governed_repair'),
    ({'source': 'daily_sync'}, 'correction_source_is_the_governed_repair'),
    ({'corrected_at': None}, 'correction_timestamp_is_populated'),
    ({'operation_id': None}, 'governed_operation_id_is_populated'),
])
def test_missing_correction_metadata_fails(app, monkeypatch, kwargs, failing_check):
    seed_ledger()
    seed_amendment_row(**kwargs)
    monkeypatch.setattr(completeness, 'run_diagnostic', clean_diagnostic)
    monkeypatch.setattr(aggregation, 'run_aggregation', clean_aggregation)
    payload = _run()
    assert payload['result'] == closeout.RESULT_FAIL
    assert payload['reviewed_amendment_verification']['checks'][failing_check] is False


def test_a_missing_amendment_row_fails_closed(app, monkeypatch):
    seed_ledger()
    monkeypatch.setattr(completeness, 'run_diagnostic', clean_diagnostic)
    monkeypatch.setattr(aggregation, 'run_aggregation', clean_aggregation)
    payload = _run()
    assert payload['result'] == closeout.RESULT_FAIL
    assert payload['reviewed_amendment_verification']['checks'][
        'reviewed_amendment_row_exists'] is False


# ═══════════════ 6. Read-only guarantees ═══════════════════════════════════
def test_the_closeout_service_performs_zero_writes(committed):
    statements = []

    @sa.event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    try:
        payload = _run()
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', _capture)

    assert payload['result'] == closeout.RESULT_PASS
    assert payload['database_writes_performed'] is False
    assert payload['repair_reapplied'] is False
    lowered = ' '.join(statements).lower()
    for forbidden in ('insert into', 'update ', 'delete from', 'truncate', 'drop table',
                      'alter table', 'create table'):
        assert forbidden not in lowered, forbidden


def _called_names(path):
    """Every function/method name the module actually CALLS.

    Inspects the AST rather than the raw text, so prose that merely names a forbidden call
    in order to document that it is not made cannot trip the guard.
    """
    import ast as _ast
    called = set()
    for node in _ast.walk(_ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, _ast.Call):
            func = node.func
            if isinstance(func, _ast.Name):
                called.add(func.id)
            elif isinstance(func, _ast.Attribute):
                called.add(func.attr)
    return called


def _imported_modules(path):
    import ast as _ast
    modules = set()
    for node in _ast.walk(_ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, _ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, _ast.ImportFrom):
            modules.add(node.module or '')
            modules.update(alias.name for alias in node.names)
    return modules


def test_the_closeout_service_never_invokes_the_apply_entrypoint():
    called = _called_names(SERVICE_PATH)
    for forbidden in ('apply_reviewed_repair', 'acquire_repair_advisory_lock', 'commit',
                      'add', 'delete', 'flush', 'merge', 'execute', 'bulk_save_objects'):
        assert forbidden not in called, forbidden


def test_the_closeout_service_never_invokes_the_apply_command():
    modules = _imported_modules(SERVICE_PATH)
    for forbidden in ('subprocess', 'os', 'shutil', 'runpy',
                      'scripts.run_official_pitching_line_repair_apply_2026'):
        assert forbidden not in modules, forbidden
    called = _called_names(SERVICE_PATH)
    for forbidden in ('system', 'run', 'Popen', 'check_output', 'exec_module'):
        assert forbidden not in called, forbidden

    cli_modules = _imported_modules(CLI_PATH)
    cli_called = _called_names(CLI_PATH)
    assert 'official_pitching_line_repair_apply_2026' not in cli_modules
    assert 'apply_reviewed_repair' not in cli_called
    for forbidden in ('subprocess', 'runpy'):
        assert forbidden not in cli_modules, forbidden
    # The CLI's only governed entrypoint is the read-only closeout verifier.
    assert 'run_closeout_verification' in cli_called


def test_a_committed_run_is_not_reapplied_and_the_ledger_row_is_untouched(committed):
    before = db.session.query(Ledger).one()
    before_state = (before.id, before.status, before.total_action_count,
                    before.approved_manifest_fingerprint, before.committed_at)
    payload = _run()
    assert payload['result'] == closeout.RESULT_PASS
    db.session.expire_all()
    after = db.session.query(Ledger).one()
    assert (after.id, after.status, after.total_action_count,
            after.approved_manifest_fingerprint, after.committed_at) == before_state
    assert db.session.query(Ledger).count() == 1
    # The corrected row is read, never rewritten.
    log = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    assert log.hits_allowed == 0
    assert log.stat_correction_count == 1


def test_rerunning_the_apply_remains_forbidden_and_unnecessary(committed):
    # Unnecessary: the closeout proves the repair from the durable record alone.
    assert _run()['result'] == closeout.RESULT_PASS
    # Forbidden: the apply path refuses a second execution for the approved fingerprint,
    # and the ledger's unique constraint refuses a second row.
    apply_text = (REPO_ROOT / 'backend' / 'services'
                  / 'official_pitching_line_repair_apply_2026.py').read_text(
                      encoding='utf-8')
    assert 'ABORT_ALREADY_COMPLETED' in apply_text
    assert 'repair_already_completed_for_this_approved_fingerprint' in apply_text
    assert 'uq_oplr_executions_approved_fingerprint' in (
        REPO_ROOT / 'backend' / 'models'
        / 'official_pitching_line_repair_execution.py').read_text(encoding='utf-8')


def test_the_historical_apply_artifact_is_never_rewritten():
    text = SERVICE_PATH.read_text(encoding='utf-8')
    # The closeout reads live evidence and the ledger; it never opens, edits, or republishes
    # a prior apply artifact.
    for forbidden in ('open(', 'write_text', 'Path(', 'json.dump', 'shutil'):
        assert forbidden not in text, forbidden
    # And it publishes its own separate artifact identity.
    assert closeout.CAPABILITY != apply_service.CAPABILITY
    assert closeout.MODE_CLOSEOUT != apply_service.MODE_APPLY


# ═══════════════ 7. Workflow and governed constants ════════════════════════
def test_the_closeout_workflow_is_dispatch_only():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    for forbidden in ('schedule:', 'push:', 'pull_request:', 'repository_dispatch:',
                      'workflow_call:', 'workflow_run:', 'cron'):
        assert forbidden not in text, forbidden
    assert 'concurrency:' in text
    assert 'cancel-in-progress: false' in text
    assert 'retention-days: 30' in text


def test_the_closeout_workflow_validates_its_confirmation_first():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    steps = text.split('      - name: ')
    assert steps[1].startswith('Validate closeout confirmation'), steps[1][:60]
    assert 'VERIFY-2026-PITCHING-LINE-REPAIR-CLOSEOUT' in steps[1]
    # Secrets are checked for presence, never printed.
    assert 'echo "$DATABASE_URL' not in text
    assert 'echo "$SECRET_KEY' not in text
    # Confirmation precedes checkout.
    assert text.index('Validate closeout confirmation') < text.index('actions/checkout')


def test_the_closeout_workflow_contains_no_apply_or_mutation_command():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    for forbidden in ('run_official_pitching_line_repair_apply_2026', 'apply_reviewed_repair',
                      'alembic', 'flask db upgrade', 'db upgrade', '--confirm-apply',
                      'APPLY-2026-PITCHING-LINE-REPAIR'):
        assert forbidden not in text, forbidden
    assert 'run_official_pitching_line_repair_closeout_2026.py' in text
    assert 'database_writes_performed' in text


def _workflow_directives(path):
    """Workflow lines that actually DO something — comment lines removed, so prose that
    documents the absence of a retry cannot trip the guard."""
    return '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                     if not line.lstrip().startswith('#'))


def test_the_closeout_workflow_never_retries():
    directives = _workflow_directives(WORKFLOW_PATH)
    for forbidden in ('retry', 'max_attempts', 'continue-on-error: true', 'until ',
                      'while '):
        assert forbidden not in directives, forbidden
    # Exactly one invocation of the closeout command.
    assert directives.count('run_official_pitching_line_repair_closeout_2026.py') == 1


def test_the_closeout_confirmation_phrase_is_distinct_from_the_apply_phrase():
    assert closeout.CONFIRMATION_PHRASE == 'VERIFY-2026-PITCHING-LINE-REPAIR-CLOSEOUT'
    assert closeout.CONFIRMATION_PHRASE != apply_service.CONFIRMATION_PHRASE
    cli = CLI_PATH.read_text(encoding='utf-8')
    assert "CONFIRMATION_PHRASE = 'VERIFY-2026-PITCHING-LINE-REPAIR-CLOSEOUT'" in cli
    # The CLI refuses a wrong phrase ahead of its own imports.
    assert cli.index('if args.confirm_closeout != CONFIRMATION_PHRASE:') < cli.index(
        'from app import app')


def test_the_apply_fingerprint_and_confirmation_phrase_are_unchanged():
    assert (apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026
            == FINGERPRINT)
    assert apply_service.CONFIRMATION_PHRASE == 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06'
    assert apply_service.APPROVED_EXECUTION_CONTRACT['total_action_count'] == 675
    assert APPLY_WORKFLOW_PATH.read_text(encoding='utf-8').count(
        'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06') >= 1


def test_every_downstream_gate_stays_blocked_on_every_closeout_outcome(committed,
                                                                      monkeypatch):
    passing = _run()
    assert passing['result'] == closeout.RESULT_PASS
    for gate in closeout.DOWNSTREAM_GATES:
        assert passing[gate] == closeout.GATE_BLOCKED
        assert passing['downstream_gate_statuses'][gate] == closeout.GATE_BLOCKED

    monkeypatch.setattr(completeness, 'run_diagnostic',
                        lambda **kwargs: dict(clean_diagnostic(), result='fail',
                                              exit_code=1, stat_mismatch_count=2))
    failing = _run()
    assert failing['result'] == closeout.RESULT_FAIL
    for gate in closeout.DOWNSTREAM_GATES:
        assert failing[gate] == closeout.GATE_BLOCKED
    # A passing closeout makes Foundation 3A eligible for review; it opens nothing.
    assert passing['decision_reasons'] == [
        'foundation_3a_repair_closeout_ready_for_review']
    assert closeout.DOWNSTREAM_GATES == (
        'foundation_3b_gate', 'public_reader_gate', 'team_state_performance_gate',
        'share_card_performance_gate', 'sc_05_gate')


# ═══════════════ 8. Artifact completeness ══════════════════════════════════
def test_the_closeout_artifact_carries_every_required_field(committed):
    payload = _run()
    for field in (
        'capability', 'result', 'exit_code', 'decision_reasons', 'generated_at', 'git_sha',
        'migration_head', 'database_writes_performed', 'approved_manifest_fingerprint',
        'execution_ledger_verification', 'reviewed_amendment_verification',
        'completeness_verification', 'local_only_aggregation_verification',
        'local_only_applicable_reconciliations',
        'local_only_non_applicable_reconciliations',
        'official_validation_aggregation_verification',
        'official_validation_applicable_reconciliations',
        'present_checks', 'executed_checks', 'not_executed_checks', 'check_states',
        'failed_checks', 'unresolved_issues', 'downstream_gate_statuses',
    ):
        assert field in payload, field
    assert payload['exit_code'] == 0
    assert payload['capability'] == 'official_pitching_line_repair_closeout_2026_v1'
    assert payload['local_only_non_applicable_reconciliations'][
        'all_mandatory_metrics_match']['status'] == 'not_applicable_to_local_only'
    assert payload['official_validation_applicable_reconciliations'][
        'all_mandatory_metrics_match'] is True
    # No credential or connection detail is ever recorded.
    encoded = repr(payload)
    for forbidden in ('postgres://', 'postgresql://', 'password', 'DATABASE_URL'):
        assert forbidden not in encoded, forbidden
