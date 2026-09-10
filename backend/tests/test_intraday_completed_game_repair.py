from datetime import date

import pytest

from services.intraday_completed_game_repair import (
    IntradayCompletedGameRepairError,
    _fetch_exact_completed_games,
    _require_complete_processing,
)


SLATE = date(2026, 7, 23)


def _game(game_pk=900001, *, status_code='F', detailed='Final', abstract='Final',
          home=143, away=121):
    return {
        'gamePk': game_pk,
        'officialDate': SLATE.isoformat(),
        'status': {
            'statusCode': status_code,
            'detailedState': detailed,
            'abstractGameState': abstract,
        },
        'teams': {
            'home': {'team': {'id': home}},
            'away': {'team': {'id': away}},
        },
    }


class _Client:
    def __init__(self, games):
        self.games = list(games)
        self.calls = []

    def get_schedule(self, start_date=None, end_date=None):
        self.calls.append((start_date, end_date))
        return list(self.games)


def _scope(*game_pks):
    return {
        'completed_game_pks': list(game_pks),
        'slate_dates': [SLATE.isoformat()],
    }


def test_exact_completed_game_is_selected():
    client = _Client([_game()])
    selected = _fetch_exact_completed_games(_scope(900001), client=client)
    assert list(selected) == [900001]
    assert selected[900001]['status']['detailedState'] == 'Final'
    assert client.calls == [(SLATE.isoformat(), SLATE.isoformat())]


def test_equivalent_duplicate_final_rows_collapse():
    game = _game()
    selected = _fetch_exact_completed_games(_scope(900001), client=_Client([game, dict(game)]))
    assert list(selected) == [900001]


def test_conflicting_duplicate_rows_fail_closed():
    with pytest.raises(IntradayCompletedGameRepairError, match='conflicting'):
        _fetch_exact_completed_games(
            _scope(900001),
            client=_Client([_game(), _game(home=111)]),
        )


def test_game_missing_at_write_time_fails_closed():
    with pytest.raises(IntradayCompletedGameRepairError, match='no longer contains'):
        _fetch_exact_completed_games(_scope(900001), client=_Client([]))


def test_finality_regression_fails_closed():
    with pytest.raises(IntradayCompletedGameRepairError, match='no longer proves'):
        _fetch_exact_completed_games(
            _scope(900001),
            client=_Client([
                _game(status_code='I', detailed='In Progress', abstract='Live')
            ]),
        )


def test_processing_accepts_fully_processed_result():
    _require_complete_processing(900001, {
        'processing_status': 'fully_processed',
        'pitcher_resolution_failures': 0,
        'correction_attempts_failed': 0,
        'skipped': False,
    })


def test_processing_accepts_idempotent_already_processed_skip():
    _require_complete_processing(900001, {
        'processing_status': 'fully_processed',
        'pitcher_resolution_failures': 0,
        'correction_attempts_failed': 0,
        'skipped': True,
        'reason': 'already_processed',
    })


def test_processing_rejects_incomplete_marker():
    with pytest.raises(IntradayCompletedGameRepairError, match='fully processed'):
        _require_complete_processing(900001, {
            'processing_status': 'incomplete',
            'pitcher_resolution_failures': 0,
            'correction_attempts_failed': 0,
        })


def test_processing_rejects_unresolved_pitcher():
    with pytest.raises(IntradayCompletedGameRepairError, match='unresolved pitchers'):
        _require_complete_processing(900001, {
            'processing_status': 'fully_processed',
            'pitcher_resolution_failures': 1,
            'correction_attempts_failed': 0,
        })


def test_processing_rejects_failed_correction():
    with pytest.raises(IntradayCompletedGameRepairError, match='failed corrections'):
        _require_complete_processing(900001, {
            'processing_status': 'fully_processed',
            'pitcher_resolution_failures': 0,
            'correction_attempts_failed': 1,
        })
