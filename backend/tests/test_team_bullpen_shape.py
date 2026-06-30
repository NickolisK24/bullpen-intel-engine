import re

from services.team_bullpen_shape import (
    DATA_LIMITED_DISCLAIMER,
    TEAM_BULLPEN_PUBLIC_LABELS,
    build_team_bullpen_shape,
)
from services.workload_concentration import summarize_workload_concentration


ROLE_LABELS = {
    'trust_arm': 'Trust Arm',
    'bridge_arm': 'Bridge Arm',
    'coverage_arm': 'Coverage Arm',
    'depth_arm': 'Depth Arm',
    'limited_read': 'Limited Read',
}

READ_LABELS = {
    'clean_option': 'Rested',
    'watch_arm': 'Watch Arm',
    'rest_restricted': 'Rest-Restricted',
    'unavailable': 'Unavailable',
    'limited_read': 'Limited Read',
}


def card(role_key, read_key, fatigue_score=20):
    return {
        'pitcher_id': abs(hash((role_key, read_key, fatigue_score))) % 100000,
        'name': f'{ROLE_LABELS[role_key]} {READ_LABELS[read_key]}',
        'fatigue_score': fatigue_score,
        'pitcher_labels': {
            'role': {
                'kind': 'role',
                'key': role_key,
                'label': ROLE_LABELS[role_key],
                'source': 'backend:test',
            },
            'read': {
                'kind': 'read',
                'key': read_key,
                'label': READ_LABELS[read_key],
                'source': 'backend:test',
            },
        },
    }


def capacity_payload(
    *,
    capacity_state='healthy',
    resource_state='strong',
    active=8,
    clean=6,
    anchor=1,
    leverage=4,
    trusted=1,
    top_available=1,
):
    return {
        'resource_health': {
            'capacity_state': capacity_state,
            'resource_health_state': resource_state,
            'bullpen_capacity': {
                'capacity_state': capacity_state,
                'active_reliever_count': active,
                'clean_active_reliever_count': clean,
            },
        },
        'trust_hierarchy': {
            'anchor_count': anchor,
            'leverage_count': leverage,
            'trusted_count': trusted,
            'trusted_group_size': anchor + leverage + trusted,
            'top_trust_bucket_available_count': top_available,
            'hierarchy_confidence': 'medium',
        },
        'trust_capacity_loss': {
            'trust_arms_unavailable': 0,
            'trust_capacity_unavailable_pct': 0,
        },
    }


def shape(
    cards,
    state='manageable',
    workload_concentration=None,
    capacity_intelligence=None,
    bullpen_environment=None,
):
    return build_team_bullpen_shape(
        [{'status': 'Available', 'pitchers': cards, 'count': len(cards)}],
        context={'health': {'state': state}},
        workload_concentration=workload_concentration,
        capacity_intelligence=capacity_intelligence,
        bullpen_environment=bullpen_environment,
    )


def test_team_shape_produces_approved_backend_public_reads():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'watch_arm'),
        card('bridge_arm', 'clean_option'),
        card('coverage_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'watch_arm'),
    ])

    assert result['source'] == 'backend'
    assert [read['key'] for read in result['reads']] == [
        'trustAvailability',
        'cleanOptions',
        'bullpenPressure',
        'workloadConcentration',
        'coverageSafety',
        'depthSafety',
    ]
    for read in result['reads']:
        assert read['label'] in TEAM_BULLPEN_PUBLIC_LABELS[read['key']]
        assert result['byKey'][read['key']] == read


def test_trust_availability_uses_backend_authored_trust_read_counts():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'watch_arm'),
        card('bridge_arm', 'clean_option'),
        card('coverage_arm', 'clean_option'),
        card('depth_arm', 'rest_restricted'),
    ])

    assert result['trustAvailability']['label'] == 'Strong Late-Inning Availability'
    assert result['trustAvailability']['supportingCounts']['trustArms'] == 3
    assert result['trustAvailability']['supportingCounts']['cleanTrustArms'] == 2


