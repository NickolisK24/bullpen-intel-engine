# BaseballOS Canonical Document Library

**Owner:** Nickolis Kacludis  
**Current product direction:** August 17, 2026  
**Status:** Canonical documentation system

BaseballOS now uses seven canonical product documents. Together they define the product, intelligence model, user experience, architecture, roadmap, distribution posture, and active frontend migration direction.

The governing product ambition is simple: **make BaseballOS the best dedicated bullpen platform in baseball — extraordinarily deep underneath, extraordinarily simple on top, relentlessly current, and useful before every game.**

## The Seven Authorities

| Order | Document | Primary responsibility |
|---|---|---|
| 1 | [BaseballOS Constitution](01_BASEBALLOS_CONSTITUTION.md) | Identity, product thesis, market ambition, permanent boundaries, and product decision tests. |
| 2 | [Bullpen Intelligence Standard](02_BULLPEN_INTELLIGENCE_STANDARD.md) | Baseball domains, derived reads, Team State, deployment, game context, What Changed, and historical intelligence. |
| 3 | [Product Experience Standard](03_PRODUCT_EXPERIENCE_STANDARD.md) | Tonight, Dashboard, Team Board, Pitcher, Matchup, history, search, personalization, mobile, and desktop experience. |
| 4 | [Platform Architecture & Operations Manual](04_PLATFORM_ARCHITECTURE_OPERATIONS.md) | Canonical data flow, domain ownership, read models, sync/update strategy, reliability, performance, and frontend boundaries. |
| 5 | [Product Roadmap & Decision Ledger](05_PRODUCT_ROADMAP_DECISION_LEDGER.md) | Product-first execution sequence, Team Board 2.0 packages, priorities, market-leadership decisions, and founder operating rule. |
| 6 | [Editorial & Distribution Standard](06_EDITORIAL_DISTRIBUTION_STANDARD.md) | Baseball-first voice, content pillars, platform-native distribution, share objects, creator workflow, and measurement. |
| 7 | [Frontend Design & Migration Specification](07_FRONTEND_DESIGN_MIGRATION_SPECIFICATION.md) | Product-first visual system, responsive density, Team Board 2.0 composition, Tonight/Dashboard/Pitcher presentation, and migration order. |

## Product Spine

The canonical product hierarchy is:

1. **Tonight** — what matters before tonight's games.
2. **League** — which bullpens deserve a closer look.
3. **Team** — the definitive bullpen page for one club.
4. **Pitcher** — one reliever's current workload, role, deployment, and trends.
5. **History** — how the bullpen or reliever got here and what changed.

The **Team Board is the product center of gravity**. It receives the next major product and UX investment after the currently in-flight Team State production proof and small semantic-contract closeout work are complete.

## Current Execution Direction

The Roadmap is the execution authority. Its August 17 product-first sequence is:

1. Close the scheduled trusted-publication / Team State calibration proof already in flight.
2. Finalize the Team State semantic/publication boundary without reopening classifier design absent a demonstrated defect.
3. Establish the shared visual foundation and shell.
4. Build Team Board 2.0 progressively.
5. Rebuild Dashboard from the same team read model.
6. Build Tonight as the daily pregame command center.
7. Upgrade Pitcher, Matchup/Search, History, and then Personalization.
8. Invest in full distribution/growth mechanics after the core product is worth returning to and sharing.

## Protected Product Boundaries

- Public Team State remains exactly `Fresh`, `Stretched`, and `Vulnerable`.
- Team State describes the shape of the canonical active bullpen rather than a worst-arm-wins rule.
- Public arm reads remain `Clean Option`, `Watch Arm`, `Limited Rest`, `Unavailable`, and `Limited Read`.
- Frontend presentation does not derive or rewrite Team State, arm reads, role movement, or What Changed semantics.
- Trust, provenance, freshness, suppression, and correction remain required infrastructure, but they do not dominate the default user experience.
- BaseballOS remains bullpen-only and descriptive rather than predictive.
- No betting, fantasy recommendations, private-health inference, manager-intent claims, quality rankings, or unexplained public composite scores.

## Documentation Rule

Update the smallest canonical document that owns the durable change. Supporting runbooks, audits, decision records, and implementation notes may provide detail but do not override these seven documents.

Historical evidence should remain historical. Do not rewrite old audits or production records merely to match new terminology; instead, update the current canonical authority and preserve the earlier record as point-in-time evidence.

## Supporting Documentation

The rest of `docs/` remains subordinate to this library:

- `docs/current/` — active runbooks, setup guides, operational procedures, and current subsystem notes.
- `docs/decisions/` — focused durable decision records.
- `docs/audits/` — point-in-time audits and verification evidence.
- `docs/archive/` — historical material.

The canonical product documents define what BaseballOS is becoming. Runtime code remains the executable authority for exact schemas, constants, routes, and production behavior until those implementations are intentionally migrated to the canonical product direction.
