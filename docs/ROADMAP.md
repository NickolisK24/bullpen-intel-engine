# BaseballOS Roadmap

This roadmap records current direction and major historical milestones. It is
planning context, not an authorization to implement new behavior.

## Current Position

BaseballOS is a trust-first bullpen availability and workload intelligence
platform with roster-status authority, team-assignment authority, stale
ownership correction, unavailable-pitcher separation, Player Detail/Bullpen
Board final availability consistency, certified V1 and V2 recommendation
governance, completed V2.5 governance hardening, V3 Team Operations Bullpen
Readiness approved for constrained controlled rollout, V4 frontend explanation
surfaces approved for production rollout, and V5 Bullpen Intelligence Surface
approved for full production rollout.

Current V3 status:

```text
CERTIFIED_WITH_NON_BLOCKING_OPERATIONAL_GAPS
CONTROLLED_ROLLOUT_APPROVED
READY_FOR_CONTROLLED_ROLLOUT_OBSERVATION
FULL_PRODUCTION_ROLLOUT_NOT_APPROVED
```

## Active Direction

The current platform posture is production trust hardening after V5 Bullpen
Intelligence Surface full production rollout approval. The active direction is
to make bullpen availability easier to inspect while preserving descriptive,
explainable, trust-first behavior and no ranking, selection, prediction,
betting, or automated recommendation behavior.

```text
V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVED
FULL_PRODUCTION_ROLLOUT_APPROVED
```

Ranking, selection, recommendation, prediction, matchup advice, pitcher advice,
betting use cases, and automated decision behavior remain unauthorized.

## Product Tracks

| Track | Current state | Next decision |
| --- | --- | --- |
| Bullpen Intelligence | Complete production foundation with roster-aware board semantics | Continue reliability and evidence retention |
| Fatigue Engine | Complete deterministic workload heuristic | Preserve transparency and avoid prediction claims |
| Availability Engine V1 | Complete with roster-adjusted final availability on board and detail surfaces | Maintain threshold governance and final/workload separation |
| Roster and Team Authority | Active roster-status authority, team-assignment authority, and stale ownership correction | Add transaction lineage only after separate approval |
| Recommendation Engine V1 | Certified / production ready | Preserve candidate-only scope |
| Recommendation Engine V2 | Certified / production rollout approved | Preserve no-ranking and no-selection boundaries |
| Team Operations Bullpen Readiness | Certified with non-blocking gaps / controlled rollout approved | Observe controlled rollout before full rollout planning |
| V4 Evidence and Explanation Layer | Availability, Team Operations readiness explanations, explanation API layer, and frontend explanation surfaces certified with non-blocking observations; production rollout approved for certified explanation surfaces | Monitor production rollout and preserve explanation-only governance |
| V5 Bullpen Intelligence Surface | Governance certified / full production rollout approved | Monitor production rollout and preserve V5 governance boundaries |
| Prospect Pipeline | Prototype | Keep prototype until ownership, data, runbook, and evidence gaps close |

## Near-Term Roadmap

1. Pitcher search.
2. Mobile review of the current bullpen board and Player Detail availability
   flow.
3. Active MLB pitchers versus bullpen arms transparency, including future
   counters for excluded starters.
4. Competitive positioning versus Rotowire.
5. Optional transaction lineage/history after separate approval.
6. V5 post-approval production monitoring and governance preservation.
7. V4 Phase 27 post-rollout monitoring and governance preservation review.

## Candidate Future Tracks

These are candidates, not commitments:

- Team Operations Bullpen Readiness full rollout planning.
- Future V4+ explanation scope expansion, new frontend surfaces, or new
  explanation APIs only after separate planning, certification, and rollout
  authorization.
- V5 runtime observation generation or rollout expansion only after separate
  governed approval.
- Team-level operations intelligence beyond bullpen readiness.
- Transaction feed ingestion for roster and ownership lineage.
- Prospect Pipeline evidence backfill and potential promotion review.
- Role-aware fatigue distinctions for starters and relievers.
- Reports, exports, and a documented API platform.
- Real minor-league prospect ingestion with a defensible source and lifecycle
  evidence packet.

