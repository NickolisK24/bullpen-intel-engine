"""Shared game finality authority.

This module owns precedence-based status classification for MLB games. It keeps
finality decisions in one place so schedule ingestion, postgame refresh, daily
game-log ingestion, and slate coverage cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


FINAL_AND_USABLE = 'final_and_usable'
FINAL_PENDING_DATA = 'final_pending_data'
NOT_FINAL = 'not_final'
POSTPONED = 'postponed'
SUSPENDED = 'suspended'
CANCELLED = 'cancelled'
UNKNOWN = 'unknown'

SCHEDULED_STATUS_STATE = 'scheduled'
FINAL_STATUS_STATE = 'final'
POSTPONED_STATUS_STATE = 'postponed'
SUSPENDED_STATUS_STATE = 'suspended'
OTHER_STATUS_STATE = 'other'

FINAL_GAME_STATUS_CODES = frozenset({'F', 'O', 'FR', 'FT'})
SCHEDULED_STATUS_CODES = frozenset({'S', 'P', 'PW', 'PR'})
IN_PROGRESS_STATUS_CODES = frozenset({'I'})

FINAL_DETAILED_STATES = frozenset({
    'final',
    'game over',
    'completed early',
    'final: tied',
})

SCHEDULED_DETAILED_STATES = frozenset({
    'scheduled',
    'pre-game',
    'warmup',
    'delayed start',
})


@dataclass(frozen=True)
class GameFinalityDecision:
    state: str
    reason: str
    game_pk: int | None = None
    status_state: str = OTHER_STATUS_STATE
    final_status: bool = False
    usable_boxscore: bool = False

    @property
    def is_final_and_usable(self) -> bool:
        return self.state == FINAL_AND_USABLE

    @property
    def has_safe_final_status(self) -> bool:
        return self.final_status and self.state in {
            FINAL_AND_USABLE,
            FINAL_PENDING_DATA,
        }


def classify_game_finality(
    game: dict | None,
    *,
    boxscore: dict | None = None,
    require_boxscore: bool = False,
) -> GameFinalityDecision:
    """Classify a game using status first, then optional boxscore evidence.

    Precedence is deliberately conservative:
    postponed, suspended, cancelled, missing game id, and non-final states
    always override final-ish status. ``abstractGameState=Final`` alone is not
    enough to make a game final.
    """
    game = game or {}
    game_pk = _positive_int(game.get('gamePk'))
    if game_pk is None:
        return GameFinalityDecision(
            state=UNKNOWN,
            reason='missing_game_pk',
            game_pk=None,
            status_state=OTHER_STATUS_STATE,
        )

    status = game.get('status') or {}
    status_decision = classify_status(status, game_pk=game_pk)
    if not status_decision.final_status:
        return status_decision

    if not require_boxscore and boxscore is None:
        return status_decision

    boxscore_decision = classify_boxscore_usability(boxscore)
    if not boxscore_decision.is_final_and_usable:
        return GameFinalityDecision(
            state=FINAL_PENDING_DATA,
            reason=boxscore_decision.reason,
            game_pk=game_pk,
            status_state=FINAL_STATUS_STATE,
            final_status=True,
            usable_boxscore=False,
        )

    return GameFinalityDecision(
        state=FINAL_AND_USABLE,
        reason='final_status_with_usable_boxscore',
        game_pk=game_pk,
        status_state=FINAL_STATUS_STATE,
        final_status=True,
        usable_boxscore=True,
    )


def classify_status(status: dict | None, *, game_pk: int | None = None) -> GameFinalityDecision:
    """Classify raw MLB schedule status without boxscore evidence."""
    status = status or {}
    code = str(status.get('statusCode') or '').strip().upper()
    detailed = str(status.get('detailedState') or '').strip().lower()
    abstract = str(status.get('abstractGameState') or '').strip().lower()

    if 'postpon' in detailed:
        return GameFinalityDecision(
            state=POSTPONED,
            reason='postponed_status',
            game_pk=game_pk,
            status_state=POSTPONED_STATUS_STATE,
        )
    if 'suspend' in detailed:
        return GameFinalityDecision(
            state=SUSPENDED,
            reason='suspended_status',
            game_pk=game_pk,
            status_state=SUSPENDED_STATUS_STATE,
        )
    if 'cancel' in detailed or code == 'C':
        return GameFinalityDecision(
            state=CANCELLED,
            reason='cancelled_status',
            game_pk=game_pk,
            status_state=OTHER_STATUS_STATE,
        )
    if (
        code in SCHEDULED_STATUS_CODES
        or abstract == 'preview'
        or detailed in SCHEDULED_DETAILED_STATES
    ):
        return GameFinalityDecision(
            state=NOT_FINAL,
            reason='scheduled_status',
            game_pk=game_pk,
            status_state=SCHEDULED_STATUS_STATE,
        )
    if (
        code in IN_PROGRESS_STATUS_CODES
        or abstract == 'live'
        or 'progress' in detailed
        or detailed == 'live'
    ):
        return GameFinalityDecision(
            state=NOT_FINAL,
            reason='live_or_in_progress_status',
            game_pk=game_pk,
            status_state=OTHER_STATUS_STATE,
        )
    if (
        code in FINAL_GAME_STATUS_CODES
        or detailed in FINAL_DETAILED_STATES
        or detailed.startswith('final')
    ):
        return GameFinalityDecision(
            state=FINAL_PENDING_DATA,
            reason='final_status_pending_boxscore',
            game_pk=game_pk,
            status_state=FINAL_STATUS_STATE,
            final_status=True,
        )
    if abstract == 'final':
        return GameFinalityDecision(
            state=UNKNOWN,
            reason='abstract_final_without_final_status',
            game_pk=game_pk,
            status_state=OTHER_STATUS_STATE,
        )
    return GameFinalityDecision(
        state=UNKNOWN,
        reason='unknown_status',
        game_pk=game_pk,
        status_state=OTHER_STATUS_STATE,
    )


def normalize_schedule_status_state(game_or_status: dict | None) -> str:
    """Map raw MLB status into the stored scheduled_games status_state value.

    This is a compatibility/status display mapping, not a second finality
    authority. It delegates to ``classify_status``.
    """
    value = game_or_status or {}
    status = value.get('status') if 'status' in value else value
    return classify_status(status).status_state


def has_safe_final_status(game: dict | None) -> bool:
    """Return True only when status is final by code/detail precedence."""
    return classify_game_finality(game).has_safe_final_status


def classify_boxscore_usability(boxscore: dict | None) -> GameFinalityDecision:
    if not isinstance(boxscore, dict) or not boxscore:
        return GameFinalityDecision(
            state=FINAL_PENDING_DATA,
            reason='missing_boxscore',
            usable_boxscore=False,
        )

    teams = boxscore.get('teams')
    if not isinstance(teams, dict) or not teams:
        return GameFinalityDecision(
            state=FINAL_PENDING_DATA,
            reason='empty_boxscore',
            usable_boxscore=False,
        )

    valid_lines = 0
    identity_failures = 0
    side_failures = 0
    for side in ('home', 'away'):
        side_data = teams.get(side)
        if not isinstance(side_data, dict):
            side_failures += 1
            continue
        side_valid, side_identity_failures = _pitching_identity_counts(side_data)
        valid_lines += side_valid
        identity_failures += side_identity_failures
        if side_valid == 0:
            side_failures += 1

    if valid_lines == 0:
        return GameFinalityDecision(
            state=FINAL_PENDING_DATA,
            reason='empty_boxscore',
            usable_boxscore=False,
        )
    if identity_failures or side_failures:
        return GameFinalityDecision(
            state=FINAL_PENDING_DATA,
            reason='missing_pitcher_identity',
            usable_boxscore=False,
        )
    return GameFinalityDecision(
        state=FINAL_AND_USABLE,
        reason='usable_boxscore_pitching_identity',
        usable_boxscore=True,
    )


def scheduled_rows_have_unresolved_resumed_linkage(rows: Iterable[object]) -> bool:
    """Return True when stored suspended/resumed linkage is too ambiguous.

    Suspended rows remain unresolved until a safe resumed link is stored. Final
    rows that identify a resumed-from game need the original product date.
    """
    rows = list(rows or [])
    if not rows:
        return False

    if _conflicting_values(rows, 'resumed_from_game_pk'):
        return True
    if _conflicting_values(rows, 'resumed_to_game_pk'):
        return True
    if _conflicting_values(rows, 'original_product_date'):
        return True
    if _conflicting_values(rows, 'resumed_product_date'):
        return True

    for row in rows:
        status_state = getattr(row, 'status_state', None)
        resumed_from = getattr(row, 'resumed_from_game_pk', None)
        resumed_to = getattr(row, 'resumed_to_game_pk', None)
        original_date = getattr(row, 'original_product_date', None)
        resumed_date = getattr(row, 'resumed_product_date', None)

        if status_state == SUSPENDED_STATUS_STATE:
            return True
        if resumed_from is not None and original_date is None:
            return True
        if resumed_to is not None and resumed_date is None:
            return True
    return False


def _pitching_identity_counts(side_data: dict) -> tuple[int, int]:
    players = side_data.get('players') or {}
    pitcher_ids = [
        _positive_int(value)
        for value in (side_data.get('pitchers') or [])
    ]
    pitcher_ids = [value for value in pitcher_ids if value is not None]

    ids_from_players = []
    for key, player in players.items():
        pitching = ((player or {}).get('stats') or {}).get('pitching')
        if pitching:
            ids_from_players.append(_positive_int(str(key).removeprefix('ID')))

    candidate_ids = pitcher_ids or [value for value in ids_from_players if value is not None]
    if not candidate_ids:
        return 0, 0

    valid = 0
    failures = 0
    for player_id in candidate_ids:
        player = players.get(f'ID{player_id}')
        person = (player or {}).get('person') or {}
        stats = ((player or {}).get('stats') or {}).get('pitching') or {}
        person_id = _positive_int(person.get('id') or player_id)
        name = str(person.get('fullName') or person.get('lastFirstName') or '').strip()
        if person_id is None or not name or not stats:
            failures += 1
        else:
            valid += 1
    return valid, failures


def _conflicting_values(rows: Iterable[object], field_name: str) -> bool:
    values = {
        _normalized_value(getattr(row, field_name, None))
        for row in rows
        if getattr(row, field_name, None) is not None
    }
    return len(values) > 1


def _normalized_value(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
