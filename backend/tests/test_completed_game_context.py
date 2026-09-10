"""Tests for the Completed Game Context foundation (COIN Phase 2).

The extraction service is pure and deterministic, so most tests build fixture
dictionaries and assert the derived fields directly. A small set of DB-backed
tests cover the model and the (team_id, game_pk) upsert identity.
"""

from datetime import date

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db
from models.completed_game_context import CompletedGameContext  # noqa: F401  (registers table)

from services.completed_game_context_service import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    TAG_BULLPEN_KEPT_TEAM_ALIVE,
    TAG_BULLPEN_OVEREXPOSED,
    TAG_INSUFFICIENT_CONTEXT,
    TAG_LOST_GAME_SHAPE,
    TAG_PROTECTED_GAME_SHAPE,
    TAG_STARTER_COVERED_BULLPEN,
    extract_completed_game_contexts,
    upsert_completed_game_context,
)
from services.game_shape import SHAPE_NORMAL_START


# ── Fixture builders ──────────────────────────────────────────────────────────

def _line(player_id, name, games_started, outs, pitches=0):
    return {
        'player_id': player_id,
        'name': name,
        'games_started': games_started,
        'innings_pitched_outs': outs,
        'pitches_thrown': pitches,
    }


def _play(inning, half, away_score, home_score, pitcher_id):
    return {
        'inning': inning,
        'half': half,
        'away_score': away_score,
        'home_score': home_score,
        'pitcher_id': pitcher_id,
    }


def _home_team(pitchers):
    return {'team_id': 1, 'team_name': 'Home Nine', 'pitchers': pitchers}


def _away_team(pitchers):
    return {'team_id': 2, 'team_name': 'Away Nine', 'pitchers': pitchers}


def _home_context(contexts):
    return next(c for c in contexts if c['home_away'] == 'home')


def _away_context(contexts):
    return next(c for c in contexts if c['home_away'] == 'away')


# A normal-start home team (starter goes 6 IP = 18 outs) plus one reliever.
HOME_STARTER = _line(11, 'Home Starter', 1, 18, pitches=92)
HOME_RELIEVER = _line(12, 'Home Reliever', 0, 9, pitches=20)
# Away side: short starter (12 outs) and heavy bullpen (18 relief outs).
AWAY_STARTER = _line(21, 'Away Starter', 1, 12, pitches=70)
AWAY_RELIEVER = _line(22, 'Away Reliever', 0, 18, pitches=55)


# ── Boxscore-only → fail closed at LOW ────────────────────────────────────────

def test_boxscore_only_yields_low_confidence_and_null_running_score():
    game = {
        'game_pk': 700,
        'game_date': '2026-06-25',
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        # no linescore, no plays
    }
    contexts = extract_completed_game_contexts(game)
    assert len(contexts) == 2
    home = _home_context(contexts)

    assert home['confidence'] == CONFIDENCE_LOW
    assert home['bullpen_story_tag'] == TAG_INSUFFICIENT_CONTEXT
    # No running score is invented.
    assert home['final_score_for'] is None
    assert home['final_score_against'] is None
    assert home['game_shape_created'] is None
    assert home['game_shape_protected'] is None
    assert home['turning_inning'] is None
    assert home['starter_exit_score_for'] is None
    assert home['bullpen_entry_score_for'] is None
    assert home['lead_protected'] is None
    assert home['lead_lost'] is None
    # Starter identity from the boxscore is still allowed.
    assert home['starter_player_id'] == 11
    assert home['starter_ip'] == pytest.approx(6.0)


# ── Linescore present → MEDIUM, game shape derivable ──────────────────────────

def test_linescore_derives_game_shape_and_final_at_medium_confidence():
    game = {
        'game_pk': 701,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {
            'innings': [
                {'num': 1, 'home': 1, 'away': 0},
                {'num': 2, 'home': 1, 'away': 0},
                {'num': 7, 'home': 0, 'away': 1},
            ],
            'home_runs': 3,
            'away_runs': 1,
        },
    }
    home = _home_context(extract_completed_game_contexts(game))

    assert home['confidence'] == CONFIDENCE_MEDIUM
    assert home['game_shape_created'] == SHAPE_NORMAL_START
    assert home['final_score_for'] == 3
    assert home['final_score_against'] == 1
    assert home['largest_lead'] == 2
    # Home pitches the top half, so it allowed the away run in the 7th.
    assert home['runs_allowed_innings_7_to_9'] == 1
    assert home['late_runs_allowed'] == 1
    # Bullpen-handoff score needs play-by-play; not asserted at MEDIUM.
    assert home['bullpen_entry_score_for'] is None
    assert home['lead_protected'] is None


# ── Play-by-play → HIGH, protected vs lost game shape ─────────────────────────

def _normal_start_home_game(seventh_top_away_score, final_away, final_home, plays):
    """Home team: normal start, reliever finishes. Caller supplies the play log."""
    return {
        'game_pk': 702,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {'home_runs': final_home, 'away_runs': final_away},
        'plays': plays,
    }


