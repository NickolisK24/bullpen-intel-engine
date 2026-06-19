from services.bullpen_coverage_safety import (
    LABEL_LIMITED,
    LABEL_LIMITED_READ,
    LABEL_STABLE,
    LABEL_STRONG,
    LABEL_THIN,
    build_bullpen_coverage_safety_read,
)


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
    trust_unavailable=0,
    trust_unavailable_pct=0,
    hierarchy_confidence='medium',
):
    return {
        'capability': 'bullpen_capacity_intelligence_v1',
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
            'hierarchy_confidence': hierarchy_confidence,
        },
        'trust_capacity_loss': {
            'trust_arms_unavailable': trust_unavailable,
            'trust_capacity_unavailable_pct': trust_unavailable_pct,
        },
    }


def test_strong_coverage_requires_capacity_resource_health_and_trust_structure():
    result = build_bullpen_coverage_safety_read(capacity_payload())

    assert result['label'] == LABEL_STRONG
    counts = result['supportingCounts']
    assert counts['coverageSafetyVersion'] == '2.0'
    assert counts['capacityState'] == 'healthy'
    assert counts['resourceHealthState'] == 'strong'
    assert counts['anchorCount'] == 1
    assert counts['trustedGroupSize'] == 6


def test_strained_resource_health_prevents_strong_read():
    result = build_bullpen_coverage_safety_read(capacity_payload(resource_state='strained'))

    assert result['label'] == LABEL_STABLE
    assert any('strained' in reason for reason in result['reasons'])


def test_capacity_or_trusted_availability_pressure_reads_thin():
    thin_capacity = build_bullpen_coverage_safety_read(capacity_payload(
        capacity_state='thin',
        resource_state='strained',
        active=8,
        clean=2,
        anchor=1,
        leverage=3,
        trusted=1,
    ))
    trusted_loss = build_bullpen_coverage_safety_read(capacity_payload(
        capacity_state='healthy',
        resource_state='moderate',
        trust_unavailable=2,
        trust_unavailable_pct=40,
    ))

    assert thin_capacity['label'] == LABEL_THIN
    assert trusted_loss['label'] == LABEL_THIN


def test_depleted_capacity_or_shallow_trust_structure_reads_limited():
    depleted = build_bullpen_coverage_safety_read(capacity_payload(
        capacity_state='depleted',
        resource_state='moderate',
        active=4,
        clean=1,
    ))
    shallow = build_bullpen_coverage_safety_read(capacity_payload(
        active=7,
        clean=4,
        anchor=0,
        leverage=1,
        trusted=0,
        top_available=1,
    ))

    assert depleted['label'] == LABEL_LIMITED
    assert shallow['label'] == LABEL_LIMITED


def test_unknown_inputs_return_limited_read_without_inventing_pressure():
    result = build_bullpen_coverage_safety_read(capacity_payload(
        capacity_state='unknown',
        resource_state='moderate',
        hierarchy_confidence='medium',
    ))

    assert result['label'] == LABEL_LIMITED_READ
    assert result['limitations']


def test_missing_v2_inputs_return_none_for_legacy_fallback():
    assert build_bullpen_coverage_safety_read({}) is None
    assert build_bullpen_coverage_safety_read({'resource_health': {}}) is None


def test_environment_pressure_can_hold_strong_shape_at_stable():
    result = build_bullpen_coverage_safety_read(
        capacity_payload(),
        bullpen_environment={
            'status': 'pressure_with_context',
            'primary_pressure_sources': ['rotation_support_pressure'],
        },
    )

    assert result['label'] == LABEL_STABLE
    assert result['supportingCounts']['environmentStatus'] == 'pressure_with_context'
    assert any('environment pressure' in reason for reason in result['reasons'])


def test_output_exposes_no_scores_rankings_recommendations_or_predictions():
    result = build_bullpen_coverage_safety_read(capacity_payload())

    def visit(value, path=()):
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, str(index)))
            return
        if isinstance(value, dict):
            for key, child in value.items():
                joined = '.'.join((*path, key))
                lowered = key.lower()
                assert 'score' not in lowered, joined
                assert 'rank' not in lowered, joined
                assert 'recommend' not in lowered, joined
                assert 'prediction' not in lowered, joined
                visit(child, (*path, key))
            return
        if isinstance(value, str):
            lowered = value.lower()
            assert 'recommend' not in lowered
            assert 'prediction' not in lowered
            assert 'betting' not in lowered

    visit(result)
