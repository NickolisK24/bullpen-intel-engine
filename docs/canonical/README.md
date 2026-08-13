# BaseballOS Canonical Document Library

**Owner:** Nickolis Kacludis  
**Established:** July 29, 2026  
**Last repository-wide documentation review:** August 13, 2026  
**Status:** Canonical documentation system

BaseballOS uses six living documents. Together they define the product without
forcing every decision, implementation detail, incident, and roadmap update
into one file.

No other document may call itself the BaseballOS master plan, constitution,
source of truth, product vision, or canonical roadmap unless it is one of the
six authorities below.

## The Six Authorities

| Order | Document | The question it owns | Normal update trigger |
|---|---|---|---|
| 1 | [BaseballOS Constitution](01_BASEBALLOS_CONSTITUTION.md) | Why does BaseballOS exist, and what must it never become? | A mission, category, permanent guardrail, ontology, or long-term strategy changes. |
| 2 | [Bullpen Intelligence Standard](02_BULLPEN_INTELLIGENCE_STANDARD.md) | What must be true before BaseballOS may publish a baseball claim? | A source authority, data domain, metric, evidence rule, vocabulary contract, freshness rule, or publication gate changes. |
| 3 | [Product Experience Standard](03_PRODUCT_EXPERIENCE_STANDARD.md) | What should a user understand and be able to do on every surface? | A page mission, navigation model, interaction contract, failure state, accessibility standard, or end-state experience changes. |
| 4 | [Platform Architecture & Operations Manual](04_PLATFORM_ARCHITECTURE_OPERATIONS.md) | How does BaseballOS work, publish safely, and recover when something fails? | A system boundary, schema, service, sync mode, API, deployment process, security boundary, or operational contract changes. |
| 5 | [Editorial & Distribution Standard](06_EDITORIAL_DISTRIBUTION_STANDARD.md) | How does BaseballOS communicate, package, distribute, correct, and measure its intelligence? | Voice, content pillars, channel behavior, artifact presentation, cadence, outreach, or editorial measurement changes. |
| 6 | [Product Roadmap & Decision Ledger](05_PRODUCT_ROADMAP_DECISION_LEDGER.md) | What is BaseballOS building now, next, and later, and why? | Work merges, priorities change, a phase exits, a production incident changes sequence, a risk changes, or a durable decision is made. |

## Precedence

When two documents appear to conflict, use this order:

1. Constitution
2. Bullpen Intelligence Standard
3. Product Experience Standard
4. Platform Architecture & Operations Manual
5. Editorial & Distribution Standard
6. Product Roadmap & Decision Ledger
7. Active subsystem specification or current runbook within its narrow scope
8. Decision record / implementation record
9. Point-in-time audit or report
10. Historical/archive material

The Roadmap determines sequence. It does not authorize work that violates a
higher authority.

The Architecture Manual determines technical delivery and operating contracts.
It does not redefine the user experience or intelligence contract.

A current runbook may contain exact procedural detail. It may not create a new
source authority, public vocabulary, product promise, or publication rule.

## Source of Truth Versus Code Authority

These documents govern intent, contracts, and operating decisions. Canonical
code owners remain the executable authority for exact runtime mappings, schemas,
constants, thresholds, and route behavior.

When documentation and production code disagree:

1. do not silently choose the more convenient answer;
2. identify whether the disagreement is a product decision, implementation defect, stale document, or stale code path;
3. fix the correct authority;
4. preserve production evidence needed to explain the mismatch;
5. record the change in the Roadmap & Decision Ledger when it affects product behavior, risk, or sequence.

## August 6, 2026 Review Result

The repository-wide documentation reconciliation confirmed that the canonical
model remains correct, but several supporting entry points had drifted.

The highest-risk drift included:

- root README arm terminology that still exposed the older Available / On Watch / Limited public ladder;
- setup language that still described BaseballOS as a broader analytics platform with a Prospect Pipeline;
- sync documentation that still described game-driven daily mode as `off` even though daily/postgame are in shadow;
- sync wording that implied the legacy per-pitcher GameLog loop had retired even though it remains authoritative;
- historical June project-state material living under `docs/current/`;
- current execution summaries that predated the August 6 OPS-002 runtime-budget incident.

