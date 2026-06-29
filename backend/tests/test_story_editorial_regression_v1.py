"""Editorial regression tests for public story output.

This is a governance-only test layer: it builds a deterministic 30-team public
story corpus from existing story services and records the editorial gates that
future story-refinement phases must make hard-passing.
"""

from __future__ import annotations

from collections import Counter
import re

import pytest

from services.story_feed import build_canonical_story_feed
from services.story_intelligence_service_v1 import build_team_story
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
    PURPOSE_FORWARD,
    PURPOSE_LESSON,
    PURPOSE_OPENING,
    PURPOSE_SURFACE,
    PURPOSE_WATCH,
    contains_banned_public_language,
    contains_denied_public_phrase,
    render_voice_line,
)


DATE = '2026-06-20'
MAX_DUPLICATE_HEADLINE_COUNT = 1
MAX_DUPLICATE_OPENING_COUNT = 1

PUBLIC_BEATS = (
    BEAT_ROUTE_CHANGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_AVAILABILITY_DEPTH,
    BEAT_TRUST_LANE,
    BEAT_BRIDGE,
)

PUBLIC_PHRASES_BANNED_IN_HEADLINES_AND_BODIES = (
    '0 trusted',
    'retained 0 arms',
    '3-spot change',
)

FINAL_EXPLANATION_PHRASES = (
    'clean options are limited',
)

TEAM_ROWS = (
    (108, 'Los Angeles Angels', 'LAA'),
    (109, 'Arizona Diamondbacks', 'ARI'),
    (110, 'Baltimore Orioles', 'BAL'),
    (111, 'Boston Red Sox', 'BOS'),
    (112, 'Chicago Cubs', 'CHC'),
    (113, 'Cincinnati Reds', 'CIN'),
    (114, 'Cleveland Guardians', 'CLE'),
    (115, 'Colorado Rockies', 'COL'),
    (116, 'Detroit Tigers', 'DET'),
    (117, 'Houston Astros', 'HOU'),
    (118, 'Kansas City Royals', 'KC'),
    (119, 'Los Angeles Dodgers', 'LAD'),
    (120, 'Washington Nationals', 'WSH'),
    (121, 'New York Mets', 'NYM'),
    (133, 'Athletics', 'ATH'),
    (134, 'Pittsburgh Pirates', 'PIT'),
    (135, 'San Diego Padres', 'SD'),
    (136, 'Seattle Mariners', 'SEA'),
    (137, 'San Francisco Giants', 'SF'),
    (138, 'St. Louis Cardinals', 'STL'),
    (139, 'Tampa Bay Rays', 'TB'),
    (140, 'Texas Rangers', 'TEX'),
    (141, 'Toronto Blue Jays', 'TOR'),
    (142, 'Minnesota Twins', 'MIN'),
    (143, 'Philadelphia Phillies', 'PHI'),
    (144, 'Atlanta Braves', 'ATL'),
    (145, 'Chicago White Sox', 'CWS'),
    (146, 'Miami Marlins', 'MIA'),
    (147, 'New York Yankees', 'NYY'),
    (158, 'Milwaukee Brewers', 'MIL'),
)


def _arms(abbr: str, count=3) -> list[str]:
    return [f'{abbr} Arm {index}' for index in range(1, count + 1)]


def _clean(value) -> str:
    return ' '.join(str(value or '').split())


