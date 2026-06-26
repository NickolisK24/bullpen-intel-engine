"""Tests for the Story Composition Pass (COIN).

These cover the priority-weighted composition: story length scales with
priority, CRITICAL adds opening context, HIGH adds a consequence, MEDIUM stays
to narrative + evidence (no observation list), LOW stays neutral — all while
remaining deterministic, evidence-backed, and free of invented facts.
"""

import re

from story_orchestrator import build_story_package
from story_writers import DashboardStoryWriter, MorningBriefWriter, TeamStoryWriter

_FORBIDDEN_FUTURE = ('tomorrow', 'tonight', 'next game', 'next week', 'upcoming', 'series')


def _ctx(**over):
    base = {
        'team_id': 1, 'game_pk': 700, 'confidence': 'HIGH',
        'bullpen_story_tag': 'lost_game_shape', 'game_shape_created': 'normal_start',
        'team_name': 'the Giants', 'lead_protected': False, 'lead_lost': True,
        'lead_when_bullpen_entered': 4, 'bullpen_entry_inning': 7,
        'bullpen_entry_score_for': 6, 'bullpen_entry_score_against': 2,
        'largest_lead': 4, 'largest_deficit': 3, 'late_runs_allowed': 7,
        'runs_allowed_innings_7_to_9': 7, 'turning_inning': 8,
        'starter_name': 'Landen Roupp', 'starter_ip': 6.0, 'starter_pitch_count': 95,
        'starter_exit_inning': 6,
        'key_relief_appearances': [
            {'name': 'Ryan Walker', 'innings': 0.2, 'runs_allowed': 4},
            {'name': 'Tyler Rogers', 'innings': 1.0, 'runs_allowed': 3},
        ],
    }
    base.update(over)
    return base


def _team_context(clean_names=('Erik Miller',)):
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 3,
            'clean_workload_options': [
                {'player_id': i, 'name': n, 'availability': 'Available'}
                for i, n in enumerate(clean_names)
            ],
            'secondary_options': [], 'practical_close_game_paths_count': 2,
            'optionality_band': 'thin',
        },
        'bullpen_concentration_context': {'concentration_band': 'concentrated', 'window_days': 10},
        'rotation_context': {}, 'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _team_story(**over):
    pkg = build_story_package(1, completed_game_context=_ctx(**over), team_context=_team_context())
    return TeamStoryWriter(pkg).write()


# A MEDIUM scenario (overexposed) and a HIGH scenario (protected).
def _medium_ctx():
    return _ctx(
        confidence='MEDIUM', bullpen_story_tag='bullpen_overexposed',
        game_shape_created='short_start', team_name='the Yankees',
        lead_lost=None, lead_protected=None, largest_lead=0, largest_deficit=2,
        late_runs_allowed=1, runs_allowed_innings_7_to_9=1,
        starter_name='Carlos Rodon', starter_ip=3.0, starter_pitch_count=62,
        bullpen_entry_inning=4, lead_when_bullpen_entered=None,
        key_relief_appearances=[{'name': 'Ian Hamilton', 'innings': 2.1, 'runs_allowed': 1}],
    )


def _high_ctx():
    return _ctx(
        bullpen_story_tag='protected_game_shape', team_name='the Rays',
        lead_protected=True, lead_lost=False, largest_lead=3, largest_deficit=0,
        late_runs_allowed=0, runs_allowed_innings_7_to_9=0, lead_when_bullpen_entered=2,
        starter_name='Shane Baz', starter_ip=6.0, turning_inning=None,
        key_relief_appearances=[{'name': 'Pete Fairbanks', 'innings': 1.0, 'runs_allowed': 0}],
    )


# ── Length scales with priority ───────────────────────────────────────────────

def test_story_length_varies_by_priority():
    critical = _team_story()                                  # lost -> CRITICAL
    high = TeamStoryWriter(build_story_package(
        1, completed_game_context=_high_ctx(), team_context=_team_context())).write()
    medium = TeamStoryWriter(build_story_package(
        1, completed_game_context=_medium_ctx(), team_context=_team_context())).write()
    assert len(critical.body) > len(high.body) > len(medium.body)


