# BaseballOS Documentation

This folder holds the documentation for BaseballOS. The root
[`README.md`](../README.md) is the project front page; this folder contains the
deeper product, methodology, governance, and historical records.

Documentation is organized into a small set of purpose-driven folders so that
active, authoritative material is easy to find and superseded material is
preserved without cluttering the current view.

## Folder Guide

- **`current/`** — Active project state, roadmap, setup, and changelog. Start
  here to understand where the project is today.
- **`roadmap/`** — Canonical execution roadmaps for upcoming product phases.
- **`product/`** — Product strategy, positioning, go-to-market, monetization,
  and product/UX direction.
- **`methodology/`** — How the engines work: availability and fatigue
  classification, usage roles, roster/team source authority, sync data
  pipeline, and the current recommendation-engine architecture and contracts.
- **`governance/`** — Trust guardrails, fail-closed policy, certifications,
  audits, boundary/review records, and the certification ledger.
- **`archive/`** — Historical and superseded material organized by month
  (`archive/YYYY-MM/`): old implementation and phase plans, milestone handoffs,
  rollout and monitoring evidence, investigations, and remediations. Archive
  documents are kept for history and are **not necessarily authoritative**.

## Recommended Starting Points

- New to the project: [`current/PROJECT_STATE_2026_06.md`](current/PROJECT_STATE_2026_06.md)
  then [`current/ROADMAP.md`](current/ROADMAP.md).
- Setting up locally: [`current/SETUP.md`](current/SETUP.md).
- Understanding the intelligence model:
  [`methodology/BULLPEN_AVAILABILITY_ENGINE_V1.md`](methodology/BULLPEN_AVAILABILITY_ENGINE_V1.md).
- Governance and trust posture:
  [`governance/CERTIFICATION_LEDGER.md`](governance/CERTIFICATION_LEDGER.md).
- Story selection, user-facing language, and narrative governance:
  [`product/BASEBALLOS_STORY_RULES.md`](product/BASEBALLOS_STORY_RULES.md),
  [`product/BASEBALLOS_WRITING_RULES.md`](product/BASEBALLOS_WRITING_RULES.md),
  and
  [`governance/BASEBALLOS_NARRATIVE_GOVERNANCE.md`](governance/BASEBALLOS_NARRATIVE_GOVERNANCE.md).

## Authoritative Docs

These are the current primary references. Other documents — especially anything
under `archive/` — provide history and context but do not override these.

| Area | Document |
| --- | --- |
| Canonical project state | [`current/PROJECT_STATE_2026_06.md`](current/PROJECT_STATE_2026_06.md) |
| Roadmap | [`current/ROADMAP.md`](current/ROADMAP.md) |
| V4 daily bullpen platform roadmap | [`roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md`](roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md) |
| Setup and deployment | [`current/SETUP.md`](current/SETUP.md) |
| Changelog | [`current/CHANGELOG.md`](current/CHANGELOG.md) |
| Availability / fatigue engine | [`methodology/BULLPEN_AVAILABILITY_ENGINE_V1.md`](methodology/BULLPEN_AVAILABILITY_ENGINE_V1.md) |
| Availability threshold tuning | [`methodology/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`](methodology/AVAILABILITY_THRESHOLD_TUNING_PLAN.md) |
| Pitcher usage roles | [`methodology/PITCHER_USAGE_ROLE_SEPARATION_V1.md`](methodology/PITCHER_USAGE_ROLE_SEPARATION_V1.md) |
| Team-assignment authority | [`methodology/TEAM_ASSIGNMENT_AUTHORITY.md`](methodology/TEAM_ASSIGNMENT_AUTHORITY.md) |
| Roster status sync | [`methodology/ROSTER_STATUS_SYNC_IMPLEMENTATION.md`](methodology/ROSTER_STATUS_SYNC_IMPLEMENTATION.md) |
| Recommendation engine (V2) architecture | [`methodology/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`](methodology/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md) |
| Recommendation engine (V2) API contract | [`methodology/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`](methodology/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md) |
| Story rules | [`product/BASEBALLOS_STORY_RULES.md`](product/BASEBALLOS_STORY_RULES.md) |
| Writing rules and narrative standards | [`product/BASEBALLOS_WRITING_RULES.md`](product/BASEBALLOS_WRITING_RULES.md) |
| Narrative governance | [`governance/BASEBALLOS_NARRATIVE_GOVERNANCE.md`](governance/BASEBALLOS_NARRATIVE_GOVERNANCE.md) |
| Certification ledger | [`governance/CERTIFICATION_LEDGER.md`](governance/CERTIFICATION_LEDGER.md) |
| Governance boundaries | [`governance/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`](governance/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md) |
| Operational reviews summary | [`governance/OPERATIONAL_REVIEWS.md`](governance/OPERATIONAL_REVIEWS.md) |
| Product audit | [`product/PRODUCT_AUDIT_JUNE_2026.md`](product/PRODUCT_AUDIT_JUNE_2026.md) |

