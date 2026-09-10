from utils.db import db
from utils.time import utc_now_naive


class SourceSubject(db.Model):
    """Stable identity for one repeatable external-source request."""

    __tablename__ = 'source_subjects'
    __table_args__ = (
        db.UniqueConstraint('identity_key', name='uq_source_subjects_identity_key'),
        db.Index(
            'ix_source_subjects_provider_domain',
            'provider',
            'source_domain',
            'id',
        ),
        db.Index(
            'ix_source_subjects_subject',
            'subject_type',
            'subject_key',
            'id',
        ),
        db.Index('ix_source_subjects_baseball_date', 'baseball_date', 'id'),
        db.Index('ix_source_subjects_request_identity', 'request_identity'),
    )

    id = db.Column(db.Integer, primary_key=True)
    identity_key = db.Column(db.String(64), nullable=False)
    provider = db.Column(db.String(40), nullable=False)
    source_domain = db.Column(db.String(40), nullable=False)
    endpoint = db.Column(db.String(255), nullable=False)
    subject_type = db.Column(db.String(40), nullable=False)
    subject_key = db.Column(db.String(255), nullable=False)
    request_identity = db.Column(db.String(64), nullable=False)
    request_schema_version = db.Column(db.Integer, nullable=False)
    request_parameters = db.Column(db.JSON, nullable=False)
    baseball_date = db.Column(db.Date)
    range_start = db.Column(db.Date)
    range_end = db.Column(db.Date)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )


