# BaseballOS V3 Phase 5 - Team Operations Bullpen Readiness Backend Domain Foundation

## Decision

Status:

```text
V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION_COMPLETE
```

Implemented backend domain foundation:

```text
TEAM_OPERATIONS_BULLPEN_READINESS_DOMAIN_FOUNDATION
```

Recommended next milestone:

```text
BaseballOS V3 Phase 6 Team Operations Bullpen Readiness Internal API Route Integration
```

V3 Phase 5 implements the backend domain foundation for Team Operations
Bullpen Readiness. It creates contract objects, metadata validation,
fail-closed assembly, and backend tests without registering a public route,
changing frontend behavior, or changing the certified Recommendation Engine V2
contract.

## Phase Purpose

The purpose of V3 Phase 5 is to make Team Operations Bullpen Readiness
testable as a backend domain capability before any route or frontend
integration work.

This phase converts the Phase 2 capability definition, Phase 3 implementation
plan, and Phase 4 API contract into a bounded backend domain layer that can:

- assemble a deterministic team-level readiness payload
- expose readiness status vocabulary
- summarize constraints
- summarize workload pressure
- summarize availability distribution
- summarize coverage inventory
- summarize handedness coverage
- expose explanations and limitations
- carry trust metadata
- carry freshness metadata
- carry refusal metadata
- preserve fail-closed behavior
- preserve governance metadata

## Scope

In scope:

- backend Team Operations package creation
- backend readiness contract constants
- backend metadata contract objects
- deterministic readiness assembly
- fail-closed handling for missing trust metadata
- fail-closed handling for missing freshness metadata
- fail-closed handling for explicit refusal input
- backend tests for domain serialization and governance boundaries
- documentation updates

Out of scope:

- public route registration
- frontend UI implementation
- frontend client implementation
- certified Recommendation Engine V2 contract changes
- Recommendation Engine V1 behavior changes
- fatigue formula changes
- ranking behavior
- selection behavior
- prediction behavior
- pitcher-level advice
- matchup advice
- production exposure

## Backend Files Created/Modified

Created:

- `backend/team_operations/__init__.py`
- `backend/team_operations/contracts.py`
- `backend/team_operations/bullpen_readiness.py`
- `backend/tests/test_team_operations_bullpen_readiness.py`
- `docs/V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md`

Modified:

- `README.md`
- `docs/PROJECT_STATE_2026_06.md`
- `docs/V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md`

No frontend runtime files, API route files, Recommendation Engine V2 runtime
files, fatigue formula files, database schema files, or generated artifacts are
modified by this phase.

## Domain Architecture Summary

Phase 5 creates a separate backend domain package:

```text
backend/team_operations/
```

The package is intentionally separate from:

- `backend/recommendation/`
- `backend/api/recommendations.py`
- frontend dashboard components

The domain entrypoint is:

```text
assemble_bullpen_readiness(...)
```

The assembly function accepts internal readiness inputs and produces the Phase
4 contract-shaped payload without registering an endpoint. The function is
deterministic for identical inputs and does not read external data sources.

The implementation uses existing-compatible evidence concepts only:

- availability classifications
- workload categories
- current workload coverage
- availability coverage
- throwing-hand coverage
- trust metadata
- freshness metadata
- refusal metadata

## Contract Summary

The domain payload preserves the Phase 4 top-level contract identity:

```text
capability: team_operations_bullpen_readiness
scope: team_bullpen_readiness
contract: team_operations_bullpen_readiness_api_contract
contract_version: v3_phase_4
```

The payload includes:

- `contract_state`
- `ranking_applied`
- `selection_made`
- `generated_at`
- `team`
- `readiness`
- `constraints`
- `workload_pressure`
- `availability_distribution`
- `coverage_inventory`
- `handedness_coverage`
- `explanations`
- `limitations`
- `trust_metadata`
- `freshness`
- `refusal`
- `fail_closed`

Allowed readiness status codes remain constrained to:

- `operationally_stable`
- `operationally_constrained`
- `operationally_stressed`
- `data_limited`
- `refused`

