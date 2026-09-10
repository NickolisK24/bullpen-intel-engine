"""
Shared pytest fixtures and import setup for the backend test suite.

These tests deliberately avoid any database, Flask app context, or network:
the fatigue scoring engine is pure Python, so we test it directly with small
in-memory stand-ins for the Pitcher and GameLog models.
"""

import os
import sys
from datetime import date

import pytest

# Put the backend package root (the parent of this tests/ dir) on sys.path so
# `import services.fatigue` / `models...` resolve exactly as they do when the
# app runs from the backend/ directory.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from tests.db_config import (  # noqa: E402,F401
    assert_disposable_test_target,
    configure_test_database,
    create_test_schema,
    drop_test_schema,
    test_database_url,
)


def pytest_sessionstart(session):
    database_url = test_database_url()
    assert_disposable_test_target(database_url, operation='pytest session')


class PitcherStub:
    """Minimal stand-in for the Pitcher model — calculate_fatigue only reads .id."""
    def __init__(self, pitcher_id=1):
        self.id = pitcher_id


class GameLogStub:
    """
    Minimal stand-in for a GameLog row. calculate_fatigue only reads
    game_date, pitches_thrown, innings_pitched, and optionally
    innings_pitched_outs.
    """
    def __init__(self, game_date, pitches_thrown=0, innings_pitched=0.0,
                 innings_pitched_outs=None):
        if isinstance(game_date, str):
            game_date = date.fromisoformat(game_date)
        self.game_date = game_date
        self.pitches_thrown = pitches_thrown
        self.innings_pitched = innings_pitched
        self.innings_pitched_outs = innings_pitched_outs


@pytest.fixture
def pitcher():
    return PitcherStub(pitcher_id=42)


@pytest.fixture
def make_log():
    """Factory for GameLogStub so each test builds exactly the logs it needs."""
    def _make(game_date, pitches_thrown=0, innings_pitched=0.0,
              innings_pitched_outs=None):
        return GameLogStub(
            game_date,
            pitches_thrown,
            innings_pitched,
            innings_pitched_outs,
        )
    return _make


@pytest.fixture
def reference_date():
    """A fixed reference date so calculate_fatigue tests are deterministic."""
    return date(2024, 9, 10)