class SourcePayloadArtifact(db.Model):
    """Content-addressed JSON retained once across source observations."""

    __tablename__ = 'source_payload_artifacts'
    __table_args__ = (
        db.UniqueConstraint(
            'content_hash',
            'payload_schema_version',
            'payload_kind',
            name='uq_source_payload_artifacts_content_schema_kind',
        ),
        db.Index('ix_source_payload_artifacts_content_hash', 'content_hash'),
    )

    id = db.Column(db.Integer, primary_key=True)
    content_hash = db.Column(db.String(64), nullable=False)
    hash_algorithm = db.Column(db.String(20), nullable=False)
    payload_schema_version = db.Column(db.Integer, nullable=False)
    payload_kind = db.Column(db.String(30), nullable=False)
    storage_format = db.Column(db.String(20), nullable=False, default='json')
    payload_json = db.Column(db.JSON, nullable=False)
    payload_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class SourceObservation(db.Model):
    """Immutable material version observed for a stable source subject."""

    __tablename__ = 'source_observations'
    __table_args__ = (
        db.UniqueConstraint(
            'source_subject_id',
            'version_number',
            name='uq_source_observations_subject_version',
        ),
        db.UniqueConstraint('dedupe_key', name='uq_source_observations_dedupe_key'),
        db.Index(
            'ix_source_observations_subject_latest',
            'source_subject_id',
            'version_number',
        ),
        db.Index(
            'ix_source_observations_subject_authoritative',
            'source_subject_id',
            'is_authoritative',
            'version_number',
        ),
        db.Index('ix_source_observations_fingerprint', 'fingerprint'),
        db.Index('ix_source_observations_outcome_created', 'outcome', 'created_at'),
        db.Index('ix_source_observations_predecessor', 'predecessor_observation_id'),
        db.Index('ix_source_observations_sync_run', 'sync_run_id', 'id'),
        db.Index('ix_source_observations_sync_job', 'sync_job_id', 'id'),
        db.CheckConstraint(
            "completeness IN ('complete', 'partial', 'unknown')",
            name='ck_source_observations_completeness',
        ),
        db.CheckConstraint(
            "outcome IN ('new', 'changed', 'corrected', 'partial', 'empty_valid')",
            name='ck_source_observations_outcome',
        ),
        db.CheckConstraint(
            'version_number > 0 AND payload_schema_version > 0',
            name='ck_source_observations_version_bounds',
        ),
        db.CheckConstraint(
            'record_count IS NULL OR record_count >= 0',
            name='ck_source_observations_record_count',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    source_subject_id = db.Column(
        db.Integer,
        db.ForeignKey('source_subjects.id', ondelete='RESTRICT'),
        nullable=False,
    )
    version_number = db.Column(db.Integer, nullable=False)
    dedupe_key = db.Column(db.String(64), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    fingerprint_algorithm = db.Column(db.String(20), nullable=False)
    fingerprint_version = db.Column(db.String(40), nullable=False)
    payload_schema_version = db.Column(db.Integer, nullable=False)
    payload_artifact_id = db.Column(
        db.Integer,
        db.ForeignKey('source_payload_artifacts.id', ondelete='RESTRICT'),
    )
    completeness = db.Column(db.String(20), nullable=False)
    outcome = db.Column(db.String(20), nullable=False)
    is_change = db.Column(db.Boolean, nullable=False, default=False)
    is_authoritative = db.Column(db.Boolean, nullable=False, default=False)
    record_count = db.Column(db.Integer)
    source_updated_at = db.Column(db.DateTime)
    source_revision = db.Column(db.String(160))
    source_etag = db.Column(db.String(255))
    predecessor_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='SET NULL'),
    )
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'))
    sync_job_id = db.Column(db.Integer, db.ForeignKey('sync_jobs.id'))
    observed_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    subject = db.relationship(
        'SourceSubject',
        backref=db.backref('observations', lazy='dynamic'),
        foreign_keys=[source_subject_id],
    )
    payload_artifact = db.relationship('SourcePayloadArtifact')
    predecessor = db.relationship(
        'SourceObservation',
        remote_side=[id],
        backref=db.backref('successors', lazy='dynamic'),
        foreign_keys=[predecessor_observation_id],
    )


class SourceFetchAttempt(db.Model):
    """Compact evidence for one external request, distinct from job attempts."""

    __tablename__ = 'source_fetch_attempts'
    __table_args__ = (
        db.Index(
            'ix_source_fetch_attempts_subject_started',
            'source_subject_id',
            'started_at',
        ),
        db.Index('ix_source_fetch_attempts_status_started', 'status', 'started_at'),
        db.Index('ix_source_fetch_attempts_observation', 'source_observation_id'),
        db.Index('ix_source_fetch_attempts_sync_run', 'sync_run_id', 'id'),
        db.Index('ix_source_fetch_attempts_sync_job', 'sync_job_id', 'id'),
        db.CheckConstraint(
            "status IN ('succeeded', 'partial', 'failed')",
            name='ck_source_fetch_attempts_status',
        ),
        db.CheckConstraint(
            "completeness IN ('complete', 'partial', 'unknown', 'failed')",
            name='ck_source_fetch_attempts_completeness',
        ),
        db.CheckConstraint(
            "outcome IN ('new', 'unchanged', 'changed', 'corrected', "
            "'partial', 'empty_valid', 'failed')",
            name='ck_source_fetch_attempts_outcome',
        ),
        db.CheckConstraint(
            'http_retry_count >= 0 AND '
            '(duration_ms IS NULL OR duration_ms >= 0) AND '
            '(response_bytes IS NULL OR response_bytes >= 0) AND '
            '(record_count IS NULL OR record_count >= 0)',
            name='ck_source_fetch_attempts_count_bounds',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    source_subject_id = db.Column(
        db.Integer,
        db.ForeignKey('source_subjects.id', ondelete='RESTRICT'),
        nullable=False,
    )
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='SET NULL'),
    )
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'))
    sync_job_id = db.Column(db.Integer, db.ForeignKey('sync_jobs.id'))
    status = db.Column(db.String(20), nullable=False)
    outcome = db.Column(db.String(20), nullable=False)
    completeness = db.Column(db.String(20), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=False)
    http_status = db.Column(db.Integer)
    http_retry_count = db.Column(db.Integer, nullable=False, default=0)
    duration_ms = db.Column(db.Integer)
    response_bytes = db.Column(db.Integer)
    record_count = db.Column(db.Integer)
    error_class = db.Column(db.String(80))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    subject = db.relationship('SourceSubject')
    observation = db.relationship('SourceObservation')
