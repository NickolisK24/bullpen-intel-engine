# 02 — Full Platform Audit

**BaseballOS 2026 End-of-Season Platform Audit — 2026-10-29**

This document is the complete technical, product, baseball-intelligence and operational audit. Finding IDs (`EOS-###`) refer to `03_FINDINGS_REGISTER.md`. Evidence sources are indexed in `08_AUDIT_EVIDENCE_INDEX.md`.

---

## 0. Method, access and limits

### 0.1 What was examined

| Source | How | Status |
|---|---|---|
| Repository `main` @ `0c90be9b` | Full read; shallow clone of 64 commits (2026-10-02 → 10-28) | VERIFIED |
| `feat/sync-pipeline` branch | Fetched read-only (`git fetch --depth=200`) | VERIFIED |
| `claude/baseballos-viability-audit-8ufhk9` (2026-09-24 prior audit) | Fetched read-only | VERIFIED |
| Production publications | `frontend/public/team/*` and `frontend/public/share/*`, generated from the trusted production snapshot and committed by automation, with `Snapshot-ID`, `Data-Through` and `Workflow-Run` trailers | VERIFIED (production artifacts) |
| GitHub Actions | Run list (Oct 7–28), job lists and failed-job logs, via the GitHub API | VERIFIED |
| GitHub branch metadata | `protected: false` on every branch, including `main` | VERIFIED |
| Backend tests | Local throwaway PostgreSQL 16, Python 3.11, 4 CI shards | VERIFIED |
| Frontend tests, build, render | `npm ci`, `npm test`, `vite build`, `vite preview` + Playwright screenshots at 390/768/1440 px with no backend | VERIFIED |
| Dependency audit | `pip-audit`, `npm audit` | VERIFIED |
| Competitor research | Web search; competitor pages themselves were network-blocked | Snippet-level only |
| baseballos.app, production API, statsapi.mlb.com, mlb.com, Render, Vercel, Supabase, analytics, Metricool | — | **BLOCKED** (session network policy / no credentials) |

### 0.2 Season context used

The context comes from web search; mlb.com itself was blocked.

- The 2026 regular season ended **2026-09-27**.
- **NLCS:** Milwaukee swept Los Angeles (Dodgers) 4–0.
- **ALCS:** Tampa Bay beat Cleveland 4–2; Game 6 was played 2026-10-19.
- **World Series: Milwaukee vs Tampa Bay.**
  - Game 1: 2026-10-23 (MIL 3–2).
  - The schedule continues through Games 5–7 on 10-28, 10-30 and 10-31, if necessary.
  - The status at audit time is UNVERIFIED.
  - The latest production publication covers data through **2026-10-27**: snapshot **5656**, sync run **95956**.

### 0.3 Evidence discipline

- A merged PR, passing test or roadmap checkbox is never treated as proof of production behaviour.
- Production behaviour is asserted only from the committed production artifacts and the Actions history.

---

## 1. What BaseballOS actually is today

BaseballOS is a Flask + PostgreSQL + React/Vite application.

**How it publishes:**
- A legacy daily/postgame writer runs on Render Cron, with GitHub Actions as a delayed fallback.
- The writer ingests MLB Stats API schedule, game-log, boxscore, roster and transaction data into a canonical appearance ledger.
- It derives per-reliever availability, roles and a three-level Team State.
- It publishes a league `dashboard_snapshot` about twice a day through a fail-closed gate.
- A GitHub workflow dispatched by Render then commits static Open Graph and route pages to `main`, which Vercel deploys.

**What users see:**

| Surface | Route |
|---|---|
| Tonight (home) | `/`, `/tonight` |
| League Board | `/dashboard` |
| Team Board 2.0 | `/bullpen?view=board&team=X` |
| Compare, Reliever Finder, Pitcher detail, Matchup | — |
| Stories | — |
| Methodology | — |
| Data & Trust | — |
| Search | — |
| History | — |
| Immutable Share Artifacts | `/share/{id}` |
| Static team preview stubs | `/team/{ABBR}` |

**Scale of the machinery:**

| Item | Size |
|---|---|
| Non-test backend code | 222,879 lines; 285 service modules (162,637 lines) |
| Backend tests | 10,726 collected |
| Frontend tests | 1,299 |
| Workflows | 27 |
| Alembic migrations | 87 |
| Markdown documents | 420 (123,618 lines) |

**The central fact of this audit:** the published product is currently wrong about the thing it exists to describe (§5).

---

## 2. Governing documents vs reality

### 2.1 The canonical set

| Doc | Version / date | Key binding rules relevant here |
|---|---|---|
| 01 Constitution | v1.1, Aug 14 | No prediction/betting/medical/intent (148-158); "quieter under uncertainty, never wronger" (140); founder sustainability is a product constraint (169) |
| 02 Bullpen Intelligence Standard | Header v1.4 (Aug 14), but the revision history shows v1.6 (Aug 21) | Team State is exactly Fresh/Stretched/Vulnerable (535-543); Monitor → "On Watch" (553-560); "Staleness degrades scope. It never silently degrades accuracy." (676); "A stale value is never presented as current." (685) |
| 03 Product Experience Standard | v1.5, Aug 14 | Today at `/` is the daily edition (124, 388-406) |
| 04 Platform Architecture & Ops | v1.6, Aug 14 | GitHub Actions automation (58-60); legacy writer authoritative (243-249); D-053 generated content (519-557) |
| 05 Roadmap & Decision Ledger | v5.16, Sep 4 | "No active implementation package" (9); D-001…D-058; open O-002…O-013 |
| 06 Editorial & Distribution | v1.3, Aug 14 | Banned vocabulary ("elite", 275); manual-before-automation (D-015) |
| 07 Frontend Design & Migration Spec | v2.1, Aug 17 | Self-described "not a seventh canonical authority" (26); forbids a Tonight route rename (130) |

### 2.2 Conflicts and proposed resolutions