## Governance Boundaries

Future roadmap work must preserve:

```text
ranking_applied === false
selection_made === false
```

Future roadmap work must not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

Any future surface that changes lifecycle tier, certification state, rollout
state, data trust assumptions, or user-facing decision language must pass the
governance and lifecycle evidence process linked from
[docs/INDEX.md](INDEX.md).

## Historical Milestone Summary

- V1 completed candidate-level recommendation certification.
- V2 implemented and certified governed bullpen-state intelligence.
- V2.5 completed lifecycle governance hardening, evidence packets, citation
  maps, ownership assignment, retention cadence, and closeout.
- V3 selected Team Operations Bullpen Readiness as the next product direction,
  implemented backend, route, client, and dashboard UI surfaces, completed
  formal certification review, remediated deployment configuration blockers,
  retained manual evidence, approved constrained controlled rollout, and
  reached controlled rollout observation readiness.
- V4 Phase 1 defined the Evidence and Explanation capability as an
  explanation-only layer for existing governed states.
- V4 Phase 2 defined architecture, explanation scopes, proposed object shapes,
  evidence item model, reason code model, governance contract, API candidates,
  frontend candidates, certification requirements, and readiness for Phase 3
  implementation planning.
- V4 Phase 3 defined the implementation roadmap, backend plan, frontend plan,
  contract plan, testing strategy, certification strategy, rollout strategy,
  documentation requirements, and readiness for Phase 4 backend domain
  foundation.
- V4 Phase 4 implemented the internal backend domain foundation, including
  explanation objects, evidence items, reason codes, limitation types,
  governance payloads, validation helpers, deterministic serialization, and
  focused backend tests.
- V4 Phase 5 implemented deterministic explanation builders, evidence helpers,
  limitation helpers, reason helpers, governance defaults, stable generated IDs,
  serialization support, and focused backend tests.
- V4 Phase 6 implemented an internal availability explanation adapter that maps
  existing Availability Engine outputs into governed V4 explanations without
  changing status assignment, API routes, frontend UI, or dashboard behavior.
- V4 Phase 7 completed certification-readiness review for availability
  explanations, with PASS decisions for coverage, evidence attribution,
  limitation handling, governance, determinism, testing, and engine
  preservation, and a PARTIAL reason-mapping observation for conservative
  positive Available-state reason granularity.
- V4 Phase 8 certified internal backend Availability Explanation Integration
  with non-blocking observations, preserving the explanation-only scope and
  leaving API, frontend, dashboard, rollout, and additional explanation
  categories for future phases.
- V4 Phase 9 defined the Team Operations Readiness explanation capability,
  including user questions, allowed and prohibited outputs, candidate scopes,
  evidence sources, reason codes, limitation model, governance definition,
  certification requirements, and readiness for Phase 10 architecture.
- V4 Phase 10 defined the Team Operations Readiness explanation architecture,
  including systems boundaries, scope architecture, evidence mapping, reason
  code strategy, limitation strategy, builder integration, object shapes,
  testing architecture, certification architecture, and readiness for Phase 11
  implementation.
- V4 Phase 11 implemented an internal backend Team Operations Readiness
  explanation adapter that maps existing readiness payloads into deterministic
  V4 explanations with governed evidence, reason, limitation, freshness, trust,
  confidence, and governance metadata without changing readiness behavior or
  exposing API/UI surfaces.
- V4 Phase 12 completed certification-readiness review for internal backend
  Team Operations Readiness explanations, with PASS decisions for coverage,
  limitation handling, governance, determinism, testing, and engine
  preservation, PARTIAL observations for conservative reason mapping and
  fatigue/risk distribution evidence, and readiness for Phase 13 formal
  certification review.
- V4 Phase 13 certified internal backend Team Operations Readiness Explanations
  with non-blocking observations, preserving explanation-only governance and
  leaving API, frontend, dashboard, rollout, Risk Distribution Explanations, and
  future readiness expansion areas for future phases.
