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
from services.team_state_public_copy import build_public_copy
from services.team_state_source import TeamStateSource


# The revised canonical public-copy contract (SC-04B). It carries the same
# governed intelligence as v1.0.0 plus a backend-owned, deterministic,
# baseball-native ``public_copy`` block (public state, headline, why sentence,
# reader-facing evidence, freshness/trust/limitation language, alt text,
# platform-neutral description). Meaning-bearing copy lives in the payload, so it
# automatically participates in the equivalence + integrity hashes. Legacy
# v1.0.0 artifacts remain immutable and publicly readable under their own version.
TEAM_STATE_V1_1 = 'team-state-1.1.0'

# The card-baseline contract (SC-04B v1.2). It carries everything v1.1.0 carries
# plus the code-rendered Team State card's two backend-owned data blocks — a
# four-metric ``readiness_summary`` and a bounded, deterministically-ordered
# ``reliever_evidence`` table — grouped under a single ``card`` block, alongside a
# frozen ``artifact_context`` (scope-aware publication labels + data_through). It
# adds NO performance metrics or league ranks (unsupported without a
# team-at-appearance authority) and requires NO DB migration: ``payload`` /
# ``trust_metadata`` are ``db.JSON`` and ``SHARE_ARTIFACT_SCHEMA_VERSION`` stays
# ``1.0.0``. Legacy 1.0.0 / 1.1.0 artifacts remain immutable and readable under
# their own versions.
TEAM_STATE_V1_2 = 'team-state-1.2.0'

# The version new artifacts are generated under. Legacy versions stay registered.
TEAM_STATE_LATEST = TEAM_STATE_V1_2


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


def _durable_limitations(limitations) -> list:
    """Drop transient runtime limitations so only durable evidence caveats freeze.

    A transient limitation (a sync momentarily running at generation time) recovers on
    the next completed sync; freezing it into an immutable artifact would assert it
    forever. Durable limitations (bounded partial coverage, stale source) pass through.
    """
    from services.sync_metadata import TRANSIENT_LIMITATION_TEXTS
    return [
        item for item in (limitations or [])
        if item not in TRANSIENT_LIMITATION_TEXTS
    ]


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
            # SC-03B-07: preserve DURABLE governed trust limitations (e.g. the bounded
            # partial-active-bullpen-coverage note that keeps a medium read honest) on
            # the immutable document, so a published medium artifact never presents a
            # partial read as complete. TRANSIENT runtime limitations (a sync in
            # progress) are dropped here so a momentary process state is never frozen
            # into an immutable public artifact. Deterministic (no build-time content).
            'limitations': _durable_limitations(trust_metadata.get('limitations')),
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
# Version 1.1.0 contract — v1.0.0 + backend-owned canonical public copy (SC-04B)
# ---------------------------------------------------------------------------


def _build_team_state_document_v1_1(
    source: TeamStateSource,
    eligibility: TeamStateEligibilityResult,
) -> dict:
    """v1.0.0 governed document + a deterministic, backend-owned public-copy block.

    The public copy is produced by the canonical copy authority from governed
    facts only. It fails closed (no artifact) if the internal status has no public
    Team State or if any public field carries banned internal language. No AI, no
    external language service, no build-time timestamp — identical governed input
    yields a byte-identical document.
    """
    built = _build_team_state_document_v1(source, eligibility)
    document = built['document']

    readiness = source.readiness if isinstance(source.readiness, Mapping) else {}
    trust_metadata = (
        readiness.get('trust_metadata')
        if isinstance(readiness.get('trust_metadata'), Mapping) else {}
    )
    team_block = document.get('team') or {}
    team_state = document.get('team_state') or {}
    trust = document.get('trust') or {}
    active_bullpen_coverage = trust_metadata.get('active_bullpen_coverage')

    # The public copy is derived from the RAW governed constraints (which retain
    # the governed ``count`` that the v1.0.0 document intentionally strips), in the
    # same canonical constraint_id order the document uses. The reader-facing
    # receipts are then frozen into public_copy.evidence.
    raw_constraints = sorted(
        (c for c in (readiness.get('constraints') or ()) if isinstance(c, Mapping)),
        key=lambda c: str(c.get('constraint_id')),
    )

    public_copy = build_public_copy(
        team_name=team_block.get('team_name'),
        team_abbreviation=team_block.get('team_abbreviation'),
        status_code=team_state.get('status_code'),
        confidence=trust.get('confidence'),
        constraints=raw_constraints,
        limitations=trust.get('limitations') or (),
        active_bullpen_coverage=active_bullpen_coverage,
        product_date=(document.get('authority') or {}).get('data_through'),
    )

    document['payload_version'] = TEAM_STATE_V1_1
    team_state['public_state'] = public_copy['state']
    if isinstance(active_bullpen_coverage, Mapping):
        trust['active_bullpen_coverage'] = dict(active_bullpen_coverage)
    document['public_copy'] = public_copy

    built['trust_metadata'] = dict(built['trust_metadata'])
    built['trust_metadata']['payload_version'] = TEAM_STATE_V1_1
    return built


