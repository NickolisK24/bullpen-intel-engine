# BaseballOS Canonical Document Library

**Owner:** Nickolis Kacludis  
**Effective:** July 29, 2026  
**Status:** Canonical documentation system

BaseballOS uses six living documents. Together they define the product without forcing every decision, implementation detail, and roadmap update into one file.

No other document may call itself the BaseballOS master plan, constitution, source of truth, product vision, or canonical roadmap unless it is one of the six authorities below.

## The Six Authorities

| Order | Document | The question it owns | Normal update trigger |
|---|---|---|---|
| 1 | [BaseballOS Constitution](01_BASEBALLOS_CONSTITUTION.md) | Why does BaseballOS exist, and what must it never become? | A mission, category, permanent guardrail, ontology, or long-term strategy changes. |
| 2 | [Bullpen Intelligence Standard](02_BULLPEN_INTELLIGENCE_STANDARD.md) | What must be true before BaseballOS may publish a baseball claim? | A source authority, data domain, metric, evidence rule, vocabulary contract, freshness rule, or publication gate changes. |
| 3 | [Product Experience Standard](03_PRODUCT_EXPERIENCE_STANDARD.md) | What should a user understand and be able to do on every surface? | A page mission, navigation model, interaction contract, failure state, accessibility standard, or end-state experience changes. |
| 4 | [Platform Architecture & Operations Manual](04_PLATFORM_ARCHITECTURE_OPERATIONS.md) | How does BaseballOS work, publish safely, and recover when something fails? | A system boundary, schema, service, sync mode, API, deployment process, security boundary, or runbook changes. |
| 5 | [Product Roadmap & Decision Ledger](05_PRODUCT_ROADMAP_DECISION_LEDGER.md) | What is BaseballOS building now, next, and later, and why? | Work merges, priorities change, a phase exits, a risk changes, or a durable product decision is made. |
| 6 | [Editorial & Distribution Standard](06_EDITORIAL_DISTRIBUTION_STANDARD.md) | How does BaseballOS communicate, package, distribute, correct, and measure its intelligence? | Voice, content pillars, channel behavior, artifact presentation, cadence, outreach, or editorial measurement changes. |

## Precedence

When two documents appear to conflict, use this order:

1. Constitution
2. Bullpen Intelligence Standard
3. Product Experience Standard
4. Platform Architecture & Operations Manual
5. Editorial & Distribution Standard
6. Product Roadmap & Decision Ledger
7. Active subsystem specification
8. Work package, implementation note, or branch plan
9. Historical audit or archived roadmap

The Roadmap determines sequence. It does not authorize work that violates a higher authority.

The Architecture Manual determines technical delivery. It does not redefine the user experience or the intelligence contract.

An active subsystem specification may add implementation detail. It may not create a second vocabulary, evidence standard, page mission, or product strategy.

## Source of Truth Versus Code Authority

These documents govern intent, contracts, and operating decisions. Canonical code owners remain the executable authority for exact runtime mappings, schemas, constants, thresholds, and route behavior.

When documentation and production code disagree:

1. do not silently choose the more convenient answer;
2. identify whether the disagreement is a product decision, implementation defect, or stale document;
3. fix the correct authority;
4. record the change in the Roadmap & Decision Ledger when it affects product behavior.

## Supporting Documentation

The rest of `docs/` remains useful, but its role is narrower:

- `docs/current/` - active setup guides, operating runbooks, incident procedures, and subsystem status notes;
- `docs/decisions/` - durable decision records that preserve the reason a specific choice was made;
- `docs/audits/` - point-in-time investigations and verification evidence;
- `docs/roadmap/`, phase folders, reports, and implementation notes - historical execution records unless the canonical Roadmap explicitly points to them as active support;
- `docs/archive/` - retained historical material.

Supporting files may explain implementation. They do not override the six authorities.

## Subsystem Specification Lifecycle

A separate subsystem specification is justified only when the work has a durable domain model, several services or routes, trust-sensitive behavior, a multi-stage implementation, or continuing operational duties.

Its lifecycle is:

1. Draft for an approved subsystem.
2. Use during implementation.
3. Update while the subsystem is actively being built.
4. Close after production validation.
5. Migrate permanent rules into the relevant canonical documents.
6. Preserve the specification as a historical implementation record.

Do not create a new top-level strategy document for a feature, audit, redesign, or monthly planning pass.

## Maintenance Rules

- Every canonical document carries a version, effective date, owner, update rule, review cadence, source basis, and revision history.
- Update the smallest authority that owns the change.
- Never duplicate a definition merely to make another document feel complete; link to its canonical home.
- Historical claims remain historical. Corrections are appended or superseded, not silently rewritten.
- At least once per month during the MLB season, review the six documents for drift against production code and current product decisions.
- The Roadmap receives the most frequent edits. The Constitution should change rarely.

## Creating New Documentation

Before adding a file under `docs/`, answer:

1. Which canonical document owns the permanent rule?
2. Is this an operating runbook, decision record, audit, implementation plan, or historical artifact?
3. Does an existing file already own the same question?
4. What event retires or archives this file?

A file with no clear owner or retirement condition should not be added.
