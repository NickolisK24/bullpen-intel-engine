import json
from datetime import datetime, timezone

from services.bullpen_identity import build_bullpen_identity
from services.bullpen_identity_distribution_review import (
    CAPABILITY,
    build_bullpen_identity_distribution_review,
)


def capacity_item(
    *,
    team_id,
    team_name,
    team_abbreviation,
    capacity_state='healthy',
    resource_state='strong',
    active=8,
    clean=6,
    anchor=1,
    leverage=2,
    trusted=2,
    depth=1,
    top_available=1,
    hierarchy_confidence='high',
):
    payload = {
        'capability': 'bullpen_capacity_intelligence_v1',
        'source': 'backend',
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
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
            'trust_arms_unavailable': 0,
            'trust_capacity_unavailable_pct': 0,
        },
        'capacity_loss': {
            'status': 'clear',
            'limitations': [],
        },
    }
    payload['bullpen_identity'] = build_bullpen_identity(payload)
    return payload


def dashboard_payload(items):
    return {
        'capacity_intelligence': {
            'capability': 'league_bullpen_capacity_intelligence_v1',
            'teams': items,
            'by_team_id': {str(item['team_id']): item for item in items},
        },
    }


def test_review_orders_teams_alphabetically_and_includes_context_fields():
    later = capacity_item(
        team_id=2,
        team_name='Zulu Club',
        team_abbreviation='ZUL',
        depth=3,
    )
    earlier = capacity_item(
        team_id=1,
        team_name='Alpha Club',
        team_abbreviation='ALP',
        anchor=1,
        leverage=1,
        trusted=0,
        depth=1,
        active=7,
        clean=4,
    )

    report = build_bullpen_identity_distribution_review(
        dashboard_payload([later, earlier]),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=2,
    )

    assert report['capability'] == CAPABILITY
    assert report['complete_team_count'] is True
    assert report['ordering_basis'] == 'team_name_then_team_id'
    assert [team['team_abbreviation'] for team in report['teams']] == ['ALP', 'ZUL']

    first = report['teams'][0]
    assert set(first) >= {
        'team_name',
        'identity_key',
        'identity_label',
        'identity_summary',
        'supporting_traits',
        'caveats',
        'confidence',
        'context',
        'review_flags',
    }
    assert set(first['context']) >= {
        'capacity_state',
        'resource_health_state',
        'coverage_safety',
        'trust_structure',
    }
    assert set(first['context']['trust_structure']) >= {
        'summary',
        'anchor_count',
        'leverage_count',
        'trusted_group_size',
        'hierarchy_confidence',
    }


def test_review_distribution_and_flags_surface_unknowns_without_ranking():
    known = capacity_item(
        team_id=1,
        team_name='Alpha Club',
        team_abbreviation='ALP',
    )
    unknown = {
        'team_id': 2,
        'team_name': 'Beta Club',
        'team_abbreviation': 'BET',
    }

    report = build_bullpen_identity_distribution_review(
        dashboard_payload([known, unknown]),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=2,
    )

    assert report['identity_distribution']['Unknown / Insufficient Context'] == 1
    assert report['review_findings']['unknown_identity_count'] == 1
    assert report['review_findings']['unknown_identity_over_threshold'] is True
    assert report['review_findings']['teams_for_human_review'] == [
        {
            'team_id': 2,
            'team_name': 'Beta Club',
            'team_abbreviation': 'BET',
            'identity_label': 'Unknown / Insufficient Context',
            'review_flags': [
                'unknown_identity',
                'low_confidence',
                'coverage_needs_review',
            ],
        }
    ]


def test_review_output_keeps_governance_boundaries_and_no_score_leakage():
    report = build_bullpen_identity_distribution_review(
        dashboard_payload([
            capacity_item(
                team_id=1,
                team_name='Alpha Club',
                team_abbreviation='ALP',
            )
        ]),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=1,
    )

    assert report['ranking_applied'] is False
    assert report['selection_made'] is False
    assert report['prediction_applied'] is False

    allowed_governance_keys = {'ranking_applied', 'prediction_applied'}

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
            assert 'recommend' not in lowered
            assert 'prediction' not in lowered
            assert 'betting' not in lowered
            assert 'best' not in lowered
            assert 'worst' not in lowered

    visit(report)
    encoded = json.dumps({
        key: value
        for key, value in report.items()
        if key not in allowed_governance_keys
    }).lower()
    assert 'score' not in encoded
    assert 'recommend' not in encoded
    assert 'betting' not in encoded
