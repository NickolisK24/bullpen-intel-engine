from utils.db import db
from utils.time import utc_now_naive


class EvidenceObject(db.Model):
    __tablename__ = 'evidence_objects'
    __correction_policy_name__ = 'evidence_object_corrections'
    __correction_identity_fields__ = ('evidence_key',)
    __correction_sensitive_fields__ = (
        'evidence_key',
        'evidence_type',
        'subject_type',
        'subject_id',
        'subject_key',
        'product_date',
        'claim_template_id',
        'rendered_claim',
        'rule_id',
        'rule_version',
        'rule_definition_hash',
        'typed_cited_inputs',
        'computation_trace',
        'completeness_state',
        'reason_codes',
        'limitations',
        'posture',
        'recompute_status',
        'recompute_reason_codes',
        'invalidated_at',
        'invalidated_by_source_table',
        'invalidated_by_source_pk',
        'superseded_by_evidence_id',
        'source',
    )

    COMPLETENESS_COMPLETE = 'complete'
    COMPLETENESS_PARTIAL = 'partial'
    COMPLETENESS_UNKNOWN = 'unknown'
    COMPLETENESS_CONFLICT = 'conflict'
    COMPLETENESS_WITHHELD = 'withheld'

    POSTURE_INTERNAL_ONLY = 'internal_only'
    POSTURE_PUBLIC_CANDIDATE = 'public_candidate'

    RECOMPUTE_CURRENT = 'current'
    RECOMPUTE_NEEDED = 'recompute_needed'
    RECOMPUTE_RECOMPUTED = 'recomputed'
    RECOMPUTE_SUPERSEDED = 'superseded'

    __table_args__ = (
        db.UniqueConstraint('evidence_key', name='uq_evidence_objects_evidence_key'),
        db.CheckConstraint(
            "completeness_state IN ('complete', 'partial', 'unknown', 'conflict', 'withheld')",
            name='ck_evidence_objects_completeness_state',
        ),
        db.CheckConstraint(
            "posture IN ('internal_only', 'public_candidate')",
            name='ck_evidence_objects_posture',
        ),
        db.CheckConstraint(
            "recompute_status IN ('current', 'recompute_needed', 'recomputed', 'superseded')",
            name='ck_evidence_objects_recompute_status',
        ),
        db.Index('ix_evidence_objects_rule', 'rule_id', 'rule_version'),
        db.Index('ix_evidence_objects_subject_date', 'subject_type', 'subject_key', 'product_date'),
        db.Index('ix_evidence_objects_posture', 'posture'),
        db.Index('ix_evidence_objects_recompute_status', 'recompute_status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    evidence_key = db.Column(db.String(220), nullable=False)
    evidence_type = db.Column(db.String(80), nullable=False)
    subject_type = db.Column(db.String(40), nullable=False)
    subject_id = db.Column(db.String(80))
    subject_key = db.Column(db.String(160), nullable=False)
    product_date = db.Column(db.Date, nullable=False)
    claim_template_id = db.Column(db.String(120), nullable=False)
    rendered_claim = db.Column(db.Text, nullable=False)
    rule_id = db.Column(db.String(120), nullable=False)
    rule_version = db.Column(db.Integer, nullable=False)
    rule_definition_hash = db.Column(db.String(64), nullable=False)
    typed_cited_inputs = db.Column(db.JSON, nullable=False)
    computation_trace = db.Column(db.JSON, nullable=False)
    completeness_state = db.Column(db.String(20), nullable=False)
    reason_codes = db.Column(db.JSON)
    limitations = db.Column(db.JSON)
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
    superseded_by_evidence_id = db.Column(
        db.Integer,
        db.ForeignKey('evidence_objects.id'),
        nullable=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    citations = db.relationship(
        'EvidenceCitation',
        backref='evidence_object',
        cascade='all, delete-orphan',
        lazy='select',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'evidence_key': self.evidence_key,
            'evidence_type': self.evidence_type,
            'subject_type': self.subject_type,
            'subject_id': self.subject_id,
            'subject_key': self.subject_key,
            'product_date': _iso(self.product_date),
            'claim_template_id': self.claim_template_id,
            'rendered_claim': self.rendered_claim,
            'rule_id': self.rule_id,
            'rule_version': self.rule_version,
            'rule_definition_hash': self.rule_definition_hash,
            'typed_cited_inputs': list(self.typed_cited_inputs or []),
            'computation_trace': dict(self.computation_trace or {}),
            'completeness_state': self.completeness_state,
            'reason_codes': list(self.reason_codes or []),
            'limitations': list(self.limitations or []),
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
            'superseded_by_evidence_id': self.superseded_by_evidence_id,
            'citations': [citation.to_dict() for citation in self.citations],
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


class EvidenceCitation(db.Model):
    __tablename__ = 'evidence_citations'
    __correction_policy_name__ = 'evidence_citation_corrections'
    __correction_identity_fields__ = (
        'evidence_object_id',
        'source_family',
        'source_table',
        'source_pk',
        'citation_role',
    )
    __correction_sensitive_fields__ = (
        'evidence_object_id',
        'source_family',
        'source_table',
        'source_pk',
        'source_field_names',
        'citation_role',
        'cited_values',
        'provenance',
    )

    __table_args__ = (
        db.Index('ix_evidence_citations_object', 'evidence_object_id'),
        db.Index('ix_evidence_citations_source_row', 'source_table', 'source_pk'),
        db.Index('ix_evidence_citations_source_family', 'source_family'),
    )

    id = db.Column(db.Integer, primary_key=True)
    evidence_object_id = db.Column(
        db.Integer,
        db.ForeignKey('evidence_objects.id'),
        nullable=False,
    )
    source_family = db.Column(db.String(80), nullable=False)
    source_table = db.Column(db.String(80), nullable=False)
    source_pk = db.Column(db.String(120), nullable=False)
    source_field_names = db.Column(db.JSON, nullable=False)
    citation_role = db.Column(db.String(60), nullable=False, default='supporting_input')
    cited_values = db.Column(db.JSON)
    provenance = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'evidence_object_id': self.evidence_object_id,
            'source_family': self.source_family,
            'source_table': self.source_table,
            'source_pk': self.source_pk,
            'source_field_names': list(self.source_field_names or []),
            'citation_role': self.citation_role,
            'cited_values': dict(self.cited_values or {}),
            'provenance': dict(self.provenance or {}),
            'created_at': _iso(self.created_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
