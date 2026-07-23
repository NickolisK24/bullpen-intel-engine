"""Canonical Team State V1 payload builder + version registry (SC-02).

The payload builder produces the immutable *intelligence document* that SC-03
will persist as a Share Artifact. It is the authoritative content of the card —
not a rendering. It carries the explicit team authority fields established in
SC-01, the governed team operating-state summary, and governed trust metadata.
It serializes no presentation details, generates no images, and includes no
renderer-specific information.

The builder is deterministic and fails closed: it refuses to produce a payload
unless the eligibility engine says the trust requirements are satisfied, and two
builds from the same governed source produce byte-identical documents (no
build-time timestamps leak into the canonical document).

Contracts are semantically versioned and registered so future payload contracts
(e.g. ``team-state-1.1.0``) can coexist without breaking immutable artifacts
created under earlier versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Mapping, Optional

from team_operations.contracts import (
    READINESS_STATUSES,
    require_team_operations_governance_safe,
)

from services.share_artifact_integrity import to_json_safe
from services.share_artifacts import ShareArtifactEvidenceInput
from services.team_state_eligibility import (
    TEAM_STATE_V1,
    TeamStateEligibilityResult,
    evaluate_team_state_eligibility,
)
from services.team_state_source import TeamStateSource


TEAM_STATE_ARTIFACT_TYPE = 'team_state'
TEAM_STATE_DOCUMENT_CONTRACT = 'baseballos.share_card.team_state'

# Governed, non-forbidden constraint fields that may be carried into the payload.
_CONSTRAINT_FIELDS = ('constraint_id', 'category', 'severity', 'affected_area', 'message')

# Map the governed data_state onto a Share Artifact evidence completeness state.
_DATA_STATE_TO_COMPLETENESS = {
    'fresh': 'complete',
    'historical': 'complete',
    'stale': 'partial',
    'incomplete': 'partial',
    'missing': 'unknown',
    'unknown': 'unknown',
}


class TeamStatePayloadError(Exception):
    """Base error for the Team State payload builder."""


class TeamStatePayloadVersionError(TeamStatePayloadError):
    """Raised when an unknown payload contract version is requested."""


class TeamStatePayloadRefused(TeamStatePayloadError):
    """Raised when a payload is requested for an ineligible source (fail closed)."""

    def __init__(self, eligibility: TeamStateEligibilityResult):
        self.eligibility = eligibility
        super().__init__(
            'Team State payload refused: '
            f'blocking_conditions={list(eligibility.blocking_conditions)}'
        )


@dataclass(frozen=True)
class TeamStatePayload:
    """A built, immutable Team State intelligence document + SC-01 authority."""

    payload_version: str
    artifact_type: str
    team_id: int
    source_snapshot_id: int
    source_sync_run_id: Optional[int]
    product_date: Optional[date]
    document: Mapping[str, Any]
    trust_metadata: Mapping[str, Any]
    evidence: tuple

    def to_share_artifact_kwargs(self) -> dict:
        """Keyword arguments for SC-01 ``publish_new_share_artifact``.

        The canonical document is the artifact payload, the payload version is
        the render contract version, and the governed evidence becomes the
        artifact's frozen evidence. This is the SC-01 persistence bridge; SC-02
        itself never publishes.
        """
        return {
            'artifact_type': self.artifact_type,
            'team_id': self.team_id,
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'render_version': self.payload_version,
            'product_date': self.product_date,
            'payload': dict(self.document),
            'trust_metadata': dict(self.trust_metadata),
            'evidence': list(self.evidence),
        }

    def to_dict(self) -> dict:
        return {
            'payload_version': self.payload_version,
            'artifact_type': self.artifact_type,
            'team_id': self.team_id,
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'product_date': self.product_date.isoformat() if self.product_date else None,
            'document': dict(self.document),
            'trust_metadata': dict(self.trust_metadata),
            'evidence': [
                {
                    'evidence_key': item.evidence_key,
                    'role': item.role,
                    'claim': item.claim,
                    'completeness_state': item.completeness_state,
                    'snapshot': item.snapshot,
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True)
class TeamStatePayloadContract:
    """A versioned Team State payload contract."""

    version: str
    builder: Callable[[TeamStateSource, TeamStateEligibilityResult], dict]
    description: str


class TeamStatePayloadRegistry:
    """Registry of versioned Team State payload contracts.

    Multiple versions coexist; an immutable artifact built under an earlier
    version keeps validating because its version's builder stays registered.
    """

    def __init__(self):
        self._contracts: dict = {}

    def register(self, contract: TeamStatePayloadContract) -> TeamStatePayloadContract:
        if contract.version in self._contracts:
            raise TeamStatePayloadVersionError(
                f'payload contract {contract.version!r} already registered'
            )
        self._contracts[contract.version] = contract
        return contract

    def get(self, version: str) -> TeamStatePayloadContract:
        try:
            return self._contracts[version]
        except KeyError:
            raise TeamStatePayloadVersionError(
                f'unknown Team State payload version {version!r}'
            )

    def versions(self) -> tuple:
        return tuple(sorted(self._contracts))

    def latest(self) -> TeamStatePayloadContract:
        if not self._contracts:
            raise TeamStatePayloadVersionError('no payload contracts registered')
        return self._contracts[max(self._contracts)]


team_state_payload_registry = TeamStatePayloadRegistry()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(value) -> Optional[str]:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _governed_constraints(constraints) -> list:
    governed = []
    for constraint in constraints or ():
        if not isinstance(constraint, Mapping):
            continue
        governed.append({
            key: constraint.get(key)
            for key in _CONSTRAINT_FIELDS
            if key in constraint
        })
    governed.sort(key=lambda item: str(item.get('constraint_id')))
    return governed


def _completeness_for(data_state) -> str:
    return _DATA_STATE_TO_COMPLETENESS.get(data_state, 'unknown')


def _evidence_inputs(source, readiness, status_code, summary, constraints) -> tuple:
    trust_metadata = readiness.get('trust_metadata') if isinstance(readiness, Mapping) else {}
    trust_metadata = trust_metadata if isinstance(trust_metadata, Mapping) else {}
    freshness = readiness.get('freshness') if isinstance(readiness, Mapping) else {}
    freshness = freshness if isinstance(freshness, Mapping) else {}
    data_through = _iso(source.snapshot.data_through) or 'unknown-date'
    base_key = f'team_state:{source.team_id}:{data_through}'

    inputs = [
        ShareArtifactEvidenceInput(
            evidence_key=f'{base_key}:readiness',
            role='team_state_readiness',
            claim=summary,
            completeness_state=_completeness_for(trust_metadata.get('data_state')),
            snapshot={
                'status_code': status_code,
                'contract_state': readiness.get('contract_state'),
                'confidence': trust_metadata.get('confidence'),
                'data_state': trust_metadata.get('data_state'),
                'freshness_state': freshness.get('freshness_state'),
            },
        ),
    ]
    for constraint in constraints:
        inputs.append(ShareArtifactEvidenceInput(
            evidence_key=f"{base_key}:constraint:{constraint.get('constraint_id')}",
            role='team_state_constraint',
            claim=constraint.get('message'),
            completeness_state='complete',
            snapshot={
                'category': constraint.get('category'),
                'severity': constraint.get('severity'),
            },
        ))
    return tuple(inputs)


# ---------------------------------------------------------------------------
# Version 1.0.0 contract
# ---------------------------------------------------------------------------


def _build_team_state_document_v1(
    source: TeamStateSource,
    eligibility: TeamStateEligibilityResult,
) -> dict:
    readiness = source.readiness or {}
    team_block = readiness.get('team') if isinstance(readiness.get('team'), Mapping) else {}
    readiness_block = (
        readiness.get('readiness') if isinstance(readiness.get('readiness'), Mapping) else {}
    )
    trust_metadata = (
        readiness.get('trust_metadata')
        if isinstance(readiness.get('trust_metadata'), Mapping) else {}
    )
    freshness = (
        readiness.get('freshness') if isinstance(readiness.get('freshness'), Mapping) else {}
    )
    status_code = readiness_block.get('status_code')
    summary = readiness_block.get('summary')
    constraints = _governed_constraints(readiness.get('constraints'))
    snapshot = source.snapshot

    document = {
        'contract': TEAM_STATE_DOCUMENT_CONTRACT,
        'payload_version': TEAM_STATE_V1,
        'team': {
            'team_id': source.team_id,
            'team_name': team_block.get('team_name'),
            'team_abbreviation': team_block.get('team_abbreviation'),
        },
        'authority': {
            'source_snapshot_id': snapshot.snapshot_id,
            'source_sync_run_id': snapshot.sync_run_id,
            'data_through': _iso(snapshot.data_through),
            'published_at': _iso(snapshot.published_at),
        },
        'team_state': {
            'status_code': status_code,
            'status_label': READINESS_STATUSES.get(status_code),
            'summary': summary,
            'contract_state': readiness.get('contract_state'),
            'constraints': constraints,
        },
        'trust': {
            'confidence': trust_metadata.get('confidence'),
            'data_state': trust_metadata.get('data_state'),
            'source_evidence_state': trust_metadata.get('source_evidence_state'),
            'governance_state': trust_metadata.get('governance_state'),
            'freshness_state': freshness.get('freshness_state'),
            'trust_state': eligibility.trust_state,
            'ranking_applied': False,
            'selection_made': False,
        },
        'evidence_summary': dict(eligibility.evidence_summary),
    }

    trust_metadata_out = {
        'payload_version': TEAM_STATE_V1,
        'confidence': trust_metadata.get('confidence'),
        'data_state': trust_metadata.get('data_state'),
        'source_evidence_state': trust_metadata.get('source_evidence_state'),
        'governance_state': trust_metadata.get('governance_state'),
        'freshness_state': freshness.get('freshness_state'),
        'contract_state': readiness.get('contract_state'),
        'trust_state': eligibility.trust_state,
        'ranking_applied': False,
        'selection_made': False,
    }

    evidence = _evidence_inputs(source, readiness, status_code, summary, constraints)

    return {
        'document': document,
        'trust_metadata': trust_metadata_out,
        'evidence': evidence,
    }


team_state_payload_registry.register(TeamStatePayloadContract(
    version=TEAM_STATE_V1,
    builder=_build_team_state_document_v1,
    description='Team State Share Card canonical payload, contract v1.0.0.',
))


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_team_state_payload(
    source: TeamStateSource,
    *,
    version: str = TEAM_STATE_V1,
) -> TeamStatePayload:
    """Build the canonical Team State payload, or fail closed.

    Raises ``TeamStatePayloadRefused`` when the eligibility engine refuses (the
    builder must never create a payload if trust requirements are not
    satisfied). Raises ``TeamStatePayloadVersionError`` for an unknown version.
    """
    contract = team_state_payload_registry.get(version)

    eligibility = evaluate_team_state_eligibility(source, payload_version=version)
    if not eligibility.eligible:
        raise TeamStatePayloadRefused(eligibility)

    built = contract.builder(source, eligibility)

    # Canonicalize the document deterministically (sorted keys, normalized
    # dates); the same governed source always yields an identical document.
    document = to_json_safe(built['document'])
    trust_metadata = to_json_safe(built['trust_metadata'])

    # Defense in depth: the served document must carry no forbidden governance
    # field names. Fail closed if it does.
    require_team_operations_governance_safe(document)

    snapshot = source.snapshot
    return TeamStatePayload(
        payload_version=version,
        artifact_type=TEAM_STATE_ARTIFACT_TYPE,
        team_id=source.team_id,
        source_snapshot_id=snapshot.snapshot_id,
        source_sync_run_id=snapshot.sync_run_id,
        product_date=snapshot.data_through,
        document=document,
        trust_metadata=trust_metadata,
        evidence=tuple(built['evidence']),
    )
