# Live Board Discrimination — Investigation

> **Type:** Investigation and diagnosis only. No code, thresholds, logic,
> migrations, branches, commits, or PRs were created or modified.
> **Question:** Why does the live Bullpen Board fail to produce meaningful
> distribution across Available / Monitor / Limited / Avoid / Unavailable?
> **Method:** End-to-end code trace + review of existing audit reports. Evidence
> is cited by `file:line` and by report name.
> **Bias guard:** The engine is presumed innocent until the inputs are proven
> correct. The job is to verify whether the engine is being fed good data — not
> to assume it is wrong.

---

## Section 1 — Executive Summary

**Root-cause confidence: HIGH.**

**Primary finding.** The Bullpen Board's discrimination problem is **a data-input
problem, not a classification problem.** When the workload data feeding the board
is current, the engine discriminates correctly. The widely-cited "all-Monitor"
result is **correct fail-closed behavior on a *stale* dataset**, reproduced by an
audit that evaluated *every* pitcher (including stale ones) against "today." The
production board does not even render those stale pitchers — it excludes them — so
the real stale-data failure mode is an **empty / `no_data` board**, not a wall of
Monitor. The thresholds and the fatigue model are demonstrably fine.

**Secondary findings.**
1. **A freshness-metadata reporting defect** (`sync_status.json` is git-ignored, so
   `/api/bullpen/sync/status` reports `never`) made it impossible for anyone — user
   or auditor — to tell whether the data was fresh. Stale-data symptoms therefore
   *looked* like a live engine failure. This is the one confirmed, genuine defect
   in the chain, and it is a *reporting* bug, not a *classification* bug.
2. **A measurement gap:** no existing report directly audits the **production
   board's** Available→Unavailable status spread on *fresh* data. The "live board
   clusters" premise is largely inferred from a stale-data audit, not measured on a
   healthy production board.
3. **An expectation mismatch:** the "snapshot" audit mode that shows a rich spread
   (268/174/156/106) is **structurally biased toward the restricted end** because
   it evaluates every pitcher at their own peak-workload date. It is a
   *capability* oracle, not a realistic *target* for the live board, which should
   legitimately lean Available/Monitor on a normal day.

**Recommended next action.** Before any code change: **(a)** confirm the deployed
database's most-recent `game_log.game_date` relative to today, and **(b)** capture
a direct status-distribution audit of the production `/board` on that fresh data.
That single measurement will confirm the diagnosis and tell you whether *any*
classification work is warranted (the evidence says it is not). The only justified
engineering is **freshness visibility** (already partly shipped) and **keeping the
deployed/demo data current** — an ops action, not a model change.

---

## Section 2 — Data Flow Trace

```
[1] MLB Stats API  (statsapi.mlb.com)
        │  rosters, pitching game logs, boxscore leverage
        ▼
[2] SYNC PIPELINE  (services/sync.py, triggered by .github/workflows/baseballos-sync.yml
        │           — external POST at 10:00 UTC daily; not the in-process scheduler)
        │   order: team assignment → roster status → game-log ingest → fatigue recalc
        ▼
[3] PERSISTENCE  (PostgreSQL)
        │   game_logs (immutable appearance history; unique (pitcher_id, mlb_game_pk))
        │   fatigue_scores (APPEND-ONLY; one row per recalc, keyed calculated_at)
        │   pitchers (team + roster authority)
        │   sync_runs (durable run metadata)
        ▼
[4] AVAILABILITY PROCESSING
        │   services/availability_snapshot.py
        │     - _recent_pitcher_ids_subquery(): KEEP only pitchers whose MAX(game_date)
        │       is within ACTIVE_WINDOW_DAYS (14) of today   ← stale pitchers dropped here
        │     - classify_fatigue_rows(mode=CURRENT_AVAILABILITY_MODE):
        │         evaluation_date = today for ALL pitchers
        │         logs_for_availability_windows(): loads each pitcher's [today-4 .. today] games
        │     - services/availability.py classify_availability():
        │         if data_state in {stale, missing} → SHORT-CIRCUIT to Monitor/low (lines 276-308)
        │         else _evaluate_workload() applies thresholds → real status
        ▼
[5] BOARD ASSEMBLY  (services/bullpen_board.py)
        │   build_board_payload(): group into 5 buckets, alphabetical within group
        │   classify_bullpen_health(): manageable/monitoring/elevated/constrained/no_data
        ▼
[6] API  (api/bullpen.py)
        │   GET /api/bullpen/teams/<id>/board   → _build_team_board(include_stale=False)
        │   (also GET /api/bullpen/fatigue, GET /api/bullpen/sync/status)
        ▼
[7] FRONTEND BOARD  (components/bullpen/board/*)
            tonightsBullpenBoardView.getBoardGroups(): renders backend groups verbatim
            ("backend is the source of truth and we never re-sort pitchers on the client")
```