def test_rested_bullpen_interpretation_uses_role_shape_on_backend():
    depth_led = shape([
        card('trust_arm', 'unavailable'),
        card('trust_arm', 'unavailable'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
    ])
    trust_led = shape([
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('depth_arm', 'rest_restricted'),
        card('depth_arm', 'rest_restricted'),
        card('depth_arm', 'rest_restricted'),
    ])

    assert depth_led['cleanOptions']['supportingCounts']['cleanOptionCount'] == 5
    assert depth_led['cleanOptions']['label'] == 'Thin Rested Bullpen'
    assert trust_led['cleanOptions']['supportingCounts']['cleanOptionCount'] == 3
    assert trust_led['cleanOptions']['label'] == 'Healthy Rested Bullpen'


def test_bullpen_pressure_uses_late_inning_baseball_copy_on_backend():
    result = shape([
        card('trust_arm', 'rest_restricted', fatigue_score=75),
        card('trust_arm', 'unavailable'),
        card('bridge_arm', 'watch_arm'),
        card('coverage_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
    ])

    assert result['bullpenPressure']['label'] == 'High Late-Inning Pressure'
    assert result['bullpenPressure']['supportingCounts']['highFatigueArms'] == 1
    assert result['bullpenPressure']['supportingCounts']['unavailableTrustArms'] == 1


def test_late_inning_pressure_keeps_high_threshold_for_thinning_late_path():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'watch_arm'),
        card('trust_arm', 'rest_restricted'),
        card('bridge_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('coverage_arm', 'clean_option'),
    ])

    assert result['trustAvailability']['label'] == 'Stable Late-Inning Availability'
    assert result['cleanOptions']['label'] == 'Deep Rested Bullpen'
    assert result['bullpenPressure']['label'] == 'High Late-Inning Pressure'
    assert result['bullpenPressure']['supportingCounts']['watchArmCount'] == 1
    assert result['bullpenPressure']['supportingCounts']['restRestrictedCount'] == 1
    assert result['bullpenPressure']['supportingCounts']['cleanTrustArms'] == 2


def test_workload_concentration_uses_shared_pitch_share_bands():
    workload = summarize_workload_concentration({
        1: 42,
        2: 28,
        3: 14,
        4: 10,
        5: 6,
    })
    result = shape([
        card('trust_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('coverage_arm', 'watch_arm'),
        card('depth_arm', 'watch_arm'),
        card('depth_arm', 'clean_option'),
    ], workload_concentration=workload)

    assert workload['concentration_descriptor'] == 'a heavily concentrated workload'
    assert result['workloadConcentration']['label'] == 'Heavily Concentrated Workload'
    assert result['workloadConcentration']['supportingCounts']['topSharePct'] == 84
    assert result['workloadConcentration']['supportingCounts']['topArmCount'] == 3
    assert '(84 of 100)' not in result['workloadConcentration']['explanation']
    assert result['workloadConcentration']['explanation'] == (
        'Three arms have carried 84% of the recent relief work across five bullpen arms.'
    )


def test_team_shape_public_copy_retire_taxonomy_and_weighting_language():
    workload = summarize_workload_concentration({
        1: 42,
        2: 28,
        3: 14,
        4: 10,
        5: 6,
    })
    result = shape([
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'rest_restricted'),
        card('bridge_arm', 'watch_arm'),
        card('coverage_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'unavailable'),
    ], workload_concentration=workload)
    rendered = '\n'.join(
        str(item)
        for read in result['reads']
        for item in (read.get('label'), read.get('explanation'), *read.get('reasons', []))
    )
    lowered = rendered.lower()

    for phrase in (
        'clean option',
        'clean options',
        'interpretation weighs',
        'weighs clean',
        'late-inning pressure weighs',
        'trust arms above',
        'depth arms above',
        'classified available',
        '(84 of 100)',
        '1 of 1 trust arms',
        '0 of 1 coverage arms',
        'coverage arms are clean options',
    ):
        assert phrase not in lowered


def test_workload_concentration_fails_closed_without_recent_relief_workload():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
    ])

    assert result['workloadConcentration']['label'] == 'Limited Read'
    assert result['workloadConcentration']['supportingCounts']['totalRecentPitches'] == 0