These are consistent with the Constitution. **None is silently applied**; see `06`.

| # | Conflict | Evidence | Proposed resolution |
|---|---|---|---|
| C1 | **Today vs Tonight.** 03/07 protect Today at `/`; production made Tonight the home page and deleted Today (TN-10/TN-11) | `docs/audits/tonight-v1-root-cutover-tn-10.md:3-5`; 03:124; 07:130 | Ledger the cutover as a decision and amend 03/07 to describe Tonight as home, *with an offseason state* (DEC-07) |
| C2 | **Scheduler.** 04 says GitHub Actions; reality is Render Cron primary | `docs/current/SYNC_PIPELINE.md:52-54` | Amend 04; commit `render.yaml` (EOS-030) |
| C3 | **D-051 "no manual daily" vs governed `recovery_daily`** | 04:235 vs SYNC_PIPELINE.md:26-39 | Ledger the exception explicitly |
| C4 | **Decisions after D-058 have no ledger IDs** (Sep 21, 22, 28, 29; Oct 6) | `docs/decisions/` | Assign D-059…D-063 |
| C5 | **WHIP published** while the vocabulary says ERA is "exactly" the approved performance term | 02:641-646, 06:283 vs 02 §7D | Amend the vocabulary list |
| C6 | **04 says performance is "unwired"**; 02/05 say ERA/WHIP are live | 04:170 | Amend 04 |
| C7 | **"Six canonical documents"** vs seven in `docs/canonical/` | canonical/README:8 | Clarify (EOS-035) |
| C8 | **No standard defines Team State for idle, eliminated, or season-complete clubs** | grep: none | New Standard 02 section (DEC-01/DEC-02) — the central policy gap |
| C9 | **D-013 "no AI attribution"** vs 8 Claude-authored commits merged in PRs #905/#907/#908 | git log | Founder to reaffirm or retire D-013 |
| C10 | **"Phase 4 – Offseason Intelligence Depth"** was completed Aug 26, mid-season; no phase covers the real offseason | 05:322, 645 | The roadmap in `05` of this audit supplies one |

### 2.3 Governance health

- Roadmap 05 stopped on Sep 4. After that the following ran with no Roadmap edition:
  - CU-01..08;
  - Tonight v1;
  - role movement;
  - the truth-certification harness.
- The one-active-objective discipline (05:541) is stated but was not practised in September–October.
- `docs/current/` holds 21 point-in-time `CU_*` proof reports, against the documentation map's own classification rule.
- About 15 documents describe the same sync → publish → serve path.
- The prior viability audit (2026-09-24, unmerged) made the core recommendations this audit repeats: alerting, demand baseline, a postseason/offseason decision, indexable team pages, no HTML in git. **None was executed.** That is the most important process finding (EOS-029).

---

## 3. Public product audit

> **Limitation.** The live site was BLOCKED. This section uses:
> - the shipped code;
> - production-generated static pages;
> - local renders with no backend, which show failure states only;
> - the frontend tests' fixtures.
>
> Live first-load, live content and live navigation are **UNVERIFIED**. The checks in `07` G-6 close this.

### 3.1 Personas

| Persona | Can they get the answer? | Evidence |
|---|---|---|
| **A. First-time fan (10-second test)** | **Partially, at best.** In the offseason Tonight says "No MLB games are on tonight's slate." A newcomer landing on a team via search gets a JavaScript redirect stub. Navigation has 10 entries with emoji icons and both "Tonight" and "League Board" labels. The footer line ("a daily read on which bullpens are fresh, stretched, or vulnerable, and why") is the clearest statement of value and sits at the bottom | `frontend/src/components/tonight/tonightView.js`; `frontend/public/team/NYY/index.html`; Sidebar; screenshots |
| **B. Team-focused fan / beat writer / broadcaster** | **In season, probably yes**, with Team Board 2.0's 11 domains (UNVERIFIED live). **Today, no:** the board says the club is Vulnerable with 12–19 relievers On Watch for a club that has not played in a month | EOS-001/002 |
| **C. Senior analyst** | **No.** The decisive rule is not shown first; evidence can be irrelevant (handedness); rule definitions differ between modules (3-in-4 counts appearances in one place and days in another); the On-Watch population differs from the Team State population; postseason roles decay | EOS-005, EOS-017, EOS-018, EOS-006 |

### 3.2 Surface-by-surface

Columns:
- **Q** — the intended question;
- **Ans** — answered immediately?;
- **Correct** — correct and current?;
- **Named** — named arms and evidence?;
- **Deep** — deeper inspection available?;
- **Return** — a reason to return?;
- **Noise** — redundant or technical language?;
- **Keep** — does it deserve its place?

