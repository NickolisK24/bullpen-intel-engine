"""Internal Phase 0F pitcher evidence review payloads.

This module is intentionally read-only and admin-route only. It serializes
stored Phase 0D/0E evidence/read rows for operator review without composing new
baseball conclusions.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import asc, desc
from sqlalchemy.orm import selectinload

from models.composed_read import (
    ComposedRead,
    ComposedReadComponent,
    ComposedReadEvidenceCitation,
)
from models.evidence_contract import EvidenceObject
from models.legacy_read_audit import LegacyReadDivergence
from models.pitcher import Pitcher
from services.reliever_daily_read import READ_TYPE as RELIEVER_DAILY_READ_TYPE


CAPABILITY = 'phase0f_internal_pitcher_evidence_review'
ROUTE_STATUS = 'internal_admin_only'

WORKLOAD_RULE_PREFIXES = ('workload_', 'usage_', 'outing_')
ENTRY_EXIT_RULE_IDS = {
    'appearance_entry_context',
    'appearance_exit_context',
    'appearance_inherited_runners',
    'appearance_inherited_runners_scored',
    'appearance_inherited_traffic_outcome',
    'outing_clean',
    'outing_traffic',
    'outing_context_unknown',
}
ENTRY_EXIT_EVIDENCE_TYPES = {
    'appearance_context_fact',
    'inherited_traffic_fact',
}
ROSTER_RULE_TOKENS = ('roster', 'il', 'depth')
ROSTER_EVIDENCE_TYPES = {
    'pitcher_roster_membership_context',
    'pitcher_il_placement_context',
    'pitcher_il_activation_context',
    'roster_depth_fact',
}


class PitcherEvidenceRequestError(ValueError):
    pass


class PitcherEvidenceNotFound(LookupError):
    pass


def parse_product_date(value) -> date:
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if not text:
        raise PitcherEvidenceRequestError('date_required')
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise PitcherEvidenceRequestError('date_invalid') from exc


def parse_positive_int(value, *, field_name: str) -> int | None:
    if value is None or str(value).strip() == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PitcherEvidenceRequestError(f'{field_name}_invalid') from exc
    if parsed <= 0:
        raise PitcherEvidenceRequestError(f'{field_name}_invalid')
    return parsed


def build_internal_pitcher_evidence_payload(
    *,
    pitcher_id=None,
    mlb_id=None,
    product_date=None,
) -> dict:
    ref = parse_product_date(product_date)
    pitcher = _resolve_pitcher(pitcher_id=pitcher_id, mlb_id=mlb_id)
    read = _current_reliever_daily_read(pitcher.id, ref)
    evidence_objects = _evidence_objects(pitcher.id, ref, read=read)
    cited_evidence = _cited_evidence_objects(read)
    cited_evidence_ids = {row.id for row in cited_evidence if row is not None}
    divergences = _reconciliation_divergences(pitcher.id, ref)

    section_presence = {
        'reliever_daily_read': read is not None,
        'read_components': bool(read and read.components),
        'cited_evidence_rendered_claims': bool(cited_evidence),
        'workload_evidence_references': any(_is_workload_evidence(row) for row in evidence_objects),
        'entry_exit_context_references': any(_is_entry_exit_evidence(row) for row in evidence_objects),
        'roster_depth_il_context': any(_is_roster_evidence(row) for row in evidence_objects),
        'reconciliation_divergences': bool(divergences),
    }

    return {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'request': {
            'pitcher_id': pitcher.id,
            'mlb_id': pitcher.mlb_id,
            'date': ref.isoformat(),
            'data_through': ref.isoformat(),
        },
        'pitcher': _pitcher_identity(pitcher),
        'target_date': ref.isoformat(),
        'data_through': ref.isoformat(),
        'reliever_daily_read': _serialize_read(read),
        'read_components': _serialize_components(read),
        'states': {
            'read_completeness_state': read.completeness_state if read else None,
            'read_recompute_status': read.recompute_status if read else None,
        },
        'reasons': list(read.reason_codes or []) if read else [],
        'limitations': list(read.limitations or []) if read else [],
        'cited_evidence_rendered_claims': [
            row.rendered_claim for row in cited_evidence if row is not None
        ],
        'evidence_objects': [_serialize_evidence_object(row) for row in evidence_objects],
        'workload_evidence_references': [
            _evidence_reference(row) for row in evidence_objects if _is_workload_evidence(row)
        ],
        'entry_exit_context_references': [
            _evidence_reference(row) for row in evidence_objects if _is_entry_exit_evidence(row)
        ],
        'roster_depth_il_context': [
            _evidence_reference(row) for row in evidence_objects if _is_roster_evidence(row)
        ],
        'other_pitcher_evidence_references': [
            _evidence_reference(row)
            for row in evidence_objects
            if (
                row.id not in cited_evidence_ids
                and not _is_workload_evidence(row)
                and not _is_entry_exit_evidence(row)
                and not _is_roster_evidence(row)
            )
        ],
        'reconciliation_divergences': [
            _serialize_divergence(row) for row in divergences
        ],
        'source_readiness_notes': {
            'stored_fields_only': True,
            'quote_only_rendered_claims': True,
            'optional_sections_present': section_presence,
            'missing_optional_sections': [
                key for key, present in section_presence.items() if not present
            ],
        },
    }


def error_payload(reason: str, *, status: int) -> dict:
    return {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'status': 'error',
        'error': reason,
        'http_status': status,
    }


def _resolve_pitcher(*, pitcher_id, mlb_id) -> Pitcher:
    normalized_pitcher_id = parse_positive_int(pitcher_id, field_name='pitcher_id')
    normalized_mlb_id = parse_positive_int(mlb_id, field_name='mlb_id')
    if normalized_pitcher_id is None and normalized_mlb_id is None:
        raise PitcherEvidenceRequestError('pitcher_identifier_required')

    query = Pitcher.query
    if normalized_pitcher_id is not None:
        query = query.filter(Pitcher.id == normalized_pitcher_id)
    if normalized_mlb_id is not None:
        query = query.filter(Pitcher.mlb_id == normalized_mlb_id)
    pitcher = query.one_or_none()
    if pitcher is None:
        raise PitcherEvidenceNotFound('pitcher_not_found')
    return pitcher


def _current_reliever_daily_read(pitcher_id: int, ref: date) -> ComposedRead | None:
    return (
        ComposedRead.query
        .options(
            selectinload(ComposedRead.components)
            .selectinload(ComposedReadComponent.evidence_citations)
            .selectinload(ComposedReadEvidenceCitation.evidence_object)
            .selectinload(EvidenceObject.citations)
        )
        .filter(ComposedRead.read_type == RELIEVER_DAILY_READ_TYPE)
        .filter(ComposedRead.subject_type == ComposedRead.SUBJECT_PITCHER_DAY)
        .filter(ComposedRead.subject_id == str(pitcher_id))
        .filter(ComposedRead.product_date == ref)
        .filter(ComposedRead.posture == ComposedRead.POSTURE_INTERNAL_ONLY)
        .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_CURRENT)
        .order_by(desc(ComposedRead.id))
        .first()
    )


def _evidence_objects(pitcher_id: int, ref: date, *, read: ComposedRead | None) -> list[EvidenceObject]:
    rows = (
        EvidenceObject.query
        .options(selectinload(EvidenceObject.citations))
        .filter(EvidenceObject.subject_type == 'pitcher')
        .filter(EvidenceObject.subject_id == str(pitcher_id))
        .filter(EvidenceObject.product_date == ref)
        .filter(EvidenceObject.posture == EvidenceObject.POSTURE_INTERNAL_ONLY)
        .filter(EvidenceObject.recompute_status == EvidenceObject.RECOMPUTE_CURRENT)
        .order_by(
            asc(EvidenceObject.evidence_type),
            asc(EvidenceObject.rule_id),
            asc(EvidenceObject.id),
        )
        .all()
    )
    by_id = {row.id: row for row in rows}
    for row in _cited_evidence_objects(read):
        if row is not None:
            by_id.setdefault(row.id, row)
    return sorted(
        by_id.values(),
        key=lambda row: (
            row.evidence_type or '',
            row.rule_id or '',
            row.id or 0,
        ),
    )


def _cited_evidence_objects(read: ComposedRead | None) -> list[EvidenceObject]:
    if read is None:
        return []
    rows = []
    seen = set()
    for component in sorted(read.components or [], key=lambda row: row.component_name):
        for citation in sorted(component.evidence_citations or [], key=lambda row: row.id or 0):
            evidence = citation.evidence_object
            if evidence is None or evidence.id in seen:
                continue
            rows.append(evidence)
            seen.add(evidence.id)
    return rows


def _reconciliation_divergences(pitcher_id: int, ref: date) -> list[LegacyReadDivergence]:
    return (
        LegacyReadDivergence.query
        .filter(LegacyReadDivergence.subject_type == LegacyReadDivergence.SUBJECT_PITCHER_DAY)
        .filter(LegacyReadDivergence.subject_id == str(pitcher_id))
        .filter(LegacyReadDivergence.product_date == ref)
        .order_by(asc(LegacyReadDivergence.category), asc(LegacyReadDivergence.id))
        .all()
    )


def _watermark() -> dict:
    return {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }


def _pitcher_identity(pitcher: Pitcher) -> dict:
    return {
        'id': pitcher.id,
        'mlb_id': pitcher.mlb_id,
        'full_name': pitcher.full_name,
        'team_id': pitcher.team_id,
        'team_name': pitcher.team_name,
        'team_abbreviation': pitcher.team_abbreviation,
        'active': bool(pitcher.active),
    }


def _serialize_read(read: ComposedRead | None) -> dict | None:
    if read is None:
        return None
    return {
        'id': read.id,
        'read_key': read.read_key,
        'read_type': read.read_type,
        'read_version': read.read_version,
        'subject_type': read.subject_type,
        'subject_id': read.subject_id,
        'subject_key': read.subject_key,
        'product_date': _iso(read.product_date),
        'completeness_state': read.completeness_state,
        'reason_codes': list(read.reason_codes or []),
        'limitations': list(read.limitations or []),
        'component_summary': dict(read.component_summary or {}),
        'posture': read.posture,
        'source': read.source,
        'sync_run_id': read.sync_run_id,
        'recompute_status': read.recompute_status,
        'recompute_reason_codes': list(read.recompute_reason_codes or []),
        'created_at': _iso(read.created_at),
        'updated_at': _iso(read.updated_at),
    }


def _serialize_components(read: ComposedRead | None) -> list[dict]:
    if read is None:
        return []
    components = []
    for component in sorted(read.components or [], key=lambda row: row.component_name):
        components.append({
            'id': component.id,
            'component_name': component.component_name,
            'required': bool(component.required),
            'component_state': component.component_state,
            'reason_codes': list(component.reason_codes or []),
            'limitations': list(component.limitations or []),
            'evidence_citations': [
                {
                    'id': citation.id,
                    'evidence_object_id': citation.evidence_object_id,
                    'citation_role': citation.citation_role,
                    'cited_completeness_state': citation.cited_completeness_state,
                    'evidence': _evidence_reference(citation.evidence_object),
                    'created_at': _iso(citation.created_at),
                }
                for citation in sorted(
                    component.evidence_citations or [],
                    key=lambda row: row.id or 0,
                )
            ],
            'created_at': _iso(component.created_at),
        })
    return components


def _serialize_evidence_object(row: EvidenceObject) -> dict:
    payload = _evidence_reference(row)
    payload.update({
        'subject_type': row.subject_type,
        'subject_id': row.subject_id,
        'subject_key': row.subject_key,
        'claim_template_id': row.claim_template_id,
        'rule_version': row.rule_version,
        'rule_definition_hash': row.rule_definition_hash,
        'typed_cited_inputs': list(row.typed_cited_inputs or []),
        'computation_trace': dict(row.computation_trace or {}),
        'posture': row.posture,
        'source': row.source,
        'sync_run_id': row.sync_run_id,
        'recompute_status': row.recompute_status,
        'recompute_reason_codes': list(row.recompute_reason_codes or []),
        'citations': [
            {
                'id': citation.id,
                'source_family': citation.source_family,
                'source_table': citation.source_table,
                'source_pk': citation.source_pk,
                'source_field_names': list(citation.source_field_names or []),
                'citation_role': citation.citation_role,
                'cited_values': dict(citation.cited_values or {}),
                'provenance': dict(citation.provenance or {}),
                'created_at': _iso(citation.created_at),
            }
            for citation in sorted(row.citations or [], key=lambda item: item.id or 0)
        ],
        'created_at': _iso(row.created_at),
        'updated_at': _iso(row.updated_at),
    })
    return payload


def _evidence_reference(row: EvidenceObject | None) -> dict | None:
    if row is None:
        return None
    return {
        'id': row.id,
        'evidence_key': row.evidence_key,
        'evidence_type': row.evidence_type,
        'product_date': _iso(row.product_date),
        'rule_id': row.rule_id,
        'rendered_claim': row.rendered_claim,
        'completeness_state': row.completeness_state,
        'reason_codes': list(row.reason_codes or []),
        'limitations': list(row.limitations or []),
    }


def _serialize_divergence(row: LegacyReadDivergence) -> dict:
    return {
        'id': row.id,
        'subject_type': row.subject_type,
        'subject_id': row.subject_id,
        'product_date': _iso(row.product_date),
        'category': row.category,
        'is_material': bool(row.is_material),
        'escalation_state': row.escalation_state,
        'legacy_capture': dict(row.legacy_capture or {}),
        'read_capture': dict(row.read_capture or {}),
        'comparison_basis': row.comparison_basis,
        'notes': row.notes,
        'source': row.source,
        'sync_run_id': row.sync_run_id,
        'created_at': _iso(row.created_at),
        'updated_at': _iso(row.updated_at),
    }


def _is_workload_evidence(row: EvidenceObject) -> bool:
    rule_id = row.rule_id or ''
    return row.evidence_type == 'workload_recovery_fact' or rule_id.startswith(WORKLOAD_RULE_PREFIXES)


def _is_entry_exit_evidence(row: EvidenceObject) -> bool:
    return (
        row.evidence_type in ENTRY_EXIT_EVIDENCE_TYPES
        or row.rule_id in ENTRY_EXIT_RULE_IDS
    )


def _is_roster_evidence(row: EvidenceObject) -> bool:
    rule_id = (row.rule_id or '').lower()
    return (
        row.evidence_type in ROSTER_EVIDENCE_TYPES
        or any(token in rule_id for token in ROSTER_RULE_TOKENS)
    )


def _iso(value):
    return value.isoformat() if value is not None else None
