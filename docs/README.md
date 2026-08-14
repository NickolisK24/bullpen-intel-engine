# BaseballOS Documentation

This directory is organized around **six canonical living documents**. Start
with the canonical library. Everything else is supporting procedure, a durable
decision record, point-in-time evidence, an implementation record, or history.

## Start Here

[Open the BaseballOS Canonical Document Library](canonical/README.md)

| Authority | Owns |
|---|---|
| [BaseballOS Constitution](canonical/01_BASEBALLOS_CONSTITUTION.md) | Mission, category, permanent guardrails, ontology, and long-term direction. |
| [Bullpen Intelligence Standard](canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md) | Source authority, data domains, evidence, vocabulary, freshness, suppression, publication, and correction rules. |
| [Product Experience Standard](canonical/03_PRODUCT_EXPERIENCE_STANDARD.md) | Page missions, navigation, interaction hierarchy, mobile behavior, failure states, accessibility, and acceptance tests. |
| [Platform Architecture & Operations Manual](canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md) | System boundaries, persistence, sync/publication, APIs, security, deployment, monitoring, repair, and runbook governance. |
| [Editorial & Distribution Standard](canonical/06_EDITORIAL_DISTRIBUTION_STANDARD.md) | Voice, public claim structure, distribution, cadence, corrections, and measurement. |
| [Product Roadmap & Decision Ledger](canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md) | Current state, active objective, priorities, phases, risks, completion evidence, and durable decisions. |

For a repository-wide classification of documentation, including files that are
historical despite living outside `archive/`, see
[REPOSITORY_DOCUMENTATION_MAP.md](REPOSITORY_DOCUMENTATION_MAP.md).

## Current Execution Snapshot

As of August 14, 2026, with `main` at `b2f0e90`:

