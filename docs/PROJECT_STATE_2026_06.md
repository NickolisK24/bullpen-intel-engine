# Project State: June 2026

## Executive Summary

BaseballOS has completed the Availability Engine trust foundation and
Recommendation Engine V1. The platform now moves beyond a fatigue dashboard
into explainable bullpen availability intelligence and certified
candidate-level decision support while preserving clear limits around what
public workload data can and cannot prove.

The current product identity is:

```text
BaseballOS: trust-first bullpen intelligence for workload, availability, and
freshness-aware decision support.
```

The repository remains `bullpen-intel-engine`. Repository structures, package
names, imports, and deployment configuration should not be renamed solely for
branding.

## Completed Foundations

### Bullpen Intelligence

BaseballOS ingests MLB Stats API rosters and pitching game logs, computes
fatigue scores, and exposes team, pitcher, and dashboard workload views.

### Fatigue Engine

The Fatigue Engine remains the deterministic workload base. It produces a
transparent 0-100 workload score from pitch-count load, rest days, appearance
frequency, and innings load.

### Availability Engine V1

Availability Engine V1 is implemented. It translates fatigue, rest, recent
workload, appearance compression, and data state into:

- `Available`
- `Monitor`
- `Limited`
- `Avoid`
- `Unavailable`

The classifier is centralized in the backend availability service and is not
embedded directly in routes. API responses remain backward-compatible by adding
availability objects rather than replacing fatigue fields.

### Explainability

Availability output includes:

- status
- confidence
- data state
- reasons
- limitations
- deterministic inputs

Every non-Available classification must expose reasons. Missing, stale, or
incomplete data must lower confidence, alter display, or make limitations
visible.

### Dashboard Integration

The dashboard now includes:

- current-mode availability summary
- status distribution
- confidence distribution
- data-state distribution
- stale/missing-data trust notes
- dashboard trust strip for data status, sync date, data-through date, and
  refresh coverage

### Status Reachability

Frontend fixture coverage verifies that all five availability statuses render
correctly even when the current local dataset does not naturally contain all
statuses at once. Fixture validation is for UI correctness only, not threshold
validation.

### Governance Framework

Availability threshold governance is implemented through:

- repeatable threshold audit tooling
- latest-workload snapshot validation mode
- explanation quality audit
- threshold tuning plan
- boundary review process
- adoption records
- readiness certification reports

Threshold changes must be evidence-based, single-variable where possible, and
reviewed before adoption.

### Recommendation Engine V1

Recommendation Engine V1 is complete, certified, and production-ready for
candidate-level evaluation. It translates trusted availability, confidence,
freshness, explanation, limitation, and refusal evidence into structured
candidate-level recommendation or refusal output.

The certified V1 system includes:

- backend recommendation foundation contracts and schemas
- eligibility and exclusion gates
- category eligibility assignment
- response builder/composer
- candidate-level engine integration
- candidate API route
- frontend recommendation API client
- Recommendation Panel UI
- controlled success, caution, refusal, loading, error, and empty states
- pitcher detail dashboard integration
- UI polish and regression certification

Recommendation Engine V1 remains bounded to one pitcher candidate at a time.
It does not rank the bullpen or select the final pitcher.

## Current Capabilities

| Capability | Status |
| --- | --- |
| Bullpen Intelligence | ✓ Complete |
| Fatigue Engine | ✓ Complete |
| Availability Engine | ✓ Complete |
| Explainability | ✓ Complete |
| Trust Layer | ✓ Complete |
| Freshness Transparency | ✓ Complete |
| Governance Framework | ✓ Complete |
| Recommendation Engine V1 | ✓ Complete / Certified / Production Ready |
| Recommendation Engine V2 Strategy | Scope Definition Active |
| Recommendation Engine V2 Governance Boundaries | Documented |
| Recommendation Engine V2 Architecture | Documented |
| Recommendation Engine V2 API Contract | Documented |
| Prospect Pipeline | Prototype |

## Trust & Governance Status

Trust-first rules currently in force:

- No black-box availability labels.
- Every status must expose reasons when workload or data-state constraints are
  present.
- Stale data must not be presented as current availability.
- Missing data must reduce confidence or alter display.
- `Unavailable` means workload-unavailable from public data, not injured,
  medically unavailable, or team-reported unavailable.
- Recommendation wording must not imply private clubhouse, medical, travel, or
  manager-intent knowledge.
- Recommendation Engine V1 must preserve candidate-level evaluation only.
- Recommendation Engine V1 must preserve `ranking_applied=false` and
  `selection_made=false`.
- Recommendation Engine V1 must keep confidence, freshness, explanations,
  limitations, and refusal reasons visible.
- Threshold changes require audit evidence and before/after comparison.

The first governed threshold adoption is complete:

```text
Unavailable 3-day pitch threshold: 80 -> 90
```

This adoption allows 80-89 pitches in three days to classify as `Avoid` unless
another Unavailable rule fires. 90+ pitches in three days remains
`Unavailable`.

Reference artifacts:

- `docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`
- `backend/reports/availability_threshold_adoption_candidate_c.md`
- `backend/reports/availability_unavailable_boundary_review.md`
- `backend/reports/availability_post_adoption_readiness_certification.md`

## Freshness & Sync Status

Durable sync metadata is implemented through the `sync_runs` persistence model.
The backend can separately expose:

- last sync attempt
- last successful sync
- latest baseball game-log date
- latest workload date
- latest fatigue calculation timestamp
- sync status
- freshness limitations

The dashboard distinguishes:

```text
Synced:
June 1, 2026

Data Through:
May 31, 2026
```

This distinction matters because a sync timestamp is operational metadata, while
data-through date is baseball data coverage. BaseballOS should never substitute
one for the other.

