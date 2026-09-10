from utils.db import db
from utils.time import utc_now_naive


class SyncRun(db.Model):
    __tablename__ = 'sync_runs'

    __table_args__ = (
        db.Index('ix_sync_runs_started_at', 'started_at'),
        db.Index('ix_sync_runs_status_completed', 'status', 'completed_at'),
        db.Index('ix_sync_runs_type_started', 'run_type', 'started_at'),
        db.Index('ix_sync_runs_trigger_type', 'trigger_type'),
        db.Index('ix_sync_runs_baseball_date', 'baseball_date'),
        db.Index('ix_sync_runs_correlation_id', 'correlation_id'),
        db.Index('ix_sync_runs_parent', 'parent_sync_run_id'),
        db.Index('ix_sync_runs_source_domain', 'source_domain'),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Name of the sync job that produced this row. Defaults to the combined
    # daily refresh; lets pipeline observability group runs by job.
    job_name = db.Column(db.String(50), nullable=False, default='daily_sync')
    run_type = db.Column(db.String(50), nullable=True)
    trigger_type = db.Column(db.String(40), nullable=True)
    baseball_date = db.Column(db.Date, nullable=True)
    source_domain = db.Column(db.String(40), nullable=True)
    parent_sync_run_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_runs.id', ondelete='SET NULL'),
        nullable=True,
    )
    correlation_id = db.Column(db.String(36), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    # completed_at is the spec's "finished_at" (kept under its established name
    # for backward compatibility with existing callers and tests).
    completed_at = db.Column(db.DateTime)
    # status is one of: running / success / partial / failed.
    status = db.Column(db.String(20), nullable=False, default='running')
    # Pipeline stage reached by this run. Failed runs also carry failed_stage.
    stage = db.Column(db.String(50), nullable=False, default='started')
    failed_stage = db.Column(db.String(50))
    published_dashboard_snapshot_id = db.Column(db.Integer, nullable=True)
    publication_id = db.Column(db.String(120), nullable=True)
    source = db.Column(db.String(30), nullable=False, default='manual')

    latest_game_date = db.Column(db.Date)
    latest_workload_date = db.Column(db.Date)
    latest_fatigue_calculated_at = db.Column(db.DateTime)

    records_processed = db.Column(db.Integer, default=0)
    # Number of records that could not be processed and were dead-lettered.
    records_failed = db.Column(db.Integer, default=0)
    new_logs_added = db.Column(db.Integer, default=0)
    pitchers_updated = db.Column(db.Integer, default=0)
    errors = db.Column(db.Integer, default=0)
    # MLB API calls made and retries consumed during the run (from the client
    # metrics accumulator) — pipeline observability for retry pressure.
    api_calls_made = db.Column(db.Integer, default=0)
    retries_used = db.Column(db.Integer, default=0)
    source_reads = db.Column(db.Integer, nullable=False, default=0)
    source_changes = db.Column(db.Integer, nullable=False, default=0)
    canonical_mutations = db.Column(db.Integer, nullable=False, default=0)
    affected_games = db.Column(db.Integer, nullable=False, default=0)
    affected_teams = db.Column(db.Integer, nullable=False, default=0)
    affected_pitchers = db.Column(db.Integer, nullable=False, default=0)
    downstream_work_created = db.Column(db.Integer, nullable=False, default=0)
    warnings_count = db.Column(db.Integer, nullable=False, default=0)
    zero_mutation = db.Column(db.Boolean, nullable=True)
    outcome_json = db.Column(db.JSON, nullable=True)
    # error_message is the spec's "error_summary" (kept under its established
    # name for backward compatibility).
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    parent = db.relationship(
        'SyncRun',
        remote_side=[id],
        foreign_keys=[parent_sync_run_id],
        backref=db.backref('children', passive_deletes=True),
    )
    scopes = db.relationship(
        'SyncRunScope',
        back_populates='sync_run',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='SyncRunScope.id',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'job_name': self.job_name,
            'run_type': self.run_type,
            'trigger_type': self.trigger_type,
            'baseball_date': self.baseball_date.isoformat() if self.baseball_date else None,
            'source_domain': self.source_domain,
            'parent_sync_run_id': self.parent_sync_run_id,
            'correlation_id': self.correlation_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            # Spec-facing alias so consumers can read either name.
            'finished_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status,
            'stage': self.stage,
            'failed_stage': self.failed_stage,
            'published_dashboard_snapshot_id': self.published_dashboard_snapshot_id,
            'publication_id': self.publication_id,
            'source': self.source,
            'latest_game_date': self.latest_game_date.isoformat() if self.latest_game_date else None,
            'latest_workload_date': self.latest_workload_date.isoformat() if self.latest_workload_date else None,
            'latest_fatigue_calculated_at': self.latest_fatigue_calculated_at.isoformat() if self.latest_fatigue_calculated_at else None,
            'records_processed': self.records_processed or 0,
            'records_failed': self.records_failed or 0,
            'new_logs_added': self.new_logs_added or 0,
            'pitchers_updated': self.pitchers_updated or 0,
            'errors': self.errors or 0,
            'api_calls_made': self.api_calls_made or 0,
            'retries_used': self.retries_used or 0,
            'source_reads': self.source_reads or 0,
            'source_changes': self.source_changes or 0,
            'canonical_mutations': self.canonical_mutations or 0,
            'affected_games': self.affected_games or 0,
            'affected_teams': self.affected_teams or 0,
            'affected_pitchers': self.affected_pitchers or 0,
            'downstream_work_created': self.downstream_work_created or 0,
            'warnings_count': self.warnings_count or 0,
            'zero_mutation': self.zero_mutation,
            'outcome_json': self.outcome_json,
            'scopes': [scope.to_dict() for scope in self.scopes],
            'error_message': self.error_message,
            'error_summary': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SyncRunScope(db.Model):
    __tablename__ = 'sync_run_scopes'

    __table_args__ = (
        db.UniqueConstraint(
            'sync_run_id',
            'scope_type',
            'scope_key',
            name='uq_sync_run_scopes_run_type_key',
        ),
        db.Index(
            'ix_sync_run_scopes_type_key_run',
            'scope_type',
            'scope_key',
            'sync_run_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    sync_run_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_runs.id', ondelete='CASCADE'),
        nullable=False,
    )
    scope_type = db.Column(db.String(30), nullable=False)
    scope_key = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    sync_run = db.relationship('SyncRun', back_populates='scopes')

    def to_dict(self):
        return {
            'scope_type': self.scope_type,
            'scope_key': self.scope_key,
        }
