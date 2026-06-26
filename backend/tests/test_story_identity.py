"""Tests for the Editorial Identity Pass (COIN).

Stories should sound like BaseballOS: no generic/templated phrasing, a factual
"so what" takeaway, names led, and a morning brief that explains today's bullpen
picture. All deterministic and evidence-backed; nothing invented.
"""

from story_orchestrator import build_story_package
from story_writers import DashboardStoryWriter, MorningBriefWriter, TeamStoryWriter

# Phrases the editorial identity pass deliberately retired.
_BANNED = (
    'the team', 'profiles as', "couldn't hold it", 'could not hold it',
    'without giving anything back', 'game shape', 'remains in good shape',
    'thin on rested arms',
)


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


def _protected_ctx():
    return {'bullpen_story_tag': 'protected_game_shape', 'team_name': 'the Rays',
            'lead_lost': False, 'lead_protected': True, 'largest_lead': 3,
            'largest_deficit': 0, 'late_runs_allowed': 0, 'runs_allowed_innings_7_to_9': 0,
            'lead_when_bullpen_entered': 2, 'starter_name': 'Shane Baz', 'starter_ip': 6.0,
            'turning_inning': None,
            'key_relief_appearances': [{'name': 'Pete Fairbanks', 'innings': 1.0, 'runs_allowed': 0}]}


def _medium_ctx():
    return {'confidence': 'MEDIUM', 'bullpen_story_tag': 'bullpen_overexposed',
            'game_shape_created': 'short_start', 'team_name': 'the Yankees',
            'lead_lost': None, 'lead_protected': None, 'largest_lead': 0,
            'largest_deficit': 2, 'late_runs_allowed': 1, 'runs_allowed_innings_7_to_9': 1,
            'starter_name': 'Carlos Rodon', 'starter_ip': 3.0, 'bullpen_entry_inning': 4,
            'lead_when_bullpen_entered': None,
            'key_relief_appearances': [{'name': 'Ian Hamilton', 'innings': 2.1, 'runs_allowed': 1}]}


def _all_text(pkg):
    return ' '.join(
        w(pkg).write().rendered_text for w in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter)
    )


# ── Generic / templated language eliminated ───────────────────────────────────

def test_no_banned_generic_phrases_across_named_stories():
    for ctx in (None, _protected_ctx(), _medium_ctx()):
        text = _all_text(_pkg(ctx)).lower()
        for phrase in _BANNED:
            assert phrase not in text, (ctx, phrase)


def test_stories_lead_with_team_and_player_names():
    body = TeamStoryWriter(_pkg()).write().body
    assert 'the Giants' in body
    assert 'Landen Roupp' in body
    assert 'Ryan Walker and Tyler Rogers' in body


# ── "So what" takeaway endings ────────────────────────────────────────────────

def test_critical_story_ends_with_a_consequence_takeaway():
    body = TeamStoryWriter(_pkg()).write().body
    assert body.rstrip().endswith(
        'That late collapse leaves the relief corps down to fewer rested options.')


def test_high_protected_story_ends_with_clean_finish_takeaway():
    deep_pen = _team_context(optionality_band='deep', concentration_band='balanced',
                             clean_names=['Garrett Cleavinger'])
    body = TeamStoryWriter(_pkg(_protected_ctx(), team=deep_pen)).write().body
    assert body.rstrip().endswith('The clean finish keeps the relief corps deep in fresh arms.')


def test_medium_story_has_no_takeaway():
    # MEDIUM is matter-of-fact: narrative only, no closing takeaway sentence.
    body = TeamStoryWriter(_pkg(_medium_ctx())).write().body
    assert 'relief corps' not in body
    assert body.count('.') <= 1


# ── Editorial rhythm (varied sentence length) ─────────────────────────────────

def test_critical_story_varies_sentence_length():
    body = TeamStoryWriter(_pkg()).write().body
    sentences = [s.strip() for s in body.split('. ') if s.strip()]
    lengths = [len(s.split()) for s in sentences]
    assert len(set(lengths)) >= 3            # not all the same length
    assert min(lengths) <= 4                 # a short punch ("It didn't last")
    assert max(lengths) >= 12                # a long opener


# ── Morning brief identity: yesterday -> today's bullpen ──────────────────────

def test_morning_brief_explains_todays_bullpen_with_names():
    brief = MorningBriefWriter(_pkg(team=_team_context(clean_names=['Erik Miller', 'Sean Hjelle']))).write()
    assert 'Available arms: Erik Miller, Sean Hjelle.' in brief.body
    assert "Yesterday's late damage leaves the relief corps" in brief.body
    assert brief.observations == []


def test_dashboard_stays_headline_plus_one_line_plus_one_fact():
    dash = DashboardStoryWriter(_pkg()).write()
    assert dash.body.count('.') == 1
    assert len(dash.evidence) <= 1
    assert dash.observations == []


# ── No future language; determinism ───────────────────────────────────────────

def test_no_future_language_in_identity_render():
    forbidden = ('tomorrow', 'tonight', 'next game', 'next week', 'upcoming', 'series')
    for ctx in (None, _protected_ctx(), _medium_ctx()):
        text = _all_text(_pkg(ctx)).lower()
        for term in forbidden:
            assert term not in text, term


def test_identity_render_is_deterministic():
    pkg = _pkg()
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        assert writer_cls(pkg).write().to_dict() == writer_cls(pkg).write().to_dict()
