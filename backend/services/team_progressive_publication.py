"""Progressive per-team Team State Share Artifact publication.

The league-wide dashboard snapshot stays all-or-nothing (it waits for the entire
required slate to be final). This module publishes an individual team's Team State
artifact progressively — after THAT team's own completed game and required evidence
pass the canonical trust gates — so a late game between two other teams cannot block
the teams whose games already ended.

It introduces no second readiness or eligibility engine. A completed game resolves
its two participating teams; each team is evaluated INDEPENDENTLY through the exact
existing single-team path (``resolve_team_readiness_payload`` ->
``gather_team_state_source`` -> ``evaluate_team_state_eligibility`` ->
``build_team_state_payload`` -> ``publish_share_artifact``). The only new input is a
team-scoped trusted source authority — an immutable ``TeamProgressivePublication``
checkpoint whose fail-closed trust verdict is computed from that team's own final-game
evidence, and whose id supplies the artifact's ``source_snapshot_id``. One team may
publish while its opponent refuses for a team-specific trust problem; unfinished
unrelated games are never consulted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError

from models.game_log import GameLog
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.team_progressive_publication import TeamProgressivePublication
from services.share_artifact_generation import (
    OUTCOME_FAILED_CLOSED,
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
    generate_team_state_artifact,
)
from services.team_directory import is_valid_team_id
from services.team_state_source import TeamStateSnapshotAuthority
from utils.db import db


# Single source of truth (model) so the audit request_source the operations read
# filters on cannot drift from the value this service writes.
PROGRESSIVE_REQUEST_SOURCE = TeamProgressivePublication.REQUEST_SOURCE

# Fail-closed source-unavailable reasons (governed, non-sensitive).
REASON_GAME_NOT_FINAL = 'game_not_final'
REASON_LEDGER_INCOMPLETE = 'appearance_ledger_incomplete'
REASON_GAME_NOT_FOUND = 'game_not_found'
REASON_TEAMS_UNRESOLVED = 'participating_teams_unresolved'


@dataclass(frozen=True)
class ProgressiveGameResult:
    """Two-team accounting for one completed-game progressive event."""

    game_pk: int
    game_date: Optional[date]
    attempted: int
    accounted: int
    generated: int
    reused: int
    refused: int
    failed: int
    team_outcomes: dict  # team_id -> outcome code
    unavailable_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'scope': TeamProgressivePublication.SCOPE,
            'trigger_game_pk': self.game_pk,
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'attempted': self.attempted,
            'accounted': self.accounted,
            'generated': self.generated,
            'reused': self.reused,
            'refused': self.refused,
            'failed': self.failed,
            'missing': max(self.attempted - self.accounted, 0),
            'team_outcomes': {str(k): v for k, v in self.team_outcomes.items()},
            'unavailable_reason': self.unavailable_reason,
        }


def _game_rows(game_pk, session):
    return session.query(ScheduledGame).filter(ScheduledGame.game_pk == game_pk).all()


def _participating_team_ids(rows) -> list:
    ids = set()
    for row in rows:
        for candidate in (row.team_id, row.opponent_team_id):
            if candidate is not None and _safe_valid_team(candidate):
                ids.add(int(candidate))
    return sorted(ids)


def _safe_valid_team(team_id) -> bool:
    try:
        return bool(is_valid_team_id(team_id))
    except Exception:
        return False


def _game_is_final(rows) -> bool:
    return bool(rows) and all(row.status_state == ScheduledGame.STATE_FINAL for row in rows)


def _ledger_complete_for_game(game_pk, session) -> bool:
    marker = (
        session.query(PostgameProcessedGame)
        .filter(PostgameProcessedGame.mlb_game_pk == game_pk)
        .first()
    )
    return marker is not None and (
        marker.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED
    )


def _canonical_ledger_digest(rows) -> str:
    """Pure, row-order-independent digest of a game's appearance-ledger rows.

    ``rows`` is any iterable of ``(pitcher_id, pitches_thrown, innings_pitched_outs,
    stat_correction_count)`` tuples. The rows are canonicalized (None coerced to a
    stable sentinel) and SORTED before hashing, so the fingerprint is identical
    regardless of the order the rows are supplied, and it changes iff the
    meaning-bearing content changes. Isolated from the DB so its determinism is
    trivially testable.
    """
    canonical = sorted(
        (
            int(pitcher_id),
            int(pitches) if pitches is not None else -1,
            int(outs) if outs is not None else -1,
            int(corrections) if corrections is not None else 0,
        )
        for pitcher_id, pitches, outs, corrections in rows
    )
    serialized = json.dumps(canonical, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _appearance_ledger_digest(game_pk, session) -> str:
    """Canonical digest of a game's committed appearance ledger.

    Hashes the sorted, meaning-bearing pitching-line fields for the game, so the
    fingerprint is (1) identical regardless of the order the database returns the
    rows, and (2) sensitive to a genuine authoritative box-score correction — a
    changed pitch count, recorded out count, or the per-row stat-correction counter
    all change the digest even when the NUMBER of appearances is unchanged. A bare
    row count would miss such a correction and wrongly reuse the prior checkpoint.
    """
    rows = (
        session.query(
            GameLog.pitcher_id,
            GameLog.pitches_thrown,
            GameLog.innings_pitched_outs,
            GameLog.stat_correction_count,
        )
        .filter(GameLog.mlb_game_pk == game_pk)
        .all()
    )
    return _canonical_ledger_digest(rows)


def _evidence_revision(game_pk, *, game_final, ledger_complete, ledger_digest, data_through) -> str:
    raw = f'{game_pk}:{int(bool(game_final))}:{int(bool(ledger_complete))}:{ledger_digest}:{data_through}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]


def build_team_progressive_checkpoint(
    team_id: int,
    game_pk: int,
    *,
    session=None,
    sync_run_id: Optional[int] = None,
) -> Optional[TeamProgressivePublication]:
    """Build (idempotently) the immutable team-scoped source authority for a team's
    completed game. Fail-closed: the checkpoint is ``trusted`` only when the game is
    final, its appearance ledger/box score is complete, and the participating teams
    resolve. Returns ``None`` only when the game itself cannot be resolved.

    Idempotency: keyed on (team_id, trigger_game_pk, evidence_revision). Re-running
    the same final-game evidence reuses the existing checkpoint (so no duplicate
    artifacts on reconciliation reruns); a genuine authoritative correction changes
    the evidence revision and mints a NEW immutable checkpoint (and a new artifact),
    never rewriting the prior one.
    """
    session = session or db.session
    rows = _game_rows(game_pk, session)
    if not rows:
        return None
    game_date = rows[0].game_date
    team_ids = _participating_team_ids(rows)
    if int(team_id) not in team_ids or len(team_ids) < 2:
        # The team is not a participant, or the two sides did not resolve.
        game_final = _game_is_final(rows)
        ledger_complete = _ledger_complete_for_game(game_pk, session)
        return _persist_checkpoint(
            session, team_id=team_id, game_pk=game_pk, game_date=game_date,
            game_final=game_final, ledger_complete=ledger_complete,
            teams_resolved=False, sync_run_id=sync_run_id,
        )

    game_final = _game_is_final(rows)
    ledger_complete = _ledger_complete_for_game(game_pk, session)
    return _persist_checkpoint(
        session, team_id=team_id, game_pk=game_pk, game_date=game_date,
        game_final=game_final, ledger_complete=ledger_complete,
        teams_resolved=True, sync_run_id=sync_run_id,
    )


def _find_checkpoint(session, *, team_id, game_pk, revision):
    return (
        session.query(TeamProgressivePublication)
        .filter(
            TeamProgressivePublication.team_id == int(team_id),
            TeamProgressivePublication.trigger_game_pk == int(game_pk),
            TeamProgressivePublication.evidence_revision == revision,
        )
        .first()
    )


def _persist_checkpoint(
    session, *, team_id, game_pk, game_date, game_final, ledger_complete,
    teams_resolved, sync_run_id,
) -> TeamProgressivePublication:
    ledger_digest = _appearance_ledger_digest(game_pk, session)
    revision = _evidence_revision(
        game_pk, game_final=game_final, ledger_complete=ledger_complete,
        ledger_digest=ledger_digest, data_through=game_date,
    )
    trusted = bool(game_final and ledger_complete and teams_resolved)
    if not teams_resolved:
        unavailable_reason = REASON_TEAMS_UNRESOLVED
    elif not game_final:
        unavailable_reason = REASON_GAME_NOT_FINAL
    elif not ledger_complete:
        unavailable_reason = REASON_LEDGER_INCOMPLETE
    else:
        unavailable_reason = None

    existing = _find_checkpoint(session, team_id=team_id, game_pk=game_pk, revision=revision)
    if existing is not None:
        return existing

    checkpoint = TeamProgressivePublication(
        team_id=int(team_id),
        trigger_type=TeamProgressivePublication.TRIGGER_GAME_FINAL,
        trigger_game_pk=int(game_pk),
        official_game_date=game_date,
        data_through=game_date,
        availability_reference_date=(game_date + timedelta(days=1)) if game_date else None,
        source_sync_run_id=sync_run_id,
        game_final=game_final,
        ledger_complete=ledger_complete,
        evidence_complete=bool(ledger_complete),
        trusted=trusted,
        unavailable_reason=unavailable_reason,
        evidence_revision=revision,
        status=(
            TeamProgressivePublication.STATUS_TRUSTED
            if trusted
            else TeamProgressivePublication.STATUS_WITHHELD
        ),
    )
    # Insert inside a SAVEPOINT so a concurrent postgame run that inserted the same
    # (team, game, evidence revision) first trips the unique constraint here; we roll
    # back just this savepoint and reuse the winner's checkpoint rather than minting a
    # duplicate. Idempotency is therefore enforced by the database, not merely by the
    # find-first query above (which cannot see an uncommitted concurrent insert).
    try:
        with session.begin_nested():
            session.add(checkpoint)
            session.flush()
    except IntegrityError:
        existing = _find_checkpoint(session, team_id=team_id, game_pk=game_pk, revision=revision)
        if existing is not None:
            return existing
        raise
    return checkpoint


def _checkpoint_subject_key(checkpoint: TeamProgressivePublication) -> str:
    """Self-describing, deterministic source identity stamped onto the artifact.

    Encodes the exact team-progressive source (team, triggering game, evidence
    revision) so the artifact identifies its source WITHOUT dereferencing the
    numeric ``source_snapshot_id`` — the same evidence yields the same key (dedup);
    a genuine correction yields a new key (a new immutable artifact)."""
    return (
        f'{TeamProgressivePublication.SCOPE}:{checkpoint.team_id}:'
        f'{checkpoint.trigger_game_pk}:{checkpoint.evidence_revision}'
    )


def _checkpoint_authority(checkpoint: TeamProgressivePublication) -> TeamStateSnapshotAuthority:
    return TeamStateSnapshotAuthority(
        snapshot_id=checkpoint.id,
        sync_run_id=checkpoint.source_sync_run_id,
        data_through=checkpoint.data_through,
        published_at=checkpoint.published_at,
        unavailable_reason=(
            None if checkpoint.is_trusted
            else (checkpoint.unavailable_reason or 'team_source_untrusted')
        ),
        # Durable source-authority discriminator carried onto the immutable artifact.
        subject_type=TeamProgressivePublication.SCOPE,
        subject_key=_checkpoint_subject_key(checkpoint),
    )


def publish_team_state_for_final_game(
    game_pk: int,
    *,
    session=None,
    actor: Optional[str] = None,
    request_source: str = PROGRESSIVE_REQUEST_SOURCE,
    sync_run_id: Optional[int] = None,
) -> ProgressiveGameResult:
    """Attempt an independent Team State artifact for each of a completed game's two
    teams. Reuses the canonical single-team generation path unchanged; one team may
    publish while the other refuses for a team-specific trust problem. Never consults
    any other (unfinished) game. Accounting: attempted == accounted == number of
    resolved participants (2 for a normal game), missing == 0.
    """
    session = session or db.session
    rows = _game_rows(game_pk, session)
    if not rows:
        return ProgressiveGameResult(
            game_pk=int(game_pk), game_date=None, attempted=0, accounted=0,
            generated=0, reused=0, refused=0, failed=0, team_outcomes={},
            unavailable_reason=REASON_GAME_NOT_FOUND,
        )
    game_date = rows[0].game_date
    team_ids = _participating_team_ids(rows)

    generated = reused = refused = failed = accounted = 0
    outcomes: dict = {}
    for team_id in team_ids:
        # Per-team isolation: the canonical single-team path already fails closed on
        # operational errors (returning failed_closed, never raising), but a team is
        # still evaluated INDEPENDENTLY here so that any unexpected error for one
        # participant is contained and counted as a failure for THAT team without
        # blocking its opponent's publication. One team never brings down the other.
        try:
            checkpoint = build_team_progressive_checkpoint(
                team_id, game_pk, session=session, sync_run_id=sync_run_id,
            )
            if checkpoint is None:
                continue
            authority = _checkpoint_authority(checkpoint)
            result = generate_team_state_artifact(
                team_id,
                requested_date=game_date,
                actor=actor,
                request_source=request_source,
                source_authority=authority,
                session=session,
            )
            outcome = result.outcome
        except Exception:
            # Discard this team's uncommitted work only; the opponent's already
            # committed artifact is durable and untouched.
            session.rollback()
            outcomes[team_id] = OUTCOME_FAILED_CLOSED
            accounted += 1
            failed += 1
            continue
        outcomes[team_id] = outcome
        accounted += 1
        if outcome == OUTCOME_PUBLISHED:
            generated += 1
        elif outcome == OUTCOME_REUSED:
            reused += 1
        elif outcome == OUTCOME_REFUSED:
            refused += 1
        else:
            failed += 1

    return ProgressiveGameResult(
        game_pk=int(game_pk), game_date=game_date, attempted=len(team_ids),
        accounted=accounted, generated=generated, reused=reused, refused=refused,
        failed=failed, team_outcomes=outcomes,
        unavailable_reason=(REASON_TEAMS_UNRESOLVED if len(team_ids) < 2 else None),
    )
