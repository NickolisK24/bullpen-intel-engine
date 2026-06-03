# ⚾ BaseballOS

> Trust-first bullpen intelligence platform for workload risk, fatigue transparency, and pitching-staff decision support.

## What BaseballOS Is

BaseballOS is a full-stack baseball intelligence platform focused on **relief-pitcher
workload**. It ingests live MLB Stats API data, scores each pitcher's recent workload as a
transparent 0–100 fatigue value, and presents it through a dashboard built around one
principle: **show what the system knows, what it doesn't, and when the data was last
refreshed.**

It is not a general stats clone and not an "analytics command center" that does a little of
everything. It does one thing seriously — bullpen workload and availability intelligence —
and is honest about everything still in progress.

**Stack:** React + TailwindCSS · Flask + Python · PostgreSQL · MLB Stats API

> The fatigue score is a **transparent workload heuristic** — not an injury or performance
> prediction. The in-app Methodology page documents exactly how every number is computed and
> what the model intentionally does not measure.

## Why It Exists

Bullpen management turns on a hard, time-sensitive question: *who is actually available, and
who is carrying too much recent workload?* That signal is usually buried in raw game logs.
BaseballOS surfaces it directly — rest days, pitch-count load, appearance frequency, and
innings load rolled into one explainable score per pitcher — and pairs it with freshness and
coverage visibility so the number can be trusted instead of taken on faith.

## Current Capabilities

Everything here is implemented and runs against real MLB Stats API data:

- **Fatigue scoring engine** — a deterministic 0–100 workload heuristic from four factors the
  MLB Stats API exposes reliably: pitch-count load (35%), rest days (30%), appearance
  frequency (20%), innings load (15%). Continuous and monotonic across thresholds.
- **Availability Engine V1** — deterministic bullpen availability statuses
  (`Available`, `Monitor`, `Limited`, `Avoid`, `Unavailable`) derived from existing
  workload, fatigue, rest, and freshness data.
- **Recommendation Engine V1** — certified candidate-level decision support in
  pitcher detail, using fail-closed eligibility, category eligibility,
  explanations, limitations, confidence, freshness, refusal reasons, and
  explicit no-ranking/no-selection metadata.
- **Availability explainability** — every non-Available status carries ordered reasons,
  confidence, data state, limitations, and deterministic inputs; labels are not black boxes.
- **Dashboard availability summary** — current-mode availability distributions, confidence
  counts, and stale/missing-data notes are visible from the dashboard.
- **MLB Stats API ingestion** — pulls rosters and game-by-game pitching logs; idempotent
  (skips duplicates, enforced at the database level).
- **Pitcher detail workflow** — per-pitcher view with score, risk tier, weighted component
  breakdown, component radar, fatigue trend, recent appearances, availability status,
  confidence, reasons, and limitations — on desktop **and** mobile.
- **Team bullpen views** — per-team bullpen overview and team-vs-team workload summaries.
- **Trust strip and sync freshness visibility** — the dashboard separates platform data
  status, last successful sync, baseball data-through date, and refresh coverage.
- **Durable sync metadata** — sync attempts persist in the `sync_runs` table so successful,
  failed, and missing metadata states survive restarts and deployments.
- **Current-season coverage transparency** — the dashboard distinguishes total tracked
  pitchers, pitchers with computed workload data, and pitchers refreshed in the latest sync,
  so coverage gaps are visible rather than hidden.
- **Freshness-aware bullpen visibility** — active/current data is the default; stale or
  inactive pitchers remain inspectable without being presented as current availability.
- **External scheduled sync** — a GitHub Actions workflow refreshes data daily via the
  protected backend endpoint.
- **Protected operational endpoints** — sync and fatigue-recalculation are admin-token
  gated; all read endpoints stay public.
- **Methodology page** — public, in-app documentation of the model, weights, and limitations.
- **Availability governance framework** — threshold audits, snapshot validation, boundary
  review, and adoption reports document how status thresholds are changed.
- **Backend test coverage** — unit + integration tests for the scoring engine, the
  availability engine, admin-token guard, game-log uniqueness constraint, sync-status
  endpoint, and threshold audit tools.
- **Data integrity** — a database unique constraint makes duplicate game logs impossible.
- **Production config hardening** — environment-driven config with fail-fast checks before a
  hosted launch.

## Platform Status

| Capability | Status |
|------------|--------|
| Bullpen Intelligence | ✓ Complete |
| Fatigue Engine | ✓ Complete |
| Availability Engine | ✓ Complete |
| Explainability | ✓ Complete |
| Trust Layer | ✓ Complete |
| Freshness Transparency | ✓ Complete |
| Governance Framework | ✓ Complete |
| Recommendation Engine V1 | ✓ Complete / Certified / Production Ready |
| Recommendation Engine V1 Candidate Evaluation Layout Remediation | Complete |
| Dashboard and Bullpen Loading Performance Remediation | Complete |
| Recommendation Engine V2 Strategy | Scope Definition Active |
| Recommendation Engine V2 Governance Boundaries | Documented |
| Recommendation Engine V2 Architecture | Documented |
| Recommendation Engine V2 API Contract | Documented |
| Recommendation Engine V2 Frontend Contract | Documented |
| Recommendation Engine V2 Certification Requirements | Documented |
| Recommendation Engine V2 Implementation Readiness Review | Complete |
| Recommendation Engine V2 Implementation Plan | Complete |
| Recommendation Engine V2 Phase 1 Domain Foundation | Complete |
| Recommendation Engine V2 Phase 2 Context Assembly | Complete |
| Recommendation Engine V2 Phase 3 Neutral Intelligence | Complete |
| Recommendation Engine V2 Phase 4 Inventory Visibility | Complete |
| Recommendation Engine V2 Phase 5 Team Bullpen Context | Complete |
| Recommendation Engine V2 Phase 6 Trust Metadata Integration | Complete |
| Recommendation Engine V2 Phase 7 Refusal Fail-Closed Integration | Complete |
| Recommendation Engine V2 Phase 8 API Contract Exposure | Complete |
| Recommendation Engine V2 Phase 9 Frontend Client Integration | Complete |
| Recommendation Engine V2 Phase 10 Governed Frontend Rendering | Complete |
| Recommendation Engine V2 Phase 10A Desktop Layout Remediation | Complete |
| Recommendation Engine V2 Phase 10B Bullpen Selected Pitcher Layout Remediation | Complete |
| Recommendation Engine V2 Phase 11 Mobile Accessibility Validation | Complete |
| Recommendation Engine V2 Phase 12 Certification Readiness Validation | Ready for Formal Certification Review |
| Recommendation Engine V2 Phase 13 Formal Certification Review | Certified / Production Ready |
| BaseballOS V2.5 Phase 14 Inventory Presentation Optimization | Complete |
| BaseballOS V2.5 Phase 15 Intelligence Presentation Optimization | Complete |
| BaseballOS V2.5 Phase 16 Production Rollout Decision | Approved for Production Rollout |
| BaseballOS V2.5 Phase 17 Post-Rollout Monitoring and Boundary Review | Complete |
| BaseballOS V2.5 Phase 18 Maintenance Warning Remediation Review | Complete |
| BaseballOS V2.5 Phase 19 Prototype Surface Maintenance Review | Complete |
| BaseballOS V2.5 Phase 20 Prototype Promotion and Deprecation Policy | Complete |
| BaseballOS V2.5 Phase 21 Lifecycle Enforcement Checklist | Complete |
| BaseballOS V2.5 Phase 22 Lifecycle Review Log and Adoption Audit | Complete |
| BaseballOS V2.5 Phase 23 Lifecycle Evidence Backfill and Owner Assignment Plan | Complete |
| BaseballOS V2.5 Phase 24 Lifecycle Evidence Packet Template and Initial Backfill | Complete |
| BaseballOS V2.5 Phase 25 Lifecycle Evidence Packet Review and Backfill Execution | Complete |
| BaseballOS V2.5 Phase 26 Lifecycle Evidence Citation Backfill and Stewardship Review | Complete |
| BaseballOS V2.5 Phase 27 Lifecycle Evidence Section-Level Citation Map | Complete |
| BaseballOS V2.5 Phase 28 Evidence Ownership, Monitoring Artifact, and Test Mapping Closeout | Complete |
| BaseballOS V2.5 Phase 29 Governance Hardening Closeout and V3 Readiness Decision | Complete |
| Recommendation Engine V2 Production Fail-Closed Diagnosis | Complete / Remediation Planning |
| Recommendation Engine V2 Production Fail-Closed Communication and Freshness Metadata Remediation | Complete |
| BaseballOS V3 Phase 1 Product Capability Review and Priority Decision | Complete |
| BaseballOS V3 Phase 2 Team Operations Bullpen Readiness Capability Definition | Complete |
| BaseballOS V3 Phase 3 Team Operations Bullpen Readiness Implementation Plan | Complete |
| BaseballOS V3 Phase 4 Team Operations Bullpen Readiness API Contract and Certification Requirements | Complete |
| BaseballOS V3 Phase 5 Team Operations Bullpen Readiness Backend Domain Foundation | Complete |
| BaseballOS V3 Phase 6 Team Operations Bullpen Readiness Internal API Route Integration | Complete / Internal / Uncertified |
| BaseballOS V3 Phase 7 Team Operations Bullpen Readiness Route Certification Readiness Review | Ready for Frontend Integration Planning |
| BaseballOS V3 Phase 8 Team Operations Bullpen Readiness Frontend Integration Plan | Complete / Planning Only |
| BaseballOS V3 Phase 9 Team Operations Bullpen Readiness Frontend Client Normalization and Contract Tests | Complete / Client Only / No Dashboard UI |
| BaseballOS V3 Phase 10 Team Operations Bullpen Readiness Dashboard UI Integration | Complete / Internal UI / Uncertified |
| BaseballOS V3 Phase 11 Team Operations Bullpen Readiness Dashboard UI Certification Readiness Review | Ready for Formal Certification Planning |
| BaseballOS V3 Phase 12 Team Operations Bullpen Readiness Formal Certification Plan and Rollout Prerequisites | Complete / Certification Plan Only |
| Prospect Pipeline | Prototype |

