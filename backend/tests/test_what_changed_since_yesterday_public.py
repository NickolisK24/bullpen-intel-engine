import json

from services.what_changed_since_yesterday_public import (
    CAPABILITY,
    DEFAULT_PUBLIC_ITEM_LIMIT,
    build_what_changed_public_payload,
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
    coverage_label='Stable Coverage Safety',
    identity_key='flexible_distribution',
    identity_label='Flexible Distribution Bullpen',
):
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'resource_health': {
            'confidence': 'high',
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
            'anchor_count': 1,
            'leverage_count': 2,
            'trusted_count': 1,
            'depth_count': 1,
            'trusted_group_size': trusted_group,
            'hierarchy_confidence': 'high',
        },
        'coverage_safety': {
            'label': coverage_label,
        },
        'bullpen_identity': {
            'identity_key': identity_key,
            'identity_label': identity_label,
            'confidence': 'medium',
        },
    }


def payload(items, *, data_through='2026-06-19'):
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


def build_public(current_items, prior_items=None, **kwargs):
    return build_what_changed_public_payload(
        payload(current_items, data_through='2026-06-19'),
        payload(prior_items, data_through='2026-06-18') if prior_items is not None else None,
        **kwargs,
    )


def test_public_payload_includes_only_frontend_safe_copy_items():
    current = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=5),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=4),
    ]
    prior = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=4),
    ]

    result = build_public(current, prior)

    assert result['capability'] == CAPABILITY
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False
    assert result['comparison']['comparison_available'] is True
    assert result['item_count'] == 1
    assert result['items'] == [
        {
            'key': 'AAA-what-changed',
            'team_id': 1,
            'team_name': 'Alpha Club',
            'team_abbreviation': 'AAA',
            'public_headline': 'The Alpha Club bullpen has a few more paths available.',
            'public_summary': (
                'The bullpen went from 2 rested options to 5, adding three cleaner paths than yesterday.'
            ),
            'public_context': None,
        }
    ]


def test_public_payload_skips_no_prior_no_change_and_tiny_flagged_changes():
    no_prior = build_public([snapshot(clean=5)], None)
    no_change = build_public([snapshot(clean=5)], [snapshot(clean=5)])
    tiny_only = build_public(
        [snapshot(capacity_state='reduced', clean=5)],
        [snapshot(capacity_state='thin', clean=4)],
    )

    assert no_prior['items'] == []
    assert no_prior['comparison']['comparison_available'] is False
    assert no_change['items'] == []
    assert tiny_only['items'] == []


def test_public_payload_enforces_cap_without_ranking_language():
    current = [
        snapshot(
            team_id=idx,
            team_name=f'Team {idx}',
            team_abbreviation=f'T{idx}',
            active=12,
            clean=idx + 4,
        )
        for idx in range(1, 10)
    ]
    prior = [
        snapshot(
            team_id=idx,
            team_name=f'Team {idx}',
            team_abbreviation=f'T{idx}',
            active=12,
            clean=idx,
        )
        for idx in range(1, 10)
    ]

    result = build_public(current, prior, limit=DEFAULT_PUBLIC_ITEM_LIMIT)

    assert len(result['items']) == DEFAULT_PUBLIC_ITEM_LIMIT
    assert [item['team_abbreviation'] for item in result['items']] == [
        'T1',
        'T2',
        'T3',
        'T4',
        'T5',
        'T6',
    ]
    assert result['ordering_basis'] == 'team_abbreviation_then_team_name'


def test_public_payload_skips_items_with_repeated_public_copy_flags():
    current = [
        snapshot(
            team_id=1,
            team_name='Alpha Club',
            team_abbreviation='AAA',
            identity_key='depth_driven',
            identity_label='Depth-Driven Bullpen',
        ),
        snapshot(
            team_id=2,
            team_name='Beta Club',
            team_abbreviation='BBB',
            identity_key='depth_driven',
            identity_label='Depth-Driven Bullpen',
        ),
    ]
    prior = [
        snapshot(
            team_id=1,
            team_name='Alpha Club',
            team_abbreviation='AAA',
            identity_key='flexible_distribution',
            identity_label='Flexible Distribution Bullpen',
        ),
        snapshot(
            team_id=2,
            team_name='Beta Club',
            team_abbreviation='BBB',
            identity_key='flexible_distribution',
            identity_label='Flexible Distribution Bullpen',
        ),
    ]

    result = build_public(current, prior)

    assert result['items'] == []


def test_public_payload_does_not_leak_internal_keys_scores_confidence_or_identity_labels():
    result = build_public(
        [
            snapshot(
                team_name='Alpha Club',
                team_abbreviation='AAA',
                identity_key='resource_strained',
                identity_label='Resource-Strained Bullpen',
            )
        ],
        [
            snapshot(
                team_name='Alpha Club',
                team_abbreviation='AAA',
                identity_key='flexible_distribution',
                identity_label='Flexible Distribution Bullpen',
            )
        ],
    )

    encoded_items = json.dumps(result['items']).lower()
    for forbidden in (
        'change_type',
        'change_direction',
        'confidence',
        'supporting_facts',
        'copy_review_flags',
        'public_copy_generated',
        'identity_label',
        'flexible distribution bullpen',
        'resource-strained bullpen',
        'raw_score',
        'score',
        'recommend',
        'prediction',
        'ranking',
        'best reliever',
    ):
        assert forbidden not in encoded_items
