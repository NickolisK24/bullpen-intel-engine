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

1. **Roster and team assignment.** Official **active-roster** evidence for every
   MLB team (via the same acquisition helpers the daily sync uses:
   `build_team_roster_status_index` + `classify_roster_evidence`) compared with
   stored pitcher state. The production default fetches **active-roster evidence
   only** — one request per team (~30 calls), not the full four-roster-type sweep
   (~120) — because the approved intraday question is only whether a player's
   *active*-roster membership changed after the morning sync. It detects: player
   now active but stored inactive; player now inactive but stored active; recall
   and IL activation (inferred from the *stored* status, so still detected under
   the active-only default); team-assignment change; newly discovered active
   player (with the MLB-supplied source name preserved for evidence); a source
   player that cannot be safely matched to an MLB identity; and conflicting
   official team evidence. Where only a departure from the active roster is
   proven, a neutral `removed_from_active_roster` change type is used — an exact
   inactive destination (IL placement, option, DFA) is **never** inferred from
   active-roster absence alone. Reading the specific inactive destination directly
   from non-active roster evidence is a manual **deep-diagnostic** capability
   (`--deep-roster`, `roster_types=DEEP_ROSTER_TYPES`); the production GitHub
   Actions run uses the lightweight active-only default. Identity is resolved
   **only** by MLB numeric id — never by name — so an unmatchable source row stays
   unresolved, and a preserved source name is used for human-readable evidence
   only, never for matching.

2. **Transactions.** Recent official transactions compared with stored
   transaction evidence, **event-aware, bullpen-relevance-gated, and
   current-membership-aware**. Source components are grouped by their stable MLB
   transaction-event id (`statsapi:{id}`), so a *compound* event never
   manufactures one stored-conflict per component. Before any finding becomes
   materially actionable, its participant's **bullpen relevance** is proven from
   the MLB numeric id alone (Correction 1) — a tracked `Pitcher` row, position
   evidence on the source row, or a bounded, deduplicated, cached
   `get_player_info` (`/people/{id}`) lookup (Correction 2). Role is **never**
   inferred from transaction type, player name, destination team, or stored
   absence. Governed roles: `proven_pitcher`, `proven_two_way`,
   `proven_non_pitcher`, `unresolved`. Only proven pitchers / two-way players may
   become actionable bullpen findings; a `proven_non_pitcher` is informational
   (`non_pitcher_transaction`), and an `unresolved` role is review-required
   (`bullpen_relevance_unresolved`) and never assumed to be a pitcher.

   Exact stored-transaction alignment is separated from **public active-bullpen
   membership** (Correction 4). A stored transaction whose exact snapshot detail
   differs is not automatically material: the audit resolves the player's
   **chronology** (the latest applicable roster-affecting event; earlier ones are
   `superseded_transaction`; ambiguous ordering is `chronology_unresolved`,
   Correction 6) and consults the **roster lane's current active-membership
   authority** (Correction 7). If current official membership already matches
   stored state, the finding is benign (`transaction_detail_mismatch` or
   `current_state_aligned`) — for example an option to a minor-league affiliate
   whose pitcher is correctly outside the active bullpen. Only when current
   official membership genuinely disagrees with stored state for a proven pitcher
   is it `public_bullpen_effect_unreflected` (materially actionable). Compound
   events remain event-level: `compound_transaction_new` (gated by relevance),
   event-level `stored_conflict`, `compound_transaction_review_required`, or
   `compound_event_reflected`.

   Only **meaningful** findings (actionable or review-required) are serialized
   into `differences`. Benign inventory (`already_reflected`,
   `non_player_transaction`, `compound_event_reflected`, `non_pitcher_transaction`,
   `transaction_detail_mismatch`, `superseded_transaction`, `current_state_aligned`)
   is counted, bounded-sampled, and reported with a suppressed count. Public team
   impact is scoped to the governed MLB clubs (`MLB_TEAM_IDS`, Correction 3):
   minor-league / affiliate / unknown team ids stay in the finding's evidence and
   in `non_mlb_team_ids_observed`, but never enter `affected_team_ids` or
   `recalculate_team_reads`. No transaction or dead-letter row is inserted,
   updated, resolved, or deleted. (`status_effect_unreflected` from contract 1.1
   is retired in favour of the refined membership classes.)

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
per-lane `lanes` results, `would_refresh`, `material_change_detected`, a
`summary` block, a `safety` block of guarantees, the `source_api` call totals
grouped by endpoint, and `limitations`). The `capability` value is
`intraday_reconciliation_audit_v1` and is the pinned contract identity; the
finer-grained `version` is currently `1.2.0`. Two backward-compatible minor bumps
have shipped inside capability v1: `1.0.0 → 1.1.0` (signal-quality: benign
inventory aggregated, summary buckets, active-roster-only default) and
`1.1.0 → 1.2.0` (bullpen-relevance: role-gated actionability, MLB-team impact
scoping, exact-state vs public-membership separation, chronology). Each bump only
**adds** fields and classifications; none of the fields the workflow's artifact
validator checks (`capability` / `mode` / `check_only` / `status`) change, so the
validator still accepts the artifact. The `summary` block additionally carries
`actionable_bullpen_differences`, `role_unresolved_findings`,
`non_pitcher_transactions`, `transaction_detail_mismatches`,
`superseded_transactions`, `public_membership_mismatches`, `mlb_teams_affected`,
and `non_mlb_team_ids_observed`. Only the governed MLB clubs appear in
`affected_team_ids` / `would_refresh.recalculate_team_reads`; affiliate ids are
evidence-only.