## Folder Contents

### current/

- [`PROJECT_STATE_2026_06.md`](current/PROJECT_STATE_2026_06.md)
- [`ROADMAP.md`](current/ROADMAP.md)
- [`ROADMAP_2_0_PROPOSAL.md`](current/ROADMAP_2_0_PROPOSAL.md)
- [`ROADMAP_2_0_PHASE1_IMPLEMENTATION_PLAN.md`](current/ROADMAP_2_0_PHASE1_IMPLEMENTATION_PLAN.md)
- [`SETUP.md`](current/SETUP.md)
- [`CHANGELOG.md`](current/CHANGELOG.md)

### roadmap/

- [`BaseballOS_V4_Daily_Bullpen_Platform.md`](roadmap/BaseballOS_V4_Daily_Bullpen_Platform.md)

### product/

- [`BASEBALLOS_STORY_RULES.md`](product/BASEBALLOS_STORY_RULES.md)
- [`BASEBALLOS_WRITING_RULES.md`](product/BASEBALLOS_WRITING_RULES.md)
- [`PRODUCT_AUDIT_JUNE_2026.md`](product/PRODUCT_AUDIT_JUNE_2026.md)
- [`COMPETITIVE_ANALYSIS_JUNE_2026.md`](product/COMPETITIVE_ANALYSIS_JUNE_2026.md)
- [`MONETIZATION_AND_ADOPTION.md`](product/MONETIZATION_AND_ADOPTION.md)
- [`STORYTELLING_SURFACES.md`](product/STORYTELLING_SURFACES.md)
- [`USER_HABIT_LOOP_ANALYSIS.md`](product/USER_HABIT_LOOP_ANALYSIS.md)

### methodology/

- [`BULLPEN_AVAILABILITY_ENGINE_V1.md`](methodology/BULLPEN_AVAILABILITY_ENGINE_V1.md)
- [`AVAILABILITY_THRESHOLD_TUNING_PLAN.md`](methodology/AVAILABILITY_THRESHOLD_TUNING_PLAN.md)
- [`PITCHER_USAGE_ROLE_SEPARATION_V1.md`](methodology/PITCHER_USAGE_ROLE_SEPARATION_V1.md)
- [`TEAM_ASSIGNMENT_AUTHORITY.md`](methodology/TEAM_ASSIGNMENT_AUTHORITY.md)
- [`ROSTER_STATUS_SYNC_IMPLEMENTATION.md`](methodology/ROSTER_STATUS_SYNC_IMPLEMENTATION.md)
- [`RECOMMENDATION_ENGINE_V2_STRATEGY.md`](methodology/RECOMMENDATION_ENGINE_V2_STRATEGY.md)
- [`RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`](methodology/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md)
- [`RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`](methodology/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md)
- [`RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md`](methodology/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md)

### governance/

- [`BASEBALLOS_NARRATIVE_GOVERNANCE.md`](governance/BASEBALLOS_NARRATIVE_GOVERNANCE.md)
- [`CERTIFICATION_LEDGER.md`](governance/CERTIFICATION_LEDGER.md)
- [`OPERATIONAL_REVIEWS.md`](governance/OPERATIONAL_REVIEWS.md)
- [`RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`](governance/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md)
- [`RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`](governance/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md)
- [`RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md`](governance/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md)
- [`BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md`](governance/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md)
- [`PHASE_1_AUDIT_REMEDIATION_REPORT_2026_06.md`](governance/PHASE_1_AUDIT_REMEDIATION_REPORT_2026_06.md)

### archive/

Historical and superseded material, organized by month. Current archive:
[`archive/2026-06/`](archive/2026-06/) — Recommendation Engine V1 plans and
certification, V2 implementation/phase records, V2.5 lifecycle and governance
hardening phases, V3 Team Operations readiness phases, V4 evidence/explanation
phases, V5 bullpen intelligence surface phases, operational review and
monitoring evidence, dashboard/UX remediation passes, and feature
investigations and bugfixes. These documents are retained for history and are
not necessarily authoritative.

## Documentation Boundary

This documentation preserves governance, certification, rollout, operational,
and monitoring evidence. It does not authorize backend changes, frontend
changes, API contract changes, recommendation logic changes, ranking behavior,
selection behavior, prediction behavior, or full production rollout beyond the
explicit decisions in the linked records.
