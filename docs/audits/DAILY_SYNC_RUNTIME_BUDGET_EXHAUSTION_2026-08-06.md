# Daily Sync Runtime-Budget Exhaustion — Incident Investigation, August 6, 2026

| Field | Value |
|---|---|
| Status | Point-in-time read-only production incident investigation |
| Owner | Nickolis Kacludis |
| Purpose | Determine why repeated full daily sync runs exhaust the runtime budget before publication-critical GameLog completion |
| Authority | Evidence and recommendation only; authorizes no runtime change, workflow dispatch, production access, mode change, or authority transfer |
| Retirement condition | Retain as incident evidence after the accepted repair is merged and proven in scheduled production. It does not become a competing operations manual or roadmap. |
| Repository basis | `NickolisK24/bullpen-intel-engine` main at `da7e39c1f888d72afb33fefd69d5dbb7be6d644f` |
| Investigation method | Repository source reading, GitHub Actions run/job metadata, and the complete retained `public-sync` job logs for all four runs. No production database session, no workflow dispatch, no production mutation. |
| Revision | Corrected after independent review. The first revision conflated the combined ingestion pool with the legacy GameLog budget, and recorded the run 462/463 logs as unretrievable. Both are fixed here from original log evidence. |

---

## 1. Executive verdict

The daily sync is not failing because of MLB instability, GitHub scheduling, or a database fault. It is failing because **the runtime budget is allocated in the wrong order relative to how the work is distributed**, and because the resulting remainder is far too small for the current cold workload.

Publication-critical GameLog ingestion is the *last* expensive stage in the run, and what reaches it is a remainder of a remainder. Three distinct quantities are involved, and conflating them is what made the first revision of this document wrong:

```
combined_ingestion_pool = min(720, max(1080 − elapsed_before_ingestion, 0) − 300)
shadow_lane_allocation  = combined_ingestion_pool × 0.25      # shadow mode, sync.py:2809-2814
legacy_gamelog_budget   = combined_ingestion_pool − shadow_actual_elapsed
```

Five upstream stages — team assignment, roster status, transactions, schedule-finality preflight, and slate refresh — consumed **628.5 s** and **612.2 s** in the two scheduled/dispatch failures *before* the pool was computed. The **combined ingestion pools** that remained were **151.5 s** and **167.8 s**. The game-driven shadow observer then consumed **38.753 s** and **43.170 s** of those pools, so the **legacy GameLog writer actually received 112.747 s and 124.630 s** for a stage that must evaluate **861 pitchers with one MLB season-log call each**. It completed 120 and 129 of them and dead-lettered the rest in a single batch.

Two structural facts make this a design defect rather than a tuning miss:

1. **The configured 720 s ingestion cap is unreachable in practice.** It can only bind when upstream finishes in ≤ 60 s (`1080 − 60 − 300 = 720`). Upstream has never been that fast in any observed full run. The documented cap is effectively fiction; the real pool is a remainder.
2. **The upstream stages are unconditional full refreshes.** Roster status re-fetches 30 teams × 4 roster types on every run, and team-assignment sync independently does the same — 240 roster calls per run, in every one of the four runs examined. Transactions re-fetch a fixed 7-day window on every run. Neither consults a last-success checkpoint. None of that work is publication-critical, yet all of it is spent before the publication-critical lane is allowed to start.

The "successful" recovery run did not succeed because it was correct. The evidence strongly supports that it **behaved as a warm second pass**, benefiting from durable state established by a failed run 30 minutes earlier on the same SHA. It is the single most operationally significant finding here: manual retry has become load-bearing recovery behaviour, and nobody designed it that way. The exact share of the improvement attributable to persisted state, database cache effects, source latency, and other runtime variability is **not isolated** by the available evidence — notably, the warm run still repeated the full API call structure, including all 240 roster calls and all 861 pitcher-stat calls.

**Verdict: root cause proven.** The immediate incident mechanism includes an inadequate runtime ceiling for the current workload; the durable architectural defect is work volume and ordering. Raising the ceiling alone would convert a hard failure into a slower hard failure as the active-pitcher population grows, so it is proposed only as time-boxed mitigation.

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
| Candidate 359 not published | Run `31095686315` — `Dashboard snapshot DB write completed snapshot_id=359 status=pending published=False`; snapshot **358** remained the trusted served snapshot until run `31097712768` later published 360 | **Safe** |
| Candidate 361 not published | Run `31099639901` — `snapshot_id=361 status=pending published=False`; step 13 reported served `id=360` | **Safe** |
| Candidate 362 not published | Run `31103076829` — `snapshot_id=362 status=pending published=False`; served `id=360` | **Safe** |
| Snapshot 360 still selected and served | `31099639901` job log 12:27:22: `Dashboard snapshot verification passed: id=360 data_through=2026-08-05 generated_at=2026-08-06T11:45:33.037127` | **Safe** |
| Three candidates withheld in total | 359, 361, 362 — every incomplete run failed closed without exception | **Safe** |
| Appearance ledger complete | Step 11 "Appearance ledger audit (publish eligibility)" — `success` in all three failed runs | **Safe** |
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
| **Tonight** | "Refresh schedule and warm Tonight" (step 6) **skipped** in all three failed runs — it lacks `if: always()` | **Stale.** Tonight did not refresh at all on any failed run; it ran only on the one success (114 s). |
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

### The formula — three quantities, not one

**This is the correction at the centre of this revision.** `ingestion_budget_seconds` is a *combined ingestion pool* shared by two lanes. It is not the legacy GameLog allowance, and no figure derived from it may be labelled as one.

**Step 1 — the combined pool.** `backend/services/sync.py:3423-3461`, `_daily_sync_runtime_budget()`:

```
elapsed_before_ingestion = monotonic() − sync_started            # line 3427
remaining_total          = max(1080 − elapsed_before, 0)          # lines 3428-3432
budget_after_reserve     = max(remaining_total − 300, 0)          # lines 3433-3437
ingestion_budget         = min(720, budget_after_reserve)         # lines 3440-3443   ← COMBINED POOL
```

`sync_started` is set at `sync.py:6142`, before any stage. The budget is measured from **process start**, not from cron time. It is computed at `sync.py:6294` — **before** the game-driven lane runs at `:6311`. **The shadow lane is therefore *not* part of `elapsed_before_ingestion`.** It is a consumer of the pool, not a contributor to the elapsed time that sizes it.

**Step 2 — the shadow lane's allocation.** `_game_driven_lane_time_budget()` (`sync.py:2809-2814`):

```python
if game_driven_ingestion.publication_authoritative(mode):
    return float(ingestion_budget_seconds)          # authoritative: whole pool
return float(ingestion_budget_seconds) * _game_driven_lane_budget_share()
```

`_game_driven_lane_budget_share()` (`:2791-2806`) returns `GAME_DRIVEN_INGESTION_BUDGET_SHARE` or **0.25** by default. Daily is in `shadow`, which is *not* publication-authoritative, so the lane receives **25 % of the combined pool** — a configured allocation, deliberately bounded so an observer cannot starve the lane that is still authoritative.

