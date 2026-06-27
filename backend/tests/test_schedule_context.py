"""Tests for Schedule Context V1 (services/schedule_context.py).

The service computes per-team schedule pressure from scheduled_games rows: who is
playing today, recent played games, games ahead, the next off day, off-day
adjacency, and consecutive-game streaks. Most tests inject in-memory rows for
pure determinism; a couple exercise the real database load path and the
per-date helper. No product surface is involved; nothing is predicted.
"""

from datetime import date, datetime
from itertools import count

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from services import schedule_context as sc
from services.schedule_context import (
    build_schedule_contexts_for_date,
    build_team_schedule_context,
)
from utils.db import db
from models.scheduled_game import ScheduledGame
# Import related models so the SQLAlchemy mapper registry resolves fully (Pitcher
# references GameLog/FatigueScore) even when constructing rows in memory.
import models.pitcher  # noqa: F401
import models.game_log  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401

REF = date(2026, 6, 26)
_pk = count(700000)


def _row(day, *, status='final', team_id=116, opponent=142, home_away='home',
         dt=None, dh='N', game_number=1):
    gd = date.fromisoformat(day) if isinstance(day, str) else day
    return ScheduledGame(
        team_id=team_id, game_pk=next(_pk), game_date=gd, game_datetime=dt,
        opponent_team_id=opponent, home_away=home_away, status_state=status,
        doubleheader=dh, game_number=game_number,
    )


def _ctx(rows, ref=REF, **kw):
    return build_team_schedule_context(116, ref, rows=rows, **kw)


# ── 1. No schedule rows ───────────────────────────────────────────────────────

def test_no_rows_returns_unavailable_with_limitation():
    ctx = _ctx([])
    assert ctx['context_available'] is False
    assert ctx['limitations'] == ['no_schedule_rows']
    assert ctx['is_playing_today'] is False
    assert ctx['games_today_count'] == 0
    assert ctx['next_off_day'] is None


# ── Full happy-path scenario (matches the spec example) ───────────────────────

def _full_scenario():
    rows = []
    # Five consecutive finals 6/21..6/25 entering the 26th.
    for d in ('2026-06-21', '2026-06-22', '2026-06-23', '2026-06-24', '2026-06-25'):
        rows.append(_row(d, status='final'))
    # Scheduled 6/26 (today, vs 142 home, timed) through 6/29; 6/30 is an off day.
    rows.append(_row('2026-06-26', status='scheduled', dt=datetime(2026, 6, 26, 23, 10, 0)))
    for d in ('2026-06-27', '2026-06-28', '2026-06-29'):
        rows.append(_row(d, status='scheduled'))
    return rows


def test_full_scenario_matches_expected_fields():
    ctx = _ctx(_full_scenario())
    assert ctx == {
        'team_id': 116,
        'reference_date': '2026-06-26',
        'context_available': True,
        'is_playing_today': True,
        'opponent_today': None,                 # no resolver injected
        'opponent_team_id_today': 142,
        'home_away_today': 'home',
        'game_time_today': '2026-06-26T23:10:00Z',
        'doubleheader_today': False,
        'games_today_count': 1,
        'games_played_last_3_days': 3,          # 6/23,24,25
        'games_played_last_5_days': 5,          # 6/21..25
        'games_in_next_3_days': 3,              # 6/26,27,28
        'next_off_day': '2026-06-30',
        'days_until_next_off_day': 4,
        'games_until_next_off_day': 4,          # 6/26,27,28,29
        'is_first_game_after_off_day': False,
        'is_last_game_before_off_day': False,
        'consecutive_games_played_entering_today': 5,
        'consecutive_games_scheduled_from_today': 4,
        'limitations': [],
    }


def test_is_deterministic():
    rows = _full_scenario()
    assert _ctx(rows) == _ctx(rows)


# ── 2. Single scheduled game today ────────────────────────────────────────────

def test_single_game_today_sets_matchup_fields():
    rows = [_row('2026-06-26', status='scheduled', opponent=142, home_away='away',
                 dt=datetime(2026, 6, 26, 20, 5, 0)),
            _row('2026-06-28', status='scheduled')]  # so an off day exists at 6/27
    ctx = _ctx(rows)
    assert ctx['is_playing_today'] is True
    assert ctx['games_today_count'] == 1
    assert ctx['opponent_team_id_today'] == 142
    assert ctx['home_away_today'] == 'away'
    assert ctx['game_time_today'] == '2026-06-26T20:05:00Z'
    assert ctx['doubleheader_today'] is False


