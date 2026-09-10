# SP-05 — Roster & Transaction Authority

## 1. Objective

SP-05 gives BaseballOS durable official evidence and historical intervals for MLB pitcher roster membership. It answers who is on a club's active or 40-man roster now, who was there on a prior baseball date, and which immutable MLB observation opened or closed the interval. It also makes canonical transaction corrections append-only and gives later packages targeted, deduplicated work rather than recomputing intelligence here.

This package does not activate production polling and does not change bullpen role, workload, Team State, publication, or frontend semantics.

## 2. Existing Infrastructure Reused

| Existing component | SP-05 disposition | Reason |
|---|---|---|
| `services/roster_evidence.py` | REUSE AS-IS | Its run-scoped four-view cache remains the daily sync fetch-sharing contract. |
| `services/roster_status_sync.py` | EXTEND | Existing classification, date snapshots, correction counters, and current roster-status cache remain authoritative for compatibility. Snapshot rows gain exact active/40-man observation references. |
| `services/team_assignment_sync.py` | REUSE AS-IS / MIGRATE LATER | Current organization projection remains widely consumed. SP-05 only updates it on positive complete roster inclusion and never clears it from an incomplete response. |
| `services/transaction_ingestion.py` | EXTEND | Existing typed categories, participant qualification, exact-date roster alignment, dead letters, and correction notifications remain. Completeness and append-only canonical versions are added. |
| `services/intraday_repair.py` and `services/intraday_transaction_roster_repair.py` | DO NOT TOUCH / MIGRATE LATER | The governed manual repair path remains production-safe and preserves its exact-date evidence contract. SP-13 may converge it onto interval correction primitives. |
| SP-01 `SyncRun` | REUSE AS-IS | Roster and transaction jobs use `roster_transactions` runs and record source, mutation, scope, warning, and downstream counters. |
| SP-02 `SyncJob` | REUSE AS-IS | Existing `fetch_roster`, `fetch_transactions`, and `rebuild_team` types provide durable execution and handoff. |
| SP-03 source evidence | REUSE AS-IS | Provider/domain/request identity, immutable versions, fingerprints, completeness, failure attempts, and run/job linkage are the acquisition authority. |
| SP-04 schedule state | DO NOT TOUCH | Future priority planners may use playing-team context; SP-05 does not duplicate schedule logic. |

No parallel roster snapshot, transaction queue, or source fingerprint system was introduced.

## 3. Authority Hierarchy

1. **Current active-roster membership:** complete official MLB team roster response with `rosterType=active` for the represented date.
2. **Current 40-man membership:** complete official MLB team roster response with `rosterType=40Man` for the represented date.
3. **Transaction event:** official MLB `/transactions` typed identity/code/date/team fields from a complete bounded response.
4. **Current `Pitcher` fields:** compatibility projection. Positive complete roster inclusion may set team/active tracking fields. Absence from partial, unknown, or failed evidence never clears them. Transaction text alone never changes them.
5. **Historical membership:** current-version membership intervals and their immutable source-observation boundary references, not today's `Pitcher.team_id` and not reconstructed transaction prose.

Roster and transaction evidence answer different questions. A transaction proves an event; it does not necessarily prove the final roster after all related moves. When they disagree, complete dated roster membership owns current roster state. The transaction remains durable and triggers targeted confirmation for its `fromTeam` and `toTeam` only.

## 4. Roster Source Contract

`observe_team_roster(team_id, roster_date, roster_type)` uses the existing MLB client and records an SP-03 subject at this grain:

```text
provider = mlb_stats_api
domain = roster
endpoint = /teams/{team_id}/roster
subject = team:{team_id}:{roster_type}
request = teamId + rosterType + represented date
```

Active and 40-man views are separate subjects and observations. The retained normalized artifact contains official roster records and compact completeness proof; the fingerprint uses the order-insensitive canonical roster record collection. Repeated identical content records a fetch attempt but creates no new observation version.

The endpoint supplies player identity, roster position, and public status hints. SP-05 creates interval membership only for official pitcher or two-way roster entries. This means `active pitcher on roster`; it does not assert reliever role.

## 5. Transaction Source Contract

The established date-range subject remains authoritative and now includes the safety limit in request identity:

```text
GET /transactions
sportId=1
startDate=YYYY-MM-DD
endDate=YYYY-MM-DD
limit=1000
```

The canonical row retains typed identity, dates, from/to team, raw MLB type code, raw MLB type description, normalized category, participant qualification, IL facts, roster alignment, and specialized rehab-assignment evidence. Raw response blobs, health claims, and unrelated prose are not copied into the canonical transaction table.

