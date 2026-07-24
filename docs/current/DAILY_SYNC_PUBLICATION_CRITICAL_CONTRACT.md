# Daily Sync — Publication-Critical vs Best-Effort Trust Contract (SC-04B production unblock)

## Symptom (production)

The daily public sync (GitHub Actions run `30124220074`, `SyncRun` 466, candidate
dashboard snapshot 270, `product_date` 2026-07-23) finished, refreshed every public
domain, and produced a candidate snapshot for a slate the appearance-ledger audit
certified complete:

```
Publish eligible: YES
games final / included:   96 / 96
appearances reconciled:  825 / 825
errors:                    0
records_failed:          234
sync_status:         partial
```

Yet the trusted snapshot was **withheld**. The public `/share/:publicId` page and the
public dashboard kept serving the prior day's snapshot, blocking SC-04B production
verification.

## Root cause

Two independently-correct rules combined into one wrong outcome:

1. `services/sync.py::_complete_sync_phase` sets
   `final_status = STATUS_PARTIAL if records_failed else STATUS_SUCCESS`. Any
   dead-lettered record — including a purely best-effort one — makes the whole
   `SyncRun` `partial`.
2. `services/slate_coverage.py::compute_slate_coverage` forced
   `complete_enough_to_publish = False` whenever `sync_status == 'partial'`,
   **regardless** of whether the current slate's games, postgame markers, finality,
   and appearance ledger were complete.

In run 466 the 234 `records_failed` were **entirely** budget-exhausted per-pitcher
game-log *correction* attempts for off-active-roster / historical arms (`errors = 0`).
That lane runs under a runtime budget (`DAILY_SYNC_TOTAL_BUDGET_SECONDS`) and
dead-letters its unfinished tail so the final publish phase always has reserve. None
of those 234 items were required to build the current public trusted snapshot — the
appearance ledger for the current slate was independently complete (825/825). The
coarse `partial` rule could not tell "the current slate is incomplete" apart from
"a best-effort maintenance lane didn't finish," so it withheld a publishable snapshot.

## Decision (founder-approved contract)

Separate the work the daily sync performs into two classes and gate publication on the
first class only:

- **Publication-critical** — work REQUIRED to establish the current public trusted
  snapshot: current active-MLB-roster pitchers' game logs, and every non-game-log
  publication lane (team assignments, roster statuses, transactions, schedule/finality
  preflight). Its completeness gates publication.
- **Best-effort** — historical / enrichment corrections (off-active-roster, optioned,
  IL, minors, DFA arms; retroactive game-log corrections). May be deferred or
  dead-lettered without withholding the current snapshot.
- **Unknown criticality** — anything not confidently classifiable **fails closed**
  (treated as publication-critical for the gate).

A trusted snapshot may publish under an overall `partial` `SyncRun` **only when every
publication-critical requirement is complete** and the shortfall is best-effort. No
existing trust gate is weakened: finality, appearance-ledger, freshness, provenance,
and every current-slate game/marker check are unchanged and still withhold a genuine
gap.

## Implementation (smallest correct change)

### One canonical classifier + completeness result

`services/publication_criticality.py` (new) owns the single classifier and the single
fail-closed completeness result. It reuses the canonical Roster Authority
(`services/roster_authority.py::roster_status_category_for_status`) — no second roster
registry, no second slate authority:

- `criticality_for_roster_status(code)` → `publication_critical` (active MLB roster),
  `best_effort` (optioned / IL / minors / DFA / off-roster), or `unknown` (missing /
  unrecognized code → fail closed). The current active MLB roster is a safe **superset**
  of the active bullpen, so an active-bullpen arm is never misclassified as best-effort.
- `build_publication_critical_result(...)` → `{status, complete, counts…, reason_codes}`.
  `complete` is True **iff** zero publication-critical failures (game-log AND
  non-game-log), zero unresolved publication-critical work, and zero unknown-criticality
  items — and only when the classifier authority was available. Best-effort deferrals
  never block.

### Critical-first ingestion order (WS-B)