| Surface | Q | Ans | Correct | Named | Deep | Return | Noise | Keep |
|---|---|---|---|---|---|---|---|---|
| Tonight `/` | What matters in tonight's bullpens? | In season, yes (fixtures). Offseason: "no games" | Offseason: no season context | Yes (matchup cards) | Yes → board | In season only | "Latest publication:", "Latest sync failed before publish" (EOS-020) | Yes, plus an offseason state (EOS-M03) |
| League Board `/dashboard` | Which pens are Fresh/Stretched/Vulnerable? | Yes | **No.** 28/30 Vulnerable on 10-28 | Counts, not names | Yes | Weak | "already-published Team State reads for every expected club" | Merge into home as the 30-club strip |
| Team Board | What is this pen's state and why? | Yes, but long on mobile (prior F-09: no reliever rows in the first 390 px viewport) | **No** for idle clubs | Partially; the explanation can name the wrong cause | Yes | Yes in season | "…in this snapshot", "publication-bound" | **Centre of gravity. Fix first** |
| Compare | How do two pens differ? | Yes | Inherits EOS-001 | Partial | Yes | Low | — | Fold into the Team Board |
| Reliever Finder / Pitcher | What has this arm carried? | Yes | Mostly; roles decay in the postseason (EOS-006) | Yes | Yes | Low | — | Keep |
| Matchup | Both pens tonight | Yes in season | — | Yes | Yes | In season | — | Keep as a Tonight card |
| What Changed | What moved since yesterday? | Yes, in counts | Inherits EOS-001: idle clubs "changed" as arms crossed 14 days | Counts, not named arms (prior F-06/I02) | Partial | **The main return mechanism**, under-built | — | Keep; rebuild in named-arm terms |
| Search | Find a reliever or team | Yes (static) | — | — | — | — | — | Keep as a header search |
| History | What happened before? | Partial | Contains a month of wrong reads | Yes | Yes | Offseason value | — | Becomes the 2026 archive |
| Stories | Supported storylines | API errors render raw (EOS-020) | — | — | — | Low | Raw "API 500" | Demote; keep only factual recaps |
| Methodology | How is it computed? | Yes (static) | Defines rules that differ from code (EOS-017) | — | — | — | — | Generate from rule definitions |
| Data & Trust | Is data current? | Yes | — | — | — | — | Reads as an incident report when degraded; "Computed Not computed" | Reduce to one freshness/corrections page |
| Share `/share/{id}` | What was published then? | Yes | 747 October artifacts carry EOS-001 errors | Evidence list | Link to current | Citation | "Published BaseballOS Snapshot" | Keep; add correction banners |
| `/team/{ABBR}` stub | Team entry for search and shares | Redirects | Dated claim (wrong in October) | No | Redirect | — | "published snapshot 5656" | Replace with a real page (EOS-022) |
| Error / loading / empty states | — | Inconsistent: 3 card designs; the board says "Pick a team" when the URL names one | — | — | — | — | — | Fix (EOS-028) |

### 3.3 Responsiveness and accessibility

From local renders of 8 routes at 390, 768 and 1440 px.

**Verified good:**
- no horizontal overflow on any route at any width;
- one H1 per page;
- a skip link;
- focus moves to `main` on navigation with the H1 announced;
- 309 aria attributes;
- state colours always paired with text.

**Gaps:**
- axe runs only on Tonight (EOS-034);
- team switching is not announced.

Perceived speed: one 707 kB JS chunk (193 kB gzipped) plus 64 kB CSS, and 4 font families (prior F-27). Live timing is BLOCKED.

### 3.4 Is the interface getting simpler as intelligence deepens?

**No.**

- Team Board 2.0 added 11 domains in September.
- Navigation has 10 entries.
- There are three trust surfaces.
- The frontend still composes baseball sentences itself (EOS-019).

Meanwhile the single headline (Team State) became less reliable. The deeper layers are good; the top layer needs to become *one* answer per club.

---

## 4. Baseball intelligence audit (primary pillar)

### 4.A Active bullpen authority

| Item | Finding | Status |
|---|---|---|
| Active roster membership | The MLB active-roster flag plus bullpen eligibility (`bullpen_visibility.py:56-60`). Roster isolation to MLB clubs only (`roster_status_sync.py:936`, migration `d2e5f8a1b4c7`) | VERIFIED code |
| Population consistency | The board population and the Team State population can differ (`publication_truth_certification.py:544-568`). Washington shows 19 "On Watch", more than a roster carries (EOS-018) | VERIFIED / INFERRED cause |
| Relief vs starter classification | Official starter evidence from completed games; starter workload removed from bullpen display (fix `game_shape.py:305`) | VERIFIED code; production UNVERIFIED |
| Transactions / IL / options | Canonical transaction acquisition and qualification with many governed decisions (Aug 22 set) | VERIFIED code |
| Two-way / role-changing players | Mixed-usage handled by appearance-level classification | INFERRED |
| Postseason roster authority | The active-roster flag is used; no postseason-roster concept; eligibility flags postseason arms low-confidence (EOS-006) | VERIFIED gap |
| Affiliated vs MLB identities | The affiliate-universe failure recurred twice in September (34-team universe); fixed by consumer filters plus roster isolation | VERIFIED history |
| Historical roster reconstruction | `roster_status_snapshots` are dated; point-in-time reconstruction is possible but not exposed | VERIFIED |

### 4.B Workload and rest

| Item | Implementation | Status |
|---|---|---|
| Appearances, pitches, outs, BF | `game_logs` columns (`models/game_log.py:95-136`) | VERIFIED |
| Days since last appearance | Yes | VERIFIED |
| Back-to-back | `availability.py:109-120` | VERIFIED |
| 3-in-4 | Counts *appearances* (`availability.py:166`); the public rule counts *days* | **Inconsistent** (EOS-017) |
| 4-in-6 | Availability uses **4-in-5** (`:167`); public/spec use 4-in-6 (O-012 open) | **Inconsistent** |
| Multi-inning | 1.5 IP in roles vs 4 outs elsewhere | **Inconsistent** |
| High pitch count | Monitor at ≥15 pitches yesterday; public "high pitch" ≥25 | **Inconsistent** |
| Rolling windows | Availability: 1/3/4/5 days plus a 14-day staleness line. Public relief work: 3/7/14/30. Fatigue: 7/14. No 2-day window | Partial vs 02 |
| Team workload concentration | `workload_concentration.py`, `bullpen_concentration_context.py` | VERIFIED code |
| Off-days / recovery | The schedule-aware reference date advances across **league-wide** no-game days only (`availability_reference_date.py:99-143`) | VERIFIED; **wrong unit** for idle clubs (EOS-002) |

**Representative case verification against authoritative game records is BLOCKED.** Neither the MLB API nor the production DB was reachable. What was verified instead:

- **Code-path verification of the decisive rules.**
- **A production-artifact case trace (Washington).**
  - Last game: 2026-09-27.
  - Data-through-10-10 publication: Stretched, 15 On Watch.
  - Data-through-10-11 publication: Vulnerable, 19 On Watch.
  - That matches exactly the moment every arm's last appearance became more than 14 days old relative to the reference date.