## Trust & Transparency

BaseballOS is built to earn a reviewer's trust rather than ask for it:

- **Methodology page** documents the model, the exact component weights, and — importantly —
  what it does **not** measure (e.g. leverage index is deliberately excluded, not faked).
- **Honest framing:** the score is a workload heuristic; the retrospective fatigue→ERA
  analysis is presented as an exploratory, correlational finding with sample sizes and
  limitations, never as causation or validation.
- **Freshness is always visible** — you can see when data was last synced (or that it's a
  historical snapshot) instead of guessing.
- **Synced and Data Through are distinct** — sync timestamps come from durable sync metadata;
  baseball coverage dates come from workload/game-log data.
- **Availability labels are explainable** — status badges are paired with confidence, data
  state, reasons, and limitations.
- **Threshold changes are governed** — the first adopted change raised the Unavailable
  three-day pitch threshold from 80 to 90 after audit, experiment, and boundary review.
- **Coverage is explicit** — tracked vs. workload-data vs. refreshed counts are labeled
  distinctly so gaps aren't mistaken for bugs.
- **Write operations are protected** — only an admin token can trigger sync/recalculation.
- **Integrity is enforced in the database**, not just in application code.
- **Tested** — the core scoring logic and operational safeguards have automated coverage.

## Production / Hosted Architecture

| Layer | Where |
|-------|-------|
| Frontend | Vercel (static React build) |
| Backend | Render (Flask + gunicorn) |
| Database | Managed PostgreSQL |
| Scheduled sync | GitHub Actions (daily) |
| Data source | MLB Stats API |

Daily sync is driven **externally** rather than by an in-process timer: a GitHub Actions
workflow (`.github/workflows/baseballos-sync.yml`) POSTs the protected sync endpoint each
morning, authenticating with an `X-Admin-Token` header from a repository secret. This avoids
relying on a free web instance happening to be awake at the scheduled moment. An uptime/health
monitor can keep the backend warm via `GET /api/health`, but health checks **do not** perform
a sync — only the scheduled workflow (or a manual admin call) does. See
[`docs/SETUP.md`](docs/SETUP.md) for the full setup, including the DST note on the run time.

## Planned / Experimental Modules

- **Prospect Pipeline — prototype (sample data).** A development-pipeline view wired to a
  working API but populated with a small set of illustrative, hand-entered sample players —
  **not** a live minor-league feed. It's clearly labeled as a prototype in the UI; treat it as
  a roadmap preview, not a data product.

## Product Direction

Direction, not promises — these are where the platform is headed, not features that exist
today:

