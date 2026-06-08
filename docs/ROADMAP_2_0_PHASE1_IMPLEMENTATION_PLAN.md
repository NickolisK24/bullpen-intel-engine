# Roadmap 2.0 — Phase 1 Implementation Plan

> **Status:** Planning and repository-analysis only. No code, migrations,
> branches, commits, or PRs are produced by this document. It converts the first
> Roadmap 2.0 milestone into a precise, ready-to-execute plan.
>
> **Scope lock.** This plan covers exactly three initiatives — **Live Board
> Discrimination**, **Follow My Team**, and **What Changed Since Yesterday** — and
> nothing else. No new engines, no recommendation expansion, no governance or
> certification work, no future-phase items.
>
> **Companion context:** [ROADMAP_2_0_PROPOSAL.md](ROADMAP_2_0_PROPOSAL.md),
> [USER_HABIT_LOOP_ANALYSIS.md](USER_HABIT_LOOP_ANALYSIS.md),
> [PRODUCT_AUDIT_JUNE_2026.md](PRODUCT_AUDIT_JUNE_2026.md).

---

## Section 1 — Executive Recommendation

### Recommended implementation order

1. **Live Board Discrimination (Initiative A)** — *first, and partly a prerequisite.*
2. **Follow My Team (Initiative B)** — *second; fully parallelizable, independent.*
3. **What Changed Since Yesterday (Initiative C)** — *third; depends on A being correct.*

### Rationale

The single most important finding of this analysis is that **A is not a tuning
problem — it is a data-freshness problem, and it is already diagnosed in the
repository.** The Availability Engine demonstrably discriminates (Monitor /
Limited / Avoid / Unavailable in a 268 / 174 / 156 / 106 split) the moment it is
fed in-window workload data; it collapses every pitcher to `Monitor` only when
the data it sees is *stale or missing*. That means A is mostly an integrity/
pipeline fix, not a model rewrite — low conceptual risk, high product payoff, and
a prerequisite for C (deltas computed on top of a flat all-`Monitor` board are
meaningless).

B is **independent of A and C entirely** — it is a frontend-only persistence
feature with zero backend dependencies and zero existing preference code to
collide with. It can be built in parallel by anyone, at any time, and it is the
cheapest retention win on the board.

C is **last because it depends on A being correct** — "what changed" is only
worth showing once the board shows real, varying statuses — and because the
honest version of C requires either reusing existing fatigue-score history or
adding one small snapshot table.

### Expected impact

| Initiative | Primary product effect | Magnitude |
| --- | --- | --- |
| A — Live Board Discrimination | The flagship surface stops lying-by-sameness; every other feature becomes worth building | ★★★★★ (unblocks everything) |
| B — Follow My Team | Converts a stateless tool into a personal daily destination | ★★★★★ (retention foundation) |
| C — What Changed | Manufactures a fresh reason to return every day | ★★★★☆ |

### Estimated effort (relative, engine already exists)

| Initiative | Effort | Shape of the work |
| --- | --- | --- |
| A | **Medium** | Mostly data-pipeline + freshness-handling + validation; little/no threshold change |
| B | **Low** | Frontend-only: local persistence + a default-route redirect + a small "change team" affordance |
| C | **Medium** | Backend delta endpoint over existing history (MVP) → optional snapshot table (v2) + one frontend surface |

### Key risks (top-level)

1. **A is misdiagnosed as a threshold problem and the team "tunes" the model.**
   This is the biggest trap. The evidence says **do not touch thresholds** — touch
   data freshness. Re-tuning to force discrimination on stale data would corrupt
   a calibrated, honest engine.
2. **B persists a team id that later becomes invalid** (trade, ID drift, empty
   roster) and produces a broken default landing. Must fail soft.
3. **C invents a heavyweight snapshot/event store** when the existing
   `FatigueScore` history + `GameLog` already support an MVP. Scope creep risk.

---

## Section 2 — Initiative A: Live Board Discrimination

### What was audited

- `backend/services/availability.py` — the classifier, `AvailabilityThresholds`,
  `_evaluate_workload`, and the data-state gating.
