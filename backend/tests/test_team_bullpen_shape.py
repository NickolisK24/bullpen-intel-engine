from services.team_bullpen_shape import TEAM_BULLPEN_PUBLIC_LABELS, build_team_bullpen_shape
from services.workload_concentration import summarize_workload_concentration


ROLE_LABELS = {
    'trust_arm': 'Trust Arm',
    'bridge_arm': 'Bridge Arm',
    'coverage_arm': 'Coverage Arm',
    'depth_arm': 'Depth Arm',
    'limited_read': 'Limited Read',
}

READ_LABELS = {
    'clean_option': 'Clean Option',
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


def shape(cards, state='manageable', workload_concentration=None):
    return build_team_bullpen_shape(
        [{'status': 'Available', 'pitchers': cards, 'count': len(cards)}],
        context={'health': {'state': state}},
        workload_concentration=workload_concentration,
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

    assert result['trustAvailability']['label'] == 'Strong Trust Arm Availability'
    assert result['trustAvailability']['supportingCounts']['trustArms'] == 3
    assert result['trustAvailability']['supportingCounts']['cleanTrustArms'] == 2


def test_clean_options_interpretation_weighs_role_shape_on_backend():
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
    assert depth_led['cleanOptions']['label'] == 'Thin Clean Options'
    assert trust_led['cleanOptions']['supportingCounts']['cleanOptionCount'] == 3
    assert trust_led['cleanOptions']['label'] == 'Healthy Clean Options'


def test_bullpen_pressure_weights_trust_and_bridge_stress_on_backend():
    result = shape([
        card('trust_arm', 'rest_restricted', fatigue_score=75),
        card('trust_arm', 'unavailable'),
        card('bridge_arm', 'watch_arm'),
        card('coverage_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
        card('depth_arm', 'clean_option'),
    ])

    assert result['bullpenPressure']['label'] == 'High Bullpen Pressure'
    assert result['bullpenPressure']['supportingCounts']['highFatigueArms'] == 1
    assert result['bullpenPressure']['supportingCounts']['unavailableTrustArms'] == 1


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
