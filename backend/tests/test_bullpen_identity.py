import json

from services.bullpen_identity import (
    CAPABILITY,
    IDENTITY_DEPTH_DRIVEN,
    IDENTITY_FLEXIBLE_DISTRIBUTION,
    IDENTITY_FRAGILE_COVERAGE,
    IDENTITY_RESOURCE_STRAINED,
    IDENTITY_TRUST_CONCENTRATED,
    IDENTITY_UNKNOWN,
    build_bullpen_identity,
)
from services.team_story_facts import BEAT_SIGNAL, build_story_facts


def capacity_payload(
    *,
    capacity_state='healthy',
    resource_state='strong',
    active=8,
    clean=6,
    anchor=1,
    leverage=3,
    trusted=1,
    depth=1,
    top_available=1,
    trust_unavailable=0,
    hierarchy_confidence='high',
):
    return {
        'capability': 'bullpen_capacity_intelligence_v1',
        'version': 'test',
        'source': 'backend',
        'team_id': 1,
        'team_name': 'Test Team',
        'team_abbreviation': 'TST',
        'resource_health': {
            'capacity_state': capacity_state,
            'resource_health_state': resource_state,
            'bullpen_capacity': {
                'capacity_state': capacity_state,
                'active_reliever_count': active,
                'clean_active_reliever_count': clean,
            },
            'organizational_resource_health': {
                'resource_health_state': resource_state,
            },
        },
        'trust_hierarchy': {
            'anchor_count': anchor,
            'leverage_count': leverage,
            'trusted_count': trusted,
            'depth_count': depth,
            'unknown_count': 0,
            'trusted_group_size': anchor + leverage + trusted,
            'top_trust_bucket_available_count': top_available,
            'hierarchy_confidence': hierarchy_confidence,
        },
        'trust_capacity_loss': {
            'trust_arms_unavailable': trust_unavailable,
            'trust_capacity_unavailable_pct': 0,
        },
        'capacity_loss': {
            'status': 'clear',
            'limitations': [],
        },
    }


def test_trust_concentrated_identity_uses_narrow_trusted_lane():
    result = build_bullpen_identity(capacity_payload(
        active=7,
        clean=4,
        anchor=1,
        leverage=1,
        trusted=0,
        depth=1,
        top_available=1,
    ))

    assert result['capability'] == CAPABILITY
    assert result['identity_key'] == IDENTITY_TRUST_CONCENTRATED
    assert result['identity_label'] == 'Trust-Concentrated Bullpen'
    assert result['confidence'] in {'medium', 'high'}
    assert any('trusted lane is narrow' in trait['text'] for trait in result['supporting_traits'])


def test_depth_driven_identity_uses_stable_depth_behind_trust_group():
    result = build_bullpen_identity(capacity_payload(
        active=8,
        clean=5,
        anchor=1,
        leverage=2,
        trusted=2,
        depth=3,
        top_available=1,
    ))

    assert result['identity_key'] == IDENTITY_DEPTH_DRIVEN
    assert result['identity_label'] == 'Depth-Driven Bullpen'
    assert any('Depth volume' in trait['text'] for trait in result['supporting_traits'])


def test_flexible_distribution_identity_uses_broad_usable_lanes():
    result = build_bullpen_identity(capacity_payload(
        active=8,
        clean=5,
        anchor=1,
        leverage=2,
        trusted=2,
        depth=1,
        top_available=1,
    ))

    assert result['identity_key'] == IDENTITY_FLEXIBLE_DISTRIBUTION
    assert result['identity_label'] == 'Flexible Distribution Bullpen'
    assert 'several usable lanes' in result['identity_summary']


def test_resource_strained_identity_keeps_pool_strain_separate_from_coverage():
    result = build_bullpen_identity(capacity_payload(
        resource_state='strained',
        active=8,
        clean=5,
        anchor=1,
        leverage=3,
        trusted=1,
        depth=1,
    ))

    assert result['identity_key'] == IDENTITY_RESOURCE_STRAINED
    assert result['identity_label'] == 'Resource-Strained Bullpen'
    assert any('broader resource pool is strained' in trait['text'] for trait in result['supporting_traits'])


def test_fragile_coverage_identity_uses_thin_capacity_or_coverage():
    result = build_bullpen_identity(capacity_payload(
        capacity_state='thin',
        resource_state='strong',
        active=5,
        clean=1,
        anchor=0,
        leverage=1,
        trusted=1,
        depth=1,
        top_available=1,
    ))

    assert result['identity_key'] == IDENTITY_FRAGILE_COVERAGE
    assert result['identity_label'] == 'Fragile Coverage Bullpen'
    assert any('little margin' in trait['text'] for trait in result['supporting_traits'])


def test_unknown_identity_fails_closed_for_missing_or_unknown_context():
    missing = build_bullpen_identity({})
    unknown = build_bullpen_identity(capacity_payload(
        capacity_state='unknown',
        active=0,
        clean=0,
        anchor=0,
        leverage=0,
        trusted=0,
        depth=0,
        top_available=0,
    ))

    assert missing['identity_key'] == IDENTITY_UNKNOWN
    assert missing['confidence'] == 'none'
    assert unknown['identity_key'] == IDENTITY_UNKNOWN
    assert unknown['confidence'] == 'low'


def test_story_facts_expose_identity_without_changing_story_selection_inputs():
    capacity = capacity_payload(
        active=8,
        clean=5,
        anchor=1,
        leverage=2,
        trusted=2,
        depth=1,
    )
    identity = build_bullpen_identity(capacity)
    capacity['bullpen_identity'] = identity
    facts = build_story_facts(
        'pressure_distribution',
        {
            'team': {'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
            'capacity_intelligence': capacity,
            'workload': {'total_pitches': 60, 'participant_count': 6},
            'availability': {'available': 6, 'total': 8},
        },
        [{'key': BEAT_SIGNAL, 'text': 'The Test Team bullpen work is spread out tonight.'}],
    )

    assert facts['bullpen_identity'] == identity
    assert facts['identity_context'] == identity['identity_summary']


def test_identity_output_keeps_governance_boundaries_and_no_score_leakage():
    result = build_bullpen_identity(capacity_payload())

    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False

    allowed_governance_keys = {'ranking_applied', 'prediction_applied'}
    blocked_text = ('recommend', 'prediction', 'betting')

    def visit(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered_key = key.lower()
                assert 'score' not in lowered_key, '.'.join((*path, key))
                if key not in allowed_governance_keys:
                    assert 'rank' not in lowered_key, '.'.join((*path, key))
                    assert 'prediction' not in lowered_key, '.'.join((*path, key))
                    assert 'recommend' not in lowered_key, '.'.join((*path, key))
                visit(child, (*path, key))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*path, str(index)))
            return
        if isinstance(value, str):
            lowered = value.lower()
            assert 'score' not in lowered
            for blocked in blocked_text:
                assert blocked not in lowered

    visit(result)
    encoded = json.dumps({
        key: value
        for key, value in result.items()
        if key not in allowed_governance_keys
    }).lower()
    assert 'score' not in encoded
    assert 'recommend' not in encoded
    assert 'betting' not in encoded
