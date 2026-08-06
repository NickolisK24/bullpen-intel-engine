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

As of August 6, 2026:

- **UX-001 (#590) is complete.** Backend-owned Team State is proven in corrected production. PR #617 aligned readiness derivation with the canonical current active bullpen. Production run `31097712768` published and served snapshot `360`, data through August 5, with naturally occurring `Stretched`, `Vulnerable`, and a governed fail-closed case. Fresh evidence was not manufactured when no team naturally qualified.
- **PROD-001 (#592) and CI-001 (#599) are complete.**
- **OPS-001 (#593) is implemented but its scheduled observation window remains open.** `public-sync` and `shadow-activation-health` are separate verdicts.
- **OPS-002 (#620) is the immediate production-reliability blocker.** August 6 evidence proved that daily runtime allocation can starve the publication-critical legacy GameLog writer after expensive unconditional upstream work. Three candidate snapshots were correctly withheld while snapshot `360` remained served. The system failed closed safely, but live Team Board/Compare/Tonight freshness was degraded.
- Daily and postgame game-driven ingestion remain **shadow**. Backfill is off by default. The legacy writer remains authoritative. Automated game-driven write mode and publication-authority transfer remain unapproved.
- The game `824487` source-revision checkpoint repair is terminally complete and its single-purpose mutation capability has been retired. It must not be reintroduced as a current operator path.

The exact current execution order and decision state live in the
[Product Roadmap & Decision Ledger](canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md).
GitHub issues remain the precise acceptance checklist for open remediation work.

## Authority Order

When two documents appear to conflict, use this order:

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
3. sync documentation that still described game-driven daily mode as `off` and implied the legacy all-pitcher loop had already retired;
4. historical project-state files living under `docs/current/`;
5. operational documents that could be mistaken for broader authority after the game `824487` repair was retired;
6. current execution summaries that predated OPS-002.

This reconciliation fixes the entry points and current runbooks first. Historical
evidence is preserved rather than mass-edited to current terminology.