def test_critical_story_has_opening_context():
    draft = _team_story()
    assert draft.story_priority == 'CRITICAL'
    # Opening establishes the baseball situation with the starter, not the bullpen.
    assert draft.body.startswith('After their most recent game, Landen Roupp gave the Giants')
    assert draft.observations  # CRITICAL carries the "why" list
    assert draft.evidence


def test_high_story_has_consequence_no_opening():
    draft = TeamStoryWriter(build_story_package(
        1, completed_game_context=_high_ctx(), team_context=_team_context())).write()
    assert draft.story_priority == 'HIGH'
    # No starter-first opening; consequence sentence present.
    assert not draft.body.startswith('After their most recent game, Shane Baz gave')
    assert 'protecting the game shape the Rays built' in draft.body
    assert draft.observations and draft.evidence


def test_medium_story_is_concise_narrative_and_evidence_only():
    draft = TeamStoryWriter(build_story_package(
        1, completed_game_context=_medium_ctx(), team_context=_team_context())).write()
    assert draft.story_priority == 'MEDIUM'
    assert draft.observations == []          # MEDIUM has no "why" section
    assert draft.evidence                    # but keeps evidence
    # One narrative sentence, no consequence/state pile-up.
    assert draft.body.count('.') <= 1


def test_low_story_stays_neutral():
    draft = _team_story(confidence='LOW', bullpen_story_tag='insufficient_context')
    assert draft.observations == [] and draft.evidence == []
    assert not re.search(r'\d', draft.body)


# ── Natural composition / no template seams ───────────────────────────────────

def test_body_blends_evidence_into_one_paragraph():
    body = _team_story().body
    assert 'Landen Roupp' in body and 'four-run lead' in body
    assert 'Ryan Walker and Tyler Rogers combined to allow the decisive damage' in body
    # Not the old one-clause "inherited a lead" seam.
    assert 'the bullpen inherited a four-run lead' not in body


def test_body_does_not_open_every_sentence_with_bullpen():
    body = _team_story().body
    sentences = [s.strip() for s in body.split('. ') if s.strip()]
    bullpen_openers = sum(1 for s in sentences if s.lower().startswith('the bullpen'))
    assert bullpen_openers <= 1


# ── No invention / no duplicated evidence / determinism ───────────────────────

def test_no_invented_facts_when_starter_absent():
    draft = _team_story(starter_name=None, starter_ip=None, starter_pitch_count=None)
    assert 'Landen Roupp' not in draft.body
    assert all(not line.startswith('Starter:') for line in draft.evidence)


def test_evidence_has_no_duplicates():
    draft = _team_story()
    assert len(draft.evidence) == len(set(draft.evidence))


def test_composition_is_deterministic():
    pkg = build_story_package(1, completed_game_context=_ctx(), team_context=_team_context())
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        assert writer_cls(pkg).write().to_dict() == writer_cls(pkg).write().to_dict()


def test_no_future_language_in_composed_render():
    for ctx in (_ctx(), _high_ctx(), _medium_ctx()):
        pkg = build_story_package(1, completed_game_context=ctx, team_context=_team_context())
        for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
            text = writer_cls(pkg).write().rendered_text.lower()
            for term in _FORBIDDEN_FUTURE:
                assert term not in text, term


def test_morning_brief_names_relievers_and_dashboard_concise():
    pkg = build_story_package(1, completed_game_context=_ctx(),
                              team_context=_team_context(['Erik Miller', 'Sean Hjelle']))
    brief = MorningBriefWriter(pkg).write()
    assert 'Available arms: Erik Miller, Sean Hjelle.' in brief.body
    dashboard = DashboardStoryWriter(pkg).write()
    assert len(dashboard.evidence) <= 1
    assert dashboard.observations == []