- **Recommendation Engine V2 boundary** — future recommendation work may explore
  bullpen-level intelligence, grouped eligibility reporting, team-level stress
  intelligence, readiness visibility, neutral grouping without ranking, and
  broader explainability. The Phase 1 backend domain object foundation,
  Phase 2 backend context assembly layer, Phase 3 backend-only neutral
  intelligence expansion, Phase 4 backend-only inventory visibility layer,
  Phase 5 backend-only team bullpen context layer, and Phase 6 backend-only
  trust metadata integration, and Phase 7 backend-only refusal/fail-closed
  integration now exist. Phase 8 exposes the approved backend-only V2
  bullpen-state API contract. Phase 9 adds frontend client integration for
  that endpoint with contract-safe normalization. Phase 10 renders governed
  V2 bullpen intelligence on the dashboard with visible trust, freshness,
  limitation, explanation, refusal, fail-closed, inventory, team-context, and
  neutral group information. Phase 10A remediates the desktop layout defect in
  that governed panel so metadata, refusal, explanation, inventory, and
  context sections remain readable on common desktop widths. Phase 10B
  remediates the Bullpen selected-pitcher detail layout so the pitcher card and
  recommendation trust surface remain readable on common desktop widths. The
  V1 Candidate Evaluation article inside that selected-pitcher detail surface
  now stays on an embedded single-column layout path so status, trust,
  freshness, categories, explanations, limitations, refusal, and metadata
  sections remain readable. Phase 11 validates and improves mobile and
  accessibility behavior across the Dashboard V2 panel, Bullpen
  selected-pitcher detail surface, and embedded V1 Candidate Evaluation
  surface. Phase 12 compiles backend, API, frontend, trust, freshness,
  refusal, fail-closed, mobile, accessibility, and V1 regression evidence and
  classifies V2 as ready for formal certification review. Phase 13 formally
  certifies the implemented and governed V2 scope as production-ready while
  leaving production rollout to a separate governed decision. V2.5 Phase 14
  optimizes certified inventory presentation so summary cards show category
  counts, trust state, freshness state, and evidence summaries first, with
  full inventory membership available on demand. V2.5 Phase 15 audits the full
  Dashboard V2 intelligence surface and makes candidate groups, team context,
  limitations, explanations, and refusal details summary-first with expansion
  on demand. A later Dashboard V2 collapsible remediation corrects the live
  production presentation by adding nested member/detail controls for
  high-volume inventory, candidate, Team Context, limitation, explanation, and
  refusal surfaces. V2.5 Phase 16 approves the current certified V2 Dashboard
  experience for production rollout within the implemented scope only. V2.5
  Phase 17 establishes post-rollout monitoring, warning review, and boundary
  review procedures to protect the approved system from governance,
  contract, UX, and technical-debt regressions. V2.5 Phase 18 reviews and
  remediates the backend warning debt surfaced during post-rollout validation,
  reducing the full backend test-suite warning count from 139 to 0 without
  changing certified Recommendation Engine behavior. V2.5 Phase 19 inventories
  production, supported, prototype, experimental, legacy, and deprecated
  surfaces, classifies prototype governance risks, and neutralizes rank-style
  presentation language outside the certified V2 path. V2.5 Phase 20 defines
  the official lifecycle policy for promotion, support, production approval,
  legacy classification, deprecation, and removal. V2.5 Phase 21 converts that
  policy into an operational enforcement checklist for lifecycle movement,
  production promotion, deprecation, removal, and intelligence-surface review.
  V2.5 Phase 22 adds the lifecycle review log and adoption audit layer that
  records checklist usage, evidence requirements, surface-by-surface review
  findings, and remaining owner/runbook/metadata/test evidence gaps. V2.5
  Phase 23 converts those findings into the owner assignment, evidence gap,
  promotion-readiness, and evidence acquisition framework required before any
  prototype, experimental, or legacy lifecycle movement can proceed. V2.5
  Phase 24 introduces the standard lifecycle evidence packet template and
  initial packet stubs for selected production, prototype, experimental, and
  legacy surfaces. V2.5 Phase 25 performs the first formal packet review and
  backfill execution pass, assigning evidence readiness scores and lifecycle
  readiness classifications without changing runtime behavior. V2.5 Phase 26
  performs the first production-focused citation backfill and stewardship
  review, replacing broad packet evidence claims with document-level source
  references where current records support them. V2.5 Phase 27 converts those
  production citations into section-level citation maps for the certified
  Dashboard V2 and V2 bullpen-state API surfaces where current records support
  that specificity. V2.5 Phase 28 assigns packet-level retention ownership,
  defines evidence cadence and monitoring artifact format, and maps production
  governance evidence to exact test files and test names where available. V2.5
  Phase 29 formally closes the governance hardening program and classifies the
  remaining operational retention gaps as non-blocking for V3 product
  capability planning. A June 3, 2026 V2 production fail-closed diagnosis
  finds the production degraded fail-closed state is correctly triggered by
  stale source evidence. The follow-up remediation now exposes sync, source
  freshness, aggregate V2 freshness, trust, and fail-closed reason metadata
  while improving Dashboard communication for degraded freshness protection.
  V3 Phase 1 is complete and neutrally evaluates current
  product paths, selecting Team Operations Bullpen Readiness planning as the
  best next product direction based on current evidence, data availability,
  implementation risk, governance risk, portfolio value, and baseball
  operations value. V3 Phase 2 is complete and defines that capability's
  allowed inputs, prohibited inputs, allowed outputs, prohibited outputs,
  readiness vocabulary, metadata requirements, refusal behavior, fail-closed
  requirements, testing expectations, accessibility expectations, and
  certification gates before any implementation work. V3 Phase 3 is complete
  and converts that definition into a backend, API, frontend, testing,
  certification, and rollout implementation plan without changing runtime
  behavior. V3 Phase 4 is complete and establishes the official Team
  Operations Bullpen Readiness API contract and certification requirements for
  future implementation, preserving the certified V2 recommendation contract.
  V3 Phase 5 is complete and adds the separate backend Team Operations domain
  foundation, deterministic readiness assembly, metadata contracts,
  fail-closed handling, and focused backend tests without registering a route
  or changing frontend behavior. V3 Phase 6 is complete and registers the
  separate Team Operations Bullpen Readiness Flask route as internal,
  non-production, and uncertified, with governed request validation,
  fail-closed behavior, and route tests. It does not add frontend exposure or
  production certification. V3 Phase 7 is complete and classifies that internal
  route as `READY_FOR_FRONTEND_INTEGRATION_PLANNING` after reviewing contract
  compliance, governance metadata, request validation, fail-closed behavior,
  anti-ranking, anti-selection, anti-prediction, focused test coverage, and V2
  regression safety. It does not grant production certification or frontend
  implementation authorization. V3 Phase 8 is complete and defines the governed
  frontend integration plan for future Dashboard presentation, including client
  normalization, summary-first rendering, expand-on-demand evidence,
  trust/freshness/refusal visibility, accessibility, mobile behavior, neutral
  language rules, and frontend tests without adding UI. V3 Phase 9 is complete
  and adds frontend client normalization and contract tests for the internal
  Team Operations Bullpen Readiness route without adding Dashboard UI,
  production certification, public exposure, or Recommendation Engine V2
  contract changes. V3 Phase 10 is complete and adds the governed Dashboard
  panel for Team Operations Bullpen Readiness using the Phase 9 normalized
  client payload, with visible internal/non-production/uncertified status,
  summary-first rendering, expand-on-demand evidence, trust/freshness/refusal
  metadata, governance metadata, and frontend rendering tests. It does not
  grant production certification, public route certification, or any
  Recommendation Engine V2 contract change. V3 Phase 11 is complete and
  reviews that Dashboard UI for certification readiness, classifying it as
  `READY_FOR_FORMAL_CERTIFICATION_PLANNING` while preserving internal,
  non-production, uncertified status and withholding production certification
  and rollout approval. V3 Phase 12 is complete and defines the formal
  certification checklist, evidence packet requirements, monitoring artifact
  requirements, rollout prerequisites, and stop conditions required before any
  formal certification review or production rollout decision can be attempted.
  It does not grant production certification or rollout approval.
  No
  ranking UI, final pitcher choice UI, or prediction UI is implemented. Those capabilities
  remain outside the completed Recommendation Engine V1 certification. V1 is
  production-ready for candidate-level evaluation only.
  See
  [`docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md`](docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md),
  [`docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`](docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md),
  [`docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`](docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md),
  [`docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`](docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md),
  [`docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md),
  [`docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md),
  [`docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`](docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md),
  [`docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md`](docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md),
  and
  [`docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md),
  the completed Phase 1 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md),
  and the completed Phase 2 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_2_CONTEXT_ASSEMBLY.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_2_CONTEXT_ASSEMBLY.md),
  and the completed Phase 3 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_3_NEUTRAL_INTELLIGENCE.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_3_NEUTRAL_INTELLIGENCE.md),
  and the completed Phase 4 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_4_INVENTORY_VISIBILITY.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_4_INVENTORY_VISIBILITY.md),
  and the completed Phase 5 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_5_TEAM_BULLPEN_CONTEXT.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_5_TEAM_BULLPEN_CONTEXT.md),
  and the completed Phase 6 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_6_TRUST_METADATA_INTEGRATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_6_TRUST_METADATA_INTEGRATION.md),
  and the completed Phase 7 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_7_REFUSAL_FAIL_CLOSED.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_7_REFUSAL_FAIL_CLOSED.md),
  and the completed Phase 8 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_8_API_CONTRACT_EXPOSURE.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_8_API_CONTRACT_EXPOSURE.md),
  and the completed Phase 9 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md),
  and the completed Phase 10 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md),
  and the completed Phase 10A record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md),
  and the completed Phase 10B record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md),
  and the completed V1 Candidate Evaluation layout remediation record in
  [`docs/RECOMMENDATION_ENGINE_V1_CANDIDATE_EVALUATION_LAYOUT_REMEDIATION.md`](docs/RECOMMENDATION_ENGINE_V1_CANDIDATE_EVALUATION_LAYOUT_REMEDIATION.md),
  and the completed Phase 11 record in
  [`docs/RECOMMENDATION_ENGINE_V2_PHASE_11_MOBILE_ACCESSIBILITY.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_11_MOBILE_ACCESSIBILITY.md),
  and the completed Phase 12 certification readiness record in
  [`docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md`](docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md),
  and the completed Phase 13 formal certification record in
  [`docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md`](docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md),
  and the completed V2.5 Phase 14 inventory presentation record in
  [`docs/V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md`](docs/V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md),
  and the completed V2.5 Phase 15 intelligence presentation record in
  [`docs/V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md`](docs/V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md),
  and the Dashboard V2 collapsible remediation record in
  [`docs/V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md`](docs/V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md),
  and the completed V2.5 Phase 16 production rollout decision in
  [`docs/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md`](docs/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md),
  and the completed V2.5 Phase 17 post-rollout monitoring and boundary review in
  [`docs/V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md`](docs/V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md),
  and the completed V2.5 Phase 18 maintenance warning remediation review in
  [`docs/V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md`](docs/V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md),
  and the completed V2.5 Phase 19 prototype surface maintenance review in
  [`docs/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md`](docs/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md),
  and the completed V2.5 Phase 20 prototype promotion and deprecation policy in
  [`docs/V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md`](docs/V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md),
  and the completed V2.5 Phase 21 lifecycle enforcement checklist in
  [`docs/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md`](docs/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md),
  and the completed V2.5 Phase 22 lifecycle review log and adoption audit in
  [`docs/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md`](docs/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md),
  and the completed V2.5 Phase 23 lifecycle evidence backfill and owner
  assignment plan in
  [`docs/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md`](docs/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md),
  and the completed V2.5 Phase 24 lifecycle evidence packet template and
  initial backfill record in
  [`docs/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md`](docs/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md),
  and the completed V2.5 Phase 25 lifecycle evidence packet review and
  backfill execution record in
  [`docs/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md`](docs/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md),
  and the completed V2.5 Phase 26 lifecycle evidence citation backfill and
  stewardship review in
  [`docs/V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md`](docs/V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md),
  and the completed V2.5 Phase 27 lifecycle evidence section-level citation
  map in
  [`docs/V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md`](docs/V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md),
  and the completed V2.5 Phase 28 evidence ownership, monitoring artifact, and
  test mapping closeout in
  [`docs/V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md`](docs/V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md),
  and the completed V2.5 Phase 29 governance hardening closeout and V3
  readiness decision in
  [`docs/V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md`](docs/V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md),
  and the completed V3 Phase 1 product capability review and priority decision
  in
  [`docs/V3_PHASE_1_PRODUCT_CAPABILITY_REVIEW_AND_PRIORITY_DECISION.md`](docs/V3_PHASE_1_PRODUCT_CAPABILITY_REVIEW_AND_PRIORITY_DECISION.md),
  and the completed V3 Phase 2 Team Operations Bullpen Readiness capability
  definition in
  [`docs/V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION.md`](docs/V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION.md),
  and the completed V3 Phase 3 Team Operations Bullpen Readiness
  implementation plan in
  [`docs/V3_PHASE_3_TEAM_OPERATIONS_BULLPEN_READINESS_IMPLEMENTATION_PLAN.md`](docs/V3_PHASE_3_TEAM_OPERATIONS_BULLPEN_READINESS_IMPLEMENTATION_PLAN.md),
  and the completed V3 Phase 4 Team Operations Bullpen Readiness API contract
  and certification requirements in
  [`docs/V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md`](docs/V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md),
  and the completed V3 Phase 5 Team Operations Bullpen Readiness backend domain
  foundation in
  [`docs/V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md`](docs/V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md),
  and the completed V3 Phase 6 Team Operations Bullpen Readiness internal API
  route integration in
  [`docs/V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md`](docs/V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md),
  and the completed V3 Phase 7 Team Operations Bullpen Readiness route
  certification-readiness review in
  [`docs/V3_PHASE_7_TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE_CERTIFICATION_READINESS_REVIEW.md`](docs/V3_PHASE_7_TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE_CERTIFICATION_READINESS_REVIEW.md),
  and the completed V3 Phase 8 Team Operations Bullpen Readiness frontend
  integration plan in
  [`docs/V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN.md`](docs/V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN.md),
  and the completed V3 Phase 9 Team Operations Bullpen Readiness frontend
  client normalization and contract tests in
  [`docs/V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS.md`](docs/V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS.md),
  and the completed V3 Phase 10 Team Operations Bullpen Readiness Dashboard UI
  integration in
  [`docs/V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION.md`](docs/V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION.md),
  and the completed V3 Phase 11 Team Operations Bullpen Readiness Dashboard UI
  certification-readiness review in
  [`docs/V3_PHASE_11_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_CERTIFICATION_READINESS_REVIEW.md`](docs/V3_PHASE_11_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_CERTIFICATION_READINESS_REVIEW.md),
  and the completed V3 Phase 12 Team Operations Bullpen Readiness formal
  certification plan and rollout prerequisites in
  [`docs/V3_PHASE_12_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_PLAN_AND_ROLLOUT_PREREQUISITES.md`](docs/V3_PHASE_12_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_PLAN_AND_ROLLOUT_PREREQUISITES.md).