For changed events, `player_transaction_versions` permanently retains `fact_json`, SHA-256 fact fingerprint, version number, predecessor, schema version, and source observation. Query-window dates are fetch provenance, not baseball-event meaning, so processing the same event in a later rolling window does not manufacture a correction version.

## 6. Roster Completeness Contract

| State | Evidence | May open membership | May close from absence | May update current fields |
|---|---|---:|---:|---:|
| `complete` | Response is an object with a roster array and every row has usable player identity | Yes | Yes | Positive inclusion only |
| `partial` | Collection exists but at least one roster row cannot be identified | No | No | No |
| `unknown` | Missing/malformed collection or unrecognized client completeness | No | No | No |
| `failed` | Source request raised | No observation; failed fetch attempt | No | No |

HTTP 200 alone is not completeness. An explicit complete empty array is valid evidence; because it is authoritative for absence, it can close existing membership for that team/type. A malformed empty value is unknown and closes nothing.

## 7. Membership Interval Model

`roster_membership_intervals` has grain:

```text
pitcher + MLB team/organization + membership_type + effective interval version
```

Fields include MLB and canonical pitcher identity, team and organization, type, start/end date, optional precise timestamps, boundary precision, authority, opening/closing source observations, optional opening/closing transactions, current-version marker, predecessor interval, correction reason, and audit timestamps.

Date boundaries are half-open for historical lookup: `start_date <= query_date < end_date`. A roster-date removal therefore means the player is not a member on the removal date. Date-only evidence remains date precision; SP-05 never invents a midnight or transaction time.

Normal observation of departure closes the existing interval and preserves it. Re-addition creates a new stint. A later correction uses `supersede_membership_interval`: the cited prior interval remains stored with `is_current_version=false`; a corrected interval points to it and emits `membership_corrected`. SP-13 owns deciding and orchestrating correction/backfill.

## 8. Membership Types

The controlled storage vocabulary is:

- `active_roster` — implemented from complete official active-roster views.
- `forty_man_roster` — implemented from complete official 40-man views.
- `organization` — representationally ready; population deferred until official assignment rules are proven.
- `minor_assignment` — representationally ready; population deferred.
- `public_inactive` — representationally ready for official public status evidence; not inferred here.
- `rehab_assignment` — representationally ready; existing certified transaction subtype remains the current evidence contract.

`bullpen member`, closer, setup, long relief, and other deployment roles are intentionally absent. Those are derived baseball semantics owned later.

## 9. Current State vs History

The three retained representations have non-competing roles:

- `RosterStatusSnapshot`: dated evidence/classification used by existing consumers and transaction alignment. It now cites both active and 40-man observations.
- `RosterMembershipInterval`: normalized historical membership and boundary provenance.
- `Pitcher`: latest compatibility projection used by existing application services.

Complete positive inclusion can create a pitcher identity and set the current team/assignment cache. SP-05 does not clear `Pitcher.team_id` merely because one team's response omitted the player; an outbound player may not yet have confirmed destination evidence. Complete membership intervals still close correctly. Existing team-assignment sync continues to own its broader current-organization reconciliation.

## 10. Transaction Normalization

Existing normalized categories remain:

`recall`, `option`, `il_placement`, `il_activation`, `roster_activation`, `roster_deactivation`, `trade`, `dfa`, `outright`, `release`, `contract_selection`, `waiver_claim`, `suspension`, `bereavement`, `paternity`, `restricted`, and `unknown`.

Typed MLB codes win. Raw code and description are retained for audit and future classifier evolution. Unknown remains explicit. Existing `ASG` handling remains conservative: generic Assigned is `unknown`; only separately certified MLB-to-affiliate pitcher rehab evidence becomes the non-material `rehab_assignment` subtype.

Free-agent signing and general minor assignment are not assigned new text heuristics in SP-05. They remain `unknown` unless a stable source code is proven. This avoids overfitting descriptions.

## 11. Transaction Correction Handling

Official transaction ID is the stable canonical key when supplied. Identical content is unchanged. A meaningful same-key source change updates the compatibility row, increments existing correction provenance, and appends V2 with V1 as predecessor. Both fact sets remain queryable. A duplicate fetched through another request window updates request provenance only.

Fallback transaction keys remain content-derived because MLB did not supply an ID. If a correction changes a key component, automatic predecessor association cannot be proven; this is an explicit SP-13 repair concern. Source observations still preserve both upstream versions.

Source disappearance or withdrawn/deleted semantics are **UNKNOWN / REQUIRES PROOF**. SP-05 does not delete a canonical transaction merely because it is absent from a later bounded window.

## 12. Organizational Depth

Active and 40-man intervals are enough for later SP-10 to distinguish active staff from the 40-man pool and compute descriptive membership churn. The schema can add proven organization, minor-assignment, public-inactive, and rehab intervals without a second history table.