def test_protected_game_shape_when_team_leads_at_handoff_and_wins():
    # Home leads 3-1 when the bullpen enters in the 7th and holds for the win.
    plays = [
        _play(6, 'top', 1, 3, 11),    # starter's last batter, home up 3-1
        _play(7, 'top', 1, 3, 12),    # reliever enters, top 7th
        _play(8, 'top', 1, 3, 12),
        _play(9, 'top', 1, 3, 12),    # final 3-1 home
    ]
    game = _normal_start_home_game(1, 1, 3, plays)
    home = _home_context(extract_completed_game_contexts(game))

    assert home['confidence'] == CONFIDENCE_HIGH
    assert home['starter_exit_inning'] == 6
    assert home['starter_exit_score_for'] == 3
    assert home['bullpen_entry_inning'] == 7
    assert home['bullpen_entry_score_for'] == 3
    assert home['bullpen_entry_score_against'] == 1
    assert home['lead_when_bullpen_entered'] == 2
    assert home['lead_protected'] is True
    assert home['lead_lost'] is False
    assert home['game_shape_created'] == SHAPE_NORMAL_START
    assert home['game_shape_protected'] is True
    assert home['bullpen_story_tag'] == TAG_PROTECTED_GAME_SHAPE


def test_lost_game_shape_when_team_leads_at_handoff_and_loses_late():
    # Home leads 3-1 at handoff but the bullpen coughs up 3 runs in the 8th.
    plays = [
        _play(6, 'top', 1, 3, 11),    # starter's last batter, home up 3-1
        _play(7, 'top', 1, 3, 12),    # reliever enters
        _play(8, 'top', 4, 3, 12),    # bullpen allows 3, now down 4-3
        _play(9, 'top', 4, 3, 12),    # final 4-3 away
    ]
    game = _normal_start_home_game(4, 4, 3, plays)
    home = _home_context(extract_completed_game_contexts(game))

    assert home['confidence'] == CONFIDENCE_HIGH
    assert home['lead_when_bullpen_entered'] == 2
    assert home['lead_protected'] is False
    assert home['lead_lost'] is True
    assert home['game_shape_protected'] is False
    assert home['late_runs_allowed'] == 3
    assert home['runs_allowed_innings_7_to_9'] == 3
    assert home['turning_inning'] == 8
    assert home['bullpen_story_tag'] == TAG_LOST_GAME_SHAPE


def test_burke_style_tied_handoff_keeps_largest_deficit_separate_from_entry_state():
    # Away starter records 16 outs (5.1 IP), trails earlier, exits tied, and
    # the offense breaks the tie later. The largest deficit must not become the
    # starter/bullpen handoff state.
    burke = _line(1451, 'Sean Burke', 1, 16, pitches=89)
    sox_reliever = _line(1452, 'White Sox Reliever', 0, 11, pitches=31)
    home_starter = _line(1161, 'Home Starter', 1, 15, pitches=80)
    home_reliever = _line(1162, 'Home Reliever', 0, 12, pitches=42)
    plays = [
        _play(1, 'top', 0, 0, 1161),
        _play(3, 'bottom', 0, 1, 1451),  # Chicago trails by one.
        _play(5, 'top', 2, 2, 1161),     # Chicago ties before the handoff.
        _play(6, 'bottom', 2, 2, 1451),  # Burke's final batter, still tied.
        _play(6, 'bottom', 2, 2, 1452),  # Bullpen enters with a tied score.
        _play(8, 'top', 4, 2, 1162),     # Chicago breaks the tie later.
        _play(9, 'bottom', 4, 2, 1452),
    ]
    game = {
        'game_pk': 826001,
        'away': _away_team([burke, sox_reliever]) | {'team_id': 145, 'team_name': 'Chicago White Sox'},
        'home': _home_team([home_starter, home_reliever]) | {'team_id': 116, 'team_name': 'Home Club'},
        'linescore': {'home_runs': 2, 'away_runs': 4},
        'plays': plays,
    }

    away = _away_context(extract_completed_game_contexts(game))

    assert away['starter_name'] == 'Sean Burke'
    assert away['starter_ip'] == pytest.approx(16 / 3)
    assert away['starter_exit_inning'] == 6
    assert away['starter_exit_score_for'] == 2
    assert away['starter_exit_score_against'] == 2
    assert away['bullpen_entry_inning'] == 6
    assert away['bullpen_entry_score_for'] == 2
    assert away['bullpen_entry_score_against'] == 2
    assert away['lead_when_bullpen_entered'] is None
    assert away['deficit_when_bullpen_entered'] is None
    assert away['largest_deficit'] == 1
    assert away['turning_inning'] == 8
    assert away['late_runs_allowed'] == 0
    assert away['bullpen_story_tag'] == TAG_BULLPEN_KEPT_TEAM_ALIVE


# ── Exposure-based tags (no lead context required) ────────────────────────────

def test_starter_covered_bullpen_tag_for_deep_start_light_pen():
    # Deep starter (18 outs), light pen (9 outs), quiet linescore.
    game = {
        'game_pk': 703,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {
            'innings': [{'num': 1, 'home': 2, 'away': 0}],
            'home_runs': 2,
            'away_runs': 0,
        },
    }
    home = _home_context(extract_completed_game_contexts(game))
    assert home['bullpen_story_tag'] == TAG_STARTER_COVERED_BULLPEN