team_state_payload_registry.register(TeamStatePayloadContract(
    version=TEAM_STATE_V1_1,
    builder=_build_team_state_document_v1_1,
    description=(
        'Team State Share Card canonical payload, contract v1.1.0 — adds the '
        'backend-owned deterministic public-copy block (SC-04B).'
    ),
))


# ---------------------------------------------------------------------------
# Version 1.2.0 contract — v1.1.0 + the code-rendered card's data blocks (SC-04B)
# ---------------------------------------------------------------------------


def _card_artifact_context(source, data_through_iso) -> dict:
    """Frozen, deterministic publication-scope context for the card.

    Scope labels come from the DURABLE source-authority discriminator
    (``subject_type``) via the single centralized scope authority — never the
    numeric ``source_snapshot_id`` — so a team-progressive artifact and a league
    artifact each describe their own scope, frozen immutably. The artifact's OWN
    ``generated_at`` / ``published_at`` are intentionally NOT frozen here (they are
    unknown at build time and non-deterministic); the public read supplies them
    from the artifact columns.
    """
    from services.share_artifact_scope import scope_labels_for_subject_type

    scope = scope_labels_for_subject_type(getattr(source.snapshot, 'subject_type', None))
    return {
        'publication_scope': scope['publication_scope'],
        'publication_label': scope['display_label'],
        'historical_note': scope['historical_note'],
        'data_through': data_through_iso,
    }


def _build_team_state_document_v1_2(
    source: TeamStateSource,
    eligibility: TeamStateEligibilityResult,
) -> dict:
    """v1.1.0 governed document + the code-rendered card's backend-owned data blocks.

    Adds a single ``card`` block: a frozen ``artifact_context`` (scope + data_through),
    the canonical ``team`` identity, the public ``state`` (public state + headline +
    why, reused from the deterministic public copy), the four-metric
    ``readiness_summary`` and bounded ``reliever_evidence`` from the card-metrics
    authority, a reader-facing ``trust`` triplet, and durable ``limitations``. All
    baseball meaning is backend-owned; nothing here is a performance metric or a
    league rank. Deterministic: the same governed slate + data yields a
    byte-identical document (no build-time clock).
    """
    from services.team_state_card_metrics import build_team_state_card_metrics

    built = _build_team_state_document_v1_1(source, eligibility)
    document = built['document']

    public_copy = document.get('public_copy') if isinstance(document.get('public_copy'), Mapping) else {}
    team_block = document.get('team') or {}
    trust_block = document.get('trust') or {}
    public_state = public_copy.get('state') if isinstance(public_copy.get('state'), Mapping) else {}

    data_through = source.snapshot.data_through
    data_through_iso = _iso(data_through)

    if isinstance(data_through, date):
        metrics = build_team_state_card_metrics(source.team_id, reference_date=data_through)
    else:
        # No slate to anchor to (eligibility should preclude this) — fail closed to
        # empty card data rather than an unanchored computation.
        metrics = {'readiness_summary': {}, 'reliever_evidence': [], 'evidence_window': {}}

    card = {
        'card_version': TEAM_STATE_V1_2,
        'artifact_context': _card_artifact_context(source, data_through_iso),
        'team': {
            'team_id': team_block.get('team_id'),
            'canonical_name': team_block.get('team_name'),
            'abbreviation': team_block.get('team_abbreviation'),
        },
        'state': {
            'public_state': public_state.get('public_code'),
            'public_label': public_state.get('public_label'),
            'headline': public_copy.get('headline'),
            'why': public_copy.get('why'),
        },
        'readiness_summary': metrics.get('readiness_summary') or {},
        'reliever_evidence': list(metrics.get('reliever_evidence') or ()),
        'trust': {
            'confidence': trust_block.get('confidence'),
            'coverage_statement': public_copy.get('freshness_line'),
            'source_statement': public_copy.get('trust_line'),
        },
        # Durable only: the public-copy limitations are already derived from the
        # DURABLE governed trust limitations (transient runtime states dropped).
        'limitations': [str(item) for item in (public_copy.get('limitations') or ())],
        'evidence_window': metrics.get('evidence_window') or {},
    }

    document['payload_version'] = TEAM_STATE_V1_2
    document['card'] = card

    built['trust_metadata'] = dict(built['trust_metadata'])
    built['trust_metadata']['payload_version'] = TEAM_STATE_V1_2
    return built


team_state_payload_registry.register(TeamStatePayloadContract(
    version=TEAM_STATE_V1_2,
    builder=_build_team_state_document_v1_2,
    description=(
        'Team State Share Card canonical payload, contract v1.2.0 — adds the '
        'code-rendered card data blocks (readiness_summary + bounded reliever '
        'evidence + scope-aware artifact_context), no performance metrics or ranks.'
    ),
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
