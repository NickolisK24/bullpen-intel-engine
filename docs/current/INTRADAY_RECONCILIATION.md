# Intraday Reconciliation — Phase 1 (Audit-Only)

Status: **Phase 1 shipped — audit/check-only, manual, non-writing.**
Related: `docs/current/SYNC_PIPELINE.md` · Workflow:
`.github/workflows/baseballos-sync.yml` (job `intraday-audit`) · Service:
`backend/services/intraday_reconcile.py` · Command:
`backend/scripts/run_intraday_reconcile.py`.

## 1. The four-mode synchronization architecture

BaseballOS coordinates authoritative baseball state through four approved
synchronization modes. All four coordinate through the **same public sync
writer advisory lock** so they can never overlap.

| Mode | Cadence | Purpose | Writes canonical data? |
|---|---|---|---|
| **daily** | morning cron + manual | full authoritative morning reconciliation: team assignments, roster statuses, transactions, recent game-log ingestion, fatigue, trusted snapshot publication | yes |
| **intraday** | **manual only (Phase 1)** | lightweight, delta-aware reconciliation *throughout the day*; Phase 1 is **audit-only** | **no (Phase 1)** |
| **postgame** | overnight cron + manual | completed-game ingestion, trailing slate repair, fatigue recalculation, trusted snapshot publication | yes |
| **backfill** | manual only | explicit historical repair for one requested slate date | yes |

`intraday` sits between the heavy `daily` and `postgame` passes. Its job is to
notice time-sensitive source changes *between* those passes without ever
becoming another full sync.

## 2. Why intraday reconciliation exists

The daily sync establishes a trusted morning baseline, and the postgame sync
repairs completed games overnight. Between them, official state can move —
players are recalled, optioned, placed on or activated from the IL, traded;
games are postponed, resumed, or go final — and BaseballOS has no lane that
notices until the next major sync. Intraday reconciliation closes that window.
Phase 1 proves the *detection* is accurate before any *write* behavior is
authorized.

## 3. The July 16, 2026 class of incident (motivating scenario)

On 2026-07-16, the Philadelphia Phillies recalled Seth Johnson after the
morning daily sync had already run. He later appeared as a reliever, but
BaseballOS continued to treat him as outside the active roster because no lane
reconciled roster state intraday; the outdated active-roster state persisted
until the next major sync.

This is a *class* of incident, not a one-off: **any** player can be recalled
(or optioned, placed on the IL, activated, traded) after the morning sync, so
BaseballOS can hold an outdated active-roster state until the next major sync.
Seth Johnson / Philadelphia is used here only as the concrete, observed
motivating scenario. This document makes **no** claim about private team or
manager intent; it describes only publicly observable roster/source state.

## 4. Phase 1 behavior (what this branch implements)

Phase 1 is deliberately narrow:

- **Manual only.** Dispatched from the Actions tab (`mode: intraday`) or run as
  a CLI command. There is **no cron** for it.
- **Audit / check only.** It reports what *would* need to change.
- **No canonical writes.** It never modifies `pitchers`, roster-status fields
  or snapshots, team assignments, transactions, `scheduled_games`, game logs,
  fatigue scores, dashboard snapshots, or dead-letter rows.
- **No snapshot publication.**
- **No derived-state recalculation** (no fatigue, no Current-Pen ERA, no
  league ERA rank, no Team Board / Comparison / Share-card / Product
  Intelligence changes).
- **No public cache warming** (no Tonight warm), **no story generation**.
- **No database migration and no new production data table.**

The audit *may*: read the production database and official MLB sources through
the existing MLB client and retry policy; acquire and release the existing
public synchronization advisory lock (read-only, see §7); emit logs; and write
a **local** JSON artifact file when `--output` is given.

## 5. The audit lanes

The audit runs three source-vs-stored comparison lanes and one derived lane:

1. **Roster and team assignment.** Official active-roster evidence for every
   MLB team (via the same acquisition helpers the daily sync uses:
   `build_team_roster_status_index` + `classify_roster_evidence`) compared with
   stored pitcher state. Detects: player now active but stored inactive; player
   now inactive but stored active; recall; option; IL placement; IL activation;
   DFA / removal from the active roster; team-assignment change; newly
   discovered active player; a stored player on the wrong team; a source player
   that cannot be safely matched to an MLB identity; and conflicting official
   team evidence. Identity is resolved **only** by MLB numeric id — never by
   name — so an unmatchable source row stays unresolved.

2. **Transactions.** Recent official transactions compared with stored
   transaction evidence, using the daily sync's exact classification order
   (non-player → unresolved identity → invalid shape → actionable-not-stored /
   stored-conflict / already-reflected), plus a flag for a stored transaction
   whose roster effect is not reflected in current roster state. No transaction
   or dead-letter row is inserted, updated, resolved, or deleted.

