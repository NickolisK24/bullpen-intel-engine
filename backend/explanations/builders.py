"""Deterministic builders for V4 Evidence and Explanation objects.

The builders in this module assemble Phase 4 domain objects from controlled
inputs. They do not integrate with Availability Engine, Recommendation Engine,
Team Operations Readiness, API routes, database state, or frontend surfaces.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from explanations.contracts import (
    V4Confidence,
    V4EvidenceItem,
    V4Explanation,
    V4FreshnessReference,
    V4GovernancePayload,
    V4Limitation,
    V4Reason,
    V4TrustReference,
    validate_explanation_scope,
    validate_limitation_type,
    validate_reason_code,
    validate_subject_type,
)


def stable_json_dumps(payload: Any) -> str:
    """Return canonical JSON for deterministic IDs and serialization checks."""

    return json.dumps(
        payload,
        default=str,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )


def _stable_identifier(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(stable_json_dumps(payload).encode('utf-8')).hexdigest()
    return f'{prefix}:{digest[:16]}'


def _freshness_reference(
    freshness: V4FreshnessReference | Mapping[str, Any] | None,
) -> V4FreshnessReference:
    if freshness is None:
        return V4FreshnessReference()
    if isinstance(freshness, V4FreshnessReference):
        return freshness
    if isinstance(freshness, Mapping):
        return V4FreshnessReference(**dict(freshness))
    raise ValueError('freshness must be a V4FreshnessReference, mapping, or None.')


def _trust_reference(
    trust: V4TrustReference | Mapping[str, Any] | None,
) -> V4TrustReference:
    if trust is None:
        return V4TrustReference()
    if isinstance(trust, V4TrustReference):
        return trust
    if isinstance(trust, Mapping):
        return V4TrustReference(**dict(trust))
    raise ValueError('trust must be a V4TrustReference, mapping, or None.')


def _confidence_reference(
    confidence: V4Confidence | Mapping[str, Any] | None,
) -> V4Confidence:
    if confidence is None:
        return V4Confidence()
    if isinstance(confidence, V4Confidence):
        return confidence
    if isinstance(confidence, Mapping):
        return V4Confidence(**dict(confidence))
    raise ValueError('confidence must be a V4Confidence, mapping, or None.')


def build_reason(code: str) -> V4Reason:
    """Build a validated V4 reason from a stable reason code."""

    validate_reason_code(code)
    return V4Reason.from_code(code)


def build_reasons(reason_codes: Sequence[str] | None = None) -> tuple[V4Reason, ...]:
    """Build validated V4 reasons while preserving caller-provided order."""

    return tuple(build_reason(code) for code in reason_codes or ())


def build_limitation(
    *,
    limitation_type: str,
    summary: str,
    severity: str = 'informational',
    affected_scopes: Sequence[str] | None = None,
    requires_refusal: bool = False,
) -> V4Limitation:
    """Build a validated V4 limitation."""

    validate_limitation_type(limitation_type)
    return V4Limitation(
        limitation_type=limitation_type,
        severity=severity,
        summary=summary,
        affected_scopes=tuple(affected_scopes or ()),
        requires_refusal=requires_refusal,
    )


def _limitation_reference(
    limitation: V4Limitation | Mapping[str, Any] | None,
) -> V4Limitation | None:
    if limitation is None:
        return None
    if isinstance(limitation, V4Limitation):
        return limitation
    if isinstance(limitation, Mapping):
        return build_limitation(**dict(limitation))
    raise ValueError('limitation must be a V4Limitation, mapping, or None.')


def _limitation_tuple(
    limitations: Sequence[V4Limitation | Mapping[str, Any]] | None,
) -> tuple[V4Limitation, ...]:
    return tuple(
        resolved
        for resolved in (_limitation_reference(limitation) for limitation in limitations or ())
        if resolved is not None
    )


def _evidence_reference(
    evidence: V4EvidenceItem | Mapping[str, Any],
) -> V4EvidenceItem:
    if isinstance(evidence, V4EvidenceItem):
        return evidence
    if isinstance(evidence, Mapping):
        return build_evidence_item(**dict(evidence))
    raise ValueError('supporting_evidence must contain V4EvidenceItem objects or mappings.')


def _evidence_tuple(
    evidence_items: Sequence[V4EvidenceItem | Mapping[str, Any]] | None,
) -> tuple[V4EvidenceItem, ...]:
    return tuple(_evidence_reference(evidence) for evidence in evidence_items or ())


def build_evidence_item(
    *,
    evidence_type: str,
    label: str,
    value: Any,
    evidence_id: str | None = None,
    unit: str | None = None,
    source: str | None = None,
    freshness: V4FreshnessReference | Mapping[str, Any] | None = None,
    trust_status: str = 'unknown',
    impact: str | None = None,
    limitation: V4Limitation | Mapping[str, Any] | None = None,
) -> V4EvidenceItem:
    """Build a validated evidence item with a deterministic ID when omitted."""

    freshness_reference = _freshness_reference(freshness)
    limitation_reference = _limitation_reference(limitation)
    resolved_evidence_id = evidence_id or _stable_identifier(
        f'evidence:{evidence_type}',
        {
            'evidence_type': evidence_type,
            'label': label,
            'value': value,
            'unit': unit,
            'source': source,
            'freshness': freshness_reference.to_dict(),
            'trust_status': trust_status,
            'impact': impact,
            'limitation': limitation_reference.to_dict()
            if limitation_reference
            else None,
        },
    )

    return V4EvidenceItem(
        evidence_id=resolved_evidence_id,
        evidence_type=evidence_type,
        label=label,
        value=value,
        unit=unit,
        source=source,
        freshness=freshness_reference,
        trust_status=trust_status,
        impact=impact,
        limitation=limitation_reference,
    )


def build_numeric_evidence(
    *,
    evidence_type: str,
    label: str,
    value: int | float,
    unit: str,
    evidence_id: str | None = None,
    source: str | None = None,
    freshness: V4FreshnessReference | Mapping[str, Any] | None = None,
    trust_status: str = 'unknown',
    impact: str | None = None,
    limitation: V4Limitation | Mapping[str, Any] | None = None,
) -> V4EvidenceItem:
    """Build numeric evidence while rejecting non-numeric values."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('numeric evidence value must be an int or float.')

    return build_evidence_item(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        label=label,
        value=value,
        unit=unit,
        source=source,
        freshness=freshness,
        trust_status=trust_status,
        impact=impact,
        limitation=limitation,
    )


