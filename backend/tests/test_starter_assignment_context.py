"""Unit coverage for the starter-assignment derivation.

These tests exercise ``derive_starter_assignment_context`` directly with
stub rows so ordering, dedupe, and fail-closed paths are covered without a
database. Endpoint-level behavior lives in
``test_public_team_relief_work.py``.
"""

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from services import pitcher_season_ledger_coverage
from services.starter_assignment_context import (
    COVERAGE_SCOPE_PITCHER_SEASON_TO_TARGET,
    COVERAGE_STATE_COMPLETE,
    FIRST_SEASON_START_MIN_RELIEF_APPEARANCES,
    MIN_CONSECUTIVE_RELIEF_APPEARANCES,
    MIN_DAYS_SINCE_PREVIOUS_START,
    NARRATIVE_FIRST_SEASON_START,
    NARRATIVE_FIRST_START_IN_DAYS,
    derive_starter_assignment_context,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / 'backend/services/starter_assignment_context.py'

PITCHER = SimpleNamespace(full_name='Stub Pitcher', mlb_id=12345)


def _row(game_date, game_pk, games_started=0, game_type='R'):
    return SimpleNamespace(
        game_date=game_date,
        mlb_game_pk=game_pk,
        games_started=games_started,
        game_type=game_type,
        pitcher_id=1,
    )


def _target(game_date=date(2026, 7, 5), game_pk=9900):
    return _row(game_date, game_pk, games_started=1)


def _verified_coverage(target, history, *, source_appearances=None, source_starts=None):
    counted = {target.mlb_game_pk: target}
    for row in history:
        if row.game_date is None or row.mlb_game_pk is None:
            continue
        if row.game_date > target.game_date:
            continue
        if row.game_date == target.game_date and row.mlb_game_pk > target.mlb_game_pk:
            continue
        counted.setdefault(row.mlb_game_pk, row)
    appearances = len(counted)
    starts = sum(1 for row in counted.values() if row.games_started == 1)
    fingerprint = pitcher_season_ledger_coverage.manifest_fingerprint(
        pitcher_season_ledger_coverage.build_stored_manifest_from_rows(
            counted.values()
        )['entries']
    )
    return {
        'coverage_state': COVERAGE_STATE_COMPLETE,
        'coverage_scope': COVERAGE_SCOPE_PITCHER_SEASON_TO_TARGET,
        'pitcher_id': target.pitcher_id,
        'pitcher_mlb_id': PITCHER.mlb_id,
        'season': target.game_date.year,
        'game_type': target.game_type,
        'target_game_pk': target.mlb_game_pk,
        'covered_through_date': target.game_date.isoformat(),
        'stored_appearance_count': appearances,
        'source_appearance_count': (
            appearances if source_appearances is None else source_appearances
        ),
        'stored_games_started_count': starts,
        'source_games_started_count': starts if source_starts is None else source_starts,
        'source_manifest_fingerprint': fingerprint,
        'stored_manifest_fingerprint': fingerprint,
    }


def test_reconciled_ledger_produces_combined_sentence():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    target = _target()
    context = derive_starter_assignment_context(
        target,
        PITCHER,
        history,
        history_coverage=_verified_coverage(target, history),
    )

    assert context == {
        'narrative_type': NARRATIVE_FIRST_START_IN_DAYS,
        'sentence': (
            'Stub Pitcher made his first start in 38 days after '
            '3 consecutive relief appearances.'
        ),
        'previous_start_date': '2026-05-28',
        'days_since_previous_start': 38,
        'consecutive_relief_appearances': 3,
    }


def test_target_game_row_is_never_counted_as_history():
    history = [
        _row(date(2026, 7, 5), 9900, games_started=1),
    ]
    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_duplicate_game_rows_count_once():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    target = _target()
    context = derive_starter_assignment_context(
        target,
        PITCHER,
        history,
        history_coverage=_verified_coverage(target, history),
    )

    assert context['consecutive_relief_appearances'] == 3


def test_doubleheader_rows_order_by_game_identifier():
    target = _target(game_pk=9900)
    history = [
        _row(date(2026, 6, 15), 9800, games_started=1),
        _row(date(2026, 7, 1), 9801),
        _row(date(2026, 7, 3), 9802),
        # Same date as the target: the lower game id sorts before the
        # target and counts; the higher game id sorts after it and never
        # counts.
        _row(date(2026, 7, 5), 9899),
        _row(date(2026, 7, 5), 9901),
    ]
    context = derive_starter_assignment_context(
        target,
        PITCHER,
        history,
        history_coverage=_verified_coverage(target, history),
    )

    assert context['consecutive_relief_appearances'] == 3
    assert context['days_since_previous_start'] == 20


def test_missing_history_date_stays_silent():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(None, 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_missing_target_date_stays_silent():
    target = _row(None, 9900, games_started=1)
    history = [_row(date(2026, 6, 1), 9801)]
    assert derive_starter_assignment_context(target, PITCHER, history) is None


def test_unknown_flag_inside_sequence_stays_silent():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802, games_started=None),
        _row(date(2026, 6, 20), 9803),
    ]
    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_malformed_flag_inside_sequence_stays_silent():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801, games_started=7),
        _row(date(2026, 6, 20), 9803),
    ]
    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_gap_below_threshold_stays_silent():
    previous = date(2026, 7, 5) - timedelta(days=MIN_DAYS_SINCE_PREVIOUS_START - 1)
    history = [
        _row(previous, 9800, games_started=1),
        _row(date(2026, 7, 1), 9801),
        _row(date(2026, 7, 2), 9802),
        _row(date(2026, 7, 3), 9803),
    ]
    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_relief_run_below_threshold_stays_silent():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
    ]
    history.extend(
        _row(date(2026, 7, 1 + offset), 9801 + offset)
        for offset in range(MIN_CONSECUTIVE_RELIEF_APPEARANCES - 1)
    )
    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_first_start_of_season_after_relief_only_history():
    history = [
        _row(date(2026, 6, 1 + offset), 9801 + offset)
        for offset in range(FIRST_SEASON_START_MIN_RELIEF_APPEARANCES)
    ]
    target = _target()
    context = derive_starter_assignment_context(
        target,
        PITCHER,
        history,
        history_coverage=_verified_coverage(target, history),
    )

    assert context == {
        'narrative_type': NARRATIVE_FIRST_SEASON_START,
        'sentence': (
            'Stub Pitcher made his first start of the season after '
            '5 relief appearances.'
        ),
        'previous_start_date': None,
        'days_since_previous_start': None,
        'consecutive_relief_appearances': 5,
    }