**Step 3 — what the legacy GameLog writer actually gets.** The lane does **not** automatically forfeit its whole allocation. After it completes, `_run_game_driven_ingestion_stage()` subtracts its *actual* elapsed time (`sync.py:2924-2927`):

```python
if ingestion_budget is not None:
    result['remaining_ingestion_budget_seconds'] = max(
        float(ingestion_budget) - elapsed, 0.0
    )
```

and that value — not the post-allocation remainder — is what `sync_recent_logs()` receives (`sync.py:6326`):

```python
time_budget_seconds=game_lane['remaining_ingestion_budget_seconds'],
```

So:

```
legacy_gamelog_budget = combined_ingestion_pool − shadow_actual_elapsed
```

When shadow finishes early it hands the unused time back. When it is budget-stopped at its allocation, the deduction approximates the 25 % share.

### Verification against observed runs — all four, from original logs

Every figure below is quoted from the `runtime_budget` and `game_driven_ingestion` blocks of the retained `public-sync` job logs.

| Run | elapsed_before | `1080 − elapsed` | `− 300` | Combined pool `min(720, ·)` | Logged pool | Shadow alloc (25 %) | Shadow actual | **Legacy GameLog budget** | GameLog actual |
|---|---|---|---|---|---|---|---|---|---|
| `31095686315` (462) | 624.9 | 455.1 | 155.1 | **155.1** | 155.1 ✔ | 38.775 | 39.004 | **116.096** | 119.5 |
| `31099639901` (464) | 628.5 | 451.5 | 151.5 | **151.5** | 151.5 ✔ | 37.875 | 38.753 | **112.747** | 116.2 |
| `31103076829` (465) | 612.2 | 467.8 | 167.8 | **167.8** | 167.8 ✔ | 41.950 | 43.170 | **124.630** | 127.0 |
| `31097712768` (463) | 361.0 | 719.0 | 419.0 | **419.0** | 419.0 ✔ | 104.750 | 56.263 | **362.737** | 162.7 |

Exact match on all four. The formula is proven, and so is the two-stage split.

Two things this table makes visible that the previous revision hid:

- **151.5 and 167.8 are combined pools.** The GameLog writer never saw those numbers. It saw 112.747 and 124.630 — roughly **26 % less** than the figures previously attributed to it.
- **Run 463 is the only run where shadow returned time.** It finished naturally in 56.263 s of a 104.750 s allocation (`budget_stop_triggered: false`), handing 48.487 s back to the GameLog writer. In all three failures shadow was **budget-stopped at its allocation** (`budget_stop_triggered: true`) — it had more work than time, and its true cold requirement is therefore unmeasured. That matters for the mitigation (§15).

### The 720 s cap is effectively fictional

The cap binds only when `1080 − elapsed − 300 ≥ 720`, i.e. **elapsed_before_ingestion ≤ 60 s**. No observed full daily run has upstream under 60 s; the three cold runs were 10× that, and even the warm run was 361.0 s. The operator-facing configuration advertises a 12-minute ingestion pool while the code delivers 2.5 minutes to two lanes combined. **This gap is itself a defect** — it makes the system's most important constraint invisible to the person tuning it.

### Conservative runtime model (real evidence only — 4 full-daily samples, no invented percentiles)

The cold GameLog requirement must be extrapolated from **GameLog-only** elapsed time. The previous revision divided completions by the *combined pool*, which included the shadow lane and produced an inflated ≈ 1100 s estimate. That estimate does not survive correction and has been withdrawn.

Two extrapolation models, both from original log values. Neither is a point estimate:

| Run | Completed | GameLog elapsed (**observed**) | of which fetch / process | Total-rate → 861 (**derived**) | Process-rate + fetch → 861 (**derived**) |
|---|---|---|---|---|---|
| `31095686315` | 115 | 119.5 s | 10.4 / 106.9 | 894.7 s | 810.8 s |
| `31099639901` | 120 | 116.2 s | 7.5 / 105.9 | 833.7 s | 767.3 s |
| `31103076829` | 129 | 127.0 s | 9.7 / 115.9 | 847.7 s | 783.3 s |
| `31097712768` (warm) | 861 | 162.7 s | 29.7 / 130.1 | — (completed) | — (completed) |

| Quantity | Value | Label |
|---|---|---|
| Observed minimum full-daily process | 824 s (run 463, warm) | **observed** |
| Observed maximum full-daily process | 998 s (run 464, cold) | **observed** |
| Observed upstream (pre-ingestion), cold | 612.2 – 628.5 s | **observed** |
| Observed upstream, warm | 361.0 s | **observed** |
| Cold GameLog requirement for 861 pitchers | **767 – 895 s** | **derived upper-bound range** |
| Warm GameLog actual for 861 pitchers | 162.7 s | **observed** |
| Final phase observed | ≈ 214.6 s (`998 − 628.5 − 38.753 − 116.2`, i.e. total less upstream, shadow, and GameLog); snapshot phase alone 110.007 / 115.394 / 110.224 / 189.735 s | **observed** |
| Implied cold total (upstream + shadow + GameLog + final) | ≈ 628 + ~40 + ~895 + ~218 ≈ **1780 s** | **derived upper bound** |

**Uncertainty, stated plainly.** The total-rate model (894.7 s worst case) divides completions by full GameLog elapsed including one-time fetch setup, so it *overstates* the marginal per-pitcher cost. The process-rate model (810.8 s worst case) separates the fetch prefix and is the better estimator, but both measure the *first* pitchers processed, which are ordered publication-critical-first (`sync.py:3665-3672`) and are the most likely to have new rows to write. The true full-population cold rate is probably faster than either. The corrected range is therefore an **upper bound of 767–895 s**, not a prediction — materially lower than the withdrawn ≈ 1100 s figure, and still far outside the 112–125 s the writer actually received.

**No observed cold-equivalent run in this incident set completed in one pass.** Four samples cannot support a stronger historical claim than that, and none is made.

---

## 5. Four-run comparison

Every cell below is quoted from the original `public-sync` job logs (jobs `92597035957`, `92603597729`, `92611884320`, `92621255398`). No cell in the budget, stage, or API groups is derived unless labelled.