- `backend/services/fatigue.py` — `calculate_fatigue`, `recalculate_all_fatigue`.
- `backend/services/availability_snapshot.py` — current vs. latest-workload modes.
- `backend/services/bullpen_board.py` — board grouping / health classification.
- `backend/api/bullpen.py` — `/teams/<id>/board`, `/fatigue`, `/sync/status`.
- `backend/reports/availability_threshold_audit.md` — the decisive evidence.
- `docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md` — the governance baseline.
- `docs/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md` — prior diagnosis.

### The seven required questions, answered from evidence

**1. Why are classifications clustering?**
Because the live/current-availability path classifies **data state before
workload**. In `classify_availability` (availability.py:276–308), any pitcher
whose `data_state` is `stale` or `missing` is short-circuited to
`{availability_status: 'Monitor', confidence: 'low'}` **before
`_evaluate_workload` ever runs.** The threshold audit shows the live run produced
**704/704 `Monitor`**, with data state **640 stale + 64 missing** — i.e. *zero*
pitchers reached the workload rules at all. The clustering is not the model
choosing Monitor; it is the model *declining to judge* stale data and using
Monitor as the safe placeholder.

**2. Is this a threshold problem?** **No.** The same audit's *latest-workload
snapshot* mode — identical thresholds, identical classifier, but anchored to each
pitcher's own most recent game — produces a healthy spread: **Monitor 268 /
Limited 174 / Avoid 156 / Unavailable 106**, with **640 high-confidence**. The
thresholds discriminate correctly when fed in-window data. **Re-tuning thresholds
would be solving the wrong problem and would damage a calibrated engine.**

**3. Is this a data problem?** **Yes — this is the root cause.** Every workload
input in the live audit is empty: `pitches_yesterday`, `pitches_last_3_days`,
`pitches_last_5_days` all have median **and max = 0**, and
`appearances_last_3/5_days` are **0 for all 704 pitchers**. The reference date
(2026-06-01) sits far outside the most recent game data in the database (seed/
historical 2024–2025 logs), so the freshness window catches nothing. The board is
flat because **the database the board reads is not fresh to the current season at
the reference date** — a sync/data-currency gap, not a logic gap.

**4. Is this a workload-model problem?** **No.** The fatigue scores themselves are
well-distributed (audit: min 6, median 48.5, max 85.9). The model produces
varied scores; the availability layer simply never gets to use them on the live
path because the supporting game logs aren't in-window.

