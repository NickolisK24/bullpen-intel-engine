# BaseballOS V4 Phase 5 - Evidence And Explanation Deterministic Builder

## Phase Status

Phase status:

```text
V4_PHASE_5_EVIDENCE_AND_EXPLANATION_DETERMINISTIC_BUILDER_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
BACKEND_BUILDER_ONLY
```

This phase adds the deterministic builder layer for V4 Evidence and
Explanation. It creates reusable helpers that assemble valid explanation
objects from controlled inputs while preserving the Phase 4 explanation-only
contract.

This phase does not integrate V4 explanations with Availability Engine,
Recommendation Engine, Team Operations Bullpen Readiness, Flask routes,
persistence, frontend UI, dashboard behavior, or production rollout surfaces.

## Builder Architecture

Phase 5 adds:

```text
backend/explanations/builders.py
backend/tests/test_v4_explanations_deterministic_builder.py
```

The builder module sits on top of the Phase 4 domain contracts in:

```text
backend/explanations/contracts.py
```

The builder accepts controlled inputs, validates supported vocabularies,
normalizes mappings into Phase 4 dataclasses, attaches governance defaults, and
returns `V4Explanation` objects. It is dependency-light and isolated from
runtime surfaces.

## Helper Functions

Phase 5 adds helpers for:

- `build_explanation(...)`
- `build_evidence_item(...)`
- `build_numeric_evidence(...)`
- `build_percentage_evidence(...)`
- `build_limitation(...)`
- `build_reason(...)`
- `build_reasons(...)`
- `serialize_explanation(...)`
- `stable_json_dumps(...)`

These helpers make explanation, evidence, limitation, reason, and serialization
construction consistent across future internal integrations.

## Deterministic Explanation Creation

`build_explanation(...)` creates a valid `V4Explanation` from:

- scope
- subject type
- subject id
- state explained
- summary
- reason codes
- supporting evidence
- limitations
- freshness reference
- trust reference
- confidence reference
- generated timestamp
- optional explicit explanation id

The builder validates scope, subject type, reason codes, limitation types, and
reference object shapes before constructing an explanation. Invalid input raises
a validation error and cannot produce an explanation object.

## Evidence Assembly

Evidence helpers support generic, numeric, and percentage evidence items.

Evidence items preserve:

- evidence id
- evidence type
- label
- value
- unit
- source
- freshness reference
- trust status
- impact
- optional limitation

Numeric evidence rejects non-numeric values. Percentage evidence rejects
non-numeric values and values outside `0` through `100`.

## Limitation Assembly

`build_limitation(...)` supports all Phase 4 limitation types:

```text
missing_data
stale_data
partial_coverage
uncertified_source
limited_confidence
insufficient_context
```

Unsupported limitation types are rejected before any explanation is produced.
Limitations remain explanation boundaries only. They do not create advice,
recommendation, ranking, selection, prediction, or fail-closed overrides.

## Reason Code Assembly

Reason helpers support the Phase 4 reason-code vocabulary:

```text
WORKLOAD_RECENT_USAGE_ELEVATED
FRESHNESS_STALE_SOURCE
COVERAGE_PARTIAL
TRUST_LIMITED
AVAILABILITY_MONITOR_THRESHOLD_MET
READINESS_DEGRADED_BY_LIMITATIONS
```

Unsupported reason codes fail validation and cannot be attached to an
explanation.

## Governance Behavior

Builder-generated explanations automatically attach a safe governance payload.
Consumers do not need to set governance fields manually.

The generated governance defaults are:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The builder does not accept a governance override. This prevents callers from
accidentally producing explanations with unsafe decision, advice, ranking,
selection, recommendation, or prediction metadata.

## Determinism Guarantees

Phase 5 implements deterministic identifiers when explicit IDs are not
supplied.

Deterministic evidence IDs use:

```text
evidence:<evidence_type>:<sha256 digest prefix>
```

Deterministic explanation IDs use:

```text
explanation:<scope>:<subject_type>:<subject_id>:<sha256 digest prefix>
```

The digest is computed from canonical JSON using sorted keys, compact
separators, ASCII-safe output, and the controlled input fields that define the
evidence item or explanation.

Identical inputs produce identical evidence IDs, explanation IDs, dictionaries,
and stable serialized JSON strings.

Explicit caller-provided IDs are preserved for future integrations that need to
carry a known external reference.

## Serialization Behavior

`serialize_explanation(...)` returns the `V4Explanation.to_dict()` payload and
rejects non-explanation objects.

`stable_json_dumps(...)` produces canonical JSON-compatible output for
determinism checks and future retained evidence comparisons.

## Validation Behavior

The builder fails closed on invalid controlled input by raising validation
errors before returning a domain object.

Validation covers:

- unsupported explanation scopes
- unsupported subject types
- unsupported reason codes
- unsupported limitation types
- invalid freshness reference shapes
- invalid trust reference shapes
- invalid confidence reference shapes
- non-numeric numeric evidence values
- invalid percentage evidence values
- non-explanation serialization inputs

Invalid input cannot produce explanation objects.

## Test Coverage

Backend tests were added in:

```text
backend/tests/test_v4_explanations_deterministic_builder.py
```

Coverage verifies:

- minimal valid explanation creation
- fully populated explanation creation
- multiple evidence items
- multiple limitations
- map-based helper input normalization
- invalid scope rejection
- invalid subject type rejection
- invalid reason-code rejection
- invalid limitation-type rejection
- governance defaults
- deterministic repeated outputs
- deterministic generated IDs
- explicit ID preservation
- stable serialization
- fail-closed invalid input behavior
- absence of prohibited ranking, selection, recommendation, prediction,
  best/preferred arm, hidden priority ordering, pitcher-level advice, and
  matchup-advice fields

Focused validation also re-ran the Phase 4 domain foundation tests to preserve
the underlying contract.

## Intentionally Unimplemented Integrations

Phase 5 intentionally does not implement:

- Availability Engine integration
- Recommendation Engine integration
- Team Operations Bullpen Readiness integration
- Flask API routes
- frontend API clients
- Dashboard UI
- database storage
- external data sources
- public certification
- production rollout approval

Future integrations require separate authorization and certification review.

## Governance Preservation

V4 may explain.

V4 may not decide.

This phase does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred arm behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation

The V4 builder remains an internal explanation-only layer.

## Remaining Risks

- Builder helpers are not yet connected to real BaseballOS availability,
  readiness, or recommendation outputs.
- Future runtime integrations must prove they pass only controlled evidence into
  the builder.
- Future route or frontend work must preserve the generated governance payload
  without turning explanations into advice.
- Additional evidence and reason-code vocabularies may be required once the
  first real integration target is selected.

## Recommended Next Milestone

```text
V4 Phase 6 - Availability Explanation Integration
```

The next milestone should use the deterministic builder to attach internal V4
explanations to an existing governed availability state in a narrowly scoped
backend integration. It should preserve all existing availability calculations,
avoid API and frontend exposure unless separately authorized, and keep V4
explanations explanation-only.