- V4 Phase 14 defined governed API contract planning for certified V4
  Availability and Team Operations Readiness explanations, including candidate
  routes, shared response shape, fail-closed response shape, safe error
  handling, governance requirements, testing requirements, certification
  boundaries, and readiness for Phase 15 route implementation.
- V4 Phase 15 implemented governed internal backend API routes for certified
  V4 Availability and Team Operations Readiness explanations, including shared
  success and fail-closed envelopes, certified scope allowlists, safe request
  validation, route tests, and no frontend or Dashboard exposure.
- V4 Phase 16 completed certification-readiness review for explanation API
  routes, with PASS decisions for certified scope exposure, route coverage,
  response contracts, fail-closed behavior, governance, determinism, and
  behavior preservation, a PARTIAL testing observation for direct forced
  builder-validation exception coverage, and readiness for Phase 17 formal API
  certification review.
- V4 Phase 17 certified the internal backend Explanation API layer with
  non-blocking observations, preserving certified scope exposure, governed
  success and fail-closed envelopes, deterministic behavior, and source-engine
  behavior preservation while leaving frontend, Dashboard, rollout,
  Recommendation Explanations, Risk Distribution Explanations, and future
  explanation scopes for future phases.
- V4 Phase 18 defined governed frontend integration planning for certified
  explanation APIs, including candidate surfaces, default visibility,
  progressive disclosure, Availability and Team Operations Readiness UI
  strategy, fail-closed UI behavior, compact governance display, Dashboard
  anti-regression rules, frontend contract requirements, test requirements, and
  readiness for Phase 19 frontend explanation surface implementation.
- V4 Phase 19 implemented governed frontend explanation surfaces for certified
  V4 APIs, adding compact Operational Readiness and selected pitcher
  availability explanation actions, shared progressive disclosure,
  fail-closed rendering, compact governance messaging, frontend tests, and no
  backend, API contract, Dashboard redesign, ranking, selection, prediction, or
  recommendation behavior changes.
- V4 Phase 20 completed frontend explanation surface certification-readiness
  review with PASS decisions for surface coverage, certified API consumption,
  progressive disclosure, fail-closed UI, governance, UX anti-regression,
  testing, and behavior preservation, and readiness for Phase 21 formal
  frontend certification review.
- V4 Phase 21 formally certified frontend explanation surfaces with
  non-blocking observations, including Operational Readiness and selected
  pitcher Availability explanation surfaces, shared disclosure, frontend API
  normalization, fail-closed rendering, governance-safe presentation, testing,
  and behavior preservation, while leaving rollout approval for a later
  milestone.
- V4 Phase 22 defined frontend explanation surface rollout planning and
  monitoring, including rollout scope, staged rollout strategy, manual review
  requirements, monitoring expectations, rollback conditions, observation
  evidence requirements, approval gates, certification preservation, and
  readiness for Phase 23 controlled rollout review.
- V4 Phase 23 approved controlled rollout for certified frontend explanation
  surfaces, including Operational Readiness explanations, selected pitcher
  Availability explanations, shared disclosure, certified explanation APIs,
  monitoring expectations, rollback conditions, required observation evidence,
  and full production rollout boundaries.
- V4 Phase 24 reviewed available controlled rollout observation evidence for
  certified frontend explanation surfaces, found no critical governance
  regression in repository-retained records, identified incomplete retained
  desktop, mobile, responsive, accessibility, fail-closed, and monitoring
  evidence, and deferred production rollout review readiness.
- V4 Phase 25 captured and reassessed repository-retained source/test evidence
  for certified frontend explanation surfaces, confirmed no critical
  governance finding, and kept production rollout review readiness blocked
  because runtime screenshots, manual accessibility smoke evidence, live
  fail-closed evidence, and deployed monitoring observations remain incomplete.
