# BaseballOS V2.5 Phase 20 - Prototype Promotion and Deprecation Policy

## Decision

BaseballOS V2.5 Phase 20 establishes the official lifecycle policy for
promoting prototype and experimental surfaces and retiring production,
supported, legacy, and deprecated surfaces.

This phase is a governance policy phase only. It does not add features,
change Recommendation Engine behavior, change fatigue formulas, expand API
contracts, add ranking logic, add selection logic, or add prediction logic.

Decision:

```text
PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY_ESTABLISHED
```

## Scope

This policy governs lifecycle transitions for all BaseballOS user-facing,
API-facing, operational, and maintenance surfaces.

Classification states:

```text
Prototype -> Experimental -> Supported -> Production
Production -> Legacy -> Deprecated -> Removed
```

The policy applies to:

- frontend routes and panels
- backend routes and APIs
- shared frontend API helpers
- operational/admin endpoints
- analysis scripts and reports
- maintenance utilities
- documentation-backed governance tools

## Classification Definitions

| Classification | Definition |
| --- | --- |
| PROTOTYPE | Early surface used to explore a product idea. It may use sample data or incomplete contracts and must be visibly labeled as not production. |
| EXPERIMENTAL | Surface used for analysis, validation, or constrained review. It may use real data, but it is not production user decision support. |
| SUPPORTED | Maintained surface with an owner, documentation, tests appropriate to risk, and defined failure behavior. |
| PRODUCTION | User-facing, API-facing, or operationally relied-upon surface approved for the current product boundary. |
| LEGACY | Older production or supported surface retained for compatibility or transition. It may be replaced but is not yet deprecated. |
| DEPRECATED | Surface with a documented replacement and migration path. New usage is discouraged or blocked. |
| REMOVED | Surface no longer available after migration window completion and governance approval. |

## Promotion Policy

### Prototype -> Experimental

A prototype may become experimental only after all minimum criteria are met:

- defined purpose
- named owner or owning area
- explicit current classification
- basic documentation
- known data source or sample-data statement
- known users or review audience
- visible non-production labeling where user-facing
- known limitations
- known risks
- initial governance review

Prototype promotion is blocked when the surface:

- is unlabeled or could be mistaken for production
- has no documented purpose
- has no owner
- uses unclear data provenance
- implies ranking, selection, prediction, or final decision support
- weakens existing trust, freshness, refusal, or fail-closed boundaries

### Experimental -> Supported

An experimental surface may become supported only after all minimum criteria
are met:

- documented purpose and owner
- documented limitations
- documented data provenance
- documented failure behavior
- test coverage appropriate to surface risk
- governance review
- security/access review if operational or admin-only
- user-facing copy review if visible in the app
- no unresolved governance blockers
- clear support expectations

For intelligence surfaces, the following must also exist before supported
status:

- trust metadata requirements
- freshness metadata requirements
- refusal behavior
- fail-closed behavior
- anti-ranking review
- anti-selection review
- anti-prediction review

Experimental promotion is blocked when the surface:

- lacks test coverage for its critical behavior
- lacks documented limitations
- bypasses current trust or freshness visibility
- exposes raw source data as production intelligence
- could be interpreted as a prediction or recommendation without governance
- depends on unreviewed ranking, scoring, priority, or preference logic

### Supported -> Production

A supported surface may become production only after all production criteria
are met:

- certification review
- API contract review when an API is involved
- frontend contract review when a UI is involved
- production readiness review
- rollout review
- documented operational ownership
- documented monitoring expectations
- regression tests appropriate to risk
- accessibility review for user-facing UI
- mobile review for user-facing UI
- security/access review for admin or operational behavior
- documented fallback and failure modes
- documentation updates in current status surfaces

For intelligence surfaces, production eligibility additionally requires:

- trust metadata
- freshness metadata
- refusal behavior
- fail-closed behavior
- limitation visibility
- explanation visibility
- anti-ranking review
- anti-selection review
- anti-prediction review
- no best/preferred/recommended option behavior
- no automated decision behavior

Production promotion is blocked when the surface:

- lacks certification evidence
- lacks a rollout decision
- changes Recommendation Engine behavior without a separate approved phase
- changes fatigue formulas without a separate approved phase
- expands API contracts without a separate approved phase
- adds ranking, selection, prediction, or automated decisions
- allows trust, freshness, refusal, or fail-closed metadata to be bypassed

## Deprecation Policy

### Production -> Legacy

A production surface may be reclassified as legacy when at least one condition
is true:

- replacement exists
- maintenance burden exceeds current value
- strategic retirement is approved
- production usage is no longer central to the product boundary
- a safer or more governed path exists

Before legacy classification, the review must document:

- current users or consumers
- replacement or ongoing compatibility path
- known risks
- maintenance expectations
- owner
- whether new usage remains allowed

### Legacy -> Deprecated

A legacy surface may become deprecated only after all conditions are met:

- migration path exists
- replacement is documented
- deprecation notice is documented
- owner is documented
- removal criteria are documented
- compatibility impact is understood
- tests or validation cover the migration path where applicable

Deprecation is blocked when:

- no replacement or migration path exists
- production consumers cannot be identified
- the removal impact is unknown
- the surface still provides a required production capability

### Deprecated -> Removed

A deprecated surface may be removed only after all conditions are met:

- documented replacement exists
- migration window is complete
- no active production dependency remains
- governance approval is recorded
- documentation is updated
- tests are updated or removed intentionally
- deployment and rollback impact is understood
- final validation passes

Removal is blocked when:

