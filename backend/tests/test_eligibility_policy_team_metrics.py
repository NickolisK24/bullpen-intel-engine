"""Tests for eligibility policy integration into team bullpen metrics (Phase C3D).

Swing/Bulk Relief arms are held out of the Trust Arm / Bridge Arm / rested-arm
lanes but still contribute to coverage and depth context. Starter Protected,
Excluded, and Unknown/Limited remain withheld (they are ineligible). Normal
Relief is unchanged.
"""

from services.bullpen_capacity import build_team_bullpen_capacity
from services.bullpen_eligibility_vocabulary import (
    ELIGIBILITY_EXCLUDED,
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_STARTER_PROTECTED,
    ELIGIBILITY_SWING_BULK_RELIEF,
    ELIGIBILITY_UNKNOWN_LIMITED,
    record_counts_for_primary_lane,
    record_eligibility_type,
    record_is_swing_bulk,
)
from services.bullpen_trust_hierarchy import (
    BUCKET_ANCHOR,
    BUCKET_DEPTH,
    build_bullpen_trust_hierarchy,
    classify_trust_bucket,
)
from services.team_bullpen_shape import build_team_bullpen_shape

_ROLE_LABELS = {
    'trust_arm': 'Trust Arm',
    'bridge_arm': 'Bridge Arm',
    'coverage_arm': 'Coverage Arm',
    'depth_arm': 'Depth Arm',
    'limited_read': 'Limited Read',
}
_READ_LABELS = {
    'clean_option': 'Rested',
    'watch_arm': 'Watch Arm',
    'rest_restricted': 'Rest-Restricted',
    'unavailable': 'Unavailable',
    'limited_read': 'Limited Read',
}


def _card(role_key, read_key='clean_option', eligibility_type=ELIGIBILITY_NORMAL_RELIEF, name='Arm'):
    return {
        'name': name,
        'fatigue_score': 0,
        'pitcher_labels': {
            'role': {'key': role_key, 'label': _ROLE_LABELS[role_key]},
            'read': {'key': read_key, 'label': _READ_LABELS[read_key]},
        },
        'eligibility': {'eligible': True, 'eligibility_type': eligibility_type},
    }


def _groups(cards):
    return [{'pitchers': cards}]


def _record(pid, public_role='trust_arm', read_key='clean_option', observed='late_high_leverage',
            eligibility_type=ELIGIBILITY_NORMAL_RELIEF, availability_status='Available'):
    return {
        'pitcher_id': pid,
        'name': f'P{pid}',
        'availability': {'availability_status': availability_status, 'data_state': 'fresh', 'confidence': 'high'},
        'role': {
            'role_key': observed,
            'confidence': 'high',
            'evidence': ['12 appearances in the recent window', '4 save situation finish(es) recorded'],
        },
        'pitcher_labels': {'role': {'key': public_role}, 'read': {'key': read_key}},
        'roster_status': {'status': 'active', 'is_active_mlb': True, 'is_inactive_context': False},
        'eligibility': {'eligible': True, 'eligibility_type': eligibility_type},
    }


# ── Policy helpers ───────────────────────────────────────────────────────────

def test_policy_helpers_classify_swing_bulk_and_primary_lane():
    swing = {'eligibility': {'eligible': True, 'eligibility_type': ELIGIBILITY_SWING_BULK_RELIEF}}
    normal = {'eligibility': {'eligible': True, 'eligibility_type': ELIGIBILITY_NORMAL_RELIEF}}
    untyped = {'eligibility': {'eligible': True}}

    assert record_is_swing_bulk(swing) is True
    assert record_is_swing_bulk(normal) is False
    # Legacy untyped payloads are not treated as swing/bulk (preserves behavior).
    assert record_is_swing_bulk(untyped) is False

    assert record_counts_for_primary_lane(normal) is True
    assert record_counts_for_primary_lane(untyped) is True
    assert record_counts_for_primary_lane(swing) is False

    assert record_eligibility_type({}) == ELIGIBILITY_UNKNOWN_LIMITED


def test_withheld_types_never_count_for_primary_lane():
    for withheld in (ELIGIBILITY_STARTER_PROTECTED, ELIGIBILITY_EXCLUDED, ELIGIBILITY_UNKNOWN_LIMITED):
        record = {'eligibility': {'eligible': False, 'eligibility_type': withheld}}
        assert record_counts_for_primary_lane(record) is False
        assert record_is_swing_bulk(record) is False


