from datetime import date
from types import SimpleNamespace

import pytest

from services.game_finality import (
    CANCELLED,
    FINAL_AND_USABLE,
    FINAL_PENDING_DATA,
    NOT_FINAL,
    POSTPONED,
    SUSPENDED,
    UNKNOWN,
    classify_game_finality,
    scheduled_rows_have_unresolved_resumed_linkage,
)


def _game(game_pk=7001, *, code='F', detailed='Final', abstract='Final', game_number=1):
    return {
        'gamePk': game_pk,
        'gameNumber': game_number,
        'status': {
            'statusCode': code,
            'detailedState': detailed,
            'abstractGameState': abstract,
        },
    }


def _boxscore():
    return {
        'teams': {
            'home': {
                'pitchers': [101],
                'players': {
                    'ID101': {
                        'person': {'id': 101, 'fullName': 'Home Pitcher'},
                        'stats': {'pitching': {'inningsPitched': '1.0'}},
                    },
                },
            },
            'away': {
                'pitchers': [202],
                'players': {
                    'ID202': {
                        'person': {'id': 202, 'fullName': 'Away Pitcher'},
                        'stats': {'pitching': {'inningsPitched': '1.0'}},
                    },
                },
            },
        },
    }


def test_final_completed_game_with_usable_boxscore_is_final_and_usable():
    decision = classify_game_finality(
        _game(),
        boxscore=_boxscore(),
        require_boxscore=True,
    )

    assert decision.state == FINAL_AND_USABLE
    assert decision.is_final_and_usable is True
    assert decision.has_safe_final_status is True


def test_abstract_final_alone_is_not_final_usable():
    decision = classify_game_finality(
        _game(code='I', detailed='In Progress', abstract='Final'),
        require_boxscore=True,
    )

    assert decision.state == NOT_FINAL
    assert decision.is_final_and_usable is False
    assert decision.has_safe_final_status is False


@pytest.mark.parametrize(
    ('game', 'expected_state'),
    [
        (_game(code='F', detailed='Postponed', abstract='Final'), POSTPONED),
        (_game(code='U', detailed='Suspended', abstract='Live'), SUSPENDED),
        (_game(code='C', detailed='Cancelled', abstract='Final'), CANCELLED),
        (_game(code='I', detailed='In Progress', abstract='Live'), NOT_FINAL),
        (_game(code='I', detailed='Final', abstract='Final'), NOT_FINAL),
        (_game(code='S', detailed='Final', abstract='Final'), NOT_FINAL),
        ({'status': {'statusCode': 'F'}}, UNKNOWN),
    ],
)
def test_status_precedence_blocks_unsafe_finality(game, expected_state):
    decision = classify_game_finality(game, require_boxscore=True)

    assert decision.state == expected_state
    assert decision.is_final_and_usable is False


def test_final_status_without_boxscore_is_pending_data():
    decision = classify_game_finality(_game(), require_boxscore=True)

    assert decision.state == FINAL_PENDING_DATA
    assert decision.reason == 'missing_boxscore'
    assert decision.is_final_and_usable is False


def test_empty_boxscore_is_pending_data():
    decision = classify_game_finality(
        _game(),
        boxscore={'teams': {'home': {'pitchers': [], 'players': {}}}},
        require_boxscore=True,
    )

    assert decision.state == FINAL_PENDING_DATA
    assert decision.reason == 'empty_boxscore'


def test_partial_boxscore_is_pending_data():
    boxscore = _boxscore()
    boxscore['teams'].pop('away')

    decision = classify_game_finality(
        _game(),
        boxscore=boxscore,
        require_boxscore=True,
    )

    assert decision.state == FINAL_PENDING_DATA
    assert decision.reason == 'missing_pitcher_identity'


def test_missing_pitcher_identity_is_pending_data():
    boxscore = _boxscore()
    boxscore['teams']['away']['players'].pop('ID202')

    decision = classify_game_finality(
        _game(),
        boxscore=boxscore,
        require_boxscore=True,
    )

    assert decision.state == FINAL_PENDING_DATA
    assert decision.reason == 'missing_pitcher_identity'


def test_split_doubleheader_games_remain_separate_by_game_pk_and_game_number():
    game_one = classify_game_finality(
        _game(game_pk=8001, game_number=1),
        boxscore=_boxscore(),
        require_boxscore=True,
    )
    game_two = classify_game_finality(
        _game(game_pk=8002, game_number=2),
        boxscore=_boxscore(),
        require_boxscore=True,
    )

    assert game_one.state == FINAL_AND_USABLE
    assert game_two.state == FINAL_AND_USABLE
    assert game_one.game_pk == 8001
    assert game_two.game_pk == 8002


def test_resumed_linkage_with_original_product_date_is_resolved():
    rows = [
        SimpleNamespace(
            status_state='final',
            resumed_from_game_pk=7001,
            resumed_to_game_pk=None,
            original_product_date=date(2026, 6, 20),
            resumed_product_date=date(2026, 7, 4),
        ),
        SimpleNamespace(
            status_state='final',
            resumed_from_game_pk=7001,
            resumed_to_game_pk=None,
            original_product_date=date(2026, 6, 20),
            resumed_product_date=date(2026, 7, 4),
        ),
    ]

    assert scheduled_rows_have_unresolved_resumed_linkage(rows) is False


@pytest.mark.parametrize(
    'rows',
    [
        [
            SimpleNamespace(
                status_state='suspended',
                resumed_from_game_pk=None,
                resumed_to_game_pk=None,
                original_product_date=None,
                resumed_product_date=None,
            ),
        ],
        [
            SimpleNamespace(
                status_state='final',
                resumed_from_game_pk=7001,
                resumed_to_game_pk=None,
                original_product_date=None,
                resumed_product_date=date(2026, 7, 4),
            ),
        ],
        [
            SimpleNamespace(
                status_state='final',
                resumed_from_game_pk=7001,
                resumed_to_game_pk=None,
                original_product_date=date(2026, 6, 20),
                resumed_product_date=date(2026, 7, 4),
            ),
            SimpleNamespace(
                status_state='final',
                resumed_from_game_pk=7002,
                resumed_to_game_pk=None,
                original_product_date=date(2026, 6, 20),
                resumed_product_date=date(2026, 7, 4),
            ),
        ],
    ],
)
def test_ambiguous_resumed_linkage_fails_closed(rows):
    assert scheduled_rows_have_unresolved_resumed_linkage(rows) is True
