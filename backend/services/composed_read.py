"""Builder and recompute helpers for Phase 0E composed reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from typing import Mapping

from models.composed_read import (
    ComposedRead,
    ComposedReadComponent,
    ComposedReadEvidenceCitation,
)
from models.evidence_contract import EvidenceObject
from services.composed_read_registry import (
    ComponentSpec,
    ReadTypeRegistry,
    read_type_registry,
)
from utils.db import db
from utils.time import utc_now_naive


class ComposedReadBuildError(AssertionError):
    """Raised when a composed read would violate the Phase 0E contract."""


@dataclass(frozen=True)
class ComponentInput:
    component_state: str
    evidence_objects: tuple[EvidenceObject, ...] = ()
    reason_codes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


SEVERITY_ORDER = {
    ComposedRead.COMPLETENESS_COMPLETE: 0,
    ComposedRead.COMPLETENESS_PARTIAL: 1,
    ComposedRead.COMPLETENESS_UNKNOWN: 2,
    ComposedRead.COMPLETENESS_CONFLICT: 3,
    ComposedRead.COMPLETENESS_WITHHELD: 4,
}

ABSENT_REQUIRED_SEVERITY_STATE = ComposedRead.COMPLETENESS_UNKNOWN

BASELINE_REASON_CODES = frozenset({
    'component_absent',
    'component_evidence_unavailable',
    'component_evidence_conflict',
    'component_evidence_superseded',
    'evidence_type_not_allowed',
    'read_type_not_registered',
    'source_family_not_ready',
})


def build_composed_read(
    *,
    read_type: str,
    subject_type: str,
    subject_id: str | int,
    product_date: date,
    component_inputs: Mapping[str, ComponentInput | dict],
    read_version: int | None = None,
    subject_key: str | None = None,
    sync_run_id: int | None = None,
    source: str = 'phase0e:composed_read',
    registry: ReadTypeRegistry | None = None,
) -> ComposedRead:
    """Build and stage, but do not commit, an internal-only composed read."""
    registry = registry or read_type_registry
    read_definition = registry.get(read_type, read_version)
    if subject_type != read_definition.subject_type:
        raise ComposedReadBuildError(
            f'subject_type {subject_type!r} does not match read type '
            f'{read_definition.subject_type!r}'
        )
    if product_date is None:
        raise ComposedReadBuildError('product_date is required')
    normalized_subject_key = subject_key or _default_subject_key(
        subject_type=subject_type,
        subject_id=subject_id,
        product_date=product_date,
    )
    normalized_inputs = _normalize_component_inputs(component_inputs)
    component_specs = {component.name: component for component in read_definition.components}
    extra = sorted(set(normalized_inputs) - set(component_specs))
    if extra:
        raise ComposedReadBuildError(f'unregistered component input: {extra}')

    components = []
    component_summary = {}
    required_states = []
    read_reason_codes = []
    read_limitations = []
    for spec in read_definition.components:
        component_input = normalized_inputs.get(spec.name)
        component = _build_component(spec, component_input)
        components.append(component)
        component_summary[spec.name] = {
            'state': component.component_state,
            'required': spec.required,
            'evidence_citation_count': len(component.evidence_citations),
        }
        if spec.required:
            required_states.append(component.component_state)
        for reason in component.reason_codes or []:
            read_reason_codes.append(f'{spec.name}:{reason}')
        for limitation in component.limitations or []:
            read_limitations.append(f'{spec.name}:{limitation}')

    completeness_state = _read_completeness(required_states)
    read_key = _read_key(
        read_type=read_definition.read_type,
        read_version=read_definition.read_version,
        subject_type=subject_type,
        subject_key=normalized_subject_key,
        product_date=product_date,
    )
    now = utc_now_naive()
    read = ComposedRead(
        read_key=read_key,
        read_type=read_definition.read_type,
        read_version=read_definition.read_version,
        subject_type=subject_type,
        subject_id=str(subject_id) if subject_id is not None else None,
        subject_key=normalized_subject_key,
        product_date=product_date,
        completeness_state=completeness_state,
        reason_codes=_dedupe(read_reason_codes),
        limitations=_dedupe(read_limitations),
        component_summary=component_summary,
        posture=ComposedRead.POSTURE_INTERNAL_ONLY,
        source=source,
        sync_run_id=sync_run_id,
        first_seen_at=now,
        recompute_status=ComposedRead.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
        components=components,
    )
    _stage_read_with_supersession(read, sync_run_id=sync_run_id)
    return read


def mark_dependent_reads_for_recompute(
    *,
    evidence_object_ids: tuple[int, ...] | list[int] | set[int],
    reason_code: str,
    batch_size: int = 100,
    sync_run_id: int | None = None,
    correction_source: str = 'upstream_evidence_correction',
) -> dict:
    if batch_size <= 0:
        raise ComposedReadBuildError('batch_size must be positive')
    ids = [int(item) for item in evidence_object_ids]
    if not ids:
        return {'marked_count': 0, 'read_ids': []}
    citation_rows = (
        ComposedReadEvidenceCitation.query
        .join(ComposedReadComponent)
        .join(ComposedRead)
        .filter(ComposedReadEvidenceCitation.evidence_object_id.in_(ids))
        .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_CURRENT)
        .order_by(ComposedReadEvidenceCitation.id.asc())
        .limit(batch_size)
        .all()
    )
    read_ids = []
    seen = set()
    for citation in citation_rows:
        read_id = citation.component.composed_read_id
        if read_id not in seen:
            read_ids.append(read_id)
            seen.add(read_id)
    if not read_ids:
        return {'marked_count': 0, 'read_ids': []}

    now = utc_now_naive()
    rows = (
        ComposedRead.query
        .filter(ComposedRead.id.in_(read_ids))
        .order_by(ComposedRead.id.asc())
        .all()
    )
    source_pk = ','.join(str(item) for item in ids)
    marked_ids = []
    for row in rows:
        row.recompute_status = ComposedRead.RECOMPUTE_NEEDED
        row.recompute_reason_codes = _dedupe(
            list(row.recompute_reason_codes or []) + [reason_code]
        )
        row.invalidated_at = now
        row.invalidated_by_source_table = 'evidence_objects'
        row.invalidated_by_source_pk = source_pk
        row.last_corrected_at = now
        row.correction_count = (row.correction_count or 0) + 1
        row.correction_source = correction_source
        if sync_run_id is not None:
            row.sync_run_id = sync_run_id
        marked_ids.append(row.id)
    db.session.flush()
    return {'marked_count': len(marked_ids), 'read_ids': marked_ids}


def validate_composed_read_integrity(*, registry: ReadTypeRegistry | None = None) -> dict:
    registry = registry or read_type_registry
    errors = []
    reads = ComposedRead.query.order_by(ComposedRead.id.asc()).all()
    citation_count = 0
    for row in reads:
        try:
            read_definition = registry.get(row.read_type, row.read_version)
        except Exception:
            errors.append(f'composed_read:{row.id}:unknown_read_type:{row.read_type}')
            continue
        expected_components = {component.name for component in read_definition.components}
        actual_components = {component.component_name for component in row.components}
        if expected_components != actual_components:
            errors.append(f'composed_read:{row.id}:component_mismatch')
        for component in row.components:
            for citation in component.evidence_citations:
                citation_count += 1
                evidence = db.session.get(EvidenceObject, citation.evidence_object_id)
                if evidence is None:
                    errors.append(
                        f'composed_read_citation:{citation.id}:missing_evidence_object'
                    )
                    continue
                if not evidence.citations:
                    errors.append(
                        f'composed_read_citation:{citation.id}:evidence_without_provenance'
                    )
                for evidence_citation in evidence.citations:
                    if not (evidence_citation.provenance or {}).get('source'):
                        errors.append(
                            f'composed_read_citation:{citation.id}:provenance_missing_source'
                        )
                if citation.cited_completeness_state not in SEVERITY_ORDER:
                    errors.append(
                        f'composed_read_citation:{citation.id}:invalid_cited_completeness'
                    )
    if errors:
        raise ComposedReadBuildError('; '.join(errors))
    return {
        'read_rows_checked': len(reads),
        'citation_rows_checked': citation_count,
    }


def _normalize_component_inputs(component_inputs):
    result = {}
    for name, value in dict(component_inputs or {}).items():
        if isinstance(value, ComponentInput):
            result[name] = value
            continue
        result[name] = ComponentInput(
            component_state=value.get('component_state'),
            evidence_objects=tuple(value.get('evidence_objects') or ()),
            reason_codes=tuple(value.get('reason_codes') or ()),
            limitations=tuple(value.get('limitations') or ()),
        )
    return result


def _build_component(spec: ComponentSpec, component_input: ComponentInput | None):
    if component_input is None:
        reason_codes = ['component_absent'] if spec.required else []
        return ComposedReadComponent(
            component_name=spec.name,
            required=spec.required,
            component_state=ComposedReadComponent.COMPONENT_ABSENT,
            reason_codes=reason_codes,
            limitations=[],
            evidence_citations=[],
        )
    if component_input.component_state not in set(SEVERITY_ORDER) | {
        ComposedReadComponent.COMPONENT_ABSENT,
    }:
        raise ComposedReadBuildError(
            f'{spec.name} has unsupported component_state: '
            f'{component_input.component_state}'
        )
    reason_codes = list(component_input.reason_codes or [])
    limitations = list(component_input.limitations or [])
    citations = []
    for evidence in component_input.evidence_objects:
        _validate_cited_evidence(spec, evidence)
        if evidence.recompute_status == EvidenceObject.RECOMPUTE_SUPERSEDED:
            reason_codes.append('component_evidence_superseded')
        citations.append(ComposedReadEvidenceCitation(
            evidence_object_id=evidence.id,
            citation_role='read_component',
            cited_completeness_state=evidence.completeness_state,
        ))
    if (
        component_input.component_state == ComposedReadComponent.COMPONENT_ABSENT
        and spec.required
        and 'component_absent' not in reason_codes
    ):
        reason_codes.append('component_absent')
    return ComposedReadComponent(
        component_name=spec.name,
        required=spec.required,
        component_state=component_input.component_state,
        reason_codes=_dedupe(reason_codes),
        limitations=_dedupe(limitations),
        evidence_citations=citations,
    )


def _validate_cited_evidence(spec: ComponentSpec, evidence: EvidenceObject) -> None:
    if evidence is None or evidence.id is None:
        raise ComposedReadBuildError('component citation requires a real evidence object row')
    stored = db.session.get(EvidenceObject, evidence.id)
    if stored is None:
        raise ComposedReadBuildError('component citation references missing evidence object')
    if evidence.evidence_type not in spec.allowed_evidence_types:
        raise ComposedReadBuildError(
            f'evidence_type_not_allowed:{spec.name}:{evidence.evidence_type}'
        )


def _read_completeness(required_states):
    if not required_states:
        return ComposedRead.COMPLETENESS_UNKNOWN
    worst_state = ComposedRead.COMPLETENESS_COMPLETE
    worst_severity = -1
    for state in required_states:
        normalized = (
            ABSENT_REQUIRED_SEVERITY_STATE
            if state == ComposedReadComponent.COMPONENT_ABSENT
            else state
        )
        severity = SEVERITY_ORDER[normalized]
        if severity > worst_severity:
            worst_state = normalized
            worst_severity = severity
    return worst_state


def _stage_read_with_supersession(read: ComposedRead, *, sync_run_id: int | None) -> None:
    existing = ComposedRead.query.filter_by(read_key=read.read_key).one_or_none()
    now = utc_now_naive()
    if existing is not None:
        existing.read_key = f'{existing.read_key}:superseded:{existing.id}'
        existing.recompute_status = ComposedRead.RECOMPUTE_SUPERSEDED
        existing.recompute_reason_codes = _dedupe(
            list(existing.recompute_reason_codes or []) + ['read_rebuilt']
        )
        existing.last_corrected_at = now
        existing.correction_count = (existing.correction_count or 0) + 1
        existing.correction_source = 'phase0e:read_rebuild'
        if sync_run_id is not None:
            existing.sync_run_id = sync_run_id
        db.session.flush()
    db.session.add(read)
    db.session.flush()
    if existing is not None:
        existing.superseded_by_read_id = read.id
        db.session.flush()


def _default_subject_key(*, subject_type, subject_id, product_date):
    identity = subject_id if subject_id not in (None, '') else 'product'
    return f'{subject_type}:{identity}:{product_date.isoformat()}'


def _read_key(*, read_type, read_version, subject_type, subject_key, product_date):
    payload = '|'.join((
        read_type,
        str(read_version),
        subject_type,
        subject_key,
        product_date.isoformat(),
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