- Usage **simulator** and bullpen **planning dashboard**
- **Role-aware** fatigue (separating starters from relievers)
- **Reports / exports** and a documented **API platform**
- Real minor-league prospect ingestion with a defensible grade/ETA source

## Project Structure

```
bullpen-intel-engine/
├── .github/workflows/
│   └── baseballos-sync.yml      # Daily external sync (POSTs the protected endpoint)
├── backend/                     # Flask API server
│   ├── app.py                   # App factory + env-driven config selection
│   ├── config.py                # Dev/prod config + production fail-fast checks
│   ├── requirements.txt
│   ├── .env.example             # Backend env template
│   ├── seed.py                  # Seeds pitchers, game logs, fatigue scores (+ sample prospects)
│   ├── recalculate_fatigue.py   # Recompute fatigue from historical reference dates
│   ├── api/                     # Route blueprints (bullpen, prospects, methodology)
│   ├── models/                  # SQLAlchemy models (incl. sync_run metadata)
│   ├── recommendation/          # Recommendation Engine V1 contracts, gates, category mapping, builder, and engine pipeline
│   ├── services/                # mlb_api · fatigue · availability · sync metadata
│   ├── utils/                   # db.py · auth.py (admin-token guard)
│   ├── analysis/                # Out-of-band retrospective fatigue→ERA analysis
│   ├── migrations/              # Alembic migrations (incl. game-log uniqueness)
│   ├── reports/                 # Audit, threshold, freshness, and readiness reports
│   └── tests/                   # pytest coverage for fatigue, availability, sync, audits
├── frontend/                    # React + Vite app
│   ├── .env.example             # Frontend env template
│   └── src/
│       ├── components/          # dashboard · bullpen · prospects · methodology · recommendations · teamOperations · UI
│       ├── hooks/
│       └── utils/               # API client, formatters, shared fatigue-model definitions
└── docs/
    ├── PROJECT_STATE_2026_06.md # Current product state and certification snapshot
    ├── RECOMMENDATION_ENGINE_V1_POLICY.md
    ├── RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md
    ├── RECOMMENDATION_ENGINE_V1_API_CONTRACT.md
    ├── RECOMMENDATION_ENGINE_V1_UI_IMPLEMENTATION_PLAN.md
    ├── RECOMMENDATION_ENGINE_V1_DASHBOARD_INTEGRATION_PLAN.md
    ├── RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md
    ├── RECOMMENDATION_ENGINE_V2_STRATEGY.md
    ├── RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md
    ├── RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md
    ├── RECOMMENDATION_ENGINE_V2_API_CONTRACT.md
    ├── RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md
    ├── RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md
    ├── RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md
    ├── RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_2_CONTEXT_ASSEMBLY.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_3_NEUTRAL_INTELLIGENCE.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_4_INVENTORY_VISIBILITY.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_5_TEAM_BULLPEN_CONTEXT.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_6_TRUST_METADATA_INTEGRATION.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_7_REFUSAL_FAIL_CLOSED.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_8_API_CONTRACT_EXPOSURE.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md
    ├── RECOMMENDATION_ENGINE_V2_PHASE_11_MOBILE_ACCESSIBILITY.md
    ├── RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md
    ├── RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md
    ├── V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md
    ├── V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md
    ├── V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md
    ├── V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md
    ├── V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md
    ├── V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md
    ├── V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md
    ├── V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md
    ├── V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md
    ├── V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md
    ├── V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md
    ├── V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md
    ├── V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md
    ├── V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md
    ├── V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md
    ├── V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md
    ├── V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md
    ├── V3_PHASE_1_PRODUCT_CAPABILITY_REVIEW_AND_PRIORITY_DECISION.md
    ├── V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION.md
    ├── V3_PHASE_3_TEAM_OPERATIONS_BULLPEN_READINESS_IMPLEMENTATION_PLAN.md
    ├── V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md
    ├── V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md
    ├── V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md
    ├── V3_PHASE_7_TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE_CERTIFICATION_READINESS_REVIEW.md
    ├── V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN.md
    ├── BULLPEN_AVAILABILITY_ENGINE_V1.md
    ├── AVAILABILITY_THRESHOLD_TUNING_PLAN.md
    └── SETUP.md                 # Full setup, env reference, and deployment notes
```

