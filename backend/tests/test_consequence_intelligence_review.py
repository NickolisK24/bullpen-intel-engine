from datetime import datetime, timezone

from services.consequence_intelligence_review import (
    CAPABILITY,
    build_consequence_intelligence_review,
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


def dashboard_payload(items, *, data_through='2026-06-19'):
    return {
        'freshness': {
            'data_through': data_through,
            'availability_reference_date': data_through,
        },
        'capacity_intelligence': {
            'teams': items,
            'by_team_id': {str(item['team_id']): item for item in items},
        },
    }


def build_review(current_items, prior_items=None, **kwargs):
    return build_consequence_intelligence_review(
        dashboard_payload(current_items, data_through='2026-06-19'),
        (
            dashboard_payload(prior_items, data_through='2026-06-18')
            if prior_items is not None
            else None
        ),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=len(current_items),
        **kwargs,
    )


def test_review_orders_teams_deterministically_and_includes_all_teams():
    current = [
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=5),
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=5),
    ]
    prior = [
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=2),
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
    ]

    report = build_review(current, prior)

    assert report['capability'] == CAPABILITY
    assert report['complete_team_count'] is True
    assert report['ordering_basis'] == 'team_abbreviation_then_team_name'
    assert [team['team_abbreviation'] for team in report['teams']] == ['AAA', 'BBB']
    assert all(team['comparison_available'] is True for team in report['teams'])
    assert all(team['primary_consequence'] for team in report['teams'])
    assert all(team['related_what_changed_item'] for team in report['teams'])


def test_review_no_consequence_state_is_handled_cleanly():
    report = build_review([snapshot()], [snapshot()])
    team = report['teams'][0]
    summary = report['distribution_summary']

    assert team['primary_consequence'] is None
    assert team['all_consequences'] == []
    assert team['consequence_state']['state'] == 'no_consequences'
    assert team['what_changed_state']['state'] == 'no_meaningful_changes'
    assert team['review_flags'] == ['no_consequence']
    assert summary['teams_without_consequence'] == 1
    assert summary['teams_with_primary_consequence'] == 0
    assert summary['review_flag_counts'] == {'no_consequence': 1}


def test_review_repeated_summary_and_context_flags_work():
    current = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=5),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=5),
    ]
    prior = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=2),
    ]
    duplicate_consequence = {
        'consequence_type': 'manual_test_consequence',
        'consequence_summary': 'The bullpen has more flexibility than yesterday.',
        'consequence_context': 'More rested options add clean paths before the game reaches the tightest lanes.',
        'significance': 'meaningful',
        'confidence': 'medium',
        'supporting_facts': [
            {
                'fact_key': 'rested_options',
                'previous_value': 2,
                'current_value': 5,
            }
        ],
    }
    consequence_payload = {
        'teams': [
            {
                'team_id': 1,
                'team_name': 'Alpha Club',
                'team_abbreviation': 'AAA',
                'status': 'available',
                'state': 'consequences_detected',
                'consequence_count': 1,
                'limitations': [],
                'consequences': [duplicate_consequence],
            },
            {
                'team_id': 2,
                'team_name': 'Beta Club',
                'team_abbreviation': 'BBB',
                'status': 'available',
                'state': 'consequences_detected',
                'consequence_count': 1,
                'limitations': [],
                'consequences': [duplicate_consequence],
            },
        ],
    }

    report = build_review(current, prior, consequence_payload=consequence_payload)
    summary = report['distribution_summary']

    assert list(summary['repeated_summary_counts'].values()) == [2]
    assert list(summary['repeated_context_counts'].values()) == [2]
    assert summary['review_flag_counts'] == {
        'repeated_context': 2,
        'repeated_summary': 2,
    }
    assert all(
        {'repeated_summary', 'repeated_context'} <= set(team['review_flags'])
        for team in report['teams']
    )


def test_generated_variation_reduces_repeated_summary_and_context_flags():
    current = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=5),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=5),
        snapshot(team_id=3, team_name='Gamma Club', team_abbreviation='CCC', clean=5),
        snapshot(team_id=4, team_name='Delta Club', team_abbreviation='DDD', clean=5),
    ]
    prior = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=2),
        snapshot(team_id=3, team_name='Gamma Club', team_abbreviation='CCC', clean=2),
        snapshot(team_id=4, team_name='Delta Club', team_abbreviation='DDD', clean=2),
    ]

    report = build_review(current, prior)
    summary = report['distribution_summary']

    assert summary['repeated_summary_counts'] == {}
    assert summary['repeated_context_counts'] == {}
    assert summary['review_flag_counts'] == {}
    assert {
        team['consequence_type']
        for team in report['teams']
    } == {'more_flexibility'}


