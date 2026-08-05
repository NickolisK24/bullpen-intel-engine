# BaseballOS Documentation

This directory is organized around **six canonical living documents**. Start with the canonical library. Everything else is supporting implementation evidence, an operational runbook, a durable decision record, or history.

## Start Here

[Open the BaseballOS Canonical Document Library](canonical/README.md)

| Authority | Owns |
|---|---|
| [BaseballOS Constitution](canonical/01_BASEBALLOS_CONSTITUTION.md) | Mission, category, permanent guardrails, ontology, and long-term direction. |
| [Bullpen Intelligence Standard](canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md) | Source authority, data domains, evidence, vocabulary, freshness, suppression, publication, and correction rules. |
| [Product Experience Standard](canonical/03_PRODUCT_EXPERIENCE_STANDARD.md) | Page missions, navigation, interaction hierarchy, mobile behavior, failure states, accessibility, and acceptance tests. |
| [Platform Architecture & Operations Manual](canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md) | System boundaries, persistence, sync and publication, APIs, security, deployment, monitoring, repair, and runbooks. |
| [Product Roadmap & Decision Ledger](canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md) | Active objective, priorities, phases, dependencies, risks, backlog, completion log, and durable decisions. |
| [Editorial & Distribution Standard](canonical/06_EDITORIAL_DISTRIBUTION_STANDARD.md) | Voice, content pillars, public claim structure, share artifacts, platform-native publishing, cadence, corrections, and measurement. |

## Current Execution Snapshot

As of the August 4–5, 2026 nightly closeout:

- PROD-001 (#592) and CI-001 (#599) are complete.
- OPS-001 (#593) is implemented and remains open for its required scheduled observation window.
- UX-001 (#590) is merged through PR #611 and remains open for production proof of one Fresh, one Stretched, and one Vulnerable team with matching payload and rendered text.
- #591 remains the backend-owned Why-copy package.
- #594 remains the routed/static team metadata and freshness package.
- Daily and postgame game-driven ingestion remain shadow; backfill remains off; automated write and publication authority have not transferred.

The [current changelog](current/CHANGELOG.md) records the completed implementation and production-evidence state. GitHub issues remain the exact acceptance-checklist and closure evidence for open audit findings.

## Authority Order

1. Constitution
2. Bullpen Intelligence Standard
3. Product Experience Standard
4. Platform Architecture & Operations Manual
5. Editorial & Distribution Standard
6. Product Roadmap & Decision Ledger
7. Active subsystem specifications
8. Work packages and implementation notes
9. Historical audits and archived roadmaps

The Roadmap controls sequence but cannot override a higher product, intelligence, experience, or architecture contract.

## Active Supporting Documentation

### Operations and Setup

- [`current/SETUP.md`](current/SETUP.md) - local development, configuration, tests, and deployment setup.
- [`current/SYNC_PIPELINE.md`](current/SYNC_PIPELINE.md) - current public sync order, trust gates, and recovery procedure.
- [`current/INTRADAY_RECONCILIATION.md`](current/INTRADAY_RECONCILIATION.md) - intraday reconciliation contract and rollout state.
- [`current/SHARE_CARDS_OPERATIONS.md`](current/SHARE_CARDS_OPERATIONS.md) - internal artifact coverage and refusal monitoring.
- [`current/SHARE_CARDS_CUTOVER.md`](current/SHARE_CARDS_CUTOVER.md) - immutable artifact generation/read cutover record.
- [`current/PROGRESSIVE_TEAM_ARTIFACT_PUBLICATION.md`](current/PROGRESSIVE_TEAM_ARTIFACT_PUBLICATION.md) - team-scoped progressive publication authority.
- [`current/SHARE_CARDS_PUBLIC_ARTIFACT_PAGE.md`](current/SHARE_CARDS_PUBLIC_ARTIFACT_PAGE.md) - public immutable share-page implementation contract.
- [`current/CHANGELOG.md`](current/CHANGELOG.md) - major product, governance, rollout, CI, and operational milestones.

These files support current operations or document active subsystem behavior. They do not replace the canonical library.

### Decision Records

`decisions/` preserves discrete, durable choices and their rationale. A decision record may clarify a decision but may not create a competing product constitution, vocabulary, or roadmap. Permanent decisions must also be reflected in the canonical document that owns them.

### Audits, Reports, Phase Records, and Archives

- `audits/` contains point-in-time verification and incident analysis.
- `reports/`, phase folders, implementation records, and prior roadmap material preserve engineering evidence.
- `archive/` retains historical documents.

These records are intentionally preserved. They are not current authorities unless one of the six canonical documents links to a specific record as active supporting evidence.

## Documentation Rules

- Do not create another master plan or source-of-truth document.
- Update the canonical document that owns the permanent rule.
- Use a subsystem specification only for a genuinely multi-stage, trust-sensitive subsystem.
- Give every temporary document an owner, purpose, and retirement condition.
- Preserve history; replace competing authorities with redirect notes rather than erasing the record.
- Keep exact runtime mappings in canonical code and tests. Update documentation when the public contract changes.

## Superseded Entry Points

The former standalone roadmap and product-vision files now redirect to the canonical Roadmap and Product Experience Standard. Their prior content remains available in Git history.
