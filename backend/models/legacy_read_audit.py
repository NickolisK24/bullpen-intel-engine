from utils.db import db
from utils.time import utc_now_naive


class LegacyReadDivergence(db.Model):
    __tablename__ = 'legacy_read_divergences'
    __correction_policy_name__ = 'legacy_read_divergence_corrections'
    __correction_identity_fields__ = (
        'subject_type',
        'subject_id',
        'product_date',
        'category',
    )
    __correction_sensitive_fields__ = (
        'subject_type',
        'subject_id',
        'product_date',
        'category',
        'is_material',
        'escalation_state',
        'legacy_capture',
        'read_capture',
        'comparison_basis',
        'notes',
        'source',
        'sync_run_id',
        'last_corrected_at',
        'correction_count',
        'correction_source',
    )

    SUBJECT_PITCHER_DAY = 'pitcher_day'
    SUBJECT_TEAM_DAY = 'team_day'

    ESCALATION_RECORDED = 'recorded'
    ESCALATION_RECOMMENDED = 'escalation_recommended'

    CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING = 'legacy_label_present_read_missing'
    CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING = 'read_present_legacy_label_missing'
    CATEGORY_ACTIONABLE_ON_DEGRADED_READ = 'legacy_actionable_label_on_degraded_read'
    CATEGORY_CONFIDENT_ON_STALE_INPUTS = 'legacy_confident_on_stale_inputs'
    CATEGORY_STATE_CONTRADICTS_FACT = 'legacy_state_contradicts_stored_fact'
    CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ = 'legacy_team_aggregate_on_degraded_team_read'
    CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION = 'legacy_team_count_contradicts_composition'

    CATEGORY_CODES = (
        CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING,
        CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING,
        CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
        CATEGORY_CONFIDENT_ON_STALE_INPUTS,
        CATEGORY_STATE_CONTRADICTS_FACT,
        CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ,
        CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION,
    )

    __table_args__ = (
        db.UniqueConstraint(
            'subject_type',
            'subject_id',
            'product_date',
            'category',
            name='uq_legacy_read_divergences_subject_date_category',
        ),
        db.CheckConstraint(
            "subject_type IN ('pitcher_day', 'team_day')",
            name='ck_legacy_read_divergences_subject_type',
        ),
        db.CheckConstraint(
            "escalation_state IN ('recorded', 'escalation_recommended')",
            name='ck_legacy_read_divergences_escalation_state',
        ),
        db.CheckConstraint(
            "category IN ("
            "'legacy_label_present_read_missing',"
            "'read_present_legacy_label_missing',"
            "'legacy_actionable_label_on_degraded_read',"
            "'legacy_confident_on_stale_inputs',"
            "'legacy_state_contradicts_stored_fact',"
            "'legacy_team_aggregate_on_degraded_team_read',"
            "'legacy_team_count_contradicts_composition'"
            ")",
            name='ck_legacy_read_divergences_category',
        ),
        db.Index(
            'ix_legacy_read_divergences_subject_date',
            'subject_type',
            'product_date',
        ),
        db.Index(
            'ix_legacy_read_divergences_category',
            'category',
            'product_date',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    subject_type = db.Column(db.String(40), nullable=False)
    subject_id = db.Column(db.String(80), nullable=False)
    product_date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(80), nullable=False)
    is_material = db.Column(db.Boolean, nullable=False, default=False)
    escalation_state = db.Column(
        db.String(40),
        nullable=False,
        default=ESCALATION_RECORDED,
    )
    legacy_capture = db.Column(db.JSON, nullable=False)
    read_capture = db.Column(db.JSON, nullable=False)
    comparison_basis = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=False)

    source = db.Column(db.String(100), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_corrected_at = db.Column(db.DateTime)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    correction_source = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'subject_type': self.subject_type,
            'subject_id': self.subject_id,
            'product_date': _iso(self.product_date),
            'category': self.category,
            'is_material': bool(self.is_material),
            'escalation_state': self.escalation_state,
            'legacy_capture': dict(self.legacy_capture or {}),
            'read_capture': dict(self.read_capture or {}),
            'comparison_basis': self.comparison_basis,
            'notes': self.notes,
            'source': self.source,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


class LegacyReadAuditRun(db.Model):
    __tablename__ = 'legacy_read_audit_runs'
    __correction_policy_name__ = 'legacy_read_audit_run_corrections'
    __correction_identity_fields__ = ('product_date', 'subject_type')
    __correction_sensitive_fields__ = (
        'product_date',
        'subject_type',
        'subjects_compared',
        'aligned_count',
        'divergence_count_by_category',
        'skipped_count',
        'run_status',
        'structural_findings',
        'source',
        'sync_run_id',
    )

    SUBJECT_PITCHER_DAY = 'pitcher_day'
    SUBJECT_TEAM_DAY = 'team_day'

    STATUS_COMPLETED = 'completed'
    STATUS_SKIPPED_READS_MISSING = 'skipped_reads_missing'
    STATUS_SKIPPED_LEGACY_MISSING = 'skipped_legacy_missing'

    __table_args__ = (
        db.UniqueConstraint(
            'product_date',
            'subject_type',
            name='uq_legacy_read_audit_runs_date_subject',
        ),
        db.CheckConstraint(
            "subject_type IN ('pitcher_day', 'team_day')",
            name='ck_legacy_read_audit_runs_subject_type',
        ),
        db.CheckConstraint(
            "run_status IN ('completed', 'skipped_reads_missing', 'skipped_legacy_missing')",
            name='ck_legacy_read_audit_runs_status',
        ),
        db.Index('ix_legacy_read_audit_runs_date', 'product_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_date = db.Column(db.Date, nullable=False)
    subject_type = db.Column(db.String(40), nullable=False)
    subjects_compared = db.Column(db.Integer, nullable=False, default=0)
    aligned_count = db.Column(db.Integer, nullable=False, default=0)
    divergence_count_by_category = db.Column(db.JSON, nullable=False)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    run_status = db.Column(db.String(40), nullable=False)
    structural_findings = db.Column(db.JSON, nullable=False)

    source = db.Column(db.String(100), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'product_date': _iso(self.product_date),
            'subject_type': self.subject_type,
            'subjects_compared': self.subjects_compared or 0,
            'aligned_count': self.aligned_count or 0,
            'divergence_count_by_category': dict(
                self.divergence_count_by_category or {}
            ),
            'skipped_count': self.skipped_count or 0,
            'run_status': self.run_status,
            'structural_findings': list(self.structural_findings or []),
            'source': self.source,
            'sync_run_id': self.sync_run_id,
            'created_at': _iso(self.created_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