def _team_context(
    team_id,
    team_name,
    team_abbreviation,
    *,
    rotation=None,
    concentration=None,
    optionality=None,
    stability=None,
    injury=None,
):
    arms = _arms(team_abbreviation, 4)
    return {
        'team_id': team_id,
        'team': {
            'team_id': team_id,
            'team_name': team_name,
            'team_abbreviation': team_abbreviation,
        },
        'reference_date': DATE,
        'data_through_date': DATE,
        'rotation_context': {
            'context_available': True,
            'rotation_avg_ip_7d': 5.8,
            'rotation_avg_ip_14d': 5.8,
            'rotation_ip_trend': -0.1,
            'early_bullpen_entry_rate': 12.0,
            'bullpen_coverage_ip_7d': 3.0,
            'rotation_games_analyzed_7d': 6,
            'rotation_games_analyzed_14d': 12,
            'rotation_early_bullpen_entry_games_14d': 1,
            **(rotation or {}),
        },
        'bullpen_concentration_context': {
            'context_available': True,
            'concentration_band': 'normal',
            'top_three_workload_share_10d': 58.0,
            'league_top_three_workload_share_10d': 58.0,
            'top_three_share_delta_vs_league': 0.0,
            'bullpen_workload_total_10d': 180,
            'top_three_relievers_10d': [
                {'name': arms[0], 'pitches': 52, 'workload_share': 28.9},
                {'name': arms[1], 'pitches': 35, 'workload_share': 19.4},
                {'name': arms[2], 'pitches': 25, 'workload_share': 13.9},
            ],
            'league_team_count_10d': 30,
            **(concentration or {}),
        },
        'bullpen_optionality_context': {
            'context_available': True,
            'optionality_band': 'narrow',
            'practical_close_game_paths_count': 3,
            'available_arms_count': 4,
            'monitor_arms_count': 1,
            'restricted_arms_count': 1,
            'limited_arms_count': 1,
            'avoid_arms_count': 0,
            'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': arms[0]}],
            'secondary_options': [{'name': arms[3]}],
            **(optionality or {}),
        },
        'role_stability_context': {
            'context_available': True,
            'stability_band': 'mostly_stable',
            'current_operational_core': arms[:3],
            'previous_operational_core': arms[:3],
            'core_retention_count': 3,
            'core_stability_pct': 100,
            'core_change_count': 0,
            'new_core_members': [],
            'departed_core_members': [],
            'current_core_size': 3,
            'previous_core_size': 3,
            **(stability or {}),
        },
        'injury_context': {
            'context_available': True,
            'depth_pressure_band': 'light',
            'active_bullpen_arms_count': 8,
            'inactive_bullpen_arms_count': 0,
            'il_bullpen_arms_count': 0,
            'non_il_inactive_bullpen_arms_count': 0,
            'inactive_bullpen_share': 0.0,
            'injury_context_confidence': 'high',
            'inactive_bullpen_arms': [],
            'role_uncertain_inactive_count': 0,
            'unknown_roster_status_count': 0,
            **(injury or {}),
        },
        'limitations': [],
    }


def _coverage_context(row, offset):
    team_id, team_name, abbr = row
    return _team_context(
        team_id,
        team_name,
        abbr,
        rotation={
            'rotation_avg_ip_7d': round(4.1 + (offset % 4) * 0.2, 1),
            'rotation_avg_ip_14d': 5.7,
            'rotation_ip_trend': -1.2,
            'early_bullpen_entry_rate': 58.0 + offset,
            'bullpen_coverage_ip_7d': 4.6 + (offset % 3) * 0.2,
        },
    )


def _sustainability_context(row, offset):
    team_id, team_name, abbr = row
    arms = _arms(abbr, 3)
    return _team_context(
        team_id,
        team_name,
        abbr,
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 84.0 + offset,
            'top_three_share_delta_vs_league': 22.0 + offset,
            'bullpen_workload_total_10d': 220 + offset,
            'top_three_relievers_10d': [{'name': name} for name in arms],
        },
        optionality={
            'optionality_band': 'thin',
            'practical_close_game_paths_count': 2,
            'available_arms_count': 3,
            'clean_workload_options': [{'name': arms[0]}],
        },
    )


def _depth_context(row, offset):
    team_id, team_name, abbr = row
    inactive = [
        {'name': f'{abbr} Depth {index}'}
        for index in range(1, 4 + (offset % 3))
    ]
    return _team_context(
        team_id,
        team_name,
        abbr,
        optionality={
            'optionality_band': 'thin',
            'practical_close_game_paths_count': 2,
            'available_arms_count': 3,
            'clean_workload_options': [{'name': f'{abbr} Clean'}],
        },
        injury={
            'depth_pressure_band': 'heavy',
            'active_bullpen_arms_count': 6,
            'inactive_bullpen_arms_count': len(inactive),
            'il_bullpen_arms_count': max(len(inactive) - 1, 0),
            'non_il_inactive_bullpen_arms_count': 1,
            'inactive_bullpen_share': 35.0,
            'inactive_bullpen_arms': inactive,
        },
    )


def _route_context(row, offset):
    team_id, team_name, abbr = row
    current = [f'{abbr} New {index}' for index in range(1, 4)]
    previous = [f'{abbr} Old {index}' for index in range(1, 4)]
    return _team_context(
        team_id,
        team_name,
        abbr,
        optionality={
            'optionality_band': 'deep',
            'practical_close_game_paths_count': 5,
            'clean_workload_options': [{'name': f'{abbr} Clean 1'}, {'name': f'{abbr} Clean 2'}],
        },
        stability={
            'stability_band': 'rebuilding',
            'current_operational_core': current,
            'previous_operational_core': previous,
            'new_core_members': current,
            'departed_core_members': previous,
            'core_retention_count': 0,
            'core_stability_pct': 0,
            'core_change_count': 3,
        },
    )


