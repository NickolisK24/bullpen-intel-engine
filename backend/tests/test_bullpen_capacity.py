from services.bullpen_capacity import (
    COUNT_BASED_LIMITATION,
    NO_TRUST_ARM_LIMITATION,
    UNAVAILABLE_ZERO_OUTS_LIMITATION,
    UNKNOWN_CAPACITY_LIMITATION,
    WEIGHTING_COUNT_BASED,
    WEIGHTING_SEASON_RELIEF_OUTS,
    build_team_bullpen_capacity,
)


def record(
    pitcher_id,
    *,
    role_key='bridge_arm',
    read_key='clean_option',
    availability_status='Available',
    data_state='fresh',
    confidence='high',
    roster_active=True,
    roster_inactive=False,
    eligibility=True,
):
    return {
        'pitcher_id': pitcher_id,
        'name': f'Pitcher {pitcher_id}',
        'availability': {
            'availability_status': availability_status,
            'data_state': data_state,
            'confidence': confidence,
        },
        'pitcher_labels': {
            'role': {'key': role_key, 'label': 'Trust Arm' if role_key == 'trust_arm' else 'Bridge Arm'},
            'read': {'key': read_key, 'label': 'Unavailable' if read_key == 'unavailable' else 'Clean Option'},
        },
        'roster_status': {
            'is_active_mlb': roster_active,
            'is_inactive_context': roster_inactive,
        },
        'eligibility': {'eligible': eligibility},
    }


def capacity(records, relief_outs=None):
    return build_team_bullpen_capacity(
        records,
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
        relief_outs_by_pitcher=relief_outs or {},
    )


def test_no_unavailable_relievers_reads_clear_with_weighted_workload():
    result = capacity(
        [
            record(1, role_key='trust_arm'),
            record(2),
            record(3),
        ],
        relief_outs={1: 12, 2: 12, 3: 12},
    )

    loss = result['capacity_loss']
    assert loss['status'] == 'clear'
    assert loss['available_capacity_pct'] == 100
    assert loss['unavailable_capacity_pct'] == 0
    assert loss['unavailable_pitcher_count'] == 0
    assert loss['weighting']['method'] == WEIGHTING_SEASON_RELIEF_OUTS
    assert loss['limitations'] == []


def test_inactive_roster_relievers_count_as_unavailable_capacity():
    result = capacity(
        [
            record(1),
            record(2),
            record(3, roster_active=False, roster_inactive=True),
            record(4, roster_active=False, roster_inactive=True),
        ],
        relief_outs={1: 9, 2: 9, 3: 9, 4: 9},
    )

    loss = result['capacity_loss']
    assert loss['status'] == 'constrained'
    assert loss['available_capacity_pct'] == 50
    assert loss['unavailable_capacity_pct'] == 50
    assert loss['inactive_roster_unavailable_capacity_pct'] == 50
    assert loss['inactive_roster_unavailable_pitcher_count'] == 2
    assert loss['total_bullpen_pitcher_count'] == 4


def test_unavailable_trust_arm_drives_trust_capacity_loss():
    result = capacity(
        [
            record(1, role_key='trust_arm'),
            record(2, role_key='trust_arm', read_key='unavailable', availability_status='Unavailable'),
            record(3),
        ],
        relief_outs={1: 10, 2: 20, 3: 10},
    )

    trust = result['trust_capacity_loss']
    assert trust['status'] == 'constrained'
    assert trust['trust_arms_available'] == 1
    assert trust['trust_arms_total'] == 2
    assert trust['trust_arms_unavailable'] == 1
    assert trust['trust_capacity_unavailable_pct'] == 67


def test_limited_workload_sample_falls_back_to_count_based_weighting():
    result = capacity(
        [
            record(1),
            record(2),
            record(3),
        ],
        relief_outs={1: 3},
    )

    loss = result['capacity_loss']
    assert loss['weighting']['method'] == WEIGHTING_COUNT_BASED
    assert COUNT_BASED_LIMITATION in loss['limitations']


