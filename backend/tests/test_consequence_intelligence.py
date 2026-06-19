import json

from services.consequence_intelligence import (
    CAPABILITY,
    CONSEQUENCE_HEAVIER_WORKLOAD_CONCENTRATION,
    CONSEQUENCE_LESS_COVERAGE_MARGIN,
    CONSEQUENCE_LESS_FLEXIBILITY,
    CONSEQUENCE_MORE_COVERAGE_MARGIN,
    CONSEQUENCE_MORE_FLEXIBILITY,
    CONSEQUENCE_MORE_STABLE_BULLPEN_SHAPE,
    CONSEQUENCE_NARROWER_TRUST_SUPPORT,
    CONSEQUENCE_WIDER_TRUST_SUPPORT,
    STATE_CONSEQUENCES_DETECTED,
    STATE_NO_CONSEQUENCES,
    build_consequence_intelligence_payload,
    build_team_consequence_intelligence,
)


def snapshot(
    *,
    team_id=1,
    team_name='Test Team',
    team_abbreviation='TST',
    capacity_state='reduced',
    resource_state='moderate',
    active=7,
    clean=4,
    trusted_group=4,
    anchor=1,
    leverage=2,
    trusted=1,
    coverage_label='Stable Coverage Safety',
    identity_key='flexible_distribution',
    identity_confidence='medium',
    resource_confidence='high',
    hierarchy_confidence='high',
):
    return {
        'capability': 'bullpen_capacity_intelligence_v1',
        'version': 'test',
        'source': 'backend',
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'resource_health': {
            'confidence': resource_confidence,
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
            'depth_count': 1,
            'unknown_count': 0,
            'trusted_group_size': trusted_group,
            'top_trust_bucket_available_count': 1,
            'hierarchy_confidence': hierarchy_confidence,
            'limitations': [],
        },
        'trust_capacity_loss': {
            'trust_arms_unavailable': 0,
            'trust_capacity_unavailable_pct': 0,
        },
        'coverage_safety': {
            'label': coverage_label,
        },
        'bullpen_identity': {
            'identity_key': identity_key,
            'confidence': identity_confidence,
        },
    }


def consequence(result, consequence_type):
    for item in result['consequences']:
        if item['consequence_type'] == consequence_type:
            return item
    raise AssertionError(f'Missing consequence type: {consequence_type}')


def test_flexibility_improvement_from_more_rested_options():
    result = build_team_consequence_intelligence(
        snapshot(clean=5),
        snapshot(clean=2),
    )

    item = consequence(result, CONSEQUENCE_MORE_FLEXIBILITY)

    assert result['capability'] == CAPABILITY
    assert result['state'] == STATE_CONSEQUENCES_DETECTED
    assert item['significance'] == 'meaningful'
    assert 'Test Team' in item['consequence_summary']
    assert item['consequence_context']
    assert item['supporting_facts'][0]['previous_value'] == 2
    assert item['supporting_facts'][0]['current_value'] == 5


def test_flexibility_decline_from_fewer_rested_options():
    result = build_team_consequence_intelligence(
        snapshot(clean=2),
        snapshot(clean=5),
    )

    item = consequence(result, CONSEQUENCE_LESS_FLEXIBILITY)

    assert item['consequence_summary'] == 'The bullpen has less flexibility than yesterday.'
    assert 'Fewer rested options' in item['consequence_context']


def test_coverage_improvement_describes_more_margin():
    result = build_team_consequence_intelligence(
        snapshot(coverage_label='Stable Coverage Safety'),
        snapshot(coverage_label='Thin Coverage Safety'),
    )

    item = consequence(result, CONSEQUENCE_MORE_COVERAGE_MARGIN)

    assert item['significance'] == 'structural'
    assert 'Test Team' in item['consequence_summary']
    assert item['consequence_context']


def test_coverage_decline_describes_less_margin():
    result = build_team_consequence_intelligence(
        snapshot(coverage_label='Thin Coverage Safety'),
        snapshot(coverage_label='Stable Coverage Safety'),
    )

    item = consequence(result, CONSEQUENCE_LESS_COVERAGE_MARGIN)

    assert item['consequence_summary'] == 'Coverage has less margin than yesterday.'
    assert item['confidence'] == 'high'


def test_trust_expansion_describes_wider_support():
    result = build_team_consequence_intelligence(
        snapshot(trusted_group=5, anchor=1, leverage=3, trusted=1),
        snapshot(trusted_group=2, anchor=1, leverage=1, trusted=0),
    )

    item = consequence(result, CONSEQUENCE_WIDER_TRUST_SUPPORT)

    assert 'Test Team' in item['consequence_summary']
    assert item['consequence_context']


def test_trust_contraction_describes_narrower_support():
    result = build_team_consequence_intelligence(
        snapshot(trusted_group=3, anchor=1, leverage=2, trusted=0),
        snapshot(trusted_group=6, anchor=1, leverage=4, trusted=1),
    )

    item = consequence(result, CONSEQUENCE_NARROWER_TRUST_SUPPORT)

    assert item['consequence_summary'] == 'The trusted group is narrower than yesterday.'
    assert item['significance'] == 'structural'