`sync_recent_logs` sorts pitchers publication-critical/unknown first, best-effort last,
before the budgeted game-log loop. Criticality is read from each pitcher's
already-synced canonical `roster_status` code **in memory (zero extra queries)** — it
must not add pre-ingestion cost that would worsen the very starvation it fixes. A budget
shortfall can therefore only defer best-effort work; publication-critical records are
processed first.

### Typed budget-exhaustion classification (WS-C)

When the game-log lane exhausts its budget, the deferred tail is classified by
criticality (critical / unknown / best-effort), counted, logged, and written into the
dead-letter payload (`publication_critical_remaining`, `unknown_criticality_remaining`,
`best_effort_remaining`, plus a bounded id list). Non-budget game-log failures and every
non-game-log lane failure are folded in as publication-critical (fail closed).

### Gate refinement (WS-D / WS-E)

`compute_slate_coverage(..., publication_critical_complete=None)` replaces the coarse
`sync_status == 'partial'` block with
`_partial_blocks = (sync_status == 'partial') and not bool(publication_critical_complete)`.
Default `None` preserves the prior conservative behavior exactly for every non-daily
caller. `services/dashboard_snapshot.py` threads `publication_critical_complete` from
`build_bullpen_dashboard_snapshot` → `store_dashboard_snapshot` →
`_payload_with_slate_coverage` → `compute_slate_coverage`; `services/sync.py`
`complete_sync_run_with_snapshot` passes the daily sync's result through.

### Publication proof (WS-F)

`services/sync_publication_proof.py::build_candidate_publication_proof` accepts
`publication_critical` and `sync_status` and attaches them to the proof so an operator
can read **why** a `partial` run was allowed to publish (every publication-critical
requirement complete; only best-effort deferred). The fail-closed serving verdict is
unchanged. `scripts/run_daily_sync.py` forwards both into the proof and the summary.

## Observability (WS-I)

- `status['publication_critical']` — the full completeness result on every daily-sync
  status dict.
- Budget-exhaustion log line now reports `publication_critical=…`, `unknown=…`,
  `best_effort=…` counts.
- Dead-letter payload carries the typed remainder counts and a bounded critical-id list.
- The publication proof carries `publication_critical` + `sync_status`.

## Budget enforcement (WS-G) — unchanged, restated

`DAILY_SYNC_TOTAL_BUDGET_SECONDS` (default 1080) with `FINAL_PHASE_RESERVE` (300) and the
game-log ingestion cap (720) still bound ingestion on a monotonic clock; the final
publish phase still runs inside its reserve. The repair changes only how a
budget-driven best-effort shortfall is *interpreted* by the publication gate, not the
budget mechanism.

## Roster-fetch dedup (WS-H) — deferred

WS-H (deduplicating roster fetches across lanes) is a performance optimization that would
recover budget headroom. It is **not required** for correctness of this contract and was
explicitly deferred with founder permission. The publication-critical gate makes the
current snapshot resilient to budget shortfall regardless of WS-H, so the optimization is
independent follow-up.

## Snapshot 270 preservation (WS-J)

Snapshot 270 is historical evidence of the incident. This change **does not mutate** it —
no `status`, `is_published`, `published_at`, or serving change. The contract applies to
the next daily sync, which builds a fresh candidate. Snapshot 270 remains exactly as the
incident left it.

## Fresh-verification procedure

1. Run the daily public sync (`scripts/run_daily_sync.py --public-only`) or wait for the
   scheduled GitHub Actions `public-sync` job.
2. Confirm the JSON summary shows `publication_critical.complete = true` and
   `publication_proof.verified = true`, and that the served snapshot id equals the
   candidate id.
3. Confirm the public dashboard / `/share/:publicId` serve the new `product_date`.
4. If a run reports `publication_critical.complete = false`, the snapshot is correctly
   withheld: inspect `publication_critical.reason_codes` and the dead-letter payload for
   the critical/unknown remainder.

## Relationship to SC-04B / SC-05

- This is the production unblock for **SC-04B** (canonical public Team State voice +
  public share page). SC-04B code merged as PR #528 (`origin/main` 74c1716); its
  production verification was blocked solely by the withheld snapshot this contract
  fixes.
- **SC-05 remains blocked** until a fresh trusted snapshot publishes under this contract
  and SC-04B is verified in production. SC-05 is not started.
