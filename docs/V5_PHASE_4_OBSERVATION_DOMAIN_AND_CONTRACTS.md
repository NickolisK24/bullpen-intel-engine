# BaseballOS V5 Phase 4 - Observation Domain And Contracts

## Phase Status

Phase status:

```text
V5_PHASE_4_OBSERVATION_DOMAIN_AND_CONTRACTS_COMPLETE
```

Certification roadmap status:

```text
V5_PHASE_4_BACKEND_FOUNDATION_CERTIFIED
```

Capability track:

```text
V5_BULLPEN_INTELLIGENCE_SURFACE
```

Implementation status:

```text
BACKEND_DOMAIN_CONTRACTS_ONLY
```

V5 Phase 4 implements the backend domain and contract foundation for future
Bullpen Intelligence observations. It does not implement observation builders,
API routes, frontend UI, database migrations, runtime observation generation,
ranking, selection, prediction, matchup advice, pitcher advice, or automated
decision-making.

## 1. Implemented Scope

Phase 4 adds a backend-only `observations` package:

- `backend/observations/enums.py`
- `backend/observations/contracts.py`
- `backend/observations/validators.py`
- `backend/observations/__init__.py`

It also adds focused contract coverage:

- `backend/tests/test_observation_contracts.py`

Implemented scope:

- governed observation enum vocabularies
- backend dataclass contracts
- serialization helpers
- contract validators
- prohibited-language validation
- governance field validation
- collection serialization
- focused unit tests

## 2. Observation Vocabularies

Phase 4 defines controlled vocabularies for:

- `ObservationType`
- `ObservationFamily`
- `ObservationSeverity`
- `ObservationTrustStatus`

Observation families align to the V5 Phase 2 taxonomy:

- inventory
- readiness
- workload pressure
- constraint
- freshness
- trust
- availability movement
- snapshot change

Severity values are:

- informational
- monitor
- elevated
- significant

Severity is descriptive display metadata only. It is not ranking,
recommendation strength, pitcher priority, action priority, selection, or
decision automation.

## 3. Observation Contracts

Phase 4 defines:

- `ObservationEvidence`
- `ObservationLimitation`
- `BullpenObservation`
- `ObservationCollection`

`BullpenObservation` supports:

- `observation_id`
- `observation_type`
- `family`
- `severity`
- `title`
- `summary`
- `evidence`
- `limitations`
- `confidence`
- `freshness`
- `trust_status`
- `explanation_reference`
- `generated_at`
- `ranking_applied`
- `selection_made`

Required governance defaults are enforced by the dataclass contracts:

```text
ranking_applied === false
selection_made === false
```

The governance fields are not constructor-configurable to true in Phase 4.

## 4. Validation Guarantees

Phase 4 validators enforce:

- observation type is present and uses approved vocabulary
- observation family is present and uses approved vocabulary
- observation severity is present and uses approved vocabulary
- observation title is present
- observation summary is present
- observation evidence includes at least one item
- observation freshness metadata is present
- observation confidence metadata is present
- observation trust status is present and uses approved vocabulary
- `ranking_applied` remains false
- `selection_made` remains false
- title and summary reject prohibited recommendation-drift language
- nested payloads reject forbidden ranking, selection, recommendation,
  matchup, prediction, and hidden-priority fields

The prohibited-language validator conservatively rejects terms including:

- use
- best
- preferred
- should close
- manager should
- recommend
- pick
- choose
- start him
- sit him
- matchup advantage

## 5. Serialization Guarantees

Phase 4 serialization helpers return plain dictionaries:

- `serialize_observation`
- `serialize_collection`

Serialization preserves:

- evidence
- limitations
- freshness metadata
- confidence metadata
- trust status
- explanation reference
- `ranking_applied: false`
- `selection_made: false`

The serialized contract shape is intended for future read-only API work, but
Phase 4 does not expose an API route.

## 6. Test Coverage

Phase 4 adds focused backend tests proving:

- valid observation contracts serialize correctly
- missing evidence fails validation
- missing freshness or trust fails validation
- `ranking_applied` cannot become true
- `selection_made` cannot become true
- prohibited language fails validation
- severity remains descriptive only
- collection serialization works
- nested forbidden fields are detected

The tests do not require database access, external services, API routes,
frontend assets, or live-data observation generation.

## 7. Governance Boundary

V5 observations must remain:

```text
OBSERVATIONAL
DESCRIPTIVE
TRUST_AWARE
EXPLAINABLE
GOVERNED
```

Phase 4 does not authorize:

- observation builders
- API routes
- frontend UI
- database migrations
- runtime observation generation
- ranking
- selection
- pitcher recommendations
- matchup advice
- best-arm language
- closer/setup/role advice
- prediction
- automated decision-making

## 8. Next Phase Boundary

Recommended next milestone:

```text
V5_PHASE_5_OBSERVATION_BUILDER_FOUNDATION
```

Phase 5 may introduce deterministic observation builders from existing trusted
V1-V4 state. Phase 5 must preserve the Phase 4 contracts, validators,
serialization guarantees, prohibited-language safeguards, and governance
invariants unless a later governance record explicitly changes that boundary.

Phase 5 must still not expose API routes, frontend UI, database migrations,
ranking, selection, prediction, matchup advice, pitcher advice, or automated
decision-making unless separately authorized.

## Final Boundary

This document certifies only the V5 Phase 4 backend observation domain and
contract foundation.

It does not certify observation builders, API surfaces, frontend surfaces,
runtime observations, rollout readiness, production readiness, ranking,
selection, prediction, pitcher recommendations, matchup advice, best-arm
language, role advice, or automated decision-making.
