"""Tests for Game Shape classification infrastructure (Phase C3F).

The classifier is deterministic and uses only stored game-log data. These cover
each detectable shape, the conservative UNKNOWN fallbacks, and the additive
rotation_context integration (metadata only, no calculation change).
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.game_shape import (
    DETECTABLE_GAME_SHAPES,
    DETECTION_GAPS,
    GAME_SHAPES,
    SHAPE_BULLPEN_GAME,
    SHAPE_INJURY_EARLY_EXIT,
    SHAPE_NORMAL_START,
    SHAPE_OPENER_BULK_GAME,
    SHAPE_SHORT_START,
    SHAPE_SUSPENDED_RESUMED_GAME,
    SHAPE_UNKNOWN,
    classify_game_shape,
    game_shape_of,
)
from services.rotation_context import _analyze_game, build_rotation_context

REF = date(2026, 6, 20)


def _log(games_started, outs):
    return {'games_started': games_started, 'innings_pitched_outs': outs}


def _gl(game_pk, days_ago, games_started, outs):
    return SimpleNamespace(
        mlb_game_pk=game_pk,
        game_date=REF - timedelta(days=days_ago),
        game_type='R',
        games_started=games_started,
        innings_pitched_outs=outs,
    )


# ── Vocabulary ───────────────────────────────────────────────────────────────

def test_vocabulary_and_documented_detection_gaps():
    assert {
        SHAPE_NORMAL_START, SHAPE_SHORT_START, SHAPE_OPENER_BULK_GAME,
        SHAPE_BULLPEN_GAME, SHAPE_SUSPENDED_RESUMED_GAME, SHAPE_INJURY_EARLY_EXIT,
        SHAPE_UNKNOWN,
    } == set(GAME_SHAPES)
    assert DETECTABLE_GAME_SHAPES <= GAME_SHAPES
    # Categories that cannot be detected today are documented and not "detectable".
    assert SHAPE_SUSPENDED_RESUMED_GAME in DETECTION_GAPS
    assert SHAPE_INJURY_EARLY_EXIT in DETECTION_GAPS
    assert SHAPE_SUSPENDED_RESUMED_GAME not in DETECTABLE_GAME_SHAPES
    assert SHAPE_INJURY_EARLY_EXIT not in DETECTABLE_GAME_SHAPES


# ── Detectable shapes ────────────────────────────────────────────────────────

def test_normal_start():
    result = classify_game_shape([_log(1, 18), _log(0, 3), _log(0, 6)])
    assert result['shape'] == SHAPE_NORMAL_START
    assert result['starter_outs'] == 18


def test_short_start():
    result = classify_game_shape([_log(1, 12), _log(0, 9), _log(0, 6)])
    assert result['shape'] == SHAPE_SHORT_START
    assert any('injury/early exit' in limit for limit in result['limitations'])


def test_opener_bulk_game():
    result = classify_game_shape([_log(1, 3), _log(0, 15), _log(0, 3)])
    assert result['shape'] == SHAPE_OPENER_BULK_GAME
    assert result['starter_outs'] == 3


def test_short_opener_without_bulk_follower_is_short_start():
    # A one-inning starter with no long follower cannot be confirmed as an
    # opener/bulk game; it reads as a short start.
    result = classify_game_shape([_log(1, 3), _log(0, 3), _log(0, 6)])
    assert result['shape'] == SHAPE_SHORT_START


def test_bullpen_game():
    result = classify_game_shape([_log(0, 9), _log(0, 9), _log(0, 6)])
    assert result['shape'] == SHAPE_BULLPEN_GAME


# ── Conservative UNKNOWN fallbacks ───────────────────────────────────────────

def test_unknown_start_rows_are_unknown():
    result = classify_game_shape([_log(None, 12), _log(0, 9)])
    assert result['shape'] == SHAPE_UNKNOWN
    assert result['reason'] == 'unknown_start_rows'


def test_multiple_starters_is_unknown():
    result = classify_game_shape([_log(1, 12), _log(1, 9)])
    assert result['shape'] == SHAPE_UNKNOWN
    assert result['reason'] == 'multiple_starters'


def test_missing_starter_innings_is_unknown():
    result = classify_game_shape([_log(1, None), _log(0, 9)])
    assert result['shape'] == SHAPE_UNKNOWN
    assert result['reason'] == 'missing_starter_innings'


def test_malformed_input_is_unknown():
    assert classify_game_shape(None)['shape'] == SHAPE_UNKNOWN
    assert classify_game_shape([])['shape'] == SHAPE_UNKNOWN
    malformed = classify_game_shape([{'games_started': 'x', 'innings_pitched_outs': 'nope'}])
    assert malformed['shape'] == SHAPE_UNKNOWN


def test_missing_relief_innings_still_classifies_starter():
    # A relief row without outs does not block classifying the starter's length.
    result = classify_game_shape([_log(1, 18), _log(0, None)])
    assert result['shape'] == SHAPE_NORMAL_START
    assert any('missing recorded outs' in limit for limit in result['limitations'])


# ── rotation_context integration (additive metadata only) ────────────────────

def test_analyze_game_attaches_game_shape_without_changing_fields():
    item, reason = _analyze_game([_gl(1, 1, 1, 18), _gl(1, 1, 0, 9)])
    assert reason is None
    assert item['game_shape'] == SHAPE_NORMAL_START
    # Existing calculation fields remain intact and unchanged.
    assert item['starter_outs'] == 18
    assert item['bullpen_outs'] == 9
    assert item['known_outs'] == 27
    assert item['coverage_available'] is True


def test_rotation_context_exposes_game_shape_distribution():
    logs = [
        _gl(1, 1, 1, 18), _gl(1, 1, 0, 3), _gl(1, 1, 0, 6),   # normal start
        _gl(2, 2, 0, 9), _gl(2, 2, 0, 9), _gl(2, 2, 0, 6),    # bullpen game (excluded from analysis)
    ]
    out = build_rotation_context(logs, reference_date=REF)
    distribution = out['game_shape_distribution']
    assert distribution.get(SHAPE_NORMAL_START) == 1
    assert distribution.get(SHAPE_BULLPEN_GAME) == 1
    # The bullpen game stays excluded from analysis; classification did not
    # change which games are counted.
    assert out['games_excluded_14d'] >= 1


def test_game_shape_of_returns_constant():
    assert game_shape_of([_gl(9, 1, 1, 18)]) == SHAPE_NORMAL_START
