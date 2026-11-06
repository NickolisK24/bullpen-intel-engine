"""WP-0.2 (EOS-007): the shadow validator reads what run_due_sync really writes.

Since the Render-primary cutover the scheduled workflow writes its summary with
``scripts/run_due_sync.py``, which wraps the legacy runner summary in
``result``. The validator only understood the legacy shape, so every cycle
failed as ``validator_reported_failure`` and the workflow was red by
construction. These tests feed the real producer's output to the consumer.
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts import validate_game_driven_shadow_cycle as validator
from tests import test_game_driven_shadow_activation_validator as legacy


def _due_summary(cycle_kind, due_status, *, legacy_summary=None, result_extra=None):
    """The exact shape run_due_sync.main writes (scripts/run_due_sync.py)."""
    inner = legacy_summary if legacy_summary is not None else legacy._summary(cycle_kind)
    if due_status == validator.DUE_STATUS_ALREADY_SATISFIED:
        result = {
            'status': due_status, 'executed': False,
            'satisfied_by_attempt_id': 548, 'execution': {'outcome': 'already_satisfied'},
        }
    else:
        result = {
            'status': due_status, 'executed': True, 'execution': {'outcome': due_status},
            'publication_proof': inner['publication_proof'], 'sync': inner['sync'],
            'distribution_delivery': {'status': 'skipped'},
        }
    result.update(result_extra or {})
    return {
        'status': due_status, 'mode': cycle_kind, 'source': 'github_schedule',
        'intended_window': f'{cycle_kind}:2026-11-05',
        'scheduled_for': '2026-11-05T10:17:00+00:00', 'result': result,
    }


@pytest.mark.parametrize('cycle_kind', ['daily', 'postgame'])
def test_executed_due_cycle_with_a_healthy_lane_passes(cycle_kind):
    decision = validator.validate_cycle(
        _due_summary(cycle_kind, 'executed'), cycle_kind=cycle_kind, runner_exit_code=0,
    )
    assert decision['result'] == validator.RESULT_PASS, decision.get('failed_invariants')
    assert decision['sync_status'] == 'success'


@pytest.mark.parametrize('cycle_kind', ['daily', 'postgame'])
def test_already_satisfied_window_is_a_labelled_no_op(cycle_kind):
    decision = validator.validate_cycle(
        _due_summary(cycle_kind, 'already_satisfied'), cycle_kind=cycle_kind, runner_exit_code=0,
    )
    assert decision['result'] == validator.RESULT_PASS
    # Not proof of lane health: it is recorded as a distinct no-op.
    assert decision['work_state'] == validator.WORK_STATE_ALREADY_SATISFIED
    assert decision['due_status'] == 'already_satisfied'


def test_already_satisfied_without_its_proof_still_fails():
    summary = _due_summary('daily', 'already_satisfied', result_extra={'satisfied_by_attempt_id': None})
    decision = validator.validate_cycle(summary, cycle_kind='daily', runner_exit_code=0)
    assert decision['result'] == validator.RESULT_FAILED


@pytest.mark.parametrize('due_status', ['failed', 'blocked'])
def test_failed_or_blocked_due_runs_are_real_failures(due_status):
    decision = validator.validate_cycle(
        _due_summary('daily', due_status), cycle_kind='daily', runner_exit_code=1,
    )
    assert decision['result'] == validator.RESULT_FAILED
    assert 'due_outcome' in {item['invariant'] for item in decision['failed_invariants']}


def test_executed_cycle_with_an_unverified_daily_proof_still_fails():
    inner = legacy._summary('daily', proof={'verified': False})
    decision = validator.validate_cycle(
        _due_summary('daily', 'executed', legacy_summary=inner), cycle_kind='daily',
        runner_exit_code=0,
    )
    assert decision['result'] == validator.RESULT_FAILED


def test_legacy_runner_summary_is_still_accepted():
    decision = validator.validate_cycle(legacy._summary('daily'), cycle_kind='daily', runner_exit_code=0)
    assert decision['result'] == validator.RESULT_PASS


def test_real_run_due_sync_output_is_accepted_by_the_validator(monkeypatch, tmp_path):
    """Producer -> consumer: write the summary with run_due_sync.main itself."""
    from scripts import run_due_sync
    from services import sync_due, sync_execution_context

    inner = legacy._summary('daily')
    context = SimpleNamespace(
        mode='daily', source='github_schedule', intended_window='daily:2026-11-05',
        scheduled_for=datetime(2026, 11, 5, 10, 17, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(sync_execution_context, 'validate_execution_context', lambda **kwargs: context)
    monkeypatch.setattr(sync_due, 'run_due_sync', lambda app, ctx, **kwargs: {
        'status': 'executed', 'executed': True, 'execution': {'outcome': 'executed'},
        'publication_proof': inner['publication_proof'], 'sync': inner['sync'],
    })
    output = tmp_path / 'daily-sync-summary.json'
    exit_code = run_due_sync.main([
        '--mode', 'daily', '--execution-source', 'github_schedule',
        '--scheduled-for', '2026-11-05T10:17:00Z', '--output', str(output),
    ])
    assert exit_code == 0
    written = json.loads(output.read_text())
    assert 'result' in written and 'sync' not in written
    decision = validator.validate_cycle(written, cycle_kind='daily', runner_exit_code=exit_code)
    assert decision['result'] == validator.RESULT_PASS, decision.get('failed_invariants')