Signal semantics the contract guarantees:

- **`changed` reflects meaningful findings only.** It is `true` when any
  actionable *or* review-required finding exists, so a genuine
  human-review-required finding is never hidden — but benign inventory
  (already-reflected / non-player / reflected compound events) never sets it.
  A lane whose only transaction activity is benign is **not** listed in
  `changed_lanes`.
- **`material_change_detected` is stricter than `changed`.** It is `true` only
  when a future authorized write/recompute would actually be required — an
  actionable finding or a newly-final game. Review-required findings are
  `changed` but **not** material, and `would_refresh.publish_snapshot` follows
  `material_change_detected`.
- **`summary`** carries honest buckets: `records_checked`, `total_differences`
  (meaningful only), `actionable_differences`, `review_required_findings`,
  `unresolved_findings`, `informational_records`, `benign_records_suppressed`,
  and `material_change_detected`.
- **Per-lane transaction inventory** lives in the transaction lane's `checked`
  counts, `informational_counts`, bounded `informational_samples`, and
  `suppressed_counts.benign_records_suppressed` — so the full benign volume is
  auditable by count without bloating `differences`.
- **Affected identity sets** (`affected_team_ids` / `affected_pitcher_ids` /
  `affected_pitcher_mlb_ids`) and the `would_refresh` plan are derived from
  **actionable** findings only; benign and review-required findings never add a
  team or pitcher to a write plan, and a transaction-only delta never warms
  Tonight.

`status` is one of:

| status | meaning | CLI exit |
|---|---|---|
| `success` | every requested lane fully verified | 0 |
| `partial` | at least one lane could not be fully verified this run (for example a source fetch failed); successfully checked lanes keep their findings, and the unverified lane carries an explicit limitation — a partial source failure never presents as a clean "no change" | 1 |
| `failed` | verification could not be established — all lanes unverifiable, an internal integrity issue such as an unexpected pending ORM write, or a production application bootstrap failure before the audit could start (`reason_code: application_bootstrap_failed`; see the operational note below) | 1 |
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

## 12. Operational note — production configuration and bootstrap failures

The intraday job runs with `APP_ENV=production`, so it initializes the
production Flask app. Production initialization requires `DATABASE_URL`,
`SECRET_KEY`, and `ADMIN_API_TOKEN` (the admin token gate keeps operational
write endpoints from being exposed to anonymous callers). The workflow maps the
existing `BASEBALLOS_ADMIN_API_TOKEN` repository secret to `ADMIN_API_TOKEN` —
the same secret the daily, postgame, backfill, and enrichment jobs already use.
Supplying the admin token does not authorize or trigger any write: the audit
stays read-only.

If required configuration is missing, the command fails during application
startup — this is a **bootstrap failure, not a partial source verification**.
The audit never acquires the lock, reads a source, or writes anything. The CLI
still emits a valid, versioned `failed` JSON artifact with
`reason_code: application_bootstrap_failed`, `product_date: null`, all lanes
marked not-checked, zero API calls, and a sanitized limitation (the raw
traceback goes only to stderr, never into the artifact); it exits `1`. The
workflow validates the artifact's contract before upload and preserves that exit
code, so a bootstrap failure surfaces loudly instead of masquerading as a normal
partial audit.

This is an operational configuration incident, not a data or trust failure: no
public baseball data was written, no snapshot was published, and the audit's
read-only boundary is unchanged. (Historical note: the first production intraday
run on 2026-07-17 hit exactly this, because the job had not yet supplied
`ADMIN_API_TOKEN`.)

## 13. Production Observation #1 (2026-07-17) and the signal-quality correction