- **Gate G-1 in `07`** defines the executable reconciliation of N sampled appearances against the MLB boxscore, to be run when access is available.

### 4.C Team State and arm reads

**Team State Contract A** (`team_operations/contracts.py:67-78`; classifier `bullpen_readiness.py:563-644`) works on status counts only:

```
clean    = Available
moderate = Monitor + Limited
severe   = Avoid + Unavailable

1. data gate (trust)                       -> data_limited
2. clean <= 2                              -> Vulnerable   (margin floor)
3. severe_share >= 1/3                     -> Vulnerable   (severity share)
4. clean_share >= 3/5 AND clean >= 5
   AND severe <= 1                         -> Fresh
5. otherwise                               -> Stretched
```

**Findings:**

1. **Unknown-as-negative (EOS-001, Critical).**
   - The `stale` and `missing` data states become Monitor and are never clean.
   - The trust gate accepts old appearances as valid observed rest, so the gate passes and a state publishes.
   - The state then reads Vulnerable.
   - The same idle arm is On Watch in the availability family and Limited Read in the pitcher-read family.
2. **Can one reliever distort Team State?**
   - One Unavailable arm alone cannot produce Vulnerable unless the pool is 3 or fewer.
   - Two severe arms block Fresh.
   - `clean <= 2` is an **absolute** count regardless of pen size, so a 13-arm pen with 2 clean arms is Vulnerable and so is a 7-arm pen.
   - **The explanation layer misattributes cause.** "One reliever is Unavailable" is ranked first even when the decisive rule was the margin floor (EOS-005).
3. **Second classifier.** The board health tiers (`bullpen_board.py:150-217`, 40% / 20%) produce the sentences next to Team State, using different thresholds (EOS-018).
4. **Calibration.**
   - In season the distribution was non-degenerate: for example, prior audit snapshot 3521 had 8 Fresh / 15 Stretched / 7 Vulnerable.
   - Churn was high: 15.6 of 30 clubs changed state per snapshot (prior F-06).
   - There is no outcome validation of whether labels predict actual non-use the next day (EOS-M05). This is not prediction; it is checking that "Unavailable" describes a real constraint.
5. **Labels describe operating context, not readiness.** The wording is descriptive, e.g. "fewer clean options available after recent work". The violation is factual, not tonal: the sentence asserts recent work that did not happen.

### 4.D Role and deployment intelligence

**How roles are derived:**
- Roles are observed, not static (`pitcher_role.py:246-429`):
  - a 45-day window with a 21-day confirmation;
  - save/hold share at least 15% with at least 2 events and at least 1 recent;
  - leverage average ≥1.5 → late, ≥1.0 → setup;
  - average ≥1.5 IP or ≥50% multi-inning outings → coverage.
- Public mapping (`pitcher_public_labels.py`): late → Trusted Arm; setup → Setup Arm; long → Coverage Arm; middle → Middle Relief Arm. Low confidence → Role Unclear.
- Entry inning is not used in role labels; it is used only by role movement (8th inning or later).

**Role movement (Oct 6):**
- adjacent 7-day windows;
- at least 3 appearances in each window;
- at least 3 known values per signal;
- a share shift of at least 1/2;
- refuses to compare across phases.

This is well-governed descriptive intelligence.

**Gap:** the regular-season-only role logs (EOS-006) undercut the postseason exactly when deployment is most scrutinized. "Who has been closing?" has no direct descriptive answer (EOS-M07).

**Verdict:** BaseballOS explains actual deployment better than static depth charts, but presents it through four role buckets. Its most useful deployment fact (late-inning entries, games finished) is not surfaced as a named hierarchy.

### 4.E Performance and context

- **ERA/WHIP:** current-active-group, regular-season only, calendar-year season (`season_era.py:94-127`; `public_team_performance.py:23`). This matches Standard 02.
- **Inherited runners:** present in the schema (`game_logs.inherited_runners*`). An authority diagnostic workflow exists, so completeness was in question (UNVERIFIED).
- **Rotation workload transferred:** short starts / rotation support pressure exist (`rotation_support_pressure.py`, `rotation_context.py`). This is a differentiator (prior audit). Unknown game types are treated as R in four modules (EOS-023).
- **Extra innings, bullpen games, schedule density:** `game_shape.py`, `schedule_context.py` exist. No public "consecutive games without an off-day" context was verified.
- **Postseason implications:** none modelled (EOS-002).

### 4.F Historical intelligence

| Item | Status |
|---|---|
| Daily snapshots | Every published snapshot retained (no retention job). Good for integrity; growth unmanaged (EOS-015) |
| Team State timeline | Exists (`team_state_history.py`, export workflow). Now contains about a month of EOS-001 reads, which need a correction overlay |
| Pitcher workload history | `game_logs` plus pitch-level data since 2026-07-04 |
| Role movement history | Since Oct 6 only |
| Roster changes | Dated snapshots plus versioned transactions |
| What Changed events | Versioned delta substrates (Aug 18/20 decisions) |
| Corrections | `stat_correction_count`, `last_stat_correction_*` on `game_logs`; artifact supersede/withdraw lifecycle exists |
| Immutability | Share artifacts carry an integrity hash; the frozen page is static |

### 4.G Missing domains

Each has a baseball question and a user benefit.

| Missing domain | Baseball question | Benefit | Priority |
|---|---|---|---|
| Season phase / club status | "Is this club still playing?" | Removes false current reads | **Mandatory** |
| Descriptive late-inning hierarchy | "Who has been getting the 9th / finishing games?" | Answers the first fan question without predicting | High |
| Consecutive-games-without-off-day context | "How long since this pen had a day off?" | Explains cumulative load in stretches | Medium |
| Velocity-under-workload (stored pitch data) | "Is this arm's velocity down after a heavy week?" | Unique descriptive signal from data already stored | Stretch (2027 mid-season) |
| Postseason workload carryover | "How much did October cost this pen?" | Offseason archive story; spring context | Medium (archive) |

