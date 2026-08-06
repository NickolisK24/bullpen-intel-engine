# Daily Sync Runtime-Budget Exhaustion — Incident Investigation, August 6, 2026

| Field | Value |
|---|---|
| Status | Point-in-time read-only production incident investigation |
| Owner | Nickolis Kacludis |
| Purpose | Determine why repeated full daily sync runs exhaust the runtime budget before publication-critical GameLog completion |
| Authority | Evidence and recommendation only; authorizes no runtime change, workflow dispatch, production access, mode change, or authority transfer |
| Retirement condition | Retain as incident evidence after the accepted repair is merged and proven in scheduled production. It does not become a competing operations manual or roadmap. |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `da7e39c1f888d72afb33fefd69d5dbb7be6d644f` |
| Investigation method | Repository source reading, GitHub Actions run/job metadata, retained job logs. No production database session, no workflow dispatch, no production mutation. |

---

## 1. Executive verdict

The daily sync is not failing because of MLB instability, GitHub scheduling, or a database fault. It is failing because **the runtime budget is allocated in the wrong order relative to how the work is distributed.**

Publication-critical GameLog ingestion is the *last* expensive stage in the run, and its budget is whatever is left over:

```
ingestion_budget = min(720, max(1080 − elapsed_before_ingestion, 0) − 300)
```

Five upstream stages — team assignment, roster status, transactions, schedule-finality preflight, and slate refresh, followed by the game-driven shadow lane — consumed **628.5 s** and **612.2 s** in the two failed runs. That left **151.5 s** and **167.8 s** for a stage that must evaluate **861 pitchers with one MLB season-log call each**. It completed 120 and 129 of them respectively and dead-lettered the rest in a single batch.

Two structural facts make this a design defect rather than a tuning miss:

1. **The configured 720 s ingestion cap is unreachable in practice.** It can only bind when upstream finishes in ≤ 60 s (`1080 − 60 − 300 = 720`). Upstream has never been that fast in any observed full run. The documented cap is effectively fiction; the real budget is a remainder.
2. **The upstream stages are unconditional full refreshes.** Roster status re-fetches 30 teams × 4 roster types on every run. Transactions re-fetch a fixed 7-day window on every run. Neither consults a last-success checkpoint. None of that work is publication-critical, yet all of it is spent before the publication-critical lane is allowed to start.

The "successful" recovery run did not succeed because it was correct. It succeeded because **it was the second pass of an accidental two-pass pipeline** — a failed run 30 minutes earlier had already performed the durable upstream and partial-ingestion work, so the second run had materially less to do. That is the single most important finding in this document: manual retry is currently load-bearing, and it is not a control anyone designed.

**Verdict: root cause proven. The repair is a work-reduction and ordering problem, not a ceiling problem.** Raising the ceiling alone would convert a hard failure into a slower hard failure as the active-pitcher population grows.

---

## 2. Incident timeline

All times UTC, August 6, 2026. Workflow `.github/workflows/baseballos-sync.yml`, concurrency group `baseballos-sync` (`cancel-in-progress: false`, workflow lines 69–71).

| Time | Run | Event | SHA | Result | Note |
|---|---|---|---|---|---|
| 10:55:05 | — | — | `d5ddb5f` | — | PR #617 merged to main |
| 11:03:01 → 11:20:24 | `31095686315` (run 462) | `workflow_dispatch` | `d5ddb5f` | **failure** | **Not present in the incident brief.** Recovery attempt #1. |
| 11:33:06 → 12:10:26 | `31097712768` (run 463) | `workflow_dispatch` | `d5ddb5f` | success | Recovery attempt #2. Published snapshot 360. |
| 12:01:15 | `31099639901` | `schedule` | `5be94b7` | — | Run created; job queued behind the concurrency lane |
| 12:10:29 → 12:27:26 | `31099639901` | `schedule` | `5be94b7` | **failure** | Job started only after run 463's `internal-enrichment` released the lane at 12:10:22 |
| 12:49:30 → 13:07:01 | `31103076829` | `workflow_dispatch` | `5be94b7` | **failure** | Recovery attempt #3 |

The brief describes three runs. There were **four**. Run `31095686315` is the missing one, and it is the run that explains the success.

### Daily-sync step durations (job step 5, "Run direct daily sync")

| Run | Step start | Step end | Duration | Outcome |
|---|---|---|---|---|
| `31097712768` | 11:33:21 | 11:47:05 | **824 s** | success |
| `31099639901` | 12:10:40 | 12:27:18 | **998 s** | failure |

Neither hit the 1200 s shell timeout or the 1080 s total budget. **The process was never killed.** It ran to completion, deferred work it could not fit, and exited non-zero because publication proof failed. The failure is a governed refusal, not a crash — which is the system behaving correctly given a starved lane.

---

## 3. Production safety assessment

Verified from retained run evidence. Every safety property held.

