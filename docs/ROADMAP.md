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

The next platform capability track is V4 Evidence and Explanation. V4 is
planning-only at this stage and is intended to explain why existing governed
states appear without ranking, selecting, predicting, recommending, or
automating a decision. V4 Phase 2 has completed architecture and contract
planning and is ready for Phase 3 implementation planning.

Recommended next milestone:

```text
V4 Phase 3 - Evidence And Explanation Implementation Plan
```

The next V4 milestone should convert the Phase 2 architecture and contract plan
into a concrete implementation plan, including target modules, tests,
certification gates, and rollout gates before any runtime implementation
begins.

## Product Tracks

| Track | Current state | Next decision |
| --- | --- | --- |
| Bullpen Intelligence | Complete production foundation | Continue reliability and evidence retention |
| Fatigue Engine | Complete deterministic workload heuristic | Preserve transparency and avoid prediction claims |
| Availability Engine V1 | Complete | Maintain threshold governance |
| Recommendation Engine V1 | Certified / production ready | Preserve candidate-only scope |
| Recommendation Engine V2 | Certified / production rollout approved | Preserve no-ranking and no-selection boundaries |
| Team Operations Bullpen Readiness | Certified with non-blocking gaps / controlled rollout approved | Observe controlled rollout before full rollout planning |
| V4 Evidence and Explanation Layer | Architecture and contract planning complete / planning only | Define implementation plan before implementation |
| Prospect Pipeline | Prototype | Keep prototype until ownership, data, runbook, and evidence gaps close |

## Near-Term Roadmap

1. V4 Phase 3 evidence and explanation implementation planning.
2. Controlled rollout monitoring artifact retention for V3 readiness.
3. Post-rollout issue triage if any governance, trust, freshness, refusal, or
   accessibility issue appears.
4. Separate full production rollout decision only if controlled rollout
   evidence supports it.
5. V4 implementation only after the Phase 3 implementation plan and later
   authorization gates are complete.

## Candidate Future Tracks

These are candidates, not commitments:

- Team Operations Bullpen Readiness full rollout planning.
- V4 Evidence and Explanation implementation after Phase 3 planning and
  separate authorization.
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

For detailed milestone history, use:

- [Changelog](CHANGELOG.md)
- [Certification ledger](governance/CERTIFICATION_LEDGER.md)
- [Operational reviews](operations/OPERATIONAL_REVIEWS.md)
- [Project state snapshot](PROJECT_STATE_2026_06.md)
