# BaseballOS Sync Pipeline — Execution Order and Trust Gates

Last updated: 2026-07-30 (Foundation 3C game-driven daily appearance lane).
Workflow: `.github/workflows/baseballos-sync.yml` · Incident background:
`docs/audits/sync-reliability-audit-2026-07-08.md` and
`docs/audits/appearance-ledger-restoration-2026-07-08.md`.

**Daily appearance ingestion:
[`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md)** — the
canonical reference for the game-driven critical lane: work planner, game
eligibility, appearance extraction, idempotent persistence, durable
checkpoint/resume, correction horizon, publication completeness proof, failure
semantics, operator repair, and the retirement status of the all-pitcher loop.

## The order, in one line

**schedule finality preflight → sync → publish/withhold → appearance ledger audit → dashboard cache verification**

The foundational rule: if we cannot prove the appearance ledger is complete,
we do not publish. The previous trusted snapshot keeps serving.

## Schedules and modes

| Trigger | When (UTC) | Mode |
|---|---|---|
| cron `0 10 * * *` | ~6 AM ET | daily |
| cron `0 2,4,6 * * *` | overnight passes | postgame |
| Run workflow → `mode: daily` / `postgame` | manual | same as above |
| Run workflow → `mode: backfill` + `backfill_date` | manual only | explicit historical replay |
| Run workflow → `mode: intraday` | manual only | audit-only intraday reconciliation (Phase 1 — no writes) |

Historical backfills are **never automatic**. The postgame job self-heals the
trailing `POSTGAME_LOOKBACK_DAYS` (default 2) slate dates as part of normal
operation; anything older requires an operator to dispatch `mode=backfill`
with a concrete `YYYY-MM-DD` slate date.

## public-sync job, step by step

1. **Sync (acquisition + derived state + snapshot build)**
   - daily: `run_daily_sync.py --days-back 7 --public-only` — team
     assignments, roster statuses, transactions, production schedule/finality
     preflight for the gameLog window, the **game-driven appearance lane**
     (Foundation 3C: newly final and corrected games, one box-score fetch per
     game, durable per-game checkpoint — see
     [`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md)), then
     the per-pitcher gameLog lane (statusless splits resolved against
     `scheduled_games`; unresolvable finality is dead-lettered, never silently
     skipped), fatigue, then the snapshot build.

     Once `GAME_DRIVEN_INGESTION_MODE=authoritative`, the game lane is the
     publication-critical path and the per-pitcher loop runs after it as
     governed best-effort repair — `best_effort_only=True` so it cannot
     withhold the snapshot, and `skip_game_pks` so it never rewrites a game the
     game lane already reconciled in the same run. Until then the mode is
     `off` and behaviour is unchanged.
   - postgame: `run_postgame_refresh.py --public-only` — production
     schedule/finality preflight for stale non-final stored slates, then sweeps
     the primary slate plus the trailing lookback dates, ingests completed-game
     boxscores, fatigue, then the snapshot build.
   - backfill: `run_postgame_refresh.py --date <backfill_date>` — exactly one
     explicitly requested slate.
2. **Snapshot publish/withhold (inside the sync process)** —
   `publish_dashboard_snapshot` enforces, in order: sync-run provenance,
   slate coverage for the newest data date, and the **appearance ledger gate**
   (`services/appearance_ledger.py`, trailing
   `APPEARANCE_LEDGER_WINDOW_DAYS` = 10 days). Any deficit — a final game with
   zero appearance rows, a game holding fewer rows than the pitching lines its
   ingest saw, or an incomplete/failed postgame marker — leaves the new
   snapshot `pending` with reason
   `dashboard_snapshot_appearance_ledger_incomplete`; readers keep receiving
   the previous published snapshot.
3. **Tonight refresh** (daily/postgame modes) — schedule ±10 days re-ingest
   and Tonight cache warm.
4. **Appearance ledger audit (workflow gate)** —
   `appearance_ledger_audit.py --days 10 --deep` re-proves publish
   eligibility from the database and prints the verdict:
   - exit 0 → `::notice` **Publish eligible: YES** — run continues.
   - exit 1 → `::error` **Publish eligible: NO** — the workflow **fails
     loudly**. The report (uploaded as the `appearance-ledger-audit-<run id>`
     artifact) names missing game_pks, dates with holes, and — via `--deep` —
     the affected players and their latest-appearance mismatches. Remediate
     with `mode=backfill` on the flagged slate date.
   - exit 2 / timeout → the audit itself could not run; eligibility is
     UNPROVEN and the workflow fails.
5. **Dashboard snapshot cache verification** — confirms the public dashboard
   endpoint serves a published cache (`served_from=cache`,
   `is_published=true`, `data_through` present).

Downstream jobs (`internal-enrichment`, `static-team-story-preview`) run only
after `public-sync` succeeds, so a failed ledger verdict also stops enrichment
and static page publication from advancing on unproven data.

