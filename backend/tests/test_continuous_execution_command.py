import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

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


def test_cycle_summary_preserves_true_boolean_safety_values():
    payload = cycle_payload(
        production_authority_affected=True,
        timeout_reached=True,
        source_budget_exhausted=True,
        circuit_breaker_open=True,
    )

    summary = json.loads(command.render_output(payload)[0])

    assert summary['production_authority_affected'] is True
    assert summary['timeout_reached'] is True
    assert summary['source_budget_exhausted'] is True
    assert summary['circuit_breaker_open'] is True


@pytest.mark.parametrize('field', [
    'production_authority_affected',
    'timeout_reached',
    'source_budget_exhausted',
    'circuit_breaker_open',
])
def test_cycle_summary_rejects_non_boolean_safety_values(field):
    payload = cycle_payload(**{field: 'false'})

    with pytest.raises(TypeError, match=field):
        command.render_output(payload)


def test_rejected_observation_emits_existing_detector_fields():
    payload = cycle_payload(
        rejected_observations=1,
        detection_results=[{
            'game_pk': 823665,
            'classification': 'stale_observation',
            'changed': False,
            'reason': 'older_source_observation',
            'finality_state': 'final_pending_data',
            'source_authority': 'mlb_statsapi_live_feed_v1_1',
            'previous_observation_identity': 'accepted-fingerprint',
            'current_observation_identity': 'incoming-fingerprint',
            'differences': {},
        }],
    )

    lines = command.render_output(payload)

    assert len(lines) == 2
    assert json.loads(lines[1]) == {
        'event': 'game_rejected',
        'game_pk': 823665,
        'classification': 'stale_observation',
        'reason': 'older_source_observation',
        'finality': 'final_pending_data',
        'source_authority': 'mlb_statsapi_live_feed_v1_1',
        'previous_observation_identity': 'accepted-fingerprint',
        'current_observation_identity': 'incoming-fingerprint',
    }


def test_two_rejected_observations_emit_exactly_two_lines():
    payload = cycle_payload(
        rejected_observations=2,
        unchanged_games=1,
        detection_results=[
            {
                'game_pk': 823665,
                'classification': 'stale_observation',
                'changed': False,
                'reason': 'weaker_source_authority',
            },
            {
                'game_pk': 823666,
                'classification': 'ambiguous_observation',
                'changed': False,
                'reason': 'missing_source_observation_order',
            },
            {
                'game_pk': 823667,
                'classification': 'unchanged',
                'changed': False,
                'reason': 'material_fingerprint_match',
            },
        ],
    )

    lines = command.render_output(payload)
    rejected = [
        json.loads(line) for line in lines
        if json.loads(line)['event'] == 'game_rejected'
    ]

    assert len(lines) == 3
    assert [item['game_pk'] for item in rejected] == [823665, 823666]
    assert [item['classification'] for item in rejected] == [
        'stale_observation', 'ambiguous_observation',
    ]
    assert [item['reason'] for item in rejected] == [
        'weaker_source_authority', 'missing_source_observation_order',
    ]


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
