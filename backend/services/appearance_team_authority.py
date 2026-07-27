"""Canonical team-at-appearance authority (Foundation 1 of 6).

Every BaseballOS pitching appearance must be able to answer, durably and
correction-safely: *which MLB team did this pitcher represent in this game?* That
answer is resolved from OFFICIAL GAME-SIDE evidence at ingestion and frozen onto
the appearance row (``GameLog.appearance_team_id`` + provenance/status/reason). It
is NEVER derived from the pitcher's mutable current ``Pitcher.team_id``, so a trade,
option, release, or ordinary roster sync can never rewrite historical attribution.

Source precedence (most authoritative first):

  1. ``boxscore_side``   — the official box-score pitching side (home/away). The
     postgame refresh already resolves this per line with conflict detection; this
     module records it durably.
  2. ``schedule_opponent`` — the official schedule ledger (``ScheduledGame``): the
     side that faces the appearance's official opponent. Used by the daily-sync
     game-log lane, whose per-pitcher payload carries the opponent but not the
     pitcher's own side.

The pitcher's current team is FORBIDDEN as an attribution source (it may be used
only as an out-of-band diagnostic comparison). Missing authority fails closed as
``unresolved``; two authoritative sources that disagree fail closed as
``conflict``. Neither is ever encoded as a fake team id.

The per-pitcher gameLog feed may include an all-zero, zero-out listing for a final
game even when the player never pitched. A NEW all-zero row therefore requires
``boxscore_side`` authority. A schedule-only or unresolved all-zero listing fails
closed before INSERT; the official postgame box-score lane remains the authority for
legitimate 0.0-IP appearances. An existing official row may still be re-read by the
daily lane without flapping or creating a duplicate.

This module performs NO historical backfill. Legacy rows stay NULL until Step 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.game_log import GameLog
from models.scheduled_game import ScheduledGame
from utils.db import db


# Resolution status (mirrors the GameLog column vocabulary).
STATUS_RESOLVED = GameLog.APPEARANCE_TEAM_RESOLVED
STATUS_UNRESOLVED = GameLog.APPEARANCE_TEAM_UNRESOLVED
STATUS_CONFLICT = GameLog.APPEARANCE_TEAM_CONFLICT

# Official game-side sources, most authoritative first. Current Pitcher.team_id is
# deliberately NOT a source.
SOURCE_BOXSCORE = 'boxscore_side'
SOURCE_SCHEDULE = 'schedule_opponent'
SOURCE_CONFLICT = 'source_conflict'

# Governed, non-sensitive reason codes for internal diagnostics.
REASON_RESOLVED_BOXSCORE = 'appearance_team_resolved_boxscore'
REASON_RESOLVED_SCHEDULE = 'appearance_team_resolved_schedule'
REASON_UNRESOLVED = 'appearance_team_unresolved'
REASON_CONFLICT = 'appearance_team_source_conflict'
REASON_CORRECTED = 'appearance_team_corrected'
REASON_ZERO_OUT_UNVERIFIED = 'zero_out_appearance_requires_boxscore_line'

# Higher rank = more authoritative. Used to decide governed corrections and to
# guarantee non-flapping when two runs resolve the same appearance from different
# official sources.
_SOURCE_PRECEDENCE = {
    SOURCE_SCHEDULE: 1,
    SOURCE_BOXSCORE: 2,
}

_REASON_FOR_SOURCE = {
    SOURCE_BOXSCORE: REASON_RESOLVED_BOXSCORE,
    SOURCE_SCHEDULE: REASON_RESOLVED_SCHEDULE,
}

_ZERO_OUT_INTEGER_FIELDS = (
    'innings_pitched_outs',
    'pitches_thrown',
    'strikes',
    'hits_allowed',
    'runs_allowed',
    'earned_runs',
    'walks',
    'strikeouts',
    'home_runs_allowed',
    'batters_faced',
    'balls',
    'games_finished',
    'inherited_runners',
    'inherited_runners_scored',
)
_ZERO_OUT_BOOLEAN_FIELDS = (
    'save_situation',
    'hold',
    'blown_save',
    'win',
    'loss',
    'save',
)


class UnverifiedZeroOutAppearance(ValueError):
    """A new zero-out listing lacks final official box-score pitching authority."""

    reason_code = REASON_ZERO_OUT_UNVERIFIED


def _precedence(source: Optional[str]) -> int:
    return _SOURCE_PRECEDENCE.get(source, 0)


@dataclass(frozen=True)
class AppearanceTeamResolution:
    """The result of resolving the team an appearance represented."""

    team_id: Optional[int]
    status: str
    source: Optional[str]
    reason: Optional[str]

    @property
    def resolved(self) -> bool:
        return self.status == STATUS_RESOLVED and self.team_id is not None

    def to_write_fields(self) -> dict:
        """The four GameLog column values this resolution writes."""
        return {
            'appearance_team_id': self.team_id if self.resolved else None,
            'appearance_team_source': self.source,
            'appearance_team_status': self.status,
            'appearance_team_reason': self.reason,
        }


def _unresolved(reason: str = REASON_UNRESOLVED) -> AppearanceTeamResolution:
    return AppearanceTeamResolution(None, STATUS_UNRESOLVED, None, reason)


def resolve_from_schedule(game_pk, opponent_team_id, *, session=None) -> Optional[int]:
    """The represented team id from the official schedule, or None.

    A game_pk has one ``ScheduledGame`` row per side. The pitcher's team is the side
    that FACES the appearance's official opponent. Ambiguous or missing schedule
    coverage returns None (fails closed), never the opponent and never a guess.
    """
    session = session or db.session
    if game_pk is None or opponent_team_id is None:
        return None
    rows = (
        session.query(ScheduledGame)
        .filter(ScheduledGame.game_pk == game_pk)
        .all()
    )
    facing = {
        row.team_id
        for row in rows
        if row.team_id is not None and row.opponent_team_id == opponent_team_id
    }
    if len(facing) == 1:
        return next(iter(facing))
    return None


def resolve_for_write(
    *,
    boxscore_team_id: Optional[int] = None,
    game_pk: Optional[int] = None,
    opponent_team_id: Optional[int] = None,
    session=None,
) -> AppearanceTeamResolution:
    """Resolve the represented team for a GameLog about to be written.

    Applies the source-precedence contract. When the box-score side is known it is
    authoritative and is cross-checked against the schedule ledger: agreement (or an
    absent schedule) resolves via box score; a definite schedule disagreement fails
    closed as ``conflict``. Without a box-score side, the schedule ledger's
    opponent-facing side resolves it; otherwise the appearance is ``unresolved``.
    Current Pitcher.team_id is never consulted.
    """
    session = session or db.session
    boxscore_team_id = _positive_or_none(boxscore_team_id)
    opponent_team_id = _positive_or_none(opponent_team_id)

    if boxscore_team_id is not None:
        schedule_team_id = resolve_from_schedule(game_pk, opponent_team_id, session=session)
        if schedule_team_id is not None and schedule_team_id != boxscore_team_id:
            return AppearanceTeamResolution(
                None, STATUS_CONFLICT, SOURCE_CONFLICT, REASON_CONFLICT,
            )
        return AppearanceTeamResolution(
            boxscore_team_id, STATUS_RESOLVED, SOURCE_BOXSCORE, REASON_RESOLVED_BOXSCORE,
        )

    schedule_team_id = resolve_from_schedule(game_pk, opponent_team_id, session=session)
    if schedule_team_id is not None:
        return AppearanceTeamResolution(
            schedule_team_id, STATUS_RESOLVED, SOURCE_SCHEDULE, REASON_RESOLVED_SCHEDULE,
        )
    return _unresolved()


def _positive_or_none(value) -> Optional[int]:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return None
    return candidate if candidate > 0 else None


def is_all_zero_game_log_values(values: dict) -> bool:
    """Whether a complete normalized pitching line contains no pitching event.

    Optional integer fields may be absent/NULL or zero. The core run-prevention
    fields must be explicitly present so a partial fixture or malformed line cannot
    accidentally enter this special contract.
    """
    values = values or {}
    required = (
        'innings_pitched_outs',
        'strikes',
        'hits_allowed',
        'runs_allowed',
        'earned_runs',
        'walks',
        'strikeouts',
        'home_runs_allowed',
    )
    if any(field not in values for field in required):
        return False
    if values.get('games_started') not in (None, 0):
        return False
    if any(values.get(field) not in (None, 0) for field in _ZERO_OUT_INTEGER_FIELDS):
        return False
    if any(bool(values.get(field, False)) for field in _ZERO_OUT_BOOLEAN_FIELDS):
        return False
    return True


def _existing_game_log(values: dict):
    pitcher_id = _positive_or_none((values or {}).get('pitcher_id'))
    game_pk = _positive_or_none((values or {}).get('mlb_game_pk'))
    if pitcher_id is None or game_pk is None:
        return None
    return GameLog.query.filter_by(
        pitcher_id=pitcher_id,
        mlb_game_pk=game_pk,
    ).first()


def apply_to_new_log(values: dict, resolution: AppearanceTeamResolution) -> dict:
    """Fold a resolution's fields into a values dict for an INSERT.

    A resolved appearance stores its team + source; an unresolved/conflict appearance
    is still stored (the appearance is real) but carries a fail-closed status and no
    attributed team.

    Exception: a NEW all-zero, zero-out listing is not yet proven to be an appearance.
    Only an official box-score pitching line may create it. Schedule-only and
    unresolved listings fail closed before INSERT. If an official row already exists,
    the daily feed may re-read it because no new appearance can be invented.
    """
    if resolution is None:
        return values
    values = dict(values)
    if (
        resolution.source != SOURCE_BOXSCORE
        and is_all_zero_game_log_values(values)
        and _existing_game_log(values) is None
    ):
        raise UnverifiedZeroOutAppearance(REASON_ZERO_OUT_UNVERIFIED)
    values.update(resolution.to_write_fields())
    return values


def reconcile_on_update(
    log: GameLog,
    resolution: Optional[AppearanceTeamResolution],
    *,
    correction_applied: bool,
) -> Optional[str]:
    """Precedence-aware, non-flapping update of an existing appearance's team.

    Rules (deterministic):
      * A legacy/unattributed row (NULL status) is attributed ONLY when the row is
        genuinely being corrected (``correction_applied``) and the new authority is
        resolved — a pure re-sweep never backfills a legacy row (Step 2 owns that).
      * An already-attributed row is never downgraded by an unresolved authority.
      * The same resolved team is idempotent; a strictly higher-precedence source
        may refresh the source label without a team change.
      * A different resolved team from a HIGHER-precedence source is a governed
        authoritative correction (logged); from a LOWER-precedence source it is
        ignored (no flap); at EQUAL precedence it fails closed as ``conflict``.

    Returns a reason code when the row changed, else None. Never consults
    Pitcher.team_id.
    """
    if resolution is None:
        return None

    stored_status = log.appearance_team_status

    if stored_status is None:
        if correction_applied and resolution.resolved:
            _write(log, resolution)
            return resolution.reason
        return None

    if not resolution.resolved:
        return None

    # The same represented team is idempotent regardless of which official source
    # re-derived it — the attribution never flaps and the row is left untouched.
    if resolution.team_id == log.appearance_team_id:
        return None

    new_prec = _precedence(resolution.source)
    cur_prec = _precedence(log.appearance_team_source)

    if new_prec > cur_prec:
        log.appearance_team_id = resolution.team_id
        log.appearance_team_source = resolution.source
        log.appearance_team_status = STATUS_RESOLVED
        log.appearance_team_reason = REASON_CORRECTED
        return REASON_CORRECTED
    if new_prec < cur_prec:
        return None

    # Equal precedence, different team -> fail closed. A conflicted appearance carries
    # NO silently-selected team id (the stored-state invariant): the prior team is
    # cleared so no aggregation ever trusts it.
    log.appearance_team_id = None
    log.appearance_team_status = STATUS_CONFLICT
    log.appearance_team_source = SOURCE_CONFLICT
    log.appearance_team_reason = REASON_CONFLICT
    return REASON_CONFLICT


def _write(log: GameLog, resolution: AppearanceTeamResolution) -> None:
    fields = resolution.to_write_fields()
    log.appearance_team_id = fields['appearance_team_id']
    log.appearance_team_source = fields['appearance_team_source']
    log.appearance_team_status = fields['appearance_team_status']
    log.appearance_team_reason = fields['appearance_team_reason']


def resolve_appearance_team(game_log) -> AppearanceTeamResolution:
    """Canonical READ accessor for an appearance's represented team.

    The single seam future performance/aggregation work must consume — never a
    re-invented ``Pitcher.team_id`` fallback. Returns the stored authority as a
    resolution: ``resolved`` (with team_id), ``unresolved``, or ``conflict``. A
    legacy row with no stored status reads as ``unresolved`` (team_id None) so it is
    excluded from team-season aggregation until Step 2 backfills it.
    """
    status = getattr(game_log, 'appearance_team_status', None)
    team_id = getattr(game_log, 'appearance_team_id', None)
    source = getattr(game_log, 'appearance_team_source', None)
    reason = getattr(game_log, 'appearance_team_reason', None)
    if status is None:
        return _unresolved()
    if status == STATUS_RESOLVED and team_id is not None:
        return AppearanceTeamResolution(team_id, STATUS_RESOLVED, source, reason)
    if status == STATUS_CONFLICT:
        return AppearanceTeamResolution(None, STATUS_CONFLICT, source, reason or REASON_CONFLICT)
    return AppearanceTeamResolution(None, STATUS_UNRESOLVED, source, reason or REASON_UNRESOLVED)
