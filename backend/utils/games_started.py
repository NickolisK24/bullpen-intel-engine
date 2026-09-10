from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class InvalidGamesStartedValue(ValueError):
    """Raised when a gamesStarted value is present but not 0 or 1."""


START = 'start'
RELIEF = 'relief'
UNKNOWN = 'unknown'


UNKNOWN_START_SHARE_THRESHOLD = 0.25
UNKNOWN_START_LIMITATION = (
    'Some rows are missing gamesStarted; unknown rows are excluded from '
    'start/relief-specific workload reads.'
)
MATERIAL_UNKNOWN_START_LIMITATION = (
    'More than 25% of rows in this window are missing gamesStarted, so the '
    'start/relief-specific workload read is withheld.'
)


@dataclass(frozen=True)
class GamesStartedSummary:
    total: int
    starts: int
    relief: int
    unknown: int

    @property
    def known(self) -> int:
        return self.starts + self.relief

    @property
    def unknown_share(self) -> float:
        return self.unknown / self.total if self.total else 0.0

    @property
    def material_unknown(self) -> bool:
        return self.unknown_share > UNKNOWN_START_SHARE_THRESHOLD


def parse_games_started(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise InvalidGamesStartedValue(f'Invalid gamesStarted value: {value!r}') from None
    if parsed not in (0, 1):
        raise InvalidGamesStartedValue(f'Invalid gamesStarted value: {value!r}')
    return parsed


def games_started_state(value: Any) -> str:
    parsed = parse_games_started(value)
    if parsed == 1:
        return START
    if parsed == 0:
        return RELIEF
    return UNKNOWN


def log_games_started_state(log: Any) -> str:
    return games_started_state(getattr(log, 'games_started', None))


def is_start(log: Any) -> bool:
    return log_games_started_state(log) == START


def is_relief(log: Any) -> bool:
    return log_games_started_state(log) == RELIEF


def is_unknown_start(log: Any) -> bool:
    return log_games_started_state(log) == UNKNOWN


def games_started_summary(logs) -> GamesStartedSummary:
    states = [log_games_started_state(log) for log in list(logs or [])]
    return GamesStartedSummary(
        total=len(states),
        starts=sum(1 for state in states if state == START),
        relief=sum(1 for state in states if state == RELIEF),
        unknown=sum(1 for state in states if state == UNKNOWN),
    )