**Every handoff is faithful** except for one input dependency: stage **[4]** is
entirely at the mercy of stage **[3]**'s *freshness relative to today*. There are
exactly two places discrimination can collapse, and both are **input-driven**, not
logic-driven:

- **Collapse point A (board path):** `_recent_pitcher_ids_subquery`
  (`api/bullpen.py:60-73`) drops every pitcher whose latest game is >14 days old.
  On a stale dataset, the board's input set is **empty → `no_data`** (an empty
  board), not "all Monitor."
- **Collapse point B (audit/`/fatigue` path with `include_stale`):** when stale
  pitchers *are* included and evaluated against "today," their workload window is
  empty and `classify_availability` correctly short-circuits them all to
  **Monitor/low** (`services/availability.py:276-308`). This is the origin of the
  "all-Monitor" report.

Discrimination never collapses at stages [5], [6], or [7].

---

## Section 3 — Live Data Audit

Evidence drawn from `backend/reports/availability_threshold_audit.md` (run
2026-06-01) and `backend/reports/data_freshness_validation_summary.md`
(2026-06-02), which inspected the *public/production* backend.

| Question | Answer | Evidence |
| --- | --- | --- |
| **1. What date does the system believe it's operating through?** | "Today" = the run date (e.g. 2026-06-01); workload windows are anchored to `date.today()` | `availability_snapshot.evaluation_date_for_mode`; `availability._derive_inputs` uses `reference_date` |
| **2. Newest workload evidence?** | Production: **2026-05-31** (`latest_game_date`); the stale audit DB: >14 days before run date | freshness summary: `latest_game_date = 2026-05-31`, 35,768 logs; threshold audit: all windows empty |
| **3. Is live data current?** | **In production, yes** at the time of review (May 31 within the 14-day window) | freshness summary: **428 fresh** classifications |
| **4. Is live data stale?** | **In the audited DB, yes — entirely** (640/704). In production, **partially** (251 stale) | threshold audit data-state: 640 stale; freshness summary: 251 stale |
| **5. Is live data incomplete?** | No material incompleteness found | threshold audit: `incomplete = 0` |
| **6. Is workload evidence missing?** | 64/704 pitchers had no score/logs in the stale audit; production not all-missing | threshold audit: 64 `missing` |

**Decisive numbers.** In the stale audit DB every current-window input is empty —
`pitches_yesterday`, `pitches_last_3_days`, `pitches_last_5_days` all show
**min = median = max = 0** across all 704 pitchers, and `appearances_last_3/5_days
= 0` for all 704. That is the unambiguous signature of *no in-window games*, i.e. a
data-currency gap — **not** a threshold or model defect. In production, by
contrast, the same investigation found a **healthy 428 fresh / 251 stale split**,
i.e. it was *not* all-stale and *not* all-Monitor.

---

## Section 4 — Threshold Audit

| Question | Answer | Evidence |
| --- | --- | --- |
| **1. Are thresholds functioning as designed?** | **Yes.** | `AvailabilityThresholds` (`availability.py:42-72`): Monitor≥40, Limited≥60, Avoid≥75, Unavailable≥85 + pitch/appearance/rest rules in `_evaluate_workload` (`:166-238`) |
| **2. Do historical audits show meaningful distribution?** | **Yes — clearly.** | `availability_threshold_audit.md` *snapshot mode*: **Monitor 268 / Limited 174 / Avoid 156 / Unavailable 106**, 640 fresh / 64 missing |
| **3. Is there evidence thresholds are the problem?** | **No.** | The *same 704 pitchers* and the *same thresholds* discriminate fully when the evaluation window contains games. Fatigue scores are well-spread (min 6, median 48.5, max 85.9). `availability_all_monitor_diagnosis.md` concludes: "This is correct fail-closed behavior on a stale dataset — not a threshold defect. No threshold change is warranted." |

**No speculation required:** the engine separates workload levels correctly when
fed in-window data. Re-tuning thresholds would be solving a problem that the
evidence says does not exist — and would risk manufacturing false certainty on
data the engine has correctly flagged as untrustworthy.