| Field | `31095686315` | `31097712768` | `31099639901` | `31103076829` |
|---|---|---|---|---|
| Run number | 462 | 463 | 464 | 465 |
| Event | workflow_dispatch | workflow_dispatch | schedule | workflow_dispatch |
| Schedule expression | — | — | `0 10 * * *` | — |
| Repository SHA | `d5ddb5f` | `d5ddb5f` | `5be94b7` | `5be94b7` |
| Run start → end | 11:03:01 → 11:20:24 | 11:33:06 → 12:10:26 | 12:01:15 → 12:27:45 | 12:49:30 → 13:07:01 |
| Run duration | 17 m 23 s | 37 m 20 s | 26 m 30 s | 17 m 31 s |
| `public-sync` job | 11:03:03 → 11:20:01 | 11:33:10 → 11:49:05 | 12:10:29 → 12:27:26 | 12:49:41 → 13:06:36 |
| Daily-sync step duration | **997 s** (11:03:15→11:19:52) | **824 s** | **998 s** (12:10:40→12:27:18) | **996 s** (12:49:52→13:06:28) |
| Runner exit | 1 | 0 | 1 | 1 |
| Sync status | failure | success | failure | failure |
| **Elapsed before combined ingestion** | **624.9 s** | **361.0 s** | **628.5 s** | **612.2 s** |
| **Combined ingestion pool** | **155.1 s** | **419.0 s** | **151.5 s** | **167.8 s** |
| **Shadow configured allocation (25 %)** | **38.775 s** | **104.750 s** | **37.875 s** | **41.950 s** |
| **Shadow actual elapsed** | **39.004 s** | **56.263 s** | **38.753 s** | **43.170 s** |
| Shadow budget-stopped | **yes** | **no** (returned 48.487 s) | **yes** | **yes** |
| **Legacy GameLog budget** (pool − shadow actual) | **116.096 s** | **362.737 s** | **112.747 s** | **124.630 s** |
| **Legacy GameLog actual elapsed** | **119.5 s** | **162.7 s** | **116.2 s** | **127.0 s** |
| — of which fetch / process | 10.4 / 106.9 | 29.7 / 130.1 | 7.5 / 105.9 | 9.7 / 115.9 |
| GameLog pitchers planned | **861** | **861** | **861** | **861** |
| **GameLog completed** | **115** | **861** | **120** | **129** |
| **GameLog dead-lettered** (`budget_exhausted_pitchers`) | **746** | **0** | **741** | **732** |
| Publication-critical completed / failed / total | 115 / **303** / 418 | 861 / **0** / 418 | 120 / **298** / 418 | 129 / **289** / 418 |
| Best-effort deferred | 443 | 0 | 443 | 443 |
| `records_failed` | 746 | 0 | 741 | 732 |
| **Candidate snapshot** | **359 — pending, withheld** | **360 — published, selected, served** | 361 — pending, withheld | 362 — pending, withheld |
| **Served snapshot after run** | **358** (`data_through=2026-08-05`) | **360** | **360** | **360** |
| Snapshot / finalisation phase | **110.007 s** (partial) | **189.735 s** (success) | **115.394 s** (partial) | **110.224 s** (partial) |
| *Stage — team assignments* | 81.1 s | 45.4 s | 75.4 s | 78.9 s |
| *Stage — roster statuses* | 275.0 s | 163.4 s | 269.0 s | 268.5 s |
| *Stage — transactions* | 204.1 s | 125.5 s | 207.6 s | 201.2 s |
| *Stage — schedule-finality preflight* | 34.9 s | 14.0 s | 42.7 s | 34.4 s |
| *Stage — slate-schedule refresh* | 25.077 s | 9.987 s | 29.208 s | 24.701 s |
| *Five upstream stages, summed* | 620.2 s | 358.3 s | 623.9 s | 607.7 s |
| *Unattributed pre-ingestion overhead* | 4.7 s | 2.7 s | 4.6 s | 4.5 s |
| *Stage — fatigue* | 99.6 s | 51.1 s | 93.9 s | 98.7 s |
| **Total MLB API calls** | **472** | **1 320** | **481** | **493** |
| — `/teams/{id}/roster` | **240** | **240** | **240** | **240** |
| — `/people/{id}/stats` | **115** | **861** | **120** | **129** |
| — `/game/{id}/boxscore` | 84 | 186 | 88 | 91 |
| — `/people/{id}` | 29 | 29 | 29 | 29 |
| — `/schedule` / `/teams` / `/transactions` | 2 / 1 / 1 | 2 / 1 / 1 | 2 / 1 / 1 | 2 / 1 / 1 |
| API retries | 0 | 0 | 0 | 0 |
| Appearance-ledger audit | pass | pass | **pass** | **pass** |
| Dashboard-cache verification | **pass** (`id=358`) | pass | **pass** (`id=360 data_through=2026-08-05`) | **pass** (`id=360`) |
| Shadow activation health | fail | **pass** | **fail** (independent job) | fail |
| Tonight refresh (step 6) | skipped | **ran, 114 s** | **skipped** | skipped |
| `internal-enrichment` | skipped | **ran, 21 m 01 s** | skipped | skipped |
| `static-team-story-preview` | skipped | **ran, 3 m 05 s** | skipped | skipped |

### Differences explained

- **Run 463's 37-minute total** is not a slow sync. Its daily step was the *fastest* (824 s). The extra time is `internal-enrichment` (11:49:21 → 12:10:22), which only runs when `public-sync` succeeds.
- **The scheduled run's 9-minute job queue** (run created 12:01:15, job started 12:10:29) is the singleton concurrency lane: run 463's `internal-enrichment` held it until 12:10:22. This is a queueing artifact, not scheduling latency, and it consumed **no** internal budget.
- **Run 463's upstream was 361.0 s against 612.2–628.5 s cold** — a 251.2–267.5 s reduction, concentrated in roster statuses (−105.6 s vs run 462), transactions (−78.6 s), and team assignments (−35.7 s). Those are exactly the stages whose durable rows run 462 had already written.
- **The 10:00 cron → 12:01 run creation gap** is not explained by evidence available here. Listed as unresolved in §20. It is **not** causal (see H-09).

### Genuinely unresolved differences

- **Attribution of each upstream stage between MLB API latency and database processing.** The per-stage *totals* are now known (above); the split inside each is not. Recorded API latency accounts for only a fraction — e.g. run 464's 240 roster calls cost 13.65 s of measured latency inside a 269.0 s roster stage, and run 462's cost 18.15 s inside 275.0 s. **The overwhelming majority of upstream time is not MLB wait time**, which sharpens H-08 without resolving it.
- **The shadow lane's natural cold completion time.** It was budget-stopped in all three cold runs, so only its warm figure (56.263 s) is a true completion. This matters directly to the mitigation (§15).

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

### Measured per-stage attribution of the upstream block

This was the largest gap in the first revision. It is now closed from original log evidence — the five upstream stages account for essentially the whole pre-ingestion block, leaving only 2.7–4.7 s unattributed.

| Stage | Run 462 | Run 463 (warm) | Run 464 | Run 465 | Cold share |
|---|---|---|---|---|---|
| Team assignments | 81.1 s | 45.4 s | 75.4 s | 78.9 s | ~13 % |
| **Roster statuses** | **275.0 s** | 163.4 s | **269.0 s** | **268.5 s** | **~44 %** |
| **Transactions** | **204.1 s** | 125.5 s | **207.6 s** | **201.2 s** | **~33 %** |
| Schedule-finality preflight | 34.9 s | 14.0 s | 42.7 s | 34.4 s | ~6 % |
| Slate-schedule refresh | 25.1 s | 10.0 s | 29.2 s | 24.7 s | ~4 % |
| **Sum** | **620.2 s** | **358.3 s** | **623.9 s** | **607.7 s** | |
| Reported `elapsed_before_ingestion` | 624.9 s | 361.0 s | 628.5 s | 612.2 s | |

