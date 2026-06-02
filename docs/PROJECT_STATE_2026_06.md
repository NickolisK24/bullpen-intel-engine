# Project State: June 2026

## Executive Summary

BaseballOS has completed the Availability Engine trust foundation. The platform
now moves beyond a fatigue dashboard into explainable bullpen availability
intelligence while preserving clear limits around what public workload data can
and cannot prove.

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
| Recommendation Engine | Planned |
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
- Recommendation Engine V1 decision logic and UI are not implemented yet; the
  backend foundation contracts, eligibility gates, and category eligibility
  assignment are present. The builder can compose candidate-level structured
  responses, but final ranking and selection remain future work.
- Latest-workload snapshot mode is validation/admin only and must not be treated
  as current availability.

## Next Major Milestone

The next major initiative is:

```text
Recommendation Engine V1 Policy
```

Goal:

```text
Move BaseballOS from availability intelligence to decision-support intelligence.
```

This milestone should define policy before implementation:

- what a recommendation is allowed to say
- what it must not imply
- how confidence and limitations are carried into recommendations
- how workload-unavailable differs from unknown availability
- how stale/missing data changes recommendation wording
- how future simulator work can consume availability classifications without
  bypassing trust rules

The authoritative policy document is:

- `docs/RECOMMENDATION_ENGINE_V1_POLICY.md`

The staged implementation planning document is:

- `docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md`

No Recommendation Engine implementation details are authorized by this project
state document or by the implementation plan itself.