The review rule is **not** to rewrite historical evidence into today's language.
Entry points and active runbooks are corrected; audits and archived records keep
the language that was true when they were produced.

## Current Authority Boundaries Worth Protecting

As of the August 13 review:

- public Team State remains exactly `Fresh`, `Stretched`, `Vulnerable`;
- arm reads remain `Clean Option`, `Watch Arm`, `Limited Rest`, `Unavailable`, `Limited Read`;
- Team State is derived from the canonical current active bullpen population.

The production-mutation posture is unchanged and is **not restated here**: the
legacy writer remains authoritative, game-driven daily/postgame lanes remain
shadow, backfill is off by default, the game `824487` repair capability is
retired, and generated content reaches `main` only through the self-gating
publication job (D-053). The exact list, its evidence, and its decision history
are owned by
[`05_PRODUCT_ROADMAP_DECISION_LEDGER.md`](05_PRODUCT_ROADMAP_DECISION_LEDGER.md),
with the operating procedure in
[`../current/SYNC_PIPELINE.md`](../current/SYNC_PIPELINE.md).

### Security and reliability boundary

Production ships runtime requirements only, a standing read-only CI dependency
audit refuses unreviewed production dependency risk, and the residual frontend
React Router advisories are an expiry-controlled acceptance — **2026-11-13**,
tracked by #645. The full boundary and its standing obligations live in
[`../current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md`](../current/DEPENDENCY_SECURITY_CLOSEOUT_2026-08-13.md);
the durable rule lives in the Architecture Manual.

The canonical Roadmap owns exact current sequence and production acceptance
evidence.

## Supporting Documentation

The rest of `docs/` remains useful, but its role is narrower:

- `docs/current/` — active setup guides, operating runbooks, incident procedures, and subsystem status notes;
- `docs/decisions/` — durable decision records preserving why a focused choice was made;
- `docs/audits/` — point-in-time investigations and verification evidence;
- phase folders, reports, methodology research, governance packets, and older top-level design files — implementation/research history unless explicitly reactivated;
- `docs/archive/` — retained historical material.

See [Repository Documentation Map](../REPOSITORY_DOCUMENTATION_MAP.md) for the
repository-wide classification, including known historical files that still
live under older directory layouts.

Supporting files may explain implementation. They do not override the six
authorities.

## Subsystem Specification Lifecycle

A separate subsystem specification is justified only when work has a durable
domain model, several services or routes, trust-sensitive behavior, a
multi-stage implementation, or continuing operational duties.

Its lifecycle is:

1. Draft for an approved subsystem.
2. Use during implementation.
3. Update while the subsystem is actively being built.
4. Close after production validation.
5. Migrate permanent rules into the relevant canonical documents.
6. Preserve the specification as a historical implementation record.

Do not create a new top-level strategy document for a feature, audit, redesign,
or monthly planning pass.

## Maintenance Rules

- Every canonical document carries a version, effective date, owner, update rule, review cadence, source basis, and revision history.
- Update the smallest authority that owns the change.
- Never duplicate a definition merely to make another document feel complete; link to its canonical home.
- Historical claims remain historical. Corrections are appended or superseded, not silently rewritten.
- At least once per month during the MLB season, review the six documents and active entry points for drift against production code and current decisions.
- Review immediately after a material trust incident or authority change.
- The Roadmap receives the most frequent edits. The Constitution should change rarely.
- A document's directory or length does not grant it authority.

## Creating New Documentation

Before adding a file under `docs/`, answer:

1. Which canonical document owns the permanent rule?
2. Is this an operating runbook, decision record, audit, implementation plan, or historical artifact?
3. Does an existing file already own the same question?
4. What event retires or archives this file?
5. Will the filename/location cause a future reader to mistake point-in-time evidence for current state?

A file with no clear owner or retirement condition should not be added.
