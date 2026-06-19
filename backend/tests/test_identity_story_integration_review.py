from datetime import datetime, timezone

from services.bullpen_identity import (
    IDENTITY_FLEXIBLE_DISTRIBUTION,
    IDENTITY_LABELS,
    IDENTITY_UNKNOWN,
)
from services.identity_story_integration_review import (
    CAPABILITY,
    build_identity_story_integration_review,
)


def identity_payload(
    *,
    identity_key=IDENTITY_FLEXIBLE_DISTRIBUTION,
    confidence='medium',
    caveats=None,
):
    return {
        'identity_key': identity_key,
        'identity_label': IDENTITY_LABELS[identity_key],
        'confidence': confidence,
        'caveats': list(caveats or []),
    }


def capacity_item(team_id, team_name, team_abbreviation, *, identity=None):
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'bullpen_identity': identity if identity is not None else identity_payload(),
    }


def story_item(
    team_id,
    team_name,
    team_abbreviation,
    *,
    rule_key='pressure_distribution',
    narrative=None,
    integration=None,
    identity=None,
):
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'rule_key': rule_key,
        'rule_label': 'Pressure Distribution',
        'narrative': narrative or (
            f'The {team_name} bullpen enters tonight with room to maneuver.\n\n'
            'Recent relief work has moved through a lot of different hands. '
            'The shape is less about one arm and more about how many paths are still open.\n\n'
            'That gives the staff more than one way to get through a game.'
        ),
        'story_facts': {
            'team': {
                'team_id': team_id,
                'team_name': team_name,
                'team_abbreviation': team_abbreviation,
            },
            'supporting_context': 'Recent relief work has been spread across 8 relievers.',
            'pressure_source': 'The shape comes from recent work being spread across more of the bullpen.',
            'workload_pattern': 'The workload pattern is broad: 8 relievers have shared the work.',
            'story_identity_integration': integration or {
                'applied': True,
                'text': 'The shape is less about one arm and more about how many paths are still open.',
                'reason': 'usable_width',
            },
        },
        'computed': {
            'bullpen_identity': identity if identity is not None else identity_payload(),
            'story_identity_integration': integration or {
                'applied': True,
                'text': 'The shape is less about one arm and more about how many paths are still open.',
                'reason': 'usable_width',
            },
        },
    }


def dashboard_payload(teams, stories):
    return {
        'capacity_intelligence': {
            'teams': teams,
            'by_team_id': {str(team['team_id']): team for team in teams},
        },
        'four_beat_stories': {
            'items': stories,
        },
    }


def test_identity_story_review_reports_story_output_without_selecting_new_story():
    team = capacity_item(1, 'Alpha Club', 'ALP')
    story = story_item(1, 'Alpha Club', 'ALP', rule_key='pressure_distribution')

    report = build_identity_story_integration_review(
        dashboard_payload([team], [story]),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=1,
    )

    assert report['capability'] == CAPABILITY
    assert report['complete_team_count'] is True
    assert report['selection_made'] is False
    assert report['teams'][0]['selected_story_key'] == 'pressure_distribution'
    assert report['teams'][0]['selected_story_archetype'] == 'flexible_bullpen'
    assert report['teams'][0]['identity_text_applied'] is True
    assert report['teams'][0]['identity_sentence'] in report['teams'][0]['story_text']
    assert report['distribution_summary']['identity_text_applied_count'] == 1
    assert report['distribution_summary']['identity_text_skipped_count'] == 0
    assert report['distribution_summary']['applied_count_by_identity_key'] == {
        IDENTITY_FLEXIBLE_DISTRIBUTION: 1,
    }


def test_identity_story_review_flags_raw_label_and_governance_language():
    team = capacity_item(1, 'Alpha Club', 'ALP')
    story = story_item(
        1,
        'Alpha Club',
        'ALP',
        narrative=(
            'Flexible Distribution Bullpen is the phrase that should not be public.\n\n'
            'This would recommend a move and includes prediction language.'
        ),
    )

    report = build_identity_story_integration_review(
        dashboard_payload([team], [story]),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=1,
    )
    flags = report['teams'][0]['review_flags']

    assert 'raw_identity_label_leaked' in flags
    assert 'governance_language_detected' in flags
    assert report['distribution_summary']['review_flag_counts']['raw_identity_label_leaked'] == 1


def test_identity_story_review_flags_low_confidence_application_and_skips_unknown():
    low_identity = identity_payload(confidence='low')
    low_team = capacity_item(1, 'Alpha Club', 'ALP', identity=low_identity)
    low_story = story_item(1, 'Alpha Club', 'ALP', identity=low_identity)

    unknown_identity = identity_payload(
        identity_key=IDENTITY_UNKNOWN,
        confidence='low',
    )
    unknown_team = capacity_item(2, 'Beta Club', 'BET', identity=unknown_identity)
    unknown_story = story_item(
        2,
        'Beta Club',
        'BET',
        identity=unknown_identity,
        integration={
            'applied': False,
            'text': None,
            'reason': 'unknown_or_low_confidence_identity',
        },
    )

    report = build_identity_story_integration_review(
        dashboard_payload([low_team, unknown_team], [low_story, unknown_story]),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=2,
    )
    by_abbr = {team['team_abbreviation']: team for team in report['teams']}

    assert 'low_confidence_identity_text_applied' in by_abbr['ALP']['review_flags']
    assert by_abbr['BET']['identity_text_applied'] is False
    assert by_abbr['BET']['identity_sentence'] is None
    assert 'low_confidence_identity_text_applied' not in by_abbr['BET']['review_flags']
    assert report['distribution_summary']['identity_text_applied_count'] == 1
    assert report['distribution_summary']['identity_text_skipped_count'] == 1


def test_identity_story_review_flags_repeated_identity_sentence_after_summary_pass():
    sentence = 'The shape is less about one arm and more about how many paths are still open.'
    teams = [
        capacity_item(team_id, f'Team {team_id}', f'T{team_id}')
        for team_id in range(1, 6)
    ]
    stories = [
        story_item(team['team_id'], team['team_name'], team['team_abbreviation'])
        for team in teams
    ]

    report = build_identity_story_integration_review(
        dashboard_payload(teams, stories),
        generated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        expected_team_count=5,
    )

    assert report['distribution_summary']['identity_sentence_counts'][sentence] == 5
    assert report['distribution_summary']['review_flag_counts'][
        'identity_sentence_repeated_too_often'
    ] == 5
    assert all(
        'identity_sentence_repeated_too_often' in team['review_flags']
        for team in report['teams']
    )