def test_coverage_safety_substitute_capacity_lifts_limited_to_thin_only():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('coverage_arm', 'unavailable'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
    ])

    assert result['coverageSafety']['label'] == 'Thin Coverage Safety'
    assert result['coverageSafety']['supportingCounts']['substituteCoverageApplied'] is True


def test_coverage_safety_v2_uses_capacity_resource_health_and_trust_structure():
    result = shape(
        [
            card('coverage_arm', 'clean_option'),
            card('coverage_arm', 'clean_option'),
            card('trust_arm', 'clean_option'),
            card('bridge_arm', 'clean_option'),
        ],
        capacity_intelligence=capacity_payload(
            capacity_state='thin',
            resource_state='strained',
            active=8,
            clean=1,
            anchor=0,
            leverage=6,
            trusted=0,
            top_available=6,
        ),
    )

    assert result['coverageSafety']['label'] == 'Thin Coverage Safety'
    assert result['coverageSafety']['supportingCounts']['coverageSafetyVersion'] == '2.0'
    assert result['coverageSafety']['supportingCounts']['capacityState'] == 'thin'
    assert 'substituteCoverageApplied' not in result['coverageSafety']['supportingCounts']


def test_depth_safety_trust_anchor_guardrail_lives_on_backend():
    anchored = shape([
        card('trust_arm', 'clean_option'),
        card('trust_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'watch_arm'),
        card('depth_arm', 'clean_option'),
    ])
    unanchored = shape([
        card('trust_arm', 'rest_restricted'),
        card('trust_arm', 'unavailable'),
        card('bridge_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'watch_arm'),
        card('depth_arm', 'clean_option'),
    ])

    assert anchored['depthSafety']['label'] == 'Strong Depth Safety'
    assert unanchored['depthSafety']['label'] == 'Stable Depth Safety'
    assert unanchored['depthSafety']['supportingCounts']['anchoredByTrust'] is False


def test_sparse_backend_labels_return_limited_reads():
    result = shape([
        card('limited_read', 'limited_read'),
        card('limited_read', 'limited_read'),
        card('limited_read', 'limited_read'),
    ])

    assert all(read['label'] == 'Limited Read' for read in result['reads'])
    text = ' '.join(
        str(item)
        for read in result['reads']
        for item in (read.get('explanation'), *read.get('reasons', []))
    ).lower()
    for phrase in (
        '0 of 0',
        '0 trusted',
        'trusted-group',
        'top trust bucket',
        'coverage margin',
        'resource health',
        'active capacity',
        'trust structure',
        'clean options',
        'length option',
        '(unknown)',
    ):
        assert phrase not in text
    explanation_text = ' '.join(str(read.get('explanation') or '') for read in result['reads'])
    assert explanation_text.count(DATA_LIMITED_DISCLAIMER) == 1
    assert 'data-limited note' in text


def test_team_shape_public_copy_uses_sentence_case_and_long_relief_language():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('coverage_arm', 'rest_restricted'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'watch_arm'),
    ])
    text = ' '.join(
        str(item)
        for read in result['reads']
        for item in (read.get('explanation'), *read.get('reasons', []))
    )
    lowered = text.lower()

    assert not re.search(r'(?<=[.!?])\s+[a-z]', text)
    assert 'long reliever' in lowered or 'long relief' in lowered
    assert 'length option' not in lowered
    assert 'on monitor' not in lowered
    assert 'Rested' in ' '.join(read['label'] for read in result['reads'])


def test_team_shape_output_exposes_no_score_or_ranking_fields():
    result = shape([
        card('trust_arm', 'clean_option'),
        card('bridge_arm', 'clean_option'),
        card('coverage_arm', 'watch_arm'),
        card('depth_arm', 'rest_restricted'),
    ])

    def visit(value, path=()):
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, str(index)))
            return
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            joined = '.'.join((*path, key))
            assert 'score' not in key.lower(), joined
            assert 'rank' not in key.lower(), joined
            assert 'leaderboard' not in key.lower(), joined
            visit(child, (*path, key))

    visit(result)
