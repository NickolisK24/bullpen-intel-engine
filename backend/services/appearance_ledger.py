"""
Appearance Ledger integrity checks.

The trust question this module answers: for every MLB game that went final in
a trailing window, does the database hold the appearance rows we can prove
should exist? Three durable sources are reconciled:

- ``scheduled_games``   — which games went final (EXPECTED games)
- ``game_logs``         — which games have appearance rows (REPRESENTED games)
- ``postgame_processed_games`` — how many pitching lines each completed-game
  ingest saw (EXPECTED appearance counts per game)

This exists because the July 4, 2026 slate was partially ingested, the sync
lanes that should have healed it failed, and the publish gate only validated
the single newest data date — so the hole became invisible the moment July 5
data landed. The ledger check is windowed precisely so history stays proven.

Fail-closed contract: any deficit means the ledger is NOT complete, and the
dashboard snapshot publisher withholds publication (the previous trusted
snapshot keeps serving). We never optimize around availability.
"""

from datetime import timedelta
import logging
import os

from sqlalchemy import func

from models.game_log import GameLog
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from services.availability_reference_date import product_current_date
from utils.db import db


logger = logging.getLogger(__name__)

DEFAULT_LEDGER_WINDOW_DAYS = 10
_FALSEY_ENV_VALUES = {'0', 'false', 'no', 'off', 'disabled'}

REASON_MISSING_GAMES = 'final_games_without_appearance_rows'
REASON_COUNT_DEFICITS = 'appearance_rows_below_ingested_pitching_lines'
REASON_INCOMPLETE_MARKERS = 'final_games_with_incomplete_postgame_markers'


def ledger_gate_enabled() -> bool:
    """Publish-gate kill switch. Enabled unless explicitly disabled — the
    override exists for operators, never for code paths."""
    raw = os.environ.get('APPEARANCE_LEDGER_GATE_ENABLED')
    if raw is None:
        return True
    return str(raw).strip().lower() not in _FALSEY_ENV_VALUES


def ledger_window_days() -> int:
    raw = os.environ.get('APPEARANCE_LEDGER_WINDOW_DAYS')
    try:
        value = int(raw) if raw not in (None, '') else DEFAULT_LEDGER_WINDOW_DAYS
    except (TypeError, ValueError):
        value = DEFAULT_LEDGER_WINDOW_DAYS
    return max(1, value)


def _expected_final_games(start_date, end_date):
    """Distinct final games in the window: game_pk -> game_date."""
    rows = (
        db.session.query(ScheduledGame.game_pk, ScheduledGame.game_date)
        .filter(ScheduledGame.game_date >= start_date)
        .filter(ScheduledGame.game_date <= end_date)
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .distinct()
        .all()
    )
    return {game_pk: game_date for game_pk, game_date in rows}


def _stored_appearance_counts(game_pks):
    if not game_pks:
        return {}
    rows = (
        db.session.query(GameLog.mlb_game_pk, func.count(GameLog.id))
        .filter(GameLog.mlb_game_pk.in_(game_pks))
        .group_by(GameLog.mlb_game_pk)
        .all()
    )
    return dict(rows)


def _postgame_markers(game_pks):
    if not game_pks:
        return {}
    markers = (
        PostgameProcessedGame.query
        .filter(PostgameProcessedGame.mlb_game_pk.in_(game_pks))
        .all()
    )
    return {marker.mlb_game_pk: marker for marker in markers}