**5. Is this a roster-filtering problem?** **No, but adjacent and worth a guard.**
The 64 `missing` pitchers (no score/logs) and the starter-exclusion logic in
`bullpen_eligibility.py` are correct behavior, not the cause. Roster filtering
affects *who appears* on the board, not *why everyone who appears is Monitor*. It
should be verified (so the board isn't padded with stale starters) but it is not
the discrimination defect.

**6. What existing work already exists?**
- A fully working discriminating classifier (`availability.py`).
- A proven validation oracle: the **latest-workload snapshot mode**
  (`availability_snapshot.py`) that demonstrates correct discrimination.
- A durable sync/freshness system (`SyncRun`, `/api/bullpen/sync/status`).
- A repeatable audit script that generated `availability_threshold_audit.md`.
- A governance baseline in `AVAILABILITY_THRESHOLD_TUNING_PLAN.md`.

**7. What reports or audits already discuss this?**
- `backend/reports/availability_threshold_audit.md` — the primary evidence
  (live-all-Monitor vs. snapshot-discriminates).
- `docs/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md` §1 / §17 — independently flags
  "the live board shows all-`Monitor`" and "diagnose freshness vs. threshold."
- `backend/reports/data_freshness_validation_summary.md` — freshness-seam issues.

### Exact surfaces involved

- **Files:** `backend/services/availability.py`,
  `backend/services/availability_snapshot.py`, `backend/services/fatigue.py`,
  `backend/services/sync.py`, `backend/services/bullpen_board.py`,
  `backend/api/bullpen.py`.
- **APIs:** `GET /api/bullpen/teams/<team_id>/board`, `GET /api/bullpen/fatigue`,
  `GET /api/bullpen/sync/status`, `POST /api/bullpen/sync`,
  `POST /api/bullpen/fatigue/recalculate`.
- **DB tables:** `game_logs` (freshness source of truth), `fatigue_scores`,
  `pitchers` (roster/team), `sync_runs` (freshness metadata).
- **Frontend surfaces affected:** `TonightsBullpenBoard.jsx` /
  `BullpenBoardView.jsx` (the board), `BullpenContextSummary.jsx`,
  `dashboard/BullpenLandscape.jsx` (storylines read the same statuses),
  `AvailabilityBadge.jsx`.

### Recommended implementation sequence (do NOT implement — plan only)

1. **Confirm the data-currency gap empirically.** Query `max(game_logs.game_date)`
   in the live/deployed DB and compare to "today." Confirm the gap that the audit
   implies. This single query determines everything below.
2. **Restore data currency on the live path.** Ensure the sync pipeline is
   actually populating *current-season* game logs into the deployed DB on its
   daily cadence (the diagnosis is that it is not, leaving seed-era data). This is
   the real fix and most of the work.
3. **Make freshness handling honest and visible, not silently flattening.** When
   data genuinely is stale/offseason, the board should *say so* (an explicit
   "data is N days old — workload signals paused" state) rather than rendering a
   wall of indistinguishable `Monitor` chips that read as a live judgment.
   Distinguish "everyone is Monitor because workload says so" from "everyone is
   Monitor because we have no fresh data."
4. **Adopt the snapshot mode as the discrimination regression oracle.** Wire the
   existing latest-workload snapshot into a validation check that asserts a
   healthy status spread on known-good data, so future regressions are caught.
5. **Re-run the threshold audit against fresh data** and confirm the live path now
   matches the snapshot spread. **Only if** a real, documented skew remains after
   data is fresh should threshold tuning even be considered — and then strictly
   under `AVAILABILITY_THRESHOLD_TUNING_PLAN.md` (one variable at a time,
   before/after distributions).
6. **Verify roster/starter filtering** so the discriminating board isn't diluted
   by excluded starters or stale-ownership rows.

### Risks

- **Tuning the model instead of fixing the data** (highest risk; would break
  calibration and trust).
- **Live data simply isn't available at the reference date** (offseason / source
  gap). If so, the correct product behavior is the explicit "stale data" state
  (step 3), *not* fabricated discrimination.
- **Performance:** recomputing in-window workload per pitcher across full rosters
  on each board load; confirm query windows are indexed (the
  `ix_fatigue_pitcher_calc` and `(pitcher_id, game_date)` indexes already exist).

### Validation strategy

- **Oracle test:** live-path status distribution must approximate the snapshot-mode
  distribution on the same fresh dataset (not 100% identical — modes differ — but
  no longer 704/704 single-bucket).
- **Freshness assertion:** `/api/bullpen/sync/status` `latest_game_date` is within
  the active window after a successful sync.
- **Spot-check:** a known recently-overused reliever classifies `Avoid`/
  `Unavailable`; a known rested arm classifies `Available`.
- **Regression:** the snapshot-spread check runs in CI/test so all-`Monitor`
  cannot silently return.

### Estimated effort

**Medium.** The classifier needs little or no change; the work is data-pipeline
currency, an explicit stale-state presentation, and validation wiring. The
intellectual risk is low because the fix is already diagnosed; the operational
risk is in the sync/data layer.

---

## Section 3 — Initiative B: Follow My Team

### Repository audit findings

**1. Current navigation flow.** `frontend/src/App.jsx` uses `react-router-dom`
`BrowserRouter` with five routes; `/` renders `Dashboard` (league-wide aggregate).
There is **no concept of a "current team."** The user always lands on the league
view and must navigate inward every visit.