**Roster statuses and transactions alone are ~77 % of the cold upstream block — roughly 470–480 s per run — and neither is publication-critical.** That is the single most actionable measurement in this document and it directly ranks the permanent-correction options: D and E target 77 % of the upstream cost, and neither carries the correctness risk that reordering (Option C) does.

Note that none of the shadow lane's time appears above. Shadow runs *after* the budget is computed and is a consumer of the pool, not a contributor to `elapsed_before_ingestion`.

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

Observed per-run totals, quoted from each run's `API calls: N total, 0 retries, by endpoint: {...}` log line. **These are measurements, not estimates.**

| Endpoint | Run 462 | Run 463 (success) | Run 464 | Run 465 | Character |
|---|---|---|---|---|---|
| `/teams/{id}/roster` | **240** | **240** | **240** | **240** | full refresh, unconditional, **identical in every run** |
| `/people/{id}/stats` | 115 | **861** | 120 | 129 | one season fetch per active pitcher |
| `/game/{id}/boxscore` | 84 | 186 | 88 | 91 | box-score fallback |
| `/people/{id}` | 29 | 29 | 29 | 29 | identity resolution |
| `/schedule` | 2 | 2 | 2 | 2 | window refresh |
| `/teams` | 1 | 1 | 1 | 1 | — |
| `/transactions` | 1 | 1 | 1 | 1 | one call, 7-day window |
| **Total** | **472** | **1 320** | **481** | **493** | |
| Retries | 0 | 0 | 0 | 0 | **no source instability in any run** |

### The 120-versus-240 roster distinction

The previous revision attributed ~120 roster calls to the run as a whole. That undercounts by half, because **two independent stages each perform the full 30 × 4 sweep**:

- `roster_status_sync.build_team_roster_status_index` (`:269-296`) loops all four `ROSTER_TYPES` (`:36-41`) for every team from `_team_ids_to_sync` (`:301-311`) — **~120 calls**.
- `team_assignment_sync.build_team_assignment_index` (`:178-202`) independently loops `for roster_type in roster_types` calling `client.get_team_roster(team_id, roster_type=roster_type)` over the same `ROSTER_TYPES` — **~120 more**.

**240 roster calls per run, observed identically in all four runs — including the successful one.** Roster-status synchronisation itself accounts for only half of them.

### Totals vary sharply, and the reason matters

There is no stable "~1,000 calls per run" figure, and the previous revision should not have generalised one. Observed totals ranged from **472 to 1,320**. The variance is almost entirely `/people/{id}/stats`: a run that completes the full enumeration makes **861** of those calls, while a budget-stopped run makes only as many as it reached before exhaustion (115, 120, 129). **A failed run reports *fewer* API calls than a successful one — because it did less work, not because it was throttled or blocked.** Reading a low call total as evidence of a source problem would invert the causality.

Only the observed endpoints above are counted. No undocumented or inferred calls are included.

### Database work versus API latency

The GameLog stage is already well optimised on the read side (one prefetch for the season, one for unresolved fetch refs). The per-stage totals are now measured (§6), but the split *inside* each stage is not — and the recorded latency figures make the gap concrete rather than speculative:

| Run | Roster stage total | Measured `/teams/{id}/roster` latency | Unattributed |
|---|---|---|---|
| 462 | 275.0 s | 18.15 s | **256.9 s (93 %)** |
| 464 | 269.0 s | 13.65 s | **255.4 s (95 %)** |
| 465 | 268.5 s | 17.55 s | **251.0 s (93 %)** |
| 463 | 163.4 s | 6.11 s | **157.3 s (96 %)** |

**Over 90 % of the roster stage is not MLB wait time.** That is a strong signal that database processing and commit granularity dominate, but the logs do not separate database time from in-process computation, so H-08 remains **unproven** rather than upgraded on this basis alone. It is now a much narrower question than before.

No artificial sleeps or pacing were found in the daily path. The only sleeps observed are in the dashboard-verification retry loop (workflow lines ~416+), which runs after the sync.

---

## 8. Successful-run versus failed-run explanation

This is the crux, and the incident brief could not have reached it because it omitted run `31095686315`.

```
11:03:15  run 462  dispatch  FAILS after 997s
                             → team assignments refreshed and committed  (81.1s)
                             → roster statuses refreshed and committed  (275.0s, 240 roster calls)
                             → transactions ingested for the 7-day window (204.1s)
                             → schedule finality + slate refreshed       (34.9s + 25.1s)
                             → combined pool 155.1s; shadow took 39.004s
                             → GameLog got 116.096s, completed 115 of 861
                             → 746 dead-lettered; candidate 359 withheld; 358 stays served

          30-minute gap

11:33:21  run 463  dispatch  SUCCEEDS — daily step 824s
                             → same stages re-run, but far cheaper:
                               assignments 45.4s (−35.7), rosters 163.4s (−111.6),
                               transactions 125.5s (−78.6), finality 14.0s, slate 10.0s
                             → elapsed_before_ingestion 361.0s (−263.9s vs run 462)
                             → combined pool 419.0s; shadow finished naturally in
                               56.263s of its 104.75s allocation and returned 48.487s
                             → GameLog got 362.737s and used 162.7s for all 861
                             → snapshot 360 published, selected, served at 11:45:33
```

The successful run's daily step (824 s) was **173 s faster** than run 462's (997 s) and **174 s faster** than the scheduled failure's (998 s). The upstream block alone was **263.9 s cheaper**, and the GameLog stage processed **7.5× as many pitchers in 1.36× the time** (861 in 162.7 s versus 115 in 119.5 s) — a per-pitcher rate of 5.29/s warm against 0.96/s cold.

### What the evidence supports, and what it does not

**The evidence strongly supports that run `31097712768` benefited from durable state established by run `31095686315` and behaved as a warm second pass.** The sequence is unambiguous: same SHA, 30 minutes apart, every stage materially faster, and the stages that sped up most are exactly the ones whose durable rows the first run had already written.

**The exact share of its improvement attributable to persisted state, database cache effects, source latency, and other runtime variability is not isolated by the available evidence.** Three facts require that caution:

1. **The warm run repeated the full API call structure.** It still made all **240** roster calls and all **861** `/people/{id}/stats` calls — *more* API work than the failed run, not less. Nothing was skipped at the source layer.
2. **Measured API latency fell too.** Roster latency dropped from 18.15 s to 6.11 s for the *identical* 240 calls, which no amount of persisted database state explains. Some portion of the improvement is upstream-side or runner-side variability.
3. **Only one warm sample exists.** A single pairing cannot separate the contributions.

**Operational conclusion, which the evidence does support: manual retry has become load-bearing recovery behaviour.** Three of four runs failed; the one that succeeded did so 30 minutes after a failure that had done its durable work. Nobody designed that, it is not a control, and it must not be described as a reliable one — a retry is not guaranteed to reproduce the warm conditions. "It worked when we retried" is not evidence of health.

