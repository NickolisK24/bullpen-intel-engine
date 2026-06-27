"""Tests for Tonight candidate selection V1.

The service joins Phase 2 schedule context with the existing bullpen context to
produce diverse pregame candidates — at most one per signal family, distinct
teams, strongest first. Most tests inject schedule/bullpen context for pure
determinism; one drives the real schedule path from seeded scheduled_games with a
stubbed bullpen builder. Copy must stay descriptive and evidence-backed — no
predictions, betting, or "best option" framing — and nothing here may touch the
COIN completed-game story services.
"""

import inspect as _inspect
from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from services import tonight_candidate_selection as tcs
from services.tonight_candidate_selection import (
    build_team_tonight_candidate,
    build_tonight_candidates,
)
from utils.db import db
from models.scheduled_game import ScheduledGame
import models.pitcher  # noqa: F401
import models.game_log  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401

REF = '2026-06-26'

_BANNED = (
    'will win', 'will lose', 'guaranteed', 'probability', 'odds', 'recommend',
    'ranked', 'predict', 'blow', 'likely', 'betting', 'best option', ' lock',
)


def _sc(team_id=116, *, playing=True, days_until=3, games_until=3, games_next3=3,
        last3=3, last5=5, is_last_before_off=False, doubleheader=False,
        opponent='Minnesota Twins', limitations=None):
    return {
        'team_id': team_id, 'reference_date': REF, 'context_available': True,
        'is_playing_today': playing, 'opponent_today': opponent,
        'opponent_team_id_today': 142, 'home_away_today': 'home',
        'game_time_today': '2026-06-26T23:10:00Z',
        'doubleheader_today': doubleheader,
        'games_today_count': (2 if doubleheader else (1 if playing else 0)),
        'games_played_last_3_days': last3, 'games_played_last_5_days': last5,
        'games_in_next_3_days': games_next3,
        'next_off_day': '2026-06-30', 'days_until_next_off_day': days_until,
        'games_until_next_off_day': games_until,
        'is_first_game_after_off_day': False,
        'is_last_game_before_off_day': is_last_before_off,
        'consecutive_games_played_entering_today': last3,
        'consecutive_games_scheduled_from_today': 4,
        'limitations': list(limitations or []),
    }


def _pen(*, clean=1, band='thin', paths=2, conc='normal', share=40.0,
         available=True, name='Detroit Tigers'):
    return {
        'context_available': available,
        'clean_options_count': clean, 'optionality_band': band,
        'practical_close_game_paths_count': paths,
        'available_arms_count': 3, 'monitor_arms_count': 2,
        'limited_arms_count': 1, 'restricted_arms_count': 3,
        'concentration_band': conc, 'top_three_workload_share_10d': share,
        'team_name': name,
    }


def _builder(pen_by_team):
    def build(team_id, reference_date):
        return pen_by_team.get(team_id)
    return build


def _all_text(candidate):
    return ' '.join([candidate['headline'], candidate['summary'],
                     *candidate['evidence']]).lower()


# ── 1 & 16. Empty / not-playing ───────────────────────────────────────────────

def test_returns_empty_when_no_schedule_contexts():
    assert build_tonight_candidates(REF, schedule_contexts=[],
                                    bullpen_context_builder=_builder({})) == []


def test_skips_teams_not_playing_today():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(116, playing=False)],
        bullpen_context_builder=_builder({116: _pen()}))
    assert out == []


# ── 3. thin_before_next_off_day ───────────────────────────────────────────────

def test_thin_before_next_off_day_candidate():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(116, days_until=3, games_until=3)],
        bullpen_context_builder=_builder({116: _pen(clean=1, band='thin', paths=3)}))
    assert len(out) == 1
    c = out[0]
    assert c['signal_type'] == 'thin_before_next_off_day'
    assert c['signal_family'] == 'schedule_pressure'
    assert c['team_name'] == 'Detroit Tigers'
    assert 'rest day' in c['headline'].lower()


# ── 4. no_clean_margin_tonight ────────────────────────────────────────────────

def test_no_clean_margin_candidate():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(120, days_until=1, games_until=1)],
        bullpen_context_builder=_builder({120: _pen(clean=0, band='thin', paths=1,
                                                    conc='normal', share=30.0,
                                                    name='Washington Nationals')}))
    signals = {c['signal_type'] for c in out}
    assert 'no_clean_margin_tonight' in signals
    c = next(c for c in out if c['signal_type'] == 'no_clean_margin_tonight')
    assert 'almost no clean margin' in c['headline'].lower()


# ── 5. heavy_recent_workload_with_games_ahead ─────────────────────────────────