**2. How users currently select teams.** In `Bullpen.jsx` / `TonightsBullpenBoard.jsx`:
selection is held in component `useState` (`selectedTeam`), seeded from a `?team=`
URL param (`resolveTeamId` matches id, abbreviation, or name) and otherwise
**defaulting to `teamList[0]`** (TonightsBullpenBoard.jsx:59–64). The dashboard
`BullpenLandscape` deep-links into `?view=board&team=XYZ`. **Selection is
ephemeral — nothing survives a reload or a new session.**

**3. Components that already exist** (reusable, no new selector needed):
- `TonightsBullpenBoard.jsx` (team pills + `resolveTeamId` + selection state).
- `dashboard/BullpenLandscape.jsx` (team drilldown links).
- `getTeams()` hook/data and the team list shape (`team_id`,
  `team_abbreviation`, `team_name`).

**4. Is local storage already used elsewhere?** **No.** A full-tree search found
**zero** `localStorage`/`sessionStorage` usages in `frontend/src`. This is a
greenfield persistence feature with no existing pattern to conflict with — and no
existing pattern to reuse, so a tiny convention should be established.

**5. Existing preference systems?** **None.** No settings, no user accounts, no
profile, no cookie/preference layer. Follow My Team would be the *first*
personalization primitive in the product.

### Affected surfaces

- **Frontend (all work lives here):** `App.jsx` (default-route behavior),
  `Dashboard.jsx` (offer/honor "your team"), `Sidebar.jsx` (a "your team"
  entry/affordance), `bullpen/Bullpen.jsx` + `board/TonightsBullpenBoard.jsx`
  (seed selection from the saved team), and a small new
  `hooks/useFollowedTeam.js` (or equivalent) wrapping persistence.
- **Backend:** **none required for the MVP.** Persistence is client-side.
- **APIs:** none new; reuse `getTeams()` for validation of the stored id.
- **Persistence options:** (a) `localStorage` — recommended, zero backend, instant;
  (b) URL/shareable param — already exists, but not *sticky* across sessions;
  (c) backend user-preference — rejected for MVP (no auth system; large scope;
  contradicts "smallest useful version").

### Recommended UX (exact behavior)

1. **First visit (no followed team):** Dashboard shows the current league view,
   plus a lightweight prompt — "Follow your team for a faster bullpen check" — with
   a one-tap team picker (reuse existing team pills).
2. **Choosing a team:** stores the team id locally and immediately personalizes
   the dashboard ("PHI Bullpen Tonight" first, league context below).
3. **Return visit:** the app **opens directly to the followed team's board/
   personalized dashboard** — no re-selection. This is the core retention payoff.
4. **Changing/clearing:** a always-visible "following: PHI ▾" control (sidebar or
   dashboard header) lets the user switch or unfollow in one action.
5. **Deep links still win:** an explicit `?team=` in the URL overrides the followed
   team for that visit (shareability preserved), without overwriting the saved
   preference unless the user opts in.
6. **Fail soft:** if the stored id no longer resolves against `getTeams()`, fall
   back to the current league/default behavior and quietly clear the bad value.

### Recommended architecture

- A single source of truth: `useFollowedTeam()` hook wrapping `localStorage`
  (key e.g. `baseballos.followedTeamId`), exposing
  `{ followedTeamId, setFollowedTeam, clearFollowedTeam }`.
- **Validation on read** against the loaded team list (reuse `resolveTeamId`);
  never trust the stored id blindly.
- **Precedence order:** explicit URL `?team=` → followed team → existing
  first-team default. This layering means the feature is purely *additive* over
  today's logic.

### Implementation sequence (do NOT implement — plan only)

1. Add the `useFollowedTeam` persistence hook (local, validated).
2. Seed `TonightsBullpenBoard`/`Bullpen` selection from `followedTeam` when no
   URL param is present (extend the existing default-selection effect).
3. Add the "follow / following ▾ / unfollow" affordance (sidebar + dashboard).
4. Personalize the dashboard ordering when a team is followed.
5. Make the followed team influence the default route/landing.
6. Add fail-soft handling for stale/invalid stored ids.

### Risks

- **Stored id drift / invalid team** → broken landing. Mitigated by read-time
  validation + soft fallback.
