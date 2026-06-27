"""Tests for the Tonight intelligence service (public envelope wrapper).

The wrapper resolves the reference date, derives candidates, strips internal
fields (strength), and shapes the public envelope with honest empty reasons.
These inject schedule/bullpen context for determinism; the endpoint test drives
the HTTP layer and the real schedule path.
"""

import pytest

from services import tonight_intelligence_service as svc
from services.tonight_intelligence_service import serve_tonight

REF = '2026-06-26'

_BANNED = (
    'will win', 'will lose', 'guaranteed', 'probability', 'odds', 'recommend',
    'ranked', 'ranking', 'predict', 'betting', 'best option', ' lock',
)


def _sc(team_id=116, *, playing=True, days_until=3, games_until=3, games_next3=3,
        limitations=None):
    return {
        'team_id': team_id, 'reference_date': REF, 'context_available': True,
        'is_playing_today': playing, 'opponent_today': 'Minnesota Twins',
        'opponent_team_id_today': 142, 'home_away_today': 'home',
        'game_time_today': '2026-06-26T23:10:00Z', 'doubleheader_today': False,
        'games_today_count': 1 if playing else 0,
        'games_played_last_3_days': 3, 'games_played_last_5_days': 5,
        'games_in_next_3_days': games_next3, 'next_off_day': '2026-06-30',
        'days_until_next_off_day': days_until, 'games_until_next_off_day': games_until,
        'is_first_game_after_off_day': False, 'is_last_game_before_off_day': False,
        'consecutive_games_played_entering_today': 3,
        'consecutive_games_scheduled_from_today': 4,
        'limitations': list(limitations or []),
    }


def _pen(*, clean=1, band='thin', paths=2, conc='normal', share=40.0,
         name='Detroit Tigers'):
    return {
        'context_available': True, 'clean_options_count': clean,
        'optionality_band': band, 'practical_close_game_paths_count': paths,
        'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 1,
        'restricted_arms_count': 3, 'concentration_band': conc,
        'top_three_workload_share_10d': share, 'team_name': name,
    }


def _builder(pen_by_team):
    return lambda team_id, reference_date: pen_by_team.get(team_id)


# ── Status ok with cards ──────────────────────────────────────────────────────

def test_ok_with_cards():
    out = serve_tonight(REF, schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    assert out['status'] == 'ok'
    assert out['reference_date'] == REF
    assert out['card_count'] == len(out['cards']) == 1
    assert out['empty_reason'] is None
    card = out['cards'][0]
    assert card['team_id'] == 116
    assert card['team_name'] == 'Detroit Tigers'


# ── 7 & 8. Public card field hygiene ──────────────────────────────────────────

def test_public_card_omits_strength_and_keeps_public_fields():
    out = serve_tonight(REF, schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    card = out['cards'][0]
    assert 'strength' not in card
    assert 'reference_date' not in card     # carried by the envelope, not the card
    for key in ('team_id', 'team_name', 'headline', 'summary', 'signal_type',
                'signal_family', 'evidence', 'schedule_context', 'bullpen_context',
                'limitations'):
        assert key in card


def test_card_count_matches_cards_length():
    out = serve_tonight(
        REF, limit=3,
        schedule_contexts=[_sc(116), _sc(118, games_next3=3), _sc(120, days_until=1, games_until=1)],
        bullpen_context_builder=_builder({
            116: _pen(clean=1, band='thin'),
            118: _pen(clean=3, band='flexible', conc='narrow', share=55.0),
            120: _pen(clean=0, band='thin', paths=0),
        }))
    assert out['card_count'] == len(out['cards'])


# ── Empty states ──────────────────────────────────────────────────────────────

def test_empty_no_schedule_context():
    out = serve_tonight(REF, schedule_contexts=[])
    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_schedule_context'
    assert out['cards'] == [] and out['card_count'] == 0


def test_empty_no_teams_playing():
    out = serve_tonight(REF, schedule_contexts=[_sc(116, playing=False)])
    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_teams_playing_today'


def test_empty_no_signals():
    # Team plays but its bullpen is deep with an off day right after -> no signal.
    out = serve_tonight(
        REF, schedule_contexts=[_sc(116, days_until=5, games_until=5, games_next3=1)],
        bullpen_context_builder=_builder({116: _pen(clean=5, band='deep', paths=5,
                                                    conc='balanced', share=20.0)}))
    assert out['status'] == 'empty'
    assert out['empty_reason'] == 'no_tonight_signals'


# ── Reference date resolution ─────────────────────────────────────────────────

def test_defaults_to_product_current_date(monkeypatch):
    from datetime import date
    monkeypatch.setattr(svc, 'product_current_date', lambda: date(2026, 6, 26))
    out = serve_tonight(None, schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    assert out['reference_date'] == '2026-06-26'


def test_explicit_reference_date_is_honored():
    out = serve_tonight('2026-07-04', schedule_contexts=[_sc(116)],
                        bullpen_context_builder=_builder({116: _pen()}))
    assert out['reference_date'] == '2026-07-04'


# ── No ranking / recommendation language ──────────────────────────────────────

def test_response_has_no_forbidden_language():
    out = serve_tonight(
        REF, limit=3,
        schedule_contexts=[_sc(116), _sc(118, games_next3=3), _sc(120, days_until=1, games_until=1)],
        bullpen_context_builder=_builder({
            116: _pen(clean=1, band='thin'),
            118: _pen(clean=3, band='flexible', conc='narrow', share=55.0),
            120: _pen(clean=0, band='thin', paths=0),
        }))
    blob = str(out).lower()
    for term in _BANNED:
        assert term not in blob, term


# ── Determinism ───────────────────────────────────────────────────────────────

def test_deterministic_for_same_inputs():
    args = dict(schedule_contexts=[_sc(116), _sc(118, games_next3=3)],
                bullpen_context_builder=_builder({
                    116: _pen(clean=1, band='thin'),
                    118: _pen(clean=3, band='flexible', conc='narrow', share=55.0)}))
    assert serve_tonight(REF, **args) == serve_tonight(REF, **args)


# ── Envelope aggregates card limitations ──────────────────────────────────────

def test_envelope_aggregates_card_limitations():
    out = serve_tonight(
        REF, schedule_contexts=[_sc(116, limitations=['doubleheader_today'])],
        bullpen_context_builder=_builder({116: _pen()}))
    assert 'doubleheader_today' in out['limitations']