| Property | Evidence | Verdict |
|---|---|---|
| Candidate 361 not published | Run `31099639901` step 13 reported served `id=360`; candidate remained pending | **Safe** |
| Candidate 362 not published | Run `31103076829`, same pattern | **Safe** |
| Snapshot 360 still selected and served | `31099639901` job log 12:27:22: `Dashboard snapshot verification passed: id=360 data_through=2026-08-05 generated_at=2026-08-06T11:45:33.037127` | **Safe** |
| Appearance ledger complete | Step 11 "Appearance ledger audit (publish eligibility)" — `success` in both failed runs | **Safe** |
| No corrupted candidate promoted | Publication proof failed closed; `run_daily_sync.py:88-90` returns non-zero unless `publication_proof.verified is True` | **Safe** |
| Publication failed closed | Same | **Safe** |
| Shadow zero-write | `GAME_DRIVEN_INGESTION_MODE: 'shadow'` set at step scope only (workflow line 114); shadow health failed *independently* in its own job | **Safe** |
| No shadow commits / checkpoint advances | `shadow-activation-health` is a separate job (`needs: public-sync`) reporting observer health only; job log 12:27:41 states publication authority unchanged | **Safe** |
| No mode or authority change | No workflow or configuration change in the window | **Safe** |

### Degradation assessment — the platform is *not* healthy

Serving snapshot 360 is safe, but safe is not current. These are distinct and must not be conflated.

| Surface | State | Risk |
|---|---|---|
| **Dashboard** | Serving snapshot 360, data through Aug 5 | **Safe but frozen.** Every failed run leaves the Dashboard one day further behind. It is honest — `data_through` is visible — but it is stale. |
| **Team Board** | Live reads compute against current DB rows | **Degraded.** GameLog ingestion completed only 120/861 and 129/861 pitchers. Live per-team readiness reads whatever rows exist, so a team whose arms were dead-lettered reads against incomplete recent work. This is the most concerning surface. |
| **Compare** | Consumes two Team Board contracts | **Degraded, and asymmetrically.** One side may have been ingested and the other dead-lettered, producing a side-by-side of unequal freshness. |
| **Tonight** | "Refresh schedule and warm Tonight" (step 6) **skipped** in both failed runs — it lacks `if: always()` | **Stale.** Tonight did not refresh at all on either failed run. |
| **Roster freshness** | Roster stage ran to completion before the failure | **Current.** |
| **Fatigue freshness** | Fatigue runs in the final phase, after ingestion | **Computed, but over an incomplete GameLog.** Fatigue is fresh with respect to stale inputs. |
| **Scheduled slate** | Slate refresh ran before the failure | **Current.** |
| **Internal enrichment / static preview** | Both jobs gated on `needs.public-sync.result == 'success'` (workflow lines 715, 798) — **skipped** | Static team preview pages are not regenerating. |

**The dead-letter path is where public truth quietly degrades.** 741 and 732 pitchers were dead-lettered with `records_failed` incremented (`backend/services/sync.py:3746-3747`), and the run reported 298 and 289 publication-critical failures. Live reads do not consult the dead-letter ledger.

---

## 4. Current runtime-budget model

### Configured hierarchy

| Layer | Value | Location |
|---|---|---|
| GitHub job timeout | 40 min | workflow line 87 |
| Shell timeout (`timeout --kill-after=30s`) | 20 min = 1200 s | workflow line 118, applied line 138 |
| `DAILY_SYNC_TOTAL_BUDGET_SECONDS` | **1080** | workflow line 123 |
| `DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS` | **300** | workflow line 124 |
| `DAILY_SYNC_INGESTION_BUDGET_SECONDS` (cap) | **720** | workflow line 128 |
| Downstream `internal-enrichment` timeout | 50 min | workflow line 717 |
| Downstream `static-team-story-preview` timeout | 15 min | workflow line 799 |
| Workflow concurrency | singleton `baseballos-sync`, no cancel | workflow lines 69–71 |

### The formula

`backend/services/sync.py:3423-3461`, `_daily_sync_runtime_budget()`:

```
elapsed_before_ingestion = monotonic() − sync_started            # line 3427
remaining_total          = max(1080 − elapsed_before, 0)          # lines 3428-3432
budget_after_reserve     = max(remaining_total − 300, 0)          # lines 3433-3437
ingestion_budget         = min(720, budget_after_reserve)         # lines 3440-3443
```

`sync_started` is set at `sync.py:6142`, before any stage. The budget is measured from **process start**, not from cron time.

### Verification against observed runs

| Run | elapsed_before | `1080 − elapsed` | `− 300` | `min(720, ·)` | Reported |
|---|---|---|---|---|---|
| `31099639901` | 628.5 | 451.5 | 151.5 | **151.5** | 151.5 ✔ |
| `31103076829` | 612.2 | 467.8 | 167.8 | **167.8** | 167.8 ✔ |

Exact match. The formula is proven.

### The 720 s cap is effectively fictional

The cap binds only when `1080 − elapsed − 300 ≥ 720`, i.e. **elapsed_before_ingestion ≤ 60 s**. No observed full daily run has upstream under 60 s; the two failures were 10× that. The operator-facing configuration advertises a 12-minute ingestion budget while the code delivers 2.5 minutes. **This gap is itself a defect** — it makes the system's most important constraint invisible to the person tuning it.

