from datetime import datetime, timezone

from services.what_changed_since_yesterday_review import (
    CAPABILITY,
    build_what_changed_since_yesterday_review,
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
    identity_label='Flexible Distribution Bullpen',
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
            'identity_label': identity_label,
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


def build_review(current_items, prior_items=None):
    return build_what_changed_since_yesterday_review(
        dashboard_payload(current_items, data_through='2026-06-19'),
        (
            dashboard_payload(prior_items, data_through='2026-06-18')
            if prior_items is not None
            else None
        ),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=len(current_items),
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
    assert all(team['comparison_possible'] is True for team in report['teams'])
    assert all(team['selected_top_change'] for team in report['teams'])


def test_review_no_prior_snapshot_fails_closed_for_every_team():
    report = build_review([
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA'),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB'),
    ])

    assert report['comparison']['comparison_available'] is False
    assert report['distribution_summary']['teams_without_prior_snapshot'] == 2
    assert report['distribution_summary']['teams_with_meaningful_changes'] == 0
    assert report['distribution_summary']['review_flag_counts'] == {
        'no_prior_snapshot': 2,
    }
    assert all(team['comparison_possible'] is False for team in report['teams'])
    assert all(team['confidence'] == 'none' for team in report['teams'])


def test_review_does_not_promote_tiny_capacity_changes():
    report = build_review(
        [snapshot(clean=5, active=8)],
        [snapshot(clean=4, active=8)],
    )
    team = report['teams'][0]

    assert team['all_meaningful_changes'] == []
    assert 'no_meaningful_change' in team['review_flags']
    assert 'tiny_change_promoted' not in team['review_flags']
    assert report['distribution_summary']['teams_with_no_meaningful_changes'] == 1
    assert report['distribution_summary']['count_by_change_type'] == {}


def test_review_does_not_select_tiny_capacity_change_over_structural_change():
    report = build_review(
        [
            snapshot(
                capacity_state='reduced',
                clean=5,
                coverage_label='Stable Coverage Safety',
            )
        ],
        [
            snapshot(
                capacity_state='thin',
                clean=4,
                coverage_label='Thin Coverage Safety',
            )
        ],
    )
    team = report['teams'][0]

    assert [
        change['change_type']
        for change in team['all_meaningful_changes']
    ] == ['rested_options_changed', 'coverage_safety_changed']
    assert team['selected_top_change']['change_type'] == 'coverage_safety_changed'
    assert team['review_summary'] == (
        'Coverage safety improved from Thin Coverage Safety to Stable Coverage Safety.'
    )
    assert 'tiny_change_promoted' not in team['review_flags']


def test_review_summary_counts_change_types_and_directions():
    report = build_review(
        [
            snapshot(
                team_id=1,
                team_name='Alpha Club',
                team_abbreviation='AAA',
                clean=5,
                coverage_label='Stable Coverage Safety',
            ),
            snapshot(
                team_id=2,
                team_name='Beta Club',
                team_abbreviation='BBB',
                active=6,
                clean=4,
            ),
        ],
        [
            snapshot(
                team_id=1,
                team_name='Alpha Club',
                team_abbreviation='AAA',
                clean=2,
                coverage_label='Thin Coverage Safety',
            ),
            snapshot(
                team_id=2,
                team_name='Beta Club',
                team_abbreviation='BBB',
                active=8,
                clean=4,
            ),
        ],
    )
    summary = report['distribution_summary']

    assert summary['teams_reviewed'] == 2
    assert summary['teams_with_comparison_available'] == 2
    assert summary['teams_with_meaningful_changes'] == 2
    assert summary['count_by_change_type'] == {
        'coverage_safety_changed': 1,
        'rested_options_changed': 1,
        'usable_bullpen_depth_changed': 1,
    }
    assert summary['count_by_change_direction'] == {
        'decreased': 1,
        'improved': 1,
        'increased': 1,
    }


def test_review_flags_governance_language_without_changing_engine_output():
    report = build_review(
        [
            snapshot(
                identity_key='recommendation_identity',
                identity_label='Recommended Best Bullpen',
            )
        ],
        [
            snapshot(
                identity_key='prediction_identity',
                identity_label='Projected Worst Bullpen',
            )
        ],
    )

    flags = report['teams'][0]['review_flags']
    assert 'recommendation_language' in flags
    assert 'prediction_language' in flags
    assert 'ranking_language' in flags
    assert report['teams'][0]['review_summary'] == 'Bullpen identity changed between snapshots.'
    assert 'identity_label_public_leak' not in flags
    assert report['distribution_summary']['review_flag_counts']['recommendation_language'] == 1