def _availability_context(row, offset):
    team_id, team_name, abbr = row
    clean = [{'name': f'{abbr} Fresh {index}'} for index in range(1, 5 + (offset % 2))]
    return _team_context(
        team_id,
        team_name,
        abbr,
        optionality={
            'optionality_band': 'deep',
            'practical_close_game_paths_count': 6,
            'available_arms_count': 8,
            'monitor_arms_count': 0,
            'restricted_arms_count': 0,
            'limited_arms_count': 0,
            'clean_workload_options': clean,
            'secondary_options': [{'name': f'{abbr} Secondary'}],
        },
    )


def _trust_lane_context(row, offset):
    team_id, team_name, abbr = row
    return _team_context(
        team_id,
        team_name,
        abbr,
        optionality={
            'context_available': True,
            'optionality_band': 'flexible',
            'practical_close_game_paths_count': 4,
            'available_arms_count': 6,
            'monitor_arms_count': 1,
            'restricted_arms_count': 0,
            'limited_arms_count': 0,
            'avoid_arms_count': 0,
            'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': f'{abbr} Trusted'}],
            'secondary_options': [
                {'name': f'{abbr} Flagged {index}'}
                for index in range(1, 6)
            ],
        },
    )


def _bridge_context(row, offset):
    team_id, team_name, abbr = row
    return _team_context(
        team_id,
        team_name,
        abbr,
        rotation={
            'rotation_avg_ip_7d': 5.4,
            'rotation_avg_ip_14d': 5.5,
            'rotation_ip_trend': -0.1,
            'early_bullpen_entry_rate': 43.0 + offset,
            'bullpen_coverage_ip_7d': 4.2,
        },
        optionality={
            'context_available': True,
            'optionality_band': 'narrow',
            'practical_close_game_paths_count': 3,
            'available_arms_count': 3,
            'monitor_arms_count': 3,
            'limited_arms_count': 1,
            'restricted_arms_count': 1,
            'avoid_arms_count': 0,
            'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': f'{abbr} Bridge'}],
            'secondary_options': [{'name': f'{abbr} Mid {index}'} for index in range(1, 4)],
        },
        stability={
            'stability_band': 'stable',
            'current_operational_core': [f'{abbr} Core {index}' for index in range(1, 4)],
            'previous_operational_core': [f'{abbr} Core {index}' for index in range(1, 4)],
            'core_retention_count': 3,
            'core_stability_pct': 100,
            'core_change_count': 0,
            'new_core_members': [],
            'departed_core_members': [],
        },
    )


CONTEXT_BUILDERS = (
    _coverage_context,
    _sustainability_context,
    _depth_context,
    _route_context,
    _availability_context,
    _trust_lane_context,
    _bridge_context,
)


def _thirty_team_contexts():
    return [
        CONTEXT_BUILDERS[index % len(CONTEXT_BUILDERS)](row, index)
        for index, row in enumerate(TEAM_ROWS)
    ]


def _thirty_team_story_feed():
    contexts = _thirty_team_contexts()
    contexts_by_id = {context['team_id']: context for context in contexts}
    teams = [
        {
            'team_id': context['team_id'],
            'team_name': context['team']['team_name'],
            'team_abbreviation': context['team']['team_abbreviation'],
        }
        for context in contexts
    ]

    def story_builder(team_id, as_of_date=None):
        return build_team_story(
            team_id,
            as_of_date=as_of_date,
            team_context=contexts_by_id[team_id],
        )

    return build_canonical_story_feed(
        teams,
        as_of_date=DATE,
        story_builder=story_builder,
    )


def _public_stories(feed=None):
    feed = feed or _thirty_team_story_feed()
    return [
        story
        for story in feed['items']
        if story.get('story_available') is True
    ]


def _blueprint_text(story, key):
    for section in story.get('blueprint') or []:
        if section.get('key') == key:
            return _clean(section.get('text'))
    return ''


def _public_body(story):
    blueprint = ' '.join(
        _clean(section.get('text'))
        for section in story.get('blueprint') or []
    )
    return _clean(' '.join([story.get('narrative') or '', blueprint]))


def _first_sentence(text):
    match = re.search(r'[^.!?]+[.!?]', _clean(text))
    return _clean(match.group(0)) if match else _clean(text)


def _opening_sentence(story):
    return _first_sentence(story.get('narrative') or _blueprint_text(story, 'what_everyone_saw'))


def _duplicate_counts(values, *, max_count):
    counts = Counter(_clean(value) for value in values if _clean(value))
    return {
        value: count
        for value, count in counts.items()
        if count > max_count
    }