- **Privacy/SSR/storage-disabled edge cases** (incognito, blocked storage) → must
  degrade to today's stateless behavior, never error.
- **Conflict with deep-link sharing** → resolved by the explicit precedence order.

### Validation strategy

- Unit: hook reads/writes/clears; invalid-id fallback.
- Flow: follow → reload → lands on team; unfollow → reload → lands on league;
  `?team=` overrides without clobbering the saved value.
- Manual: storage-disabled browser still works.

### Estimated effort

**Low.** Frontend-only, no schema, no API, reuses the existing selector and
team-resolution code. The highest-ROI item in the milestone per unit of effort.

---

## Section 4 — Initiative C: What Changed Since Yesterday

### Repository audit findings

**1. What historical data already exists?**
- **`fatigue_scores` is append-only history.** `recalculate_all_fatigue`
  (`fatigue.py:217–222`) and `recalculate_fatigue.py` **`db.session.add(score)`**
  a *new* `FatigueScore` row each run, stamped `calculated_at`; "current" is
  fetched via `max(calculated_at)` per pitcher. So **a time series of fatigue
  scores per pitcher already accumulates** whenever recalculation runs (i.e. each
  daily sync). This is the key enabler.
- **`game_logs` is immutable appearance history** — "did this pitcher throw last
  night, and how many pitches?" is directly answerable today.
- **`sync_runs`** records per-run snapshots (`latest_game_date`,
  `latest_fatigue_calculated_at`, counts) — useful run-level deltas.

**2. What daily deltas are possible today (no new persistence)?**
- **Workload deltas:** new appearances since yesterday and pitch-count changes,
  straight from `game_logs`.
- **Fatigue-score deltas:** per-pitcher `raw_score` / `risk_level` change between
  the two most recent `calculated_at` snapshots, from `fatigue_scores`.
- **Reconstructed availability deltas:** re-run the existing classifier against the
  prior fatigue snapshot + logs to derive "yesterday's status," then diff against
  today. Possible, but heavier and only as trustworthy as the historical inputs.

**3. What new persistence would be required?**
- **None for the MVP** (workload + fatigue-score deltas use existing tables).
- For a robust, exact **availability-status** delta over time, a small
  **daily availability snapshot table** (`pitcher_id`, `snapshot_date`,
  `availability_status`, `data_state`, `team_id`) would make status-change history
  authoritative and cheap to query — recommended as the v2, not the MVP. There is
  **no availability-status table today** (models are Pitcher, GameLog,
  FatigueScore, SyncRun, Prospect).

**4. What can be implemented immediately?** The **fatigue-score + new-appearance
delta** (questions 1–2 above) — entirely from existing tables and the existing
indexes (`ix_fatigue_pitcher_calc`, `(pitcher_id, game_date)`).

**5. What should be deferred?** Exact, persisted **availability-status** change
history (the snapshot table) and any season-long trend storytelling — valuable,
but beyond the smallest useful version and dependent on Initiative A producing
non-flat statuses first.

### Affected systems

- **Backend:** a new read-only delta service over `fatigue_scores` + `game_logs`
  (+ optional snapshot writer in v2); reuses `availability.py` if reconstructing
  status.
- **Frontend:** a "What changed for [your team]" strip on the Dashboard/board,
  ideally gated by the followed team (Initiative B synergy).
- **APIs:** one new endpoint, e.g. `GET /api/bullpen/teams/<team_id>/changes`
  (today-vs-prior deltas). No changes to existing contracts.
- **DB tables:** **MVP** reads `fatigue_scores`, `game_logs`, `pitchers`. **v2**
  adds one `availability_snapshots` table.

### MVP version (smallest useful version)

> **"Since yesterday, for your team:"**
> • who pitched last night (from `game_logs`) and how many pitches,
> • whose fatigue score moved meaningfully (Δ`raw_score` / risk-tier crossing
>   between the two latest `fatigue_scores` snapshots),
> • surfaced as 2–5 plain-language lines on the followed team's board.