- **The Public Credibility Pass is complete.** UX-001 (#590), SEC-001 (#595), FE-001 (#591), UX-002 (#600), DIST-003 (#594), and VOC-001 (#638) are all closed after production verification. VOC-001 closed August 12 on trusted snapshot `398`.
- **PROD-001 (#592), CI-001 (#599), OPS-001 (#593), and OPS-002 (#620) are complete.** The permanent daily-sync work reduction that OPS-002's mitigation deliberately did not implement remains separate follow-up work.
- **DEP-001 (#601) is complete.** Backend runtime dependencies carry no known advisories, test dependencies no longer ship to production, and a standing read-only CI dependency audit refuses unreviewed production dependency risk. Three residual React Router advisories are an explicit acceptance expiring **2026-11-13**, tracked by #645. See [`current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`](current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md).
- **CI-003 (#598) is complete.** Naturally scheduled run `31794183367` (attempt 1) produced the gated, tree-exact, machine-attributed commit `2e83fa0` under `BaseballOS Automation`; the commit's tree equals the validated tree `1c9d7dc`; the Vercel deployment succeeded; and read-only verification of `https://baseballos.app/team/ATH` served trusted snapshot `411`, sync run `721`, and data through `2026-08-13` under `trusted_dashboard_publication_v1`. Issue #598 is closed as completed. The full chain — natural schedule, generated-content gate, frontend tests, production build, tree-exact staging, machine commit, push, deployment, live routed page — is proven.
- **Permanent daily-sync work reduction is the current ordered work**, preserving D-051 in full: scheduled first-attempt-only production daily execution, legacy writer authority, daily and postgame shadow, backfill off, and no game-driven write or publication authority.
- Daily and postgame game-driven ingestion remain **shadow**. Backfill is off by default. The legacy writer remains authoritative. Automated game-driven write mode and publication-authority transfer remain unapproved.
- **Authoritative manual daily execution is prohibited under D-051.** The production full-daily runner is schedule-only and first-attempt-only; manual dispatch and reruns are refused before application startup.
- **H-1 and H-5 through H-12 are closed** across PRs #650-#659 and this documentation-authority reconciliation. They changed public copy ownership, language quality, hierarchy, vocabulary and freshness convergence, and documentation authority — no baseball logic, sync behavior, or publication authority.
- The game `824487` source-revision checkpoint repair is terminally complete and its single-purpose mutation capability has been retired. It must not be reintroduced as a current operator path.

The exact current execution order and decision state live in the
[Product Roadmap & Decision Ledger](canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md).
GitHub issues remain the precise acceptance checklist for open remediation work.

## Authority Order

The authority order is defined by the
[Constitution](canonical/01_BASEBALLOS_CONSTITUTION.md), Section 15. It is
restated here for navigation:

1. Constitution
2. Bullpen Intelligence Standard
3. Product Experience Standard
4. Platform Architecture & Operations Manual
5. Editorial & Distribution Standard
6. Product Roadmap & Decision Ledger
7. Active subsystem specification or current runbook within its narrow scope
8. Decision record or implementation record
9. Point-in-time audit/report
10. Historical/archive material

The Roadmap controls **sequence**. It cannot weaken a higher product,
intelligence, experience, architecture, or editorial contract.

## Active Supporting Documentation

### Operations and setup

- [`current/SETUP.md`](current/SETUP.md) — local development, environment, tests, and deployment setup.
- [`current/SYNC_PIPELINE.md`](current/SYNC_PIPELINE.md) — current public-sync order, authority posture, trust gates, shadow/public signal separation, runtime-budget behavior, and recovery rules.
- [`current/DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md`](current/DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md) — publication-critical daily contract.
- [`current/GAME_DRIVEN_DAILY_INGESTION.md`](current/GAME_DRIVEN_DAILY_INGESTION.md) — game-driven ingestion subsystem and qualification evidence; read together with the canonical Architecture Manual because the lane is still shadow, not authoritative.
- [`current/INTRADAY_RECONCILIATION.md`](current/INTRADAY_RECONCILIATION.md) — intraday reconciliation contract and rollout state.
- [`current/SHARE_CARDS_OPERATIONS.md`](current/SHARE_CARDS_OPERATIONS.md) — internal artifact coverage and refusal monitoring.
- [`current/PROGRESSIVE_TEAM_ARTIFACT_PUBLICATION.md`](current/PROGRESSIVE_TEAM_ARTIFACT_PUBLICATION.md) — team-scoped progressive publication authority.
- [`current/SHARE_CARDS_PUBLIC_ARTIFACT_PAGE.md`](current/SHARE_CARDS_PUBLIC_ARTIFACT_PAGE.md) — public immutable share-page implementation contract.
- [`current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`](current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md) — current dependency-security boundary: runtime/test dependency separation, the standing CI audit gate, and the expiry-controlled frontend acceptance.
- [`current/CHANGELOG.md`](current/CHANGELOG.md) — major product, governance, rollout, CI, and operational milestones.

These files may explain exact procedures or implementation state. They do not
replace the canonical library.

### Decisions

`decisions/` preserves discrete durable choices and their rationale. A decision
record may explain **why** a rule exists but may not create a competing product
constitution, public vocabulary, architecture authority, or roadmap. Permanent
rules must be absorbed by the canonical document that owns them.

### Audits and incident evidence

`audits/` contains point-in-time verification, visual audits, production
investigations, and incident analysis. An audit can prove a defect or supply
acceptance evidence; it does not become a permanent operating manual merely
because it is detailed.

The August 6 daily-sync runtime investigation is retained as evidence under
`docs/audits/`. OPS-002 and the canonical Roadmap/Architecture documents own the
resulting current action and durable operating rules.

### Historical implementation records

Phase folders, reports, old governance packets, retired subsystem plans, and
prior roadmap material preserve how BaseballOS reached its current state. They
are evidence, not active direction, unless a canonical document explicitly
points to one for a narrow current purpose.

A file's location alone does not grant authority. In particular, older files
under `docs/current/` that are explicitly dated historical snapshots must not
be treated as current product state. The repository documentation map records
those exceptions.

## Documentation Rules

- Do not create another master plan, source of truth, or competing product vision.
- Update the canonical document that owns a permanent rule.
- Use a runbook for an exact current procedure; keep architecture meaning in the Architecture Manual.
- Use a subsystem specification only for genuinely multi-stage, trust-sensitive work.
- Give temporary documents an owner, purpose, and retirement condition.
- Preserve point-in-time evidence; do not rewrite an old audit to make the present look cleaner.
- Archive or clearly classify implementation records after production stabilization.
- Keep exact runtime mappings, schemas, thresholds, and route behavior in canonical code/tests; documentation explains the contract.
- When code and documentation disagree, determine which authority is stale before editing either.

## Current Documentation Review Priorities

The August 6 repository reconciliation identified the highest-risk documentation
drift categories:

1. public README vocabulary that still used the old Available / On Watch / Limited ladder;
2. setup text that still described BaseballOS as a broader analytics platform with a Prospect Pipeline;
3. sync documentation that still described game-driven daily mode as `off` and implied the legacy all-pitcher loop had already retired (this category recurred and was closed again on August 14 — see `backend/tests/test_document_authority_contract.py`, which now pins the workflow value against the document);
4. historical project-state files living under `docs/current/`;
5. operational documents that could be mistaken for broader authority after the game `824487` repair was retired;
6. current execution summaries that predated OPS-002.

This reconciliation fixes the entry points and current runbooks first. Historical
evidence is preserved rather than mass-edited to current terminology.