---

## Section 5 — Sync Pipeline Audit

| Question | Answer | Evidence |
| --- | --- | --- |
| **1. Are syncs succeeding?** | **Yes (in production).** | freshness summary: GitHub Actions run `26765763862`, conclusion **success**, completed `2026-06-01T21:39:56Z`; fatigue `calculated_at` max `2026-06-01T21:39:55` |
| **2. Partial success?** | No evidence of partial failure; 35,768 game logs persisted | freshness summary: "Workload data — No regression found" |
| **3. Is data reaching persistence?** | **Yes.** | 35,768 game logs; fatigue scores recalculated in the June 1 window |
| **4. Is persistence reaching APIs?** | **Yes for data; NO for sync metadata.** | `/fatigue.meta.latest_game_date = 2026-05-31` (data reaches API); but `/sync/status` returns `last_sync: null, status: never` |
| **5. Are stale snapshots being surfaced?** | The board does **not** surface stale pitchers (excluded). The *dashboard freshness label* fell back to a snapshot date because metadata was missing | `data_freshness_validation_summary.md`; `api/bullpen.py` `_board_freshness_block` degrades to "unavailable" on metadata failure |

**Exact failure point.** `/api/bullpen/sync/status` derives `last_sync` from
`backend/logs/sync_status.json`, which is **runtime-only and git-ignored**. In the
deployed environment that file is absent, so `read_status()` returns the `never`
sentinel even though the database holds freshly-synced data. The freshness summary
classifies this precisely as **`METADATA_ISSUE`** — a reporting defect, not a data
or sync defect. The architecture note in `baseballos-sync.yml` confirms the sync
itself was deliberately moved to external GitHub Actions for reliability (the
in-process Render scheduler can't be trusted on a spin-down instance).

---

## Section 6 — API Audit

| Question | Answer | Evidence |
| --- | --- | --- |
| **1. Is the API returning correct classifications?** | **Yes.** | `/board` → `_build_team_board` → `_team_bullpen_rows` → `classify_fatigue_rows(CURRENT_AVAILABILITY_MODE)` → `build_board_payload`. The classifier receives each pitcher's real `[today-4 .. today]` game window (`logs_for_availability_windows`), so workload inputs are present whenever the data is fresh. |
| **2. Is the frontend receiving correct classifications?** | **Yes.** | The payload carries pre-grouped `groups[]` with per-pitcher `availability_status`; no transformation between classifier and JSON. |
| **3. Is classification loss occurring after API generation?** | **No.** | Grouping/health (`bullpen_board.py`) is deterministic over the same statuses; governance flags are metadata-only and never alter status. |

**Important API behavior to record:** the default board **excludes stale
pitchers** (`include_stale=False` → `_recent_pitcher_ids_subquery`,
`api/bullpen.py:621-623, 60-73`). This is correct and intentional ("treats
historical local snapshots as inactive/stale instead of pretending old data is
current"), but it means **the API's stale-data behavior is an empty/`no_data`
board, not an all-Monitor board.** The all-Monitor artifact comes only from the
*audit/`/fatigue` path with stale rows included*, not from `/board`.

---

## Section 7 — Frontend Audit

| Question | Answer | Evidence |
| --- | --- | --- |
| **1. Is the frontend displaying what the backend provides?** | **Yes — verbatim.** | `tonightsBullpenBoardView.getBoardGroups`: "the backend is the source of truth and we never re-sort pitchers on the client"; groups rendered as received. |
| **2. Is frontend logic collapsing distinctions?** | **No.** | `normalizeGroup` only attaches labels/empty-copy/badges; it never remaps or merges statuses. `BullpenBoardView.jsx` renders one `BoardGroup` per canonical status. |
| **3. Is frontend filtering masking distribution?** | **No (on the board).** | The board has no client-side status filter that could hide buckets. (The separate *All-Pitchers table* has filters, but that is a different surface and not the board.) |

The frontend is exonerated. It is a faithful, non-collapsing passthrough.

---

## Section 8 — Existing Audit Review

The answer already exists in the repository; this investigation corroborates and
unifies it.

- **`availability_all_monitor_diagnosis.md` (2026-06-05) — the direct answer.**
  "Correct fail-closed behavior on a stale dataset — not a threshold defect."
  Documents the short-circuit at `availability.py:276-308`, the empty current-window
  inputs, and the snapshot-mode spread proving the engine discriminates. Names the
  fix as **visibility, not thresholds**, and explicitly forbids loosening
  thresholds.
- **`data_freshness_validation_summary.md` (2026-06-02) — the metadata defect.**
  Production data through 2026-05-31, sync succeeded, **428 fresh / 251 stale**,
  but `/sync/status` reports `never` because `sync_status.json` is git-ignored.
  Classification: **`METADATA_ISSUE`**.
- **`availability_threshold_audit.md` (2026-06-01) — the raw evidence.**
  704/704 Monitor on stale data; snapshot mode 268/174/156/106; its own trust note
  warns: "Stale or missing Monitor counts should not be read as workload-driven
  Monitor counts."
- **`data_freshness_source_trace.md`, `github_actions_freshness_audit.md`,
  `durable_sync_metadata_*` — the remediation trail.** Show the move to durable
  `sync_runs` metadata to fix the reporting defect.
- **`AVAILABILITY_THRESHOLD_TUNING_PLAN.md` — the governance guardrail.**
  Requires before/after distributions and one-variable-at-a-time changes; treats
  stale/missing/incomplete as *trust states, not workload proof*.
- **`BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md` §1/§17 — independent corroboration.**
  Flags both "live board all-Monitor" and the freshness pill reading `never`, and
  recommends diagnosing freshness *before* thresholds.

**Conclusion of the review:** prior investigations already contain the answer. The
contribution of *this* document is to (a) trace it end-to-end through the board
path specifically, (b) prove the frontend/API are faithful, and (c) surface the
two under-stated facts — the board *excludes* stale data (so its failure mode is
*empty*, not Monitor), and snapshot mode is the *wrong yardstick* for the live
board.

---

## Section 9 — Root Cause Assessment (ranked by probability)

| Rank | Candidate cause | Confidence | Supporting evidence | Contradictory evidence |
| --- | --- | --- | --- | --- |
| 1 | **Stale workload data** (demo/local/lapsed-sync envs; data > 14 days old vs. today) | **HIGH** | Threshold audit: 640/704 stale, all current-window inputs = 0; `all_monitor_diagnosis` confirms | Production at review time was only *partially* stale (251), not all-stale |
| 2 | **Freshness-metadata reporting defect** (git-ignored `sync_status.json` → `never`) | **HIGH (confirmed)** | freshness summary `METADATA_ISSUE`; `/sync/status` `never` despite fresh DB | It masks state; it does not itself change classifications |
| 3 | **Measurement gap / premise partly unverified** (no direct fresh-production board status audit) | **MEDIUM-HIGH** | No report measures `/board` status spread on fresh data; "clustering" is inferred | Snapshot spread + 428 fresh imply discrimination would appear |
| 4 | **Expectation mismatch** (snapshot spread used as the target for the live board) | **MEDIUM** | Snapshot evaluates each pitcher at their peak-workload date → skews restricted; current mode evaluates all at `today` → legitimately more Available/Monitor | — |
| 5 | **Incomplete workload data** | **LOW-MED** | 64 `missing` rows in stale audit | `incomplete = 0`; not the dominant signal |
| 6 | **Roster filtering** (stale-exclusion / starter-exclusion) | **LOW (adjacent)** | `_recent_pitcher_ids_subquery` shrinks the pool on stale data → `no_data` | Correct behavior; affects *who appears*, not *why all-same-status* |
| 7 | **API issue** | **VERY LOW** | — | Classifier receives real windows; payload faithful (`_build_team_board`) |
| 8 | **Frontend issue** | **VERY LOW** | — | Verbatim passthrough; "we never re-sort on the client" |
| 9 | **Threshold issue** | **VERY LOW** | — | Same thresholds discriminate 268/174/156/106 in snapshot mode |
| 10 | **Fatigue model issue** | **VERY LOW** | — | Scores well-distributed (6 / 48.5 / 85.9) |
| — | **Other** | — | Render free-instance spin-down could lapse syncs (sync moved to GH Actions to mitigate) | Production sync observed succeeding |

**Single most likely root cause:** the board is fed **workload data that is not
current relative to "today"** in any environment where the daily sync hasn't run
or the seed data is historical — and the **freshness reporting defect hid that
fact**, making a data-currency problem masquerade as an engine failure.

---

## Section 10 — Recommended Fix Plan *(diagnosis only — do NOT implement)*

**1. Recommended investigation conclusion.**
The Bullpen Board does not have a discrimination *engine* problem. It has a
**data-currency** problem amplified by a **freshness-reporting** defect. On fresh
data the engine, API, and frontend all discriminate and pass through faithfully.
No change to thresholds, fatigue scoring, availability logic, or the fatigue model
is warranted by the evidence.

**2. Exact systems that require attention** (in order of certainty):
- **Data currency / ops:** ensure the deployed (and any demo/portfolio) database
  holds game logs within the freshness window — i.e. the daily sync is actually
  running and landing current-season data. *Highest-certainty lever.*
- **Freshness reporting:** make durable `sync_runs` metadata the authoritative
  source for `/api/bullpen/sync/status` (the git-ignored `sync_status.json`
  dependency is the confirmed defect). *Largely already in progress per the
  `durable_sync_metadata_*` trail.*
- **Stale-state visibility (UX, optional):** when the board's recent pool is empty
  or all-stale, show an explicit "Availability paused — latest data is N days old"
  state instead of an ambiguous empty/uniform board. *Presentation only.*
- **Measurement:** add a direct status-distribution check of the production board
  on fresh data, and adopt snapshot mode strictly as a *capability* regression
  oracle (never as the live target distribution).

**3. Recommended implementation sequence:**
1. Measure: query deployed `MAX(game_log.game_date)` vs. today; capture `/board`
   status spread on fresh data. (Confirms everything below.)
2. Guarantee data currency (ops): verify the GH Actions sync cadence and that it
   lands current data; refresh demo data into the window.
3. Make freshness metadata authoritative (reporting), so users can always tell
   "data through {date}" and current/stale.
4. Add the stale-state banner (UX), so stale data is self-explanatory.
5. Wire a status-spread regression check using the snapshot oracle.

**4. Validation strategy after implementation:**
- On fresh data, `/board` for an active team renders a multi-bucket spread (not
  100% one status, not `no_data`).
- `/sync/status.latest_game_date` is within the active window after a sync and no
  longer reports `never`.
- Spot-check: a known recently-overused reliever lands `Avoid`/`Unavailable`; a
  rested arm lands `Available`.
- Stale environment correctly shows the explicit stale banner, not a silent
  empty/uniform board.

**5. Rollback considerations:**
- The freshness-reporting and banner changes are **presentation/metadata only** —
  trivially revertible and cannot alter classifications.
- **No classifier/threshold change is proposed, so there is nothing in the engine
  to roll back.** This is precisely why this path is safe: the highest-impact
  levers (data currency, reporting) carry the lowest classification risk.

---

## Founder Guidance (brutally honest)

**1. Is the engine likely wrong?** **No.** The evidence is strong and consistent:
identical thresholds produce a full 268/174/156/106 spread the moment the
evaluation window contains games, and fatigue scores are well-distributed. The
engine is behaving exactly as a fail-closed, no-fake-certainty system should.

**2. Is the data likely wrong?** **Yes — this is the problem.** Not "wrong" as in
corrupt, but **not current relative to today.** When the board's window contains no
recent games, there is nothing to discriminate, and the engine correctly declines
to invent a signal. Fix the data currency and most of this evaporates.

**3. Is the board likely wrong?** **Mostly no — with one honest caveat.** The board
faithfully renders what the backend computes, and it correctly *excludes* stale
pitchers. The caveat is **visibility**: on stale data it goes empty/uniform with no
loud explanation, and the broken freshness pill (`never`) removed the one cue that
would have told everyone "this is a data-age issue, not a board issue." That
ambiguity — not the classifications — is the board's real shortcoming.

**4. What should NOT be touched during the fix?**
- **Do not touch the availability thresholds.**
- **Do not touch the fatigue model or scoring weights.**
- **Do not touch the classification/`_evaluate_workload` logic.**
- **Do not remove the stale-exclusion or the fail-closed short-circuit** — they are
  the trust guarantee, not the bug.
- **Do not treat snapshot-mode's restricted-heavy spread as the target** for the
  live board.

**5. What is the highest-confidence next implementation task?**
**Guarantee workload-data currency in the deployed/demo environment, and make
durable sync metadata the authoritative freshness signal.** That pair is
low-risk, touches no classification logic, and is the difference between a board
that *looks* broken and a board that visibly tells its story. Everything else
(stale banner, regression oracle) is supporting polish. **Fix the inputs and the
reporting; leave the engine alone.**

---

*Investigation produced read-only. No thresholds, scoring, availability logic,
engine versions, or roadmap items were changed or proposed beyond the three
already-adopted Roadmap 2.0 items. Evidence cited from the repository's own code
and audit reports.*