SP-05 does not calculate reinforcement eligibility, option years, likely call-ups, or minor-league workload. It does not describe an active pitcher as a reliever without established role/deployment evidence.

## 13. Minor-League Boundary

Official MLB roster resources accept a team identity and roster type and MLB team records expose organization/affiliate relationships. That makes bounded affiliate roster observations plausible. This package does not claim that a complete, stable, historical player-organization assignment contract has been proven across all minor levels and seasons.

Proven now: MLB transaction rows may identify an affiliate destination, and existing team-metadata evidence can certify a narrow rehab assignment. Deferred: general affiliate-roster acquisition, historical completeness, option eligibility, and minor-league workload. These remain `UNKNOWN / REQUIRES PROOF` until source behavior is empirically certified.

## 14. Queue / Dedupe / Priority

SP-05 uses existing SP-02 jobs:

| Work | Job type | Priority | Active dedupe key |
|---|---|---:|---|
| One team/date roster reconcile | `fetch_roster` | 40 | `ROSTER_RECONCILE:{team}:{date}:contract-v1` |
| Bounded transaction range | `fetch_transactions` | 50 | `TRANSACTION_RANGE:{start}:{end}:{team-or-league}:request-v1` |
| Membership impact handoff | `rebuild_team` | 40 | `ROSTER_IMPACT:{team}:{date}:observations:{ids}` |

Lower numbers are higher priority. The transaction payload is version 1 and contains dates plus optional team scope; the roster payload is version 1 and contains team/date/trigger only. No source payload is duplicated in a job.

Terminal jobs release SP-02 active dedupe identity, so later work can run. Source-observation IDs distinguish legitimate downstream generations. A future SP-04-aware planner may raise playing-team priority; this package does not add that policy or cadence.

## 15. Source Observation Integration

Roster worker flow:

```text
claimed fetch_roster job
→ SP-01 roster_transactions run
→ active and 40Man fetch attempts/observations
→ lease revalidation
→ complete + changed only
→ interval/snapshot/current projection transaction
→ append membership mutations
→ enqueue one targeted rebuild_team handoff
→ record counters and settle through SP-02
```

Transaction worker flow:

```text
claimed fetch_transactions job
→ SP-01 roster_transactions run
→ bounded source attempt/observation
→ completeness fence
→ existing canonical ingestion + append-only versions
→ affected from/to clubs only
→ enqueue targeted roster confirmation jobs
→ settle through SP-02
```

Jobs remain distinct from runs and source attempts. Neither worker auto-executes downstream baseball intelligence.

## 16. Failure / Partial / Empty Behavior

- Roster failure persists an SP-03 failed fetch attempt before rethrowing; no observation or canonical mutation is produced. SP-02 owns retry.
- Partial/unknown roster observations are retained but no interval, snapshot, or current cache mutation occurs.
- Transaction failure preserves prior transactions, records existing domain failure/dead-letter evidence plus SP-03 failure evidence, and does not fabricate an empty observation.
- Transaction partial/unknown observations create no canonical rows. The sync window is `partial`.
- Complete zero-row transaction windows are `empty_valid`, successful, and mutation-free.
- Domain failure evidence remains separate from job retries.

## 17. Concurrency Contract

PostgreSQL serializes only the team being reconciled with `pg_advisory_xact_lock(505000000 + team_id)`. Unrelated teams proceed independently. SP-03 independently serializes source-subject version creation.

The database adds a partial unique index over `(pitcher_id, membership_type)` where the interval is open and current. This prevents duplicate or cross-team simultaneous open membership. Reconciliation locks existing candidate rows, closes prior-team membership and opens new membership in one transaction. The SP-02 partial unique active-dedupe index prevents duplicate impact jobs.

PostgreSQL tests run two simultaneous same-team reconciliations and prove one creates two membership facts, the other is unchanged, only two intervals/two mutations remain, and only one downstream job exists.

## 18. Database / Index Design

Migration `f3c7a1d9e5b2` is additive and preserves all existing rows.

New tables:

- `roster_membership_intervals`
- `roster_membership_mutations`
- `player_transaction_versions`

Extended tables:

- `roster_status_snapshots`: active and 40-man source-observation foreign keys.
- `player_transactions`: raw type description, current source-observation pointer, current fact-version number.

Indexes support current team/type membership, player/date history, opening/closing provenance, mutations by team/player/date, transaction versions by observation, and one current open player/type interval. JSON fact payloads are intentionally not indexed.

## 19. Existing Intraday Repair Relationship

The existing intraday repair remains unchanged and authoritative for its governed manual scope. It continues to acquire exact-date roster evidence for transaction participants, preserve domain dead letters, and realign current transaction facts. SP-05 does not route production repair through the new workers and does not activate the queue.

