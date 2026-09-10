"""Durable execution record for the ONE reviewed official pitching-line repair (2026).

This is not a general job-history table and it is not a second sync-run subsystem. It exists
so a single governed, fingerprint-locked repair can prove — durably, in the database it
mutated — that it ran, what it was approved to do, and what it actually did.

Two properties are enforced at the database rather than by writer discipline:

* ``status`` may only ever be ``completed``. A rolled-back or precondition-failed attempt
  performs no writes at all, so it has nothing to record here; recording it would leave a
  row asserting an execution that never happened. Failed attempts are evidenced by the
  private workflow artifact instead.
* ``approved_manifest_fingerprint`` is UNIQUE. The approval is one-time and exact, so a
  second completed execution of the same approved manifest is impossible even if a second
  operator dispatches the workflow concurrently.

The row is written inside the same transaction as the repair itself and commits with it, so
the ledger and the mutated rows are atomically consistent: either both exist or neither does.
"""

from utils.db import db


class OfficialPitchingLineRepairExecution(db.Model):
    __tablename__ = 'official_pitching_line_repair_executions'

    # The only status a stored row may carry. A repair that did not commit does not appear.
    STATUS_COMPLETED = 'completed'
    STATUSES = (STATUS_COMPLETED,)

    __table_args__ = (
        # One completed execution per approved fingerprint, forever.
        db.UniqueConstraint(
            'approved_manifest_fingerprint',
            name='uq_oplr_executions_approved_fingerprint',
        ),
        db.CheckConstraint(
            "status = 'completed'",
            name='ck_oplr_executions_status_completed',
        ),
        # A committed execution has applied exactly the counts it recorded, and the parts
        # sum to the whole. Enforced here so a miscounted ledger row cannot be stored.
        db.CheckConstraint(
            'identity_action_count >= 0 AND insert_action_count >= 0 '
            'AND update_action_count >= 0 AND total_action_count = '
            '(identity_action_count + insert_action_count + update_action_count)',
            name='ck_oplr_executions_action_counts_reconcile',
        ),
        db.Index('ix_oplr_executions_capability', 'capability'),
        db.Index('ix_oplr_executions_committed_at', 'committed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # Which governed capability executed. Recorded rather than assumed so a future repair
    # capability can never be mistaken for this one.
    capability = db.Column(db.String(120), nullable=False)

    # The fingerprint that was APPROVED for execution, and the fingerprint the planner
    # actually regenerated immediately before the write transaction. They are stored
    # separately and both retained: equality is the gate, and a reviewer must be able to see
    # both values rather than a single value asserting they agreed.
    approved_manifest_fingerprint = db.Column(db.String(64), nullable=False)
    regenerated_manifest_fingerprint = db.Column(db.String(64), nullable=False)

    # The commit the approved plan was generated at, and the commit that applied it.
    planner_git_sha = db.Column(db.String(64), nullable=True)
    apply_git_sha = db.Column(db.String(64), nullable=True)

    season = db.Column(db.Integer, nullable=False)
    as_of_date = db.Column(db.Date, nullable=False)

    # Which accepted defect baseline version governed the plan, and which reviewed amendment
    # was part of that version's definition.
    accepted_baseline_version = db.Column(db.String(16), nullable=False)
    amendment_id = db.Column(db.String(120), nullable=True)

    status = db.Column(db.String(20), nullable=False, default=STATUS_COMPLETED)

    identity_action_count = db.Column(db.Integer, nullable=False)
    insert_action_count = db.Column(db.Integer, nullable=False)
    update_action_count = db.Column(db.Integer, nullable=False)
    total_action_count = db.Column(db.Integer, nullable=False)

    started_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    committed_at = db.Column(db.DateTime, nullable=True)

    # Governed structured evidence. No free-form text, no connection details, no raw official
    # payloads: each is a bounded, deterministic summary object.
    execution_summary = db.Column(db.JSON, nullable=True)
    precondition_summary = db.Column(db.JSON, nullable=True)
    verification_summary = db.Column(db.JSON, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'capability': self.capability,
            'approved_manifest_fingerprint': self.approved_manifest_fingerprint,
            'regenerated_manifest_fingerprint': self.regenerated_manifest_fingerprint,
            'planner_git_sha': self.planner_git_sha,
            'apply_git_sha': self.apply_git_sha,
            'season': self.season,
            'as_of_date': self.as_of_date.isoformat() if self.as_of_date else None,
            'accepted_baseline_version': self.accepted_baseline_version,
            'amendment_id': self.amendment_id,
            'status': self.status,
            'identity_action_count': self.identity_action_count,
            'insert_action_count': self.insert_action_count,
            'update_action_count': self.update_action_count,
            'total_action_count': self.total_action_count,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'committed_at': self.committed_at.isoformat() if self.committed_at else None,
        }

    def __repr__(self):
        return (f'<OfficialPitchingLineRepairExecution id={self.id} '
                f'status={self.status} actions={self.total_action_count}>')