def test_workload_concentration_consequence_when_trust_contracts_to_small_group():
    result = build_team_consequence_intelligence(
        snapshot(trusted_group=2, anchor=1, leverage=1, trusted=0),
        snapshot(trusted_group=5, anchor=1, leverage=3, trusted=1),
    )

    item = consequence(result, CONSEQUENCE_HEAVIER_WORKLOAD_CONCENTRATION)

    assert item['consequence_summary'] == (
        'Workload coverage is more concentrated around the remaining trusted group.'
    )
    assert item['supporting_facts'][-1]['fact_key'] == 'trusted_group_size'
    assert item['supporting_facts'][-1]['current_value'] == 2


def test_identity_change_can_describe_more_stable_bullpen_shape_without_label_leak():
    result = build_team_consequence_intelligence(
        snapshot(identity_key='depth_driven', identity_confidence='medium'),
        snapshot(identity_key='resource_strained', identity_confidence='medium'),
    )

    item = consequence(result, CONSEQUENCE_MORE_STABLE_BULLPEN_SHAPE)
    text = json.dumps(item).lower()

    assert item['consequence_summary'] == 'The bullpen shape is more settled than yesterday.'
    assert 'depth-driven bullpen' not in text
    assert 'resource-strained bullpen' not in text


def test_stable_no_change_state_emits_no_consequences():
    current = snapshot()
    prior = snapshot()

    result = build_team_consequence_intelligence(current, prior)

    assert result['state'] == STATE_NO_CONSEQUENCES
    assert result['what_changed_state'] == 'no_meaningful_changes'
    assert result['consequences'] == []
    assert result['consequence_count'] == 0


def test_league_payload_uses_deterministic_team_order_without_ranking():
    current = {
        'freshness': {'data_through': '2026-06-19'},
        'capacity_intelligence': {
            'teams': [
                snapshot(team_id=2, team_abbreviation='BBB', clean=5),
                snapshot(team_id=1, team_abbreviation='AAA', coverage_label='Stable Coverage Safety'),
            ],
        },
    }
    prior = {
        'freshness': {'data_through': '2026-06-18'},
        'capacity_intelligence': {
            'teams': [
                snapshot(team_id=2, team_abbreviation='BBB', clean=2),
                snapshot(team_id=1, team_abbreviation='AAA', coverage_label='Thin Coverage Safety'),
            ],
        },
    }

    result = build_consequence_intelligence_payload(current, prior)

    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False
    assert result['ordering_basis'] == 'team_abbreviation_then_team_id'
    assert [team['team_abbreviation'] for team in result['teams']] == ['AAA', 'BBB']
    assert result['teams_with_consequences'] == 2


def test_phrase_variation_is_deterministic_without_changing_consequence_types():
    current = {
        'freshness': {'data_through': '2026-06-19'},
        'capacity_intelligence': {
            'teams': [
                snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=5),
                snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=5),
                snapshot(team_id=3, team_name='Gamma Club', team_abbreviation='CCC', clean=5),
                snapshot(team_id=4, team_name='Delta Club', team_abbreviation='DDD', clean=5),
            ],
        },
    }
    prior = {
        'freshness': {'data_through': '2026-06-18'},
        'capacity_intelligence': {
            'teams': [
                snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
                snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=2),
                snapshot(team_id=3, team_name='Gamma Club', team_abbreviation='CCC', clean=2),
                snapshot(team_id=4, team_name='Delta Club', team_abbreviation='DDD', clean=2),
            ],
        },
    }

    result = build_consequence_intelligence_payload(current, prior)
    repeated = build_consequence_intelligence_payload(current, prior)

    summaries = [
        team['consequences'][0]['consequence_summary']
        for team in result['teams']
    ]
    contexts = [
        team['consequences'][0]['consequence_context']
        for team in result['teams']
    ]
    repeated_summaries = [
        team['consequences'][0]['consequence_summary']
        for team in repeated['teams']
    ]

    assert summaries == repeated_summaries
    assert len(set(summaries)) > 1
    assert len(set(contexts)) > 1
    assert {
        team['consequences'][0]['consequence_type']
        for team in result['teams']
    } == {CONSEQUENCE_MORE_FLEXIBILITY}
    assert result['consequence_count'] == repeated['consequence_count'] == 4


def test_governance_safety_no_prediction_recommendation_ranking_probability_or_score_leakage():
    result = build_consequence_intelligence_payload(
        {
            'freshness': {'data_through': '2026-06-19'},
            'capacity_intelligence': {'teams': [snapshot(clean=5)]},
        },
        {
            'freshness': {'data_through': '2026-06-18'},
            'capacity_intelligence': {'teams': [snapshot(clean=2)]},
        },
    )

    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False

    allowed_keys = {'ranking_applied', 'selection_made', 'prediction_applied'}
    blocked_text = (
        'recommend',
        'projected',
        'expected',
        'forecast',
        'probability',
        'probable',
        'odds',
        'likely',
        'bet',
        'ranked',
        'best reliever',
        'should use',
        'must use',
        'manager should',
    )

    def visit(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered_key = key.lower()
                if key not in allowed_keys:
                    assert 'score' not in lowered_key, '.'.join((*path, key))
                    assert 'rank' not in lowered_key, '.'.join((*path, key))
                    assert 'recommend' not in lowered_key, '.'.join((*path, key))
                    assert 'prediction' not in lowered_key, '.'.join((*path, key))
                    assert 'probability' not in lowered_key, '.'.join((*path, key))
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