If sync metadata is unavailable but data exists, the dashboard should say so and
still show the data-through date. If the latest sync fails, the dashboard should
preserve the latest known data-through date and disclose the failed sync state.

Reference artifacts:

- `backend/reports/durable_sync_metadata_implementation.md`
- `backend/reports/durable_sync_metadata_deployment_certification.md`
- `frontend/docs/dashboard_trust_strip_polish.md`

## Availability Engine Status

Availability Engine V1 is complete as a deterministic, explainable
classification framework. Current public UI surfaces consume backend output
instead of recreating classification logic in the browser.

Implemented public-facing surfaces:

- bullpen row availability badges
- availability filter
- pitcher detail availability summary
- dashboard availability summary
- dashboard data trust strip

Implemented validation/governance surfaces:

- frontend fixtures for all five statuses
- backend status tests
- stale and missing data tests
- threshold audit
- snapshot validation
- explanation audit
- boundary review tooling
- adoption reports

The Availability Engine remains bounded by public workload data. It does not
claim team-reported availability, injury status, warm-up activity, travel
status, or manager intent.

## Known Limitations

- No injury, transaction/news, or team-reported availability feed is integrated.
- No private clubhouse, medical, travel, or manager-intent data is available.
- No Statcast, Hawk-Eye biomechanics, Stuff+, or pitch-quality modeling is used.
- Role-aware starter/reliever handling remains limited.
- Warm-up workload and bullpen phone activity are not modeled.
- Prospect Pipeline remains a prototype with sample data, not a live
  minor-league data product.
- Recommendation Engine V1 is complete, certified, and production-ready for
  candidate-level evaluation only. Bullpen ranking, pitcher ordering, final
  pitcher selection, performance forecasting, injury prediction, save
  prediction, matchup guidance, and black-box or generated baseball opinions
  remain outside V1. V2 strategy and scope-definition work may explore grouped
  bullpen and team-level visibility without ranking or automated selection.
- Latest-workload snapshot mode is validation/admin only and must not be treated
  as current availability.

## Recommendation Engine V1 Completion Status

The completed major initiative is:

```text
Recommendation Engine V1
```

Status:

```text
Completed
Certified
Production Ready
```

Mission achieved:

```text
Move BaseballOS from availability intelligence to decision-support intelligence.
```

Recommendation Engine V1 is certified for:

- fail-closed behavior
- candidate-level evaluation
- trust visibility
- freshness visibility
- confidence visibility
- explanation visibility
- limitation visibility
- refusal visibility

The official completion certification is:

- `docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md`

Supporting governance documents:

- `docs/RECOMMENDATION_ENGINE_V1_POLICY.md`
- `docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md`
- `docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md`
- `docs/RECOMMENDATION_ENGINE_V1_FRONTEND_CONTRACT.md`
- `docs/RECOMMENDATION_ENGINE_V1_UI_IMPLEMENTATION_PLAN.md`
- `docs/RECOMMENDATION_ENGINE_V1_DASHBOARD_INTEGRATION_PLAN.md`

The implemented candidate-level route evaluates one candidate at a time. The
frontend API client calls that route for one-candidate evaluation only. The
selected-pitcher detail workflow builds one candidate payload from existing
pitcher detail, availability, and workload fields and displays the controlled
Recommendation Panel response after a user-triggered evaluation.

The certified display keeps confidence, data freshness, availability,
explanations, limitations, category eligibility, refusal reasons,
`ranking_applied=false`, and `selection_made=false` visible. The integration
does not perform ranking, scoring, bullpen comparison, route navigation, or
final pitcher selection.

## Recommendation Engine V2 Strategy Milestone

Recommendation Engine V2 is entering a strategy and scope-definition phase.
This is a governance and planning milestone only.

The official strategy foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`

The governance-boundary decision filter is:

- `docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`

The architecture foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`

The API contract foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`

V2 planning may explore bullpen-level intelligence, bullpen inventory
visibility, bullpen stress awareness, leverage resource visibility, workload
distribution visibility, grouped eligibility reporting, bullpen readiness
reporting, and broader recommendation explainability.

This milestone does not authorize pitcher rankings, pitcher ordering,
automated pitcher selection, game outcome prediction, injury prediction, save
prediction, performance forecasting, opaque recommendation scores, unsupported
baseball opinions, Recommendation Engine API changes, frontend behavior
changes, or new recommendation logic.

The governance-boundary milestone documents allowed, restricted, and forbidden
V2 behaviors; preserves the active `ranking_applied=false` and
`selection_made=false` trust guarantees; and requires documented architecture,
API contract, frontend contract, certification criteria, and explicit user
approval before implementation may begin.

The architecture milestone defines the proposed V2 object model, service flow,
metadata model, fail-closed path, API and frontend architecture concepts,
governance enforcement points, testing architecture, certification
architecture, and implementation-readiness criteria. It does not authorize
backend, frontend, API, or Recommendation Engine V1 behavior changes.

The API contract milestone defines the proposed V2 response shape, provisional
bullpen-state endpoint scope, required trust metadata, response objects,
anti-ranking rules, success and refusal examples, testing requirements,
certification requirements, and implementation gate. It does not implement or
modify endpoints.

## Future Expansion Boundary

Future recommendation work belongs in Recommendation Engine V2 or later.

Possible future expansion areas include:

- bullpen-level intelligence
- team-level stress intelligence
- bullpen inventory visibility
- grouped eligibility reporting
- bullpen readiness reporting
- prioritization without ranking
- advanced decision-support layers
- role-aware recommendation behavior
- simulator integration

This project state document does not authorize further Recommendation Engine
API exposure, pitcher ranking, pitcher ordering, scoring, or final pitcher
selection.