- active consumers remain
- migration status is unknown
- replacement behavior is not production-ready
- removal would weaken trust, freshness, refusal, fail-closed, accessibility,
  mobile, security, or operational guarantees

## Intelligence Surface Requirements

Any future intelligence surface seeking supported or production status must
define and validate:

- trust metadata
- freshness metadata
- refusal behavior
- fail-closed behavior
- limitation visibility
- explanation visibility
- data provenance
- confidence semantics when applicable
- stale-data handling
- missing-data handling
- degraded-data handling
- anti-ranking review
- anti-selection review
- anti-prediction review
- user-facing copy review
- accessibility text review
- mobile presentation review
- backend/API contract review if exposed by API
- frontend contract review if rendered in UI

Mandatory governance state remains:

```text
ranking_applied === false
selection_made === false
```

Future promotions must not bypass:

- governance review
- certification review
- rollout review

## Current Surface Review

Phase 20 reviewed the currently classified prototype and experimental surfaces
from Phase 19.

No current classification correction is required.

### Prospect Pipeline

Current classification:

```text
PROTOTYPE
```

Promotion path:

```text
Prototype -> Experimental
```

Promotion blockers:

- uses illustrative sample data
- not a live minor-league data feed
- lacks production data provenance
- lacks trust metadata
- lacks freshness metadata
- lacks refusal behavior
- lacks fail-closed behavior
- uses grade-oriented prototype ordering
- lacks a production API/frontend contract

Future eligibility:

The Prospect Pipeline may become experimental after it has a defined owner,
data-source plan, limitations, review audience, user-facing prototype labels,
and governance review. Production eligibility would require a separate
contract, certification review, and rollout decision.

### Fatigue vs Next-Outing ERA Insight

Current classification:

```text
EXPERIMENTAL
```

Promotion path:

```text
Experimental -> Supported
```

Promotion blockers:

- correlational and exploratory
- not role-adjusted
- not causal
- not suitable as a recommendation input
- generated artifact provenance and refresh expectations need support policy
- test coverage should cover payload shape and limitation visibility if
  support status is requested

Future eligibility:

The insight may become supported as a reference or methodology-adjacent
surface if it preserves non-causal framing, limitation visibility, generated
timestamp visibility, and regression coverage. It is not eligible for
production recommendation behavior without a separate intelligence contract
and certification review.

### Latest-Workload Snapshot Mode

Current classification:

```text
EXPERIMENTAL
```

Promotion path:

```text
Experimental -> Supported
```

Promotion blockers:

- validation-only semantics
- admin/development access boundary must remain intact
- must not be used as current public availability
- no public frontend helper should exist

Future eligibility:

Snapshot mode may become supported as admin validation tooling if ownership,
runbook documentation, access controls, failure modes, and regression tests
remain documented. It is not eligible for public production intelligence
without a separate contract and freshness review.

### MLB Passthrough Helpers

Current classification:

```text
EXPERIMENTAL
```

Promotion path:

```text
Experimental -> Supported
```

Promotion blockers:

- raw external-source helpers do not carry the BaseballOS trust envelope
- freshness metadata is not wrapped into a product contract
- failure behavior and rate-limit behavior are not governed as product
  intelligence
- no current public UI workflow depends on them

Future eligibility:

The helpers may become supported source utilities if wrapped by a documented
contract with freshness, failure-state, provenance, and access expectations.
They are not eligible for direct production UI use without a governed
trust/freshness envelope.

### Threshold Experimentation Surfaces

Current classification:

```text
EXPERIMENTAL
```

Promotion path:

```text
Experimental -> Supported
```

Promotion blockers:

- offline governance tooling, not runtime product behavior
- output is for threshold review and audit, not user-facing intelligence
- support status requires ownership, runbook, test coverage, and report
  freshness expectations

Future eligibility:

Threshold experimentation surfaces may become supported governance tooling.
They are not production intelligence surfaces and must not drive runtime
threshold changes without the existing availability governance adoption path.

## Legacy and Deprecation Review

### Metadata-Less Fatigue Array Response

Current classification:

```text
LEGACY
```

Deprecation path:

```text
Legacy -> Deprecated -> Removed
```

Deprecation blockers:

- unknown external consumers
- backward compatibility value remains possible
- metadata-aware replacement should be documented before deprecation

Future eligibility:

This response shape may be deprecated after consumer review, migration notes,
and a migration window to metadata-aware responses.

### Standalone Fatigue Recalculation Script

Current classification:

```text
LEGACY
```

Deprecation path:

```text
Legacy -> Deprecated -> Removed
```

Deprecation blockers:

- may still be useful for manual maintenance
- supported admin-token endpoint is the preferred operational path, but script
  usage is not fully inventoried

Future eligibility:

The script may be deprecated after confirming the admin endpoint and documented
operational runbook fully replace its use.

## Governance Validation

This policy preserves the certified Recommendation Engine governance boundary:

```text
ranking_applied === false
selection_made === false
```

The policy does not authorize:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended option behavior
- automated decisions
- additional Recommendation Engine API exposure
- prototype production promotion without certification and rollout review

## Required Validation

Validation completed for this phase:

```text
npm test
77 passed, 0 failed

.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-promotion-policy
278 passed, 0 failed
```

Diff hygiene checks are required before commit:

```text
git diff --check
git diff --cached --check
```

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V2.5 Phase 21 Lifecycle Enforcement Checklist
```

Phase 21 should convert this policy into a repeatable review checklist for
future pull requests, route additions, prototype promotions, deprecations, and
production-surface changes. It should not add product features or expand
Recommendation Engine behavior.