def test_opponent_name_uses_injected_resolver():
    rows = [_row('2026-06-26', status='scheduled', opponent=142)]
    ctx = _ctx(rows, team_name_resolver=lambda tid: 'Minnesota Twins' if tid == 142 else None)
    assert ctx['opponent_today'] == 'Minnesota Twins'
    assert ctx['opponent_team_id_today'] == 142


# ── 3. Off day today ──────────────────────────────────────────────────────────

def test_off_day_today():
    rows = [_row('2026-06-24', status='final'), _row('2026-06-25', status='final'),
            _row('2026-06-28', status='scheduled')]   # nothing on 6/26
    ctx = _ctx(rows)
    assert ctx['is_playing_today'] is False
    assert ctx['next_off_day'] == '2026-06-26'
    assert ctx['days_until_next_off_day'] == 0
    assert ctx['games_until_next_off_day'] == 0
    assert ctx['is_first_game_after_off_day'] is False
    assert ctx['is_last_game_before_off_day'] is False


# ── 4. Doubleheader today ─────────────────────────────────────────────────────

def test_doubleheader_today():
    rows = [
        _row('2026-06-26', status='scheduled', dt=datetime(2026, 6, 26, 17, 10), dh='Y', game_number=1),
        _row('2026-06-26', status='scheduled', dt=datetime(2026, 6, 26, 20, 40), dh='Y', game_number=2),
        _row('2026-06-28', status='scheduled'),
    ]
    ctx = _ctx(rows)
    assert ctx['games_today_count'] == 2
    assert ctx['doubleheader_today'] is True
    assert 'doubleheader_today' in ctx['limitations']
    # Earliest game drives the matchup fields.
    assert ctx['game_time_today'] == '2026-06-26T17:10:00Z'


# ── 5. Postponed game today does not count as playing ─────────────────────────

def test_postponed_today_is_not_playing():
    rows = [_row('2026-06-26', status='postponed'),
            _row('2026-06-28', status='scheduled')]
    ctx = _ctx(rows)
    assert ctx['is_playing_today'] is False
    assert ctx['games_today_count'] == 0
    assert ctx['context_available'] is True   # rows exist near the date


# ── 6. Suspended counts as existence, not as played ───────────────────────────

def test_suspended_today_counts_as_game_not_as_played():
    rows = [
        _row('2026-06-25', status='suspended'),   # exists yesterday, but not final
        _row('2026-06-26', status='suspended'),   # exists today
        _row('2026-06-28', status='scheduled'),
    ]
    ctx = _ctx(rows)
    assert ctx['is_playing_today'] is True            # existence
    assert ctx['games_today_count'] == 1
    assert ctx['games_played_last_3_days'] == 0       # suspended != final
    assert ctx['consecutive_games_played_entering_today'] == 0


# ── 7 & 8. Recent played counts (final only; doubleheaders count two) ─────────

def test_games_played_windows_exclude_today_and_count_finals():
    rows = [
        _row('2026-06-24', status='final'),
        _row('2026-06-25', status='final'),
        _row('2026-06-25', status='final', game_number=2),   # doubleheader yesterday
        _row('2026-06-26', status='final'),                  # today - must be excluded
        _row('2026-06-28', status='scheduled'),
    ]
    ctx = _ctx(rows)
    assert ctx['games_played_last_3_days'] == 3   # 6/24 + 6/25 x2 ; excludes 6/26
    assert ctx['games_played_last_5_days'] == 3


def test_postponed_in_window_does_not_count_as_played():
    rows = [_row('2026-06-24', status='final'), _row('2026-06-25', status='postponed'),
            _row('2026-06-28', status='scheduled')]
    ctx = _ctx(rows)
    assert ctx['games_played_last_3_days'] == 1


# ── 9. Games in next 3 days (today..+2, skip postponed, DH counts two) ────────

def test_games_in_next_3_days_includes_today_and_skips_postponed():
    rows = [
        _row('2026-06-26', status='scheduled'),
        _row('2026-06-27', status='postponed'),                 # skipped
        _row('2026-06-28', status='scheduled'),
        _row('2026-06-28', status='scheduled', game_number=2),  # doubleheader -> 2
        _row('2026-06-29', status='scheduled'),                 # outside +2 window
    ]
    ctx = _ctx(rows)
    assert ctx['games_in_next_3_days'] == 3   # 6/26 (1) + 6/27 (0) + 6/28 (2)


# ── 10. Next off day / days / games-until ─────────────────────────────────────

def test_next_off_day_computation():
    rows = [_row('2026-06-26', status='scheduled'), _row('2026-06-27', status='scheduled'),
            _row('2026-06-28', status='scheduled')]  # 6/29 is the first off day
    ctx = _ctx(rows)
    assert ctx['next_off_day'] == '2026-06-29'
    assert ctx['days_until_next_off_day'] == 3
    assert ctx['games_until_next_off_day'] == 3


