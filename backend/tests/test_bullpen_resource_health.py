import pytest

from services.availability import STATUS_AVAILABLE, STATUS_UNAVAILABLE
from services.bullpen_capacity import build_team_bullpen_capacity
from services.bullpen_resource_health import (
    CAPABILITY,
    INCOMPLETE_RESOURCE_LIMITATION,
    RESOURCE_STATE_DEPLETED,
    RESOURCE_STATE_MODERATE,
    RESOURCE_STATE_STRAINED,
    RESOURCE_STATE_STRONG,
    STATE_DEPLETED,
    STATE_HEALTHY,
    STATE_REDUCED,
    STATE_THIN,
    STATE_UNKNOWN,
    build_bullpen_resource_health,
    classify_bullpen_capacity_state,
    classify_resource_health_state,
)
from services.roster_status import (
    STATUS_ACTIVE,
    STATUS_IL_15,
    STATUS_MINORS,
    STATUS_UNKNOWN,
)


def record(
    pitcher_id,
    *,
    roster_status=STATUS_ACTIVE,
    active_mlb=True,
    inactive_context=False,
    availability_status=STATUS_AVAILABLE,
    read_key='clean_option',
    eligibility=True,
):
    return {
        'pitcher_id': pitcher_id,
        'name': f'Pitcher {pitcher_id}',
        'availability': (
            {'availability_status': availability_status}
            if availability_status is not None
            else {}
        ),
        'pitcher_labels': {
            'read': {'key': read_key},
        },
        'roster_status': {
            'status': roster_status,
            'is_active_mlb': active_mlb,
            'is_inactive_context': inactive_context,
        } if roster_status is not None else {},
        'eligibility': {'eligible': eligibility},
    }


@pytest.mark.parametrize(
    ('active', 'restricted', 'total', 'unknown', 'expected'),
    [
        (8, 0, 12, 0, STATE_HEALTHY),
        (8, 3, 12, 0, STATE_HEALTHY),
        (8, 4, 12, 0, STATE_REDUCED),
        (7, 4, 12, 0, STATE_REDUCED),
        (8, 6, 12, 0, STATE_THIN),
        (5, 4, 12, 0, STATE_THIN),
        (6, 6, 12, 0, STATE_DEPLETED),
        (4, 0, 12, 0, STATE_DEPLETED),
        (4, 0, 12, 1, STATE_UNKNOWN),
        (0, 0, 0, 0, STATE_UNKNOWN),
    ],
)
def test_bullpen_capacity_state_thresholds_are_active_count_based(
    active,
    restricted,
    total,
    unknown,
    expected,
):
    assert classify_bullpen_capacity_state(
        active_reliever_count=active,
        active_restricted_reliever_count=restricted,
        total_bullpen_resource_count=total,
        unknown_reliever_count=unknown,
    ) == expected


@pytest.mark.parametrize(
    ('active', 'total', 'unknown', 'expected'),
    [
        (7, 10, 0, RESOURCE_STATE_STRONG),
        (6, 10, 0, RESOURCE_STATE_MODERATE),
        (5, 10, 0, RESOURCE_STATE_STRAINED),
        (3, 8, 0, RESOURCE_STATE_DEPLETED),
        (0, 8, 0, RESOURCE_STATE_DEPLETED),
        (8, 12, 1, STATE_UNKNOWN),
        (0, 0, 0, STATE_UNKNOWN),
    ],
)
def test_resource_health_state_thresholds_are_pool_ratio_based(
    active,
    total,
    unknown,
    expected,
):
    assert classify_resource_health_state(
        active_reliever_count=active,
        total_bullpen_resource_count=total,
        unknown_reliever_count=unknown,
    ) == expected


def test_resource_health_counts_active_injured_and_unavailable_resources():
    payload = build_bullpen_resource_health(
        [
            record(1),
            record(2),
            record(3, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),
            record(4, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),
            record(
                5,
                availability_status=STATUS_UNAVAILABLE,
                read_key='unavailable',
            ),
        ],
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
    )

    assert payload['capability'] == CAPABILITY
    assert payload['active_reliever_count'] == 2
    assert payload['injured_reliever_count'] == 1
    assert payload['unavailable_reliever_count'] == 2
    assert payload['roster_unavailable_reliever_count'] == 1
    assert payload['workload_unavailable_reliever_count'] == 1
    assert payload['total_bullpen_resource_count'] == 5
    assert payload['resource_availability_ratio'] == 0.4
    assert payload['capacity_state'] == STATE_DEPLETED
    assert payload['resource_health_state'] == RESOURCE_STATE_STRAINED
    assert payload['bullpen_capacity']['capacity_state'] == STATE_DEPLETED
    assert payload['organizational_resource_health']['resource_health_state'] == RESOURCE_STATE_STRAINED
    assert payload['confidence'] == 'high'


def test_active_bullpen_capacity_can_be_healthy_when_resource_pool_is_strained():
    payload = build_bullpen_resource_health(
        [
            *(record(idx) for idx in range(1, 10)),
            record(10, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),
            record(11, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),
            record(12, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),
            record(13, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),
            record(14, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),
            record(15, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),
            record(16, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),
        ],
    )

    assert payload['active_reliever_count'] == 9
    assert payload['injured_reliever_count'] == 3
    assert payload['unavailable_reliever_count'] == 4
    assert payload['resource_availability_ratio'] == 0.56
    assert payload['capacity_state'] == STATE_HEALTHY
    assert payload['resource_health_state'] == RESOURCE_STATE_STRAINED


def test_missing_or_unknown_resource_data_fails_unknown_without_inflating_unavailable():
    payload = build_bullpen_resource_health([
        record(1),
        record(2, roster_status=STATUS_UNKNOWN, active_mlb=None),
        record(3, roster_status=None),
        record(4, availability_status=None),
    ])

    assert payload['active_reliever_count'] == 1
    assert payload['injured_reliever_count'] == 0
    assert payload['unavailable_reliever_count'] == 0
    assert payload['unknown_reliever_count'] == 3
    assert payload['total_bullpen_resource_count'] == 4
    assert payload['resource_availability_ratio'] is None
    assert payload['capacity_state'] == STATE_UNKNOWN
    assert payload['resource_health_state'] == STATE_UNKNOWN
    assert payload['confidence'] == 'low'
    assert INCOMPLETE_RESOURCE_LIMITATION in payload['limitations']


def test_non_bullpen_records_are_excluded_from_resource_health():
    payload = build_bullpen_resource_health([
        record(1),
        record(2, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True, eligibility=False),
    ])

    assert payload['total_bullpen_resource_count'] == 1
    assert payload['active_reliever_count'] == 1
    assert payload['injured_reliever_count'] == 0


def test_capacity_payload_carries_resource_health_layer():
    result = build_team_bullpen_capacity(
        [
            record(1),
            record(2, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),
        ],
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
    )

    health = result['resource_health']
    assert health['capability'] == CAPABILITY
    assert health['active_reliever_count'] == 1
    assert health['injured_reliever_count'] == 1
    assert health['total_bullpen_resource_count'] == 2
    assert health['capacity_state'] == STATE_DEPLETED
    assert health['resource_health_state'] == RESOURCE_STATE_STRAINED
