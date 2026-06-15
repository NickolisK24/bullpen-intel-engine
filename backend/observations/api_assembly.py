"""V5 observation API assembly helpers.

The Phase 6 API uses deterministic supplied state only. This module does not
query persistence, call services, or integrate live runtime data.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from observations.builders import (
    FreshnessObservationBuilder,
    InventoryObservationBuilder,
    ReadinessObservationBuilder,
    TrustObservationBuilder,
    WorkloadPressureObservationBuilder,
    build_observation_collection,
)
from observations.contracts import (
    ObservationCollection,
    ObservationLimitation,
    serialize_collection,
)
from observations.enums import ObservationSeverity, ObservationTrustStatus
from observations.validators import require_collection_payload_valid


OBSERVATION_API_ROUTE = '/api/observations'
OBSERVATION_API_PREVIEW_ROUTE = '/api/observations/preview'
OBSERVATION_API_DOCUMENT = 'docs/V5_PHASE_6_OBSERVATION_API_SURFACE.md'
OBSERVATION_COLLECTION_ID = 'bullpen-observations:deterministic-sample'
STATIC_SAMPLE_GENERATED_AT = '2026-06-04T18:00:00Z'

FAMILY_BUILDERS = (
    ('inventory', InventoryObservationBuilder()),
    ('readiness', ReadinessObservationBuilder()),
    ('workload_pressure', WorkloadPressureObservationBuilder()),
    ('freshness', FreshnessObservationBuilder()),
    ('trust', TrustObservationBuilder()),
)
SUPPORTED_PREVIEW_FAMILIES = frozenset(family for family, _builder in FAMILY_BUILDERS)


def build_sample_observation_collection() -> ObservationCollection | None:
    """Build deterministic sample observations for non-production contract tests."""

    return build_observation_collection(
        OBSERVATION_COLLECTION_ID,
        tuple(
            (builder, _sample_state_for_family(family))
            for family, builder in FAMILY_BUILDERS
        ),
        generated_at=STATIC_SAMPLE_GENERATED_AT,
        freshness=_sample_collection_freshness(),
        confidence=_sample_collection_confidence(),
        limitations=(_sample_collection_limitation(),),
    )


def build_preview_observation_collection(
    payload: Mapping[str, Any] | None,
) -> ObservationCollection | None:
    """Build a preview collection from explicit supplied state.

    The preview path is all-or-empty. If any supplied state is invalid or
    suppressed by a builder, the API layer returns a fail-closed collection
    instead of returning partial observations.
    """

    if not isinstance(payload, Mapping):
        return None

    states = payload.get('states')
    if not isinstance(states, Mapping) or not states:
        return None

    unknown_families = frozenset(str(key) for key in states.keys()).difference(
        SUPPORTED_PREVIEW_FAMILIES
    )
    if unknown_families:
        return None

    builder_inputs = tuple(
        (builder, states[family])
        for family, builder in FAMILY_BUILDERS
        if family in states
    )
    if not builder_inputs:
        return None

    generated_at = payload.get('generated_at') or _generated_at()
    collection = build_observation_collection(
        str(payload.get('collection_id') or 'bullpen-observations:preview'),
        builder_inputs,
        generated_at=generated_at,
        freshness=payload.get('freshness') or _sample_collection_freshness(),
        confidence=payload.get('confidence') or _sample_collection_confidence(),
        limitations=payload.get('limitations') or (_sample_collection_limitation(),),
    )
    if collection is None:
        return None
    if collection.suppressed_count or len(collection.observations) != len(builder_inputs):
        return None
    return collection


def observation_api_payload(
    collection: ObservationCollection,
    *,
    source_mode: str,
    status: str = 'ok',
    trust_status: str = ObservationTrustStatus.SUPPORTED.value,
) -> dict[str, Any]:
    payload = serialize_collection(collection)
    payload.update(
        {
            'status': status,
            'trust_status': trust_status,
            'route_metadata': _route_metadata(source_mode=source_mode),
        }
    )
    require_collection_payload_valid(payload)
    return payload


def fail_closed_observation_api_payload(
    *,
    reason_code: str,
    summary: str,
    source_mode: str,
) -> dict[str, Any]:
    generated_at = _generated_at()
    collection = ObservationCollection(
        collection_id='bullpen-observations:fail-closed',
        observations=(),
        generated_at=generated_at,
        freshness={
            'status': 'unavailable',
            'reason_code': reason_code,
            'generated_at': generated_at,
        },
        confidence={
            'status': 'low',
            'reason': 'Observation output is withheld by the API fail-closed boundary.',
        },
        limitations=(
            ObservationLimitation(
                limitation_type=reason_code,
                summary=summary,
                severity=ObservationSeverity.SIGNIFICANT,
                source='v5_phase_6_observation_api',
            ),
        ),
        suppressed_count=1,
        suppression_reasons=(reason_code,),
    )
    return observation_api_payload(
        collection,
        source_mode=source_mode,
        status='fail_closed',
        trust_status=ObservationTrustStatus.FAIL_CLOSED.value,
    )


def _sample_state_for_family(family: str) -> dict[str, Any]:
    state_by_family = {
        'inventory': {
            'observation_id': 'inventory:sample:2026-06-04',
            'evidence_label': 'Available inventory count',
            'evidence_value': 5,
            'metadata_field': 'available_count',
        },
        'readiness': {
            'observation_id': 'readiness:sample:2026-06-04',
            'evidence_label': 'Readiness limitation count',
            'evidence_value': 2,
            'metadata_field': 'readiness_limitations',
        },
        'workload_pressure': {
            'observation_id': 'workload-pressure:sample:2026-06-04',
            'evidence_label': 'Elevated workload record count',
            'evidence_value': 3,
            'metadata_field': 'elevated_workload_records',
        },
        'freshness': {
            'observation_id': 'freshness:sample:2026-06-04',
            'evidence_label': 'Freshness protection state',
            'evidence_value': 'represented',
            'metadata_field': 'freshness_state',
        },
        'trust': {
            'observation_id': 'trust:sample:2026-06-04',
            'evidence_label': 'Trust limitation state',
            'evidence_value': 'represented',
            'metadata_field': 'trust_state',
        },
    }
    config = state_by_family[family]
    return {
        'observation_id': config['observation_id'],
        'evidence': [
            {
                'evidence_id': f'{family}:sample-evidence:2026-06-04',
                'source': 'baseballos_v5_deterministic_sample_state',
                'source_type': 'trusted_platform_state',
                'label': config['evidence_label'],
                'value': config['evidence_value'],
                'freshness_status': 'static_sample',
                'sample_date': '2026-06-04',
                'generated_at': STATIC_SAMPLE_GENERATED_AT,
                'metadata': {'field': config['metadata_field']},
            }
        ],
        'limitations': [
            {
                'limitation_type': 'deterministic_sample_state',
                'summary': (
                    'Observation is assembled from deterministic supplied '
                    'sample state for Phase 6 API validation.'
                ),
                'source': 'v5_phase_6_observation_api',
            }
        ],
        'confidence': {
            'status': 'medium',
            'reason': 'Supplied deterministic state is sufficient for API contract validation.',
        },
        'freshness': {
            'status': 'static_sample',
            'sample_date': '2026-06-04',
            'generated_at': STATIC_SAMPLE_GENERATED_AT,
        },
        'trust_status': ObservationTrustStatus.SUPPORTED,
        'generated_at': STATIC_SAMPLE_GENERATED_AT,
    }


def _sample_collection_freshness() -> dict[str, Any]:
    return {
        'status': 'static_sample',
        'sample_date': '2026-06-04',
        'generated_at': STATIC_SAMPLE_GENERATED_AT,
    }


def _sample_collection_confidence() -> dict[str, Any]:
    return {
        'status': 'medium',
        'reason': 'Deterministic sample observations satisfy the Phase 6 API contract.',
    }


def _sample_collection_limitation() -> ObservationLimitation:
    return ObservationLimitation(
        limitation_type='deterministic_sample_state',
        summary=(
            'The Phase 6 API surface uses deterministic sample state until '
            'separate runtime integration is authorized.'
        ),
        source='v5_phase_6_observation_api',
    )


def _route_metadata(*, source_mode: str) -> dict[str, Any]:
    return {
        'route': OBSERVATION_API_ROUTE,
        'preview_route': OBSERVATION_API_PREVIEW_ROUTE,
        'surface': 'v5_bullpen_intelligence_observation_api',
        'document': OBSERVATION_API_DOCUMENT,
        'source_mode': source_mode,
        'read_only': True,
        'frontend_exposure': False,
        'database_required': False,
        'live_runtime_integration': False,
        'sequence_basis': 'family_sequence',
    }


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