def test_empty_history_stays_silent():
    assert derive_starter_assignment_context(_target(), PITCHER, []) is None


def test_ledger_without_affirmative_coverage_stays_silent():
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]

    assert derive_starter_assignment_context(_target(), PITCHER, history) is None


def test_missing_relief_appearance_inside_short_gap_stays_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        # Missing June 5 relief appearance is represented by source count only.
        _row(date(2026, 6, 8), 9803),
        _row(date(2026, 6, 12), 9804),
    ]
    coverage = _verified_coverage(
        target,
        history,
        source_appearances=len(history) + 2,
    )

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_missing_intervening_start_stays_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    coverage = _verified_coverage(target, history, source_starts=3)

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_stored_appearance_count_mismatch_stays_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    coverage = _verified_coverage(target, history)
    coverage['stored_appearance_count'] -= 1

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_stored_games_started_count_mismatch_stays_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    coverage = _verified_coverage(target, history)
    coverage['stored_games_started_count'] -= 1

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_unknown_source_totals_stay_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    coverage = _verified_coverage(target, history)
    coverage['source_appearance_count'] = None

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_wrong_target_game_coverage_stays_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    coverage = _verified_coverage(target, history)
    coverage['target_game_pk'] = 9901

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_count_matched_manifest_mismatch_stays_silent():
    target = _target()
    history = [
        _row(date(2026, 5, 28), 9800, games_started=1),
        _row(date(2026, 6, 1), 9801),
        _row(date(2026, 6, 8), 9802),
        _row(date(2026, 6, 20), 9803),
    ]
    coverage = _verified_coverage(target, history)
    coverage['source_manifest_fingerprint'] = 'b' * 64

    assert (
        derive_starter_assignment_context(
            target,
            PITCHER,
            history,
            history_coverage=coverage,
        )
        is None
    )


def test_blackburn_complete_verified_ledger_produces_sentence():
    target = _row(date(2026, 7, 9), 9900, games_started=1)
    history = [_row(date(2026, 5, 7), 9700, games_started=1)]
    history.extend(
        _row(date(2026, 5, 10 + offset), 9701 + offset)
        for offset in range(20)
    )
    pitcher = SimpleNamespace(full_name='Paul Blackburn', mlb_id=PITCHER.mlb_id)

    context = derive_starter_assignment_context(
        target,
        pitcher,
        history,
        history_coverage=_verified_coverage(target, history),
    )

    assert context['sentence'] == (
        'Paul Blackburn made his first start in 63 days after '
        '20 consecutive relief appearances.'
    )


def test_blackburn_truncated_ledger_without_coverage_stays_silent():
    target = _row(date(2026, 7, 9), 9900, games_started=1)
    history = [_row(date(2026, 5, 7), 9700, games_started=1)]
    history.extend(
        _row(date(2026, 5, 10 + offset), 9701 + offset)
        for offset in range(12)
    )
    pitcher = SimpleNamespace(full_name='Paul Blackburn')

    assert derive_starter_assignment_context(target, pitcher, history) is None


def test_non_regular_season_target_stays_silent():
    target = _row(date(2026, 7, 5), 9900, games_started=1, game_type='P')
    history = [
        _row(date(2026, 6, 1 + offset), 9801 + offset)
        for offset in range(6)
    ]
    assert derive_starter_assignment_context(target, PITCHER, history) is None


def test_missing_pitcher_name_stays_silent():
    history = [
        _row(date(2026, 6, 1 + offset), 9801 + offset)
        for offset in range(6)
    ]
    nameless = SimpleNamespace(full_name=None)
    assert derive_starter_assignment_context(_target(), nameless, history) is None


def test_source_never_authors_unsupported_claims():
    text = MODULE_PATH.read_text(encoding='utf-8')
    for phrase in (
        'major-league start',
        'major league start',
        'first career',
        'first start for',
        'rotation',
        'converted',
        'spot start',
        'opener',
        'manager',
        'planned',
        'forced',
    ):
        assert not re.search(
            rf'(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])',
            text,
            flags=re.I,
        ), phrase
