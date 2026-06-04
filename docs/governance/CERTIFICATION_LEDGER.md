# BaseballOS Certification Ledger

This ledger summarizes certification, production, rollout, and governance state
by surface. Detailed evidence remains in the linked source records.

## Current Certification Summary

| Surface | Certification status | Rollout status | Evidence |
| --- | --- | --- | --- |
| Recommendation Engine V1 | Certified / production ready | Production-ready candidate-level surface | [V1 completion certification](../RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md) |
| Recommendation Engine V2 / Dashboard V2 bullpen-state intelligence | Certified / production ready | Production rollout approved for implemented scope | [V2 formal certification](../RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md), [V2.5 Phase 16 rollout decision](../V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md) |
| V2.5 governance hardening | Complete | Governance closeout complete | [V2.5 Phase 29 closeout](../V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md) |
| Team Operations Bullpen Readiness | Certified with non-blocking operational gaps | Controlled rollout approved; full production rollout not approved | [V3 Phase 13 certification review](../V3_PHASE_13_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_REVIEW.md), [V3 Phase 19 controlled rollout approval](../V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md) |
| Availability Explanation Integration | Certified with non-blocking observations | Internal backend only; API, frontend, dashboard, and rollout not approved | [V4 Phase 8 formal certification](../V4_PHASE_8_AVAILABILITY_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |
| Prospect Pipeline | Prototype | Not promotion-ready | [V2.5 Phase 19 prototype surface review](../V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md), [V2.5 Phase 23 evidence backfill plan](../V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md) |

## Mandatory Governance Invariants

The certified recommendation, readiness, and explanation surfaces preserve:

```text
ranking_applied === false
selection_made === false
```

The certified V4 explanation surface additionally preserves:

```text
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The certified recommendation, readiness, and explanation surfaces do not
authorize:

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
| V1 completion certification | Certified / production ready for candidate-level evaluation | [V1 completion certification](../RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md) |
| V2 formal certification | Certified / production ready for governed implemented scope | [V2 formal certification](../RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md) |
| V2 production rollout | Approved for certified Dashboard V2 implemented scope | [V2.5 Phase 16 rollout decision](../V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md) |
| V2.5 governance closeout | Governance hardening closed; remaining gaps non-blocking | [V2.5 Phase 29 closeout](../V25_PHASE_29_GOVERNANCE_HARDENING_CLOSEOUT_AND_V3_READINESS_DECISION.md) |
| V3 readiness formal certification | Certified with non-blocking operational gaps | [V3 Phase 13 certification review](../V3_PHASE_13_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_REVIEW.md) |
| V3 readiness controlled rollout | Controlled rollout approved | [V3 Phase 19 controlled rollout approval](../V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md) |
| V3 readiness full production rollout | Not approved | [V3 Phase 19 controlled rollout approval](../V3_PHASE_19_TEAM_OPERATIONS_BULLPEN_READINESS_CONTROLLED_ROLLOUT_APPROVAL.md) |
| V4 availability explanation certification | Certified with non-blocking observations for internal backend integration only | [V4 Phase 8 formal certification](../V4_PHASE_8_AVAILABILITY_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) |

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

- [Lifecycle enforcement checklist](../V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md)
- [Lifecycle review log and adoption audit](../V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md)
- [Lifecycle evidence backfill and owner assignment plan](../V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md)
- [Lifecycle evidence packet template and initial backfill](../V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md)
- [Evidence packet review and backfill execution](../V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md)
- [Citation backfill and stewardship review](../V25_PHASE_26_LIFECYCLE_EVIDENCE_CITATION_BACKFILL_AND_STEWARDSHIP_REVIEW.md)
- [Section-level citation map](../V25_PHASE_27_LIFECYCLE_EVIDENCE_SECTION_LEVEL_CITATION_MAP.md)
- [Evidence ownership, monitoring artifact, and test mapping closeout](../V25_PHASE_28_EVIDENCE_OWNERSHIP_MONITORING_ARTIFACT_AND_TEST_MAPPING_CLOSEOUT.md)

## Ledger Boundary

This ledger summarizes existing decisions. It does not create new production
approval, change runtime behavior, alter recommendation logic, change fatigue
formulas, change API contracts, or authorize any new ranking, selection, or
prediction behavior.