### Conservative runtime model (from real evidence only — 4 full-daily samples, no invented percentiles)

| Quantity | Value | Basis |
|---|---|---|
| Observed minimum full-daily process | 824 s | run `31097712768`, warm second pass |
| Observed maximum full-daily process | 998 s | run `31099639901`, cold |
| Observed upstream (pre-ingestion) | 612.2 – 628.5 s | runs `31103076829`, `31099639901` |
| Ingestion actually needed (cold, 861 pitchers) | **Not observed — never allowed to run to completion** | — |
| Ingestion observed rate | ~120 pitchers / 151.5 s ≈ **0.79/s**; 129 / 167.8 ≈ **0.77/s** | both failures |
| **Extrapolated cold ingestion requirement** | 861 ÷ 0.78 ≈ **1100 s** | derived; see caveat below |
| Final phase observed | ≈ 218 s (`998 − 628.5 − 151.5`) | run `31099639901` |
| **Implied cold total** | ≈ 628 + 1100 + 218 ≈ **1950 s (32.5 min)** | derived |

**Caveat, stated plainly:** the 0.78 pitchers/s rate is measured on the *first* pitchers processed, which are ordered publication-critical-first (`sync.py:3665-3672`) and are the most likely to have new rows to write. The true full-population rate is probably faster, so ~1950 s is an upper bound rather than a point estimate. It is nonetheless far outside the 1080 s budget and outside the 1200 s shell timeout. **A cold, single-pass daily run has probably never fitted the current budget.**

---

## 5. Three-run comparison (four runs, including the omitted one)

| Field | `31095686315` | `31097712768` | `31099639901` | `31103076829` |
|---|---|---|---|---|
| Run number | 462 | 463 | 464 | 465 |
| Event | workflow_dispatch | workflow_dispatch | schedule | workflow_dispatch |
| Schedule expression | — | — | `0 10 * * *` | — |
| Repository SHA | `d5ddb5f` | `d5ddb5f` | `5be94b7` | `5be94b7` |
| Run start → end | 11:03:01 → 11:20:24 | 11:33:06 → 12:10:26 | 12:01:15 → 12:27:45 | 12:49:30 → 13:07:01 |
| Run duration | 17 m 23 s | 37 m 20 s | 26 m 30 s | 17 m 31 s |
| `public-sync` job | 11:03:0x → 11:19:5x | 11:33:10 → 11:49:05 | 12:10:29 → 12:27:26 | — |
| Daily-sync step duration | *not separately retrieved* | **824 s** | **998 s** | *not separately retrieved* |
| Runner exit | 1 | 0 | 1 | 1 |
| Sync status | failure | success | failure | failure |
| Elapsed before ingestion | *unresolved* | *unresolved (≈400 s derived)* | **628.5 s** | **612.2 s** |
| Derived ingestion budget | *unresolved* | *unresolved (≈380 s derived)* | **151.5 s** | **167.8 s** |
| GameLog pitchers planned | *unresolved* | 861 | **861** | **861** |
| GameLog completed | *unresolved* | 861 (implied by success) | **120** | **129** |
| GameLog dead-lettered | *unresolved* | 0 | **741** | **732** |
| Publication-critical failed | *unresolved* | 0 | **298** | **289** |
| Candidate snapshot | *unresolved* | **360 — published, selected, served** | 361 — pending, withheld | 362 — pending, withheld |
| Served snapshot after run | *unresolved* | 360 | **360** | **360** |
| Appearance-ledger audit | — | pass | **pass** | **pass** |
| Dashboard-cache verification | — | pass | **pass** (`id=360 data_through=2026-08-05`) | **pass** |
| Shadow activation health | fail | **pass** | **fail** (independent job) | fail |
| Tonight refresh (step 6) | skipped | **ran, 114 s** | **skipped** | skipped |
| `internal-enrichment` | skipped | **ran, 21 m 01 s** | skipped | skipped |
| `static-team-story-preview` | skipped | **ran, 3 m 05 s** | skipped | skipped |

### Differences explained

- **Run 463's 37-minute total** is not a slow sync. Its daily step was the *fastest* (824 s). The extra time is `internal-enrichment` (11:49:21 → 12:10:22), which only runs when `public-sync` succeeds.
- **The scheduled run's 9-minute job queue** (run created 12:01:15, job started 12:10:29) is the singleton concurrency lane: run 463's `internal-enrichment` held it until 12:10:22. This is a queueing artifact, not scheduling latency, and it consumed **no** internal budget.
- **The 10:00 cron → 12:01 run creation gap** is not explained by evidence available here. Listed as unresolved in §20. It is **not** causal (see H-09).

### Unresolved differences

- Exact `elapsed_before_ingestion`, stage timings, and API-call totals for runs `31095686315` and `31097712768`. These live in the retained `daily-sync-summary.json` artifacts and in the middle of the job logs; neither was retrievable in this environment (direct GitHub API access returns HTTP 403 through the session proxy, and log tailing returns only the tail).
- Per-stage breakdown of the 612–628 s upstream block. The code identifies the stages; the run evidence available here does not attribute seconds to each. **This is the single most valuable missing measurement** and should be captured before the permanent fix is designed.