This requires **no migration** and rides entirely on existing history. It is
honest (it reports *measured* workload/score changes, not predictions) and it
directly creates the "different answer every day" return reason.

### Recommended architecture

- A backend `changes` service: for a team, load the two most recent fatigue
  snapshots per pitcher + last-24–48h game logs, compute deltas, return a compact
  list with reasons.
- Frontend renders the list as a dismissible "What changed" strip, gated to the
  followed team when set (B), else the selected team.
- **v2 (deferred):** a nightly `availability_snapshots` writer (one row per active
  pitcher per day) appended at the end of the sync pipeline, enabling exact
  status-change deltas and future trend stories — additive, low-risk, but not MVP.

### Implementation sequence (do NOT implement — plan only)

1. Confirm recalculation runs (and thus snapshots accumulate) on the daily sync
   in the deployed environment — **C's data substrate depends on A's pipeline
   being healthy.**
2. Build the read-only `changes` service over existing tables (fatigue Δ +
   new appearances).
3. Add the `GET .../changes` endpoint.
4. Add the Dashboard/board "What changed" strip, gated by followed team.
5. *(v2, deferred)* add the `availability_snapshots` table + nightly writer for
   exact status deltas.

### Risks

- **Sparse/irregular history:** if recalculation didn't run yesterday (sync gap),
  "since yesterday" is ill-defined. Mitigate by comparing the two most recent
  *available* snapshots and **labeling the actual dates** ("vs. 2 days ago").
- **Flat inputs from Initiative A:** if A isn't fixed, fatigue/status deltas are
  noise on stale data. **C must not ship before A.**
- **Delta noise:** tiny score jitters read as "changes." Apply a meaningful-change
  threshold and prefer risk-tier crossings + new appearances.

### Validation strategy

- Construct a two-day fixture (snapshot N-1 and N) and assert the service reports
  exactly the seeded appearance + score-tier changes.
- Empty/sparse-history cases produce an honest "no recent change to report"
  rather than fabricated deltas.
- Date labels always reflect the real compared snapshots.

### Estimated effort

**Medium.** MVP is one backend service + one endpoint + one frontend strip over
existing data (no migration). The v2 snapshot table is a small additive increment
when exact status history is wanted.

---

## Section 5 — Dependency Analysis

```
        ┌────────────────────────────┐
        │ A — Live Board             │  (data-freshness fix; unblocks the others)
        │ Discrimination             │
        └──────────────┬─────────────┘
                       │ provides real, varying statuses + fresh history
                       ▼
        ┌────────────────────────────┐        ┌────────────────────────────┐
        │ C — What Changed           │        │ B — Follow My Team          │
        │ (needs A's fresh history & │        │ (frontend-only; depends on  │
        │  non-flat statuses)        │        │  NOTHING)                   │
        └────────────────────────────┘        └────────────────────────────┘
                       ▲                                   │
                       └────── synergy: C gates its "what changed" strip ──┘
                               to the team chosen in B
```

- **Must happen first:** **A.** Both C's value and the board's credibility depend
  on it. C is *technically* runnable on existing history, but *meaningless* until
  A makes statuses vary.
- **Fully parallel:** **B.** Zero dependency on A or C; no backend, no shared
  files of consequence. Can be built start-to-finish independently and merged any
  time. Recommended to run **concurrently** with A to compress the schedule.
- **Creates blockers:** **A blocks C.** Nothing blocks B. C's *v2* snapshot table
  depends on A's daily recalculation actually running.
- **Synergy (not a blocker):** B improves C (gate "what changed" to the followed
  team) and improves A's payoff (personalized discriminating board), but neither
  requires B.

### Recommended execution order

1. **Start A and B in parallel.** A is the critical path; B is free throughput
   that ships retention value immediately and independently.
2. **Ship B as soon as it's ready** (it doesn't wait on A).
3. **Land A's data-freshness fix + validation oracle.**
4. **Build C (MVP) on top of corrected A**, gated by B's followed team.
5. **Defer C's v2 snapshot table** until exact status-history is demanded.

---

## Section 6 — Success Criteria

