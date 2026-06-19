import json

from services.availability import STATUS_AVAILABLE, STATUS_UNAVAILABLE
from services.bullpen_capacity import build_team_bullpen_capacity
from services.bullpen_trust_hierarchy import (
    BUCKET_ANCHOR,
    BUCKET_DEPTH,
    BUCKET_LEVERAGE,
    BUCKET_TRUSTED,
    BUCKET_UNKNOWN,
    CAPABILITY,
    build_bullpen_trust_hierarchy,
    classify_trust_bucket,
)
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15


def record(
    pitcher_id,
    *,
    name=None,
    public_role='bridge_arm',
    read_key='clean_option',
    availability_status=STATUS_AVAILABLE,
    data_state='fresh',
    availability_confidence='high',
    observed_role='middle_relief',
    role_confidence='high',
    evidence=None,
    roster_status=STATUS_ACTIVE,
    active_mlb=True,
    inactive_context=False,
    eligibility=True,
):
    return {
        'pitcher_id': pitcher_id,
        'name': name or f'Pitcher {pitcher_id}',
        'availability': {
            'availability_status': availability_status,
            'data_state': data_state,
            'confidence': availability_confidence,
        },
        'role': {
            'role_key': observed_role,
            'confidence': role_confidence,
            'evidence': evidence or ['4 appearances in the recent window'],
        },
        'pitcher_labels': {
            'role': {'key': public_role},
            'read': {'key': read_key},
        },
        'roster_status': {
            'status': roster_status,
            'is_active_mlb': active_mlb,
            'is_inactive_context': inactive_context,
        },
        'eligibility': {'eligible': eligibility},
    }


def bucket(item):
    return item['bucket']


def test_bucket_assignment_uses_existing_role_and_availability_signals():
    relief_outs = {1: 60, 2: 36, 3: 30, 4: 12, 5: 0}

    assert bucket(classify_trust_bucket(
        record(1, public_role='trust_arm', observed_role='late_high_leverage'),
        relief_outs_by_pitcher=relief_outs,
    )) == BUCKET_ANCHOR
    assert bucket(classify_trust_bucket(
        record(2, public_role='trust_arm', observed_role='setup_bridge', read_key='watch_arm', availability_status='Monitor'),
        relief_outs_by_pitcher=relief_outs,
    )) == BUCKET_LEVERAGE
    assert bucket(classify_trust_bucket(
        record(3, public_role='bridge_arm', observed_role='middle_relief'),
        relief_outs_by_pitcher=relief_outs,
    )) == BUCKET_TRUSTED
    assert bucket(classify_trust_bucket(
        record(4, public_role='coverage_arm', observed_role='long_multi_inning'),
        relief_outs_by_pitcher=relief_outs,
    )) == BUCKET_DEPTH
    assert bucket(classify_trust_bucket(
        record(5, public_role='limited_read', observed_role='insufficient_data', data_state='missing'),
        relief_outs_by_pitcher=relief_outs,
    )) == BUCKET_UNKNOWN


def test_insufficient_data_stays_unknown_unless_workload_supports_trusted_bucket():
    limited = record(
        10,
        public_role='limited_read',
        observed_role='insufficient_data',
        data_state='missing',
        role_confidence='none',
        evidence=['0 appearances in the recent window'],
    )
    workload_supported = record(
        11,
        public_role='limited_read',
        observed_role='middle_relief',
        data_state='fresh',
        role_confidence='medium',
        evidence=['4 appearances in the recent window'],
    )

    assert classify_trust_bucket(limited, relief_outs_by_pitcher={10: 0})['bucket'] == BUCKET_UNKNOWN
    assert classify_trust_bucket(workload_supported, relief_outs_by_pitcher={11: 33})['bucket'] == BUCKET_TRUSTED


def test_unavailable_and_injured_pitchers_do_not_receive_active_trust_buckets():
    injured = classify_trust_bucket(
        record(20, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),
        relief_outs_by_pitcher={20: 50},
    )
    unavailable = classify_trust_bucket(
        record(21, read_key='unavailable', availability_status=STATUS_UNAVAILABLE),
        relief_outs_by_pitcher={21: 50},
    )

    assert injured['bucket'] == BUCKET_UNKNOWN
    assert injured['is_active_bullpen_resource'] is False
    assert unavailable['bucket'] == BUCKET_UNKNOWN
    assert unavailable['is_active_bullpen_resource'] is False


def test_non_bullpen_records_are_excluded_from_hierarchy():
    payload = build_bullpen_trust_hierarchy([
        record(30, public_role='trust_arm', observed_role='late_high_leverage'),
        record(31, public_role='trust_arm', observed_role='late_high_leverage', eligibility=False),
    ], relief_outs_by_pitcher={30: 60, 31: 60})

    assert payload['anchor_count'] == 1
    assert [item['pitcher_id'] for item in payload['pitchers']] == [30]


def test_team_summary_counts_and_top_bucket_available_count_are_deterministic():
    records = [
        record(42, name='Trusted C', public_role='bridge_arm', observed_role='middle_relief'),
        record(41, name='Anchor B', public_role='trust_arm', observed_role='late_high_leverage'),
        record(43, name='Depth D', public_role='depth_arm', observed_role='low_unclear'),
        record(40, name='Anchor A', public_role='trust_arm', observed_role='late_high_leverage'),
    ]
    relief_outs = {40: 60, 41: 55, 42: 30, 43: 0}

    first = build_bullpen_trust_hierarchy(records, relief_outs_by_pitcher=relief_outs)
    second = build_bullpen_trust_hierarchy(list(reversed(records)), relief_outs_by_pitcher=relief_outs)

    assert first == second
    assert first['capability'] == CAPABILITY
    assert first['anchor_count'] == 2
    assert first['trusted_count'] == 1
    assert first['depth_count'] == 1
    assert first['trusted_group_size'] == 3
    assert first['top_trust_bucket'] == BUCKET_ANCHOR
    assert first['top_trust_bucket_available_count'] == 2
    assert [item['name'] for item in first['pitchers'][:2]] == ['Anchor A', 'Anchor B']


def test_payload_does_not_expose_recommendation_or_score_fields():
    payload = build_bullpen_trust_hierarchy([
        record(50, public_role='trust_arm', observed_role='late_high_leverage'),
    ], relief_outs_by_pitcher={50: 60})

    encoded = json.dumps(payload).lower()
    assert 'recommend' not in encoded
    assert 'should_pitch' not in encoded
    assert 'score' not in encoded
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert payload['prediction_applied'] is False


def test_capacity_payload_exposes_summary_without_player_buckets():
    result = build_team_bullpen_capacity(
        [
            record(60, public_role='trust_arm', observed_role='late_high_leverage'),
            record(61, public_role='bridge_arm', observed_role='middle_relief'),
        ],
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
        relief_outs_by_pitcher={60: 60, 61: 33},
    )

    hierarchy = result['trust_hierarchy']
    assert hierarchy['capability'] == CAPABILITY
    assert hierarchy['anchor_count'] == 1
    assert hierarchy['trusted_count'] == 1
    assert hierarchy['trusted_group_size'] == 2
    assert 'pitchers' not in hierarchy