## Quick Start

Full step-by-step setup (prerequisites, troubleshooting, deployment) is in
[`docs/SETUP.md`](docs/SETUP.md).

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # then edit DATABASE_URL
flask db upgrade            # apply existing migrations
python seed.py              # pull data from the MLB Stats API
flask run                   # http://localhost:5000
```

```bash
# Frontend (new terminal)
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

## Environment Variables

Templates: [`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example). Full reference in
[`docs/SETUP.md`](docs/SETUP.md). Do not commit real secrets.

**Backend**

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (required) |
| `APP_ENV` | `development` (default) or `production` |
| `SECRET_KEY` | Flask secret; required (non-default) in production |
| `ADMIN_API_TOKEN` | Gates the write endpoints; required in production |
| `AUTO_SYNC` | Enables the in-process scheduler (local convenience; off by default) |
| `CORS_ORIGINS` | Extra allowed frontend origins |

**Frontend**

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Backend origin (only needed when hosted separately) |
| `VITE_ADMIN_API_TOKEN` | Optional admin token for the operator recalculate action — note it ships in the public bundle, so prefer curl for protected calls |

**GitHub Actions secrets** (for the scheduled sync)

| Secret | Purpose |
|--------|---------|
| `BASEBALLOS_SYNC_URL` | The backend sync endpoint URL |
| `BASEBALLOS_ADMIN_API_TOKEN` | Must match the backend `ADMIN_API_TOKEN` |

## Testing

```bash
# Backend tests (no database or network required)
cd backend
python -m pytest
```

```bash
# Frontend production build
cd frontend
npm install
npm run build
```

## Data Sources

- **MLB Stats API** — `https://statsapi.mlb.com/api/v1/` (free, no auth) — rosters, game logs,
  and box scores.
- **PostgreSQL** — local during development; a managed instance (Render, Railway, Supabase) in
  hosted environments.

BaseballOS is an independent project and is not affiliated with or endorsed by MLB.

## Documentation

- [`docs/PROJECT_STATE_2026_06.md`](docs/PROJECT_STATE_2026_06.md) — current
  product state after Recommendation Engine V1 completion certification.
- [`docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md`](docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md)
  — official V1 completion certification documenting completed capabilities,
  certified behaviors, trust guarantees, production readiness, and future
  expansion boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`](docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md)
  — official V2 strategy and scope-definition foundation for future
  bullpen-level and team-level recommendation planning without ranking,
  automated selection, or behavior changes.
- [`docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`](docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md)
  — governance decision filter for allowed, restricted, and forbidden V2
  behavior before architecture or implementation begins.
- [`docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`](docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md)
  — architecture foundation for future V2 objects, services, outputs,
  metadata flow, trust preservation, fail-closed behavior, and governance
  enforcement.
- [`docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md)
  — proposed V2 API response contract for bullpen-state output, required trust
  metadata, anti-ranking rules, refusal shape, and certification gates.
- [`docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md)
  — proposed V2 frontend display contract for governance-safe UI patterns,
  trust/freshness/refusal rendering, mobile behavior, accessibility text, and
  certification gates.
- [`docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`](docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md)
  — certification and implementation-admission requirements for future V2
  evidence, testing, failure conditions, production readiness, and final
  approval gates.
- [`docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md`](docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md)
  — final governance readiness review for the V2 planning package, including
  readiness findings, implementation risks, remaining blockers, final
  determination, and next approved milestone.
- [`docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md)
  — phased implementation roadmap for future V2 work, including repo hygiene,
  backend/API/frontend sequencing, testing expectations, certification gates,
  rollout controls, stop conditions, and the next implementation milestone.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md)
  — completed backend-only V2 Phase 1 record for domain objects, architecture
  purpose, governance compliance, V1 preservation, and no-API/no-frontend
  boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_2_CONTEXT_ASSEMBLY.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_2_CONTEXT_ASSEMBLY.md)
  — completed backend-only V2 Phase 2 record for context assembly, source
  evidence mapping, fail-closed behavior, governance compliance, V1
  preservation, and no-API/no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_3_NEUTRAL_INTELLIGENCE.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_3_NEUTRAL_INTELLIGENCE.md)
  — completed backend-only V2 Phase 3 record for neutral internal category
  summaries, expanded candidate groups, fail-closed behavior, governance
  compliance, V1 preservation, and no-API/no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_4_INVENTORY_VISIBILITY.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_4_INVENTORY_VISIBILITY.md)
  — completed backend-only V2 Phase 4 record for deterministic inventory
  summaries, inventory evidence, fail-closed behavior, governance compliance,
  V1 preservation, and no-API/no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_5_TEAM_BULLPEN_CONTEXT.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_5_TEAM_BULLPEN_CONTEXT.md)
  — completed backend-only V2 Phase 5 record for deterministic team bullpen
  context summaries, team-level evidence, fail-closed behavior, governance
  compliance, V1 preservation, and no-API/no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_6_TRUST_METADATA_INTEGRATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_6_TRUST_METADATA_INTEGRATION.md)
  — completed backend-only V2 Phase 6 record for mandatory trust metadata
  enforcement, missing-metadata fail-closed behavior, governance compliance,
  V1 preservation, and no-API/no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_7_REFUSAL_FAIL_CLOSED.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_7_REFUSAL_FAIL_CLOSED.md)
  — completed backend-only V2 Phase 7 record for refusal/fail-closed
  integration, degraded-output handling, evidence safety handling, governance
  compliance, V1 preservation, and no-API/no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_8_API_CONTRACT_EXPOSURE.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_8_API_CONTRACT_EXPOSURE.md)
  — completed backend-only V2 Phase 8 record for the approved bullpen-state
  API endpoint, deterministic serialization, fail-closed API responses,
  governance compliance, V1 preservation, and no-frontend boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md)
  — completed V2 Phase 9 record for frontend client consumption of the
  approved bullpen-state endpoint, contract normalization, fail-closed client
  handling, governance compliance, V1 preservation, and no-UI boundaries.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md)
  — completed V2 Phase 10 record for governed dashboard rendering of V2
  bullpen intelligence, trust/freshness/refusal visibility, fail-closed
  display behavior, governance compliance, and V1 preservation.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md)
  — completed V2 Phase 10A record for desktop layout remediation of the
  governed V2 panel, container-aware metadata grids, readability preservation,
  governance compliance, and V1 preservation.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md)
  — completed V2 Phase 10B record for Bullpen selected-pitcher layout
  remediation, readable detail and recommendation trust surfaces, governance
  compliance, and V1 preservation.