### A — Live Board Discrimination

- **Functional success:** On fresh in-window data, the live `/board` status
  distribution is multi-bucket and approximates the snapshot-mode spread; no team
  renders as 100% `Monitor`; `sync/status.latest_game_date` is within the active
  window after sync.
- **Product success:** A user opening their team's board sees a believable mix of
  fresh and gassed arms that matches reality on a given night.
- **User success:** A baseball-literate user agrees with the board's calls on
  pitchers they know were recently overused or rested.
- **Failure conditions:** Still all-`Monitor` on fresh data; thresholds were
  changed to *force* spread on stale data; stale data is silently rendered as a
  live judgment instead of an explicit stale state.

### B — Follow My Team

- **Functional success:** Following a team persists across reloads/sessions; the
  app opens to that team; switching/clearing works; invalid stored ids fail soft.
- **Product success:** A returning user reaches their bullpen in zero extra clicks.
- **User success:** The product feels like *theirs* on the second visit.
- **Failure conditions:** A stale/invalid stored id breaks the landing; deep-link
  sharing is broken by persistence; storage-disabled browsers error instead of
  degrading.

### C — What Changed Since Yesterday

- **Functional success:** For a team with ≥2 days of history, the strip reports the
  correct new appearances and meaningful fatigue/score-tier changes, with honest
  date labels; sparse history yields an honest "nothing notable" rather than noise.
- **Product success:** The strip gives a genuinely different, glanceable answer on
  consecutive days.
- **User success:** A user opens the app *specifically* to see what changed
  overnight for their team.
- **Failure conditions:** Deltas computed on flat/stale data (A not fixed);
  jitter reported as change; fabricated deltas when history is missing.

---

## Section 7 — Founder Guidance (brutally honest)

**1. Which initiative creates the biggest user impact?**
**Tie, but B wins on certainty.** A is the bigger *ceiling* — without a
discriminating board nothing else is real — but A's payoff is partly hostage to a
data/infrastructure reality (is live current-season data even flowing?). **B is a
guaranteed, self-contained retention win**: it works regardless of data state and
makes the product personal on day one. A unlocks the most value; B *banks* value
with the least uncertainty.

**2. Which initiative is lowest effort?**
**B, decisively.** Frontend-only, no schema, no API, no backend, and it reuses the
existing team selector and `resolveTeamId`. There is no existing preference code
to untangle. It is the cheapest item by a wide margin.

**3. Which initiative carries the most risk?**
**A** — not technical risk (the fix is diagnosed) but **diagnosis-discipline
risk**: the standing temptation to "tune thresholds" will recur, and acting on it
would damage a calibrated engine and the trust brand. There's also a real
possibility the true blocker is upstream (live data simply isn't being synced),
which is an ops problem, not a code problem. **The risk is doing the wrong fix
confidently.**

**4. Which initiative should ship first?**
**B should ship first** (it's ready fastest and waits on nothing), while **A is
worked in parallel as the critical path.** Shipping B first puts a retention win
in users' hands immediately and buys time to fix A correctly rather than quickly.

**5. Which initiative should be tested with real users immediately?**
**B — and start now.** It's the only one that is both shippable independently and
directly observable in behavior (do followers return more than non-followers?).
Instrument "followed a team" and "returned within 48h" from day one. A and C are
worth testing too, but only *after* A's data is genuinely fresh — testing a
flat board or noise-deltas with users would teach you nothing.

---

## Final Scope Confirmation

This plan covers **only** Live Board Discrimination, Follow My Team, and What
Changed Since Yesterday. It introduces no new roadmap items, no new features
beyond these three, no engine ideas, and no future-phase work. It is an execution
plan, not an implementation — no code, migrations, branches, commits, or PRs were
created.

**The decisive takeaway:** the hardest-looking initiative (A) is the most
*already-solved* — the repository already proves the engine discriminates and
already names the cause as data freshness. Resist re-tuning; fix the data, ship B
in parallel for an immediate retention win, then layer C on top. That is the
safest, fastest, highest-confidence path through Phase 1.