Not recommended: projections, "likely available tonight", leverage-weighted composite scores. They fall outside the contract or add noise.

---

## 5. October 2026 production drift: reconstruction

From the committed `frontend/public/team/*` history (one row per distinct publication):

| Data-through | Snapshot | Fresh | Stretched | Vulnerable | Notes |
|---|---|---|---|---|---|
| 09-30 | 4157 | 21 | 7 | 2 | Wild Card round |
| 10-01 | 4222 | 25 | 5 | 0 | 18 clubs idle since 09-27 |
| 10-04 | 4363 | 23 | 5 | 2 | |
| 10-08 | 4636 | 15 | 13 | 2 | |
| 10-10 | 4731 | 6 | 15 | 9 | 13 days after 09-27 |
| **10-11** | 4764 | **3** | 8 | **19** | **14-day staleness line crossed for non-playoff clubs** |
| 10-19 | 5276 | 3 | 2 | 25 | LCS complete |
| 10-27 | 5656 | 1 (CLE) | 1 (LAD) | 28 | World Series Game 4 |

Each publication covered exactly 30 clubs (Fresh + Stretched + Vulnerable = 30 in every row). Reproduce with the loop in `08` §2.

**Why the pattern is not baseball:**
- It is monotone toward Vulnerable for clubs that are not playing.
- The flip date is identical (data-through 10-11) for all clubs that last played 09-27.
- The narrative attached is "after recent work".

**Why no system caught it:**
- the degenerate check requires 0 Fresh (EOS-004);
- the shadow health job is permanently red (EOS-007);
- no alerting exists (EOS-008).

---

## 6. Data pipeline audit

### 6.1 Flow as implemented

```
MLB Stats API  (mlb_api.py; 10 s timeout, 3 retries, backoff+jitter, Retry-After)
  -> scheduled_games    (upsert, unique team_id+game_pk; no gameType filter)
  -> game_logs          (unique pitcher_id+mlb_game_pk) via two legacy lanes:
       a) daily per-pitcher gameLog loop      (~854 requests/run; regular season only, INFERRED)
       b) postgame boxscore lane              (all game types; PBP + pitch events since 07-04)
  -> derived            (fatigue/availability, roles, Team State, read models)
  -> dashboard_snapshots candidate
       -> gates (slate coverage, appearance ledger, 30-team Team State proof)
       -> single-transaction is_published flip
  -> API serves the published snapshot (Team Board: full-row load, EOS-014)
  -> Render dispatches the generated-distribution workflow
       -> commits team/share HTML to main -> Vercel deploy  (EOS-013)
```

### 6.2 Who writes production data

- **Authoritative:** the legacy daily, morning and postgame lanes via `run_due_sync.py`.
  - Render Cron: `5 10`, `5 14`, `5 2,4,6` UTC (dashboard-managed; EOS-030).
  - The GitHub fallback is delayed 2–7 hours, and about 40% of slots are dropped (INFERRED from 65 runs in 22 days against 5 per day scheduled).
  - The generated-commit timestamps (10:13–10:16 and 04:12–04:15 UTC) confirm Render drives publication.
- **Shadow:**
  - the game-driven lane inside daily/postgame;
  - CU-08 `shadow_full_chain` every 3 minutes on Render, which can make canonical writes for allowlisted games (`continuous_execution.py:752-805`);
  - the `feat/sync-pipeline` integration runtime every 3 minutes (status UNVERIFIED; INFERRED dormant because of the migration-head mismatch).

### 6.3 Work-package truth table

| Package | Where | Status (evidence-based) |
|---|---|---|
| SP-00 Bullpen data census | `feat/sync-pipeline` only | "Contract proposal; no runtime implementation" |
| SP-01…SP-08 (control plane, queue, source observations, adaptive game state, roster/transaction authority, pregame, final reconciliation, live delta) | `feat/sync-pipeline` only | Implemented on the branch; **not merged to `main`**; only migrations were promoted; the runtime ran in shadow; development paused at 2026-09-19 |
| SP-09…SP-14 (impact, derived cohort, atomic publication, nightly closure, repair/backfill, certification) | `feat/sync-pipeline` only | Manifest: SP-14 verdict **NO-GO**; "established paths remain production authority" |
| AUDIT-R1 roster authority isolation | Branch + main-side declarations | Main-side MLB-club isolation implemented (`roster_status_sync.py:936`, migration `d2e5f8a1b4c7`) |
| AUDIT-R2 writer fencing | Branch; migration `e3f6a9b2c5d8` on main | "Implementation under validation; production certification pending". **Fences active on main** |
| AUDIT-R3 publication integrity | Branch | "**BLOCKED.** F03 is still confirmed and unfixed" |
| CU-01…CU-07 | main | Merged; shadow; CU-07 publishes to a proof target only |
| CU-08 controlled continuous execution | main + Render `*/3` | Shadow; CU-08S PARTIAL; CU-08U production replay never executed |
| OPS-002 runtime budget | main | Mitigation complete; permanent reduction not implemented (~854 gameLog calls/day) |

**Conclusion:**
- Of the sync-pipeline work, only the AUDIT-R1 main-side isolation and the migrations are in production effect.
- The fences are *active* and protect rows from `main`'s own corrections.
- Everything else is shadow or unmerged.

### 6.4 Reliability mechanisms

**Present (VERIFIED):**
- DB uniqueness on every canonical grain;
- a non-blocking advisory writer lock;
- due-window dedupe (`sync_schedule_attempts`);
- dead letters;
- postgame retry limits;
- single-transaction publication;
- fail-closed serving of the previous snapshot.

**Absent:**
- client-side rate limiting against the MLB API;
- automatic dead-letter reprocessing beyond the 7-day / 2-day lookbacks;
- distribution dispatch retry and non-fast-forward retry;
- Tonight inside the publication transaction;
- a plausibility gate (EOS-004);
- alerting (EOS-008).