def build_appearance_ledger(end_date=None, window_days=None):
    """
    Reconcile the appearance ledger over a trailing window (inclusive).

    Returns a dict with per-date detail and an overall ``complete`` verdict.
    ``complete`` is True only when every final game in the window is
    represented by appearance rows, no game holds fewer rows than the
    pitching lines its completed-game ingest saw, and no final game sits on
    an incomplete/failed postgame marker.
    """
    end_date = end_date or product_current_date()
    if window_days is None:
        window_days = ledger_window_days()
    start_date = end_date - timedelta(days=window_days - 1)

    expected = _expected_final_games(start_date, end_date)
    game_pks = sorted(expected)
    stored_counts = _stored_appearance_counts(game_pks)
    markers = _postgame_markers(game_pks)

    missing_games = []
    count_deficits = []
    incomplete_markers = []
    expected_appearances = 0
    stored_appearances = 0

    for game_pk in game_pks:
        stored = int(stored_counts.get(game_pk, 0) or 0)
        stored_appearances += stored
        marker = markers.get(game_pk)

        if stored == 0:
            missing_games.append({
                'game_pk': game_pk,
                'game_date': expected[game_pk].isoformat(),
                'marker_status': marker.processing_status if marker else None,
            })

        if marker is None:
            continue

        lines_seen = int(marker.pitching_lines_seen or 0)
        if marker.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED:
            expected_appearances += lines_seen
            if lines_seen > stored:
                count_deficits.append({
                    'game_pk': game_pk,
                    'game_date': expected[game_pk].isoformat(),
                    'expected_appearances': lines_seen,
                    'stored_appearances': stored,
                })
        else:
            incomplete_markers.append({
                'game_pk': game_pk,
                'game_date': expected[game_pk].isoformat(),
                'marker_status': marker.processing_status,
                'incomplete_reason': marker.incomplete_reason,
                'attempt_count': marker.attempt_count,
            })

    per_date = {}
    for game_pk, game_date in expected.items():
        key = game_date.isoformat()
        entry = per_date.setdefault(key, {'expected': 0, 'represented': 0, 'missing_game_pks': []})
        entry['expected'] += 1
        if int(stored_counts.get(game_pk, 0) or 0) > 0:
            entry['represented'] += 1
        else:
            entry['missing_game_pks'].append(game_pk)

    reasons = []
    if missing_games:
        reasons.append(REASON_MISSING_GAMES)
    if count_deficits:
        reasons.append(REASON_COUNT_DEFICITS)
    if incomplete_markers:
        reasons.append(REASON_INCOMPLETE_MARKERS)

    return {
        'window_start': start_date.isoformat(),
        'window_end': end_date.isoformat(),
        'window_days': window_days,
        'expected_games': len(expected),
        'represented_games': sum(
            1 for game_pk in game_pks if int(stored_counts.get(game_pk, 0) or 0) > 0
        ),
        'expected_appearances': expected_appearances,
        'stored_appearances': stored_appearances,
        'missing_games': missing_games,
        'count_deficit_games': count_deficits,
        'incomplete_marker_games': incomplete_markers,
        'per_date': dict(sorted(per_date.items())),
        'reasons': reasons,
        'complete': not reasons,
    }


def appearance_ledger_publish_block(end_date=None, window_days=None):
    """
    Publish-gate entry point. Returns ``(reason, ledger)``.

    ``reason`` is None when the ledger is provably complete (publishing is
    allowed). Any deficit — or any failure to compute the ledger at all —
    returns a non-None reason: an unprovable ledger must not publish.
    """
    if not ledger_gate_enabled():
        logger.warning(
            'Appearance ledger publish gate is DISABLED via '
            'APPEARANCE_LEDGER_GATE_ENABLED — publishing without ledger proof.'
        )
        return None, None
    try:
        ledger = build_appearance_ledger(end_date=end_date, window_days=window_days)
    except Exception as exc:  # noqa: BLE001 — unprovable ledger fails closed
        logger.error('Appearance ledger computation failed; withholding publish: %s', exc)
        return 'appearance_ledger_unavailable', None

    if ledger['complete']:
        return None, ledger

    logger.error(
        'Appearance ledger incomplete for %s..%s: reasons=%s missing=%s '
        'count_deficits=%s incomplete_markers=%s — withholding publish.',
        ledger['window_start'],
        ledger['window_end'],
        ledger['reasons'],
        [entry['game_pk'] for entry in ledger['missing_games']],
        [entry['game_pk'] for entry in ledger['count_deficit_games']],
        [entry['game_pk'] for entry in ledger['incomplete_marker_games']],
    )
    return 'appearance_ledger_incomplete', ledger