---

## 6. Stage-by-stage analysis

Execution order, `backend/services/sync.py:6163-6340`:

| # | Stage | Code | Full refresh? | Checkpoint? | Publication-critical? | Could run after publication? |
|---|---|---|---|---|---|---|
| 1 | Writer guard + sync-run start | `sync.py:6165-6172` | — | — | yes (guard) | no |
| 2 | **Team assignments** | `sync.py:6180`, `team_assignment_sync.py:341` | **yes** | **no** | no | **yes** |
| 3 | **Roster statuses** | `sync.py:6199`, `roster_status_sync.py:655` | **yes** | **no** | no | **yes** |
| 4 | **Transactions** | `sync.py:6215`, `transaction_ingestion.py:192` | **yes, fixed 7-day window** | **no** | no | **yes** |
| 5 | Schedule-finality preflight | `sync.py:6233-6262` | window refresh | no | partly | partly |
| 6 | Slate-schedule refresh | `sync.py:6264-6282` | window refresh | no | no | **yes** |
| 7 | Budget computed | `sync.py:6294` | — | — | — | — |
| 8 | Game-driven shadow lane | `sync.py:6300-6318` | observation | n/a | **no — shadow** | **yes** |
| 9 | **GameLog ingestion** | `sync.py:6322`, `sync_recent_logs` at `sync.py:3571` | **yes, all active pitchers** | **no** | **YES** | no |
| 10 | Fatigue recalculation | final phase | — | — | yes | no |
| 11 | Snapshot assembly + publication gate | final phase | — | — | yes | no |
| 12 | Writer-guard release, metadata, cleanup | final phase | — | — | yes | no |

**Six of the eight stages that run before the publication-critical lane are not themselves publication-critical, and four of them could safely run after the publication decision.**

### Stage 3 — roster statuses (the clearest offender)

`roster_status_sync.py:655-685` loops `for team_id in team_ids`, and `_team_ids_to_sync` (`:301-311`) returns every distinct `team_id` for active pitchers — all 30 clubs. For each, `build_team_roster_status_index` (`:269-296`) loops `for roster_type in roster_types` over `ROSTER_TYPES` (`:36-41`) = `ACTIVE`, `40_MAN`, `FULL`, `NON_ROSTER`.

**30 × 4 = ~120 MLB roster API calls on every daily run, unconditionally, with no last-success checkpoint and no change detection before the call.**

### Stage 4 — transactions

`transaction_ingestion.py:200-216`: `start_date = end_date − TRANSACTION_SYNC_WINDOW_DAYS`, where the constant is `7` (`:21`). The full 7-day window is re-fetched and reprocessed every run. Six of those seven days were already ingested by the previous run. `_record_sync_window` records the window *after* the fetch; nothing reads it to skip work.

### Stage 9 — GameLog ingestion

`sync.py:3639`:

```python
pitchers = Pitcher.query.filter_by(active=True).all()
```

Then, per pitcher, `sync.py:~3802`:

```python
splits = mlb_client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
```

**One full-season game-log API call per active pitcher, 861 of them, with no cheap exclusion first.** There is real optimisation already present — a single prefetch of current-season rows (`sync.py:3699-3712`), a shared finality cache (`:3695`), a shared box-score cache (`:3698`) — but all of it happens *after* the per-pitcher network call. Nothing asks "could this pitcher possibly have new work?" before spending the call.

The budget-exhaustion path (`sync.py:3731-3799`) checks elapsed time at the top of each iteration, and on exhaustion dead-letters **all remaining pitchers in one batch** and breaks. The ordering guarantee (`sync.py:3665-3672`, publication-critical first) works exactly as designed — it is simply given far too little time to matter.

---

## 7. API-call and database-work analysis

Per full daily run, derived from code:

| Stage | MLB API calls | Character |
|---|---|---|
| Team assignments | ~1 per team or per pitcher batch | full refresh |
| **Roster statuses** | **~120** (30 teams × 4 roster types) | full refresh, unconditional |
| Transactions | 1 (7-day window) | full re-fetch |
| Schedule finality | ~1 per day in window | window refresh |
| Slate refresh | ~1 per day in window | window refresh |
| Shadow lane | plans/fetches per game | observation |
| **GameLog ingestion** | **up to 861** (one season fetch per active pitcher) | full enumeration |

**Roughly 1,000 MLB API calls per daily run, of which ~86 % are the per-pitcher GameLog fetches and ~12 % are roster fetches.**

Database work: the GameLog stage is already well optimised on the read side (one prefetch for the season, one for unresolved fetch refs). The available evidence does **not** allow attributing the 612–628 s upstream block between API latency and database processing — that split is unresolved and is the key measurement to capture next. H-08 is therefore recorded as unproven rather than guessed at.

No artificial sleeps or pacing were found in the daily path. The only sleeps observed are in the dashboard-verification retry loop (workflow lines ~416+), which runs after the sync.

---

## 8. Successful-run versus failed-run explanation