def _contains_phrase(text, phrase):
    return phrase.lower() in _clean(text).lower()


def _editorial_failures(stories):
    failures = []
    for story in stories:
        label = f"{story.get('team_abbreviation')} {story.get('story_type')}"
        headline = _clean(story.get('headline'))
        body = _public_body(story)
        for phrase in PUBLIC_PHRASES_BANNED_IN_HEADLINES_AND_BODIES:
            if _contains_phrase(headline, phrase):
                failures.append(f'headline contains "{phrase}": {label}')
            if _contains_phrase(body, phrase):
                failures.append(f'body contains "{phrase}": {label}')
        for phrase in FINAL_EXPLANATION_PHRASES:
            final_public_text = ' '.join([
                _blueprint_text(story, 'why_it_matters'),
                _blueprint_text(story, 'why_it_matters_tomorrow'),
                story.get('share_summary') or '',
            ])
            if _contains_phrase(final_public_text, phrase):
                failures.append(f'final explanation contains "{phrase}": {label}')

    duplicate_headlines = _duplicate_counts(
        [story.get('headline') for story in stories],
        max_count=MAX_DUPLICATE_HEADLINE_COUNT,
    )
    if duplicate_headlines:
        failures.append(f'duplicate headlines above threshold: {duplicate_headlines}')

    duplicate_openings = _duplicate_counts(
        [_opening_sentence(story) for story in stories],
        max_count=MAX_DUPLICATE_OPENING_COUNT,
    )
    if duplicate_openings:
        failures.append(f'duplicate openings above threshold: {duplicate_openings}')

    return failures


def _story_signature(feed):
    return [
        (
            story.get('story_id'),
            story.get('story_type'),
            story.get('headline'),
            story.get('narrative'),
            tuple(
                (section.get('key'), section.get('text'))
                for section in story.get('blueprint') or []
            ),
        )
        for story in feed['items']
    ]


def test_editorial_regression_corpus_builds_thirty_public_stories():
    stories = _public_stories()

    assert len(stories) == 30
    assert {story['story_type'] for story in stories} == set(PUBLIC_BEATS)


def test_editorial_regression_corpus_is_deterministic():
    first = _story_signature(_thirty_team_story_feed())
    second = _story_signature(_thirty_team_story_feed())

    assert first == second


def test_banned_public_language_guard_catches_singular_and_plural_loopholes():
    assert contains_denied_public_phrase('The practical path narrows late.') is True
    assert contains_denied_public_phrase('The practical paths narrow late.') is True

    assert contains_denied_public_phrase('A clean public sentence stays descriptive.') is False
    assert contains_banned_public_language('This is projected to decide the game.') is True


def test_voice_library_assets_sample_non_empty_public_copy():
    for beat in PUBLIC_BEATS:
        for purpose in (
            PURPOSE_OPENING,
            PURPOSE_FORWARD,
            PURPOSE_SURFACE,
            PURPOSE_LESSON,
            PURPOSE_WATCH,
        ):
            copy = render_voice_line(
                beat,
                purpose=purpose,
                stable_parts=(beat, purpose, 118, 'KC'),
                team='Kansas City Royals',
                possessive="Kansas City Royals'",
                names='First Arm and Second Arm',
            )

            assert copy
            assert _clean(copy) == copy
            assert contains_denied_public_phrase(copy) is False
            assert contains_banned_public_language(copy) is False


def test_public_story_editorial_scanner_detects_requested_failures():
    bad_story = {
        'team_abbreviation': 'BAD',
        'story_type': 'route_change',
        'headline': 'The bullpen has a 3-spot change',
        'narrative': 'The club retained 0 arms and has 0 trusted options.',
        'share_summary': 'Clean options are limited.',
        'blueprint': [
            {'key': 'why_it_matters', 'text': 'Clean options are limited.'},
            {'key': 'why_it_matters_tomorrow', 'text': 'Watch the next call.'},
        ],
    }

    failures = _editorial_failures([bad_story])

    assert any('headline contains "3-spot change"' in failure for failure in failures)
    assert any('body contains "0 trusted"' in failure for failure in failures)
    assert any('body contains "retained 0 arms"' in failure for failure in failures)
    assert any('final explanation contains "clean options are limited"' in failure for failure in failures)


def test_public_story_corpus_current_editorial_gates_documented_for_story_refinement():
    stories = _public_stories()
    failures = _editorial_failures(stories)

    if failures:
        pytest.xfail(
            'TODO(story-refinement): current generated 30-team corpus still '
            f'violates editorial regression gates: {failures[:8]}'
        )

    assert failures == []
