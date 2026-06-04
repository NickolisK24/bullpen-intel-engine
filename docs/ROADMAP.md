# BaseballOS Roadmap

This roadmap records current direction and major historical milestones. It is
planning context, not an authorization to implement new behavior.

## Current Position

BaseballOS is a trust-first bullpen intelligence platform with certified V1 and
V2 recommendation governance, completed V2.5 governance hardening, V3 Team
Operations Bullpen Readiness approved for constrained controlled rollout, V4
frontend explanation surfaces approved for production rollout, and V5 Bullpen
Intelligence Surface architecture definition approved for planning-only
observation surfacing.

Current V3 status:

```text
CERTIFIED_WITH_NON_BLOCKING_OPERATIONAL_GAPS
CONTROLLED_ROLLOUT_APPROVED
READY_FOR_CONTROLLED_ROLLOUT_OBSERVATION
FULL_PRODUCTION_ROLLOUT_NOT_APPROVED
```

## Active Direction

The active platform capability track is V5 Bullpen Intelligence Surface. V5
converts existing trusted BaseballOS platform state into governed descriptive
observations without ranking, selecting, predicting, recommending, advising, or
automating a decision. V5 Phase 3 approves only the architecture definition for
the governed observation lifecycle, domain model, builder path, evidence,
trust, severity, fail-closed handling, frontend presentation, and governance
protection layer.

Recommended next milestone:

```text
V5 Phase 4 - Observation Domain And Contracts
```

The next V5 milestone should define observation domain contracts and controlled
vocabularies before any observation builders, API routes, frontend surfaces,
database changes, ranking, selection, recommendation, prediction, or pitcher
advice are authorized.

## Product Tracks

| Track | Current state | Next decision |
| --- | --- | --- |
| Bullpen Intelligence | Complete production foundation | Continue reliability and evidence retention |
| Fatigue Engine | Complete deterministic workload heuristic | Preserve transparency and avoid prediction claims |
| Availability Engine V1 | Complete | Maintain threshold governance |
| Recommendation Engine V1 | Certified / production ready | Preserve candidate-only scope |
| Recommendation Engine V2 | Certified / production rollout approved | Preserve no-ranking and no-selection boundaries |
| Team Operations Bullpen Readiness | Certified with non-blocking gaps / controlled rollout approved | Observe controlled rollout before full rollout planning |
| V4 Evidence and Explanation Layer | Availability, Team Operations readiness explanations, explanation API layer, and frontend explanation surfaces certified with non-blocking observations; production rollout approved for certified explanation surfaces | Monitor production rollout and preserve explanation-only governance |
| V5 Bullpen Intelligence Surface | Phase 3 architecture definition approved / planning only | Define observation domain contracts before implementation |
| Prospect Pipeline | Prototype | Keep prototype until ownership, data, runbook, and evidence gaps close |

## Near-Term Roadmap

1. V5 Phase 4 observation domain and contracts.
2. V4 Phase 27 post-rollout monitoring and governance preservation review.
3. Controlled rollout monitoring artifact retention for V3 readiness.
4. Post-rollout issue triage if any governance, trust, freshness, refusal, or
   accessibility issue appears.
5. Separate full production rollout decision only if controlled rollout
   evidence supports it.
6. V5 route or UI work only after architecture, observation domain contracts,
   deterministic builders, tests, and certification gates are established.

## Candidate Future Tracks

These are candidates, not commitments:

- Team Operations Bullpen Readiness full rollout planning.
- Future V4+ explanation scope expansion, new frontend surfaces, or new
  explanation APIs only after separate planning, certification, and rollout
  authorization.
- V5 architecture, observation domain contracts, deterministic observation
  builders, read-only API surface, frontend intelligence surface, governance
  validation, certification, controlled rollout review, and production approval
  review.
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

For detailed milestone history, use:

- [Changelog](CHANGELOG.md)
- [Certification ledger](governance/CERTIFICATION_LEDGER.md)
- [Operational reviews](operations/OPERATIONAL_REVIEWS.md)
- [Project state snapshot](PROJECT_STATE_2026_06.md)