def test_review_flags_governance_language_in_consequence_text():
    current = [snapshot(clean=5)]
    prior = [snapshot(clean=2)]
    consequence_payload = {
        'teams': [
            {
                'team_id': 1,
                'team_name': 'Test Team',
                'team_abbreviation': 'TST',
                'status': 'available',
                'state': 'consequences_detected',
                'consequence_count': 1,
                'limitations': [],
                'consequences': [
                    {
                        'consequence_type': 'unsafe_test_consequence',
                        'consequence_summary': (
                            'They are likely to win because this is the best reliever group.'
                        ),
                        'consequence_context': (
                            'The manager should use the closer; the odds and probability improved. raw score: 9. Flexible Distribution Bullpen.'
                        ),
                        'significance': 'meaningful',
                        'confidence': 'medium',
                        'supporting_facts': [
                            {
                                'fact_key': 'rested_options',
                                'previous_value': 2,
                                'current_value': 5,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    report = build_review(current, prior, consequence_payload=consequence_payload)
    flags = set(report['teams'][0]['review_flags'])

    assert {
        'prediction_language',
        'recommendation_language',
        'ranking_language',
        'betting_language',
        'probability_language',
        'reliever_selection_language',
        'raw_score_leak',
        'identity_label_leak',
    } <= flags


def test_review_flags_consequence_without_meaningful_change():
    consequence_payload = {
        'teams': [
            {
                'team_id': 1,
                'team_name': 'Test Team',
                'team_abbreviation': 'TST',
                'status': 'available',
                'state': 'consequences_detected',
                'consequence_count': 1,
                'limitations': [],
                'consequences': [
                    {
                        'consequence_type': 'manual_test_consequence',
                        'consequence_summary': 'The bullpen has more flexibility than yesterday.',
                        'consequence_context': 'More rested options add clean paths before the game reaches the tightest lanes.',
                        'significance': 'meaningful',
                        'confidence': 'medium',
                        'supporting_facts': [],
                    }
                ],
            }
        ],
    }

    report = build_review([snapshot()], [snapshot()], consequence_payload=consequence_payload)
    team = report['teams'][0]

    assert 'consequence_without_meaningful_change' in team['review_flags']
    assert team['related_what_changed_item'] is None
    assert report['distribution_summary']['review_flag_counts'][
        'consequence_without_meaningful_change'
    ] == 1


def test_review_flags_generic_consequence_text():
    consequence_payload = {
        'teams': [
            {
                'team_id': 1,
                'team_name': 'Test Team',
                'team_abbreviation': 'TST',
                'status': 'available',
                'state': 'consequences_detected',
                'consequence_count': 1,
                'limitations': [],
                'consequences': [
                    {
                        'consequence_type': 'manual_test_consequence',
                        'consequence_summary': 'This matters.',
                        'consequence_context': 'The situation changed.',
                        'significance': 'meaningful',
                        'confidence': 'medium',
                        'supporting_facts': [],
                    }
                ],
            }
        ],
    }

    report = build_review(
        [snapshot(clean=5)],
        [snapshot(clean=2)],
        consequence_payload=consequence_payload,
    )

    assert 'consequence_too_generic' in report['teams'][0]['review_flags']


def test_review_summary_counts_are_correct():
    report = build_review(
        [
            snapshot(
                team_id=1,
                team_name='Alpha Club',
                team_abbreviation='AAA',
                clean=5,
            ),
            snapshot(
                team_id=2,
                team_name='Beta Club',
                team_abbreviation='BBB',
                coverage_label='Thin Coverage Safety',
            ),
            snapshot(
                team_id=3,
                team_name='Gamma Club',
                team_abbreviation='CCC',
            ),
        ],
        [
            snapshot(
                team_id=1,
                team_name='Alpha Club',
                team_abbreviation='AAA',
                clean=2,
            ),
            snapshot(
                team_id=2,
                team_name='Beta Club',
                team_abbreviation='BBB',
                coverage_label='Stable Coverage Safety',
            ),
            snapshot(
                team_id=3,
                team_name='Gamma Club',
                team_abbreviation='CCC',
            ),
        ],
    )
    summary = report['distribution_summary']

    assert summary['teams_reviewed'] == 3
    assert summary['teams_with_comparison_available'] == 3
    assert summary['teams_with_primary_consequence'] == 2
    assert summary['teams_without_consequence'] == 1
    assert summary['consequence_counts_by_type'] == {
        'less_coverage_margin': 1,
        'more_flexibility': 1,
    }
    assert summary['consequence_counts_by_significance'] == {
        'meaningful': 1,
        'structural': 1,
    }
    assert summary['review_flag_counts'] == {
        'no_consequence': 1,
    }