3. **Schedule and game finality.** The current and previous slate dates: a
   scheduled game now postponed; a postponed game now rescheduled; a game now
   in progress; a game now final but not yet represented as final in stored
   schedule evidence; a stored finality conflicting with the source; a newly
   discovered game; and doubleheader / rescheduled-game identity issues. A
   newly final game is a detected delta, not an error; box scores and game logs
   are **not** ingested.

4. **Dry-run impact plan.** A `would_refresh` projection describing which
   teams, pitcher logs, and completed game_pks a *future* write phase would
   touch, and whether it would republish / warm. It is descriptive only.

## 6. Output contract and status meanings

The audit emits one stable, versioned JSON object (`capability`,
`version`, `mode`, `check_only`, `status`, `source`, `started_at`,
`completed_at`, `product_date`, `changed`, `changed_lanes`,
`affected_team_ids`, `affected_pitcher_ids`, `affected_pitcher_mlb_ids`, the
per-lane `lanes` results, `would_refresh`, a `safety` block of guarantees, the
`source_api` call totals grouped by endpoint, and `limitations`).

`status` is one of:

| status | meaning | CLI exit |
|---|---|---|
| `success` | every requested lane fully verified | 0 |
| `partial` | at least one lane could not be fully verified this run (for example a source fetch failed); successfully checked lanes keep their findings, and the unverified lane carries an explicit limitation — a partial source failure never presents as a clean "no change" | 1 |
| `failed` | verification could not be established (all lanes unverifiable, or an internal integrity issue such as an unexpected pending ORM write) | 1 |
| `skipped` | a public sync writer was active, so the audit safely did no work (see §7) | 0 |

Detected roster moves, transactions, postponements, and newly final games are
**normal successful findings** (`status: success`, `changed: true`), not audit
failures.

## 7. Locking and overlap behavior

The intraday audit must not overlap `daily`, `postgame`, `backfill`, another
intraday audit, or any other process holding BaseballOS's public
synchronization writer lock. It uses the **existing** public sync advisory-lock
identity and mechanism (`SYNC_WRITER_LOCK_KEY`, `LOCK_SCOPE_PUBLIC` in
`services/sync_metadata.py`) — not a second, unrelated lock.

Because the audit is read-only, it uses a narrowly scoped read-only lock
context (`acquire_public_sync_read_lock`) that:

- acquires the public advisory lock **before** any source acquisition and holds
  it for the entire audit, releasing it in a `finally` (on success, partial
  failure, or unexpected exception);
- **never** creates, reclaims, updates, or otherwise mutates a `SyncRun` row —
  the advisory lock alone is the coordination point, and a healthy active
  writer is left completely untouched;
- does **not** wait or queue when the lock is unavailable. It returns an
  explicit skipped result (`status: skipped`, `reason_code:
  public_sync_writer_active`, `changed: false`, plus safety fields proving no
  work occurred) and the command exits cleanly with code 0.

## 8. Why BaseballOS is not performing an hourly full daily sync

Running the full daily sync hourly would multiply MLB API load, repeatedly
recompute derived state and republish snapshots, and risk churn and rate-limit
pressure for little benefit — most hours have no material change. Intraday
reconciliation is instead **delta-aware**: it does the minimum source reads
needed to detect time-sensitive changes and, in later phases, would apply only
*targeted* updates for exactly what changed. Phase 1 does not write at all; it
only proves the deltas are detected accurately. The mode must never become an
hourly full sync.

## 9. Required validation period before production writes are authorized

Before any write behavior (Phase 2+) is authorized, Phase 1 must run against
production sources and the production database over a representative validation
period and demonstrate that its detected deltas are accurate and complete:
its roster/transaction/finality findings must match what the subsequent daily
and postgame syncs actually reconcile, with no false "no change" during source
degradation and no spurious deltas. Only once change detection is trusted does
targeted-write authorization proceed.

## 10. Future phases (NOT implemented by this branch)

- **Phase 2** — targeted roster and transaction writes (apply only the detected
  roster-status / assignment / transaction deltas).
- **Phase 3** — targeted newly-final game ingestion (the postgame lane for
  exactly the games the audit flags as newly final).
- **Phase 4** — affected-team recomputation and trusted snapshot publication
  (recompute only affected teams' reads; publish through the existing ledger
  gate).
- **Phase 5** — automatic hourly scheduling (a cron cadence, still delta-aware,
  never a full sync).

## 11. Scope statement

**None of Phases 2–5 are implemented by this branch.** This branch is Phase 1
only: audit-only, manual, non-writing, non-publishing, non-scheduling intraday
reconciliation. It adds no production writes, no automatic scheduling, no
snapshot publication, no fatigue/story/cache work, no public UI changes, no
database migration, and no new production data table.