def build_percentage_evidence(
    *,
    label: str,
    value: int | float,
    evidence_type: str = 'percentage_metric',
    evidence_id: str | None = None,
    source: str | None = None,
    freshness: V4FreshnessReference | Mapping[str, Any] | None = None,
    trust_status: str = 'unknown',
    impact: str | None = None,
    limitation: V4Limitation | Mapping[str, Any] | None = None,
) -> V4EvidenceItem:
    """Build percentage evidence with a normalized percent unit."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('percentage evidence value must be an int or float.')
    if value < 0 or value > 100:
        raise ValueError('percentage evidence value must be between 0 and 100.')

    return build_evidence_item(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        label=label,
        value=value,
        unit='percent',
        source=source,
        freshness=freshness,
        trust_status=trust_status,
        impact=impact,
        limitation=limitation,
    )


def _explanation_id(
    *,
    scope: str,
    subject_type: str,
    subject_id: str,
    state_explained: str,
    summary: str,
    reason_codes: Sequence[str],
    evidence_items: Sequence[V4EvidenceItem],
    limitations: Sequence[V4Limitation],
    freshness: V4FreshnessReference,
    trust: V4TrustReference,
    confidence: V4Confidence,
    generated_at: str | None,
) -> str:
    return _stable_identifier(
        f'explanation:{scope}:{subject_type}:{subject_id}',
        {
            'scope': scope,
            'subject_type': subject_type,
            'subject_id': subject_id,
            'state_explained': state_explained,
            'summary': summary,
            'reason_codes': list(reason_codes),
            'supporting_evidence': [
                evidence.to_dict() for evidence in evidence_items
            ],
            'limitations': [limitation.to_dict() for limitation in limitations],
            'freshness': freshness.to_dict(),
            'trust': trust.to_dict(),
            'confidence': confidence.to_dict(),
            'generated_at': generated_at,
        },
    )


def build_explanation(
    *,
    scope: str,
    subject_type: str,
    subject_id: str,
    state_explained: str,
    summary: str,
    reason_codes: Sequence[str] | None = None,
    supporting_evidence: Sequence[V4EvidenceItem | Mapping[str, Any]] | None = None,
    limitations: Sequence[V4Limitation | Mapping[str, Any]] | None = None,
    freshness: V4FreshnessReference | Mapping[str, Any] | None = None,
    trust: V4TrustReference | Mapping[str, Any] | None = None,
    confidence: V4Confidence | Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    explanation_id: str | None = None,
) -> V4Explanation:
    """Build a deterministic V4 explanation object from controlled inputs."""

    resolved_scope = validate_explanation_scope(scope)
    resolved_subject_type = validate_subject_type(subject_type)
    resolved_reason_codes = tuple(reason_codes or ())
    reasons = build_reasons(resolved_reason_codes)
    evidence_items = _evidence_tuple(supporting_evidence)
    limitation_items = _limitation_tuple(limitations)
    freshness_reference = _freshness_reference(freshness)
    trust_reference = _trust_reference(trust)
    confidence_reference = _confidence_reference(confidence)
    resolved_explanation_id = explanation_id or _explanation_id(
        scope=resolved_scope,
        subject_type=resolved_subject_type,
        subject_id=subject_id,
        state_explained=state_explained,
        summary=summary,
        reason_codes=resolved_reason_codes,
        evidence_items=evidence_items,
        limitations=limitation_items,
        freshness=freshness_reference,
        trust=trust_reference,
        confidence=confidence_reference,
        generated_at=generated_at,
    )

    return V4Explanation(
        explanation_id=resolved_explanation_id,
        scope=resolved_scope,
        subject_type=resolved_subject_type,
        subject_id=subject_id,
        state_explained=state_explained,
        summary=summary,
        primary_reasons=reasons,
        supporting_evidence=evidence_items,
        limitations=limitation_items,
        freshness=freshness_reference,
        trust=trust_reference,
        confidence=confidence_reference,
        governance=V4GovernancePayload(),
        generated_at=generated_at,
    )


def serialize_explanation(explanation: V4Explanation) -> dict[str, Any]:
    """Serialize a V4 explanation into a JSON-compatible stable dictionary."""

    if not isinstance(explanation, V4Explanation):
        raise ValueError('explanation must be a V4Explanation.')
    return explanation.to_dict()
