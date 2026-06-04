# BaseballOS Roadmap

This roadmap records current direction and major historical milestones. It is
planning context, not an authorization to implement new behavior.

## Current Position

BaseballOS is a trust-first bullpen intelligence platform with certified V1 and
V2 recommendation governance, completed V2.5 governance hardening, and V3 Team
Operations Bullpen Readiness approved for constrained controlled rollout and
ready for controlled rollout observation.

Current V3 status:

```text
CERTIFIED_WITH_NON_BLOCKING_OPERATIONAL_GAPS
CONTROLLED_ROLLOUT_APPROVED
READY_FOR_CONTROLLED_ROLLOUT_OBSERVATION
FULL_PRODUCTION_ROLLOUT_NOT_APPROVED
```

## Active Direction

The next platform capability track is V4 Evidence and Explanation. V4 has
certified internal backend Availability Explanation Integration and internal
backend Team Operations Readiness Explanations. V4 explains why existing
governed states appear without ranking, selecting, predicting, recommending, or
automating a decision. V4 Phase 17 certifies the internal backend Explanation
API layer with non-blocking observations for certified Availability and Team
Operations Readiness explanations. V4 Phase 18 defines frontend integration
planning for those certified APIs using progressive disclosure, compact
governance display, fail-closed UI behavior, and dashboard anti-regression
rules. V4 Phase 19 implements the first governed frontend explanation
surfaces, adding compact `Why this state?` and `Why this availability?`
actions without changing backend behavior, API contracts, recommendation
behavior, or Dashboard structure beyond the planned surfaces. V4 Phase 20
reviews those frontend surfaces for certification readiness, and V4 Phase 21
certifies them with non-blocking observations while leaving rollout approval
for a later milestone. V4 Phase 22 defines controlled rollout strategy,
monitoring expectations, manual review requirements, observation evidence,
approval gates, and rollback conditions for those certified frontend
explanation surfaces.

Recommended next milestone:

```text
V4 Phase 23 - Frontend Explanation Surface Controlled Rollout
```

The next V4 milestone should execute the controlled rollout approval review,
capture retained manual evidence, create or update monitoring artifacts,
evaluate rollback conditions, and determine whether certified frontend
explanation surfaces may enter controlled rollout.

## Product Tracks

| Track | Current state | Next decision |
| --- | --- | --- |
| Bullpen Intelligence | Complete production foundation | Continue reliability and evidence retention |
| Fatigue Engine | Complete deterministic workload heuristic | Preserve transparency and avoid prediction claims |
| Availability Engine V1 | Complete | Maintain threshold governance |
| Recommendation Engine V1 | Certified / production ready | Preserve candidate-only scope |
| Recommendation Engine V2 | Certified / production rollout approved | Preserve no-ranking and no-selection boundaries |
| Team Operations Bullpen Readiness | Certified with non-blocking gaps / controlled rollout approved | Observe controlled rollout before full rollout planning |
| V4 Evidence and Explanation Layer | Availability, Team Operations readiness explanations, explanation API layer, and frontend explanation surfaces certified with non-blocking observations; rollout planning complete | Execute controlled rollout approval review |
| Prospect Pipeline | Prototype | Keep prototype until ownership, data, runbook, and evidence gaps close |

## Near-Term Roadmap

1. V4 Phase 23 frontend explanation surface controlled rollout review.
2. Controlled rollout monitoring artifact retention for V3 readiness.
3. Post-rollout issue triage if any governance, trust, freshness, refusal, or
   accessibility issue appears.
4. Separate full production rollout decision only if controlled rollout
   evidence supports it.
5. V4 route or UI work only after architecture, backend contracts, tests, and
   certification gates are established for the relevant explanation surface.

## Candidate Future Tracks

These are candidates, not commitments:

- Team Operations Bullpen Readiness full rollout planning.
- V4 Evidence and Explanation frontend, certification, and rollout work after
  backend route implementation, route certification planning, formal route
  certification, frontend integration planning, and separate authorization.
- Team-level operations intelligence beyond bullpen readiness.
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

For detailed milestone history, use:

- [Changelog](CHANGELOG.md)
- [Certification ledger](governance/CERTIFICATION_LEDGER.md)
- [Operational reviews](operations/OPERATIONAL_REVIEWS.md)
- [Project state snapshot](PROJECT_STATE_2026_06.md)
