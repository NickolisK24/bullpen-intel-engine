from utils.db import db
from utils.time import utc_now_naive


class ComposedRead(db.Model):
    __tablename__ = 'composed_reads'
    __correction_policy_name__ = 'composed_read_corrections'
    __correction_identity_fields__ = ('read_key',)
    __correction_sensitive_fields__ = (
        'read_key',
        'read_type',
        'read_version',
        'subject_type',
        'subject_id',
        'subject_key',
        'product_date',
        'completeness_state',
        'reason_codes',
        'limitations',
        'component_summary',
        'posture',
        'source',
        'sync_run_id',
        'last_corrected_at',
        'correction_count',
        'correction_source',
        'recompute_status',
        'recompute_reason_codes',
        'invalidated_at',
        'invalidated_by_source_table',
        'invalidated_by_source_pk',
        'superseded_by_read_id',
    )

    SUBJECT_PITCHER_DAY = 'pitcher_day'
    SUBJECT_TEAM_DAY = 'team_day'

    COMPLETENESS_COMPLETE = 'complete'
    COMPLETENESS_PARTIAL = 'partial'
    COMPLETENESS_UNKNOWN = 'unknown'
    COMPLETENESS_CONFLICT = 'conflict'
    COMPLETENESS_WITHHELD = 'withheld'

    POSTURE_INTERNAL_ONLY = 'internal_only'

    RECOMPUTE_CURRENT = 'current'
    RECOMPUTE_NEEDED = 'recompute_needed'
    RECOMPUTE_RECOMPUTED = 'recomputed'
    RECOMPUTE_SUPERSEDED = 'superseded'

    __table_args__ = (
        db.UniqueConstraint('read_key', name='uq_composed_reads_read_key'),
        db.CheckConstraint(
            "subject_type IN ('pitcher_day', 'team_day')",
            name='ck_composed_reads_subject_type',
        ),
        db.CheckConstraint(
            "completeness_state IN ('complete', 'partial', 'unknown', 'conflict', 'withheld')",
            name='ck_composed_reads_completeness_state',
        ),
        db.CheckConstraint(
            "posture IN ('internal_only')",
            name='ck_composed_reads_posture',
        ),
        db.CheckConstraint(
            "recompute_status IN ('current', 'recompute_needed', 'recomputed', 'superseded')",
            name='ck_composed_reads_recompute_status',
        ),
        db.Index('ix_composed_reads_type_version', 'read_type', 'read_version'),
        db.Index('ix_composed_reads_subject_date', 'subject_type', 'subject_key', 'product_date'),
        db.Index('ix_composed_reads_posture', 'posture'),
        db.Index('ix_composed_reads_recompute_status', 'recompute_status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    read_key = db.Column(db.String(220), nullable=False)
    read_type = db.Column(db.String(120), nullable=False)
    read_version = db.Column(db.Integer, nullable=False)
    subject_type = db.Column(db.String(40), nullable=False)
    subject_id = db.Column(db.String(80))
    subject_key = db.Column(db.String(160), nullable=False)
    product_date = db.Column(db.Date, nullable=False)
    completeness_state = db.Column(db.String(20), nullable=False)
    reason_codes = db.Column(db.JSON)
    limitations = db.Column(db.JSON)
    component_summary = db.Column(db.JSON, nullable=False)
    posture = db.Column(db.String(30), nullable=False, default=POSTURE_INTERNAL_ONLY)

    source = db.Column(db.String(100), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_corrected_at = db.Column(db.DateTime)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    correction_source = db.Column(db.String(100))

    recompute_status = db.Column(
        db.String(30),
        nullable=False,
        default=RECOMPUTE_CURRENT,
    )
    recompute_reason_codes = db.Column(db.JSON)
    invalidated_at = db.Column(db.DateTime)
    invalidated_by_source_table = db.Column(db.String(80))
    invalidated_by_source_pk = db.Column(db.String(120))
    superseded_by_read_id = db.Column(
        db.Integer,
        db.ForeignKey('composed_reads.id'),
        nullable=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    components = db.relationship(
        'ComposedReadComponent',
        backref='composed_read',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'read_key': self.read_key,
            'read_type': self.read_type,
            'read_version': self.read_version,
            'subject_type': self.subject_type,
            'subject_id': self.subject_id,
            'subject_key': self.subject_key,
            'product_date': _iso(self.product_date),
            'completeness_state': self.completeness_state,
            'reason_codes': list(self.reason_codes or []),
            'limitations': list(self.limitations or []),
            'component_summary': dict(self.component_summary or {}),
            'posture': self.posture,
            'source': self.source,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'recompute_status': self.recompute_status,
            'recompute_reason_codes': list(self.recompute_reason_codes or []),
            'invalidated_at': _iso(self.invalidated_at),
            'invalidated_by_source_table': self.invalidated_by_source_table,
            'invalidated_by_source_pk': self.invalidated_by_source_pk,
            'superseded_by_read_id': self.superseded_by_read_id,
            'components': [component.to_dict() for component in self.components],
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


class ComposedReadComponent(db.Model):
    __tablename__ = 'composed_read_components'

    COMPONENT_ABSENT = 'absent'

    __table_args__ = (
        db.CheckConstraint(
            "component_state IN ('complete', 'partial', 'unknown', 'conflict', 'withheld', 'absent')",
            name='ck_composed_read_components_state',
        ),
        db.Index('ix_composed_read_components_read', 'composed_read_id'),
        db.Index('ix_composed_read_components_name', 'component_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    composed_read_id = db.Column(
        db.Integer,
        db.ForeignKey('composed_reads.id'),
        nullable=False,
    )
    component_name = db.Column(db.String(120), nullable=False)
    required = db.Column(db.Boolean, nullable=False)
    component_state = db.Column(db.String(20), nullable=False)
    reason_codes = db.Column(db.JSON)
    limitations = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    evidence_citations = db.relationship(
        'ComposedReadEvidenceCitation',
        backref='component',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'composed_read_id': self.composed_read_id,
            'component_name': self.component_name,
            'required': self.required,
            'component_state': self.component_state,
            'reason_codes': list(self.reason_codes or []),
            'limitations': list(self.limitations or []),
            'evidence_citations': [
                citation.to_dict() for citation in self.evidence_citations
            ],
            'created_at': _iso(self.created_at),
        }


class ComposedReadEvidenceCitation(db.Model):
    __tablename__ = 'composed_read_evidence_citations'

    __table_args__ = (
        db.Index(
            'ix_composed_read_evidence_citations_component',
            'composed_read_component_id',
        ),
        db.Index(
            'ix_composed_read_evidence_citations_evidence',
            'evidence_object_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    composed_read_component_id = db.Column(
        db.Integer,
        db.ForeignKey('composed_read_components.id'),
        nullable=False,
    )
    evidence_object_id = db.Column(
        db.Integer,
        db.ForeignKey('evidence_objects.id'),
        nullable=False,
    )
    citation_role = db.Column(db.String(60), nullable=False, default='read_component')
    cited_completeness_state = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    evidence_object = db.relationship('EvidenceObject', lazy='selectin')

    def to_dict(self):
        return {
            'id': self.id,
            'composed_read_component_id': self.composed_read_component_id,
            'evidence_object_id': self.evidence_object_id,
            'citation_role': self.citation_role,
            'cited_completeness_state': self.cited_completeness_state,
            'created_at': _iso(self.created_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
