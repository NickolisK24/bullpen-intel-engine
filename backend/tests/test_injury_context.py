from datetime import date, timedelta
from types import SimpleNamespace

from services.injury_context import CAPABILITY, build_injury_context
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_OPTIONED,
    STATUS_RESTRICTED,
)


REF = date(2026, 6, 20)


def pitcher(
    player_id,
    name=None,
    *,
    position='RP',
    roster_status=STATUS_ACTIVE,
    team_id=1,
):
    return SimpleNamespace(
        id=player_id + 100000,
        mlb_id=player_id,
        full_name=name or f'Pitcher {player_id}',
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position=position,
        active=True,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
    )


def active_record(p):
    return {
        'pitcher': p,
        'availability': {
            'roster_status': {
                'status': STATUS_ACTIVE,
                'is_active_mlb': True,
            },
        },
    }


def log(player_id, days_ago, *, games_started=0, outs=3):
    return SimpleNamespace(
        pitcher_id=player_id + 100000,
        game_date=REF - timedelta(days=days_ago),
        games_started=games_started,
        innings_pitched_outs=outs,
        innings_pitched=outs / 3.0,
    )


def context(pitchers, *, active=None, logs_by_pitcher=None):
    return build_injury_context(
        pitchers,
        active_records=active or [],
        logs_by_pitcher=logs_by_pitcher or {},
        reference_date=REF,
    )


def test_team_with_no_inactive_bullpen_arms_reads_no_depth_pressure():
    active = [
        pitcher(1, 'Active One'),
        pitcher(2, 'Active Two'),
    ]

    result = context(active, active=[active_record(p) for p in active])

    assert result['capability'] == CAPABILITY
    assert result['context_available'] is True
    assert result['active_bullpen_arms_count'] == 2
    assert result['inactive_bullpen_arms_count'] == 0
    assert result['il_bullpen_arms_count'] == 0
    assert result['non_il_inactive_bullpen_arms_count'] == 0
    assert result['inactive_bullpen_share'] == 0.0
    assert result['depth_pressure_band'] == 'none'
    assert result['injury_context_confidence'] == 'high'
    assert result['inactive_bullpen_arms'] == []


def test_one_inactive_bullpen_arm_reads_light_pressure():
    active = pitcher(1, 'Active One')
    inactive = pitcher(2, 'IL Arm', roster_status=STATUS_IL_15)

    result = context([active, inactive], active=[active_record(active)])

    assert result['active_bullpen_arms_count'] == 1
    assert result['inactive_bullpen_arms_count'] == 1
    assert result['il_bullpen_arms_count'] == 1
    assert result['non_il_inactive_bullpen_arms_count'] == 0
    assert result['inactive_bullpen_share'] == 50.0
    assert result['depth_pressure_band'] == 'light'
    assert result['inactive_bullpen_arms'] == [{
        'player_id': 2,
        'name': 'IL Arm',
        'status': '15-Day IL',
        'status_type': 'IL',
        'is_on_active_roster': False,
    }]


def test_multiple_il_bullpen_arms_read_moderate_pressure():
    active = [pitcher(idx, f'Active {idx}') for idx in range(1, 4)]
    inactive = [
        pitcher(10, 'First IL Arm', roster_status=STATUS_IL_15),
        pitcher(11, 'Second IL Arm', roster_status=STATUS_IL_60),
        pitcher(12, 'Third IL Arm', roster_status=STATUS_IL_15),
    ]

    result = context([*active, *inactive], active=[active_record(p) for p in active])

    assert result['active_bullpen_arms_count'] == 3
    assert result['inactive_bullpen_arms_count'] == 3
    assert result['il_bullpen_arms_count'] == 3
    assert result['non_il_inactive_bullpen_arms_count'] == 0
    assert result['inactive_bullpen_share'] == 50.0
    assert result['depth_pressure_band'] == 'moderate'


def test_non_il_inactive_pitchers_are_counted_separately():
    active = pitcher(1, 'Active One')
    inactive = [
        pitcher(20, 'Optioned Arm', roster_status=STATUS_OPTIONED),
        pitcher(21, 'Restricted Arm', roster_status=STATUS_RESTRICTED),
        pitcher(22, 'Forty Man Arm', roster_status=STATUS_40_MAN_ONLY),
    ]

    result = context([active, *inactive], active=[active_record(active)])

    assert result['inactive_bullpen_arms_count'] == 3
    assert result['il_bullpen_arms_count'] == 0
    assert result['non_il_inactive_bullpen_arms_count'] == 3
    assert result['depth_pressure_band'] == 'moderate'
    assert {arm['status_type'] for arm in result['inactive_bullpen_arms']} == {
        'NON_IL_INACTIVE',
    }


def test_active_bullpen_arms_only_keep_high_confidence():
    active = [
        pitcher(1, 'Active One'),
        pitcher(2, 'Active Two'),
        pitcher(3, 'Active Three'),
    ]

    result = context(active, active=[active_record(p) for p in active])

    assert result['active_bullpen_arms_count'] == 3
    assert result['inactive_bullpen_arms_count'] == 0
    assert result['depth_pressure_band'] == 'none'
    assert result['injury_context_confidence'] == 'high'
    assert result['injury_context_summary_inputs'] == {
        'active_count': 3,
        'inactive_count': 0,
        'il_count': 0,
        'non_il_inactive_count': 0,
        'inactive_share': 0.0,
        'depth_pressure_band': 'none',
        'confidence': 'high',
    }


def test_role_uncertainty_produces_medium_confidence():
    active = pitcher(1, 'Active One')
    uncertain = pitcher(30, 'Uncertain Pitcher', position='P', roster_status=STATUS_IL_15)

    result = context([active, uncertain], active=[active_record(active)])

    assert result['inactive_bullpen_arms_count'] == 1
    assert result['role_uncertain_inactive_count'] == 1
    assert result['injury_context_confidence'] == 'medium'
    assert result['inactive_bullpen_arms'][0]['name'] == 'Uncertain Pitcher'


def test_position_players_are_excluded_from_bullpen_injury_context():
    active = pitcher(1, 'Active One')
    position_player = pitcher(
        40,
        'Inactive Position Player',
        position='1B',
        roster_status=STATUS_IL_15,
    )

    result = context([active, position_player], active=[active_record(active)])

    assert result['inactive_bullpen_arms_count'] == 0
    assert result['excluded_position_player_count'] == 1
    assert result['depth_pressure_band'] == 'none'


def test_starters_are_excluded_when_safely_identifiable():
    active = pitcher(1, 'Active One')
    starter = pitcher(50, 'Inactive Starter', position='P', roster_status=STATUS_IL_15)

    result = context(
        [active, starter],
        active=[active_record(active)],
        logs_by_pitcher={
            starter.id: [
                log(50, 1, games_started=1, outs=18),
                log(50, 6, games_started=1, outs=18),
            ],
        },
    )

    assert result['inactive_bullpen_arms_count'] == 0
    assert result['excluded_starting_pitcher_count'] == 1
    assert result['inactive_bullpen_arms'] == []


def test_safe_neutral_output_when_roster_status_data_is_incomplete():
    unknown = pitcher(60, 'Unknown Status Arm', position='RP', roster_status=None)

    result = context([unknown])

    assert result['context_available'] is False
    assert result['active_bullpen_arms_count'] == 0
    assert result['inactive_bullpen_arms_count'] == 0
    assert result['inactive_bullpen_share'] is None
    assert result['depth_pressure_band'] == 'insufficient_data'
    assert result['injury_context_confidence'] == 'low'
    assert result['unknown_roster_status_count'] == 1