def test_bullpen_overexposed_tag_for_short_start_heavy_pen():
    # Away starter goes 12 outs, away pen absorbs 18 outs (6 IP).
    game = {
        'game_pk': 704,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {
            'innings': [{'num': 1, 'home': 0, 'away': 1}],
            'home_runs': 0,
            'away_runs': 1,
        },
    }
    contexts = extract_completed_game_contexts(game)
    away = next(c for c in contexts if c['home_away'] == 'away')
    assert away['bullpen_story_tag'] == TAG_BULLPEN_OVEREXPOSED


# ── Conservative handling of missing / ambiguous data ─────────────────────────

def test_missing_starter_data_does_not_crash():
    # No credited starter (both relief) → starter fields null, still derives.
    game = {
        'game_pk': 705,
        'home': _home_team([_line(31, 'Bulk A', 0, 9), _line(32, 'Bulk B', 0, 9)]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {'home_runs': 0, 'away_runs': 0,
                      'innings': [{'num': 1, 'home': 0, 'away': 0}]},
    }
    home = _home_context(extract_completed_game_contexts(game))
    assert home['starter_player_id'] is None
    assert home['starter_ip'] is None


def test_opener_bulk_ambiguity_resolves_to_single_credited_starter():
    # Opener credited with the start (6 outs) + bulk follower (18 outs).
    opener = _line(41, 'Opener', 1, 6, pitches=28)
    bulk = _line(42, 'Bulk Follower', 0, 18, pitches=80)
    game = {
        'game_pk': 706,
        'home': _home_team([opener, bulk]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {'home_runs': 2, 'away_runs': 1,
                      'innings': [{'num': 1, 'home': 2, 'away': 1}]},
    }
    home = _home_context(extract_completed_game_contexts(game))
    # The credited opener is the starter; we don't guess a different one.
    assert home['starter_player_id'] == 41
    assert home['confidence'] == CONFIDENCE_MEDIUM


def test_extra_innings_keep_7_to_9_window_separate_from_total_late_runs():
    # Home allows 1 run in the 8th and 1 in the 10th.
    plays = [
        _play(8, 'top', 1, 2, 12),     # away scores in the 8th → 2-1 home
        _play(10, 'top', 2, 2, 12),    # away scores in the 10th → tied 2-2
        _play(10, 'bottom', 2, 3, 12),  # home walks it off 3-2
    ]
    game = {
        'game_pk': 707,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {'home_runs': 3, 'away_runs': 2},
        'plays': plays,
    }
    home = _home_context(extract_completed_game_contexts(game))
    assert home['runs_allowed_innings_7_to_9'] == 1   # only the 8th counts
    assert home['late_runs_allowed'] == 2             # 8th + 10th


def test_returns_empty_when_game_pk_missing():
    assert extract_completed_game_contexts({'home': _home_team([HOME_STARTER])}) == []
    assert extract_completed_game_contexts('not a dict') == []


def test_service_never_emits_raw_play_by_play():
    game = {
        'game_pk': 708,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'plays': [_play(1, 'top', 0, 0, 11)],
    }
    for ctx in extract_completed_game_contexts(game):
        assert 'plays' not in ctx
        assert 'play_by_play' not in ctx
        assert 'linescore' not in ctx


# ── DB-backed: model + (team_id, game_pk) identity ────────────────────────────

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


def test_model_row_can_be_created(app):
    row = CompletedGameContext(
        team_id=1,
        game_pk=900,
        game_date=date(2026, 6, 25),
        confidence=CONFIDENCE_LOW,
        bullpen_story_tag=TAG_INSUFFICIENT_CONTEXT,
    )
    db.session.add(row)
    db.session.commit()

    fetched = CompletedGameContext.query.filter_by(team_id=1, game_pk=900).one()
    assert fetched.confidence == CONFIDENCE_LOW
    assert fetched.to_dict()['bullpen_story_tag'] == TAG_INSUFFICIENT_CONTEXT


def test_upsert_is_idempotent_per_team_and_game(app):
    game = {
        'game_pk': 901,
        'home': _home_team([HOME_STARTER, HOME_RELIEVER]),
        'away': _away_team([AWAY_STARTER, AWAY_RELIEVER]),
        'linescore': {'home_runs': 3, 'away_runs': 1,
                      'innings': [{'num': 1, 'home': 3, 'away': 1}]},
    }
    contexts = extract_completed_game_contexts(game)

    for ctx in contexts:
        upsert_completed_game_context(ctx)
    db.session.commit()
    assert CompletedGameContext.query.count() == 2

    # Re-running the same extraction updates rather than duplicates.
    for ctx in extract_completed_game_contexts(game):
        upsert_completed_game_context(ctx)
    db.session.commit()
    assert CompletedGameContext.query.count() == 2
    home_row = CompletedGameContext.query.filter_by(team_id=1, game_pk=901).one()
    assert home_row.final_score_for == 3
