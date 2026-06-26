"""Tests for evidence-aware Story Writers (COIN).

Writers now read StoryPackage.evidence_blocks to render observation and evidence
sections and to use real names/numbers — without inventing anything. These build
a real StoryPackage and assert the richer output, the fail-closed rules, and that
the safety guarantees (feed-only, no future language, LOW neutral) still hold.
"""

import re

from story_orchestrator import build_story_package
from story_writers import DashboardStoryWriter, MorningBriefWriter, TeamStoryWriter

_FORBIDDEN_FUTURE = ('tomorrow', 'tonight', 'next game', 'next week', 'upcoming', 'series')


def _completed_ctx(**over):
    base = {
        'team_id': 1, 'game_pk': 700, 'confidence': 'HIGH',
        'bullpen_story_tag': 'lost_game_shape', 'game_shape_created': 'normal_start',
        'lead_protected': False, 'lead_lost': True, 'lead_when_bullpen_entered': 4,
        'bullpen_entry_inning': 7, 'bullpen_entry_score_for': 6,
        'bullpen_entry_score_against': 2, 'largest_lead': 4, 'largest_deficit': 3,
        'late_runs_allowed': 7, 'runs_allowed_innings_7_to_9': 7, 'turning_inning': 8,
        'starter_name': 'Logan Webb', 'starter_ip': 6.0, 'starter_pitch_count': 95,
        'starter_exit_inning': 6,
        'key_relief_appearances': [
            {'name': 'Ryan Walker', 'innings': 0.2, 'runs_allowed': 4},
        ],
    }
    base.update(over)
    return base


def _team_context(clean_names=('Erik Miller', 'Tyler Rogers', 'Ryan Walker')):
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 3,
            'monitor_arms_count': 1, 'limited_arms_count': 1, 'unavailable_arms_count': 1,
            'clean_workload_options': [
                {'player_id': i, 'name': n, 'availability': 'Available'}
                for i, n in enumerate(clean_names)
            ],
            'secondary_options': [],
            'practical_close_game_paths_count': 2, 'optionality_band': 'thin',
        },
        'bullpen_concentration_context': {'concentration_band': 'concentrated',
                                          'window_days': 10, 'bullpen_workload_total_10d': 240},
        'rotation_context': {'bullpen_coverage_ip_7d': 9.0},
        'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _package(completed=None, team=None):
    return build_story_package(
        1,
        completed_game_context=completed if completed is not None else _completed_ctx(),
        team_context=team if team is not None else _team_context(),
    )


# ── Team story: observations + evidence ───────────────────────────────────────

def test_team_story_renders_observations_and_evidence():
    draft = TeamStoryWriter(_package()).write()
    # Observation section, translated to plain language.
    assert 'The bullpen did not protect the lead.' in draft.observations
    assert 'The starter created the conditions for the bullpen to finish the game.' in draft.observations
    # Evidence section, real facts only.
    assert 'Starter: Logan Webb, 6.0 IP, 95 pitches' in draft.evidence
    assert 'Largest lead: 4' in draft.evidence
    assert 'Late runs allowed: 7' in draft.evidence
    assert len(draft.evidence) <= 5
    # Body uses the starter name and exact innings.
    assert 'Logan Webb worked 6.0 innings' in draft.body


def test_rendered_text_includes_sections():
    text = TeamStoryWriter(_package()).write().rendered_text
    assert 'Why BaseballOS sees it:' in text
    assert 'Evidence:' in text
    assert '- Starter: Logan Webb, 6.0 IP, 95 pitches' in text


# ── Dashboard: concise, one evidence line ─────────────────────────────────────

def test_dashboard_stays_concise_with_one_evidence_line():
    draft = DashboardStoryWriter(_package()).write()
    assert draft.observations == []
    assert len(draft.evidence) <= 1
    assert len(draft.body) < len(TeamStoryWriter(_package()).write().body)


# ── Morning brief: reliever names vs counts ───────────────────────────────────

def test_morning_brief_lists_reliever_names_when_available():
    draft = MorningBriefWriter(_package()).write()
    assert 'Available arms: Erik Miller, Tyler Rogers, Ryan Walker.' in draft.body


def test_morning_brief_falls_back_to_count_when_names_missing():
    # Team context with counts but no named clean options.
    team = _team_context()
    team['bullpen_optionality_context']['clean_workload_options'] = []
    draft = MorningBriefWriter(_package(team=team)).write()
    assert 'Available arms: 3.' in draft.body
    assert 'Erik Miller' not in draft.body


# ── No invention / fail-closed ────────────────────────────────────────────────

def test_writers_do_not_invent_reliever_names():
    team = _team_context()
    # Names stripped; only player_ids remain.
    team['bullpen_optionality_context']['clean_workload_options'] = [{'player_id': 9}]
    draft = MorningBriefWriter(_package(team=team)).write()
    assert not re.search(r'Available arms: [A-Z][a-z]+ [A-Z]', draft.body)  # no names
    team_draft = TeamStoryWriter(_package(team=team)).write()
    assert all('Clean options:' not in line for line in team_draft.evidence)


def test_writers_do_not_mention_starter_when_absent():
    completed = _completed_ctx(starter_name=None, starter_ip=None, starter_pitch_count=None)
    draft = TeamStoryWriter(_package(completed=completed)).write()
    assert 'Logan Webb' not in draft.body
    assert all(not line.startswith('Starter:') for line in draft.evidence)
    # Falls back to the inning-based handoff phrasing.
    assert 'in the 7th inning' in draft.body


def test_writers_do_not_mention_late_runs_when_absent():
    completed = _completed_ctx(late_runs_allowed=None, runs_allowed_innings_7_to_9=None)
    draft = TeamStoryWriter(_package(completed=completed)).write()
    assert 'late runs' not in draft.body.lower()
    assert all('Late runs allowed' not in line for line in draft.evidence)


def test_key_relief_appearances_use_exact_numbers():
    draft = TeamStoryWriter(_package()).write()
    relief_lines = [line for line in draft.evidence if line.startswith('Key relief')]
    if relief_lines:
        assert 'Ryan Walker' in relief_lines[0]
        assert '4 runs' in relief_lines[0]


# ── Safety: feed-only, no future, LOW neutral, determinism ───────────────────

def test_low_confidence_remains_neutral_with_no_sections():
    pkg = _package(completed=_completed_ctx(confidence='LOW',
                                            bullpen_story_tag='insufficient_context'))
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        draft = writer_cls(pkg).write()
        assert draft.observations == []
        assert draft.evidence == []
        assert not re.search(r'\d+-run', draft.body)


def test_no_future_language_anywhere_in_render():
    pkg = _package()
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        text = writer_cls(pkg).write().rendered_text.lower()
        for term in _FORBIDDEN_FUTURE:
            assert term not in text, term


def test_evidence_aware_render_is_deterministic():
    pkg = _package()
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        assert writer_cls(pkg).write().to_dict() == writer_cls(pkg).write().to_dict()


def test_writers_consume_only_the_package_no_engine_imports():
    import os
    writers_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'story_writers')
    forbidden = ('from services', 'import services', 'from models', 'import models',
                 'utils.db', 'from app', 'import app')
    for name in os.listdir(writers_dir):
        if not name.endswith('.py'):
            continue
        source = open(os.path.join(writers_dir, name), encoding='utf-8').read()
        for token in forbidden:
            assert token not in source, f'{name} references {token!r}'
