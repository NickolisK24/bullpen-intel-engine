from utils.db import db
from utils.time import utc_now_naive


class GameIngestionWorkItem(db.Model):
    """Durable game-level ingestion work state (Foundation 3C).

    The daily publication-critical appearance lane's unit of work is ONE GAME,
    not one pitcher. This table is that lane's checkpoint: it records which
    governed games have been planned, attempted, and fully reconciled, so an
    interrupted run resumes from unresolved games instead of restarting the
    season from zero.

    Identity is ``mlb_game_pk`` — one work item per MLB game. A game that is
    re-planned because its source evidence changed reuses its row (moving back
    to ``planned`` with a new ``candidate_reason``), so replay can never create
    a second work identity for the same game.

    ``postgame_processed_games`` remains the postgame refresh lane's own marker
    and is untouched by this table. This one owns the *daily critical lane's*
    completion contract: expected-vs-reconciled appearance counts, the observed
    source revision, and the completion proof the publication gate reads.
    """

    __tablename__ = 'game_ingestion_work_items'

    # ── Status vocabulary ─────────────────────────────────────────────────────
    STATUS_PLANNED = 'planned'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_RETRYABLE_FAILURE = 'retryable_failure'
    STATUS_TERMINAL_FAILURE = 'terminal_failure'
    STATUS_SUPERSEDED = 'superseded'

    STATUSES = (
        STATUS_PLANNED,
        STATUS_IN_PROGRESS,
        STATUS_COMPLETED,
        STATUS_RETRYABLE_FAILURE,
        STATUS_TERMINAL_FAILURE,
        STATUS_SUPERSEDED,
    )

    # A game whose work is finished at its currently-known source revision.
    RESOLVED_STATUSES = (STATUS_COMPLETED, STATUS_SUPERSEDED)
    # A game the next run must pick back up.
    UNRESOLVED_STATUSES = (
        STATUS_PLANNED,
        STATUS_IN_PROGRESS,
        STATUS_RETRYABLE_FAILURE,
    )

    # ── Candidate reason vocabulary ───────────────────────────────────────────
    REASON_NEWLY_FINAL = 'newly_final'
    REASON_FINALITY_CHANGED = 'finality_changed'
    REASON_CORRECTED_FINAL = 'corrected_final'
    REASON_INCOMPLETE_PRIOR_ATTEMPT = 'incomplete_prior_attempt'
    REASON_EXPLICIT_REPAIR = 'explicit_repair'
    REASON_BACKFILL = 'backfill'

    CANDIDATE_REASONS = (
        REASON_NEWLY_FINAL,
        REASON_FINALITY_CHANGED,
        REASON_CORRECTED_FINAL,
        REASON_INCOMPLETE_PRIOR_ATTEMPT,
        REASON_EXPLICIT_REPAIR,
        REASON_BACKFILL,
    )

    # ── Criticality vocabulary ────────────────────────────────────────────────
    CRITICALITY_PUBLICATION_CRITICAL = 'publication_critical'
    CRITICALITY_BEST_EFFORT = 'best_effort'
    CRITICALITY_UNKNOWN = 'unknown'

    CRITICALITIES = (
        CRITICALITY_PUBLICATION_CRITICAL,
        CRITICALITY_BEST_EFFORT,
        CRITICALITY_UNKNOWN,
    )

    __table_args__ = (
        db.UniqueConstraint(
            'mlb_game_pk', name='uq_game_ingestion_work_items_game_pk',
        ),
        db.Index(
            'ix_game_ingestion_work_items_status_date',
            'status', 'represented_date',
        ),
        db.Index(
            'ix_game_ingestion_work_items_represented_date', 'represented_date',
        ),
        db.Index(
            'ix_game_ingestion_work_items_criticality_status',
            'criticality', 'status',
        ),
        db.CheckConstraint(
            "status IN ('planned', 'in_progress', 'completed', "
            "'retryable_failure', 'terminal_failure', 'superseded')",
            name='ck_game_ingestion_work_items_status',
        ),
        db.CheckConstraint(
            "criticality IN ('publication_critical', 'best_effort', 'unknown')",
            name='ck_game_ingestion_work_items_criticality',
        ),
        db.CheckConstraint(
            "candidate_reason IN ('newly_final', 'finality_changed', "
            "'corrected_final', 'incomplete_prior_attempt', 'explicit_repair', "
            "'backfill')",
            name='ck_game_ingestion_work_items_candidate_reason',
        ),
        # A completed work item is a completion PROOF, not a label: it must
        # carry a completion timestamp, a determined expectation, and an exact
        # reconciliation of that expectation. Enforced at the database so a
        # miscounted or optimistic writer cannot fabricate completeness.
        db.CheckConstraint(
            "status <> 'completed' OR ("
            "completed_at IS NOT NULL AND rows_expected IS NOT NULL "
            "AND rows_reconciled = rows_expected AND rows_expected > 0)",
            name='ck_game_ingestion_work_items_completion_proof',
        ),
        db.CheckConstraint(
            'attempt_count >= 0 AND rows_reconciled >= 0 '
            'AND (rows_expected IS NULL OR rows_expected >= 0)',
            name='ck_game_ingestion_work_items_counts_nonnegative',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    # ── Work identity ─────────────────────────────────────────────────────────
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    represented_date = db.Column(db.Date, nullable=False)
    game_date = db.Column(db.Date, nullable=True)
    game_type = db.Column(db.String(2), nullable=True)
    home_team_id = db.Column(db.Integer, nullable=True)
    away_team_id = db.Column(db.Integer, nullable=True)
    game_datetime = db.Column(db.DateTime, nullable=True)  # naive UTC start

    # ── Plan ──────────────────────────────────────────────────────────────────
    candidate_reason = db.Column(db.String(40), nullable=False)
    criticality = db.Column(db.String(30), nullable=False)
    finality_state = db.Column(db.String(30), nullable=True)
    source_authority = db.Column(db.String(60), nullable=True)

    # ── Execution state ───────────────────────────────────────────────────────
    status = db.Column(db.String(30), nullable=False, default=STATUS_PLANNED)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    first_attempted_at = db.Column(db.DateTime, nullable=True)
    last_attempted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_class = db.Column(db.String(60), nullable=True)

    # ── Reconciliation evidence ───────────────────────────────────────────────
    # ``source_revision`` is the observed appearance-set fingerprint for the
    # game (see services/game_appearance_extraction.py). MLB publishes no
    # boxscore revision number, so the marker is derived from the canonical
    # extracted fields themselves — an observed-content marker, never an
    # invented source semantic.
    source_revision = db.Column(db.String(64), nullable=True)
    rows_expected = db.Column(db.Integer, nullable=True)
    rows_reconciled = db.Column(db.Integer, nullable=False, default=0)
    relief_rows_reconciled = db.Column(db.Integer, nullable=False, default=0)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    completion_proof = db.Column(db.JSON, nullable=True)

    sync_run_id = db.Column(
        db.Integer, db.ForeignKey('sync_runs.id'), nullable=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )

    @property
    def resolved(self) -> bool:
        return self.status in self.RESOLVED_STATUSES

    def to_dict(self):
        return {
            'mlb_game_pk': self.mlb_game_pk,
            'represented_date': (
                self.represented_date.isoformat() if self.represented_date else None
            ),
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'game_type': self.game_type,
            'home_team_id': self.home_team_id,
            'away_team_id': self.away_team_id,
            'game_datetime': (
                self.game_datetime.isoformat() if self.game_datetime else None
            ),
            'candidate_reason': self.candidate_reason,
            'criticality': self.criticality,
            'finality_state': self.finality_state,
            'source_authority': self.source_authority,
            'status': self.status,
            'attempt_count': self.attempt_count or 0,
            'first_attempted_at': (
                self.first_attempted_at.isoformat() if self.first_attempted_at else None
            ),
            'last_attempted_at': (
                self.last_attempted_at.isoformat() if self.last_attempted_at else None
            ),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_class': self.error_class,
            'source_revision': self.source_revision,
            'rows_expected': self.rows_expected,
            'rows_reconciled': self.rows_reconciled or 0,
            'relief_rows_reconciled': self.relief_rows_reconciled or 0,
            'correction_count': self.correction_count or 0,
            'completion_proof': self.completion_proof,
            'sync_run_id': self.sync_run_id,
        }

    def __repr__(self):
        return (
            f'<GameIngestionWorkItem game_pk={self.mlb_game_pk} '
            f'date={self.represented_date} status={self.status}>'
        )
