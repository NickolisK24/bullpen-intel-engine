# BaseballOS Certification Ledger

This ledger summarizes certification, production, rollout, and governance state
by surface. Detailed evidence remains in the linked source records.

## Current Certification Summary

| Surface | Certification status | Rollout status | Evidence |
| --- | --- | --- | --- |
| Recommendation Engine V1 | Certified / production ready | Production-ready candidate-level surface | [V1 completion certification](../archive/2026-06/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md) |
| Recommendation Engine V2 / Dashboard V2 bullpen-state intelligence | Certified / production ready | Production rollout approved for implemented scope | [V2 formal certification](RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md), [V2.5 Phase 16 rollout decision](../archive/2026-06/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md) |
| V2.5 governance hardening | Complete | Governance closeout complete | [V2.5 Phase 29 closeout](../archive/2026-06/V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md) |
| Team Operations Bullpen Readiness | Certified with non-blocking operational gaps | Controlled rollout approved; full production rollout not approved | [V3 Phase 13 certification review](../archive/2026-06/V3_PHASE_13_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_REVIEW.md), [V3 Phase 19 controlled rollout approval](../archive/2026-06/V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md) |
| Availability Explanation Integration | Certified with non-blocking observations | Internal backend only; API, frontend, dashboard, and rollout not approved | [V4 Phase 8 formal certification](../archive/2026-06/V4_PHASE_8_AVAILABILITY_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |
| Team Operations Readiness Explanations | Certified with non-blocking observations | Internal backend only; API, frontend, dashboard, and rollout not approved | [V4 Phase 13 formal certification](../archive/2026-06/V4_PHASE_13_TEAM_OPERATIONS_READINESS_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |
| V4 Explanation API Layer | Certified with non-blocking observations | Internal backend API only; frontend, dashboard, and rollout not approved | [V4 Phase 17 formal certification](../archive/2026-06/V4_PHASE_17_EXPLANATION_API_FORMAL_CERTIFICATION_REVIEW.md) |
| V4 Frontend Explanation Surfaces | Certified with non-blocking observations | Full production rollout approved for certified explanation surfaces | [V4 Phase 21 formal certification](../archive/2026-06/V4_PHASE_21_FRONTEND_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md), [V4 Phase 22 rollout planning](../archive/2026-06/V4_PHASE_22_FRONTEND_EXPLANATION_ROLLOUT_PLANNING_AND_MONITORING.md), [V4 Phase 23 controlled rollout decision](../archive/2026-06/V4_PHASE_23_FRONTEND_EXPLANATION_CONTROLLED_ROLLOUT_DECISION.md), [V4 Phase 24 observation review](../archive/2026-06/V4_PHASE_24_FRONTEND_EXPLANATION_CONTROLLED_ROLLOUT_OBSERVATION_REVIEW.md), [V4 Phase 25 evidence reassessment](../archive/2026-06/V4_PHASE_25_FRONTEND_EXPLANATION_EVIDENCE_CAPTURE_AND_REASSESSMENT.md), [V4 Phase 26 production rollout review](../archive/2026-06/V4_PHASE_26_PRODUCTION_ROLLOUT_REVIEW.md) |
| V5 Bullpen Intelligence Surface | Governance certified | Full production rollout approved for certified V5 observation surface | [V5 Phase 1 capability definition](../archive/2026-06/V5_PHASE_1_BULLPEN_INTELLIGENCE_SURFACE_CAPABILITY_DEFINITION.md), [V5 Phase 2 observation taxonomy](../archive/2026-06/V5_PHASE_2_BULLPEN_INTELLIGENCE_SURFACE_OBSERVATION_TAXONOMY.md), [V5 Phase 3 architecture definition](../archive/2026-06/V5_PHASE_3_BULLPEN_INTELLIGENCE_SURFACE_ARCHITECTURE_DEFINITION.md), [V5 Phase 4 observation domain and contracts](../archive/2026-06/V5_PHASE_4_OBSERVATION_DOMAIN_AND_CONTRACTS.md), [V5 Phase 5 observation builder foundation](../archive/2026-06/V5_PHASE_5_OBSERVATION_BUILDER_FOUNDATION.md), [V5 Phase 6 observation API surface](../archive/2026-06/V5_PHASE_6_OBSERVATION_API_SURFACE.md), [V5 Phase 7 frontend intelligence surface](../archive/2026-06/V5_PHASE_7_FRONTEND_INTELLIGENCE_SURFACE.md), [V5 Phase 8 governance certification](../archive/2026-06/V5_PHASE_8_GOVERNANCE_CERTIFICATION.md), [V5 Phase 9 controlled rollout review](../archive/2026-06/V5_PHASE_9_CONTROLLED_ROLLOUT_REVIEW.md), [V5 Phase 10 production rollout review](../archive/2026-06/V5_PHASE_10_PRODUCTION_ROLLOUT_REVIEW.md), [V5 Phase 11 production evidence review](../archive/2026-06/V5_PHASE_11_PRODUCTION_EVIDENCE_REVIEW.md), [V5 Phase 12 full production rollout approval](../archive/2026-06/V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVAL.md) |
| Prospect Pipeline | Prototype | Not promotion-ready | [V2.5 Phase 19 prototype surface review](../archive/2026-06/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md), [V2.5 Phase 23 evidence backfill plan](../archive/2026-06/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md) |

## Mandatory Governance Invariants

The certified recommendation, readiness, explanation, and Bullpen Intelligence
surfaces preserve:

```text
ranking_applied === false
selection_made === false
```

The certified V4 explanation surfaces additionally preserve:

```text
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The certified recommendation, readiness, explanation, and Bullpen Intelligence
surfaces do not authorize:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

## Production And Rollout Decisions

| Decision | Result | Source |
| --- | --- | --- |
| V1 completion certification | Certified / production ready for candidate-level evaluation | [V1 completion certification](../archive/2026-06/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md) |
| V2 formal certification | Certified / production ready for governed implemented scope | [V2 formal certification](RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md) |
| V2 production rollout | Approved for certified Dashboard V2 implemented scope | [V2.5 Phase 16 rollout decision](../archive/2026-06/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md) |
| V2.5 governance closeout | Governance hardening closed; remaining gaps non-blocking | [V2.5 Phase 29 closeout](../archive/2026-06/V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md) |
| V3 readiness formal certification | Certified with non-blocking operational gaps | [V3 Phase 13 certification review](../archive/2026-06/V3_PHASE_13_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_REVIEW.md) |
| V3 readiness controlled rollout | Controlled rollout approved | [V3 Phase 19 controlled rollout approval](../archive/2026-06/V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md) |
| V3 readiness full production rollout | Not approved | [V3 Phase 19 controlled rollout approval](../archive/2026-06/V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md) |
| V4 availability explanation certification | Certified with non-blocking observations for internal backend integration only | [V4 Phase 8 formal certification](../archive/2026-06/V4_PHASE_8_AVAILABILITY_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |
| V4 Team Operations readiness explanation certification | Certified with non-blocking observations for internal backend explanations only | [V4 Phase 13 formal certification](../archive/2026-06/V4_PHASE_13_TEAM_OPERATIONS_READINESS_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |
| V4 explanation API contract planning | Complete; route implementation authorized for certified explanation types only | [V4 Phase 14 API contract planning](../archive/2026-06/V4_PHASE_14_EXPLANATION_API_CONTRACT_PLANNING.md) |
| V4 explanation API route implementation | Complete; internal backend routes implemented for certified explanation types only | [V4 Phase 15 route implementation](../archive/2026-06/V4_PHASE_15_EXPLANATION_API_ROUTE_IMPLEMENTATION.md) |
| V4 explanation API route certification readiness | Ready for formal API certification review; not yet formally API-certified | [V4 Phase 16 route certification readiness](../archive/2026-06/V4_PHASE_16_EXPLANATION_API_ROUTE_CERTIFICATION_READINESS_REVIEW.md) |
| V4 explanation API formal certification | Certified with non-blocking observations for internal backend API layer only | [V4 Phase 17 formal certification](../archive/2026-06/V4_PHASE_17_EXPLANATION_API_FORMAL_CERTIFICATION_REVIEW.md) |
| V4 frontend explanation surface implementation | Complete; compact frontend explanation surfaces implemented without rollout approval | [V4 Phase 19 frontend implementation](../archive/2026-06/V4_PHASE_19_FRONTEND_EXPLANATION_SURFACE_IMPLEMENTATION.md) |
| V4 frontend explanation surface certification readiness | Ready for formal frontend certification review; not yet formally certified | [V4 Phase 20 certification readiness review](../archive/2026-06/V4_PHASE_20_FRONTEND_EXPLANATION_SURFACE_CERTIFICATION_READINESS_REVIEW.md) |
| V4 frontend explanation surface formal certification | Certified with non-blocking observations; production rollout not approved | [V4 Phase 21 formal certification](../archive/2026-06/V4_PHASE_21_FRONTEND_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |
| V4 frontend explanation surface rollout planning | Ready for controlled rollout review; controlled rollout and production rollout not yet approved | [V4 Phase 22 rollout planning](../archive/2026-06/V4_PHASE_22_FRONTEND_EXPLANATION_ROLLOUT_PLANNING_AND_MONITORING.md) |
| V4 frontend explanation surface controlled rollout | Controlled rollout approved; full production rollout not approved | [V4 Phase 23 controlled rollout decision](../archive/2026-06/V4_PHASE_23_FRONTEND_EXPLANATION_CONTROLLED_ROLLOUT_DECISION.md) |
| V4 frontend explanation surface controlled rollout observation | Controlled rollout review required; production rollout review not ready | [V4 Phase 24 observation review](../archive/2026-06/V4_PHASE_24_FRONTEND_EXPLANATION_CONTROLLED_ROLLOUT_OBSERVATION_REVIEW.md) |
| V4 frontend explanation surface evidence reassessment | Controlled rollout review required; production rollout review not ready | [V4 Phase 25 evidence reassessment](../archive/2026-06/V4_PHASE_25_FRONTEND_EXPLANATION_EVIDENCE_CAPTURE_AND_REASSESSMENT.md) |
| V4 frontend explanation surface production rollout | Full production rollout approved for certified explanation surfaces | [V4 Phase 26 production rollout review](../archive/2026-06/V4_PHASE_26_PRODUCTION_ROLLOUT_REVIEW.md) |
| V5 Phase 1 capability definition | Capability definition approved; implementation not authorized | [V5 Phase 1 capability definition](../archive/2026-06/V5_PHASE_1_BULLPEN_INTELLIGENCE_SURFACE_CAPABILITY_DEFINITION.md) |
| V5 Phase 2 observation taxonomy | Observation taxonomy approved; implementation not authorized | [V5 Phase 2 observation taxonomy](../archive/2026-06/V5_PHASE_2_BULLPEN_INTELLIGENCE_SURFACE_OBSERVATION_TAXONOMY.md) |
| V5 Phase 3 architecture definition | Architecture definition approved; implementation not authorized | [V5 Phase 3 architecture definition](../archive/2026-06/V5_PHASE_3_BULLPEN_INTELLIGENCE_SURFACE_ARCHITECTURE_DEFINITION.md) |
| V5 Phase 4 observation domain and contracts | Backend foundation certified; builders, API, frontend, runtime observations, and rollout not approved | [V5 Phase 4 observation domain and contracts](../archive/2026-06/V5_PHASE_4_OBSERVATION_DOMAIN_AND_CONTRACTS.md) |
| V5 Phase 5 observation builder foundation | Backend builders complete; API, frontend, runtime observations, and rollout not approved | [V5 Phase 5 observation builder foundation](../archive/2026-06/V5_PHASE_5_OBSERVATION_BUILDER_FOUNDATION.md) |
| V5 Phase 6 observation API surface | Backend read-only API complete; frontend, runtime observations, and rollout not approved | [V5 Phase 6 observation API surface](../archive/2026-06/V5_PHASE_6_OBSERVATION_API_SURFACE.md) |
| V5 Phase 7 frontend intelligence surface | Frontend read-only surface complete; governance certification addressed by Phase 8; runtime observations and rollout not approved | [V5 Phase 7 frontend intelligence surface](../archive/2026-06/V5_PHASE_7_FRONTEND_INTELLIGENCE_SURFACE.md) |
| V5 Phase 8 governance certification | Governance certified; controlled rollout ready; full production rollout not approved | [V5 Phase 8 governance certification](../archive/2026-06/V5_PHASE_8_GOVERNANCE_CERTIFICATION.md) |
| V5 Phase 9 controlled rollout review | Controlled rollout approved; full production rollout not approved | [V5 Phase 9 controlled rollout review](../archive/2026-06/V5_PHASE_9_CONTROLLED_ROLLOUT_REVIEW.md) |
| V5 Phase 10 production rollout review | Production rollout not approved; retained production-readiness evidence required | [V5 Phase 10 production rollout review](../archive/2026-06/V5_PHASE_10_PRODUCTION_ROLLOUT_REVIEW.md) |
| V5 Phase 11 production evidence review | Production evidence retained; ready for full production rollout approval review; full production rollout not approved | [V5 Phase 11 production evidence review](../archive/2026-06/V5_PHASE_11_PRODUCTION_EVIDENCE_REVIEW.md) |
| V5 Phase 12 full production rollout approval | Full production rollout approved for certified V5 observation surface | [V5 Phase 12 full production rollout approval](../archive/2026-06/V5_PHASE_12_FULL_PRODUCTION_ROLLOUT_APPROVAL.md) |

## Evidence Requirements

Certification and rollout evidence should remain traceable to:

- backend validation
- frontend validation
- V2 regression validation where applicable
- contract review
- trust metadata review
- freshness metadata review
- refusal/fail-closed review
- governance invariant review
- accessibility review where frontend surfaces are involved
- monitoring artifacts where rollout or operational review is involved
- owner and retention records for promoted surfaces

## Lifecycle Governance

Lifecycle movement must follow:

- [Lifecycle enforcement checklist](../archive/2026-06/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md)
- [Lifecycle review log and adoption audit](../archive/2026-06/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md)
- [Lifecycle evidence backfill and owner assignment plan](../archive/2026-06/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md)
- [Lifecycle evidence packet template and initial backfill](../archive/2026-06/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md)
- [Evidence packet review and backfill execution](../archive/2026-06/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md)
- [Citation backfill and stewardship review](../archive/2026-06/V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md)
- [Section-level citation map](../archive/2026-06/V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md)
- [Evidence ownership, monitoring artifact, and test mapping closeout](../archive/2026-06/V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md)

## Ledger Boundary

This ledger summarizes existing decisions. It does not create new production
approval, change runtime behavior, alter recommendation logic, change fatigue
formulas, change API contracts, or authorize any new ranking, selection, or
prediction behavior.