# ── Team shape (public reads) ────────────────────────────────────────────────

def test_team_shape_holds_swing_bulk_out_of_trust_bridge_clean():
    cards = [
        _card('trust_arm'), _card('trust_arm'),
        _card('trust_arm', eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF),
        _card('bridge_arm'),
        _card('bridge_arm', eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF),
        _card('coverage_arm'), _card('coverage_arm'),
        _card('coverage_arm', eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF),
        _card('depth_arm'), _card('depth_arm'),
        _card('depth_arm', eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF),
    ]
    shape = build_team_bullpen_shape(_groups(cards))
    trust = shape['trustAvailability']['supportingCounts']
    clean = shape['cleanOptions']['supportingCounts']
    depth = shape['depthSafety']['supportingCounts']

    # Swing/Bulk excluded from trust, bridge, and the clean-option headline.
    assert trust['trustArms'] == 2
    assert clean['cleanTrustArms'] == 2
    assert clean['cleanBridgeArms'] == 1
    assert clean['cleanOptionCount'] == 7  # 11 clean cards minus 4 swing/bulk

    # Swing/Bulk still contributes to coverage and depth context.
    assert clean['cleanCoverageArms'] == 3
    assert clean['cleanDepthArms'] == 3
    assert depth['depthArms'] == 3


def test_team_shape_normal_relief_counts_in_all_lanes():
    cards = [
        _card('trust_arm'), _card('trust_arm'), _card('trust_arm'),
        _card('bridge_arm'), _card('bridge_arm'),
        _card('coverage_arm'), _card('coverage_arm'), _card('coverage_arm'),
        _card('depth_arm'), _card('depth_arm'), _card('depth_arm'),
    ]
    shape = build_team_bullpen_shape(_groups(cards))
    assert shape['trustAvailability']['supportingCounts']['trustArms'] == 3
    assert shape['cleanOptions']['supportingCounts']['cleanBridgeArms'] == 2
    assert shape['cleanOptions']['supportingCounts']['cleanOptionCount'] == 11
    assert shape['depthSafety']['supportingCounts']['depthArms'] == 3


def test_team_shape_structure_stays_intact_with_swing_bulk():
    cards = [
        _card('trust_arm'), _card('trust_arm'), _card('coverage_arm'),
        _card('coverage_arm', eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF),
        _card('depth_arm'), _card('depth_arm'),
    ]
    shape = build_team_bullpen_shape(_groups(cards))
    for key in (
        'trustAvailability', 'cleanOptions', 'bullpenPressure',
        'workloadConcentration', 'coverageSafety', 'depthSafety',
    ):
        assert key in shape
        assert shape[key]['label']


# ── Trust hierarchy (records path) ───────────────────────────────────────────

def test_trust_hierarchy_routes_swing_bulk_to_depth():
    normal = _record(1, public_role='trust_arm', observed='late_high_leverage')
    swing = _record(
        2, public_role='trust_arm', observed='late_high_leverage',
        eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF,
    )

    assert classify_trust_bucket(normal)['bucket'] == BUCKET_ANCHOR
    assert classify_trust_bucket(swing)['bucket'] == BUCKET_DEPTH

    payload = build_bullpen_trust_hierarchy([normal, swing])
    assert payload['anchor_count'] == 1
    assert payload['depth_count'] == 1
    assert payload['trusted_group_size'] == 1  # swing/bulk not in the trust group


# ── Capacity (records path) ──────────────────────────────────────────────────

def test_capacity_excludes_swing_bulk_from_trust_arms():
    records = [
        _record(1, public_role='trust_arm'),
        _record(2, public_role='trust_arm', eligibility_type=ELIGIBILITY_SWING_BULK_RELIEF),
        _record(3, public_role='bridge_arm'),
    ]
    result = build_team_bullpen_capacity(
        records, team={'team_id': 1, 'team_name': 'Test', 'team_abbreviation': 'TST'},
    )
    assert result['trust_capacity_loss']['trust_arms_total'] == 1


def test_capacity_normal_relief_trust_arms_still_count():
    records = [
        _record(1, public_role='trust_arm'),
        _record(2, public_role='trust_arm'),
        _record(3, public_role='bridge_arm'),
    ]
    result = build_team_bullpen_capacity(
        records, team={'team_id': 1, 'team_name': 'Test', 'team_abbreviation': 'TST'},
    )
    assert result['trust_capacity_loss']['trust_arms_total'] == 2
