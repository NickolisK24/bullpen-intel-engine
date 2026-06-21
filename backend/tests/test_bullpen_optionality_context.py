from datetime import date, timedelta
from types import SimpleNamespace

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.bullpen_optionality_context import (
    CAPABILITY,
    NO_OPTIONALITY_DATA_LIMITATION,
    build_bullpen_optionality_context,
)


REF = date(2026, 6, 20)


def pitcher(player_id, name=None):
    return SimpleNamespace(
        id=player_id + 100000,
        mlb_id=player_id,
        full_name=name or f'Pitcher {player_id}',
    )


def record(
    player_id,
    *,
    status=STATUS_AVAILABLE,
    name=None,
    reasons=None,
    inputs=None,
    data_state='fresh',
    confidence='high',
):
    return {
        'pitcher_id': player_id + 100000,
        'pitcher': pitcher(player_id, name=name),
        'availability': {
            'availability_status': status,
            'reasons': reasons or [],
            'inputs': inputs or {
                'appearances_last_5_days': 1,
                'pitches_last_5_days': 12,
                'pitches_last_3_days': 12,
                'pitches_yesterday': 0,
                'back_to_back': False,
            },
            'data_state': data_state,
            'confidence': confidence,
        },
    }


def log(player_id, days_ago, *, pitches=12, outs=3, game_pk=None):
    return SimpleNamespace(
        pitcher_id=player_id + 100000,
        mlb_game_pk=game_pk or (900000 + player_id),
        game_date=REF - timedelta(days=days_ago),
        game_type='R',
        games_started=0,
        pitches_thrown=pitches,
        innings_pitched_outs=outs,
        innings_pitched=outs / 3.0,
    )


def context(records, logs_by_pitcher=None):
    return build_bullpen_optionality_context(
        records,
        logs_by_pitcher=logs_by_pitcher or {},
        reference_date=REF,
    )


def test_fully_flexible_bullpen_reads_deep_optionality():
    records = [
        record(player_id, name=f'Clean Arm {player_id}')
        for player_id in range(1, 7)
    ]
    logs = {
        player_id + 100000: [log(player_id, 2)]
        for player_id in range(1, 7)
    }

    result = context(records, logs)

    assert result['capability'] == CAPABILITY
    assert result['available_arms_count'] == 6
    assert result['monitor_arms_count'] == 0
    assert result['restricted_arms_count'] == 0
    assert len(result['clean_workload_options']) == 6
    assert result['secondary_options'] == []
    assert result['practical_close_game_paths_count'] == 6
    assert result['optionality_band'] == 'deep'


def test_narrow_bullpen_with_few_clean_options():
    result = context([
        record(1, name='Clean One'),
        record(2, name='Clean Two'),
        record(3, status=STATUS_MONITOR, name='Monitor One', reasons=['recent workload']),
        record(4, status=STATUS_MONITOR, name='Monitor Two', reasons=['recent workload']),
        record(5, status=STATUS_LIMITED, name='Limited Arm'),
    ])

    assert result['available_arms_count'] == 2
    assert result['monitor_arms_count'] == 2
    assert result['restricted_arms_count'] == 1
    assert len(result['clean_workload_options']) == 2
    assert len(result['secondary_options']) == 2
    assert result['practical_close_game_paths_count'] == 3
    assert result['optionality_band'] == 'narrow'


def test_many_available_arms_can_still_have_few_clean_workload_options():
    warning_inputs = {
        'appearances_last_5_days': 2,
        'pitches_last_5_days': 24,
        'pitches_last_3_days': 24,
        'pitches_yesterday': 0,
        'back_to_back': False,
    }
    result = context([
        record(1, name='Clean One'),
        record(2, name='Clean Two'),
        record(3, name='Caution Three', inputs=warning_inputs),
        record(4, name='Caution Four', inputs=warning_inputs),
        record(5, name='Caution Five', reasons=['recent workload']),
        record(6, name='Caution Six', reasons=['recent workload']),
    ])

    assert result['available_arms_count'] == 6
    assert len(result['clean_workload_options']) == 2
    assert len(result['secondary_options']) == 4
    assert result['practical_close_game_paths_count'] == 4
    assert result['optionality_band'] == 'flexible'


def test_monitor_arms_count_as_secondary_options():
    result = context([
        record(1, name='Clean One'),
        record(2, name='Clean Two'),
        record(3, status=STATUS_MONITOR, name='Monitor One', reasons=['Back-to-back appearances']),
        record(4, status=STATUS_MONITOR, name='Monitor Two', reasons=['18 pitches yesterday']),
        record(5, status=STATUS_MONITOR, name='Monitor Three'),
        record(6, status=STATUS_MONITOR, name='Monitor Four'),
    ])

    assert result['monitor_arms_count'] == 4
    assert len(result['secondary_options']) == 4
    by_player = {option['player_id']: option for option in result['secondary_options']}
    assert by_player[3]['reason'] == 'Back-to-back appearances'
    assert result['practical_close_game_paths_count'] == 4
    assert result['optionality_band'] == 'flexible'


def test_limited_avoid_and_unavailable_arms_are_excluded_from_practical_paths():
    result = context([
        record(1, name='Clean One'),
        record(2, status=STATUS_LIMITED, name='Limited Arm'),
        record(3, status=STATUS_AVOID, name='Avoid Arm'),
        record(4, status=STATUS_UNAVAILABLE, name='Unavailable Arm'),
    ])

    assert result['available_arms_count'] == 1
    assert result['restricted_arms_count'] == 3
    assert result['limited_arms_count'] == 1
    assert result['avoid_arms_count'] == 1
    assert result['unavailable_arms_count'] == 1
    assert result['practical_close_game_paths_count'] == 1
    assert result['optionality_band'] == 'thin'


def test_zero_ip_zero_pitch_artifacts_do_not_affect_last_workload():
    records = [record(1, name='Clean One')]
    logs = {
        100001: [
            log(1, 0, pitches=0, outs=0),
            log(1, 2, pitches=14, outs=3),
        ],
    }

    result = context(records, logs)

    assert result['clean_workload_options'] == [{
        'player_id': 1,
        'name': 'Clean One',
        'availability': STATUS_AVAILABLE,
        'last_workload': '2 days ago',
        'recent_workload': 'light',
    }]
    assert result['practical_close_game_paths_count'] == 1


def test_incomplete_data_returns_safe_neutral_values():
    result = context([])

    assert result['context_available'] is False
    assert result['available_arms_count'] == 0
    assert result['monitor_arms_count'] == 0
    assert result['restricted_arms_count'] == 0
    assert result['clean_workload_options'] == []
    assert result['secondary_options'] == []
    assert result['practical_close_game_paths_count'] == 0
    assert result['optionality_band'] == 'insufficient_data'
    assert NO_OPTIONALITY_DATA_LIMITATION in result['limitations']


def test_doubleheader_workload_inputs_do_not_duplicate_bullpen_paths():
    result = context(
        [
            record(
                1,
                status=STATUS_MONITOR,
                name='Doubleheader Arm',
                reasons=['2 appearances in 5 days'],
            ),
            record(2, name='Clean Arm'),
        ],
        {
            100001: [
                log(1, 1, pitches=12, outs=3, game_pk=101),
                log(1, 1, pitches=13, outs=3, game_pk=102),
            ],
            100002: [log(2, 3)],
        },
    )

    assert result['monitor_arms_count'] == 1
    assert len(result['secondary_options']) == 1
    assert result['secondary_options'][0]['player_id'] == 1
    assert result['practical_close_game_paths_count'] == 1
    assert result['optionality_band'] == 'thin'
