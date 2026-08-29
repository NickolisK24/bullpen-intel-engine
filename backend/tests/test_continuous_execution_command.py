import json
from contextlib import nullcontext
from types import SimpleNamespace

from scripts import run_continuous_cycle as command


def cycle_payload(**overrides):
    value = {
        'mode': 'shadow_detect',
        'sync_run_id': 1125,
        'games_checked': 15,
        'changed_games': 0,
        'unchanged_games': 15,
        'rejected_observations': 0,
        'source_failures': 0,
        'failures': [],
        'source_requests': 16,
        'source_retries': 0,
        'runtime_ms': 1225.0,
        'status': 'complete',
        'reason_code': 'cycle_complete',
        'canonical_actions': 0,
        'canonical_mutation_games': 0,
        'live_publications': 0,
        'cache_handoffs': 0,
        'production_authority_affected': False,
        'timeout_reached': False,
        'source_budget_exhausted': False,
        'circuit_breaker_open': False,
        'detection_results': [],
    }
    value.update(overrides)
    return value


def test_unchanged_cycle_emits_one_summary_without_game_lines():
    payload = cycle_payload(detection_results=[{
        'game_pk': 824392,
        'classification': 'unchanged',
        'changed': False,
        'finality_state': 'not_final',
        'differences': {},
    }])

    lines = command.render_output(payload)

    assert len(lines) == 1
    summary = json.loads(lines[0])
    assert summary == {
        'event': 'continuous_cycle',
        'mode': 'shadow_detect',
        'sync_run_id': 1125,
        'games_checked': 15,
        'changed_games': 0,
        'unchanged_games': 15,
        'rejected_observations': 0,
        'source_failures': 0,
        'failures': 0,
        'source_requests': 16,
        'source_retries': 0,
        'runtime_ms': 1225.0,
        'status': 'complete',
        'reason_code': 'cycle_complete',
        'canonical_actions': 0,
        'canonical_mutation_games': 0,
        'live_publications': 0,
        'cache_handoffs': 0,
        'production_authority_affected': False,
        'timeout_reached': False,
        'source_budget_exhausted': False,
        'circuit_breaker_open': False,
    }


def test_changed_cycle_emits_summary_and_changed_observations_only():
    payload = cycle_payload(
        changed_games=2,
        unchanged_games=13,
        detection_results=[
            {
                'game_pk': 824392,
                'classification': 'changed',
                'changed': True,
                'finality_state': 'not_final',
                'differences': {
                    'status': {'old': 'Preview', 'new': 'Live'},
                    'inning': {'old': 1, 'new': 2},
                },
            },
            {
                'game_pk': 824393,
                'classification': 'unchanged',
                'changed': False,
                'finality_state': 'not_final',
                'differences': {},
            },
            {
                'game_pk': 824394,
                'classification': 'finalized',
                'changed': True,
                'finality_state': 'final_and_usable',
                'differences': {'status': {'old': 'Live', 'new': 'Final'}},
            },
        ],
    )

    lines = command.render_output(payload)

    assert len(lines) == 3
    assert json.loads(lines[0])['changed_games'] == 2
    assert json.loads(lines[1]) == {
        'event': 'game_changed',
        'game_pk': 824392,
        'classification': 'changed',
        'finality': 'not_final',
        'differences': ['status', 'inning'],
    }
    assert json.loads(lines[2]) == {
        'event': 'game_changed',
        'game_pk': 824394,
        'classification': 'finalized',
        'finality': 'final_and_usable',
        'differences': ['status'],
    }


def test_failure_summary_preserves_failure_and_safety_state():
    payload = cycle_payload(
        status='partial',
        reason_code='cycle_completed_with_failures',
        source_failures=2,
        failures=[{'scope': 'detection'}, {'scope': 'source'}],
        timeout_reached=True,
        source_budget_exhausted=True,
        circuit_breaker_open=True,
    )

    summary = json.loads(command.render_output(payload)[0])

    assert summary['status'] == 'partial'
    assert summary['reason_code'] == 'cycle_completed_with_failures'
    assert summary['source_failures'] == 2
    assert summary['failures'] == 2
    assert summary['timeout_reached'] is True
    assert summary['source_budget_exhausted'] is True
    assert summary['circuit_breaker_open'] is True
    assert summary['canonical_actions'] == 0
    assert summary['canonical_mutation_games'] == 0
    assert summary['live_publications'] == 0
    assert summary['cache_handoffs'] == 0
    assert summary['production_authority_affected'] is False


def test_full_json_preserves_complete_existing_payload():
    payload = cycle_payload(extra_debug_field={'nested': [1, 2, 3]})

    lines = command.render_output(payload, full_json=True)

    assert len(lines) == 1
    assert json.loads(lines[0]) == payload
    assert '\n' in lines[0]


def test_exit_code_contract_is_unchanged():
    assert command.exit_code(cycle_payload(status='off')) == 0
    assert command.exit_code(cycle_payload(status='complete')) == 0
    assert command.exit_code(cycle_payload(status='skipped')) == 0
    assert command.exit_code(cycle_payload(status='partial')) == 1
    assert command.exit_code(cycle_payload(status='blocked')) == 1


def test_main_defaults_to_compact_output(monkeypatch, capsys):
    payload = cycle_payload()
    monkeypatch.setattr(command, 'app', SimpleNamespace(app_context=nullcontext))
    monkeypatch.setattr(
        command, 'run_continuous_cycle',
        lambda **_kwargs: SimpleNamespace(to_dict=lambda: payload),
    )
    monkeypatch.setattr(command.sys, 'argv', ['run_continuous_cycle.py'])

    assert command.main() == 0

    output = capsys.readouterr().out.strip()
    assert '\n' not in output
    assert json.loads(output)['event'] == 'continuous_cycle'


def test_main_full_json_and_failure_exit_remain_available(monkeypatch, capsys):
    payload = cycle_payload(status='partial')
    monkeypatch.setattr(command, 'app', SimpleNamespace(app_context=nullcontext))
    monkeypatch.setattr(
        command, 'run_continuous_cycle',
        lambda **_kwargs: SimpleNamespace(to_dict=lambda: payload),
    )
    monkeypatch.setattr(
        command.sys, 'argv', ['run_continuous_cycle.py', '--full-json'],
    )

    assert command.main() == 1

    output = capsys.readouterr().out
    assert '\n' in output.strip()
    assert json.loads(output) == payload
