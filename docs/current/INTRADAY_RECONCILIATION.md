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

   **Transaction-ledger actionability is separated from public materiality
   (Observation #3).** A transaction type is classified by
   `classify_transaction_public_effect` into whether it can plausibly change
   current MLB active-bullpen membership (`active_roster_affecting`,
   `organization_or_ledger_only`, `context_dependent`, or `unknown`; unknown fails
   closed). A missing record (`actionable_not_stored` / `compound_transaction_new`)
   or a governed-fact conflict (`stored_conflict`) is **transaction-record
   actionable** — the ledger would ingest/reconcile it — but is **not**
   public-material unless the transaction type can change membership AND the roster
   lane confirms a current change for the proven pitcher. Organization/ledger-only
   records (signings, assignments — `SGN` / `SFA` / `ASG`), `effect_direction=none`
   events, and unknown types are never public-material on their own; the roster
   lane remains the sole authority for current bullpen membership, targeted
   workload, and public team-read recomputation, and a player appearing in both
   lanes is deduplicated to a single public impact.

   Only **meaningful** findings (actionable or review-required) are serialized
   into `differences`. Benign inventory (`already_reflected`,
   `non_player_transaction`, `compound_event_reflected`, `non_pitcher_transaction`,
   `transaction_detail_mismatch`, `superseded_transaction`, `current_state_aligned`)
   is counted, bounded-sampled, and reported with a suppressed count. Public team
   impact is scoped to the governed MLB clubs (`MLB_TEAM_IDS`): minor-league /
   affiliate / unknown team ids stay in the finding's evidence and in
   `non_mlb_team_ids_observed` / the `transaction_ledger` sub-plan, but never enter
   `affected_team_ids` or `recalculate_team_reads`. No transaction or dead-letter
   row is inserted, updated, resolved, or deleted. (`status_effect_unreflected`
   from contract 1.1 is retired in favour of the refined membership classes.)

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
finer-grained `version` is currently `1.4.1`. Five backward-compatible minor and
patch bumps have shipped inside capability v1: `1.0.0 → 1.1.0` (signal-quality:
benign inventory aggregated, summary buckets, active-roster-only default);
`1.1.0 → 1.2.0` (bullpen-relevance: role-gated actionability, MLB-team impact
scoping, exact-state vs public-membership separation, chronology);
`1.2.0 → 1.3.0` (transaction-ledger vs public-materiality split);
`1.3.0 → 1.4.0` (summary-contract clarification: one derivation source and one
explicit scope per aggregate count, deduplicated `public_bullpen_change_count`,
and removal of the ambiguous legacy count names); and `1.4.0 → 1.4.1`
(targeted-workload authority: the impact plan derives targeted recent-work
acquisition **exclusively** from the roster lane, so a roster-departing pitcher's
public-material transaction can no longer re-enter the targeted lists — a
behavioral bug fix with no artifact-shape change). Each bump only **adds**,
**clarifies**, or **corrects** fields, sub-plans, and classifications; none of the
fields the workflow's artifact validator checks (`capability` / `mode` /
`check_only` / `status`) change, so the validator still accepts the artifact.