Once `ADMIN_API_TOKEN` was supplied, the **first valid production intraday run**
executed on 2026-07-17 (Production Observation #1). It confirmed the
infrastructure is sound: the audit initialized the production app, acquired and
released the read-only advisory lock, read all official sources, wrote nothing,
and left a clean write guard. Read-only, locking, and source-coverage behavior
all passed.

Its **signal classification, however, was wrong**, and this branch corrects it.
Observation #1 exposed four defects:

1. **Benign inventory presented as change.** All 354 transaction records — 342
   `already_reflected` and 7 non-player — were serialized into
   `transactions.differences`, so the run reported `changed: true` with a
   "360 differences" total that was almost entirely benign. Transactions showed
   up as a changed lane when nothing actionable had happened.
2. **A self-contradictory transaction label.** Three records
   (Andre Granillo, Cam Sanders, Colton Gordon) carried
   `already_reflected` **and** `status_effect_unreflected: true` **and**
   `roster_snapshot_alignment: misaligned` simultaneously — contradictory
   semantics.
3. **Manufactured stored conflicts.** Five `stored_conflict` findings came from
   three **compound** transactions (ids `927651`, `926870`, `926807`) whose
   multiple player components share one MLB transaction id and were each compared,
   per component, against the single stored `PlayerTransaction` row for that id.
4. **Dropped source names.** Two newly-discovered active pitchers
   (MLB `669310` CJ Van Eyk / Toronto, `814305` Yunior Tur / Athletics) were
   reported with `player_name: null` even though the source supplied names. The
   run also made 120 roster calls (four roster types × 30 teams) for a question
   that only needed active-roster evidence.

The correction, captured in the contract `version` bump to `1.1.0` and pinned by
the tests in `backend/tests/test_intraday_reconcile.py` (including a compact
Observation #1 regression fixture), makes `differences` carry **only meaningful**
findings, gives `status_effect_unreflected` its **own** classification with
deterministic precedence, reconciles compound events **event-first** (one finding
per MLB transaction id; `compound_transaction_review_required` where per-component
equivalence cannot be proven under the one-row-per-id schema — no migration),
**preserves** source names, and defaults roster acquisition to **active-only**
(~30 calls).

**Observation #1 is not evidence of signal accuracy.** It was the run that
revealed the signal defects; it validates only the read-only/locking/coverage
boundary. A **new** production observation is required after this correction to
begin the representative validation period of §9. Nothing here authorizes hourly
scheduling, a write phase, or any Phase 2+ behavior; the mode remains manual,
audit-only, and non-writing.

## 14. Production Observation #2 (2026-07-17) and the bullpen-relevance correction

The second valid production intraday run (Production Observation #2, contract
version 1.1.0) completed successfully and confirmed the signal-quality
correction held: API calls fell from 123 to 33, roster calls from 120 to 30,
benign transactions no longer entered `differences`, `summary.total_differences`
fell from 360 to 9, 337 benign records were suppressed, compound events were
grouped correctly, source player names were preserved, and every read-only
guarantee passed.

Its **relevance and materiality**, however, were wrong, and this branch corrects
it. Observation #2 exposed three defects:

1. **Bullpen relevance not proven.** Four unstored transaction participants —
   Braydon Risley (836083), Carson Taylor (694930), Jack Brenner (836200), and
   Cole Dorland (836451) — became `actionable_not_stored` and entered
   `affected_pitcher_mlb_ids`, `targeted_pitcher_mlb_ids`, affected teams, and
   snapshot planning **without any evidence that they are pitchers**. For a
   bullpen-only product this is unsafe.
2. **MLB-team impact not scoped.** Minor-league / affiliate team ids 512, 556,
   and 568 entered `affected_team_ids`, `would_refresh.affected_team_ids`, and
   `recalculate_team_reads`, even though only the governed 30 MLB clubs may enter
   public team-level recomputation.
3. **Public-state materiality overstated.** Three historical option records
   (Andre Granillo 701552, Cam Sanders 676742, Colton Gordon 676467) were treated
   as materially actionable purely because `roster_snapshot_alignment=misaligned`,
   without proving the transaction was not superseded, that current official state
   was known, or that BaseballOS's current public active-bullpen membership was
   actually wrong. An option whose pitcher is correctly outside the active bullpen
   is already publicly reflected even if the exact minor-league affiliate is not
   retained.

The correction (contract `version` 1.2.0, pinned by the tests in
`backend/tests/test_intraday_reconcile.py`, including a compact Observation #2
regression fixture) adds: bullpen-role verification from the MLB id (bounded,
deduplicated `/people` lookups; fail-closed; only proven pitchers / two-way
players become actionable); MLB-club impact scoping (affiliate ids stay
evidence-only); separation of exact `transaction_state` alignment from
`public_bullpen_membership` alignment; chronology / supersession using the latest
applicable roster-affecting event; and a cross-lane step that uses the roster
lane's current active-membership as authority so the transaction lane never
claims a material mismatch the roster proves is already aligned.

**Observation #2 is not evidence of full audit accuracy.** It validated the
infrastructure, efficiency, compactness, compound grouping, source naming, and
read-only boundary, and it revealed the relevance/materiality defects. A **new**
Production Observation #3 is required after this correction merges before the
representative validation period of §9 can be considered met. Nothing here
authorizes automatic hourly scheduling, a write phase, or any Phase 2+ behavior;
the mode remains manual, audit-only, and non-writing.