### 6.5 Data-through vs baseball state

- `data_through` = the newest game date with workload. It correctly stalled at 10-19 across the Oct 20–22 off-days.
- But it is league-wide. A non-playing club inherits the league date, which then reads as that club's freshness. That is the presentation half of EOS-002.

### 6.6 Future-proof data retention

| Data class | Retained? | Recoverable later? | Action |
|---|---|---|---|
| Appearance lines (all game types via boxscore) | Yes | Yes | — |
| Pitch-level (velocity, spin, movement, location, launch) from MLB PBP | **Since 2026-07-04 only** | Yes (MLB PBP is retrievable) | Backfill Mar 26–Jul 3 2026 in the offseason (EOS-M09) |
| Raw API payloads | No ("consumed transiently") | Mostly | Archive final boxscore/PBP JSON to object storage (cheap insurance) |
| Rosters / IL (point-in-time) | Dated snapshots | Partially (`date` param) | Keep |
| Transactions | Versioned | Yes | Keep |
| Probable pitchers as announced | **No** | **No** (perishable) | Store daily (EOS-M08) |
| Live in-game states | No | No | Not needed (no live product) |
| Schedule context | Yes | Yes | — |
| Postseason 2026 | Via boxscore lane | Yes | Verify completeness in G-1 |
| Prior seasons (2025) | **No** | Yes | Optional backfill for year-over-year context (EOS-M09) |

**Irreversible-loss risks:**
1. The database itself (EOS-009).
2. Perishable probables.
3. Rows the integration runtime adopted, whose fences block correction (EOS-016).

---

## 7. Database and backend architecture

- **Migrations:**
  - 87 in a linear chain with a single head `a7c3e9f1d2b5`;
  - `flask db upgrade` from empty passes on PostgreSQL 16 (VERIFIED);
  - schema promotion uses a separate `DATABASE_MIGRATION_URL`, but role separation exists on paper only (`PRODUCTION_MIGRATION_AUTHORITY.md:162-185`).
- **Identity and integrity:**
  - `pitchers.mlb_id` unique;
  - `game_logs` unique `(pitcher_id, mlb_game_pk)` with FKs and check constraints;
  - indexes on `(pitcher_id, game_date)` and `(appearance_team_id, game_date)`;
  - `scheduled_games` unique `(team_id, game_pk)`;
  - pitch events unique `(game_pk, at_bat_index, play_event_index)`;
  - `is_published` uniqueness relies on the advisory lock, not a partial unique index (prior F-23; still the case per the backend notes).
- **Read models:**
  - league JSON snapshots (`json`, not `jsonb`) of about 16.5 MB;
  - per-team `team_public_publications` exist but are not used for serving;
  - Tonight uses an immutable `tonight_v1` row and a JSON-path projection — the right pattern, not applied to the Board (EOS-014).
- **Expensive paths:**
  - full-snapshot loads per Board, details and Compare request;
  - `max(calculated_at) GROUP BY` over the append-only `fatigue_scores` per call (`api/bullpen.py:1285`).
- **API surface:**
  - 96 routes, about 65 public;
  - admin routes token-gated (`hmac.compare_digest`, `utils/auth.py:72`);
  - production swaps view functions at startup (`public_serving_authority.py:1494-1501`), so dev/test exercise different code from production (Medium);
  - no global error handler;
  - unused public routes listed in EOS-031.
- **Dates and timezone:** the product day is America/New_York (VERIFIED). Edge cases in EOS-033.
- **Size and coupling:**
  - `sync.py` is 7,792 lines;
  - `api/bullpen.py` is 3,789;
  - 12 one-off `*_2026.py` modules (12.3k lines) and 13 `_vN` modules;
  - parallel v1/v2 Board and v1/v5 Tonight paths.
- **Scaling verdict:**
  - Data volume is small (one season of ledger rows is in the hundreds of thousands).
  - The scaling risks are read-model size per request and unbounded snapshot growth, not table size.
  - **No microservices, streaming or new infrastructure is warranted.** The needed change is per-team read rows and retention.
- **Backups and restore:** NOT documented; existence UNVERIFIED (EOS-009).

---

## 8. Frontend engineering audit

- **Stack:**
  - React + Vite + Tailwind, **JavaScript/JSX only** (0 `.ts`/`.tsx`, no tsconfig, no PropTypes);
  - type safety comes from adapter payload checks plus 1,299 tests;
  - a TypeScript migration is **not** recommended for the offseason (EOS-I06).
- **Routes (`src/App.jsx:32-57`):**
  - `/` and `/tonight` render the same page; `/today` → `/`;
  - admin, internal and private routes are statically imported into the single public bundle (EOS-021).
- **Size:**
  - largest modules: `privatePostsView.js` (1,308), `api.js` (1,236), `operatingStateReadModel.js` (865), `tonightsBullpenBoardView.js` (842), `teamBoardV2.js` (805);
  - about 2,000 lines are never imported.
- **Design spec 07 adherence:**
  - two palettes, legacy and new, mixed;
  - three error-card designs;
  - 10-item navigation versus the six lanes in 03 §5;
  - `SeasonBanner.jsx` (dead) has a pulsing "live" dot and a hardcoded '2024'.
- **Authority boundary:** client-side sentence composition and unknown → 0 (EOS-019).
- **SEO:** EOS-022.
- **Monitoring:**
  - hand-rolled Sentry reporting, active only with `VITE_SENTRY_DSN`;
  - first-party page-view beacons attach the bearer token (EOS-025).
- **Tests and build:**
  - 1,299 of 1,299 tests pass (3 need sibling backend files; about 280 s);
  - the build succeeds;
  - `dist` is 120 MB, of which 119 MB is `share/`.

---

## 9. Performance and reliability