def test_heavy_workload_candidate():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(158, games_next3=3, days_until=4, games_until=4)],
        bullpen_context_builder=_builder({158: _pen(clean=3, band='flexible', paths=4,
                                                    conc='narrow', share=52.0,
                                                    name='Milwaukee Brewers')}))
    c = next(c for c in out if c['signal_type'] == 'heavy_recent_workload_with_games_ahead')
    assert c['signal_family'] == 'workload_pressure'
    assert 'carrying workload' in c['headline'].lower()


# ── 6. off_day_relief_pressure_reduced ────────────────────────────────────────

def test_off_day_relief_candidate():
    c = build_team_tonight_candidate(
        144, REF,
        schedule_context=_sc(144, is_last_before_off=True, days_until=1, games_until=1),
        bullpen_context=_pen(clean=2, band='narrow', paths=2, conc='normal',
                             share=35.0, name='Atlanta Braves'))
    # The strongest signal might be schedule/late-game; assert the off-day signal
    # is at least produced for this team.
    cands = tcs._team_signal_candidates(144, _sc(144, is_last_before_off=True,
                                                 days_until=1, games_until=1),
                                        _pen(clean=2, band='narrow', conc='normal',
                                             name='Atlanta Braves'))
    types = {x['signal_type'] for x in cands}
    assert 'off_day_relief_pressure_reduced' in types
    assert 'softer landing' in next(
        x for x in cands if x['signal_type'] == 'off_day_relief_pressure_reduced'
    )['headline'].lower()


# ── 7 & 8. One per family, distinct teams ─────────────────────────────────────

def test_at_most_one_candidate_per_family():
    # Two thin teams both match schedule_pressure; only one survives that family.
    out = build_tonight_candidates(
        REF, limit=5,
        schedule_contexts=[_sc(116, days_until=3, games_until=3),
                           _sc(118, days_until=4, games_until=4)],
        bullpen_context_builder=_builder({
            116: _pen(clean=2, band='thin', paths=3, conc='normal', share=30.0),
            118: _pen(clean=2, band='narrow', paths=3, conc='normal', share=30.0),
        }))
    families = [c['signal_family'] for c in out]
    assert families.count('schedule_pressure') == 1


def test_distinct_teams_only():
    # One team matches multiple families; it appears at most once.
    out = build_tonight_candidates(
        REF, limit=5,
        schedule_contexts=[_sc(116, days_until=3, games_until=3, games_next3=3)],
        bullpen_context_builder=_builder({
            116: _pen(clean=0, band='thin', paths=0, conc='narrow', share=55.0)}))
    team_ids = [c['team_id'] for c in out]
    assert team_ids == [116]


# ── 9. Up to limit ────────────────────────────────────────────────────────────

def test_returns_up_to_limit():
    out = build_tonight_candidates(
        REF, limit=2,
        schedule_contexts=[_sc(116, days_until=3, games_until=3),
                           _sc(118, games_next3=3, days_until=4, games_until=4),
                           _sc(120, days_until=1, games_until=1)],
        bullpen_context_builder=_builder({
            116: _pen(clean=1, band='thin', paths=3, conc='normal'),
            118: _pen(clean=3, band='flexible', paths=4, conc='narrow', share=55.0),
            120: _pen(clean=0, band='thin', paths=0, conc='normal'),
        }))
    assert len(out) == 2


# ── 10 & 20. Deterministic strength ordering ──────────────────────────────────

def test_strength_ordering_is_deterministic_and_descending():
    schedule = [_sc(116, days_until=3, games_until=3),
                _sc(118, games_next3=3, days_until=4, games_until=4),
                _sc(120, days_until=2, games_until=2)]
    pens = {
        116: _pen(clean=1, band='thin', paths=3, conc='normal'),
        118: _pen(clean=3, band='flexible', paths=4, conc='narrow', share=58.0),
        120: _pen(clean=0, band='thin', paths=0, conc='normal'),
    }
    first = build_tonight_candidates(REF, limit=3, schedule_contexts=schedule,
                                     bullpen_context_builder=_builder(pens))
    second = build_tonight_candidates(REF, limit=3, schedule_contexts=schedule,
                                      bullpen_context_builder=_builder(pens))
    assert first == second
    strengths = [c['strength'] for c in first]
    assert strengths == sorted(strengths, reverse=True)


# ── 11. Evidence maps to source facts ─────────────────────────────────────────

def test_evidence_maps_to_source_facts():
    c = build_team_tonight_candidate(
        116, REF,
        schedule_context=_sc(116, days_until=3, games_until=3),
        bullpen_context=_pen(clean=1, band='thin', paths=3))
    text = ' '.join(c['evidence'])
    assert '1 clean bullpen option' in text
    assert 'Next off day in 3 days' in text
    assert '3 games before the next off day' in text
    # Every evidence bullet is backed by a schedule or bullpen fact (non-empty).
    assert all(isinstance(b, str) and b for b in c['evidence'])


# ── 12. No prediction / betting / recommendation language ─────────────────────

