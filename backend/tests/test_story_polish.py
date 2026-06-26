"""Tests for the Final Writer Polish Pass (COIN).

Editorial refinements: team names replace generic subjects (failing closed to
"the club"), bullpen-state language is natural (no "profiles as"), near-duplicate
observations merge, evidence shows one lead/deficit line in story order, and the
morning brief is differentiated from the team story. All deterministic and
evidence-backed; nothing invented.
"""

from story_orchestrator import build_story_package
from story_writers import DashboardStoryWriter, MorningBriefWriter, TeamStoryWriter


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


def _team_context(optionality_band='thin', concentration_band='concentrated',
                  clean_names=('Erik Miller',)):
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 3,
            'clean_workload_options': [
                {'player_id': i, 'name': n, 'availability': 'Available'}
                for i, n in enumerate(clean_names)
            ],
            'secondary_options': [], 'practical_close_game_paths_count': 2,
            'optionality_band': optionality_band,
        },
        'bullpen_concentration_context': {'concentration_band': concentration_band,
                                          'window_days': 10},
        'rotation_context': {}, 'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _pkg(ctx_over=None, team=None):
    return build_story_package(1, completed_game_context=_ctx(**(ctx_over or {})),
                               team_context=team if team is not None else _team_context())


def _kept_alive_ctx():
    return {
        'bullpen_story_tag': 'bullpen_kept_team_alive', 'team_name': 'the Athletics',
        'lead_lost': None, 'lead_protected': None, 'comeback_completed': True,
        'deficit_when_bullpen_entered': 2, 'largest_lead': 1, 'largest_deficit': 3,
        'late_runs_allowed': 0, 'runs_allowed_innings_7_to_9': 0,
        'starter_name': 'JP Sears', 'starter_ip': 5.0, 'bullpen_entry_inning': 6,
        'lead_when_bullpen_entered': None,
    }


# ── Generic subjects replaced ─────────────────────────────────────────────────

def test_team_name_used_when_present():
    body = TeamStoryWriter(_pkg()).write().body
    assert 'the Giants' in body
    assert 'the team' not in body


def test_fails_closed_to_the_club_without_team_name():
    body = TeamStoryWriter(_pkg({'team_name': None})).write().body
    assert 'the club' in body
    assert 'the team' not in body


def test_team_possessive_grammar_is_correct():
    # "the Yankees" -> "the Yankees'" (not "Yankees's"), in the morning brief recap.
    brief = MorningBriefWriter(build_story_package(
        1,
        completed_game_context=_ctx(team_name='the Yankees', confidence='MEDIUM',
                                    bullpen_story_tag='bullpen_overexposed',
                                    game_shape_created='short_start', lead_lost=None,
                                    lead_protected=None, starter_name='Carlos Rodon',
                                    starter_ip=3.0),
        team_context=_team_context())).write()
    assert "the Yankees' bullpen" in brief.body
    assert "Yankees's" not in brief.body


# ── Natural bullpen-state language ────────────────────────────────────────────

def test_bullpen_state_uses_natural_language_not_profiles_as():
    body = TeamStoryWriter(_pkg()).write().body
    assert 'profiles as' not in body
    assert 'The relief corps is down to fewer rested options.' in body


# ── Observation merging ───────────────────────────────────────────────────────

def test_starter_observations_merge_into_one_line():
    obs = TeamStoryWriter(_pkg()).write().observations
    assert 'The starter went deep and set the bullpen up to finish the game.' in obs
    # The two un-merged starter phrases must not both appear.
    assert 'The starter went deep and held down the bullpen workload.' not in obs
    assert 'The starter set the bullpen up to finish the game.' not in obs


def test_late_run_observations_merge_into_one_line():
    obs = TeamStoryWriter(_pkg()).write().observations
    assert 'The damage came after the starter exited and piled up late.' in obs
    assert 'The runs piled up late rather than in one moment.' not in obs


# ── Evidence: one lead/deficit line, in order, late runs survives ─────────────

def test_evidence_shows_only_the_story_relevant_lead_or_deficit():
    lost = TeamStoryWriter(_pkg()).write().evidence
    assert any(b.startswith('Largest lead') for b in lost)
    assert not any(b.startswith('Largest deficit') for b in lost)

    kept = TeamStoryWriter(build_story_package(
        1, completed_game_context=_ctx(**_kept_alive_ctx()),
        team_context=_team_context())).write().evidence
    assert any(b.startswith('Largest deficit') for b in kept)
    assert not any(b.startswith('Largest lead') for b in kept)


def test_evidence_capped_at_five_and_keeps_late_runs():
    ev = TeamStoryWriter(_pkg()).write().evidence
    assert len(ev) <= 5
    assert 'Late runs allowed: 7' in ev
    # Order: starter first, then the lead.
    assert ev[0].startswith('Starter:')
    assert ev[1].startswith('Largest lead')


# ── Morning brief differentiation ─────────────────────────────────────────────

def test_morning_brief_differs_from_team_story():
    pkg = _pkg()
    team = TeamStoryWriter(pkg).write()
    brief = MorningBriefWriter(pkg).write()
    assert brief.body != team.body
    assert brief.observations == []                 # brief omits the "why" list
    assert len(brief.body) < len(team.body)         # one-sentence recap, not full story
    assert 'Available arms: Erik Miller.' in brief.body
    assert 'The relief corps is down to fewer rested options.' in brief.body


def test_dashboard_leads_with_team_and_stays_short():
    dash = DashboardStoryWriter(_pkg()).write()
    assert dash.body.startswith('The Giants')
    assert dash.observations == []
    assert len(dash.evidence) <= 1


# ── Determinism preserved ─────────────────────────────────────────────────────

def test_polished_writers_are_deterministic():
    pkg = _pkg()
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        assert writer_cls(pkg).write().to_dict() == writer_cls(pkg).write().to_dict()