The payload remains team-level or context-level. It does not emit pitcher
ordering, pitcher guidance, hidden priority fields, matchup advice, or outcome
forecast fields.

## Fail-Closed Behavior

Phase 5 fails closed when required metadata is unavailable or unsafe.

Fail-closed triggers implemented:

- missing trust metadata
- incomplete trust metadata
- unsafe trust governance flags
- missing freshness metadata
- incomplete freshness metadata
- unsupported freshness vocabulary
- explicit refusal input
- forbidden serialized output fields

Fail-closed payloads include:

- `contract_state: refused`
- readiness status `Refused`
- refusal metadata
- reason code
- reason summary
- fail-closed metadata
- safe trust fallback metadata when original trust evidence is missing
- safe freshness fallback metadata when original freshness evidence is missing
- governance flags preserved as false

Fail-closed payloads do not include workload pressure, availability
distribution, coverage inventory, or handedness coverage when required evidence
is unavailable.

## Governance Preservation

Phase 5 explicitly preserves:

```text
ranking_applied === false
selection_made === false
```

It does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- best behavior
- preferred behavior
- recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

The domain layer also rejects forbidden serialized field names except for the
required governance flags:

- `ranking_applied`
- `selection_made`

The user remains the decision maker.

## Testing Coverage

Backend tests are added in:

```text
backend/tests/test_team_operations_bullpen_readiness.py
```

The tests cover:

- successful readiness assembly produces a team-level payload
- governance flags remain false
- missing freshness metadata fails closed
- missing trust metadata fails closed
- explicit refusal input fails closed
- payload contains no ranking fields
- payload contains no selection fields
- payload contains no best, preferred, or recommended labels
- readiness status vocabulary is constrained
- assembly is deterministic for identical inputs
- certified V2 recommendation context still preserves governance flags

The full backend validation suite remains the regression check that certified
Recommendation Engine V2 tests still pass.

## Validation

Required validation for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-5-readiness-domain

cd frontend
npm test

git diff --check
git diff --cached --check
```

Root `npm test` is not required for Phase 5. If no root `package.json` exists,
that is expected and is not a project failure.

## Non-Goals

Phase 5 does not:

- register `/api/team-operations/bullpen-readiness`
- expose a public Team Operations route
- create frontend UI
- create frontend client normalization
- change Recommendation Engine V2 response shape
- change Recommendation Engine V2 fail-closed behavior
- change Recommendation Engine V1 behavior
- change availability thresholds
- change fatigue formulas
- add external data sources
- certify production rollout

## Remaining Risks

Remaining risks:

- The domain foundation is not exposed through a route yet.
- Route request validation for forbidden query parameters still requires a
  later integration phase.
- Frontend rendering, accessibility behavior, and user-facing copy still need
  separate implementation and certification.
- Current tests cover the domain contract but not route serialization because
  no route is registered in this phase.
- Runtime telemetry and monitoring artifact capture are still future rollout
  concerns.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 6 Team Operations Bullpen Readiness Internal API Route Integration
```

The next milestone should integrate the domain foundation through an internal
or explicitly guarded route, preserve the certified Recommendation Engine V2
contract, and add route-level forbidden request field and serialization tests
before any frontend implementation begins.

## Phase 6 Internal Route Integration Follow-Up

BaseballOS V3 Phase 6 is complete and integrates this backend domain foundation
behind:

```text
GET /api/team-operations/bullpen-readiness
```

The Phase 6 route is explicitly:

```text
INTERNAL_NON_PRODUCTION_UNCERTIFIED
```

Phase 6 creates route-level request validation, source input assembly,
fail-closed response behavior, route metadata, and focused backend route tests.
It does not add frontend exposure, production certification, Recommendation
Engine V2 contract changes, ranking behavior, selection behavior, prediction
behavior, best/preferred/recommended behavior, pitcher-level advice, or matchup
advice.

Phase 6 preserves:

```text
ranking_applied === false
selection_made === false
```