This is the crux, and the incident brief could not have reached it because it omitted run `31095686315`.

```
11:03:01  run 462  dispatch  FAILS after 17m23s
                             → team assignments refreshed and committed
                             → roster statuses refreshed and committed (~120 API calls)
                             → transactions ingested for the 7-day window
                             → schedule finality + slate refreshed
                             → partial GameLog ingestion committed
                             → remainder dead-lettered

          30-minute gap

11:33:06  run 463  dispatch  SUCCEEDS — daily step only 824s
                             → same upstream stages re-run, but every row they
                               would write was written 30 minutes ago
                             → GameLog per-pitcher loop finds most rows already
                               present and unchanged
                             → ingestion completes inside its remainder budget
                             → snapshot 360 published at 11:45:33
```

The successful run's daily step (824 s) was **174 s faster** than the scheduled failure's (998 s) despite doing the *same nominal work*. It was faster because the work had already been done.

Deriving the split for run 463: with the failed run's final phase measured at ≈ 218 s (`998 − 628.5 − 151.5`), and ingestion completing rather than being cut off, an upstream of ≈ 400 s and an ingestion of ≈ 200 s reconciles to 824 s. That puts run 463's upstream **~228 s (≈ 36 %) below** the cold run's 628.5 s. The exact figures are unresolved (§20) — but the direction is unambiguous and the mechanism is proven independently by the run ordering.

**Conclusion: the successful run was the second pass of an unplanned two-pass pipeline.** Its success is not reproducible from a cold start. Any "it worked when we retried" reasoning is measuring the residue of the previous failure, not the health of the system.

The two runs *after* it failed because they were cold again with respect to a fresh product day's work — and, critically, because nothing in the design carries partial progress forward deliberately. The system accidentally benefits from retries while formally treating each run as independent.

---

## 9. Hypothesis verdicts

| ID | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| **H-01** | Roster sync performs a full repeated multi-roster refresh for all 30 teams even after a recent success | **SUPPORTED** | `roster_status_sync.py:655-685` loops all teams from `_team_ids_to_sync` (`:301-311`); `build_team_roster_status_index` (`:269-296`) loops all four `ROSTER_TYPES` (`:36-41`). No checkpoint, no conditional. ~120 unconditional API calls per run. |
| **H-02** | Transaction ingestion reprocesses a broad historical range every run rather than incrementally | **SUPPORTED** | `transaction_ingestion.py:200-216` computes `start_date = end_date − 7` every run and re-fetches; `TRANSACTION_SYNC_WINDOW_DAYS = 7` (`:21`). Six of seven days are redundant. Window recorded after the fact, never read to skip. |
| **H-03** | GameLog ingestion enumerates all 861 pitchers before cheaply excluding those with no possible new work | **SUPPORTED** | `sync.py:3639` `Pitcher.query.filter_by(active=True).all()`; per-pitcher `mlb_client.get_pitcher_game_logs(...)` at `sync.py:~3802`. Prefetches and caches (`:3695-3712`) all sit *after* the network call. No pre-filter exists. |
| **H-04** | The successful recovery benefited from durable work by an earlier partial run | **SUPPORTED** | Run `31095686315` (11:03–11:20, failed) preceded run `31097712768` (11:33, success) by 30 minutes on the same SHA. Success step 824 s vs cold failure 998 s. §8. |
| **H-05** | The 1080 s budget was sized from a smaller workload or warm observations and does not cover cold execution | **SUPPORTED** | Extrapolated cold requirement ≈ 1950 s vs 1080 s budget and 1200 s shell timeout (§4). No observed run has ever completed 861 pitchers from cold in one pass. |
| **H-06** | The 300 s reserve is reasonable, but its interaction with expensive upstream starves the publication-critical lane | **SUPPORTED** | Final phase measured ≈ 218 s — the reserve is correctly sized and was *not* over-generous. The starvation comes entirely from the 612–628 s upstream. Reducing the reserve would be the wrong lever and would endanger finalisation. |
| **H-07** | Publication-critical GameLog ingestion is ordered too late relative to deferrable non-GameLog work | **SUPPORTED** | Stage table §6: four fully deferrable, non-publication-critical stages plus the shadow observer all precede the publication-critical lane. |
| **H-08** | Database processing or commit granularity, not API latency, accounts for most elapsed time | **UNPROVEN** | The stage timings are recorded into `stage_timings` (`sync.py:6176-6181` onward) and persisted in the run summary artifact, but that artifact was not retrievable here. **Do not act on this hypothesis without the measurement.** |
| **H-09** | The scheduled run's delayed start was external and did not itself cause budget exhaustion | **SUPPORTED (for the causal claim)** | The budget is measured from `sync_started = time.monotonic()` at `sync.py:6142`, i.e. process start — wall-clock delay cannot consume it. Decisively: the 12:49 manual dispatch had no scheduling delay at all and failed with near-identical numbers (612.2 s / 167.8 s / 129 done / 732 dead-lettered). The 9-minute job queue is the singleton concurrency lane, not latency. The 10:00→12:01 run-creation gap itself remains unexplained (§20) but is not causal. |
| **H-10** | Repeated manual retries succeed only because prior failed runs perform durable upstream work — an accidental multi-pass pipeline | **SUPPORTED** | Directly demonstrated by the 462 → 463 sequence (§8). This is the finding with the greatest operational significance: manual retry is currently a load-bearing part of the pipeline and nobody designed it that way. |

