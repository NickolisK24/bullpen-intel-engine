BASEBALLOS  /  REWORKED CANONICAL DIRECTION

# 04 BaseballOS Platform Architecture & Operations Manual

Data Platform · Read Models · Daily Compute · Reliability · Delivery

VERSION 2.0  ·  PRODUCT-SERVING ARCHITECTURE EDITION

| Field | Value |
| --- | --- |
| Document | 04 BaseballOS Platform Architecture & Operations Manual |
| Version | VERSION 2.0 |
| Status | PRODUCT-SERVING ARCHITECTURE EDITION |
| Owner | Nickolis Kacludis |
| Effective date | August 17, 2026 |
| Product | BaseballOS - MLB Bullpen Command Center |

| ARCHITECTURE RULE | Architecture exists to make the bullpen product fast, current, deep, and sustainable. Internal rigor is valuable only when it improves correctness, delivery, developer speed, or user experience. |
| --- | --- |

## Part I - System Objectives

- Serve current MLB bullpen state quickly across Tonight, Dashboard, Team Board, Matchup, and Pitcher surfaces.
- Maintain a canonical appearance and roster record from public MLB sources.
- Compute workload, role/deployment, performance, rotation-transfer, schedule, and change intelligence once and reuse it everywhere.
- Persist daily snapshots and history so the product can explain how a bullpen got here.
- Keep production operations simple enough for one founder to operate reliably.

## Part II - Product-Oriented Domain Model

| Domain | Owns |
| --- | --- |
| Games & Schedule | Game identity, finality, participants, first pitch, doubleheaders, off-days. |
| Appearances | Official pitching lines, starter/reliever identity, outs, pitches, batters, game-side team ownership. |
| Roster | Active bullpen membership, transactions, off-active context, current team authority. |
| Workload | Rolling usage, rest, multi-day patterns, accumulation, pitch spikes. |
| Deployment | Role evidence, inning/leverage usage, saves/holds, multi-inning profile, role movement. |
| Performance | Current active-group and pitcher performance windows. |
| Rotation Transfer | Starter length, bullpen innings, short-start and series burden. |
| Team Intelligence | Team State, clean options, concentration, recovery, churn, summary facts. |
| Change | Adjacent-day deltas and timeline events. |
| Publication / Read Models | Purpose-built payloads for Tonight, Dashboard, Team Board, Matchup, Pitcher, history, share. |
| Product Analytics | Search, opens, returns, follows, evidence drills, shares, notification engagement. |

## Part III - Canonical Data Flow

MLB source acquisition -> canonical game/appearance/roster records -> reusable derived domain facts -> daily team/arm snapshots -> purpose-built read models -> public surfaces.

### 1. Compute Once, Serve Many

The frontend never reconstructs bullpen intelligence from raw fields. Team State, arm reads, role labels, workload windows, performance values, change deltas, and matchup summaries are backend-owned or delivered as purpose-built read models.

### 2. Daily Snapshot Model

- One arm snapshot per active/known reliever per baseball date.
- One team snapshot per club per baseball date.
- One change set between adjacent comparable team snapshots.
- One game/matchup read model per relevant slate game.
- Method/version identity stored with derived values when semantics can change.

## Part IV - Surface APIs

| Endpoint family | Contract |
| --- | --- |
| Tonight | Dated slate, game status, per-side state, key arms, compact workload/rotation context, lead/change items. |
| Dashboard | All 30 clubs exactly once, grouped by Team State, compact movement and counts. |
| Team Board | Full team summary plus active bullpen, usage, rest, workload, deployment, performance, rotation, roster, changes, relief ledger, timeline. |
| Pitcher | Current role/read, workload windows, appearances, usage patterns, performance, pitch trends, history. |
| Matchup | Two aligned team read models plus named differences; no winner field. |
| Search | Teams, relievers, games with direct canonical routes. |
| History | Daily team/arm snapshots and event overlays. |
| Share | Immutable historical observation payloads and crawler assets. |

## Part V - Sync and Update Strategy

### 3. Incremental First

Production acquisition should prefer incremental updates over expensive full rescans. The default path is to determine what changed since the last completed authoritative cycle and fetch only the records necessary to update affected teams, games, and relievers.

### 4. Update Cadence

| Stage | Purpose |
| --- | --- |
| Morning daily | Reconcile previous completed games, current rosters/transactions, derive league state, build Tonight baseline. |
| Pregame refresh | Schedule/game status, probable starters/context, late roster moves, routed/cache refresh. |
| Postgame incremental | New final games and official pitching lines, affected team/arm snapshots, deltas, team/matchup updates. |
| Nightly history | Finalize daily snapshots, timelines, search indexes, and analytics rollups. |

### 5. Failure Scope

A failed optional domain should remove only the dependent context. Core workload/team state should remain available if its authoritative inputs are intact. A publication should fail closed only at the scope necessary to prevent a wrong baseball claim.

## Part VI - Performance

- Team Board and Tonight payloads should be preassembled/read-optimized rather than generated from many live joins in the browser.
- Cache stable current read models at the API/CDN layer with explicit version/currentness metadata.
- Load heavy historical charts and deep ledgers after the answer block.
- Use bounded query windows and indexed date/team/player keys.
- Avoid N+1 queries for 30-team Dashboard and Tonight slate rendering.

## Part VII - Reliability and Corrections

### 6. Source Authority

Stable MLB game/person identities, official finality, official pitching lines, game-side appearance ownership, and current roster authority remain canonical. Corrections change the canonical record through explicit, auditable paths and rebuild dependent snapshots.

### 7. Historical Integrity

Published historical share artifacts remain immutable. Daily team/arm state history is versioned and reproducible. Corrected daily intelligence produces replacement/superseding records rather than silently mutating a cited publication.

## Part VIII - Frontend Boundary

- Frontend formats and arranges; backend owns baseball semantics.
- No client-side Team State derivation.
- No client-side “Why” invention.
- No client-side role calculation from raw saves/holds.
- No unknown-as-zero fallback.
- No visual dependency or component framework expansion unless it materially improves the product.

## Part IX - Observability

Operational observability should answer: Is the product current? Which teams/games failed to update? Which domain caused the failure? Did Team Board/Tonight payload generation complete? Are query latency and route errors healthy? Did yesterday-to-today deltas generate for all comparable teams?

## Part X - Founder Efficiency

1. Reduce recurring source work before increasing timeouts.
2. Prefer one reusable domain service over surface-specific calculations.
3. Automate only proven repetitive operations.
4. Treat reliability work as product work when it prevents stale or missing user value.
5. Do not create infrastructure whose only benefit is architectural sophistication.