| Item | Finding | Status |
|---|---|---|
| Home / Tonight speed | Serves an immutable row; DB timeout lead fixed | Code VERIFIED; latency BLOCKED |
| Team Board latency | Full 16.5 MB snapshot per request; never measured | EOS-014; BLOCKED |
| Pitcher page latency | Not measured | BLOCKED |
| 30-team requests | Dashboard loads the league snapshot | INFERRED heavy |
| Memory | Daily Primary OOM at 512 MiB on 2026-09-29 (`docs/audits/daily-primary-memory-incident-2026-09-29.md`) | VERIFIED history |
| Sync duration | `public-sync` ~30 s on a satisfied window; `internal-enrichment` ~18.5 min of a 20 min budget | VERIFIED (run 40656367563) |
| Cron reliability | Render: about 2 publications per day delivered Oct 2–28 with correct data-through progression. GitHub fallback: delayed and partially dropped | VERIFIED / INFERRED |
| Failed / partial publication | Fail-closed serving works by design; stuck-publication incidents Sep 11–12, Sep 25, Oct 1 froze data for 1–2 days | VERIFIED (docs) |
| Recovery after source outage | Lookbacks 7-day daily / 2-day postgame; no automatic dead-letter reprocessing | VERIFIED |
| Test reliability | Live MLB calls in tests (EOS-026) | VERIFIED |

Ranked by user consequence:
1. Wrong content (EOS-001/002).
2. Undetected outages (EOS-007/008).
3. Board latency (EOS-014).
4. Bundle weight (EOS-021).

---

## 10. Production, security and operations

See `03` EOS-009, EOS-010, EOS-011, EOS-012, EOS-025, EOS-030, EOS-032.

**Summary:**

| Area | Finding |
|---|---|
| Application security engineering | Sound |
| Operational security | Weak: public repo, unprotected `main`, production DB credential in 25 of 27 workflows, no environments, `SECRET_KEY` reused for user tokens, an Actions:write token held by Render |
| Abuse protection | None |
| Backups | Unproven |
| Staging | None |
| Alerting | None |
| Cost | GitHub minutes are free on a public repo. Render: 3 primary crons + 2 three-minute crons + web. Supabase egress already hit a P0 in September. Exact costs UNVERIFIED |

**Single points of failure, by disruption potential:**
1. Production Postgres (Critical).
2. The owner's GitHub account plus repo-wide secrets.
3. Render Cron with no alerting.
4. The MLB Stats API as the only source.
5. One web service with 2 workers and no rate limits.
6. The bot pushing to `main`, which drives Vercel.
7. The single email-provider key.
8. The CI dependency gate expiring 2026-11-13.
9. A shared admin token and `SECRET_KEY`.

**Operational work to eliminate or automate:**
- the shadow lanes (EOS-016);
- the red shadow health job (EOS-007);
- 20 one-off workflows;
- manual scheduler-health checks (→ an automated alert);
- manual incident-recovery dispatch (keep it, but document it in 04).

---

## 11. 2026 season and postseason integrity

See `04_2026_SEASON_DATA_REVIEW.md` for detail.

| Item | Finding |
|---|---|
| Postseason game classification | `game_logs.game_type` exists; the boxscore lane ingests F/D/L/W; readers default unknown to R in 4 modules |
| Postseason roster construction | Not modelled |
| Postseason bullpen workload | Counted in availability (good) |
| Postseason roles | Ignored (EOS-006) |
| Rolling windows across the season boundary | Windows span 09-27 → postseason with no phase boundary. Correct for workload; incorrect for roles |
| Eliminated clubs | Published as current (EOS-002) |
| League state with fewer than 30 active clubs | Not representable; the proof requires exactly 30 |
| Final-game handling | Postseason conditional-game retirement implemented (`schedule_absence.py`, migration `a7c3e9f1d2b5`) |
| Final 2026 publication and reconciliation | No season-close process exists (EOS-M02) |

---

## 12. Offseason product behaviour

### 12.1 What labels should do without games

| Label | Recommended offseason behaviour |
|---|---|
| Fresh / Stretched / Vulnerable | **Not published** for any club outside an active competitive window. The archive shows each club's *final* read, dated with the club's own last game date and labelled "Final 2026 read" |
| Clean Option / Watch Arm / Limited Rest / Unavailable | Not published. The archive shows each arm's final-week workload, not a current read |
| Rest counters ("days since") | Not shown as current. Shown in the archive as "last appearance: <date>" |
| Roles | Archive: "2026 observed role: Trusted Arm (late-inning entries 41, games finished 38)". Not a current role |
| What Changed | Offseason: roster and transaction changes affecting bullpens only |

### 12.2 Phase state machine (proposal; DEC-01)

```
REGULAR_SEASON --(last regular-season game final)--> POSTSEASON
POSTSEASON     --(club eliminated)--> per-club: SEASON_COMPLETE(club, final_date)
POSTSEASON     --(World Series final)--> SEASON_COMPLETE(league) -> OFFSEASON (after finalization)
OFFSEASON      --(first spring training game)--> SPRING_TRAINING
SPRING_TRAINING--(first regular-season game day)--> OPENING -> REGULAR_SEASON

Per-club status:  active | eliminated(date) | not_qualified(date) | champion
Current reads:    published only when phase in {REGULAR_SEASON, POSTSEASON}
                  AND club status = active
Workload windows: game_type allowlist per phase
                  (R; R+F/D/L/W; never S/E)
                  and reset the "staleness" concept at the phase start
                  (no arm is "stale" on Opening Day)
```

### 12.3 The smallest useful offseason product

1. **Home:**
   - "The 2026 season is complete. Champion: <club>." — filled in from data;
   - the 30-club archive strip;
   - an offseason bullpen transactions feed.
2. **Per club `/team/{ABBR}`** — a 2026 bullpen season summary:
   - total relief innings and pitches;
   - workload concentration (top-4 share);
   - multi-day patterns (back-to-backs, 3-in-4 counts);
   - observed role movement timeline;
   - the Team State timeline (corrected);
   - postseason workload where applicable;
   - current 40-man relievers added or removed since the season ended.
