"""Evidence object builder and correction hooks for Phase 0D."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256

from models.evidence_contract import EvidenceCitation, EvidenceObject
from services import source_readiness
from services.evidence_rules import (
    ClaimTemplate,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
    evidence_rule_registry,
    render_claim_template,
)
from utils.db import db
from utils.time import utc_now_naive


class EvidenceBuildError(AssertionError):
    """Raised when an evidence object would violate the Phase 0D contract."""


@dataclass(frozen=True)
class EvidenceCitationInput:
    source_family: str
    source_table: str
    source_pk: str | int
    source_field_names: tuple[str, ...]
    cited_values: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    citation_role: str = 'supporting_input'

    def to_dict(self) -> dict:
        return {
            'source_family': self.source_family,
            'source_table': self.source_table,
            'source_pk': str(self.source_pk),
            'source_field_names': list(self.source_field_names),
            'citation_role': self.citation_role,
            'cited_values': dict(self.cited_values or {}),
            'provenance': dict(self.provenance or {}),
        }


def build_evidence_object(
    *,
    rule_id: str,
    rule_version: int | None = None,
    claim_template: ClaimTemplate,
    claim_values: dict,
    subject_type: str,
    product_date: date,
    cited_inputs: tuple[EvidenceCitationInput, ...],
    computation_trace: dict,
    input_values: dict,
    subject_id: str | int | None = None,
    subject_key: str | None = None,
    readiness_payload: dict | None = None,
    contradictions: tuple[dict, ...] = (),
    limitations: tuple[str, ...] = (),
    source_posture: str = 'cleared',
    sync_run_id: int | None = None,
    registry: EvidenceRuleRegistry | None = None,
    source: str = 'phase0d:evidence_contract',
) -> EvidenceObject:
    """Build but do not commit a Phase 0D evidence object."""
    registry = registry or evidence_rule_registry
    rule = registry.get(rule_id, rule_version)
    _validate_build_inputs(
        rule=rule,
        subject_type=subject_type,
        product_date=product_date,
        cited_inputs=cited_inputs,
        computation_trace=computation_trace,
    )

    completeness, reason_codes, rendered_claim = _evaluate_evidence_state(
        rule=rule,
        claim_template=claim_template,
        claim_values=claim_values,
        readiness_payload=readiness_payload,
        input_values=input_values,
        contradictions=contradictions,
        source_posture=source_posture,
    )
    if completeness not in rule.allowed_completeness:
        completeness = EvidenceObject.COMPLETENESS_WITHHELD
        reason_codes.append('completeness_not_allowed_by_rule')
        rendered_claim = 'Evidence withheld: rule does not allow this completeness state.'

    normalized_subject_key = subject_key or _default_subject_key(
        subject_type=subject_type,
        subject_id=subject_id,
        product_date=product_date,
    )
    typed_cited_inputs = [citation.to_dict() for citation in cited_inputs]
    evidence_key = _evidence_key(
        rule=rule,
        subject_type=subject_type,
        subject_key=normalized_subject_key,
        product_date=product_date,
        claim_template_id=claim_template.template_id,
    )
    evidence = EvidenceObject(
        evidence_key=evidence_key,
        evidence_type=rule.evidence_type,
        subject_type=subject_type,
        subject_id=str(subject_id) if subject_id is not None else None,
        subject_key=normalized_subject_key,
        product_date=product_date,
        claim_template_id=claim_template.template_id,
        rendered_claim=rendered_claim,
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        rule_definition_hash=rule.definition_hash,
        typed_cited_inputs=typed_cited_inputs,
        computation_trace={
            'rule_id': rule.rule_id,
            'rule_version': rule.rule_version,
            'steps': list(computation_trace.get('steps') or []),
            'notes': list(computation_trace.get('notes') or []),
        },
        completeness_state=completeness,
        reason_codes=_dedupe(reason_codes),
        limitations=list(limitations or []),
        posture=rule.posture_default,
        source=source,
        sync_run_id=sync_run_id,
        first_seen_at=utc_now_naive(),
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    evidence.citations = [
        EvidenceCitation(
            source_family=citation.source_family,
            source_table=citation.source_table,
            source_pk=str(citation.source_pk),
            source_field_names=list(citation.source_field_names),
            citation_role=citation.citation_role,
            cited_values=dict(citation.cited_values or {}),
            provenance=dict(citation.provenance or {}),
        )
        for citation in cited_inputs
    ]
    return evidence


def mark_dependent_evidence_for_recompute(
    *,
    source_table: str,
    source_pk: str | int,
    reason_code: str,
    batch_size: int = 100,
    sync_run_id: int | None = None,
    correction_source: str = 'upstream_source_correction',
) -> dict:
    """Mark dependent evidence rows for bounded recompute after source correction."""
    if batch_size <= 0:
        raise EvidenceBuildError('batch_size must be positive')
    source_pk = str(source_pk)
    citation_rows = (
        EvidenceCitation.query
        .join(EvidenceObject)
        .filter(EvidenceCitation.source_table == source_table)
        .filter(EvidenceCitation.source_pk == source_pk)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(EvidenceCitation.id.asc())
        .limit(batch_size)
        .all()
    )
    evidence_ids = []
    seen = set()
    for citation in citation_rows:
        if citation.evidence_object_id not in seen:
            evidence_ids.append(citation.evidence_object_id)
            seen.add(citation.evidence_object_id)
    if not evidence_ids:
        return {'marked_count': 0, 'evidence_ids': []}

    now = utc_now_naive()
    rows = (
        EvidenceObject.query
        .filter(EvidenceObject.id.in_(evidence_ids))
        .order_by(EvidenceObject.id.asc())
        .all()
    )
    marked_ids = []
    for row in rows:
        row.recompute_status = EvidenceObject.RECOMPUTE_NEEDED
        row.recompute_reason_codes = _dedupe(
            list(row.recompute_reason_codes or []) + [reason_code]
        )
        row.invalidated_at = now
        row.invalidated_by_source_table = source_table
        row.invalidated_by_source_pk = source_pk
        row.last_corrected_at = now
        row.correction_count = (row.correction_count or 0) + 1
        row.correction_source = correction_source
        if sync_run_id is not None:
            row.sync_run_id = sync_run_id
        marked_ids.append(row.id)
    db.session.flush()
    return {'marked_count': len(marked_ids), 'evidence_ids': marked_ids}


def _validate_build_inputs(
    *,
    rule: EvidenceRule,
    subject_type,
    product_date,
    cited_inputs,
    computation_trace,
) -> None:
    if not subject_type:
        raise EvidenceBuildError('evidence subject_type is required')
    if product_date is None:
        raise EvidenceBuildError('evidence product_date is required')
    if not cited_inputs:
        raise EvidenceBuildError('evidence requires cited inputs')
    for citation in cited_inputs:
        if not citation.source_family or not citation.source_table or citation.source_pk in (None, ''):
            raise EvidenceBuildError('citation requires source family, table, and row identity')
        if not citation.source_field_names:
            raise EvidenceBuildError('citation requires source field names')
        if not citation.provenance.get('source'):
            raise EvidenceBuildError('citation requires source provenance')
    if not isinstance(computation_trace, dict):
        raise EvidenceBuildError('computation trace must be serializable dictionary')
    cited_fields = {
        f'{citation.source_family}.{field_name}'
        for citation in cited_inputs
        for field_name in citation.source_field_names
    }
    missing = sorted(set(rule.required_cited_fields) - cited_fields)
    if missing:
        raise EvidenceBuildError(f'evidence citations missing required fields: {missing}')


def _evaluate_evidence_state(
    *,
    rule: EvidenceRule,
    claim_template: ClaimTemplate,
    claim_values: dict,
    readiness_payload: dict | None,
    input_values: dict,
    contradictions,
    source_posture: str,
) -> tuple[str, list[str], str]:
    if source_posture != 'cleared':
        return (
            EvidenceObject.COMPLETENESS_WITHHELD,
            ['source_posture_uncleared'],
            'Evidence withheld: source posture is not cleared.',
        )

    unready = _unready_source_families(rule.required_input_families, readiness_payload)
    if unready:
        return (
            EvidenceObject.COMPLETENESS_WITHHELD,
            [f'source_family_unready:{family}' for family in unready],
            'Evidence withheld: required source family is not ready.',
        )

    unknown_fields = [
        field
        for field in rule.required_cited_fields
        if input_values.get(field) is None
    ]
    if unknown_fields:
        return (
            EvidenceObject.COMPLETENESS_UNKNOWN,
            [f'required_input_unknown:{field}' for field in unknown_fields],
            'Evidence unknown: required cited input is unavailable.',
        )

    if contradictions:
        return (
            EvidenceObject.COMPLETENESS_CONFLICT,
            ['contradictory_inputs'],
            'Evidence conflict: cited inputs disagree.',
        )

    return (
        EvidenceObject.COMPLETENESS_COMPLETE,
        [],
        render_claim_template(claim_template, claim_values),
    )


def _unready_source_families(required_families, readiness_payload):
    if not required_families:
        return []
    families = (readiness_payload or {}).get('families') or {}
    unready = []
    for family in required_families:
        family_payload = families.get(family)
        if not family_payload or family_payload.get('status') != source_readiness.READY:
            unready.append(family)
    return unready


def _default_subject_key(*, subject_type, subject_id, product_date):
    identity = subject_id if subject_id not in (None, '') else 'product'
    return f'{subject_type}:{identity}:{product_date.isoformat()}'


def _evidence_key(*, rule, subject_type, subject_key, product_date, claim_template_id):
    payload = '|'.join((
        rule.rule_id,
        str(rule.rule_version),
        subject_type,
        subject_key,
        product_date.isoformat(),
        claim_template_id,
    ))
    return sha256(payload.encode('utf-8')).hexdigest()


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