def test_copy_contains_no_forbidden_language():
    schedule = [_sc(116, days_until=3, games_until=3),
                _sc(118, games_next3=3, days_until=4, games_until=4),
                _sc(120, days_until=1, games_until=1, is_last_before_off=True)]
    pens = {
        116: _pen(clean=1, band='thin', paths=3, conc='normal'),
        118: _pen(clean=3, band='flexible', paths=4, conc='narrow', share=55.0),
        120: _pen(clean=2, band='narrow', paths=2, conc='normal'),
    }
    out = build_tonight_candidates(REF, limit=4, schedule_contexts=schedule,
                                   bullpen_context_builder=_builder(pens))
    assert out
    for c in out:
        text = _all_text(c)
        for term in _BANNED:
            assert term not in text, (c['signal_type'], term)


# ── 13. Missing bullpen fields do not crash ───────────────────────────────────

def test_missing_bullpen_fields_do_not_crash():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(116)],
        bullpen_context_builder=_builder({116: {'context_available': False}}))
    assert out == []   # nothing to assert a signal from, but no exception


def test_bullpen_builder_returning_none_is_safe():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(116)],
        bullpen_context_builder=lambda *a, **k: None)
    assert out == []


def test_bullpen_builder_raising_is_isolated():
    def boom(team_id, reference_date):
        raise RuntimeError('context down')
    out = build_tonight_candidates(REF, schedule_contexts=[_sc(116)],
                                   bullpen_context_builder=boom)
    assert out == []   # the team is skipped, not fatal


# ── 14. Schedule limitations propagate ────────────────────────────────────────

def test_schedule_limitations_propagate_into_candidate():
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(116, days_until=3, games_until=3,
                                    limitations=['doubleheader_today'])],
        bullpen_context_builder=_builder({116: _pen(clean=1, band='thin')}))
    assert out
    assert 'doubleheader_today' in out[0]['limitations']


# ── 15. Doubleheader contributes to schedule pressure ─────────────────────────

def test_doubleheader_contributes_to_schedule_pressure():
    # A doubleheader pushes games_until_next_off_day to 2 even with an off day soon.
    out = build_tonight_candidates(
        REF, schedule_contexts=[_sc(116, doubleheader=True, days_until=2, games_until=2)],
        bullpen_context_builder=_builder({116: _pen(clean=1, band='thin', paths=3)}))
    assert out
    c = out[0]
    assert c['signal_family'] == 'schedule_pressure'
    assert c['schedule_context']['doubleheader_today'] is True


# ── 17. build_team_tonight_candidate with injected contexts ───────────────────

def test_build_team_candidate_with_injected_contexts():
    c = build_team_tonight_candidate(
        116, REF,
        schedule_context=_sc(116, days_until=3, games_until=3),
        bullpen_context=_pen(clean=1, band='thin', paths=3))
    assert c is not None
    assert c['team_id'] == 116
    assert c['signal_family'] in {'schedule_pressure', 'late_game_path'}
    assert 'strength' in c and isinstance(c['strength'], int)


def test_build_team_candidate_returns_none_when_not_playing():
    assert build_team_tonight_candidate(
        116, REF, schedule_context=_sc(116, playing=False),
        bullpen_context=_pen()) is None


# ── 18. Real schedule path from seeded rows + stubbed bullpen builder ─────────

@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def test_runs_against_seeded_schedule_rows(app):
    with app.app_context():
        # Team 116 plays today through a stretch with no near off day.
        for i, d in enumerate(('2026-06-24', '2026-06-25')):
            db.session.add(ScheduledGame(team_id=116, game_pk=1000 + i,
                                         game_date=date.fromisoformat(d),
                                         status_state='final', opponent_team_id=142))
        for i, d in enumerate(('2026-06-26', '2026-06-27', '2026-06-28', '2026-06-29')):
            db.session.add(ScheduledGame(
                team_id=116, game_pk=2000 + i, game_date=date.fromisoformat(d),
                game_datetime=datetime(2026, 6, 26, 23, 10) if d == '2026-06-26' else None,
                status_state='scheduled', opponent_team_id=142, home_away='home'))
        db.session.commit()

        out = build_tonight_candidates(
            date(2026, 6, 26), limit=3,
            bullpen_context_builder=_builder({116: _pen(clean=1, band='thin', paths=2)}))
        assert len(out) == 1
        assert out[0]['team_id'] == 116
        assert out[0]['signal_family'] == 'schedule_pressure'
        assert out[0]['schedule_context']['is_playing_today'] is True


# ── 19. Does not touch COIN completed-game story services ──────────────────────

def test_module_does_not_import_coin_story_services():
    source = _inspect.getsource(tcs)
    for forbidden in ('completed_game_context', 'narrative_context', 'narrative_feed',
                      'story_orchestrator', 'story_writers', 'evidence_composition'):
        assert forbidden not in source, forbidden