---

## 10. Root cause

**The publication-critical GameLog lane receives only the remainder of a fixed 1080-second budget after five unconditional full-refresh upstream stages and a shadow observer have consumed 612–628 seconds, leaving 151–168 seconds for work that requires roughly 1100 seconds from cold.**

Three necessary conditions, all present:

1. **Ordering** — the only publication-critical source stage runs last (`sync.py:6322`, after stages at `:6180`, `:6199`, `:6215`, `:6233`, `:6264`, `:6300`).
2. **Unbounded upstream** — those stages are unconditional full refreshes with no checkpoint (`roster_status_sync.py:655`, `transaction_ingestion.py:200`).
3. **Unfiltered ingestion scope** — 861 pitchers each cost one MLB season-log call, with no cheap pre-exclusion (`sync.py:3639`, `:~3802`).

Remove any one and the incident does not occur. The budget ceiling is the *symptom surface*, not the cause.

---

## 11. Contributing factors

1. **The 720 s ingestion cap is unreachable** (needs upstream ≤ 60 s), so the configuration misrepresents the real constraint to whoever tunes it.
2. **Accidental multi-pass recovery masked the defect.** Retries "worked", so the cold-start deficit was never measured.
3. **Growth of the active-pitcher population** silently raises ingestion cost; nothing alerts when required time crosses the available remainder. *(No evidence was found of a recent code change increasing the work — the Team State correction in PR #617 touched only readiness projection, not ingestion. Volume growth is the plausible driver but is not proven here.)*
4. **Dead-lettering is silent to live reads.** 741 pitchers can be deferred while Team Board and Compare read the resulting incomplete rows without any surfaced limitation.
5. **Tonight refresh is collateral damage** — step 6 lacks `if: always()`, so a sync failure also freezes Tonight.
6. **No stage-level runtime alerting.** Upstream at 628 s is a five-alarm signal that is recorded but not acted upon.

---

## 12. Rejected causes

| Cause | Why rejected |
|---|---|
| MLB API instability | No fetch-failure evidence in the retained logs. Both failures show orderly budget-driven dead-lettering, not source errors. **No claim of MLB instability is made anywhere in this document.** |
| GitHub scheduling delay | H-09. Budget is measured from process start; the undelayed 12:49 dispatch failed identically. |
| Shell/job timeout too short | Neither was reached — 824 s and 998 s against a 1200 s shell and 40-minute job. The process exited on its own. |
| Database outage or corruption | Ledger audit and dashboard verification both passed in every failed run. |
| Publication gate misbehaving | It behaved exactly as designed: incomplete publication-critical work → candidate withheld → non-zero exit. This is the system working. |
| The PR #617 Team State change | It altered readiness projection only. Runs before and after the merge show the same upstream cost; run 462 failed on `d5ddb5f` and run 464 on `5be94b7`. |
| Shadow lane consuming the budget | Shadow health failed *independently* in its own job and is observation-only. Its share of the upstream block is unresolved but it is not the publication-critical blocker. |

---

## 13. Immediate mitigation options

| Option | Behaviour change | Runtime effect | Correctness risk | Publication risk | Rollback | Tests | Migration | Ops complexity | #593 interaction | Shadow | Masks? | Immediate? | Permanent? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** — raise total budget + shell timeout only | `1080 → ~2100`, shell `20m → ~40m` | Ingestion remainder ~1500 s; likely one-pass | None | None — gates unchanged | Trivial (revert env) | Budget-formula test | No | Very low | None | None | **Yes, partly** | **Yes** | **No** |
| **B** — A plus raise job timeout | Also `40 → 60` min | Same, with headroom | None | None | Trivial | Same | No | Very low | None | None | Yes | Yes | No |
| **C** — move publication-critical GameLog earlier | Reorder stages | Ingestion gets ~1000 s+ before upstream | **Medium** — must prove roster/team-assignment freshness is not a precondition for criticality classification (`sync.py:3655-3659` reads `p.roster_status`) | Low if proven | Moderate | Ordering + criticality tests | No | Medium | None | None | No | Risky alone | **Yes, as part** |
| **I** — bounded continuation mechanism | Resume remaining publication-critical pitchers in a second bounded pass without human retry | Converts today's accidental 2-pass into a governed one | Medium | Low — one publication decision retained | Moderate | Continuation + idempotency tests | No | Medium | None | None | No | Possible | Possible |

**Rejected as mitigations:** unlimited retries; reducing the 300 s reserve (H-06 shows the final phase genuinely needs ≈ 218 s); weakening publication completeness; treating dead-lettered publication-critical work as success. None of these are proposed.

---

## 14. Permanent correction options

| Option | Behaviour change | Runtime effect | Correctness risk | Publication risk | Rollback | Tests | Migration | Ops | #593 | Shadow | Masks? | Immediate? | Permanent? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **D** — incremental roster sync | Checkpoint last success; skip unchanged teams / fetch only needed roster types | **−100 to −300 s** (est.) | Medium — must not miss a roster change | Low | Moderate | Checkpoint, staleness, forced-full tests | Possibly (checkpoint table) — **any migration is a stop condition needing separate approval** | Medium | None | None | No | No | **Yes** |
| **E** — incremental/checkpointed transactions | Fetch only days since last successful window | **−small to −moderate** | Low — window is already recorded | Low | Easy | Window-advance + gap tests | Possibly | Low | None | None | No | No | **Yes** |
| **F** — prefilter GameLog candidates | Exclude pitchers who cannot have new work (e.g. no team game since last ingest) before the per-pitcher call | **Largest single win** — potentially −60 %+ of ingestion | **Medium-high** — a wrong filter silently drops real work; must fail *open* (include when unsure) | Medium if filter is wrong | Moderate | Extensive: inclusion superset proofs, boundary/doubleheader cases | No | Medium | None | None | No | No | **Yes — the core fix** |
| **G** — batch/parallelise safe source and DB work | Bounded concurrency within MLB rate limits | Moderate | Medium — ordering and rate-limit risk | Low | Moderate | Concurrency + rate-limit tests | No | Medium-high | None | None | No | No | Yes |
| **H** — split into separately observable jobs, one publication decision | Upstream job(s) + publication-critical job | Removes the shared-ceiling coupling | Medium | Low if the single gate is preserved | Complex | Workflow + gate tests | No | High | **Improves** signal separation, complements #593 | None | No | No | Yes |
| **J** — temporary mitigation + permanent efficiency correction | A/B now, then F+D+E | Immediate relief, durable fix | Managed | Low | Staged | Both sets | Only if D/E need one | Medium | Neutral | None | No | **Yes** | **Yes** |

---

## 15. Recommended sequence

### Immediate mitigation — **Option B** (raise total budget, shell timeout, and job timeout together)

- `DAILY_SYNC_TOTAL_BUDGET_SECONDS: 1080 → 2100`
- `DAILY_SYNC_COMMAND_TIMEOUT: 20m → 40m`
- `timeout-minutes: 40 → 60` (job)
- `DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS: 300` — **unchanged** (H-06: the final phase genuinely needs ≈ 218 s)
- `DAILY_SYNC_INGESTION_BUDGET_SECONDS: 720 → 1500`, so the cap stops being fiction

Satisfies every constraint: restores a reasonable one-pass probability (remainder ≈ 1500 s vs ≈ 1100 s extrapolated need); preserves fail-closed publication, ledger proof, dashboard-cache proof, and shadow zero-write; transfers no authority; removes the need for manual retries; reverts by restoring five env values.

**Measurable exit condition:** three consecutive scheduled daily runs complete with `budget_exhausted_pitchers == 0` and `publication_critical_failed == 0`, and a published candidate becomes the served snapshot. If any run still exhausts, the mitigation has failed and Option C/I is required before further ceiling increases.

**Explicitly acknowledged:** this masks the inefficiency. It buys reliability while the permanent fix is built, and it must not be treated as the fix. It also increases exposure to the growth curve in §11.3 — the ceiling will need raising again if the permanent work does not land.

### Permanent correction — **Option F, then D and E** (reduce work, not raise ceilings)

1. **F — prefilter GameLog candidates.** The biggest and most defensible win. Must be a proven *superset* filter that fails open: when candidacy cannot be established, the pitcher is included. Target: eliminate the majority of the 861 season fetches.
2. **D — incremental roster sync.** Checkpoint last success; avoid the unconditional 120-call refresh.
3. **E — checkpointed transactions.** Fetch only the unprocessed window.

**Measurable runtime targets:** upstream ≤ 200 s (from 612–628 s); cold ingestion ≤ 400 s (from ≈ 1100 s extrapolated); cold total ≤ 900 s inside a 2100 s budget, restoring genuine headroom. Then, and only then, consider lowering the ceiling again.

**Prerequisite before designing F/D/E:** capture the per-stage attribution that is missing today (§20). Building an optimisation against an unmeasured 628-second block would be guesswork.

---

## 16. Validation requirements

For the mitigation: budget-formula unit test at the new values; a test asserting the ingestion cap is reachable (i.e. `cap ≤ total − reserve − observed_upstream`); no change to publication-gate or dead-letter tests. Then three consecutive green scheduled runs with zero budget exhaustion.

For the permanent correction: superset proof for the F filter (every pitcher with genuinely new work is included); roster-checkpoint staleness and forced-full-refresh tests; transaction window-advance and gap-detection tests; unchanged publication-gate, ledger, and dashboard-cache tests; full four-shard PostgreSQL suite; and scheduled production proof over a full observation window.

---

## 17. Rollback requirements

Mitigation: revert the five environment values in `.github/workflows/baseballos-sync.yml`. No schema, data, artifact, snapshot, mode, or authority change; nothing to undo in the database.

Permanent correction: revert the PR. Checkpoint state, if a checkpoint table is introduced, must be additive and safe to ignore — a reverted build must fall back to the current full-refresh behaviour without repair. **If any of D/E requires a migration, that is a stop condition requiring separate approval.**

---

## 18. #593 interaction

**None of this belongs inside #593, and #593 must not be modified.**

#593 (OPS-001) is about *separating shadow-observer health from public-sync status*, and its separation worked perfectly here: in every failed run the shadow lane failed independently in its own job while the appearance-ledger audit and dashboard-cache verification passed within `public-sync`. That is #593's design behaving correctly.

This incident is the opposite problem: `public-sync` failed on its *own* merits — publication-critical work could not complete. The two are distinct defects that happen to appear in the same workflow.

One genuine interaction: `internal-enrichment` and `static-team-story-preview` are gated on `needs.public-sync.result == 'success'` (workflow lines 715, 798), so this runtime defect skips them repeatedly. That will pollute the scheduled-observation evidence #593 is waiting on. Fixing the runtime defect improves #593's signal quality — which is a reason to fix it promptly, not a reason to merge the two issues.

---

## 19. Authority preservation

This investigation changed nothing. No workflow dispatched, no production database session opened, no production data read directly or mutated, no snapshot rebuilt, no artifact generated. Daily and postgame lanes remain shadow; backfill remains off; the legacy writer remains authoritative; automated write and game-driven publication authority remain unapproved. Neither recommendation transfers authority: the mitigation changes only timeout values, and the permanent correction changes only which work is performed, never who may publish.

---

## 20. Remaining unknowns

1. **Per-stage attribution of the 612–628 s upstream block.** The highest-value missing measurement. Recorded in `stage_timings` and persisted in the run summary artifact; not retrievable in this environment (direct GitHub API returns HTTP 403 through the session proxy). **Capture before designing F/D/E.**
2. **Exact internals for runs `31095686315` and `31097712768`** — elapsed-before-ingestion, ingestion budget, completion counts. Run 463's ≈ 400 s upstream is derived, not measured.
3. **API-latency versus database-processing split** (H-08, unproven).
4. **The 10:00 cron → 12:01 run-creation gap.** Not explained by the evidence here; not causal (H-09).
5. **True cold ingestion duration.** Never observed to completion; ≈ 1100 s is an upper-bound extrapolation from the publication-critical-first prefix.
6. **Whether active-pitcher volume growth recently crossed the threshold.** Plausible per §11.3, unproven — no recent code change was found that increases ingestion work.
7. **Reader-visible impact of the 741/732 dead-lettered pitchers** on live Team Board and Compare reads. Assessed as degraded in §3 from first principles; not measured against production.

---

## 21. Evidence index

**Runs:** `31095686315` (462, dispatch, `d5ddb5f`, failure, 11:03:01–11:20:24) · `31097712768` (463, dispatch, `d5ddb5f`, success, 11:33:06–12:10:26) · `31099639901` (464, schedule, `5be94b7`, failure, 12:01:15–12:27:45) · `31103076829` (465, dispatch, `5be94b7`, failure, 12:49:30–13:07:01)

**Jobs:** `92603597729` (463 public-sync, daily step 11:33:21→11:47:05) · `92611884320` (464 public-sync, daily step 12:10:40→12:27:18) · `92615808735` (464 shadow-activation-health, failed independently) · `92597035957` (462 public-sync) · `92607106974` (463 internal-enrichment, 11:49:21→12:10:22)

**Log excerpts:** run 464 job `92611884320` @ 12:27:22 — `Dashboard snapshot verification passed: id=360 data_through=2026-08-05 generated_at=2026-08-06T11:45:33.037127`; run 464 job `92615808735` @ 12:27:41 — `Activation health is FAILED (reason=validator_reported_failure) … Current publication authority remains unchanged.`

**Code:** `.github/workflows/baseballos-sync.yml` lines 69–71 (concurrency), 87 (job timeout), 100–138 (daily step and budget env), 715/798 (downstream gates) · `backend/scripts/run_daily_sync.py:63-90` · `backend/services/sync.py:3423-3461` (budget formula), `:3571` (`sync_recent_logs`), `:3639` (861-pitcher scope), `:3655-3672` (criticality ordering), `:3695-3712` (caches/prefetch), `:3731-3799` (budget exhaustion + dead-letter), `:6142` (`sync_started`), `:6163-6340` (stage order) · `backend/services/roster_status_sync.py:36-41`, `:269-296`, `:301-311`, `:655-685` · `backend/services/transaction_ingestion.py:21`, `:192-216` · `backend/services/team_assignment_sync.py:341`

**Commit basis:** main `da7e39c1f888d72afb33fefd69d5dbb7be6d644f`

---

## 22. Issue recommendation

This defect is **distinct from #593** (§18) and from #590 (closed, Team State vocabulary and population). It has no existing issue.

**Recommend creating:** `[Critical][OPS-002] Prevent daily sync runtime-budget exhaustion before publication-critical completion`

**Not created by this investigation.** #593 was not closed or altered; the parent tracker was not modified.