Shadow **activation health** is no longer part of this job. It is evaluated in
the separate `shadow-activation-health` job — see
[OPS-001](#ops-001--publication-success-and-observer-health-are-separate-jobs)
below — so a shadow-only defect can no longer make `public-sync` red or skip
the downstream jobs.

## OPS-001 — publication success and observer health are separate jobs

### The former coupling

`public-sync` used to end with the game-driven shadow activation validator and
its health gate. That gate exits non-zero when shadow parity fails, when
evidence is missing, when the validator cannot run, or when an artifact is
unsafe — and because it lived inside `public-sync`, any of those turned the
**publication** job red.

A red `public-sync` therefore meant two entirely different things:

1. trusted public synchronization or one of its proofs failed; or
2. publication succeeded completely and an experimental observer failed.

`internal-enrichment` and `static-team-story-preview` both depend on
`public-sync`, so the second case skipped them too — even though the sync,
snapshot publication, appearance-ledger proof, and dashboard cache verification
they actually depend on had all succeeded. A shadow defect was withholding
enrichment and static page publication from data that was fine.

### The boundary

| job | question it answers |
|---|---|
| `public-sync` | Did trusted public synchronization and every publication-critical proof succeed? |
| `shadow-activation-health` | Did the game-driven shadow cycle pass its activation-health contract? |

`public-sync` keeps every publication-critical responsibility: the daily and
postgame runners, the 14:00 UTC morning slate refresh, both Tonight refreshes,
explicit backfill, the appearance-ledger audit and its artifact, and dashboard
cache verification. None of them is `continue-on-error`. No shadow verdict can
exit non-zero inside it.

`shadow-activation-health` runs `needs: public-sync` under an `always()`
condition covering **only** the daily and postgame cycles — never the 14:00 UTC
morning schedule, never backfill, never intraday. It runs even when
`public-sync` failed, because a public failure after the runner wrote its
summary still leaves real evidence worth validating and preserving.

That job holds **no** production credential: no `DATABASE_URL`, `SECRET_KEY`,
`ADMIN_API_TOKEN`, `BASEBALLOS_ADMIN_API_TOKEN`, or `BASEBALLOS_SYNC_URL`, and
no `secrets.` reference at all. It invokes no production command, performs no
baseball-data write, publishes nothing, and never sets
`GAME_DRIVEN_INGESTION_MODE` — it validates retained evidence rather than
running the lane.

### The handoff artifact

Jobs do not share a filesystem, so the cycle summary is transported explicitly
as `game-driven-shadow-handoff-<run id>`, retained 7 days.

The staging rule is the safety property: **nothing is uploaded from the
directory the runner wrote to.** The raw summary is scanned first and copied
into an empty staging directory only if it passes, so a bug in the scanner
produces an empty handoff rather than a leaked production artifact.

The handoff carries the applicable `daily-sync-summary.json` or
`postgame-sync-summary.json` plus `handoff-metadata.json`:

```
schema_version  run_id  repository_sha  cycle_kind  runner_exit_code
expected_summary_filename  summary_present  preupload_scan_safe  handoff_status
```

`handoff_status` is one of `ready`, `summary_missing`, `artifact_unsafe`,
`invalid_metadata`, `preparation_error`. Metadata is written on every failure
path — a handoff that says nothing and one that says "the summary was missing"
would otherwise be indistinguishable, and only one is diagnosable. It carries
no credential, URL, exception text, raw payload, or environment dump.

Both handoff steps are `continue-on-error` **transport only**. A failed handoff
cannot turn a green publication red; it becomes UNPROVEN activation health in
the observer job instead.

### Artifact safety

One scanner (`backend/scripts/scan_forbidden_artifact_content.py`) and one
pattern list govern both the pre-handoff scan and the final artifact scan. They
were previously two shell greps with two copies of the same list — a list that
can drift silently, since the second copy learns about a new secret shape only
if someone remembers it exists.

The scanner reports a filename and a category, never the matched content: the
tool that catches a leak must not re-leak it. An unreadable file is unsafe, not
skipped. Unsafe files are quarantined and never uploaded.

### The final gate

The final step of `shadow-activation-health` passes only when all ten hold:
handoff downloaded, metadata present and valid, status `ready`, pre-upload scan
safe, expected summary present, cycle kind daily or postgame, runner exit code a
real integer, validator exit 0, final scan safe, and final upload succeeded.

Verdict vocabulary is exactly three values:

| verdict | meaning |
|---|---|
| `PASS` | every condition held |
| `FAILED` | the validator ran and reported a real activation failure |
| `UNPROVEN` | evidence was missing, unsafe, or unreadable |

**UNPROVEN is never a skip, a warning, or a pass.** Absent evidence is the state
most easily mistaken for success, so it is named and it fails. The failure
message restates that automated write mode and authoritative mode both remain
prohibited, that publication authority is unchanged, and that the run's
publication-critical result is unaffected.

### Outcome matrix

| case | `public-sync` | `shadow-activation-health` | `internal-enrichment` | `static-team-story-preview` |
|---|---|---|---|---|
| A — both healthy | success | success | eligible | eligible |
| B — public ok, shadow failed | **success** | failure | **still eligible** | **still eligible** |
| C — public failed | failure | may still run to preserve evidence | skipped | skipped |
| D — governed withholding | non-success with its explicit ledger/publication reason | independently evaluated when evidence exists | skipped | skipped |
| E — shadow evidence missing/unsafe | decided only by publication-critical work | failure / UNPROVEN | based only on `public-sync` | based only on `public-sync` |

In Case B the overall workflow may still show red, because the observer job is
honestly red. That is intentional. What changed is that the `public-sync` job
itself stays green and the publication-dependent jobs are not skipped.

### What did not change

The appearance-ledger audit and dashboard cache verification remain
publication-critical and fail closed, with their commands, retries, exit-code
semantics, and artifacts untouched. Schedules, manual modes, permissions,
concurrency, timeouts, production commands, source values, and secrets are
unchanged. Daily and postgame remain `shadow`, backfill remains `off`, and
automated write and authoritative modes remain unapproved.

### Still to prove

The shadow-failure dependency behaviour is proven by deterministic CI tests, not
by breaking production to obtain a screenshot. The normal path needs roughly a
week of scheduled observation — one daily run, at least two postgame runs, and
the next applicable enrichment and static preview runs — before the operational
red-signal quality is considered fully proven.

## Foundation 3C — rollout closed

**The Foundation 3C bootstrap is complete and closed at 109 completed / 0
unresolved, with 946 appearance rows reconciled** and publication completeness
satisfied for the governed window.

It was independently verified in production by a final read-only Stage E replay
of all 109 games: 946 rows unchanged, 323 decimal-only differences safely
ignored, zero mutations on every target, and zero database drift.

**Every Foundation 3C rollout workflow is retired.** R1 through R6 were removed
at Stage E1; the Stage E verification workflow was removed at Stage E2. None can
be dispatched, and no renamed, disabled, or archived copy remains under
`.github/workflows`. Git history and the archived closeout record are the
historical record:
`docs/archive/2026-07/FOUNDATION_3C_BOOTSTRAP_CLOSEOUT.md`.

The permanent architecture the rollout built remains in production service — the
planner, reconciliation and identity authorities, canonical integer-outs
semantics, contract-4 fingerprinting, exclusive scope, per-game transactional
checkpoints, and fail-closed publication completeness. What was retired is the
temporary machinery that performed a one-time backfill, not the machinery that
runs.

### Normal synchronization is unchanged

Ordinary daily and postgame sync behaviour was not altered by the rollout's
closure. No schedule, cadence, publication path, or mode changed.

### Automation remains off

`GAME_DRIVEN_INGESTION_MODE` remains **off** and authoritative mode remains
**unapproved**. The bootstrap was completed by explicit manual dispatch;
completing it granted no activation authority.

**The next planned step is automated game-driven ingestion shadow.** It requires
a separate reviewed pull request and a period of production observation before
any further mode change is considered. **No authoritative cutover decision has
been made.**

`backend/scripts/profile_daily_ingestion_readonly.py` is retained as activation
operations support for observing that shadow behave. It has no workflow and is
run deliberately.

### The postgame cycle now has an integration point

Shadow activation was attempted and **halted at its baseline gate**: the
game-driven lane had an integration point in `run_daily_sync` only. The postgame
refresh — the cycle that ingests completed games overnight, and therefore the
source of most of the lane's candidates — had none. Wiring `shadow` into the
workflow in that state would have produced a postgame artifact describing a lane
that never ran, which is worse than no evidence.

That integration point now exists, in `services/sync.py::run_postgame_refresh`:

* **one** game-driven service call per postgame cycle, the same call the daily
  sync makes; no second ingestion command and no second comparator;
* placed **after** the legacy postgame sweep, which commits per game, so the
  projection reads the rows the current path just wrote instead of front-running
  them;
* `write` and `authoritative` are **refused** on this cycle, before any MLB
  request and before any write, because the postgame sweep has no
  `skip_game_pks` equivalent and therefore no way to prevent two writers from
  reaching the same canonical rows;
* bounded by `POSTGAME_REFRESH_INGESTION_BUDGET_SECONDS` (default 600s) so the
  lane can never consume the 20-minute postgame command timeout;
* a lane failure is contained: the postgame sync status, publication authority,
  markers, and runner exit code are unaffected.

One consequence is worth stating plainly: the workflow's **explicit backfill**
step runs `run_postgame_refresh.py --date`, the same function, so it now shares
the postgame integration point. That is inert while the lane is `off`, and
writing modes are refused on that cycle in any case — but a future activation
must set `GAME_DRIVEN_INGESTION_MODE: 'off'` explicitly on the backfill step
rather than assume it inherits the default.

### Automated shadow is now active on the two production cycles

`GAME_DRIVEN_INGESTION_MODE: 'shadow'` is set on the daily and postgame runner
steps in `.github/workflows/baseballos-sync.yml`, and on **no other step**. The
explicit backfill step sets `'off'` — mandatory, because backfill invokes the
same postgame runner and would not inherit the default.

Schedules, manual modes, permissions, concurrency, command timeouts, publication
gates, the appearance-ledger audit, and dashboard verification are all unchanged.
There is still exactly one game-driven service call site, reached once per
eligible cycle; no second ingestion command exists.

**The current sync and publication path remains authoritative.** Shadow writes
nothing, changes no work item or checkpoint, creates no game-driven dead letter,
and never touches `publication_critical`, which is computed from the game lane
only in authoritative mode.

**The two cycles prove different things**, because they observe different
moments:

* **daily** projects *before* the legacy pitcher writer, so projected inserts
  and updates are normal. After that writer finishes, a read-only realization
  proof checks whether it actually stored the projected canonical target state.
  Projected actions are never reported as shadow database writes.
* **postgame** projects *after* the existing completed-game writer, so a healthy
  cycle projects nothing at all. Any nonzero projection means the postgame
  writer left canonical work behind, and the cycle fails activation health.

Activation validation runs **after** the established production gates, under
`always()`. Its exit code is captured rather than allowed to end the job, the
artifacts are scanned for credentials and quarantined if they match, the summary
is appended, the artifacts upload, and only then does the final health gate run.
A shadow defect can fail the Actions run but can never preempt or withhold
production data the current authority would publish.

Artifacts are retained for 30 days as `game-driven-shadow-<run-id>`. The sync
summary comes from the runner's own `--output`, written atomically with sorted
keys — never parsed out of a mixed log stream.

**Rollback is a focused change back to `'off'` on those two steps.** No database
cleanup is needed, because shadow performs no writes.

Automated **write** mode and **authoritative** mode both remain **unapproved**,
and each requires its own separate reviewed pull request. Production observation
begins with the first scheduled cycle after merge.

### Postgame shadow is temporarily off

The first automated postgame shadow cycle failed activation health on **scope**.
The production path was unaffected: the postgame sync returned `success`, the
runner exited `0`, publication was verified with snapshot `324`, and shadow
performed zero writes on every counter. That is the isolation contract working
exactly as designed — the activation gate failed and production did not.

The lane planned 112 games and completed 98 before exhausting its 150-second
allocation, leaving 14 remaining. It was reading the planner's rolling
seven-day correction horizon instead of the games that postgame cycle actually
governs.

`GAME_DRIVEN_INGESTION_MODE` on the postgame runner step is now **`'off'`**.
Daily remains `'shadow'`; backfill remains `'off'`. No schedule, cadence,
manual mode, permission, concurrency group, command timeout, publication gate,
ledger audit, or dashboard verification changed.

While postgame is off, the activation validator, credential scan, summary,
artifact upload, and health gate run for **daily cycles only** — validating an
intentionally disabled lane would manufacture an activation failure at 02:00,
04:00, and 06:00 every night. Daily activation artifacts are unaffected.

The repair in place for reactivation: the postgame lane now takes **exclusive
scope** over its own cycle's fully-written completed games, resolved after the
writer from state the cycle already holds — no MLB request, no second planning
pass, every excluded game carrying a named reason. Non-unchanged projected rows
are now identified by game, pitcher, canonical field names, classification,
source revision, and digests, with no values.

**Neither the budget cap nor the lane share was raised**: a larger budget would
have hidden the scope defect rather than fixed it.

### Both cycles are observing again

Postgame shadow is reactivated on that exact-cycle scope. `daily` and `postgame`
runner steps are both `'shadow'`; backfill remains `'off'`. Activation
validation, credential scanning, job summary, artifact upload, and the final
health gate cover both cycles again, still after the established production
gates and still under `always()`.

Postgame receives only the games its own refresh cycle governs and its writer
finished — the seven-day correction horizon does not fan out into it, and daily
retains that observation. The lane still runs after the postgame writer, still
refuses writing modes on that cycle, and a clean cycle still requires zero
projected mutations.

Any nonzero projection now fails activation **and** must be attributable: the
validator refuses a projection it cannot explain, requiring one safe diagnostic
per non-unchanged row and rejecting any that carries raw values.

Rollback is unchanged — set those step environments back to `'off'`, no database
cleanup required. **Postgame observation restarts from this reactivation**, and
automated write and authoritative modes both remain unapproved.

### Shadow found a real writer-parity defect

The daily cycle at snapshot `326` succeeded and published normally — sync
`success`, runner exit `0`, publication verified, 97/97 games, zero shadow
writes — while the activation gate correctly FAILED on one divergent row.

The finding: a governed optional statistic is compared **only when the source
carries its key with a non-null value**, so a field one endpoint omits is never
corrected by the lane reading that endpoint. Combined with the postgame writer
never revisiting an already-complete game, a field can become permanently
uncorrectable while every lane reports no difference.

**No writer was changed at the time.** Authority for the affected field was
unproven without the live source payloads, so a read-only audit tool was
delivered instead and every plan now names the fields its source could not
evaluate. That audit has since been run — see the next section.

### The affected field was `balls`, and the box score owns it (D-038)

The production audit returned: box score `19/26/45` (19 + 26 = 45, coherent),
player game-log split with **no `balls` key at all**, stored row `20/26/45`
(20 + 26 = 46, incoherent) already carrying
`last_stat_correction_source: daily_game_log`.

The split never contradicted the box score; it had nothing to say. The stored
value was **uncorrectable, not disputed** — the daily lane is the only lane that
revisits an appearance inside the correction horizon, and it reads the split.

The daily lane now consults a declared field-authority map
(`services/gamelog_source_authority.py`): the split stays primary, and for an
**explicitly approved** field it omits, the completed-game box score may supply
it — validated (`balls + strikes == numberOfPitches`), never derived. The
approved set is exactly `balls`.

The enriched source flows through the same values builder, the same planner, and
the same writer as every other field: no second comparator, no second writer, no
direct assignment. A correction the fallback enabled records
`completed_game_boxscore_fallback` rather than crediting the lane's own source,
and every run reports the fallback counters whether or not anything was
eligible.

Shadow modes, the daily budget, and the mode-off rollback are unchanged, and no
production correction was executed as part of the repair. Impact across the
horizon is enumerated first, read-only, by
`scripts/plan_boxscore_balls_fallback_impact.py`.

Canonical reference:
[`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md).

### Pitcher identity is not written by completed games (D-009)

The FIRST production R1 and R2 passed on **GameLog reconciliation only**. The
R2 report simultaneously carried 942 pitcher-identity actions — 940 metadata
updates and 2 reactivations across 423 pitchers — attached to rows whose GameLog
action was `unchanged`, none of which appeared in the manifest or the
fingerprint. Both gates were re-run after D-009 merged and passed on the
complete mutation contract, with those differences reported as 1 and 57
suppressed current-state differences respectively.

The completed-game path no longer writes `Pitcher` rows. An existing row is the
identity anchor and is never modified: not reactivated, not reassigned, not
renamed, not restatused. Historical/current differences are reported as
suppressed evidence and refused. A missing row may be created minimally,
claiming no current team, no active status, and no official roster status.

This affects the **normal postgame refresh** as well as the game-driven lane —
both call the same resolution path. A pitcher first seen in a completed game is
now created inactive and unassigned, and roster synchronization claims them when
it next runs. Roster and team assignment authority stays entirely with the
official roster sources.

R1 and R2 now require zero mutations across every database target — GameLog,
pitcher identity, and appearance-team authority — before the rollout proceeds.

Canonical reference:
[`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md).

## Shadow observation backlog is not publication authority (D-044)

A read-only production audit of current state found **105** expected final
games, **42** with completed game-driven work items, and **63** counted as
unresolved final games — every one of the 63 classified
`completed_but_work_item_absent_because_lane_is_shadow_only`, with **zero** true
baseball deficits among them. All 63 had official-final evidence, final stored
schedule authority, and stored appearance rows. Their only defect was the
absence of a durable `GameIngestionWorkItem`, which the game-driven lane does
not create because it runs in `shadow`.

`services.game_ingestion_completeness` counted every planned critical game
without such a work item as unresolved, and
`services.sync._publication_critical_from_game_lane` folded that number into
`publication_critical_unresolved`. That is a publication-scope defect: **shadow
OBSERVATION incompleteness represented as PUBLICATION-BLOCKING
incompleteness.**

The completeness proof now produces one canonical per-game classification
(`classify_game_ingestion_scope`) and projects it into two named views:

- **observation** — what the lane has and has not persisted for its own staged
  rollout;
- **publication_gate** — what may withhold the public snapshot under the lane's
  CURRENT authority mode.

The invariant is `observation backlog != publication blocker` unless
game-driven publication authority has been explicitly activated.

| Lane mode | `authority_effect` | Work-item evidence blocks? |
|---|---|---|
| `shadow` | `observational_only` | no |
| `write` | `non_authoritative_write` | no |
| `authoritative` | `authoritative` | **yes** |
| `off` / unknown | `unavailable` | gate is never `complete` |

Evidence about BASEBALL rather than about the lane's own bookkeeping blocks in
**every** mode: canonical finality conflicts, missing required schedule
authority, an expected-versus-reconciled appearance-row shortfall, and a
material correction conflict. The canonical finality, appearance-ledger,
freshness, provenance, roster, and serving-selection gates are untouched.

The effective lane mode is passed explicitly into completeness construction by
callers that already know it, so a status report cannot describe a different
authority from the one that produced the evidence. A completeness result
arriving without the new schema degrades to the strict legacy reading, so a
malformed or missing proof can only over-withhold.

**The 63 games remain observable.** They are not erased, repaired, backfilled,
or reclassified as complete; `unresolved_final_games` still carries the
observation count for telemetry, and the gate names the games it withheld via
`observation_only_game_count`. Authority is not transferred, no mode changed,
and no work item was created or mutated.

Canonical reference:
[`DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md`](DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md).

## Postgame publication incident audit (D-043)

### The cycle that failed while its parts succeeded

Scheduled run **30873422601** (branch `main`, head
`9f9f640799af973f0a39cdafb1db83fba473b10c`, cycle `postgame`, slate
**2026-08-03**) exited 1. Every component inside it reported success.

The game-driven shadow lane was clean: 35 games planned, 35 fetched, 35
completed, 0 failed; 295 rows expected and 295 unchanged; zero projected
inserts, updates, blocked rows, canonical-outs corrections, statistical
corrections, identity mutations, appearance-team mutations, dead letters, and
baseball rows written; writes disabled; publication non-authoritative; exact
execution scope; no budget stop; 13.794s elapsed against a 150.0s allocation.
Shadow status: `complete`.

Legacy postgame ingestion also completed its baseball work: status `success`,
35 completed games found, 30 already processed, 5 newly processed (823431,
823520, 823757, 824160, 824647), 0 skipped, 0 failed, 40 new GameLog rows, 0
corrected, 10 completed-game contexts upserted, 10 progressive team
publications attempted and generated with 0 failures, intelligence snapshot
`ok`.

What failed was publication.

### The separation this audit preserves

| stage | outcome |
| :--- | :--- |
| game-driven shadow execution | **PASS** |
| legacy postgame baseball ingestion | **completed successfully** |
| appearance-ledger publication qualification | **FAILED** |
| dashboard publication qualification | **FAILED** |
| complete postgame activation cycle | **FAILED** |

This is not a game-driven reconciliation failure, and the audit is built so it
cannot be mislabelled as one. A perfect shadow reconciliation result does not
prove the publication system is correct, and a publication failure does not
invalidate the reconciliation engine.

### What the evidence said

The schedule finality preflight rechecked eight games for 2026-08-03 and mapped
822867, 824324, and 825095 to `other` while 823431, 823520, 823757, 824160, and
824647 mapped to `final`.

The appearance-ledger audit over 2026-07-25 .. 2026-08-03 expected 133 completed
games and represented 132, with 1110 expected and 1110 stored appearances, 9
latest-appearance mismatches across 9 players, missing game_pk **822867**, a
hole on 2026-08-03 at 5 of 6, and publish eligible **no** for
`final_games_without_appearance_rows`.

Candidate snapshot **344** stayed `pending`, unpublished, `published_at` null,
data through 2026-08-03, availability reference 2026-08-04, sync run **596**.
Snapshot **343** (data through 2026-08-02) kept serving. Publication proof
reported `candidate_snapshot_not_ready`, `candidate_snapshot_not_published`,
`candidate_snapshot_published_at_missing`,
`dashboard_snapshot_slate_coverage_incomplete`, and
`candidate_not_selected_for_serving`.

Game-ingestion completeness reported horizon 7, 102 expected final games, 42
completed, **60 unresolved**, 377 critical appearance rows expected and 377
reconciled, zero finality conflicts, zero missing schedule authority, zero
terminal failures, publication not complete, reason `unresolved_final_games`.

### The mechanism the audit is built to test

The unresolved-game membership comes from
`game_ingestion_completeness.unresolved_final_game_membership`, the same
function the published count is `len()` of. Every planned critical game is a
different and larger set — `corrected_final` re-checks are complete at their
last known revision — so classifying the planned total would inflate the
answer. A reconstruction that does not reconcile with the authority leaves
Question 7 unanswered rather than quietly answering about the wrong games.

> **Since D-044**, that membership is the **observation** view and is no longer
> the set of games that can withhold publication. The audit reads the
> publication-blocker projection alongside it and reports both, and it draws
> `publication_gate_scope_defect` from the **blocker** membership only. A game
> that is observationally unresolved but never reaches the gate is backlog, not
> a scope defect — otherwise the audit would keep proving a defect after the
> gate that caused it had been corrected. Historical incident-time conclusions
> and immutable incident facts are unchanged.

`services.appearance_ledger` counts a game as an expected completed game when
**any** stored `scheduled_games` row carries `status_state = final` inside the
trailing window. `services.game_ingestion_planner` plans a game only when
**every** stored row for that game agrees on `final`, and `other` is where the
finality authority places cancelled, live/in-progress,
abstract-final-without-final-status, and unknown status alike.

Those are different tests, so a game can be inside ledger membership and
outside planning scope at the same instant — a deficit no lane can close, and a
correct, permanent withholding.

**Whether game 822867 matches that mechanism is what the audit proves or
refutes against production evidence.** Nothing in this package asserts it, and
nothing here claims 822867 is final.

### Four evidence sources, never blended

1. `incident_artifact` — immutable facts from run 30873422601;
2. `current_database` — live production state at audit time;
3. `official_mlb_source` — the canonical MLB client's current answer;
4. `derived_inference` — conclusions from comparing the first three.

Every recorded fact carries its source. A current-state observation is never
presented as incident evidence, and an inference is never presented as an
observation. The 60-game membership is explicitly a **current reconstruction**,
because the retained artifacts carry the count and not the list.

### Eight questions, answered individually

Official status of 822867; its stored schedule state; why the preflight
produced `other`; why the ledger counted it completed; its exact stored
baseball state across every relevant table; what individually explains each of
the nine player mismatches; how each unresolved final game classifies; and why
snapshot 344 stayed pending while 343 kept serving.

One unanswered question makes the whole audit **UNPROVEN**. No question is ever
answered by the absence of a failure, and none is answered by recording that it
could not be concluded.

Questions 6, 7 and 8 carry explicit positive completion predicates, and the
artifact reports which conditions were unmet.

* **Q6** needs all nine players attributed exactly once, artifact ids matching
  the incident ids, zero unproven classifications, positive evidence behind
  every one of them, and — when the game is final — a box score that was
  actually observed and whose pitching lines actually extracted. An unreadable
  box score is not "no pitchers appeared"; it is not knowing who did.
* **Q7** needs canonical membership that reconciles with no missing or extra
  members, every member classified exactly once, zero unproven games, the
  window evidence observed, official evidence behind every member whose
  category rests on it, and no unrecovered required failure.
* **Q8** asks five things, so having the incident and current blocks is not
  having the answers. Eight subconditions must hold, two of which require the
  sole-blocker result and the sixty-game contribution to be **boolean** rather
  than `unproven`.

For this incident that makes **UNPROVEN the expected production outcome**: the
retained artifacts carry the unresolved count without its membership, so the
exact blocker set cannot be established. That is the honest result, and it is
preferable to a completed one claiming every required question was answered.

### Evidence addressed by exact run id and exact name

| artifact | id | retention | required | on absence |
| :--- | ---: | ---: | :--- | :--- |
| `game-driven-shadow-30873422601` | 8878694840 | 30d | yes | UNPROVEN |
| `appearance-ledger-audit-30873422601` | 8878687942 | 90d | yes | UNPROVEN |
| `game-driven-shadow-handoff-30873422601` | 8878688244 | 7d | no | reported |

Known digests are treated as expectations to VERIFY, never as facts to assume.
A digest GitHub no longer exposes is UNVERIFIED and does not fail; a digest that
is present and different is **FAILED**. Filenames are never trusted alone: run
id, head SHA, cycle kind, slate date, runner exit code, and the disputed game id
are read from inside the documents.

### Read-only, proven three ways

The acquire-only public sync advisory lock; a PostgreSQL
`SET TRANSACTION READ ONLY` with a bounded `WHERE 1 = 0` write probe that must
be **refused**; and before/after **scoped** content fingerprints over full
governed row content and timestamps.

Six scopes: exact game 822867; slate 2026-08-03; ledger window 2026-07-25 ..
2026-08-03; snapshots 343 and 344; sync run 596; and the unresolved-game set.
Any changed scope is FAILED; an uncomputable required fingerprint is UNPROVEN.

### Incident snapshot facts are not current snapshot facts

Production has since recovered and serves a newer snapshot. That says nothing
about whether withholding snapshot 344 during the incident was correct, so the
incident verdict is derived from the **retained publication proof** and never
from today's serving selection. Incident and current facts are reported as
separate blocks. `candidate_still_pending` means the status is exactly
`pending`; a failed or superseded snapshot is not called pending.

`disputed_game_is_sole_blocker` demands positive evidence that the blocker set
is exactly `{822867}`. Because the retained artifacts carry the unresolved
COUNT and not its membership, the honest answer for this incident is
**unproven** — not "yes, because the ledger named one game". Whether the
60-game signal reached the snapshot gate is likewise unproven unless incident
gate evidence names it.

### Stored schedule rows agree on more than a status

Fourteen governed identity and finality fields are checked independently —
exact team-row pair, unique team rows, reciprocal team and home/away identity,
dates, status state and code, game type and number, doubleheader state,
resumed-from/to linkage, and source — under one
`full_row_governance_agreement` verdict. Two rows can agree a game is final
while disagreeing about which teams played it, so `status_state` alone was far
too narrow.

Full agreement requires **all three** of: the matrix was evaluated, the rows
are an exact two-team reciprocal pair, and every governed check is exactly
`True`. Deriving it from "no check returned `False`" would let a lone row or
three unique rows report full agreement, because an unevaluable check returns
`None` rather than `False` — and `None` is the absence of a reading, not
agreement. Zero rows, one row, more than two rows, and duplicate team rows each
classify explicitly. Timestamps stay excluded: rows written microseconds apart
are a write-ordering artefact, not a baseball identity conflict.

Correction provenance is **columnar** in this schema, not a table of its own —
it lives on `game_logs`, `team_game_pitching_splits`,
`game_play_by_play_events`, and `game_ingestion_work_items` — so full-row
digests of those tables already cover it.

### The upstream source is bounded, and every call is bought once

At most 8 schedule calls, 10 exact-game calls, 10 box-score calls, and 20 total.
Every call goes through a single gateway that reserves budget BEFORE it dials
and records success, failure and latency after, so what the artifact reports
and what actually went over the wire are the same number by construction.

The whole completeness horizon is fetched with **one** governed range call, not
one call per date. Fetching per date would need nine calls against an allowance
of eight and would refuse the last one on every single run. The disputed game
is normally already inside that response, so answering Question 1 usually costs
nothing extra; an exact-game call is spent only when the game is genuinely
absent from the window. The box score is requested **once**, and the safe
pitcher-id set is projected from that same response — player attribution
consumes what was already paid for rather than fetching again.

Budget semantics distinguish three different facts. Spending an allowance
exactly is a completed observation and is not a defect. A **required** call the
budget refused leaves evidence missing. So does a required call that was
reserved, dialled and **failed** — the budget cannot see that, because it only
knows the reservation succeeded, so the gateway carries required
attempted/succeeded/failed and optional-failed separately.

Each call names the evidence it is bought to obtain, and any recovery must
state **which** of that evidence a fallback actually restored. The exact-game
fallback for game 822867 recovers that game's official status and nothing else,
so a failed window call leaves every other game in the window unobserved and
the audit UNPROVEN. A fallback cannot launder a gap it did not fill.

### Twelve primary classifications

`schedule_finality_mapping_drift`,
`appearance_ledger_completion_authority_defect`,
`stored_schedule_row_conflict`, `exact_game_ingestion_gap`,
`appearance_ledger_query_defect`, `publication_gate_scope_defect`,
`snapshot_state_transition_defect`,
`reschedule_or_suspension_identity_defect`, `multiple_contributing_defects`,
`incident_condition_no_longer_reproducible`, `no_platform_defect_proven`,
`unproven`.

Every classification carries positive supporting evidence AND explicit
counter-evidence, a confidence of HIGH/MEDIUM/LOW, and whether the condition
still persists. None is ever chosen from the absence of another failure.

### Results

| result | exit |
| :--- | ---: |
| `COMPLETE_ROOT_CAUSE_IDENTIFIED` | 0 |
| `COMPLETE_NO_PLATFORM_DEFECT_PROVEN` | 0 |
| `COMPLETE_INCIDENT_NOT_REPRODUCIBLE` | 0 |
| `FAILED` | 1 |
| `UNPROVEN` | 2 |

**`FAILED` is reserved for a violation of the audit's OWN safety contract** —
production content changed, the probe accepted, prohibited artifact material, or
an unauthorized invocation. A platform defect the audit *discovers* is a
successful audit and exits 0.

### Recommended next-package categories

`exact_game_finality_repair_review`, `appearance_ledger_authority_fix`,
`schedule_row_consistency_fix`, `exact_game_ingestion_repair_review`,
`publication_gate_scope_fix`, `snapshot_transition_fix`,
`reschedule_identity_fix`, `no_mutation_required`,
`additional_evidence_required`.

Exactly one is emitted, and it is informational only. It authorizes no
implementation, dispatch, or production execution.

### What this does not authorize

> This audit is read-only. It does not authorize backfill, repair,
> schedule-status mutation, appearance-row creation, marker reset, snapshot
> publication, automated writes, authoritative mode, or any future production
> mutation.

Nothing here reruns run 30873422601, reruns the failed postgame sync, repairs
game 822867, publishes or modifies snapshot 344 or 343, resets a marker, creates
a work item, or widens the MLB source authority. No migration was added; the
Alembic head remains `c7f1b408d93a`. Daily and postgame remain `shadow`,
backfill remains off, the legacy writer remains production-authoritative, and
automated write and authoritative modes remain unapproved.

The global dead-letter backlog remains governed at **1,389** unless separately
and authoritatively re-derived. This audit does not re-derive it and never
reports it as zero; what it does report is that it created zero dead letters.

## First qualification refusal, and the candidate audit (D-042)

### What run 30862655470 proved

The first production dispatch of the manual no-op write qualification targeted
game 824488 and returned **FAILED** with exactly one reason:

    target_work_item_missing

Every safety property held. Authorization passed, the writer guard was acquired
and released, **the write phase was never entered**, no baseball-data or
lane-bookkeeping effect was produced, no transaction mutation occurred, and the
evidence artifact scanned clean and uploaded before the final gate failed as
designed.

The refusal is the finding. **A GameLog row that exists and reconciles is not
the same fact as a completed durable `game_ingestion_work_item`.** The lane
writes that row only in a write-capable mode, and it has only ever run in
shadow — so no amount of inspecting reconciled statistics tells an operator
whether a game is a valid qualification target. Trying another game by intuition
would have produced the same refusal somewhere else.

### The audit

Workflow: `.github/workflows/manual-noop-qualification-candidate-audit.yml`.
Entry point: `backend/scripts/run_noop_qualification_candidate_audit.py`.
Service: `backend/services/noop_qualification_candidate_audit.py`.

Manual-only (`workflow_dispatch` only), main-only, owner-only, sharing the
`baseballos-sync` concurrency group with `cancel-in-progress: false`, bounded to
20 minutes. Inputs are bounded twice, in shell and in Python:

| input | rule |
| :--- | :--- |
| `expected_head_sha` | required; 40 lowercase hex; must equal `GITHUB_SHA` |
| `confirmation` | required; exactly `AUDIT_NOOP_QUALIFICATION_CANDIDATES` |
| `lookback_days` | 1–120, default 30 |
| `candidate_limit` | 1–50, default 20 |
| `eligible_target_count` | 1–10, default 5, never above `candidate_limit` |
| `operator_note` | optional; sanitized; cannot affect authorization |

Discovery reads completed durable work items and orders them explicitly —
`completed_at DESC, represented_date DESC, mlb_game_pk ASC` — never relying on
database default order. Scanning stops at the eligible target or the candidate
limit, whichever comes first.

Each candidate is then evaluated by the **canonical shadow lane** with exact
one-game scope, using the same reference-date behaviour as the qualification
itself. Eligibility requires the lane's exact successful-completion status
(`complete`); every other status maps to a named refusal, and any status this
contract does not recognise fails closed rather than being read as success
because some rows happened to look unchanged.

The audit reports `candidate_pool_size`, `candidates_selected`,
`candidates_evaluated`, `eligible_stop_position`, and
`configured_candidate_limit` separately — early stopping must not inflate the
evaluated count — and the stop reason distinguishes
`eligible_target_reached` from `candidate_limit_reached` and
`candidate_pool_exhausted` using the configured limit, not merely a non-empty
list. The audit owns no baseball decision: scope, finality, plan governance,
source revisions and fingerprints all come from the canonical components and the
shared qualification helpers.

### Eligibility requires positive evidence

A candidate is eligible only when every condition is positively observed:
planner executed; finality established for exactly the requested game; exact
scope with no missing, unexpected, or duplicate game; a non-empty plan whose
every row is `unchanged`; zero inserts, updates, blocked rows, canonical-outs
corrections, statistical corrections, authority reconciliations, appearance-team
mutations and identity actions; exactly one non-null source revision for the
requested game; and a plan fingerprint. **Nothing is eligible because a failure
is absent.** The shared plan-governance pass must itself declare the entire plan
already matching — unknown action count zero, prohibited actions zero, unchanged
row count equal to planned row count, no non-zero mutation counter, and
`all_rows_already_matching` exactly true — and a final positive predicate must
find every condition met. A candidate that reaches the end with no recognised
reason code but an unmet condition fails closed as
`shared_plan_governance_failed`.

Each candidate receives exactly one primary classification under a declared
precedence: read-only violation → execution error / unproven → durable-work-item
invalidity → finality / scope → mutation / identity → revision / fingerprint →
eligible.

### Read-only, proven three ways

1. The **acquire-only** public sync advisory lock
   (`acquire_public_sync_read_lock`) — it takes the same lock as the production
   writers and never creates, reclaims, or updates a `SyncRun` row.
2. A PostgreSQL `SET TRANSACTION READ ONLY` with a **refused write probe**
   bounded by `WHERE 1 = 0`, reused from the existing production diagnostics and
   failing closed. It is re-asserted after every candidate, because the shadow
   lane ends with a rollback and a rollback starts a fresh transaction.
3. **Before/after content fingerprints** — full row content and timestamps, not
   row counts — across every table the shadow path can reach: `game_logs`,
   `pitchers`, `game_ingestion_work_items`, `postgame_processed_games`,
   `scheduled_games`, and `sync_failures` (the dead-letter target).

**The audit does not attempt zero SQL writes, and does not claim to.** It issues
exactly one bounded write statement — the proof itself — and the evidence says so
in its own fields rather than rounding it to zero:

| field | expected |
| :--- | :--- |
| `read_only_probe_attempted` | true |
| `read_only_probe_count` | 1 |
| `read_only_probe_statement_class` | `UPDATE` |
| `read_only_probe_bounded_to_zero_rows` | true |
| `read_only_probe_refused` | true |
| `durable_write_attempts` | 0 |
| `durable_rows_created` / `_updated` / `_deleted` | 0 |
| `commits_performed_by_audit` | 0 |

The statement text is never reproduced in the artifact. PASS requires the probe
to have been attempted exactly once and refused.

Structural tests prove the service contains no session write API, never commits,
reaches the lane in shadow only, and contains exactly one SQL mutation verb —
the bounded refused probe.

### Results

| result | exit | meaning |
| :--- | ---: | :--- |
| `COMPLETE_ELIGIBLE_FOUND` | 0 | at least one eligible candidate |
| `COMPLETE_NO_ELIGIBLE_CANDIDATE` | 0 | completed audit, nothing eligible |
| `FAILED` | 1 | a write was observed |
| `UNPROVEN` | 2 | evidence could not be completed |

**Finding zero candidates is a success, not a failure.** The audit creates no
work item, dispatches nothing, and weakens no existing contract. The suggested
candidate is the first eligible game under the declared ordering and is
explicitly informational.

### Two database guarantees found during implementation

Recorded rather than assumed, because both make a requested guard unreachable:

- `uq_game_ingestion_work_items_game_pk` makes **duplicate work-item identity
  impossible**.
- `ck_game_ingestion_work_items_completion_proof` makes a completed row
  **without** a completion timestamp and an exactly reconciled expectation
  impossible.

The audit still de-duplicates and still filters on completion, because a guard
that depends on a constraint staying in place has a hidden premise — but the
honest statement is that the database prevents both first.

### Corrected finality evidence

The failed artifact reported `finality_proven_by_planner: true` even though
execution stopped at the work-item precondition **before the planner ran**,
because the field was derived from the absence of a not-plannable failure. That
did not weaken the refusal, but it was inaccurate evidence.

Execution state is now recorded explicitly:

| field | true only when |
| :--- | :--- |
| `work_item_precondition_checked` | the durable lookup actually ran |
| `work_item_precondition_passed` | the required completed item was found |
| `planner_phase_entered` | canonical shadow execution began |
| `finality_check_executed` | canonical planner evidence exists |
| `finality_proven_by_planner` | the planner positively planned that exact game |

For an early refusal, finality is `null` and the summary renders **`not
executed`** rather than `True`.

**The execution order was corrected to match that claim.** The qualification
previously ran the shadow lane *before* reading the durable work item, so a
refusal that was already decided still spent an MLB request and a full canonical
planning pass — and the evidence recorded a planner phase the outcome never
depended on. The work-item precondition is now read first, immediately after the
writer guard, and a missing or unreadable item refuses **without calling
`run_game_driven_ingestion` and without any MLB request**. `planner_phase_entered`
is set immediately before the lane call, and entered-and-returned is recorded
separately from entered-and-raised.

Run `30862655470` has a regression test that drives the real `run()`
orchestration — not a helper fixture — and asserts the lane and the MLB client
are never called, while the writer guard is still acquired and released.

### If no candidate exists

The audit stops at `COMPLETE_NO_ELIGIBLE_CANDIDATE`. The next step is a
separately reviewed decision between (1) a governed exact-scope lane-ledger
initialization package, or (2) allowing the first no-op qualification to create
exactly one work item under a separately governed creation contract. **Neither
is authorized**, and the audit must not be widened to manufacture a candidate.

## Manual no-op write qualification (D-041)

**Machinery only. It has not been run. Running it requires explicit operator
approval, and a PASS authorizes nothing beyond itself.**

Shadow qualification proved what the lane *would* do. It never proved the lane
could *enter* its write-capable path, because every shadow proof was obtained
with writes disabled. This qualification closes that one gap on a single
completed game whose canonical rows already match, before any real correction is
attempted.

### The shell boundary

No `${{ }}` expression appears inside any `run:` script. GitHub substitutes
expressions into the script text **before** bash parses it, so an expression
holding operator input would become shell code in a step carrying production
credentials — and sanitising it in Python happens far too late. Every
user-controlled value therefore crosses into the shell only through step-level
`env:` (`INPUT_GAME_PK`, `INPUT_EXPECTED_HEAD_SHA`, `INPUT_CONFIRMATION`,
`INPUT_OPERATOR_NOTE`) and is read only as a quoted shell variable. Tests
execute the real preflight script with hostile notes — command substitution,
backticks, semicolons, pipes, quotes, newlines, and variable references — and
assert a canary file never appears.

### Manual only, one game, exact confirmation

Workflow: `.github/workflows/manual-game-driven-noop-qualification.yml`.
Entry point: `backend/scripts/run_game_driven_noop_qualification.py`.
Contract: `backend/services/noop_write_qualification.py`.

The workflow has **only** `workflow_dispatch` — no schedule, no push, no pull
request, no `workflow_run`, no repository dispatch, and no retry that could
re-enter a write. Nothing in the scheduled pipeline can reach it.

| input | rule |
| :--- | :--- |
| `game_pk` | required; exactly one positive integer — no list, comma, range, date, or wildcard |
| `expected_head_sha` | required; full 40-character hex SHA, must equal the resolved `GITHUB_SHA` |
| `confirmation` | required; must be exactly `QUALIFY_NOOP_GAME_<game_pk>` |
| `operator_note` | optional; sanitized, recorded, and never able to affect authorization |

It runs only from `refs/heads/main`, only for the repository owner, and only in
`NickolisK24/bullpen-intel-engine`. It shares the `baseballos-sync` concurrency
group with `cancel-in-progress: false`, so it can neither race another
production writer nor be cancelled mid-transaction. Every gate is re-validated
inside the script, which trusts none of them.

### No second writer

Both phases call the one canonical entry point, `run_game_driven_ingestion`:

1. **`shadow`**, exclusive to the requested game. Reads only. Produces the
   reconciliation-plan fingerprint and the per-row plan.
2. **`write`**, exclusive to the same game, authorized by that fingerprint.

The lane re-fetches, re-plans, and refuses before its first mutation if either
the source revision or the plan moved. That drift check is the lane's own
`_authorize_reviewed_plan` — it is not re-implemented here, because a second
comparator is the exact drift this design exists to detect. The canonical
planner, canonical writer, D-009 identity governance, realization validator, and
the production writer guard are all reused unchanged.

**The write phase is never entered on a plan that proposes work.** An insert,
update, delete, block, canonical-outs correction, appearance-team mutation,
identity creation, reactivation, metadata change, provenance write, checkpoint
change, work-item change, dead-letter, or unrecognized action all refuse first.

### What "no-op" means here, precisely

Measured against the canonical lane, an exclusive write over an already-matching
game produces:

| counter | value | group |
| :--- | ---: | :--- |
| `game_log_rows_written` | 0 | baseball data |
| `pitcher_rows_written` | 0 | baseball data |
| `appearance_team_rows_written` | 0 | baseball data |
| `correction_provenance_rows_written` | 0 | baseball data |
| `dead_letters_created` | 0 | baseball data |
| `work_items_updated` | 1 | lane ledger |
| `work_items_completed` | 1 | lane ledger |
| `checkpoints_advanced` | 1 | lane ledger |
| `commits_performed` | 1 | lane ledger |

PASS requires every **baseball-data** counter to be zero, strictly.

The **lane ledger** counters are not zero and are not reported as zero.
`_process_one_game` claims a work item before fetching and completes it after
persisting whenever writes are enabled, independently of whether the plan
mutates anything. Making them zero would require either bypassing the canonical
writer or changing canonical completion and resume semantics to make a
qualification easier — both cost more safety than they buy. The artifact states
plainly that the transaction boundary was entered and the lane ledger advanced
while no baseball row changed.

Permitting the ledger to move is **not** permitting it to move arbitrarily. The
delta above is the one MEASURED through the canonical PostgreSQL path, and PASS
requires exactly it — exact integers, not `>= 1`.

The qualification requires an **existing** durable work item for the requested
game and refuses before the write phase if none exists: a first production
qualification does not create lane state. It captures the item's complete
governed lifecycle and checkpoint state before and after, enumerates every
changed field, and refuses anything outside the measured set:

| permitted to change | required to hold |
| :--- | :--- |
| `candidate_reason` (exclusive scope plans as `explicit_repair`) | `status`, `source_revision`, `rows_expected` |
| `attempt_count` (+1 exactly) | `rows_reconciled`, `relief_rows_reconciled` |
| `last_attempted_at`, `completed_at` | `correction_count`, `error_class` |
| `completion_proof` (re-stamped with this run) | `first_attempted_at`, `created_at`, and every game identity field |
| `updated_at` | |

Every **unrelated** work item and checkpoint row is fingerprinted before and
after while the writer guard is held; any movement refuses. The evidence carries
`lane_bookkeeping_before`, `lane_bookkeeping_after`,
`lane_bookkeeping_changed_fields`, `lane_bookkeeping_expected_delta`,
`lane_bookkeeping_delta_match`, `unrelated_work_items_digest_before` / `_after`,
`unrelated_checkpoints_digest_before` / `_after`, and
`unrelated_bookkeeping_unchanged`. Missing bookkeeping evidence is UNPROVEN.

This lane has no separate checkpoint table — `checkpoints_advanced` is recorded
at the same site that completes the work item — so the work-item row carries
both lifecycle and checkpoint state. They are reported as two named field
groups rather than pretending a second table exists.

### PASS, FAILED, UNPROVEN

**PASS** additionally requires: exact one-game requested and planned scope;
finality proven by the canonical planner; an available and unchanged source
revision; an available and unchanged plan fingerprint; every planned row already
matching; successful pre- and post-execution readback; identical before/after
canonical state digests; a realization proof with zero divergent, missing,
duplicate, and unresolved rows; and an evidence artifact built, scanned, and
uploaded.

The state digest covers the canonical governed field vocabulary but **excludes
provenance fields and derived decimal companions** — under D-008 a
representation difference in `innings_pitched` is never a baseball change, and
digesting it would let one read as state movement. `innings_pitched_outs`, the
integer authority, is included.

Fingerprints and source revisions are proven **positively**, never inferred
from the absence of a mismatch. Each phase must carry exactly one non-null
source revision for exactly the requested game, and the two must be equal; the
shadow and authorized plan fingerprints must both be present and equal. An
absent authorized fingerprint or an absent write-phase revision is UNPROVEN, not
a silent pass.

The writer guard is reported from what happened, not from intent. The evidence
document is built only **after** the release attempt, and carries
`writer_guard_acquired`, `writer_guard_release_attempted`, and
`writer_guard_released` separately. A failed or unattempted release is UNPROVEN;
nothing hardcodes release success.

**FAILED** is a definite observed violation. **UNPROVEN** is trustworthy
evidence that could not be completed — a missing readback, an unavailable
realization proof, absent effect counters, a missing fingerprint or source
revision, or an artifact that could not be built, scanned, or uploaded. Both
exit non-zero. UNPROVEN is never softened into PASS: absent evidence is the
state most easily mistaken for success. FAILED outranks UNPROVEN.

A fetch count of two is **not** a scope violation. An authorized exclusive write
legitimately fetches the same single game twice — once to recompute the plan for
the reviewed-fingerprint comparison, once to execute it. The contract asserts
one *distinct* game, not one fetch operation.

### Evidence

`artifacts/manual-noop-write-qualification/` holds `qualification-summary.json`,
`qualification-summary.md`, and `qualification-metadata.json`, uploaded as
`game-driven-noop-qualification-<run id>` with 30-day retention. The artifact is
scanned by the single shared forbidden-content scanner
(`scan_forbidden_artifact_content.py`) **before** upload; an unsafe artifact is
never published, and a failed scan or upload is UNPROVEN. Upload is ordered
before the final gate, so a failing qualification still leaves reviewable
evidence.

Every document carries the explicit statement: *this qualification does not
authorize scheduled writes, automated writes, authoritative publication,
backfill, or future mutations.*

### What this does not change

Daily remains `shadow`. Postgame remains `shadow`. Backfill remains `off`.
Publication authority is unchanged and the legacy sync writer remains
production-authoritative. Automated write mode and authoritative mode both
remain **unapproved**. No migration was added; the Alembic head remains
`c7f1b408d93a`. A fingerprint is evidence of what a plan was, never a token
permitting a later write.

### Next stage

After review and merge, a first qualification may be dispatched **only** with
explicit operator approval, against one completed game, from `main`. A PASS
proves the write-capable path can be entered safely on a no-op. Qualifying a
genuine mutation is a separate, separately reviewed package.


## Intraday reconciliation (audit-only, Phase 1)

**Canonical reference: [`INTRADAY_RECONCILIATION.md`](INTRADAY_RECONCILIATION.md)**
— the four-mode architecture, motivating incident, output contract and status
meanings, locking/overlap behavior, required validation period, and future
phases. The summary below is the pipeline-level view; that document is
authoritative.

A real production gap on 2026-07-16 — the Phillies recalled Seth Johnson after
the morning daily sync, and BaseballOS kept treating him as outside the active
roster until the next full sync — motivated a fourth mode, `intraday`: a
lightweight, delta-aware reconciliation throughout the baseball day. This branch
ships **Phase 1 of that mode only, and it is AUDIT-ONLY: manual, read-only, and
non-publishing.** It proves change detection is accurate before any write
behavior is authorized.

- **Trigger:** manual only (`Run workflow → mode: intraday`). There is **no
  cron** for it and it must never become an hourly full sync. It runs in the
  isolated `intraday-audit` job, so it never touches the publish lane (no snapshot
  publish/withhold, no appearance-ledger gate, no dashboard-cache verification).
- **What it does:** fetches current authoritative source state through the same
  MLB client, retry policy, product-date authority, and read-only source helpers
  the daily/postgame syncs already own (`build_team_roster_status_index` /
  `classify_roster_evidence`, `get_transactions` + `is_non_player_transaction`,
  `get_schedule` + `classify_status` + `resolve_scheduled_game_finality`),
  compares it with stored state, and reports the differences.
- **What it never does:** no canonical baseball-data writes, no roster/status/
  transaction/dead-letter mutation, no snapshot publication, no fatigue
  recalculation, no story generation, no public cache warming, and it never
  acquires the sync writer guard. The service self-certifies this with a
  `write_guard` check that fails closed if the ORM session ever holds a pending
  write.
- **Lanes:**
  1. *Active roster + team assignment* — official **active-roster** evidence for
     every MLB team vs stored pitcher state. The production default fetches one
     active-roster request per team (~30 calls), not the four-roster-type sweep
     (~120), because the intraday question is only whether *active*-roster state
     moved after the morning sync. It still detects entry to / departure from the
     active roster, team-assignment changes, newly discovered active pitchers
     (with their source names preserved), conflicting official team evidence, and
     source rows that cannot be safely matched to an MLB identity (never
     name-matched). Where only a departure is proven, a neutral
     `removed_from_active_roster` change type is used — an exact inactive
     destination (IL / optioned / DFA) is never inferred from active-roster
     absence alone. The specific-destination classification remains available as
     a manual deep-diagnostic sweep (`--deep-roster`).
  2. *Transactions* — recent official transactions vs stored transaction
     evidence, **event-aware, bullpen-relevance-gated, and current-membership-
     aware** (contract 1.2.0). Source components are grouped by their stable MLB
     transaction-event id, so a compound event yields at most one finding. A
     finding is materially actionable only when its participant is proven a
     pitcher / two-way player from the MLB id (a tracked `Pitcher` row, source
     position evidence, or a bounded/deduplicated `/people` lookup — never from
     name or transaction type); proven non-pitchers are informational and
     unresolved roles are review-required. Exact stored-state alignment is
     separated from public active-bullpen membership: a historical option/IL
     effect whose latest applicable event and current roster-lane membership prove
     the pitcher is correctly outside the active bullpen is benign
     (`transaction_detail_mismatch` / `superseded_transaction`), never material;
     only a genuine current mismatch is `public_bullpen_effect_unreflected`.
     **Transaction-record actionability is separate from public materiality**
     (contract 1.3.0, Observation #3): a missing/actionable record is
     transaction-ledger actionable but is NOT public-material unless its type can
     change active membership AND the roster lane confirms a current change —
     organization/ledger records (`SGN`/`SFA`/`ASG`), `effect_direction=none`, and
     unknown types (fail-closed) never publish. Public team impact is scoped to the
     governed MLB clubs — affiliate / minor-league ids stay in evidence
     (`non_mlb_team_ids_observed`) but never in `affected_team_ids` /
     `recalculate_team_reads`. Only **meaningful** findings are serialized; benign
     inventory is counted, bounded-sampled, and reported with a
     `benign_records_suppressed` total.
  3. *Schedule + game finality* — the current and previous slate dates: newly
     final games, postponements/reschedules, in-progress games, and stored
     finality conflicts. Contract `1.4.2` groups official rows by normalized
     integer `game_pk` before classification. Equivalent duplicates collapse
     (doubleheader evidence uses boolean `any()`); an unresolved core/status
     contradiction becomes one bounded, review-required `game_source_conflict`,
     makes the lane partial, and is excluded from completed-game and public
     action planning. No response-order freshness or unsupported status
     precedence is assumed, and no completed artifact carries more than one
     schedule difference per `game_pk`.
  4. *Impact plan* — a dry-run `would_refresh` projection split into two
     sub-plans: `public_bullpen_state` (roster/current-state-authoritative — teams,
     targeted pitcher logs, completed game_pks, publish/warm) and
     `transaction_ledger` (records to ingest/reconcile). The flat `would_refresh`
     fields derive **only** from `public_bullpen_state`; transaction-ledger-only
     findings never set public teams, targeted workload, snapshot, or warm.
     Targeted recent-work acquisition is **exclusively roster-authoritative**
     (the roster lane's governed `targeted_recent_work_required` decision), so a
     roster-departing pitcher's public-material transaction never adds a target
     (contract `version` 1.4.1, Production Observation #5). Every
     value is a projection; this audit performs none of it. The roster lane owns
     public current-state materiality and overlapping players/teams are deduped to
     one public impact.
- **`changed` vs material.** Top-level `changed` is true when any meaningful
  finding exists (actionable *or* review-required), so a real
  human-review-required finding is never hidden. `material_change_detected` is
  true only when a future authorized write/recompute would actually be required
  (an actionable finding or a newly-final game). Benign inventory sets neither.
  The `summary` block (contract `version` 1.4.2) carries honest, explicitly
  scoped buckets — `records_checked`, `total_meaningful_findings`,
  `total_actionable_findings`, `review_required_findings`, `unresolved_findings`,
  the transaction-ledger axis (`transaction_record_actionable_count`,
  `transaction_ledger_only_findings`,
  `transaction_public_bullpen_material_count`), the public axis
  (`public_roster_change_count`, `schedule_public_change_count`,
  `public_bullpen_change_count`), `informational_records`, and
  `benign_records_suppressed`. Each aggregate has one derivation source, and the
  deduplicated `public_bullpen_change_count` is `> 0` exactly when
  `public_bullpen_change_detected` is true — a meaningful/actionable finding does
  not by itself imply a public bullpen change.
- **Operator command (read-only):**

  ```
  python backend/scripts/run_intraday_reconcile.py --source manual --json [--output PATH] [--lanes roster_assignment,transactions,schedule_finality]
  ```

  Human-readable progress goes to stderr; a single JSON audit artifact goes to
  stdout with `--json`. The workflow uploads it as the
  `intraday-reconciliation-audit-<run id>` artifact.

- **Production configuration.** The intraday job runs `APP_ENV=production`, so
  production Flask initialization requires `DATABASE_URL`, `SECRET_KEY`, and
  `ADMIN_API_TOKEN`. The workflow maps the existing `BASEBALLOS_ADMIN_API_TOKEN`
  repository secret to `ADMIN_API_TOKEN` (the admin token gates operational
  write endpoints; it does not authorize any write — the audit stays read-only).
  Missing configuration is a **bootstrap failure, not a partial source
  verification**: the CLI still emits a valid `failed` JSON artifact
  (`reason_code: application_bootstrap_failed`) and exits 1, and the workflow
  validates the artifact contract before upload. See
  [`INTRADAY_RECONCILIATION.md` §12](INTRADAY_RECONCILIATION.md).

## The 14:00 UTC morning slate lane — PROD-001 root cause and repair

The scheduled 14:00 UTC schedule/Tonight coherence lane failed on **every** run.
It was not an MLB outage, a missing secret, a timeout, a finality failure, or
anything in the shadow, appearance-ledger, or publication paths. Those all
behaved correctly throughout; the appearance-ledger audit over the same period
reported 127/127 completed games, 1,082/1,082 stored appearances, zero
mismatches, and **publish eligible: YES**.

The lane reached MLB successfully. `/schedule` returned **HTTP 200** and the
schedule rows committed. It then died persisting the Tonight snapshot:

```
psycopg2.errors.StringDataRightTruncation:
value too long for type character varying(40)

UPDATE tonight_intelligence_snapshots
SET response_json = ..., source = ..., generated_at = ..., updated_at = ...
WHERE tonight_intelligence_snapshots.id = ...
```

The stored provenance the lane composes is
`github_actions_morning:schedule_coherence` — **41 characters** against a
**VARCHAR(40)** column. Deterministic, and therefore permanent until the schema
and the composition agreed.

**The defect was structural, not caused by one workflow input.** The service's
own default source composes to `morning_slate_schedule:schedule_coherence`,
also 41 characters, so every caller of this path was one character over.
Shortening `github_actions_morning` would have moved the same failure one
caller down rather than fixing it.

### The repair is capacity, not truncation

| | before | after |
|---|---|---|
| `tonight_intelligence_snapshots.source` | `VARCHAR(40)` | `VARCHAR(128)` |

Migration `c7f1b408d93a` (down revision `b9d4e17c3a80`) widens the column. It
reads no row, rewrites nothing, and leaves nullability, defaults, indexes, and
every unrelated column untouched — widening a varchar is a catalog-only change
on PostgreSQL. The **downgrade refuses** rather than corrupting: it counts rows
longer than 40 first and fails with a clear message instead of silently
truncating provenance.

128 is sized from real composition, not guessed. It keeps the complete 41-
character value, leaves bounded room for foreseeable `source:purpose`
composition, and keeps the field finite and governed — an unbounded `TEXT`
column would trade one silent failure for an unbounded one, and 41 or 42 would
leave the next composed purpose to rediscover this incident.

`TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH` in
`backend/models/tonight_intelligence_snapshot.py` is the single owner of the
width. The model column reads it, the validators read it, and a PostgreSQL test
asserts the **live** column matches it, so schema and application cannot drift
apart silently.

### Validation happens before the transaction, not at COMMIT

`compose_tonight_snapshot_source(base_source, purpose)` in
`services/tonight_intelligence_snapshot.py` is now the one place a snapshot
source is built. It requires both parts, joins them with the existing `:`
separator, preserves both whole, and validates the result against the governed
width. An oversized value raises `TonightSnapshotSourceError` with reason
`tonight_snapshot_source_too_long`, the observed length, the maximum, and the
affected field — **before any database work**, so the lane fails on a named
application condition rather than on a driver truncation error raised
mid-transaction. `write_snapshot` re-validates as defense in depth for callers
that compose their own value.

Nothing truncates, abbreviates, or hashes. Provenance that has been shortened
to fit no longer answers the question the column exists to answer. The CLI's
old `source[:40]` clip was removed for the same reason: it silently rewrote the
truth and could not prevent the failure anyway, since the longer value is
composed downstream.

### The regression that was missing (CI-002)

The lane's existing tests monkeypatched the snapshot writer, so every test
passed while production failed on every run. A mocked writer cannot observe a
column width.

`backend/tests/test_schedule_tonight_refresh_postgres.py` now exercises the
real model, the real writer, the real transaction, and a real commit against
PostgreSQL, stubbing only the MLB schedule request. It seeds an existing row
and drives the **UPDATE** production failed on — not just an insert — then
reads the stored value back from PostgreSQL and asserts all 41 characters
survived. It also narrows the live column back to `VARCHAR(40)` and proves the
same real path raises `psycopg2.errors.StringDataRightTruncation` again.

`backend/tests/test_tonight_snapshot_source_width_migration.py` proves the
migration itself in isolated PostgreSQL schemas: the pre-revision shape rejects
the 41-character value on both insert and update, the upgraded shape accepts
it, existing short values survive unchanged, nullability and indexes are
preserved, and the downgrade refuses when a row would be truncated.

### What did not change

Fail-closed behaviour is intact: a partial schedule ingestion still publishes
no Tonight snapshot, a persistence failure still fails the lane, and a
verification failure still fails the lane. The 14:00 UTC schedule, the source
argument `github_actions_morning`, `SLATE_SCHEDULE_COMMAND_TIMEOUT`, workflow
permissions, publication gates, the appearance-ledger audit, dashboard cache
verification, and every shadow mode are untouched. The root cause was schema
capacity, not runtime.

### Still to prove

**PROD-001 is not closed by this repair.** The migration reaches production
only through the normal reviewed deployment process, and the lane is validated
by the next governed 14:00 UTC run — not by a manual database edit and not by a
new dispatch mode created for the occasion. Until a governed run stores
`github_actions_morning:schedule_coherence` and verifies its readback, the
production outcome is unproven.

## Reading a failure

- **Workflow red on "Appearance ledger audit"** → the ledger has a hole; the
  public dashboard is still serving the last trusted snapshot. Read the audit
  artifact, then dispatch `mode=backfill` with the flagged date and re-run.
- **`daily gameLog lane` dead-letter / `game_log_lane_health:
  all_window_splits_dropped` in the sync summary** → the daily lane dropped
  every in-window split at the finality gate — investigate before trusting
  freshness.
- **Snapshot withheld (`error_message` on the pending snapshot row)** → the
  in-process gate fired before the workflow audit; same remediation.

## Runtime budgets and profiling

Every daily sync logs a per-stage timing summary and an MLB API call count
grouped by endpoint template (`Daily sync stage timings (s): ... API calls:
... by endpoint: ...`), and the summary JSON carries `stage_timings`,
`api_calls_by_endpoint`, `elapsed_seconds` / `fetch_seconds` /
`process_seconds` for the gameLog stage, and `budget_exhausted_pitchers`.

The daily command runs under a **whole-process soft budget**
(`DAILY_SYNC_TOTAL_BUDGET_SECONDS`, workflow value 1080s) with explicit reserve
for required final phases (`DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS`, workflow
value 300s). The gameLog ingestion budget is derived from the total remaining
time after that reserve and capped by `DAILY_SYNC_INGESTION_BUDGET_SECONDS`
(workflow value 720s).

When the derived ingestion budget is exceeded, the **per-pitcher** stage stops
cleanly: the remaining pitchers are dead-lettered in one
`daily_game_log_budget` record (counts + mlb_ids), `records_failed` includes
them, the run finishes **partial** with `lane_health=budget_exhausted`, and the
next daily run (or the postgame lookback) retries them. This is fail-closed by
construction — a truncated sweep is visible and counted, never absorbed — and
the Python process keeps enough headroom to run fatigue, snapshot
publish/withhold, durable metadata, writer-guard release, and cleanup before the
20-minute shell timeout.

The **game-driven** lane behaves differently on purpose: budget exhaustion there
is not a terminal dead-letter condition but an incomplete, resumable run state.
Remaining games are persisted as `planned` work items, the run is marked
incomplete, publication is withheld if critical games remain, and the next run
starts from that unresolved work instead of the beginning of the window. See
[`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md). Budgets
themselves are unchanged — nothing in Foundation 3C raises a timeout.

Pitcher-season ledger coverage is not recomputed for every full-season target
on every daily run. The daily hot path verifies only the accepted current-window
targets while preserving the same source-vs-stored manifest proof for each
target. Full-season coverage maintenance remains available through the
production maintenance workflow.

## Operator tools

- `python backend/scripts/appearance_ledger_audit.py [--end-date D --days N --deep --json]`
- `python backend/scripts/sync_trace.py --player <mlb_id> --date <YYYY-MM-DD> [--game-pk PK] [--no-network]`
- `python backend/scripts/run_postgame_refresh.py --date <YYYY-MM-DD> --source manual_backfill`
- `python backend/scripts/game_driven_ingestion.py [--plan-only | --mode shadow|write] [--only-game-pk PK ...] [--expected-plan-fingerprint SHA] [--game-pk PK] [--max-games N] [--include-backfill]`
  — Foundation 3C staged rollout and governed per-game repair.
  **`--only-game-pk` is exclusive** (exactly those games; fails before any MLB
  request if the planned set differs) and is what a controlled production run
  must use. **`--game-pk` is additive** — it plans the whole governed window
  AND those games. An exclusive write also requires
  `--expected-plan-fingerprint` from a reviewed shadow run. See
  [`GAME_DRIVEN_DAILY_INGESTION.md`](GAME_DRIVEN_DAILY_INGESTION.md).
- `python backend/scripts/inspect_gamelog_field_authority.py --game-pk PK --pitcher-mlb-id ID [--field balls] [--output PATH]`
  — read-only authority audit for one governed field on one appearance.
- `python backend/scripts/plan_boxscore_balls_fallback_impact.py [--days-back N] [--max-candidates N] [--skip-split-confirmation] [--output PATH]`
  — read-only impact plan for the box-score fallback across the correction
  horizon. Enumerates the affected set and reports any proposed change outside
  the approved field. Performs zero writes; run it before any production
  correction.
- `python backend/scripts/refresh_slate_schedule.py --source <source> [--reference-date YYYY-MM-DD]`
  — the 14:00 UTC schedule/Tonight coherence lane. The source is stored whole as
  snapshot provenance; a value too long for the governed column fails as
  `tonight_snapshot_source_too_long` before any write rather than being clipped.
- `python backend/scripts/scan_forbidden_artifact_content.py {FILES | --directory DIR} [--quarantine]`
  — the one forbidden-content contract for activation artifacts. Reports a
  filename and a category, never the matched content.
- `python backend/scripts/prepare_shadow_handoff.py --source-dir DIR --staging-dir DIR`
  — scans and stages the cycle summary for the observer job. Transport only.
- `python backend/scripts/evaluate_shadow_activation_gate.py --handoff-dir DIR ...`
  — the final activation verdict: `PASS`, `FAILED`, or `UNPROVEN`.
- Kill switch (operators only, logged): `APPEARANCE_LEDGER_GATE_ENABLED=false`
- Game-driven lane mode (operators only): `GAME_DRIVEN_INGESTION_MODE=off|shadow|write|authoritative`

## Roster-readiness recovery notes (2026-07-13)

Two production blockers were fixed together after Phase 0I shipped; the
behaviors below are load-bearing for the daily pipeline.

**Batched roster cache-divergence scan.** Roster readiness
(`public_roster_readiness_v1`) checks cache-vs-snapshot divergence on every
Team Board build. The scan is set-based: one query for the active-pitcher
universe plus one window-function query for each pitcher's latest snapshot
(`latest_roster_status_snapshots_by_pitcher_id`), instead of one query per
pitcher. Divergence semantics are unchanged — same pitcher universe, same
latest-snapshot ordering (`snapshot_date desc, updated_at desc, id desc`),
same compared fields — and equivalence plus a query-count bound (≤10 queries
per readiness evaluation, flat as the population grows) are enforced by
`backend/tests/test_roster_divergence_batching.py`. This keeps the static
team-story export (30 boards per run) far inside its 15-minute job timeout;
the export also logs one `Building team board i/N` line per team so a failed
run identifies the last completed team.

**Non-player transaction components.** The MLB transactions feed includes
team-level trade components (cash considerations, players to be named later,
international slot money) that reference no person. Rows whose structured
record carries neither `player_mlb_id` nor `player_full_name` are classified
`non_player_transaction`: counted in the sync summary (`non_player_count`),
logged with their transaction id and type code, never stored as player
transactions, and never dead-lettered. A row that references a person (a name
is present) but lacks a usable id is still a `player_transactions_identity`
dead letter and keeps the run partial — that gate is unchanged.

**Dead-letter reconciliation.** When a source transaction is later stored
successfully or deterministically classified non-player, its exact matching
unresolved `player_transactions_identity` dead letters are marked resolved
(timestamped, idempotent; rows are preserved, never deleted). A failure that
repeats across runs still counts against `records_failed` on every run but no
longer accumulates one duplicate unresolved row per run.

**Verifying roster readiness after a deploy or sync:**

```
curl -s https://<backend-host>/api/bullpen/teams/142/board \
  | jq '.roster_authority.readiness | {readiness_state, claims_available, counts_withheld, reason_codes, coverage}'
```

`claims_available: true` means roster claims are being served; otherwise
`reason_codes` names the exact blocker.

**Roster dead-letter reconciliation.** Public roster readiness fails closed on
ANY unresolved `roster_status_fetch` / `roster_status_snapshot_identity` /
`roster_status_snapshot_conflict` dead letter (reason code
`dead_letters_unresolved`; the gate is league-wide, so one genuine conflict
withholds every team). The daily roster sync now reconciles these against
newer authoritative official roster evidence, and only that:

- *fetch* rows resolve when the same team's roster feeds fetch successfully
  (pre-existing behavior);
- *identity* rows resolve when a later sync enumerates the same team's feeds
  and identifies every entry (a run that records a fresh identity failure for
  the team resolves nothing);
- *conflict* rows resolve when a later sync writes or confirms the same
  pitcher's official snapshot without a team conflict (a pitcher whose upsert
  conflicts in the current run is never self-resolved).

Rows are never deleted — resolution sets `resolved`/`resolved_at` only, is
idempotent, resolves duplicate rows for the same entity together, and genuine
or ambiguous conflicts stay unresolved and keep claims withheld. Inspect the
current blockers (read-only) with:

```
python backend/scripts/roster_readiness_dead_letter_report.py [--json] [--include-resolved]
```

**Confirming the current run's snapshot published (not an older one):** the
sync log line `Dashboard snapshot DB write completed snapshot_id=<id>
status=ready published=True` must show the new id, and
`/api/bullpen/dashboard` must serve that same `snapshot.snapshot_id`. A line
showing `status=pending published=False` means publication was withheld for
this run and the previously trusted snapshot is still serving — the workflow's
cache-verification step alone does not prove the new candidate published.