# ── 11 & 12. Off-day adjacency ────────────────────────────────────────────────

def test_first_game_after_off_day():
    # No game on 6/25; game on 6/26.
    rows = [_row('2026-06-24', status='final'), _row('2026-06-26', status='scheduled'),
            _row('2026-06-28', status='scheduled')]
    ctx = _ctx(rows)
    assert ctx['is_first_game_after_off_day'] is True


def test_last_game_before_off_day():
    # Game on 6/26; nothing on 6/27.
    rows = [_row('2026-06-25', status='final'), _row('2026-06-26', status='scheduled'),
            _row('2026-06-29', status='scheduled')]
    ctx = _ctx(rows)
    assert ctx['is_last_game_before_off_day'] is True


# ── 13 & 14. Consecutive streaks stop at off days ─────────────────────────────

def test_consecutive_played_stops_at_prior_off_day():
    rows = [
        _row('2026-06-22', status='final'),   # before the gap - must not count
        # 6/23 is an off day (no row)
        _row('2026-06-24', status='final'),
        _row('2026-06-25', status='final'),
        _row('2026-06-26', status='scheduled'),
        _row('2026-06-28', status='scheduled'),
    ]
    ctx = _ctx(rows)
    assert ctx['consecutive_games_played_entering_today'] == 2   # 6/25, 6/24; stops at 6/23


def test_consecutive_scheduled_stops_at_next_off_day():
    rows = [
        _row('2026-06-26', status='scheduled'),
        _row('2026-06-27', status='scheduled'),
        # 6/28 off
        _row('2026-06-29', status='scheduled'),   # must not count
    ]
    ctx = _ctx(rows)
    assert ctx['consecutive_games_scheduled_from_today'] == 2


# ── 15. Missing game time ─────────────────────────────────────────────────────

def test_missing_game_time_sets_null_and_limitation():
    rows = [_row('2026-06-26', status='scheduled', dt=None),
            _row('2026-06-28', status='scheduled')]
    ctx = _ctx(rows)
    assert ctx['game_time_today'] is None
    assert 'missing_game_time' in ctx['limitations']


# ── 16. Next off day not found within window ──────────────────────────────────

def test_next_off_day_not_found_within_window():
    # A non-postponed game every day from ref through ref+LOOKAHEAD (no off day).
    from datetime import timedelta
    rows = [_row(REF + timedelta(days=i), status='scheduled')
            for i in range(sc.LOOKAHEAD_DAYS + 1)]
    ctx = _ctx(rows)
    assert ctx['next_off_day'] is None
    assert ctx['days_until_next_off_day'] is None
    assert ctx['games_until_next_off_day'] is None
    assert 'next_off_day_not_found_within_window' in ctx['limitations']


# ── 17. build_schedule_contexts_for_date (one per team, ordered) ──────────────

def test_build_contexts_for_date_returns_one_per_team_ordered():
    rows = [
        _row('2026-06-26', status='scheduled', team_id=142, opponent=116),
        _row('2026-06-26', status='scheduled', team_id=116, opponent=142),
        _row('2026-06-28', status='scheduled', team_id=116, opponent=142),
        _row('2026-06-28', status='scheduled', team_id=142, opponent=116),
    ]
    contexts = build_schedule_contexts_for_date(REF, rows=rows)
    assert [c['team_id'] for c in contexts] == [116, 142]   # sorted by team_id
    assert all(c['is_playing_today'] for c in contexts)


# ── Database load path ────────────────────────────────────────────────────────

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


def _persist(rows):
    for r in rows:
        db.session.add(r)
    db.session.commit()


def test_loads_rows_from_database_when_not_injected(app):
    with app.app_context():
        _persist([
            _row('2026-06-25', status='final'),
            _row('2026-06-26', status='scheduled', dt=datetime(2026, 6, 26, 23, 5)),
            _row('2026-06-28', status='scheduled'),
        ])
        ctx = build_team_schedule_context(116, REF)
        assert ctx['context_available'] is True
        assert ctx['is_playing_today'] is True
        assert ctx['games_played_last_3_days'] == 1
        assert ctx['game_time_today'] == '2026-06-26T23:05:00Z'


def test_database_window_excludes_far_rows(app):
    with app.app_context():
        # A final game 60 days ago is outside the lookback window.
        _persist([_row('2026-04-27', status='final'),
                  _row('2026-06-26', status='scheduled')])
        ctx = build_team_schedule_context(116, REF)
        assert ctx['games_played_last_5_days'] == 0
        assert ctx['is_playing_today'] is True