- [`docs/RECOMMENDATION_ENGINE_V2_PHASE_11_MOBILE_ACCESSIBILITY.md`](docs/RECOMMENDATION_ENGINE_V2_PHASE_11_MOBILE_ACCESSIBILITY.md)
  — completed V2 Phase 11 record for mobile and accessibility validation of
  the Dashboard V2 panel, Bullpen selected-pitcher detail surface, embedded V1
  Candidate Evaluation surface, trust/freshness/refusal visibility, keyboard
  access, focus visibility, governance compliance, and V1 preservation.
- [`docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md`](docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md)
  — completed V2 Phase 12 record for certification readiness validation,
  backend/API/frontend evidence, trust/freshness/refusal/fail-closed evidence,
  governance compliance, V1 regression evidence, known limitations, and the
  readiness classification for formal certification review.
- [`docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md`](docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md)
  — completed V2 Phase 13 formal certification record for the implemented and
  governed V2 scope, certification decision, backend/API/frontend evidence,
  trust/freshness/refusal/fail-closed evidence, anti-ranking and
  anti-selection validation, V1 regression validation, known limitations, and
  post-certification boundaries.
- [`docs/V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md`](docs/V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md)
  — completed V2.5 Phase 14 record for summary-first inventory presentation,
  collapsible inventory membership, count visibility, preserved evidence,
  preserved trust/freshness metadata, mobile page-length reduction, and
  governance compliance.
- [`docs/V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md`](docs/V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md)
  — completed V2.5 Phase 15 record for full Dashboard V2 intelligence
  presentation audit, summary-first candidate groups, collapsible team
  context, collapsible limitation/explanation/refusal details, mobile
  page-length reduction, transparency preservation, and governance compliance.
- [`docs/V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md`](docs/V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md)
  — corrective Dashboard V2 production UX record for nested inventory,
  candidate group, Team Context indicator, limitation, explanation, and
  refusal disclosure controls while preserving transparency and governance.
- [`docs/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md`](docs/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md)
  — completed V2.5 Phase 16 governance decision approving the current
  certified V2 Dashboard experience for production rollout while preserving
  the no-ranking, no-selection, no-prediction, trust, freshness, refusal, and
  fail-closed boundaries.
- [`docs/V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md`](docs/V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md)
  — completed V2.5 Phase 17 post-rollout monitoring and boundary review record
  for governance drift, contract drift, UX drift, technical-debt warnings,
  regression protection, and continued production boundary preservation.
- [`docs/V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md`](docs/V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md)
  — completed V2.5 Phase 18 maintenance warning remediation review record for
  backend warning inventory, warning classification, safe remediation,
  deferred warnings, regression validation, and governance preservation.
- [`docs/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md`](docs/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md)
  — completed V2.5 Phase 19 prototype surface maintenance review record for
  production, supported, prototype, experimental, legacy, and deprecated
  surface classification, governance risk review, cleanup recommendations, and
  boundary preservation.
- [`docs/V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md`](docs/V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md)
  — completed V2.5 Phase 20 lifecycle policy for prototype promotion,
  experimental support, production eligibility, legacy classification,
  deprecation, removal, and future intelligence-surface governance gates.
- [`docs/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md`](docs/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md)
  — completed V2.5 Phase 21 operational checklist for enforcing lifecycle
  promotion, production eligibility, deprecation, removal, and future
  intelligence-surface governance review.
- [`docs/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md`](docs/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md)
  — completed V2.5 Phase 22 audit layer for lifecycle review logging,
  checklist adoption evidence, surface-by-surface readiness findings, and
  owner/runbook/metadata/test evidence requirements.
- [`docs/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md`](docs/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md)
  — completed V2.5 Phase 23 framework for owner assignment, evidence backfill,
  evidence gap inventory, promotion-readiness review, and acquisition
  priorities before lifecycle movement.
- [`docs/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md`](docs/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md)
  — completed V2.5 Phase 24 framework for standard lifecycle evidence packets,
  packet review requirements, initial packet stubs, prioritization, and
  explicit missing-evidence tracking.
- [`docs/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md`](docs/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md)
  — completed V2.5 Phase 25 review pass for evidence packet structure,
  completeness scoring, readiness classification, known evidence backfill, and
  remaining packet gaps.
- [`docs/V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md`](docs/V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md)
  — completed V2.5 Phase 26 production stewardship review for evidence
  citation standards, citation quality, certified-scope source references, and
  remaining uncited packet evidence.
- [`docs/V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md`](docs/V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md)
  — completed V2.5 Phase 27 section-level citation map for certified
  production evidence, stewardship traceability, remaining uncited evidence,
  and governance closeout readiness.
- [`docs/V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md`](docs/V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md)
  — completed V2.5 Phase 28 closeout for production evidence ownership,
  monitoring artifact format, retention cadence, exact test mapping, and
  remaining operational retention risks.
- [`docs/V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md`](docs/V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md)
  — completed V2.5 Phase 29 formal governance hardening closeout, gap
  classification, V3 product capability planning readiness, and certified V2
  boundary preservation.
- [`docs/V2_PRODUCTION_FAIL_CLOSED_DIAGNOSIS.md`](docs/V2_PRODUCTION_FAIL_CLOSED_DIAGNOSIS.md)
  — completed V2 production fail-closed diagnosis finding that the degraded
  fail-closed state is correctly triggered by stale source evidence while
  user-facing communication needs a bounded remediation plan.
- [`docs/V2_PRODUCTION_FAIL_CLOSED_COMMUNICATION_AND_FRESHNESS_REMEDIATION.md`](docs/V2_PRODUCTION_FAIL_CLOSED_COMMUNICATION_AND_FRESHNESS_REMEDIATION.md)
  — completed V2 production remediation for fail-closed communication,
  freshness metadata, sync-status visibility, and Dashboard degraded-state
  explanation while preserving certified governance boundaries.
