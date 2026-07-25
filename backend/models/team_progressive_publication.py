"""Durable team-scoped source authority for progressive Team State publication
(Share Cards — progressive team publication).

The league-wide dashboard snapshot remains all-or-nothing: it publishes only when
the ENTIRE required slate is final. But an individual Team State Share Artifact may
publish progressively after that team's OWN completed game and required evidence
pass the canonical trust gates — a late game between two other teams must not block
it. Progressive artifacts therefore cannot use a (pending) league snapshot as their
source authority. This immutable checkpoint IS that team-scoped source authority:

* it exists BEFORE any league snapshot for the slate,
* its ``id`` supplies the artifact's non-null ``source_snapshot_id`` (the artifact
  provenance column has no FK to ``dashboard_snapshots`` — it records "the trusted
  source that authorized this artifact", which for a progressive artifact is this
  checkpoint, not a league snapshot),
* it records exactly which completed game and evidence authorized publication, so
  every progressive artifact is durably reproducible and inspectable, and
* it carries the fail-closed trust verdict (``trusted`` / ``unavailable_reason``)
  computed from THAT team's own final-game evidence — never from the league slate.

It introduces no second readiness/eligibility engine and no second snapshot
platform; it is a small provenance record consumed by the existing single-team
generation path. The league ``dashboard_snapshots`` table and its gates are
unchanged.
"""

from models.share_artifact import SUBJECT_TYPE_TEAM_PROGRESSIVE
from utils.db import db
from utils.time import utc_now_naive


class TeamProgressivePublication(db.Model):
    __tablename__ = 'team_progressive_publications'

    # Publication scope marker carried onto the artifact (subject_type) so the
    # operations read model and public provenance can distinguish a team-progressive
    # event from a league-batch artifact durably — it is the SAME value the artifact
    # stamps into its immutable identity contract, so the two can never drift.
    SCOPE = SUBJECT_TYPE_TEAM_PROGRESSIVE

    # request_source recorded on every progressive generation audit, so the
    # league-scoped operations coverage read can exclude progressive attempts even
    # if a checkpoint id numerically collides with a league snapshot id.
    REQUEST_SOURCE = 'progressive_game_final'

    # Trigger types. Game-final is the primary progressive trigger; the checkpoint
    # is deliberately general so an approved team-scoped reconciliation event
    # (e.g. morning full reconciliation) can reuse it without a second structure.
    TRIGGER_GAME_FINAL = 'game_final'

    STATUS_TRUSTED = 'trusted'
    STATUS_WITHHELD = 'withheld'

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('trusted', 'withheld')",
            name='ck_team_progressive_status',
        ),
        # Idempotency is DB-enforced, not merely query-enforced: a team's completed
        # game at a given evidence revision maps to exactly one checkpoint. Two
        # concurrent postgame runs racing to publish the same final game cannot both
        # insert — the loser hits this constraint, rolls back its savepoint, and
        # reuses the winner's checkpoint, so no duplicate checkpoint (and therefore
        # no duplicate artifact) is ever minted.
        db.UniqueConstraint(
            'team_id', 'trigger_game_pk', 'evidence_revision',
            name='uq_team_progressive_team_game_revision',
        ),
        db.Index('ix_team_progressive_team', 'team_id'),
        db.Index('ix_team_progressive_game', 'trigger_game_pk'),
        db.Index('ix_team_progressive_team_game', 'team_id', 'trigger_game_pk'),
        db.Index('ix_team_progressive_created', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)

    team_id = db.Column(db.Integer, nullable=False)
    trigger_type = db.Column(db.String(40), nullable=False)
    # Non-null for a game-driven checkpoint; null is reserved for a future approved
    # non-game team-scoped reconciliation trigger.
    trigger_game_pk = db.Column(db.Integer, nullable=True)
    official_game_date = db.Column(db.Date, nullable=True)

    # Team-scoped freshness anchor: the data these inputs describe, and the
    # canonical next-availability reference. NOT the global max game date.
    data_through = db.Column(db.Date, nullable=False)
    availability_reference_date = db.Column(db.Date, nullable=True)
    source_sync_run_id = db.Column(db.Integer, nullable=True)

    # Fail-closed trust verdict, computed from THIS team's own final-game evidence.
    game_final = db.Column(db.Boolean, nullable=False, default=False)
    ledger_complete = db.Column(db.Boolean, nullable=False, default=False)
    evidence_complete = db.Column(db.Boolean, nullable=False, default=False)
    trusted = db.Column(db.Boolean, nullable=False, default=False)
    # Governed, non-sensitive reason the source is not trusted (null when trusted).
    unavailable_reason = db.Column(db.String(80), nullable=True)

    # Idempotency / corrections: a deterministic fingerprint of the authoritative
    # evidence. Re-running the same final game reuses the same checkpoint; a genuine
    # authoritative correction changes this and mints a new immutable checkpoint (and
    # therefore a new immutable artifact), never rewriting the prior one.
    evidence_revision = db.Column(db.String(80), nullable=True)

    status = db.Column(db.String(20), nullable=False, default=STATUS_WITHHELD)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    # ----------------------------------------------------------------------
    # TeamStateSnapshotAuthority-compatible surface. The existing single-team
    # generation path reads .snapshot_id / .sync_run_id / .data_through /
    # .published_at / and a trust verdict; this checkpoint answers that contract so
    # generate_team_state_artifact can consume it with no readiness/eligibility fork.
    # ----------------------------------------------------------------------
    @property
    def snapshot_id(self):
        return self.id

    @property
    def sync_run_id(self):
        return self.source_sync_run_id

    @property
    def published_at(self):
        return self.created_at if self.trusted else None

    @property
    def is_present(self) -> bool:
        return self.id is not None

    @property
    def is_trusted(self) -> bool:
        return bool(self.trusted) and self.unavailable_reason is None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'scope': self.SCOPE,
            'team_id': self.team_id,
            'trigger_type': self.trigger_type,
            'trigger_game_pk': self.trigger_game_pk,
            'official_game_date': _iso(self.official_game_date),
            'data_through': _iso(self.data_through),
            'availability_reference_date': _iso(self.availability_reference_date),
            'source_sync_run_id': self.source_sync_run_id,
            'game_final': self.game_final,
            'ledger_complete': self.ledger_complete,
            'evidence_complete': self.evidence_complete,
            'trusted': self.trusted,
            'unavailable_reason': self.unavailable_reason,
            'evidence_revision': self.evidence_revision,
            'status': self.status,
            'created_at': _iso(self.created_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