Two independent actionability axes (Observation #3). Every meaningful transaction
finding exposes `transaction_record_actionable` (does the ledger need this
record?) and `public_bullpen_material` (does this event prove a current public
MLB bullpen-state change?). A missing/actionable transaction record is no longer
conflated with a current public change: `would_refresh` now carries two
sub-plans, `public_bullpen_state` (roster/current-state-authoritative — teams,
targeted workload, snapshot, warm) and `transaction_ledger` (records to ingest /
reconcile). The flat `would_refresh` fields are derived **only** from
`public_bullpen_state`; transaction-ledger-only findings never set
`affected_team_ids`, `recalculate_team_reads`, `targeted_pitcher_*`,
`publish_snapshot`, or `warm_tonight`. Top-level `material_change_detected`,
`public_bullpen_change_detected`, and `transaction_ledger_change_detected` are
independent. As of contract version **1.4.0** (Production Observation #4) every
aggregate `summary` count is derived from one source (`_derive_summary_counts`)
and has one explicit, unambiguous scope: all-lane finding tallies
(`total_meaningful_findings`, `total_actionable_findings`,
`review_required_findings`, `unresolved_findings`); the transaction-LEDGER axis
(`transaction_record_actionable_count`, `transaction_ledger_only_findings`,
`transaction_public_bullpen_material_count`); the per-lane public tallies
(`public_roster_change_count`, `schedule_public_change_count`); and the
deduplicated GLOBAL `public_bullpen_change_count` (same roster authority and
overlap rules as `build_impact_plan`, so a roster/transaction overlap for one
player counts once and ledger-only or completed-game findings never inflate it).
The earlier ambiguous names `actionable_bullpen_differences`,
`actionable_differences`, `public_bullpen_material_count`,
`public_roster_changes`, `total_differences`, and `public_membership_mismatches`
were removed (no runtime consumer depended on them). Only the governed MLB clubs
appear in `affected_team_ids` / `would_refresh.recalculate_team_reads`; affiliate
ids are evidence-only.

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
- **`summary`** carries honest, explicitly-scoped buckets: `records_checked`,
  `total_meaningful_findings` (meaningful only), `total_actionable_findings`,
  `review_required_findings`, `unresolved_findings`, the transaction-ledger axis
  (`transaction_record_actionable_count`, `transaction_ledger_only_findings`,
  `transaction_public_bullpen_material_count`), the public axis
  (`public_roster_change_count`, `schedule_public_change_count`,
  `public_bullpen_change_count`), `informational_records`,
  `benign_records_suppressed`, and `material_change_detected`. A count that is
  meaningful/actionable does **not** imply a public bullpen change — that is the
  distinct `public_bullpen_change_count`, which equals the deduplicated set of
  current public changes and is `> 0` exactly when
  `public_bullpen_change_detected` is `true`.
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
benign transactions no longer entered `differences`, the meaningful-difference
total (then `summary.total_differences`, renamed `total_meaningful_findings` in
1.4.0) fell from 360 to 9, 337 benign records were suppressed, compound events were
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

## 15. Production Observation #3 (2026-07-17) and the ledger/materiality split

The third valid production intraday run (Production Observation #3, contract
version 1.2.0) completed successfully and confirmed the bullpen-relevance
correction held: exactly 30 active-roster calls, 34 bounded and deduplicated role
lookups (under the governed maximum of 40, zero failures), proven non-pitchers
informational, unresolved roles non-material, affiliate/minor-league team ids out
of public planning, current roster evidence governing public membership,
historical option-detail mismatches benign, compound events grouped, artifact
compact, and every read-only and writer-lock safeguard passing.

One materiality defect remained, and this branch corrects it: **missing
transaction records were still treated as current public bullpen changes.** The
roster lane proved only four real current bullpen-population changes —
CJ Van Eyk (669310, Toronto, newly discovered), Yunior Tur (814305, Athletics,
newly discovered), Mason Englert (669438, Tampa Bay, activation), and Alec Gamboa
(687941, Boston, activation). But the transaction lane produced 20
`actionable_not_stored` findings — many organization-level signings/assignments
(`SGN` / `SFA` / `ASG`) with `effect_direction=none`, `normalized_category=unknown`,
and no proof of an active MLB bullpen change — and those missing rows were folded
into public planning: they entered `targeted_pitcher_mlb_ids`, added many
organizations to `affected_team_ids`, recomputed team reads for 16 MLB teams, set
`publish_snapshot=true`, and set `transactions=true` in the same plan used for
public state — despite **zero** public membership mismatches. Their pitcher roles
were correctly proven, but pitcher role alone does not prove current MLB bullpen
membership or justify public recomputation.

The correction (contract `version` 1.3.0, pinned by the tests in
`backend/tests/test_intraday_reconcile.py`, including a compact Observation #3
regression fixture) makes transaction-record actionability and public-bullpen
materiality two independent axes; adds a governed transaction-type public-effect
classification that fails closed for unknown types; makes `effect_direction=none`
never public-material on its own; keeps the roster lane the sole authority for
public current-state materiality and deduplicates players/teams that appear in
both lanes; splits `would_refresh` into a `public_bullpen_state` plan and a
`transaction_ledger` plan; derives targeted workload, public team impact,
snapshot publication, and Tonight warming from proven public findings only; and
gates role lookups by effect scope + roster reuse.

**Observation #3 is not evidence of full audit accuracy.** It validated the
infrastructure, efficiency, role governance, MLB-team scoping, chronology,
transaction-detail handling, and read-only boundary, and it revealed the
ledger/materiality conflation. A **new** Production Observation #4 is required
after this correction merges before the representative validation period of §9
can be considered met. Nothing here authorizes automatic hourly scheduling, a
write phase, or any Phase 2+ behavior; the mode remains manual, audit-only, and
non-writing.

## 16. Production Observation #4 (2026-07-17) and the summary-contract clarification

The fourth valid production intraday run (Production Observation #4, contract
version 1.3.0) completed successfully and confirmed that the deployed
transaction-ledger/public-materiality split works correctly. The run proved four
current public bullpen changes (pitchers 669310 / 669438 / 687941 / 814305 on
MLB teams 111 / 133 / 139 / 141) while 24 missing transaction records stayed in
the `transaction_ledger` plan; public targeted workload and affected teams were
restricted to the four roster-proven changes, there were zero public membership
mismatches, affiliate ids remained evidence-only, cross-lane overlap was
deduplicated, and no canonical write, snapshot build, or fatigue recompute
occurred. Writer-lock, read-only safety, active-roster efficiency, role
verification and governance, chronology/supersession, and compound-event
handling all passed.

The one defect Observation #4 surfaced was **naming, not behavior**: two
aggregate summary names remained misleading. `actionable_bullpen_differences`
counted all 28 actionable findings (four public roster changes plus 24
ledger-only records), which partially re-introduced the ledger/public conflation
at the summary layer; and `public_bullpen_material_count` sounded global while it
counted only the transaction lane's public-material findings (zero), even though
the artifact simultaneously reported four public roster changes and
`public_bullpen_change_detected = true`. A downstream consumer should not have to
know a field's provenance or inspect lane internals to read the totals.

The correction (contract `version` 1.4.0, pinned by the tests in
`backend/tests/test_intraday_reconcile.py`, including a compact Observation #4
regression fixture) does not change any reconciliation, source-acquisition,
materiality, impact-plan, or role-lookup behavior. It gives every aggregate count
one explicit scope and one derivation source (`_derive_summary_counts`): the
all-lane tallies `total_meaningful_findings` / `total_actionable_findings`; the
transaction-ledger axis `transaction_record_actionable_count` /
`transaction_ledger_only_findings` / `transaction_public_bullpen_material_count`;
the per-lane public tallies `public_roster_change_count` /
`schedule_public_change_count`; and the deduplicated GLOBAL
`public_bullpen_change_count`, which reuses `build_impact_plan`'s roster authority
and overlap rules so a roster/transaction overlap for one player counts once and
ledger-only or completed-game findings never inflate it. The invariant
`public_bullpen_change_detected == (public_bullpen_change_count > 0)` is asserted,
and a pure `_summary_contract_invariants` check guards the arithmetic
structurally (logged, never fatal). The ambiguous legacy names
(`actionable_bullpen_differences`, `actionable_differences`,
`public_bullpen_material_count`, `public_roster_changes`, `total_differences`,
`public_membership_mismatches`) were **removed** because no runtime consumer
depended on them; the two in-repo log lines that read `total_differences` now
read `total_meaningful_findings`.

**Observation #4 validates the architecture but not the final summary contract.**
A **new** Production Observation #5 is required after this correction merges
before the representative validation period of §9 can be considered met. Nothing
here authorizes automatic hourly scheduling, a write phase, or any Phase 2+
behavior; the mode remains manual, audit-only, and non-writing.

## 17. Production Observation #5 (2026-07-17) and the targeted-workload authority correction

The fifth valid production intraday run (Production Observation #5, contract
version 1.4.0) completed successfully and confirmed that the deployed summary
contract is correct. The `1.4.0` summary contract clarity passed, the canonical
count arithmetic reconciled (`total_meaningful_findings` 91, `total_actionable_findings`
47, `review_required_findings` 44, `unresolved_findings` 44,
`transaction_record_actionable_count` 35, `transaction_ledger_only_findings` 34,
`transaction_public_bullpen_material_count` 2, `public_roster_change_count` 10,
`schedule_public_change_count` 2, `public_bullpen_change_count` 10), the
transaction-ledger/public-materiality separation held (35 ledger records planned,
only 2 public-material), the public-change deduplication counted overlaps once,
and schedule finality and postponement detection worked (one newly-final game,
`game_pk` 824766). Affiliate ids stayed evidence-only, role-lookup budget
exhaustion **failed closed and was reported honestly** (budget 40, used 40,
avoided 17, failures 0, budget exceeded, 43 unresolved role findings — outside
this branch and not a correctness defect), and all read-only and writer-lock
safety guarantees passed: ORM pending writes were clean and no canonical data,
snapshot, fatigue recompute, or `SyncRun` was written.

The one defect Observation #5 surfaced was in the **impact plan**: transaction
lane affected pitcher IDs were unioned into targeted recent-work acquisition.
`build_impact_plan` documented the roster lane as the sole authority for targeted
recent-work acquisition, but its implementation computed
`targeted_pitcher_ids = roster.targeted_recent_work_pitcher_ids ∪ transactions.affected_pitcher_ids`
(and the same for the MLB-id list). **Jared Koenig** (stored pitcher id 744, MLB
player id 657649, Milwaukee / team 158) was correctly marked as leaving the active
roster: the roster lane classified him `removed_from_active_roster` with
`bullpen_population_effect = leave` and `targeted_recent_work_required = false`,
and correctly **excluded** him from `targeted_recent_work_pitcher_ids` /
`targeted_recent_work_mlb_ids`. His missing OPT transaction was correctly
`transaction_record_actionable = true` and `public_bullpen_material = true`
(effect `leave`, `roster_confirmation_status = confirmed_change`). But because the
impact plan unioned the transaction lane's public-material affected pitchers into
the targeted lists, Koenig re-entered `would_refresh.targeted_pitcher_logs`,
`would_refresh.targeted_pitcher_mlb_ids`, and both nested
`public_bullpen_state.targeted_pitcher_*` fields. A pitcher **leaving** the active
bullpen does not require a new recent-work fetch for the future public-state
refresh.

The correction (contract `version` 1.4.1, pinned by the tests in
`backend/tests/test_intraday_reconcile.py`, including a compact Observation #5
regression fixture) makes targeted recent-work acquisition **exclusively
roster-authoritative**: `targeted_pitcher_ids` and `targeted_pitcher_mlb_ids` are
derived only from `roster.targeted_recent_work_pitcher_ids` /
`roster.targeted_recent_work_mlb_ids` — the roster lane's governed
`targeted_recent_work_required` output. The transaction lane still confirms public
membership changes, contributes transaction-ledger actions, sets the
transaction-specific public-change flag, and preserves affected-player evidence;
it simply never expands the targeted workload plan. Nothing else changes — public
team scope, completed-game planning, summary counts, arithmetic, role
verification, role-lookup budgets, transaction classification, schedule
classification, and the transaction-ledger plan are all identical. For
Observation #5 the roster-authoritative targeted lists are stored pitcher ids
`[77, 242, 243, 392, 520]` and MLB ids
`[621121, 656240, 669310, 669438, 676742, 678906, 687941, 814305]`; Koenig
(744 / 657649) is absent from targeting yet remains public-material, a
transaction-ledger participant, and part of the ten public affected teams
(110, 111, 114, 117, 133, 134, 138, 139, 141, 158). **Cam Sanders** (stored 392,
MLB 676742), a roster activation whose transaction overlaps, remains targeted
exactly once, authorized by the roster lane.

**Observation #5 validates the audit's public/ledger separation but not the final
impact plan.** A **new** Production Observation #6 is required after this
correction merges before the representative multi-day validation period of §9 can
be considered started or met. Automatic intraday scheduling remains unapproved,
Phase 2 remains blocked, and the mode remains manual, audit-only, and
non-writing.