- [`docs/V3_PHASE_1_PRODUCT_CAPABILITY_REVIEW_AND_PRIORITY_DECISION.md`](docs/V3_PHASE_1_PRODUCT_CAPABILITY_REVIEW_AND_PRIORITY_DECISION.md)
  — completed V3 Phase 1 product capability review and priority decision,
  neutral option matrix, Team Operations Bullpen Readiness planning
  recommendation, and governance boundary preservation.
- [`docs/V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION.md`](docs/V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION.md)
  — completed V3 Phase 2 Team Operations Bullpen Readiness capability
  definition, allowed/prohibited behavior, readiness vocabulary, metadata
  requirements, refusal/fail-closed requirements, and certification gates.
- [`docs/V3_PHASE_3_TEAM_OPERATIONS_BULLPEN_READINESS_IMPLEMENTATION_PLAN.md`](docs/V3_PHASE_3_TEAM_OPERATIONS_BULLPEN_READINESS_IMPLEMENTATION_PLAN.md)
  — completed V3 Phase 3 Team Operations Bullpen Readiness implementation
  plan, proposed backend architecture, proposed API endpoint strategy,
  proposed response contract, frontend presentation approach, test strategy,
  certification strategy, rollout strategy, and governance boundary
  preservation.
- [`docs/V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md`](docs/V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS.md)
  — completed V3 Phase 4 Team Operations Bullpen Readiness API contract and
  certification requirements, official route strategy, request/response
  contract, readiness metadata contracts, fail-closed contract, response
  examples, and backend/frontend/accessibility/governance certification gates.
- [`docs/V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md`](docs/V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md)
  — completed V3 Phase 5 Team Operations Bullpen Readiness backend domain
  foundation, contract constants, metadata objects, deterministic assembly,
  fail-closed behavior, focused backend tests, and no route/frontend exposure.
- [`docs/V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md`](docs/V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md)
  — completed V3 Phase 6 Team Operations Bullpen Readiness internal route
  integration, allowed/forbidden query validation, route metadata, fail-closed
  route behavior, focused backend route tests, and no frontend exposure.
- [`docs/V3_PHASE_7_TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE_CERTIFICATION_READINESS_REVIEW.md`](docs/V3_PHASE_7_TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE_CERTIFICATION_READINESS_REVIEW.md)
  — completed V3 Phase 7 Team Operations Bullpen Readiness route
  certification-readiness review, contract compliance review, governance
  preservation review, fail-closed review, V2 regression review, and
  `READY_FOR_FRONTEND_INTEGRATION_PLANNING` decision without production
  certification.
- [`docs/V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN.md`](docs/V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN.md)
  — completed V3 Phase 8 Team Operations Bullpen Readiness frontend
  integration plan for governed Dashboard placement, client normalization,
  summary-first rendering, expand-on-demand evidence, metadata presentation,
  accessibility, mobile behavior, neutral language rules, and frontend tests
  without runtime UI changes.
- [`docs/V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS.md`](docs/V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS.md)
  — completed V3 Phase 9 Team Operations Bullpen Readiness frontend client
  normalization and contract tests for the internal route, including governed
  success, degraded, refused, missing-field, malformed-governance, unknown
  vocabulary, and internal-status handling without Dashboard UI changes.
- [`docs/V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION.md`](docs/V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION.md)
  — completed V3 Phase 10 Team Operations Bullpen Readiness Dashboard UI
  integration for the internal route, including summary-first rendering,
  expand-on-demand context/evidence/metadata, trust/freshness/refusal
  visibility, governance metadata, accessibility controls, and frontend
  rendering tests without production certification.
- [`docs/V3_PHASE_11_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_CERTIFICATION_READINESS_REVIEW.md`](docs/V3_PHASE_11_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_CERTIFICATION_READINESS_REVIEW.md)
  — completed V3 Phase 11 Team Operations Bullpen Readiness Dashboard UI
  certification-readiness review, including UI rendering, neutral language,
  metadata visibility, refusal/fail-closed visibility, accessibility,
  frontend test coverage, V2 regression review, and
  `READY_FOR_FORMAL_CERTIFICATION_PLANNING` decision without production
  certification.
- [`docs/V3_PHASE_12_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_PLAN_AND_ROLLOUT_PREREQUISITES.md`](docs/V3_PHASE_12_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_PLAN_AND_ROLLOUT_PREREQUISITES.md)
  — completed V3 Phase 12 formal certification plan and rollout prerequisite
  checklist for Team Operations Bullpen Readiness, including backend,
  frontend, accessibility, governance, freshness, trust, refusal/fail-closed,
  V2 regression, monitoring artifact, evidence packet, rollout prerequisite,
  and stop-condition requirements without production certification.
- [`docs/RECOMMENDATION_ENGINE_V1_CANDIDATE_EVALUATION_LAYOUT_REMEDIATION.md`](docs/RECOMMENDATION_ENGINE_V1_CANDIDATE_EVALUATION_LAYOUT_REMEDIATION.md)
  — completed V1 Candidate Evaluation layout remediation record for the
  embedded selected-pitcher article, single-column embedded rendering,
  governance compliance, and V1 logic preservation.
- [`docs/DASHBOARD_BULLPEN_LOADING_PERFORMANCE_REMEDIATION.md`](docs/DASHBOARD_BULLPEN_LOADING_PERFORMANCE_REMEDIATION.md)
  — completed Dashboard and Bullpen loading performance remediation record for
  batched availability evidence loading, lean V2 API serialization, duplicate
  sync-status request removal, and governance preservation.
- [`docs/RECOMMENDATION_ENGINE_V1_POLICY.md`](docs/RECOMMENDATION_ENGINE_V1_POLICY.md)
  — authoritative policy for trust-first recommendation eligibility,
  exclusions, refusal conditions, categories, explanations, limitations, and
  governance boundaries.
- [`docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md)
  — staged engineering plan for translating the approved policy into backend
  boundaries, gates, payloads, tests, API exposure, UI planning, and governance
  validation.
- [`docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md)
  - candidate-level API contract for request and response shapes, trust
  fields, freshness fields, refusal handling, frontend display requirements,
  and no-ranking/no-selection guarantees.
- [`docs/RECOMMENDATION_ENGINE_V1_FRONTEND_CONTRACT.md`](docs/RECOMMENDATION_ENGINE_V1_FRONTEND_CONTRACT.md)
  - frontend display contract for future candidate-level UI presentation,
  required trust and freshness visibility, refusal states, safe copy,
  accessibility, and no-ranking/no-selection guarantees.
