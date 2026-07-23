"""Internal Phase 0G team evidence review payloads.

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
from services.evidence_authority import (
    cited_evidence_objects,
    resolve_current_team_evidence,
)
from services.reliever_daily_read import READ_TYPE as RELIEVER_DAILY_READ_TYPE
from services.team_daily_read import READ_TYPE as TEAM_DAILY_READ_TYPE


CAPABILITY = 'phase0g_internal_team_evidence_review'
ROUTE_STATUS = 'internal_admin_only'

OPTIONAL_SECTION_KEYS = (
    'team_daily_read',
    'read_components',
    'cited_evidence_rendered_claims',
    'evidence_objects',
    'reliever_daily_read_pointers',
    'reconciliation_divergences',
)


class TeamEvidenceRequestError(ValueError):
    pass


class TeamEvidenceNotFound(LookupError):
    pass


def parse_product_date(value) -> date:
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if not text:
        raise TeamEvidenceRequestError('date_required')
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise TeamEvidenceRequestError('date_invalid') from exc


def parse_team_id(value) -> int:
    if value is None or str(value).strip() == '':
        raise TeamEvidenceRequestError('team_id_required')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise TeamEvidenceRequestError('team_id_invalid') from exc
    if parsed <= 0:
        raise TeamEvidenceRequestError('team_id_invalid')
    return parsed


def build_internal_team_evidence_payload(
    *,
    team_id=None,
    product_date=None,
) -> dict:
    ref = parse_product_date(product_date)
    normalized_team_id = parse_team_id(team_id)
    pitchers = _team_pitchers(normalized_team_id)
    read = _current_team_daily_read(normalized_team_id, ref)
    evidence_objects = _evidence_objects(normalized_team_id, ref, read=read)
    cited_evidence = _cited_evidence_objects(read)
    divergences = _reconciliation_divergences(normalized_team_id, ref)

    if not pitchers and read is None and not evidence_objects and not divergences:
        raise TeamEvidenceNotFound('team_not_found')

    reliever_read_pointers = _reliever_daily_read_pointers(pitchers, ref)
    section_presence = {
        'team_daily_read': read is not None,
        'read_components': bool(read and read.components),
        'cited_evidence_rendered_claims': bool(cited_evidence),
        'evidence_objects': bool(evidence_objects),
        'reliever_daily_read_pointers': bool(reliever_read_pointers),
        'reconciliation_divergences': bool(divergences),
    }

    return {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'request': {
            'team_id': normalized_team_id,
            'date': ref.isoformat(),
            'data_through': ref.isoformat(),
        },
        'team': _team_identity(normalized_team_id, pitchers),
        'target_date': ref.isoformat(),
        'data_through': ref.isoformat(),
        'team_daily_read': _serialize_read(read),
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
        'reliever_daily_read_pointers': reliever_read_pointers,
        'reconciliation_divergences': [
            _serialize_divergence(row) for row in divergences
        ],
        'source_readiness_notes': {
            'stored_fields_only': True,
            'quote_only_rendered_claims': True,
            'optional_sections_present': section_presence,
            'missing_optional_sections': [
                key for key in OPTIONAL_SECTION_KEYS if not section_presence[key]
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


def _team_pitchers(team_id: int) -> list[Pitcher]:
    return (
        Pitcher.query
        .filter(Pitcher.team_id == team_id)
        .order_by(asc(Pitcher.id))
        .all()
    )


def _current_team_daily_read(team_id: int, ref: date) -> ComposedRead | None:
    return (
        ComposedRead.query
        .options(
            selectinload(ComposedRead.components)
            .selectinload(ComposedReadComponent.evidence_citations)
            .selectinload(ComposedReadEvidenceCitation.evidence_object)
            .selectinload(EvidenceObject.citations)
        )
        .filter(ComposedRead.read_type == TEAM_DAILY_READ_TYPE)
        .filter(ComposedRead.subject_type == ComposedRead.SUBJECT_TEAM_DAY)
        .filter(ComposedRead.subject_id == str(team_id))
        .filter(ComposedRead.product_date == ref)
        .filter(ComposedRead.posture == ComposedRead.POSTURE_INTERNAL_ONLY)
        .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_CURRENT)
        .order_by(desc(ComposedRead.id))
        .first()
    )


def _evidence_objects(team_id: int, ref: date, *, read: ComposedRead | None) -> list[EvidenceObject]:
    # Canonical governed authority (SC-03B-01): trusted current team evidence for
    # the exact team + product date, merged with the read's cited evidence.
    return resolve_current_team_evidence(team_id, ref, read=read)


def _cited_evidence_objects(read: ComposedRead | None) -> list[EvidenceObject]:
    return cited_evidence_objects(read)


def _reconciliation_divergences(team_id: int, ref: date) -> list[LegacyReadDivergence]:
    return (
        LegacyReadDivergence.query
        .filter(LegacyReadDivergence.subject_type == LegacyReadDivergence.SUBJECT_TEAM_DAY)
        .filter(LegacyReadDivergence.subject_id == str(team_id))
        .filter(LegacyReadDivergence.product_date == ref)
        .order_by(asc(LegacyReadDivergence.category), asc(LegacyReadDivergence.id))
        .all()
    )


def _reliever_daily_read_pointers(pitchers: list[Pitcher], ref: date) -> list[dict]:
    pitchers_by_id = {row.id: row for row in pitchers}
    if not pitchers_by_id:
        return []
    reads = (
        ComposedRead.query
        .filter(ComposedRead.read_type == RELIEVER_DAILY_READ_TYPE)
        .filter(ComposedRead.subject_type == ComposedRead.SUBJECT_PITCHER_DAY)
        .filter(ComposedRead.subject_id.in_([str(row.id) for row in pitchers]))
        .filter(ComposedRead.product_date == ref)
        .filter(ComposedRead.posture == ComposedRead.POSTURE_INTERNAL_ONLY)
        .filter(ComposedRead.recompute_status == ComposedRead.RECOMPUTE_CURRENT)
        .order_by(asc(ComposedRead.id))
        .all()
    )

    def _sort_key(read):
        pitcher = pitchers_by_id.get(int(read.subject_id))
        return ((pitcher.full_name or '') if pitcher else '', read.id or 0)

    pointers = []
    for read in sorted(reads, key=_sort_key):
        pitcher_id = int(read.subject_id)
        pitcher = pitchers_by_id[pitcher_id]
        pointers.append({
            'read_id': read.id,
            'read_key': read.read_key,
            'pitcher_id': pitcher.id,
            'pitcher_mlb_id': pitcher.mlb_id,
            'pitcher_full_name': pitcher.full_name,
            'completeness_state': read.completeness_state,
            'recompute_status': read.recompute_status,
        })
    return pointers


def _watermark() -> dict:
    return {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }


def _team_identity(team_id: int, pitchers: list[Pitcher]) -> dict:
    pitcher = pitchers[0] if pitchers else None
    return {
        'team_id': team_id,
        'team_name': pitcher.team_name if pitcher else None,
        'team_abbreviation': pitcher.team_abbreviation if pitcher else None,
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


def _iso(value):
    return value.isoformat() if value is not None else None