def test_unavailable_zero_out_arm_forces_count_based_weighting():
    result = capacity(
        [
            record(1),
            record(2),
            record(3),
            record(4, read_key='unavailable', availability_status='Unavailable'),
        ],
        relief_outs={1: 12, 2: 12, 3: 12},
    )

    loss = result['capacity_loss']
    assert loss['weighting']['method'] == WEIGHTING_COUNT_BASED
    assert loss['weighting']['sample']['pitchers_with_relief_outs'] == 3
    assert loss['weighting']['sample']['unavailable_pitchers_without_relief_outs'] == 1
    assert loss['available_capacity_pct'] == 75
    assert loss['unavailable_capacity_pct'] == 25
    assert UNAVAILABLE_ZERO_OUTS_LIMITATION in loss['limitations']


def test_non_bullpen_records_are_excluded_and_ambiguous_roles_do_not_become_trust():
    result = capacity(
        [
            record(1, role_key='limited_read'),
            record(2, role_key='trust_arm', eligibility=False),
        ],
        relief_outs={1: 12, 2: 12},
    )

    loss = result['capacity_loss']
    trust = result['trust_capacity_loss']
    assert loss['total_bullpen_pitcher_count'] == 1
    assert loss['available_pitcher_count'] == 1
    assert trust['status'] == 'limited_read'
    assert trust['trust_arms_total'] == 0
    assert NO_TRUST_ARM_LIMITATION in trust['limitations']


def test_weighted_percentage_math_uses_relief_capacity_not_pitcher_count():
    result = capacity(
        [
            record(1),
            record(2),
            record(3, read_key='unavailable', availability_status='Unavailable'),
        ],
        relief_outs={1: 20, 2: 20, 3: 20},
    )

    loss = result['capacity_loss']
    assert loss['status'] == 'elevated'
    assert loss['available_capacity_pct'] == 67
    assert loss['unavailable_capacity_pct'] == 33
    assert loss['summary'] == 'The bullpen is operating with 33% of measured relief capacity unavailable.'


def test_limited_read_capacity_is_separate_from_unavailable_capacity():
    result = capacity(
        [
            record(1),
            record(2, read_key='limited_read', data_state='missing', confidence='low'),
            record(3, read_key='unavailable', availability_status='Unavailable'),
        ],
        relief_outs={1: 12, 2: 12, 3: 12},
    )

    loss = result['capacity_loss']
    assert loss['available_capacity_pct'] == 33
    assert loss['unknown_limited_read_capacity_pct'] == 33
    assert loss['unavailable_capacity_pct'] == 33
    assert loss['unknown_limited_read_pitcher_count'] == 1
    assert UNKNOWN_CAPACITY_LIMITATION in loss['limitations']


def test_monitor_limited_and_avoid_arms_are_not_fully_unavailable_capacity():
    result = capacity(
        [
            record(1, read_key='watch_arm', availability_status='Monitor'),
            record(2, read_key='rest_restricted', availability_status='Limited'),
            record(3, read_key='rest_restricted', availability_status='Avoid'),
            record(4, read_key='unavailable', availability_status='Unavailable'),
        ],
        relief_outs={1: 12, 2: 12, 3: 12, 4: 12},
    )

    loss = result['capacity_loss']
    assert loss['available_pitcher_count'] == 3
    assert loss['unavailable_pitcher_count'] == 1
    assert loss['available_capacity_pct'] == 75
    assert loss['unavailable_capacity_pct'] == 25


def test_capacity_payload_defines_available_as_not_fully_unavailable():
    result = capacity([
        record(1),
        record(2, read_key='watch_arm', availability_status='Monitor'),
    ])

    definition = result['capacity_loss']['definitions']['available_capacity_pct']
    assert 'not classified as fully unavailable' in definition
    assert 'not be read as clean or fully available capacity' in definition
    assert 'Limited-read or unknown capacity is reported separately' in definition