The two runs *after* it failed because they were cold again with respect to a fresh product day's work — and, critically, because nothing in the design carries partial progress forward deliberately. The system accidentally benefits from retries while formally treating each run as independent.

---

## 9. Hypothesis verdicts

| ID | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| **H-01** | Roster sync performs a full repeated multi-roster refresh for all 30 teams even after a recent success | **SUPPORTED** | `roster_status_sync.py:655-685` loops all teams from `_team_ids_to_sync` (`:301-311`); `build_team_roster_status_index` (`:269-296`) loops all four `ROSTER_TYPES` (`:36-41`). No checkpoint, no conditional. ~120 calls here, plus ~120 more from `team_assignment_sync.py:178-202` — **240 observed in all four runs**, including the successful one. Measured cost: 268.5–275.0 s cold, ~44 % of the upstream block. |
| **H-02** | Transaction ingestion reprocesses a broad historical range every run rather than incrementally | **SUPPORTED** | `transaction_ingestion.py:200-216` computes `start_date = end_date − 7` every run and re-fetches; `TRANSACTION_SYNC_WINDOW_DAYS = 7` (`:21`). Six of seven days are redundant. Window recorded after the fact, never read to skip. Measured cost: 201.2–207.6 s cold from a **single** API call — ~33 % of the upstream block, essentially all of it processing rather than fetching. |
| **H-03** | GameLog ingestion enumerates all 861 pitchers before cheaply excluding those with no possible new work | **SUPPORTED** | `sync.py:3639` `Pitcher.query.filter_by(active=True).all()`; per-pitcher `mlb_client.get_pitcher_game_logs(...)` at `sync.py:~3802`. Prefetches and caches (`:3695-3712`) all sit *after* the network call. No pre-filter exists. |
| **H-04** | The successful recovery benefited from durable work by an earlier partial run | **SUPPORTED, with causation qualified** | Run `31095686315` (11:03–11:20, failed) preceded run `31097712768` (11:33, success) by 30 minutes on the same SHA. Upstream fell 624.9 → 361.0 s, concentrated in the stages the first run had already committed; GameLog rate rose 0.96 → 5.29 pitchers/s. The *direction* is unambiguous. The *magnitude attributable specifically to persisted state* is not isolated: the warm run still made all 240 roster and all 861 stats calls, and its measured roster API latency also fell (18.15 → 6.11 s for identical calls), which persisted database state cannot explain. §8. |
| **H-05** | The 1080 s budget was sized from a smaller workload or warm observations and does not cover cold execution | **SUPPORTED** | Corrected cold GameLog requirement 767–895 s (GameLog-only denominators) against a legacy GameLog budget of 112.7–124.6 s, inside a 1080 s total. Implied cold total ≈ 1780 s against a 1080 s budget and 1200 s shell timeout (§4). **No observed cold-equivalent run in this incident set completed in one pass** — the sample does not support a stronger historical claim. |
| **H-06** | The 300 s reserve is reasonable, but its interaction with expensive upstream starves the publication-critical lane | **SUPPORTED** | Final phase measured ≈ 218 s, of which the snapshot phase alone was 110.007–115.394 s on failures and 189.735 s on the success. The reserve is correctly sized and was *not* over-generous — the successful run's finalisation consumed 63 % of it. The starvation comes entirely from the 612–628 s upstream. Reducing the reserve would be the wrong lever and would endanger finalisation. |
| **H-07** | Publication-critical GameLog ingestion is ordered too late relative to deferrable non-GameLog work | **SUPPORTED** | Stage table §6: four fully deferrable, non-publication-critical stages run before the pool is even computed, and the shadow observer then takes 25 % of that pool ahead of the publication-critical writer. Measured: ~470–480 s of the upstream block is roster and transaction work that is not publication-critical. |
| **H-08** | Database processing or commit granularity, not API latency, accounts for most elapsed time | **UNPROVEN — but now narrowed** | The per-stage totals are measured (§6) and the recorded MLB latency is a small fraction of them: the roster stage spent 13.65–18.15 s of measured API latency inside 268.5–275.0 s of wall clock, so **over 90 % is not source wait time**. Transactions cost 201–208 s from a *single* API call. That is consistent with the hypothesis, but the logs do not separate database time from in-process computation, so it is **not proven**. **Do not act on this hypothesis without that final measurement.** |
| **H-09** | The scheduled run's delayed start was external and did not itself cause budget exhaustion | **SUPPORTED (for the causal claim)** | The budget is measured from `sync_started = time.monotonic()` at `sync.py:6142`, i.e. process start — wall-clock delay cannot consume it. Decisively: the 12:49 manual dispatch had no scheduling delay at all and failed with near-identical numbers (612.2 s upstream / 167.8 s combined pool / 124.630 s legacy GameLog budget / 129 done / 732 dead-lettered). The 9-minute job queue is the singleton concurrency lane, not latency. The 10:00→12:01 run-creation gap itself remains unexplained (§20) but is not causal. |
| **H-10** | Repeated manual retries succeed only because prior failed runs perform durable upstream work — an accidental multi-pass pipeline | **PARTIALLY SUPPORTED** | The 462 → 463 sequence (§8) demonstrates that the successful retry **benefited from** durable work by the preceding failed run, and that manual retry has become **load-bearing recovery behaviour**. The word *only* is **not** supported: exclusive causation cannot be isolated from one warm sample, the retry repeated the full 240-roster and 861-stats call structure rather than skipping source work, and its measured API latency also improved independently of persisted state. Retained as the finding with the greatest operational significance, and explicitly **not** as evidence that retry is a reliable control. |

---

## 10. Root cause

**The five upstream stages consumed 612–628 seconds before the combined ingestion pool was calculated, leaving a pool of 151–168 seconds. The shadow observer then consumed 38.8–43.2 seconds of that pool before the remainder was passed to legacy GameLog ingestion, which therefore received 112.7–124.6 seconds for work requiring 767–895 seconds from cold.**

Three necessary conditions, all present:

1. **Ordering** — the only publication-critical source stage runs last (`sync.py:6322`, after stages at `:6180`, `:6199`, `:6215`, `:6233`, `:6264`, `:6300`).
2. **Unbounded upstream** — those stages are unconditional full refreshes with no checkpoint (`roster_status_sync.py:655`, `transaction_ingestion.py:200`). Roster statuses and transactions alone are ~77 % of the cold upstream block.
3. **Unfiltered ingestion scope** — 861 pitchers each cost one MLB season-log call, with no cheap pre-exclusion (`sync.py:3639`, `:~3802`).

Remove any one and the incident does not occur.