- V4 Phase 26 formally approved production rollout for certified V4 frontend
  explanation surfaces after retained runtime evidence passed desktop, mobile,
  accessibility smoke, fail-closed, governance, Dashboard anti-regression,
  explanation, evidence, metadata, and limitation review while preserving
  explanation-only governance boundaries.
- V5 Phase 1 approved the Bullpen Intelligence Surface capability definition,
  allowed observational scope, prohibited outputs, trusted-source requirements,
  freshness and confidence requirements, fail-closed requirements,
  certification requirements, rollout sequence, and readiness for Phase 2
  observation taxonomy planning without authorizing implementation.
- V5 Phase 2 approved the Bullpen Intelligence Surface observation taxonomy,
  including authorized observation families, approved inputs, expected future
  output fields, governance boundary matrix, observation language rules,
  fail-closed requirements, and readiness for Phase 3 architecture definition
  without authorizing implementation.
- V5 Phase 3 approved the Bullpen Intelligence Surface architecture
  definition, including observation lifecycle, domain architecture, builder
  architecture, evidence architecture, trust architecture, severity
  architecture, fail-closed architecture, frontend surface architecture,
  governance protection layer, and readiness for Phase 4 observation domain
  and contracts without authorizing implementation.
- V5 Phase 4 implemented the backend observation domain and contract
  foundation, including governed enum vocabularies, dataclass contracts,
  serialization helpers, validators, prohibited-language safeguards, collection
  serialization, and focused tests without authorizing builders, API routes,
  frontend UI, database migrations, runtime observation generation, ranking,
  selection, prediction, matchup advice, pitcher advice, or decision
  automation.
- V5 Phase 5 implemented deterministic backend observation builders, supplied
  trusted-state inputs, fail-closed suppression, evidence propagation, trust and
  freshness propagation, collection assembly, and focused tests without
  authorizing API routes, frontend UI, database migrations, live runtime
  integration, ranking, selection, prediction, matchup advice, pitcher advice,
  or decision automation.
- V5 Phase 6 implemented the backend read-only observation API surface,
  including deterministic supplied-state assembly, `GET /api/observations`,
  `POST /api/observations/preview`, governed collection serialization,
  fail-closed API responses, route registration, and focused API tests without
  authorizing frontend UI, database migrations, live runtime integration,
  ranking, selection, prediction, matchup advice, pitcher advice, or decision
  automation.
- V5 Phase 7 implemented the frontend read-only Bullpen Intelligence surface,
  including `GET /api/observations` client normalization, a Dashboard panel,
  evidence, limitations, trust, freshness, confidence, explanation-reference
  display, empty/protected states, API failure handling, and focused frontend
  tests without authorizing backend decision logic, database migrations, live
  runtime integration, ranking, selection, prediction, matchup advice, pitcher
  advice, or decision automation.
- V5 Phase 8 certified the combined Bullpen Intelligence Surface governance
  boundary across contracts, builders, API, frontend rendering, tests, and
  documentation, preserving false ranking and selection flags and marking the
  surface controlled-rollout ready without approving full production rollout.
- V5 Phase 9 approved controlled rollout for the certified Bullpen Intelligence
  Surface while preserving false ranking and selection flags and keeping full
  production rollout unapproved.
- V5 Phase 10 completed production rollout review and retained full production
  rollout as not approved because retained production-readiness evidence is
  incomplete.
- V5 Phase 11 retained manual production evidence, cleared the Phase 10
  production evidence blocker, and recorded readiness for Phase 12 full
  production rollout approval review while keeping full production rollout
  unapproved.
- V5 Phase 12 approved full production rollout for the certified Bullpen
  Intelligence Surface while preserving false ranking and selection flags and
  keeping future runtime integration, observation-family expansion, ranking,
  selection, prediction, pitcher advice, matchup advice, manager advice, and
  automated decision-making outside the approval.

For detailed milestone history, use:

- [Changelog](CHANGELOG.md)
- [Certification ledger](governance/CERTIFICATION_LEDGER.md)
- [Operational reviews](operations/OPERATIONAL_REVIEWS.md)
- [Project state snapshot](PROJECT_STATE_2026_06.md)