SP-13 should later wrap its correction decisions with transaction-version and interval-supersession provenance. Until then, SP-05 reconciliation is a new reusable primitive alongside, not a replacement for, the operational repair path.

## 20. Explicit Non-Goals

- No production Render/GitHub schedule or cadence changes.
- No morning 30-team orchestration.
- No probable-starter or pregame enrichment.
- No final-game reconciliation or live-game ingestion.
- No Statcast acquisition.
- No workload, availability, Team State, role, deployment, bullpen churn, or publication computation.
- No frontend/API/public wording changes.
- No generalized impact engine, correction planner, repair UI, or historical backfill.
- No speculative injury, call-up, or eligibility inference.

## 21. SP-06 / SP-09 / SP-10 / SP-13 Handoffs

**SP-06:** use `current_memberships(team, active_roster)` and dated roster provenance for pregame context. Do not infer role from membership.

**SP-09:** consume append-only `roster_membership_mutations` and the queued payload containing team, pitchers, observations, and mutation IDs. Generalized impact and job fan-out belong there.

**SP-10:** derive active composition, 40-man depth context, churn, membership concentration, and denominators from interval history; do not re-fetch history.

**SP-13:** backfill pre-SP-05 intervals, resolve fallback-key transaction corrections, prove withdrawn transaction behavior, and invoke interval supersession after comparing authoritative historical observations.

**SP-12/SP-14:** SP-12 may schedule morning league sweeps; SP-14 may activate/certify workers and retire legacy entry points only after production proof.

## 22. Acceptance Checklist

- [x] Official active and 40-man roster subjects are immutable and provenanced.
- [x] Complete, partial, unknown, failed, and empty collection behavior is explicit.
- [x] Partial/failure evidence cannot remove a player or clear current team.
- [x] Transaction range completeness is conservatively proven at a documented safety limit.
- [x] Complete empty transaction windows are successful.
- [x] Canonical transaction corrections retain predecessor fact versions.
- [x] Durable active and 40-man membership intervals exist.
- [x] Removal, re-addition, transfer, multiple stints, and historical lookup are covered.
- [x] Interval boundary observations and append-only mutation facts are queryable.
- [x] Current `Pitcher` and roster snapshot compatibility remain.
- [x] Two-team events target only from/to clubs.
- [x] Database and team-scoped concurrency fences prevent duplicate open membership.
- [x] Downstream work is durable, targeted, and deduplicated but not executed here.
- [x] Existing intraday repair remains unchanged.
- [x] No scheduler, baseball semantic, publication, frontend, or `main` changes are part of SP-05.

## Appendix A — Transaction Pagination / Completeness Proof

Accessed 2026-09-07.

1. **Official MLB Stats API OpenAPI document:** <https://docs.statsapi.mlb.com/openapi.json>. The `/api/v1/transactions` operation documents `startDate`, `endDate`, filters, and `limit`. It does not document an offset, page, cursor, continuation token, or total-result response field. This supports the request contract and the conclusion that page traversal is unavailable through the documented operation.
2. **Official bounded transaction response:** <https://statsapi.mlb.com/api/v1/transactions?sportId=1&startDate=2026-09-01&endDate=2026-09-07&limit=1000>. Experimental read-only observation returned 281 transaction records and top-level keys `copyright,transactions`.
3. **Official limit probe:** <https://statsapi.mlb.com/api/v1/transactions?sportId=1&startDate=2026-09-01&endDate=2026-09-07&limit=5>. Experimental read-only observation returned exactly 5 records, proving the parameter truncates results while the response supplies no continuation evidence.

Operational conclusion: use bounded date ranges with `limit=1000`. A structurally valid collection with fewer than 1000 rows is complete under this endpoint contract. A collection at the limit is `partial` because truncation cannot be disproven, and no canonical mutation occurs. This is conservative rather than a claim that MLB can never add pagination later.

## Appendix B — Natural Read-Only MLB Proof

Accessed 2026-09-07; no production database writes were performed.

- <https://statsapi.mlb.com/api/v1/teams/110/roster?rosterType=active&date=2026-09-07> returned a roster collection with 28 rows.
- <https://statsapi.mlb.com/api/v1/teams/110/roster?rosterType=40Man&date=2026-09-07> returned 46 rows.
- <https://statsapi.mlb.com/api/v1/teams/111/roster?rosterType=active&date=2026-09-07> returned 28 rows.
- <https://statsapi.mlb.com/api/v1/teams/111/roster?rosterType=40Man&date=2026-09-07> returned 47 rows.

These probes confirm separate active/40-man collection shapes and distinct game-independent team identity. Counts are observations from that access date, not permanent roster-size guarantees.