3. **Per reliever:** a 2026 season line plus a workload calendar.
4. **Next-season status:** "Spring training games begin <date>; current bullpen reads resume on Opening Day <date>."

All of this is built from existing data; no new ingestion is required.

---

## 13. Competitive and market audit

Competitor pages were network-blocked; this rests on search-result snippets. Details and sources: `08` §4.

| Capability | MLB.com | Savant | FanGraphs / RosterResource | B-Ref | Trackers (Inside the Pen, RotoWire, Closer Monkey, Tony's Picks) | **BaseballOS** |
|---|---|---|---|---|---|---|
| Per-arm last-N-days usage grid | News only | No | **Yes** (6-day grid, "High Usage Alert") | Game logs | **Yes** | Yes |
| Closer / role hierarchy | Depth chart | No | **Yes** | No | **Yes** (fantasy) | Role buckets; no named hierarchy |
| Team-level bullpen state | No | No | No | No | Betting "fatigue score" (Tony's Picks) | **Yes, descriptive (unique)** |
| Evidence and data-through date per claim | No | No | No | No | No | **Yes (unique)** |
| Permanent citable snapshot | No | No | No | Partly (static pages) | No | **Yes (unique)** |
| Pitch quality | Gameday | **Yes** | Yes | Partial | No | Data stored, not surfaced |
| Historical archive | Yes | Yes | Yes | **Deepest** | No | One season |
| Betting / fantasy framing | No | No | Partly (Bullpen Report) | No | **Yes** | **No (by design)** |
| Search presence for "[team] bullpen" | High | — | **High** | High | Medium | **Low** (EOS-022) |

**Strengths:**
- the only neutral team-state product;
- evidence plus dates;
- citable permanence;
- role kept separate from rest.

**Weaknesses:**
- no named late-inning hierarchy;
- no search presence;
- one season of history;
- no pitch-quality surface;
- **current output credibility**.

**Gaps that don't matter for the mission:**
- save predictions;
- streamer rankings;
- "likely to pitch";
- DFS;
- minor-league depth;
- full Statcast leaderboards.

**Daily-destination potential:** real for team-focused media *if* one mobile screen replaces box score + RosterResource grid + game logs, *and* the What Changed view speaks in named arms. A beat writer's 3-step workflow becomes 1 step only if the screen is never wrong.

---

## 14. Distribution and adoption

- **Usage evidence:**
  - first-party instrumentation exists (`services/traffic_reporting.py`, `/admin/product-intelligence`);
  - **no usage number has ever been recorded in the repository** (VERIFIED absence);
  - Metricool: no reference anywhere in the repository; no access in this audit (BLOCKED).
- **Channels:**
  - a private drafting page for reddit/linkedin/x (manual posting; `/posts-bpen-7f3d9c`);
  - static Open Graph pages are the only automated distribution;
  - the newsletter signup form was deleted (TN-11), while the subscribers table and welcome email remain.
- **Discoverability:**
  - team pages are redirect stubs with conflicting canonicals;
  - SPA bodies are empty;
  - the sitemap has no `lastmod` (prior F-02);
  - `source=share` mislabels organic team visits (EOS-022).
- **Product failure vs distribution failure:**
  - Both are present.
  - The product failure (EOS-001/002) must be fixed before any distribution effort, or distribution amplifies wrong claims.
- **2027 adoption strategy** (practical, solo-founder):
  1. Record a 2026 demand baseline now (EOS-M04).
  2. Fix indexability of `/team/{ABBR}`.
  3. Recruit 15–20 named beat writers and podcasters (one or two per club) for a 30-day Opening-Day trial, with a copy-ready citation line (EOS-I03).
  4. Post at most 3 times a week per Standard 06, with team-specific named-arm observations linking to share artifacts.
  5. Measure different-day returns per club page.
  6. **Do not** add posting volume or automation until the trial shows citations or returns.

---

## 15. Maintainability and technical debt

| Retain | Simplify | Consolidate | Rewrite | Delete |
|---|---|---|---|---|
| Appearance ledger; legacy writer; publication transaction; share artifact model; role movement; the test suite (after making it hermetic) | Publication gates → one structural gate plus one plausibility gate; Trust surfaces → one page; navigation → 5–6 entries | Workload rules → one module (EOS-017); classifiers → one (EOS-018); Tonight/Dashboard home | Team Board read path → per-team rows (EOS-014); distribution → API-served metadata (EOS-013) | SP branch runtime and fences (after verification); CU shadow crons; 12 `*_2026.py` modules plus ~20 workflows; unused routes; ~2k unused frontend lines; `docs/current/CU_*` → `docs/audits/` |

**No broad rewrite is justified.** Every major issue has an incremental fix in an identifiable module.

---

## 16. Scoring methodology

- **Scale:** each category is scored 0–100 against what a serious baseball user and a solo operator need by Opening Day 2027.

| Band | Meaning |
|---|---|
| 90+ | Exemplary and verified |
| 70–89 | Strong with minor gaps |
| 50–69 | Functional with material gaps |
| 30–49 | Significant defects |
| < 30 | Absent or failing |

- **Caps:**
  - a category whose central behaviour is UNVERIFIED is capped at 60;
  - a category containing a VERIFIED Critical defect is capped at 40.
- **Confidence:**
  - High — mostly VERIFIED code and artifacts;
  - Medium — mixed;
  - Low — key behaviour BLOCKED.
- **Overall:** the unweighted mean of the 17 categories (39). A weighting by user impact (×2 for categories 3, 6, 7, 13) gives 36. The headline uses the unweighted figure to avoid false precision.
- **Readiness assessments:**
  - technical readiness: categories 7–11 and 14;
  - product readiness: categories 1–6, 12 and 13;
  - 2027 launch readiness: whether the critical path in `05` fits before about 2027-03-01 with founder capacity. It does, if infrastructure work is deferred.