**Two distinct defects, and the distinction matters for the repair sequence.** The *immediate incident mechanism* includes an inadequate runtime ceiling for the current workload: even with the shadow deduction understood, no ceiling arithmetic on 1080 s can hand the GameLog writer the 767–895 s it needs after 612–628 s of upstream and a 300 s reserve. Raising the ceiling is therefore a legitimate mitigation, not merely a mask. The *durable architectural defect* is work volume and ordering: the ceiling only became binding because ~470–480 s per run is spent re-fetching and reprocessing data that has not changed. Fixing the ceiling without fixing the volume converts a hard failure into a slower hard failure as the pitcher population grows.

---

## 11. Contributing factors

1. **The 720 s ingestion cap is unreachable** (needs upstream ≤ 60 s), so the configuration misrepresents the real constraint to whoever tunes it.
2. **Accidental multi-pass recovery masked the defect.** Retries "worked", so the cold-start deficit was never measured.
3. **Growth of the active-pitcher population** silently raises ingestion cost; nothing alerts when required time crosses the available remainder. *(No evidence was found of a recent code change increasing the work — the Team State correction in PR #617 touched only readiness projection, not ingestion. Volume growth is the plausible driver but is not proven here.)*
4. **Dead-lettering is silent to live reads.** 732–746 pitchers can be deferred while Team Board and Compare read the resulting incomplete rows without any surfaced limitation.
5. **Tonight refresh is collateral damage** — step 6 lacks `if: always()`, so a sync failure also freezes Tonight.
6. **No stage-level runtime alerting.** Upstream at 628 s is a five-alarm signal that is recorded but not acted upon.
7. **The operator-facing configuration hides the number that matters.** Three quantities — combined pool, shadow allocation, and legacy GameLog remainder — are collapsed into one `ingestion_budget_seconds` in both the configuration and the run summary. Nothing anywhere reports what the publication-critical writer actually received. **This document's own first revision made exactly that error from exactly that evidence**, which is the strongest available demonstration that the reporting gap misleads readers in practice.
8. **Duplicated roster work across two stages.** `roster_status_sync` and `team_assignment_sync` each perform the full 30 × 4 sweep, and neither is aware of the other. 240 calls per run where 120 would do, before any checkpointing is even considered.

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
| Shadow lane as the *cause* of exhaustion | Shadow health failed *independently* in its own job and is observation-only. Its consumption is now measured, not unresolved: **38.753–43.170 s** on the failures, a bounded 25 % share of the combined pool. It is a real and non-trivial deduction — ~26 % of what the GameLog writer would otherwise have had, and this document no longer omits it — but eliminating it entirely would still leave only 151.5–167.8 s against a 767–895 s requirement. **It is a contributing consumer, not the cause.** |
| Insufficient ceiling as the *whole* story | Rejected as a complete account, not as a factor. The ceiling is genuinely too low (§10), but ~470–480 s per run of unconditional roster and transaction work is why it binds. Raising the ceiling alone leaves the growth curve untouched. |

---

## 13. Immediate mitigation options

| Option | Behaviour change | Runtime effect | Correctness risk | Publication risk | Rollback | Tests | Migration | Ops complexity | #593 interaction | Shadow | Masks? | Immediate? | Permanent? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** — raise total budget + shell timeout only | `1080 → ~2100`, shell `20m → ~40m` | Combined pool ≈ 1171–1188 s; GameLog worst case ≈ 879–891 s after the 25 % shadow allocation | None | None — gates unchanged | Trivial (revert config) | Budget-formula + mitigation-floor test | No | Very low | None | None | **Yes, partly** | **Yes** | **No** |
| **B** — A plus raise job timeout | Also `40 → 60` min | Same, with job-level headroom | None | None | Trivial | Same | No | Very low | None | None | Yes | Yes | No |
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

Four workflow configuration values change; the reserve does not.

| # | Value | From | To | Kind |
|---|---|---|---|---|
| 1 | `DAILY_SYNC_TOTAL_BUDGET_SECONDS` | 1080 | **2100** | step env |
| 2 | `DAILY_SYNC_COMMAND_TIMEOUT` | 20m | **40m** | step env |
| 3 | `timeout-minutes` (job) | 40 | **60** | **workflow configuration, not an environment variable** |
| 4 | `DAILY_SYNC_INGESTION_BUDGET_SECONDS` (cap) | 720 | **1500** | step env |
| — | `DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS` | 300 | **300 — unchanged** | H-06: the final phase genuinely needs ≈ 218 s |

#### What these values actually deliver — the complete arithmetic

The pool is still a remainder, and the shadow lane still takes its 25 % share first. Both facts must be carried through, and the previous revision carried neither.

```
pool          = min(1500, max(2100 − elapsed_before_ingestion, 0) − 300)
shadow_alloc  = pool × 0.25
gamelog_worst = pool − shadow_alloc            # shadow consumes its full allocation
```

| Upstream (observed) | `2100 − elapsed − 300` | `min(1500, ·)` → **pool** | Shadow allocation | **GameLog worst case** |
|---|---|---|---|---|
| 628.5 s (max observed) | 1171.5 | **1171.5 s** | 292.875 s | **878.625 s** |
| 612.2 s (min observed) | 1187.8 | **1187.8 s** | 296.950 s | **890.850 s** |

**The effective combined pool is approximately 1171.5–1187.8 seconds, not 1500.** The 1500 s cap **does not bind and is not reachable under any observed upstream timing** — it would require `elapsed_before_ingestion ≤ 300 s`, and the fastest upstream in this incident set (the warm run) was 361.0 s. Its role is to **let the full observed remainder through** and to stand as a **safety ceiling above the currently derived pool**. It is emphatically *not* the time GameLog receives.

#### Why this is provisional, and where it is marginal

Against the corrected cold GameLog requirement of **767–895 s**:

- Under the **process-rate** upper bound (810.8 s), the worst case of 878.6 s clears with **67.8 s of margin**. Adequate.
- Under the **total-rate** upper bound (894.7 s), the worst case of 878.6 s is **16.1 s short**. Not adequate.

The proposal therefore sits **astride** its own requirement, and which side it lands on depends on which extrapolation model is right — something four samples cannot settle. Two further facts push toward caution rather than optimism:

1. **Shadow's cold requirement is unmeasured.** It was budget-stopped in all three cold runs. Raising the pool to ~1180 s raises its allocation from ~40 s to ~293 s, and there is no evidence about how much of that it would actually consume. The worst case above assumes it consumes all of it, which is the only defensible assumption given `budget_stop_triggered: true`.
2. **The population grows.** 861 pitchers today; the margin shrinks with every addition.

**Recommendation: adopt Option B, but treat 2100 as provisional and require the implementation PR to validate against a derived floor before deployment.** The arithmetically safer value is **2200 s**, which is why:

```
pool          = min(1500, 2200 − 628.5 − 300) = 1271.5 s
shadow_alloc  = 317.875 s
gamelog_worst = 953.625 s   ≥ 894.7 s upper bound, margin 58.9 s
```

2200 clears the *conservative* upper bound with margin under the worst observed upstream, and costs nothing but headroom inside a 60-minute job.

One honest difference at 2200: the 1500 s cap **would** begin to bind on cheap runs, because it binds when `upstream ≤ 400 s` and the warm run's upstream was 361.0 s (`min(1500, 2200 − 361.0 − 300) = min(1500, 1539.0) = 1500`). That is benign — a warm run needs 162.7 s and would be handed 1125 s after the shadow share — and it is a ceiling behaving as a ceiling on the cheapest runs, not a constraint on the expensive ones this incident is about. It is recorded here because the whole point of this revision is that budget arithmetic must be stated exactly rather than approximately. At **2100 the cap does not bind under any observed upstream**, warm or cold.

**The implementation PR should select between 2100 and 2200 on the strength of the mitigation-floor test in §16, not on the strength of this document.**

Everything else the option must preserve, it preserves: fail-closed publication, ledger proof, dashboard-cache proof, and shadow zero-write are untouched; no authority moves; no mode changes.

**Measurable exit condition:** three consecutive scheduled daily runs complete with `budget_exhausted_pitchers == 0` and `publication_critical_failed == 0`, and a published candidate becomes the served snapshot. If any run still exhausts, the mitigation has failed and Option C/I is required before further ceiling increases.

**Explicitly acknowledged:** this masks the inefficiency. It buys reliability while the permanent fix is built, and it must not be treated as the fix. It also increases exposure to the growth curve in §11.3 — the ceiling will need raising again if the permanent work does not land.

### Permanent correction — **Option F, then D and E** (reduce work, not raise ceilings)

1. **F — prefilter GameLog candidates.** The biggest and most defensible win. Must be a proven *superset* filter that fails open: when candidacy cannot be established, the pitcher is included. Target: eliminate the majority of the 861 season fetches.
2. **D — incremental roster sync.** Checkpoint last success. Note the scope correction: this must address **both** 30 × 4 sweeps — `roster_status_sync` *and* the independent one in `team_assignment_sync` — which together are 240 unconditional calls and 268.5–275.0 s per run.
3. **E — checkpointed transactions.** Fetch only the unprocessed window. 201–208 s per run from a single API call makes this almost entirely a reprocessing win, not a fetch win.

**Ranking note, now evidence-based rather than assumed.** With per-stage attribution measured (§6), roster statuses and transactions are **~77 % of the cold upstream block (~470–480 s)**, while the GameLog stage needs 767–895 s cold. D and E therefore attack the larger *upstream* cost and carry lower correctness risk than F, whereas F attacks the larger *single* cost but must be a proven fail-open superset filter. F remains the core durable fix; D and E are the safer early wins and may reasonably land first.

**Measurable runtime targets:** upstream ≤ 200 s (from 612–628 s); cold GameLog ≤ 400 s (from the corrected 767–895 s upper-bound range); cold total ≤ 900 s inside the mitigated budget, restoring genuine headroom. Then, and only then, consider lowering the ceiling again.

**Prerequisite before designing F/D/E:** capture the per-stage attribution that is missing today (§20). Building an optimisation against an unmeasured 628-second block would be guesswork.

---

## 16. Validation requirements

#### Mitigation

The first revision proposed asserting `cap ≤ total − reserve − observed_upstream`. **That requirement is withdrawn: the proposed values fail it**, and it was never the right property anyway.

```
1500 > 2100 − 300 − 628.5  (= 1171.5)      ✗
1500 > 2100 − 300 − 612.2  (= 1187.8)      ✗
```

Making that assertion pass would force the cap *below* the derived pool, which would convert a harmless safety ceiling into an active constraint — the precise defect (a binding, invisible cap) that this incident is about. **A cap above the derived pool is the correct configuration, not a bug.**

Replace it with a **mitigation floor** on what the publication-critical writer actually receives:

1. **Floor assertion.** Under the maximum observed upstream duration, the derived combined pool, less the shadow lane's full configured allocation, must meet or exceed the selected mitigation floor:

   ```
   derived_pool          = min(cap, total − reserve − MAX_OBSERVED_UPSTREAM)
   gamelog_worst_case    = derived_pool × (1 − GAME_DRIVEN_INGESTION_BUDGET_SHARE)
   assert gamelog_worst_case >= MITIGATION_FLOOR
   ```

2. **Floor derivation — from incident evidence, not invented.** The floor is the conservative cold GameLog requirement plus an explicitly labelled safety margin:

   | Term | Value | Source |
   |---|---|---|
   | Cold GameLog upper bound, total-rate model | **894.7 s** | run 462: 861 ÷ (115 ÷ 119.5) |
   | Cold GameLog upper bound, process-rate model | 810.8 s | run 462: 861 ÷ (115 ÷ 106.9) + 10.4 |
   | **Selected requirement** (conservative of the two) | **894.7 s** | observed evidence |
   | **Safety margin** (labelled, ~6 %) | **+55.3 s** | **chosen, not derived** — covers population growth and the unmeasured cold shadow requirement |
   | **MITIGATION_FLOOR** | **950 s** | requirement + margin |

   Implied minimum total budget, under max observed upstream:
   ```
   pool_required  = 950 ÷ 0.75          = 1266.7 s
   total_required = 1266.7 + 628.5 + 300 = 2195.2 s   →  2200 s
   ```
   This is the arithmetic behind the §15 recommendation that **2100 is provisional and 2200 is the safer selection**. At 2100 the assertion yields 878.6 s and **fails** the 950 s floor; at 2200 it yields 953.6 s and passes.

3. **Separate reporting, so this conflation cannot recur.** The implementation must log and assert on five *distinct* quantities rather than one "ingestion budget": configured cap · derived combined pool · shadow configured allocation · shadow actual elapsed · remaining GameLog budget. The last of these is the number that decides whether publication-critical work completes, and it appears nowhere in today's operator-facing configuration.

4. **Timeout containment.** The shell timeout must exceed the total internal budget with explicit cleanup headroom (`2200 s + ≥ 200 s → 40 m`), and the job `timeout-minutes` must exceed the shell timeout (`40 m → 60 m`). Assert the ordering, not just the values.

5. **Unchanged:** publication-gate, dead-letter, ledger, and dashboard-cache tests. Then three consecutive green scheduled runs with zero budget exhaustion.

For the permanent correction: superset proof for the F filter (every pitcher with genuinely new work is included); roster-checkpoint staleness and forced-full-refresh tests; transaction window-advance and gap-detection tests; unchanged publication-gate, ledger, and dashboard-cache tests; full four-shard PostgreSQL suite; and scheduled production proof over a full observation window.

---

## 17. Rollback requirements

Mitigation: **revert the four changed workflow configuration values** in `.github/workflows/baseballos-sync.yml` — `DAILY_SYNC_TOTAL_BUDGET_SECONDS`, `DAILY_SYNC_COMMAND_TIMEOUT`, `DAILY_SYNC_INGESTION_BUDGET_SECONDS`, and the job's `timeout-minutes`. Three are step environment variables; **the job `timeout-minutes` is workflow configuration, not an environment variable**, and is edited in the job block rather than the step `env:` map. `DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS` is not changed and so is not reverted. No schema, data, artifact, snapshot, mode, or authority change; nothing to undo in the database.

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

**Resolved since the first revision, and no longer unknown:** per-stage attribution of the upstream block (§6); exact internals of runs `31095686315` and `31097712768`, including their elapsed-before-ingestion values, combined ingestion budgets, shadow allocation and elapsed, completion counts, snapshot identities, and API totals (§5); and the claim that these logs were unavailable through the session proxy — **they were retrievable, and the first revision was wrong to record otherwise.** Run 463's upstream is now measured at 361.0 s, not derived at ≈ 400 s.

Genuinely unresolved:

1. **API-latency versus database-processing attribution *inside* the upstream stages** (H-08). Now narrowed rather than open: over 90 % of the roster stage is not MLB wait time, and transactions cost ~200 s from a single call. The remaining question is how that non-API time divides between database work and in-process computation. **Capture before designing D/E.**
2. **Exclusive causal attribution for the warm second-pass improvement** (H-04, H-10). The direction is proven; the split between persisted state, database cache effects, source latency, and runtime variability is not isolated from one warm sample. Notably the warm run's *measured API latency* also improved for an identical call set, which persisted state alone cannot explain.
3. **The shadow lane's natural cold completion time.** Budget-stopped in all three cold runs, so only its warm completion (56.263 s) is a true measurement. This directly affects the Option B margin (§15), where the worst case assumes it consumes its full raised allocation.
4. **True cold GameLog duration.** Never observed to completion; the 767–895 s range is an upper-bound extrapolation from the publication-critical-first prefix (`sync.py:3665-3672`), which is biased toward pitchers most likely to have new rows.
5. **Whether active-pitcher volume growth recently crossed the failure threshold.** Plausible per §11.3, unproven — no recent code change was found that increases ingestion work, and no historical population series was available here.
6. **Reader-visible impact of the 741/732 dead-lettered pitchers** on live Team Board and Compare reads, per team. Assessed as degraded in §3 from first principles; not measured against production.
7. **The 10:00 cron → 12:01 run-creation gap.** Not explained by the evidence here. **Not causal** (H-09): the budget is measured from process start, and the undelayed 12:49 dispatch failed with near-identical numbers.

---

## 21. Evidence index

**Runs:** `31095686315` (462, dispatch, `d5ddb5f`, failure, 11:03:01–11:20:24) · `31097712768` (463, dispatch, `d5ddb5f`, success, 11:33:06–12:10:26) · `31099639901` (464, schedule, `5be94b7`, failure, 12:01:15–12:27:45) · `31103076829` (465, dispatch, `5be94b7`, failure, 12:49:30–13:07:01)

**Jobs (complete `public-sync` logs retrieved and read for all four):** `92597035957` (462 public-sync, daily step 11:03:15→11:19:52) · `92603597729` (463 public-sync, daily step 11:33:21→11:47:05) · `92611884320` (464 public-sync, daily step 12:10:40→12:27:18) · `92621255398` (465 public-sync, daily step 12:49:52→13:06:28) · `92615808735` (464 shadow-activation-health, failed independently) · `92607106974` (463 internal-enrichment, 11:49:21→12:10:22)

**Primary log evidence used for the corrected budget model** — each run's `runtime_budget` block, `game_driven_ingestion.allocated_budget_seconds` / `.elapsed_seconds` / `.budget_stop_triggered`, `Daily sync stage timings (s)` line, `API calls: N total … by endpoint` line, `budget_exhausted_pitchers`, `publication_critical_*`, `dashboard_snapshot_id`, and the `Daily sync post-fatigue phase completed: phase=sync_completion_snapshot_publish` elapsed value.

**Log excerpts:**
- Run 462 job `92597035957` — `"runtime_budget": {"budget_after_reserve_seconds": 155.1, "elapsed_before_ingestion_seconds": 624.9, "final_phase_reserve_seconds": 300.0, "ingestion_budget_seconds": 155.1, "remaining_total_seconds": 455.1, "stage_budget_cap_seconds": 720.0, "total_budget_seconds": 1080.0}`; `"game_driven_ingestion": {"allocated_budget_seconds": 38.775, … "elapsed_seconds": 39.004, …}`; `Dashboard snapshot DB write completed snapshot_id=359 status=pending published=False in 1175.34 ms`; `Dashboard snapshot verification passed: id=358 data_through=2026-08-05`; `API calls: 472 total, 0 retries`.
- Run 463 job `92603597729` — `"runtime_budget": {… "elapsed_before_ingestion_seconds": 361.0, "ingestion_budget_seconds": 419.0, "remaining_total_seconds": 719.0 …}`; `"allocated_budget_seconds": 104.75, … "elapsed_seconds": 56.263`, `"budget_stop_triggered": false`, `"budget_exhausted_pitchers": 0`, `"dashboard_snapshot_id": 360`; `API calls: 1320 total, 0 retries, by endpoint: {'/people/{id}/stats': {'calls': 861 …}, '/teams/{id}/roster': {'calls': 240 …} …}`.
- Run 464 job `92611884320` @ 12:27:22 — `Dashboard snapshot verification passed: id=360 data_through=2026-08-05 generated_at=2026-08-06T11:45:33.037127`; run 464 job `92615808735` @ 12:27:41 — `Activation health is FAILED (reason=validator_reported_failure) … Current publication authority remains unchanged.`

**Code:** `.github/workflows/baseballos-sync.yml` lines 69–71 (concurrency), 87 (job timeout), 100–138 (daily step and budget env), 715/798 (downstream gates) · `backend/scripts/run_daily_sync.py:63-90` · `backend/services/sync.py:2791-2806` (`_game_driven_lane_budget_share`, 25 % default), `:2809-2814` (`_game_driven_lane_time_budget`), `:2845` (pool read), `:2881` (lane budget), `:2924-2927` (**shadow actual elapsed subtracted from the pool**), `:3423-3461` (budget formula), `:3571` (`sync_recent_logs`), `:3639` (861-pitcher scope), `:3655-3672` (criticality ordering), `:3695-3712` (caches/prefetch), `:3731-3799` (budget exhaustion + dead-letter), `:6142` (`sync_started`), `:6163-6340` (stage order), `:6294` (**pool computed before the lane**), `:6311` (lane runs), `:6326` (**remainder passed to the legacy writer**) · `backend/services/roster_status_sync.py:36-41`, `:269-296`, `:301-311`, `:655-685` · `backend/services/transaction_ingestion.py:21`, `:192-216` · `backend/services/team_assignment_sync.py:178-202` (**second 30 × 4 roster sweep**), `:341`

**Commit basis:** main `da7e39c1f888d72afb33fefd69d5dbb7be6d644f`

---

## 22. Issue recommendation

This defect is **distinct from #593** (§18) and from #590 (closed, Team State vocabulary and population). It has no existing issue.

**Recommend creating:** `[Critical][OPS-002] Prevent daily sync runtime-budget exhaustion before publication-critical completion`

**Not created by this investigation.** #593 was not closed or altered; the parent tracker was not modified.