- [`docs/RECOMMENDATION_ENGINE_V1_UI_IMPLEMENTATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V1_UI_IMPLEMENTATION_PLAN.md)
  - staged UI implementation plan for candidate-level display
  architecture, component boundaries, trust and freshness visibility,
  refusal states, mobile/accessibility expectations, testing, and guardrails.
- [`docs/RECOMMENDATION_ENGINE_V1_DASHBOARD_INTEGRATION_PLAN.md`](docs/RECOMMENDATION_ENGINE_V1_DASHBOARD_INTEGRATION_PLAN.md)
  - dashboard integration plan for safely placing candidate-level
  recommendation evaluation in the existing pitcher detail workflow without
  ranking or final selection.
- [`docs/BULLPEN_AVAILABILITY_ENGINE_V1.md`](docs/BULLPEN_AVAILABILITY_ENGINE_V1.md)
  — status definitions, implemented classifier contract, UI presentation, trust
  rules, and non-goals.
- [`docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`](docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md)
  — governance process and current threshold baseline.
- [`docs/SETUP.md`](docs/SETUP.md) — local setup, environment variables, troubleshooting,
  deployment notes, and the automated-sync guide.
- [`frontend/docs/dashboard_trust_strip_polish.md`](frontend/docs/dashboard_trust_strip_polish.md)
  — dashboard trust strip layout and messaging rationale.
- **In-app Methodology page** — how the fatigue model works, its weights, and its limitations.

## Roadmap

Recommendation Engine V1 is complete, certified, and production-ready for
candidate-level evaluation in the pitcher detail workflow. It preserves visible
confidence, freshness, availability, explanations, limitations, refusal
reasons, `ranking_applied=false`, and `selection_made=false`.

Recommendation Engine V2 has strategy, governance boundaries, architecture,
API contract, frontend contract, certification requirements, implementation
readiness, implementation planning, the Phase 1 backend domain object
foundation, the Phase 2 backend context assembly layer, and the Phase 3
backend-only neutral intelligence expansion, the Phase 4 backend-only
inventory visibility layer, and the Phase 5 backend-only team bullpen context
layer, the Phase 6 backend-only trust metadata integration layer, and the
Phase 7 backend-only refusal/fail-closed integration layer, and the Phase 8
backend-only API contract exposure layer, and the Phase 9 frontend client
integration layer, and the Phase 10 governed frontend rendering layer
complete, with Phase 10A desktop layout remediation and Phase 10B Bullpen
selected-pitcher layout remediation complete, and Phase 11 mobile and
accessibility validation complete. Phase 12 certification readiness validation
is complete and classifies V2 as ready for formal certification review, not
production certified. Phase 13 formal certification review is complete and
certifies the implemented and governed V2 scope as production-ready; production
rollout still requires a separate governed rollout decision. V2.5 Phase 14 is
complete and reduces initial inventory page length by rendering category
summaries first, with full membership and evidence available through expansion.
V2.5 Phase 15 is complete and reduces full Dashboard V2 intelligence density
by rendering candidate groups, team context, limitations, explanations, and
refusal details as summaries first, with complete detail available through
expansion. A Dashboard V2 collapsible remediation later corrects the live
production panel with nested member/detail controls and structured Team
Context indicator summaries. V2.5 Phase 16 is complete and approves the
current certified V2 Dashboard experience for production rollout within the
implemented scope only.
V2.5 Phase 17 is complete and establishes post-rollout monitoring, warning
review, regression-protection review, and boundary review for the approved
production scope. V2.5 Phase 18 is complete and remediates the current backend
test warning debt, reducing the full backend suite from 139 warnings to 0
warnings while preserving Recommendation Engine V2 governance. V2.5 Phase 19
is complete and inventories prototype, experimental, legacy, deprecated,
supported, and production surfaces without expanding Recommendation Engine V2.
V2.5 Phase 20 is complete and establishes the official promotion and
deprecation lifecycle policy for those surface classifications. V2.5 Phase 21
is complete and converts that lifecycle policy into enforceable checklists for
promotion, production eligibility, deprecation, removal, and intelligence
surface review. V2.5 Phase 22 is complete and adds the lifecycle review log
and adoption audit layer that proves checklist usage and evidence gaps are
tracked before any future lifecycle movement. V2.5 Phase 23 is complete and
converts those audit findings into a structured owner assignment and evidence
backfill plan for prototype, experimental, supported, and legacy surfaces.
V2.5 Phase 24 is complete and creates the standard lifecycle evidence packet
template plus initial packet stubs for selected production, prototype,
experimental, and legacy surfaces. V2.5 Phase 25 is complete and reviews those
packet stubs, records known evidence, identifies missing evidence, and assigns
readiness classifications for the first formal backfill execution pass. V2.5
Phase 26 is complete and performs the first citation backfill and stewardship
review for certified production evidence. Phase 27 is complete and maps those
production evidence citations to source-document sections where current records
support section-level proof. Phase 28 is complete and assigns production
evidence retention ownership, defines monitoring artifact format, and maps
current production governance evidence to exact test files and test names where
available. Phase 29 is complete and formally closes the V2.5 governance
hardening program, with V3 product capability planning ready under the existing
governance gates. The V2 production fail-closed diagnosis is complete and
classifies the observed production state as correctly degraded by stale source
evidence. The communication and freshness metadata remediation is also complete,
with explicit sync status, source freshness, aggregate V2 freshness, reason
code, trust status, freshness status, and safe partial-output metadata surfaced
for the Dashboard. V3 Phase 1 is complete and selects Team Operations Bullpen
Readiness planning as the next product direction after reviewing current
certified capabilities, prototype surfaces, experimental surfaces, legacy
surfaces, data availability, implementation risk, governance risk, portfolio
value, and baseball operations value. V3 Phase 2 is complete and defines that
readiness capability before implementation, preserving the existing
no-ranking, no-selection, no-prediction, and no decision-language boundaries.
V3 Phase 3 is complete and defines the implementation plan for that readiness
capability, including the preferred separate Team Operations backend/API
architecture, governed response contract, Dashboard integration plan, testing
strategy, certification strategy, and rollout path. V3 Phase 4 is complete and
establishes the official readiness API contract and certification requirements
for the separate Team Operations route. V3 Phase 5 is complete and implements
the separate backend domain foundation with governed readiness contracts,
deterministic assembly, fail-closed behavior, and backend tests, without
registering the route or adding frontend behavior. V3 Phase 6 is complete and
registers that route as an internal, non-production, uncertified Flask surface
with governed request validation and fail-closed route tests, without frontend
exposure or production certification. V3 Phase 7 is complete and reviews that
internal route for contract compliance, request validation, fail-closed
behavior, governance preservation, focused route/domain tests, and V2 regression
safety, classifying it as ready for frontend integration planning only. V3
Phase 8 is complete and defines the frontend integration plan for that route,
including governed Dashboard placement, client normalization, component
architecture, summary-first rendering, expand-on-demand evidence,
trust/freshness/refusal presentation, accessibility, mobile behavior, neutral
language rules, prohibited UI patterns, and frontend test requirements without
adding UI or production certification. V3 Phase 9 is complete and adds the
frontend client normalization layer and contract tests for the internal route,
including success, degraded, refused, missing-field, malformed-governance,
unknown-vocabulary, and internal-status handling without Dashboard UI,
production certification, public exposure, or Recommendation Engine V2 contract
changes.
Dashboard and Bullpen loading performance remediation is also complete, with
batched availability evidence loading, lean public V2 serialization, duplicate
Dashboard sync-status request removal, and concurrent GET de-duplication in
the frontend API helper.
Future recommendation expansion may build on those objects and internal
assembly logic to explore bullpen-level intelligence, team-level stress
intelligence, readiness visibility, certified inventory usability, and broader
explainability while preserving V1 trust protections. No V2 ranking,
final pitcher choice, or prediction behavior exists. Beyond
that, see **Product Direction** above: usage
simulation, role-aware fatigue, exports/API, and real prospect ingestion -
pursued in honest order, with prototype features labeled as such until they're
real.

## Author

Built and maintained by **Nikko** ([NickolisK24](https://github.com/NickolisK24)).
