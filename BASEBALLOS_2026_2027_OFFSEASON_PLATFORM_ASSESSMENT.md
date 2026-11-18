# BaseballOS — 2026–2027 Offseason Platform Assessment

**Assessment date:** 2026-11-18
**Code basis:** `main` @ `a16209afc5356f1fc229e24bd7bf9001757b5cf0` (merge of PR #913, 2026-11-18)
**Type:** Independent, read-only assessment. No code, configuration, workflow, branch, PR, or production state was changed.

**Evidence labels used throughout**

| Label | Meaning |
|---|---|
| **[V-code]** | Verified by reading code at the stated commit |
| **[V-run]** | Verified by executing something in this session (tests, build, audit tool, migrations on a disposable local DB) |
| **[V-gh]** | Verified from live GitHub data (Actions run logs, PR/branch/issue metadata) retrieved today |
| **[V-repo]** | Verified from files committed to the repository, such as generated public pages |
| **[Inf]** | Inference from verified facts. Not proven. |
| **[Unverified]** | Could not be observed in this session |

**Access limitations (read first).** This session's network policy blocked `baseballos.app`, the production API, Render, Vercel, Supabase, and direct fetches of competitor sites. The public product was therefore **not tested live**. Product findings come from three sources:

- the frontend code;
- a local production build exercised in headless Chromium against an unreachable or mocked API;
- the 10,174 public share pages and 30 team pages that automation commits to `main`. These are the same files Vercel serves.

Production behaviour comes from GitHub Actions logs. Competitor findings come from web-search results, not opened pages.

---

## 1. Executive Assessment

### Verdict

BaseballOS has a strong core, but it is not operationally ready for 2027.

**What is strong:**
- The descriptive bullpen model: Team State, arm reads, roles kept separate from workload, and receipts.
- An unusually disciplined trust and publication layer.
- A Team Board that is already the most complete public, single-page picture of an MLB bullpen that I could find.

**What is not ready:**
- The production pipeline has been red every day for weeks.
- The public read has not refreshed since 2026-11-11.
- CI now fails on every build.
- A silent ingestion defect blanks throwing hand for newly created pitcher records, and that gap is published as evidence on thousands of pages.
- The transition into spring training and Opening Day has never been exercised.

This offseason does not need more intelligence domains or new infrastructure. It needs three things:
1. an honest, season-aware pipeline that stays green and alerts when it breaks;
2. a short list of correctness fixes;
3. one or two focused Team Board improvements that answer the fan's first questions faster: "who is closing?" and "who is down tonight?"

### The five most important findings

1. **Daily publication is failing in production, and nobody is alerted.** [V-gh]
   - Every daily `public-sync` run from 2026-11-12 to 2026-11-17 failed with `ValueError: team_state_publication_proof_invariant_failed:reference_date_alignment` (for example run 44155845626).
   - The published snapshot has been 5827 (data through 2026-10-28) since the last distribution commit on 2026-11-11 (`7a5fde1e`).
   - `internal-enrichment` has failed on every daily and postgame run since 2026-10-28. A pitcher name such as "Will Vest" trips the forbidden-prediction regex.
   - `shadow-activation-health` has failed on every non-slate run since at least 2026-10-11.
   - Because "red" is now normal, a real failure is indistinguishable from noise.
   - No external alerting exists on `main`. A health-check workflow exists only in unmerged PR #911.
2. **CI on `main` is now red for every build.** [V-run][V-gh]
   - The React Router risk acceptances in `.github/dependency-audit-accepted.json` expired on 2026-11-13.
   - Running `backend/scripts/verify_dependency_audit.py` against today's `npm audit --omit=dev` returns `Result: FAIL` with three refused advisories (GHSA-wrjc-x8rr-h8h6, GHSA-jjmj-jmhj-qwj2, GHSA-337j-9hxr-rhxg).
   - The open-redirect and XSS advisories are real (moderate), and the migration (#645) has not been done.
3. **Throwing hand is never stored for pitchers created by the production sync.** [V-code][V-repo]
   - `Pitcher.throws` is set only in `backend/seed.py:93`.
   - The production identity-creation paths drop `pitchHand` even though they hold the MLB `person` record:
     - `services/canonical_transaction_pitcher_acquisition.py:69-84`
     - `services/pitcher_identity_reconciliation.py:258-278`
   - The consequence is public:
     - 6,209 of the 10,174 committed share pages list "N active relievers are missing throwing-hand data" as evidence for a Team State.
     - The handedness gate can withhold a team's read (`team_operations/bullpen_readiness.py:552-557`).
     - Handedness, the most basic bullpen fact, cannot be shown reliably.
4. **The 2027 season transition is unbuilt and untested.** [V-code]
   - **The offseason exit is handled.** WP-0.1 (#910, #912) withholds Team State for clubs whose season is complete (`services/club_competition_status.py`).
   - **The entry is not:**
     - Team History requests season 2026 by hardcode: `frontend/src/components/history/TeamHistoryPage.jsx:448`, `frontend/src/utils/api.js:542`, `backend/api/team_history.py:16`.
     - There is no explicit spring-training or exhibition (`S`/`E`) exclusion at ingestion or workload. The only competitive-type filter lives in competition status (`club_competition_status.py:84`) and the backtest (`availability_backtest.py:81`).
     - The failing `reference_date_alignment` proof (finding 1) shows that the date authorities already disagree when no games are played.
   - Opening Day will be the first natural test of all of this.
5. **The product is deep, but its depth is hard to reach.** [V-code][V-run]
   - The Team Board renders roughly 15 sections (§3.3).
   - Rest counts, back-to-backs and 7-day pitches each appear in three or four places.
   - The page is 6,635 px tall at 390 px width even with a one-reliever fixture.
   - The Team Board has no real `/team/:abbr` route. It lives at `/bullpen?view=board&team=X`, and `/team/X` is a static JS redirect stub.
   - The most-asked fan question, "who is closing / who finishes games?", has no direct answer. Leverage and role-movement publication remain open decisions (O-004, O-009).
   - Competitors already offer free 6-day usage grids (FanGraphs RosterResource). BaseballOS's real advantages are named-arm change, team-level state with receipts, and history. Today those are exactly the hardest things to find.

### What BaseballOS is today (one paragraph)

BaseballOS is a public, descriptive MLB bullpen platform: React/Vite on Vercel, Flask on Render, PostgreSQL (Supabase per the RLS migration).

- **Source and cadence:** it ingests MLB Stats API data on a Render cron with a GitHub Actions fallback. Daily, morning-slate and postgame lanes run; there are no live in-game updates.
- **Derived reads:**
  - per-reliever workload windows (yesterday, 3, 4, 5, 7 and 14 days);
  - arm reads (Clean Option / Watch Arm / Limited Rest / Unavailable / Limited Read);
  - descriptive roles;
  - a deterministic three-value Team State (Fresh / Stretched / Vulnerable) per club.
- **Publication:** each read goes through an atomic, proof-gated snapshot. Immutable share artifacts back a retained Team State history.
- **Surfaces:** Tonight (home), a League Board, a deep Team Board, Pitcher, Matchup/Compare, Search/Reliever Finder, History, Stories, Methodology and Data & Trust.
- **Scale:**
  - about 225k lines of non-test Python (288 service modules; `services/sync.py` alone is 7,792 lines);
  - about 224k lines of tests (464 files);
  - 87 linear migrations;
  - about 28k lines of frontend source;
  - 27 workflows.

---

## 2. Verified Current State

### 2.1 Capability status matrix

| Capability | Status | Evidence |
|---|---|---|
| Daily, morning-slate and postgame legacy writer (MLB gameLog, rosters, transactions, schedule, boxscore) | **Implemented. Production-verified through 2026-10-28 data. Currently failing daily publication since 11-12.** | `.github/workflows/baseballos-sync.yml:33-41`; runs 44155845626, 43950384156 [V-gh] |
| Atomic, proof-gated snapshot publication (advisory lock, single transaction, Team State proof, slate and ledger gates) | Implemented; production-verified (it is what currently refuses to publish) | `services/dashboard_snapshot.py:331-495`; `services/sync_metadata.py:137-325` [V-code] |
| Season-complete withholding per club (WP-0.1, DEC-01/02) | Implemented; merged 10-31 and 11-05 (#910, #912) | `services/club_competition_status.py`; `services/team_state_public_vocabulary.py` [V-code] |
| Rested-by-absence fix (inactivity no longer counted as constraint, EOS-001) | Implemented (#910) | `services/availability.py` (`availability_rest_by_absence_v2`) [V-code] |
| Publication plausibility gate (EOS-004) | Implemented (#910) | `services/team_state_plausibility.py` [V-code] |
| Team Board 2.0 (core/details read, 11 domains) | Implemented. Production-verified per ledger v5.16 (Sep 4); not re-verified live. | `api/team_board_v2.py:133-210`; `docs/canonical/05_…:701-702` |
| Tonight v1 (immutable read model, lifecycle, featured games) | Implemented. Production-certified per TN-12 audit (Sep 29); not re-verified live. | `services/tonight_v1_serving.py`; `docs/audits/tonight-v1-final-production-certification-tn-12.md` |
| Team State History (HIST-01…04) | Implemented; hardcoded to season 2026 | `api/team_history.py:16`; `TeamHistoryPage.jsx:448` [V-code] |
| Share artifacts (static + SPA) | Implemented; 10,174 static pages committed by automation | `frontend/public/share/` (120 MB) [V-repo] |
| Generated distribution (commits HTML to `main`) | Implemented; last publish 2026-11-11 | `.github/workflows/baseballos-generated-distribution.yml`; commit `7a5fde1e` [V-gh] |
| Availability backtest ("How the labels matched next-day usage") | Implemented; served on Data & Trust | `services/availability_backtest.py:35,81`; `/methodology/availability-backtest` [V-code] |
| Game-driven ingestion (daily/postgame) | **Shadow only.** Re-fetches boxscore and PBP and takes 25% of the ingestion pool while writing nothing. | `baseballos-sync.yml:140,184-190,270`; `game_driven_ingestion.py:1115-1121` [V-code] |
| Game-driven backfill | Off | `baseballos-sync.yml:323` [V-code] |
| Continuous / live-game lane (CU-02…CU-08) | **Dormant.** Default `off`; reachable only from `scripts/run_continuous_cycle.py`, which no workflow calls. | `services/continuous_execution.py:83-136` [V-code] |
| Scheduled intraday repair | Retired for 2026; manual-only | `baseballos-intraday-repair.yml:10-11` [V-code] |
| `feat/sync-pipeline` replacement control plane | **Unmerged:** 135 ahead / 299 behind, 111 files absent from `main`. Only its 3 migrations (and DB fence triggers) are on `main`. | GitHub branch comparison [V-gh] |
| Pitch-level data (velocity, spin, movement, release, extension) | **Stored, never read.** Collected since about 2026-07-04 per prior audit; read by no service or API. | `models/play_by_play_foundation.py:183-226`; `services/play_by_play_foundation.py:794` [V-code] |
| Play-by-play events (entry inning, score at entry, pitching changes) | Stored and used for deployment context | `services/team_board_public_deployment_context.py:273-285` [V-code] |
| Leverage index | **Effectively absent.** Hard-coded 0.0 in `fatigue.py:216`; `appearance_leverage.py` is imported only by tests; public leverage is undecided (O-004). | [V-code] |
| Saves, holds, games finished, inherited runners | Stored on `game_logs`. Saves and holds feed roles. Inherited runners are "not published". | `models/game_log.py:128-136`; `TeamBoardPerformance.jsx:38-39` [V-code] |
| Performance | **Team Board only:** Active-pen ERA and WHIP, 108-out floor | `services/performance_metrics.py:75-103` [V-code] |
| Prospects | Seed-only data; `/api/prospects/*` routes registered but never called by the frontend | `app.py:216`; `seed.py` [V-code] |
| Accounts / magic-link auth | Implemented (unauthenticated user creation, no rate limit) | `api/auth.py:43-59` [V-code] |
| External production monitoring / alerting | **Missing on `main`.** Proposed only in #911 (`production-health.yml`). | [V-code][V-gh] |
| Backup / restore proof | **Unverified.** Restore-rehearsal script exists only in #911. | [Unverified] |
| `main` branch protection | **Absent:** `GET /branches/main/protection` returns 404 and rulesets are `[]` | [V-gh] |

### 2.2 Tests, build and migrations executed in this session

| Check | Result |
|---|---|
| Alembic chain | 87 revisions, single root and single head `a7c3e9f1d2b5`. `flask db upgrade` on an empty local PostgreSQL 16 completed. [V-run] |
| CI shard accounting (`scripts/ci_shard.py verify`) | PASS: 0 duplicated or missing node IDs [V-run] |
| Backend suite (4 shards, local PostgreSQL 16, Python 3.11) | **10,795 passed, 8 skipped, 1 environmental failure** (passes when rerun correctly); see §2.3 [V-run] |
| Frontend unit tests (`npm test`) | **1,303 / 1,303 passed** [V-run] |
| Frontend production build | Succeeds. **One 707.98 kB JS chunk (193 kB gzip)**; no code-splitting anywhere (`lazy()` absent). `dist/` is 121 MB / 10,232 files because the share pages are copied in. [V-run] |
| Frontend browser suite (`tests/browser`, includes axe) | **Not run.** It pins a Chromium build that is not installed here. |
| Dependency gate (`verify_dependency_audit.py`) | **FAIL**: 3 expired acceptances [V-run] |
| CI on `main` (GitHub) | Green through 2026-11-05 (run 42102540444). The first push after expiry (run 44305413660, 11-18) fails `dependency-audit` only. [V-gh] |

### 2.3 Backend test result

[V-run] The full backend suite was executed as CI shards it: 4 shards from `scripts/ci_shard.py`, each against its own disposable local PostgreSQL 16 database, on Python 3.11.

| Shard | Result | Wall time |
|---|---|---|
| 1 | 2,295 passed, 1 skipped | 16 m 55 s |
| 2 | 2,778 passed, 3 skipped | 17 m 48 s |
| 3 | 3,672 passed, 3 skipped | 15 m 44 s |
| 4 | 2,050 passed, 1 failed, 1 skipped | 14 m 10 s |

**Total: 10,795 passed, 8 skipped, 1 failed.**

- **The one failure was environmental.** `test_production_lineage.py::test_fresh_and_existing_postgres_preserve_history_data_and_normal_startup` failed with `ModuleNotFoundError: alembic` because `scripts/render_start.sh` invoked the system `python`, not the venv. With the venv on `PATH`, `tests/test_production_lineage.py` passed **6/6**.
- **Skips:**
  - 3 skips are "git diff against origin/main unavailable". The behaviour-freeze guards need `origin/main`; CI uses `fetch-depth: 0`.
  - 1 skip is "no remote ancestor".
  - The remaining skips cover non-PostgreSQL branches.
- **Conclusion:** the backend suite is green on `a16209af`. Test health is not the problem. The suite runs on a fixture world and cannot see the production date-alignment failure in §5.6. That gap in coverage is part of the P0-1 acceptance criteria.

### 2.4 Open PRs and divergent branches

| Item | What it is | Relevance to current `main` | Disposition recommended |
|---|---|---|---|
| **PR #911** (WP-0.2 security & ops; 8 ahead / 16 behind, no conflicts, CI green on 11-05) | Proper-noun masking for the claim guard; shadow validator summary normalisation; `permissions: contents: read` on CI; a 6-hourly public health check with email on failure; `/api/health` release SHA; restore-rehearsal script | **Directly fixes two of the three live production failures.** `mask_proper_nouns` and `normalize_sync_summary` are absent on `main`; `evidence_language.py:38` still holds the bare `\b(will\|should…)\b` regex [V-gh][V-code] | **Re-validate on current `main` and merge first** (after the React Router fix makes CI meaningful). Low–moderate risk, no migrations. |
| **PR #909** (evidence quality vs operating state; 3 ahead / 69 behind, 12 conflicting files) | Stricter "ledger-confirmed rest" availability v2, Team State `v3_phase_6`, `evidence_indeterminate` gate | **Semantically superseded and contradicted** by #910: `main` chose "rested by absence = Available, medium confidence". Merging would re-litigate a founder-approved decision (DEC-01/02) and change method versions and receipts. Three small, valid defects in it still exist on `main`. | **Do not merge.** Close with rationale. Cherry-pick only:<br>(a) the false Methodology sentence at `Methodology.jsx:118`;<br>(b) the `'Monitor'` default in `PitcherSearch.jsx:22,24`, a component that is dead anyway;<br>(c) the `sync.py:4691` `if not logs: continue`, which freezes days-since for idle arms. Each needs its own small verification. |
| `feat/sync-pipeline` + 9 subset branches (R1/R2/R3, egress, shadow fixes) | A replacement sync control plane: durable queue, source observations | Not running. Its migrations and fence triggers are on `main`; its code is not. It is the main source of "two pipelines" ambiguity. | **Archive** (tag + one-paragraph summary) and stop treating it as pending work. Do not merge. Revisit only if a measured runtime or correctness problem demands it. |
| `claude/upbeat-hawking-g0indq` (4 ahead, 11-18) | Bullpen-state backtest (28 files, +6k lines) | Potentially useful for label validation. CI fails only on the dependency gate. | Keep as proposed work. Evaluate after P0. |
| `audit/2026-end-of-season-platform-audit` (1 ahead) | The 10-29 end-of-season audit (36 findings, EOS-001…036) | Its Phase 0 WP-0.1 was implemented. Many findings remain true; spot-verified below. | Treat as a historical input, not current truth. |

### 2.5 Status of the 10-29 audit findings, re-verified today

| Finding | Status on `a16209af` | Evidence |
|---|---|---|
| EOS-001 inactivity scored as constraint | **Fixed** | #910 |
| EOS-002 no club competition status | **Fixed** (Season Complete / Status Unconfirmed) | #910, #912 |
| EOS-004 no plausibility gate | **Fixed** | `services/team_state_plausibility.py` |
| EOS-007 sync red by construction | **Still true.** Fix is in #911. | Runs listed in §5.6 |
| EOS-008 no alerting | **Still true** | No monitor on `main` |
| EOS-010 credential exposure | **Still true:** 25 workflows reference the production DB secret; `main` unprotected | `grep` of `.github/workflows` [V-code]; [V-gh] |
| EOS-011 no rate limiting; sign-in creates users | **Still true** | `api/auth.py:43-59`; no limiter dependency in `requirements.txt` |
| EOS-012 React Router expiry | **Now actively breaking CI** | §2.2 |
| EOS-013 HTML committed to git | **Still true:** 120 MB, 10,174 share pages | `frontend/public/share` |
| EOS-014 full snapshot per Team Board request | **Still true (details path).** Latency still unmeasured. | `api/team_board_v2.py:88-100,171-177` |
| EOS-021 one 707 kB chunk; admin code shipped | **Still true** | Build output |
| EOS-023 no game-type policy | **Still true** for workload. Only competition status and the backtest filter. | §1 finding 4 |
| EOS-024 missing throwing hand | **Still true; root cause identified here** | §1 finding 3 |
| EOS-027 internal enrichment fails | **Still true; deterministic cause identified** (name-word regex) | Run 44281693317 |

---

## 3. Product Experience Audit

**Method.** Code review of every route; a local production build in headless Chromium at 390 px and 1280 px, with the API unreachable and with repository fixtures; and the committed static share and team pages. **The live site was not observed.**

**Routing** (`frontend/src/App.jsx:32-57`):
- `/` (Tonight), `/dashboard` (League Board), `/bullpen?view=board|compare|pitchers`;
- `/pitcher/:id`, `/matchup/:gameId`, `/search`, `/stories`, `/history/team/:abbr`, `/share/:publicId`;
- `/methodology`, `/trust`, `/about`, `/how-to-read`;
- auth, admin, and a private-posts route.

### 3.1 Tonight / Homepage (`/`)

- **Purpose:** the night's slate through the lens of bullpen state.
- **Implemented:**
  - H1 "Tonight in MLB Bullpens";
  - header with baseball date, "Data through", and a summary (Team State counts, clubs with back-to-back arms, bullpen changes);
  - lead development, Games to Watch, the full slate, collapsed completed games, league What Changed, "Go deeper" links.
  - Each game card shows per-side Team State, "N rested · N B2B · N in 3-in-4", key arms (name · role · pattern), recent short starts and bullpen IP, and a context sentence.
- **Strengths:**
  - the best state handling in the app: skeleton, calm "quiet" state, and an error with a double-click-safe retry (`TonightEmptyState.jsx`);
  - one request (`/bullpen/intelligence/tonight?contract=tonight_v1`, 12 s timeout);
  - a stable H1;
  - no overflow at 390 px.
- **Weaknesses / missing baseball information:**
  - no probable starters, no final scores (only "Final"), no records or venue;
  - key-arm names do not link to Pitcher pages;
  - in the offseason the home page has no reason to exist beyond "no games", though WP-0.1 now shows Season Complete states.
- **First-time-fan test (10 seconds):** the H1 and per-game Team State badges communicate the idea quickly on game days [Inf]. "3-in-4" and "B2B" are unexplained shorthand on first view.
- **Recommendations:**
  - link key arms;
  - add probable starters, because starter length is the biggest driver of tonight's bullpen burden, and MLB publishes probables;
  - show final scores on completed cards.
- **Expected benefit:** Tonight becomes a pregame tool rather than a label board.

### 3.2 League Dashboard (`/dashboard`)

- **Purpose:** all 30 bullpens at a glance.
- **Implemented:**
  - Storylines;
  - "Current Bullpen State" (30 clubs grouped Fresh/Stretched/Vulnerable, alphabetical within groups, plus publication exceptions);
  - availability context (IL / inactive counts);
  - usage-role counts.
- **Weaknesses:**
  - three names for one page: nav "League Board", H1 "MLB Bullpen Picture", eyebrow "MLB Bullpen Overview" (`Dashboard.jsx:56-60`);
  - one failed fetch renders **two** error cards with two retry buttons (`Dashboard.jsx:72-93`, observed);
  - group cards carry no per-club "why" (rested count, 7-day pitches);
  - internal vocabulary leaks into copy ("published league denominator", "Explanatory Only").
- **Missing:** a sortable 30-row league table of rested arms, back-to-back arms, 7-day relief pitches and starter length. This is the single most-used view in competitor workflows (§6). The earlier table was deliberately retired (`Bullpen.jsx:35-39`).
- **Recommendation:** replace the grouped cards with one compact, sortable league table that keeps Team State as the first column; fix the duplicate error state; settle on one name.
- **Benefit:** answers "which bullpens have carried the most recent work?" in one glance. It currently takes up to 30 clicks.

### 3.3 Team Board (`/bullpen?view=board&team=X`) — primary differentiator

- **Purpose:** the definitive public reference for one bullpen.
- **Loading:** core renders first, then identity-bound details. A 409 on publication mismatch keeps the core answer (`api/team_board_v2.py:163-206`). The read path was already consolidated from 5 → 2 initial requests (PRE-02B).

**Sections in render order** (verified in the browser with fixtures):

| # | Section | Contents |
|---|---|---|
| 0 | Route H1 + view switcher | "Team Board", switcher, subtitle |
| 1 | Answer block | Team State chip, one-sentence summary, data-through, game context; "Why this read?" (Rested Options, Coverage Safety, Workload Concentration, Recent Starter Length); Bullpen Summary (active arms, rested options, recently used, off-active, 7-day pitches) |
| 2 | Active Bullpen | Per arm: Read, Last/Rest, Last P, 7d App, 7d P, Pattern, Destination |
| 3 | What Changed | Governed change events vs the prior trusted publication |
| 4 | Recent Usage, Rest Status, Workload Overview | Including seven-day pitch contributors |
| 5 | Roles & Deployment, Performance | Deployment covers entry inning, score at entry, and leverage "not published". Performance is Active-pen ERA and WHIP only. |
| 6 | Rotation Impact, Roster & Transactions | |
| 7 | Recent Relief Work | Per-game receipts |
| 8 | Share menu | |

**Strengths:**
- Role and current read are separate concepts.
- Every number has a receipt.
- Section-local failure isolation.
- Backend-owned copy.
- Explicit "not published" instead of guessing.
- An honest data-through.
- No competitor found combines state, named-arm workload, rotation transfer, transactions and history on one page (§6).

**Weaknesses:**
1. **Redundancy:**
   - "Team Board" appears three times above the fold;
   - rested count, B2B and 7-day pitches each appear in 3–4 sections (Summary, Active Bullpen, Recent Usage, Rest Status, Workload Overview);
   - What Changed duplicates Tonight's list.
2. **Length:** 6,635 px at 390 px with a one-reliever fixture. A real 8–13-arm bullpen will be much longer [Inf]. There is no in-page navigation.
3. **Missing fan-critical answers:**
   - who has been finishing games / entering in the 8th or later (late-inning hierarchy; data exists in play-by-play, saves/holds and games finished, but publication is gated by O-004/O-009);
   - handedness counts (blocked by finding 3);
   - per-arm season line.
4. **Routing:**
   - no SPA route for `/team/:abbr`;
   - the 30 static `/team/X` pages `window.location.replace(...)` to `/bullpen?view=board&team=X&source=share`, so every organic visit is tagged `source=share`;
   - client-side navigation to `/team/NYY` shows "Page not found" [V-run].
5. **Error handling:** if `/bullpen/teams` fails, the board silently shows "Pick a team" even with `team=NYY` in the URL, with no error and no retry (`TonightsBullpenBoard.jsx:60,133-136,157-160`, observed).
6. **Navigation semantics:**
   - view buttons use `aria-pressed` but navigate;
   - about 22 internal `<a href>` links force full reloads (for example `ActiveArmRow.jsx:128`).

**Recommendation: targeted refinement, not a rebuild.** The read model and section isolation are sound.
- (a) Make the Active Bullpen table the first screen on mobile, with inline receipts.
- (b) Collapse Recent Usage, Rest Status and Workload Overview into one "Workload" section with window tabs.
- (c) Add a descriptive "Late innings, last 14 days" block once O-009 is decided.
- (d) Give the board a real `/team/:abbr` route.
- (e) Fix the teams-fetch failure state.

**Expected user benefit:** the answer to "who's available and who's been carrying it" lands on the first screen of a phone.

### 3.4 Pitcher Detail (`/pitcher/:id`)

- **Implemented:**
  - header (team, position, throws, age, number);
  - current situation (role, read, last used, days rest, 7-day apps and pitches);
  - availability summary;
  - recent work (14-day ledger);
  - workload pattern flags;
  - observed deployment (SV, HLD, GF, multi-inning).
- **Strengths:** a clean separation of role and read, plus an appearance ledger.
- **Weaknesses:**
  - no season line (IP, ERA, K/BB);
  - "Data through" is shown as a raw ISO string (`PitcherDetail.jsx:102`);
  - "Last Used" and "Days Rest" are redundant;
  - the Team Board link is a full reload (`:119-120`);
  - the error shows raw "Failed to fetch";
  - an unused `getPitcherLogs` API exists.
- **Recommendation:** add a compact season-to-date relief line (G, IP, K%, BB%, SV/HLD) from stored `game_logs`, plus a link out to Savant/FanGraphs for pitch data. Do not build pitch analytics here (§9).
- **Benefit:** a reader no longer has to leave the page for basic context.

### 3.5 Matchup / Compare

- **Matchup (`/matchup/:gameId`):** Team State A/B plus four domains (rest, 7-day workload, rotation transfer, availability counts) and links to both boards.
  - **Missing:** probable starters and key-arm availability by name.
  - **Defect:** loading and error states render **no H1** (`MatchupPage.jsx:19-24`, observed) and show raw fetch errors.
- **Compare (`/bullpen?view=compare`):** the same view with two selects. If teams fail, the selects are empty with no error.
- **Recommendation:** add probable starters and the top named arms per side (from the board's Active Bullpen). Fix the H1 and error states.
- **Benefit:** answers "how do these two bullpens differ entering tonight?" in named terms, not just counts.

### 3.6 Search / Reliever Finder

- **`/search`:** good. Grouped results, a polite live region, debounced input, 8 s timeout.
- **Reliever Finder (`/bullpen?view=pitchers`):** a sortable, paginated table (availability, 7-day pitches, rest, 7-day apps).
- **Weaknesses:**
  - not in the primary nav;
  - "Show pitchers outside the freshness window" is jargon;
  - filters and sort are not in the URL, so they are not shareable;
  - the team filter degrades silently when teams fail;
  - `PitcherSearch.jsx` (176 lines) is a third, unused search component.
- **Recommendation:** put filters in the URL, rename the jargon, delete the dead component.
- **Benefit:** writers can share a filtered view such as "all Unavailable arms today".

### 3.7 What Changed

- **Implemented:** there is no standalone page. It appears on Tonight (league list) and on the Team Board (governed events vs the prior publication).
- **Weaknesses:**
  - change domains are aggregate (rested options, usable depth, coverage safety…) rather than named arms;
  - prospective arm-read and workload deltas are explicitly not activated (O-011);
  - `/since-yesterday/<team_id>` and `getTeamChanges` exist unused;
  - PI-02 "Since Yesterday" artifact generation had **zero natural rows** at the ledger closeout (`docs/canonical/05_…`, §3) and remains unproven.
- **Recommendation:** named-arm changes ("X → Limited Rest after 31 pitches Monday"; "Y placed on IL") are the highest-retention addition available, because they give a reason to return tomorrow. This depends on the O-011 decision and on the pipeline being green.

### 3.8 History (`/history/team/:abbr`)

- **Implemented:** coverage range, partial-history notice, month jump navigation, per-date rows (state, explanation, change events, transactions, limitations), and links to immutable observations.
- **Strengths:** no historical recomputation; explicit gaps; integrity-checked artifacts.
- **Weaknesses:**
  - **season hardcoded to 2026** in three places (§1 finding 4);
  - no H1 in loading or error states;
  - raw errors.
- **History quality caveat:** a large share of retained artifacts were produced under pre-#910 semantics. The 10-29 audit estimated about 750–1,500 affected October artifacts. The comparison carrier refuses comparisons across the method boundary (`availability_method_boundary`), which is correct. A public correction note has not been published [Inf from WP-0.1 doc: the correction manifest is dry-run only].
- **Recommendation:** add a season parameter driven by the backend's current season; publish the correction note.

### 3.9 Stories (`/stories`)

- **Implemented:** filterable story cards built by about 15 `story_*_v1` backend modules.
- **Weaknesses:**
  - copy references a "morning briefing" that no surface provides (`Stories.jsx:92`);
  - generic error state;
  - the story machinery is large relative to its evident use.
- **Recommendation:** leave it as is; do not expand it (§9).

### 3.10 Share Artifacts

- **Implemented:** two renderers.
  - 10,174 static, JS-free HTML pages with OG/Twitter meta.
  - An SPA page that handles ok, superseded, withdrawn, not-found, integrity-error and API-error states.
- **Weaknesses:**
  - **6,209 pages cite missing throwing-hand data as evidence** [V-repo]. That is a data-quality gap presented as a reason.
  - 2,424 pages have no evidence rows.
  - State counts across retained pages: 5,377 Vulnerable, 3,011 Stretched, 970 Fresh. This skew is consistent with the pre-#910 defect [Inf].
  - The pages live in git (120 MB) and ship in every deploy.
- **Recommendation:**
  - stop using handedness coverage as public evidence;
  - after the ingestion fix, let natural publication replace it;
  - move distribution out of git later (P2).

### 3.11 Methodology / Data & Trust

- **Methodology:**
  - static, thorough, but 5,782 px at 390 px with no table of contents;
  - `getMethodology` is unused;
  - contains one false sentence ("…it withholds the read instead of guessing", `Methodology.jsx:118`, flagged by #909).
- **Data & Trust:** freshness, sync status and the availability backtest. With the API down it shows two separate error cards.
- **Strength:** publishing a label-vs-next-day-usage backtest is rare and credible.
- **Recommendation:**
  - add a TOC;
  - correct the sentence;
  - put the backtest headline number at the top of Data & Trust once it is computed on the full 2026 season.

### 3.12 Cross-cutting UX and frontend findings

| Finding | Evidence | User consequence |
|---|---|---|
| Raw technical errors shown to users | `hooks/useFetch.js:54` passes `err.message` ("Failed to fetch", "API 503: …") | Looks broken; undermines trust copy |
| Two visual systems | Legacy chalk/amber/mono (Dashboard, Stories, Pitcher, Matchup, Finder) vs board tokens (Team Board, History) | Inconsistent feel when switching tabs |
| About 15 dead modules (~2,000 lines); about 28 unused API functions | e.g. `board/BullpenBoardView.jsx` (469 lines), `utils/evidenceCardModel.js` (462) | Maintenance drag only |
| No code-splitting; admin and private code in the public bundle | Build output; no `lazy()` | Slower first load on mobile [Inf]; admin surface discoverable |
| Private route published in `robots.txt` and `vercel.json` | `/posts-bpen-7f3d9c` | The "unguessable" URL is public |
| No security headers or asset Cache-Control | `frontend/vercel.json` | Weaker posture; repeat-visit cost |
| Accessibility basics are good | Skip link, route focus and announce (`RouteAccessibility.jsx`), 44 px targets | Keep |

---

## 4. Bullpen Intelligence Audit

| Domain | Collected | Calculated | Public | Meaningful gap | Value of closing it | Cost |
|---|---|---|---|---|---|---|
| **Workload & rest** | Per-appearance pitches, outs, BF, dates (gameLog + boxscore ledger) | Windows: yesterday/3/4/5/7/14 d (`availability.py:31,139-177`); fatigue score (`fatigue.py:43-69`); B2B, 3-in-4, consecutive days, multi-inning | Yes: Team Board, Pitcher, Tonight, Finder | 30-day and season windows are not public. 4-in-6 is withheld (O-012). Unknown pitch counts score as 0 in fatigue (`fatigue.py:191-203`, fail-low bias). | Medium. Current windows match how writers think (§6). | Low |
| **Deployment & roles** | SV, HLD, GF, entry inning and score from PBP | Starter/reliever split (`role_authority.py:64-70`); 45-day role model (`pitcher_role.py:28-57`); role movement (#907) | Role labels, entry context; leverage "not published" | **No direct "who's closing / late-inning hierarchy" answer.** LI effectively absent. Roles built from regular-season logs only (gameLog default; EOS-006). | **High.** This is the fans' first question. | Medium (needs the O-009 decision; data exists) |
| **Active composition** | Rosters (active / 40-man / full / NRI), transactions (7-day), IL | Roster precedence (`roster_status_sync.py:567-586`) | Active Bullpen, Roster & Transactions | **Throwing hand missing for sync-created pitchers** (finding 3). Unresolved transaction codes withheld (O-010). | **High** (correctness) | Low |
| **Performance** | Full per-appearance lines | Active-pen ERA and WHIP (108-out floor) | Team Board only | No K%/BB%/HR, no per-arm season line, inherited runners scored not published (O-013) | Medium. Available elsewhere, but needed in context. | Low–Medium |
| **Rotation impact** | Starter lines | Short starts <15 outs, 7-day window, average IP (`rotation_support_pressure.py:43-71`) | Team Board, Tonight, Matchup | No probable starter for tonight | Medium–High for pregame use | Low (MLB schedule `hydrate=probablePitcher`) |
| **Schedule & recovery** | Rolling schedule, 3 days ahead; postponement and absence evidence | Off-day and slate context | Tonight, game context | Upcoming-schedule depth is shallow (3 days); first-round-bye ambiguity documented | Low–Medium | Low |
| **Pitch characteristics** | **Velocity, spin, movement, release, extension stored since about July 2026** (`models/play_by_play_foundation.py:183-226`) | None | None | Entirely unused | Medium-term differentiation (velocity under workload). Not an offseason priority. | Medium–High, plus methodology risk |
| **Historical** | Immutable Team State artifacts; appearance ledger | HIST-01…04 timeline, change markers, transaction overlays | History page | Season hardcode. Pre-#910 artifacts carry wrong semantics. No reliever or season summaries. | Medium | Low (season param); Medium (season summary) |

**Duplication risk in the intelligence layer** [V-code]:
- Contract A (the Team State rule) is re-implemented in four places: `team_operations/bullpen_readiness.py:563-644`, `team_state_vnext_production_proof.py:226`, `publication_truth_certification.py:532` and `production_accuracy_reconciliation.py:654`.
- Four further team-level classifiers carry their own thresholds: coverage safety, resource health, capacity and support pressure.
- These are proof and audit copies, but any threshold change must touch all of them, and divergence would be silent.

**Team State rule as implemented** [V-code], `bullpen_readiness.py:487-644`; constants in `team_operations/contracts.py:67-98`:
1. Data gate (freshness, trust, coverage, handedness, empty population) → withheld.
2. **Vulnerable** if clean ≤ 2 or severe share ≥ 1/3.
3. **Fresh** if clean share ≥ 3/5, clean ≥ 5 and severe ≤ 1.
4. Otherwise **Stretched**.

"Clean" means Available. "Severe" means Avoid or Unavailable. This is simple, explainable and appropriate, and it should not be replaced. Its main open question is empirical: do the labels separate next-day usage? The backtest exists; publish its full-season result.

---

## 5. Engineering and Operations Audit

### 5.1 Data acquisition

- **Mechanism:** a direct Python coordinator writes to production Postgres. Render Cron is primary and GitHub Actions is the fallback (`baseballos-sync.yml:3-6`). Render cron configuration is **not in the repository** (`docs/current/SYNC_PIPELINE.md:107-119`).
- **MLB client:** 10 s timeout, 3 retries with jittered backoff, honours `Retry-After` (`mlb_api.py:20-30,181-350`). Good.
- **Cost driver:** the daily writer fetches the full-season gameLog for **every active pitcher** (about 861) each day (`sync.py:3871,4055`). The budget was raised from 1080 to 2200 s as a stop-gap (`sync.yml:161-191`). This is acceptable for 2027 at current scale, but it is the dominant runtime risk. Defer redesign unless runs approach the budget again (#662).
- **Postgame:** games marked `fully_processed` are skipped (`sync.py:436-455`). Late MLB stat corrections therefore arrive only via the daily 7-day gameLog sweep [Inf]. That is acceptable.
- **No live in-game updates.** For a pregame/postgame descriptive product this is correct; do not add them (§9).
- **Game types:** the gameLog call passes no `gameType` (`mlb_api.py:566-571`), and the schedule call takes all types (`:623`). Whether spring or exhibition boxscores can enter the appearance ledger in March is **[Unverified]**. There is no explicit exclusion policy, so this must be tested before spring training.

### 5.2 Derived intelligence

Deterministic and well-tested, with heavy duplication (§4). There are two dead or contradictory paths:
- `fatigue.recalculate_all_fatigue` (`fatigue.py:228`) has no callers and duplicates `sync.py:4634`.
- `backend/recalculate_fatigue.py` anchors on each pitcher's last game date, which contradicts the canonical-date rule.

### 5.3 Publication

**Strengths:**
- An atomic single-transaction publish with an advisory lock, a DB check constraint, a mandatory Team State proof, slate/ledger gates and a plausibility gate (`dashboard_snapshot.py:331-495`).
- Content hashes on Tonight publications, team packages and share artifacts.

**Weaknesses:**
- Immutability is application-enforced only: no DB triggers on publication tables.
- The payload is mutated at publish time (`dashboard_snapshot.py:396-404`).
- **The proof correctly refuses to publish when date authorities disagree. In the offseason they now always disagree.** The failing summary records `data_through 2026-10-28`, `availability_reference_date 2026-10-30` and `reference_date 2026-11-17` (run 44155845626).
  - `_reference_date_alignment` (`team_state_vnext_production_proof.py:329-352`) expects availability = canonical next day after `data_through` (2026-10-29).
  - The root cause, where the 10-30 availability date comes from, is **[Unverified]** and must be diagnosed. It is the same class of defect as D-056 ("classifying the league a day early").
  - Failing closed here is the right behaviour. Being unable to publish anything, and alerting no one, is not.

### 5.4 Backend, API and database

- **Routes:** 90 routes across 25 blueprints. Unused by the frontend: `/prospects/*`, `/team-operations/*`, `/intelligence/today`, three `*/diagnostic` routes, `/mlb/*` [V-code].
- **Payloads:**
  - `/dashboard` loads and serializes the multi-megabyte snapshot per request with no Cache-Control (`api/bullpen.py:3671-3683`).
  - `/stats/overview` loads the full payload to return one sub-dict (`:2888-2892`).
  - Team Board details rebuild the published board per request (`team_board_v2.py:88-100`).
  - **Latency has never been measured** [Unverified]. Measure before optimizing.
- **N+1 queries:** fatigue recompute runs about 861 queries (`sync.py:4683-4693`). This is batch-time only, so it is acceptable.
- **Migrations:** healthy (single linear chain; upgrade verified).
- **Retention:** `fatigue_scores` is append-only and snapshots have no retention policy (EOS-015). This is a cost and egress risk on Supabase [Inf]; quantify it before acting.
- **Statement timeout:** the global 15 s `statement_timeout` also applies to batch sync (`config.py:78`) [Inf].

### 5.5 Frontend

See §3.12. Tests are strong (1,303 unit tests plus a Playwright and axe suite). The build has a single chunk. There are two visual systems and some dead code. The architecture is sound and needs no framework change, and no TypeScript migration.

### 5.6 Operations

| Area | Finding | Evidence |
|---|---|---|
| Scheduled sync | Daily publication fails since 11-12 (`reference_date_alignment`). Earlier November failures had other causes: `league_team_state_artifact_set_incomplete` (11-01), `dashboard_snapshot_slate_coverage_incomplete` (11-02), `sync_writer_already_running` (11-05). | Runs 41297054942, 41518566489, 42080329415, 44155845626 [V-gh] |
| Internal enrichment | Fails every run since 2026-10-28 (run 40727951878): `forbidden_prediction_framing: 'Will'` | Run 44281693317 [V-gh]; `evidence_language.py:38` |
| Shadow health | Fails every non-slate run since ≥ 2026-10-11 (`validator_reported_failure`) | Jobs 134724304248, 134300933289 [V-gh] |
| Shadow cost | Shadow lanes re-fetch every game and take 25% of the pool, writing nothing | `sync.yml:184-190` |
| Monitoring | None external on `main` | — |
| Backups | Unproven [Unverified] | — |
| Secrets | Production DB URL in 25 workflow files. One job with `contents: write` pushes to `main`. `main` unprotected. | `sync.yml:964-965,1299-1304` [V-code]; [V-gh] |
| Rate limiting | None. `POST /api/auth/request-link` creates a `User` row and sends mail for any address. Unauthenticated, live-computing diagnostics (`api/bullpen.py:2646,2780,2849`). Unauthenticated MLB proxy (`:3796-3812`). | [V-code] |
| Auth tokens | Magic links last 15 min and are not single-use. Bearer tokens last 30 days with no revocation. One shared admin token. | `utils/auth_tokens.py:13-110` |
| Config drift | `DEBUG` defaults on when `APP_ENV` is missing. This is mitigated by refusing non-local DBs, but `/api/health` exposes the flag. | `app.py:86-88,288` |
| Workflow sprawl | 27 workflows, about 20 of them one-off 2026 repair/audit (e.g. `official_pitching_line_matt_festa_apply.yml`) | `.github/workflows/` |
| Governance drift | The canonical ledger (v5.16) is dated Sep 4. Since then #880–#913 merged (Tonight v1, WP-0.1) without a ledger update. | `docs/canonical/05_…:1-15` |

---

## 6. Competitive Position

Sources: web search on 2026-11-18. Pages were not opened, so treat details as indicative.

| Product | Bullpen-relevant offering | Audience / cost |
|---|---|---|
| **FanGraphs RosterResource Closer Depth Chart** | Per team: all relievers, a **6-day usage grid** (pitches, SV/HLD/BS), 6-day IP and pitch totals, editorial roles (closer/setup/committee), "High Usage Alert" icons (20+ pitches, 2 straight days, 3 of 4 days), K%, BB%, SwStr%. Updated each morning. Daily written Bullpen Report. ([1], [2]) | Free; fantasy and analysts |
| **Inside the Pen** | **Closest direct competitor.** Availability table (status, fatigue, pitches, rest), usage grid, per-game matchup pages, last-5-outings panel. Premium adds a "Fatigue Factor", "Likely to Pitch" predictions and a beta live mode. ([3], [4]) | Freemium, $9.99/mo; fans, fantasy, betting |
| **ESPN Reliever Depth Chart** | Roles plus a "tired" flag (e.g. ≥25 pitches yesterday, ≥35 over 3 days) ([5]) | Free; fantasy |
| **Baseball Savant** | Unmatched pitch-level data and leaderboards. No bullpen-usage or rest tool found. | Free; analysts |
| **Baseball Reference** | Game logs and splits. No bullpen-usage view; requires manual assembly ([6]) | Free; researchers |
| **MLB.com** | "Bullpen availability" video segments (contents not verified); Gameday | Free; general fans |
| Closer Monkey, RotoWire Closer Grid, Pitcher List, FantasyPros, Fantrax usage chart, bettor fatigue boards (Cleatz, Tony's Picks) | Closer charts, written notes, team-level fatigue scores (often opaque) | Mostly fantasy and betting |

**Where BaseballOS wins today:**
- Descriptive and non-predictive with published receipts and methodology, plus a label backtest. No competitor found publishes a label-vs-outcome check.
- A team-level state that is explained by named arms.
- Combines rotation transfer, transactions, roles and workload on one page.
- Immutable, citable history of bullpen state.
- Two-bullpen comparison.

**Where it is merely equal, in a different format:** per-reliever recent pitches, rest and back-to-backs. FanGraphs provides this free, in a denser 6-day grid that writers already use.

**Where it loses:**
- No closer/late-inning answer.
- No probable starters.
- No dense multi-day grid at a glance.
- No performance context beyond team ERA/WHIP.
- Discoverability: no real team URLs and JS-redirect team pages.
- Brand recognition.

**Positioning conclusion.** BaseballOS should not try to beat FanGraphs on data breadth or Inside the Pen on prediction. Its defensible audience is **writers, broadcasters and serious fans who need a citable, pregame, one-page explanation of a bullpen's current situation and what changed**. The upgrades that strengthen that position are:
- named-arm What Changed;
- a descriptive late-inning block;
- a first-screen dense usage view;
- a copy-ready citation.

They are not more metrics.

---

## 7. Prioritized Upgrade Candidates

**Scoring.** Baseball value (BV), User impact (UI), Competitive differentiation (CD) and Reliability impact (RI) are scored 1–5, higher is better. Effort (EF) is scored 1–5, **higher means more effort**. Scores are my judgment, explained in each row; they are not measurements. Effort assumes the existing stack and a solo founder.

### P0 — Necessary for correctness, security, or reliable operation

| ID | Upgrade | BV | UI | CD | RI | EF | Op. cost | Dependencies | Confidence | Evidence and expected benefit |
|---|---|---|---|---|---|---|---|---|---|---|
| **P0-1** | **Green, honest, alerting pipeline.** Diagnose and fix the offseason `reference_date_alignment` failure. Re-validate and merge #911's two fixes (name masking; shadow summary normalisation). Either fix or stop the shadow lanes. Merge #911's public health check. | 3 | 3 | 1 | **5** | 2–3 | Low (one 6-hourly workflow) | P0-2 (so CI is meaningful) | High | Runs in §5.6. Restores daily publication and makes red mean broken. Without this, every other upgrade ships into an unobserved pipeline. |
| **P0-2** | **React Router v7 migration (#645)** and removal of the expired acceptances | 1 | 1 | 1 | 4 | 2 | None | — | High | §2.2. CI is red on every build; two moderate open-redirect/XSS advisories. |
| **P0-3** | **Throwing-hand ingestion fix + backfill + stop publishing handedness gaps as evidence.** Populate `throws` from `person.pitchHand` in the identity-creation paths. Run a one-time read-only plan, then a confirmed backfill from `/people`. | 3 | 3 | 2 | 4 | 1 | None | P0-1 for natural republication | High | `canonical_transaction_pitcher_acquisition.py:69-84`; `pitcher_identity_reconciliation.py:258`; 6,209 pages. Fixes a public evidence defect and unblocks handedness context. |
| **P0-4** | **2027 season-transition readiness.** Explicit competitive-game-type policy for workload and roles (exclude `S`/`E`). Season-driven History (no hardcode). Verified spring-to-Opening-Day state behaviour. One full rehearsal against spring-training data in March before Opening Day. | **5** at Opening Day | 4 | 2 | 5 | 3 | None | P0-1, P0-3 | Medium–High (the game-type risk itself is unverified) | §1 finding 4. Prevents an Opening Day repeat of the October EOS-001 incident. |
| **P0-5** | **Minimum security baseline.** Protect `main` with the automation bot allowlisted. Rate-limit or admin-gate `request-link`, the 3 diagnostics and the MLB proxy. Default CI permissions to read-only (in #911). Move production secrets to a GitHub `production` environment limited to the few workflows that need them. Run one backup restore drill. | 1 | 1 | 1 | 5 | 2 | Low | — | High | §5.6. A public repo with an unprotected `main` and the DB URL in 25 workflows is the largest blast-radius risk on the platform. |

### P1 — High-impact improvements to the core bullpen product

| ID | Upgrade | BV | UI | CD | RI | EF | Op. cost | Dependencies | Confidence | Evidence and expected benefit |
|---|---|---|---|---|---|---|---|---|---|---|
| **P1-1** | **Team Board first-screen refinement.** The Active Bullpen table with inline receipts as the first mobile screen. Merge Recent Usage, Rest Status and Workload Overview into one section. In-page section nav. Real `/team/:abbr` SPA route. Fix the teams-fetch failure state. | 4 | **5** | 4 | 2 | 3 | None | P0-2 (router work overlaps) | High | §3.3. The differentiator becomes usable on a phone in under 10 seconds. |
| **P1-2** | **Named-arm What Changed.** Activate arm-read and roster deltas: "X → Limited Rest after 31 P", "Y to IL". | **5** | **5** | **5** | 2 | 3 | None | O-011 decision; P0-1 (needs consecutive green publications) | Medium–High | §3.7. The strongest reason to return tomorrow; no competitor offers it. |
| **P1-3** | **Descriptive late-inning block.** "Finishing games / entries in the 8th or later, last 14 days", with counts, dates and receipts. No "closer" claim. | **5** | **5** | 4 | 1 | 3 | None | O-009 decision; P0-4 (phase-scoped roles) | Medium | §4 roles row. Answers the fans' first question descriptively, from data already stored. |
| **P1-4** | **Pregame context:** probable starters on Tonight and Matchup cards, final scores, linked key arms | 4 | 4 | 3 | 1 | 2 | None | — | Medium (assumes probables via schedule hydrate; not tested) | §3.1, §3.5. Starter length is the biggest driver of tonight's bullpen burden. |
| **P1-5** | **Failure-state and copy hygiene.** Map errors to human copy. Add H1s on Matchup and History error states. Fix the duplicate League Board error. Remove the jargon. Correct `Methodology.jsx:118`. | 1 | 4 | 2 | 3 | 2 | None | — | High | §3.12. Trust copy is undercut by "Failed to fetch". |
| **P1-6** | **Demand baseline readout** from the existing first-party traffic tables: external visitors, different-day returners, team-board repeats | 1 | 1 | 1 | 1 | 1 | None | — | High that it is missing; unknown what it shows | `services/traffic_reporting.py` exists; no number is recorded in the repo. Decides whether P1-2 or P1-3 should come first, and whether distribution work matters at all. |

### P2 — Valuable after foundations

| ID | Upgrade | BV | UI | CD | RI | EF | Notes |
|---|---|---|---|---|---|---|---|
| P2-1 | Compact league table on `/dashboard` (rested, B2B, 7-day relief P, starter length; sortable) | 4 | 4 | 3 | 1 | 2 | Replaces the grouped cards; reuses the published snapshot. |
| P2-2 | Per-arm season relief line on Pitcher and Team Board (G, IP, K%, BB%, SV/HLD), plus links out to Savant/FanGraphs | 3 | 3 | 2 | 1 | 2 | Needs an O-013 decision. Keep it context, not ranking. |
| P2-3 | Measure Team Board / `/dashboard` latency (server-timing, p95). Only if it exceeds budget, serve details from the per-team publication rows that already exist (`team_public_publications`). | 1 | 3 | 1 | 3 | 1→3 | Measurement first (EOS-014 is unmeasured). |
| P2-4 | Route-level code-splitting; drop admin and private code from the public bundle | 1 | 2 | 1 | 2 | 1 | Low-risk quick win. |
| P2-5 | Full-season label backtest published on Data & Trust; evaluate the `claude/upbeat-hawking-g0indq` work as its basis | 3 | 2 | 4 | 2 | 2 | A credibility asset that is unique in the market. |
| P2-6 | Consolidation: archive `feat/sync-pipeline` (tag + summary); archive about 20 one-off 2026 workflows and `*_2026` services; delete about 15 dead frontend modules, about 28 unused API functions and the unused `/prospects` and `/recommendations` routes; reduce Contract A to one implementation that the proofs import | 1 | 1 | 1 | 3 | 2–3 | Lowers the cost of every later change. Do it in small reviewed batches. |
| P2-7 | Publish a correction note for pre-#910 Team State artifacts (supersede via the existing manifest) | 2 | 2 | 2 | 3 | 2 | DEC-03-type decision required. |
| P2-8 | Distribution out of git: generate share and team pages only on change; serve metadata from the API or edge | 1 | 1 | 1 | 3 | 3 | Repository and deploy health. Not urgent while daily commits are small. |
| P2-9 | Retention policy for `fatigue_scores` and snapshots, after measuring table sizes | 1 | 1 | 1 | 2 | 2 | Measure first. |

### P3 — Optional, speculative, or low return

| ID | Upgrade | Why P3 |
|---|---|---|
| P3-1 | Velocity-under-workload context from stored pitch data | Interesting and partly unique, but needs methodology, has only half a season of data, and risks implying health inference. Revisit mid-2027. |
| P3-2 | 30-day / season workload windows, 4-in-6 density (O-012) | Marginal over the current windows. |
| P3-3 | Copy-ready citation line and embed for creators | Cheap, but its value is unknown until P1-6 shows a creator audience. |
| P3-4 | Offseason transactions feed for relievers | Moderate interest, but it widens scope during the quiet season. |

**Deliberately not scored:** a TypeScript migration, a new queue or worker infrastructure, live in-game updates, accounts and personalization. See §9.

---

## 8. Recommended Offseason Sequence

Four bounded initiatives, ordered by dependency. Each ends with natural production proof, not a merge.

**Initiative 1 — "Make red mean broken" (P0-2 → P0-1 → P0-3). About 2–3 weeks.**
1. React Router v7, so CI is meaningful again.
2. Rebase and re-validate #911; merge it.
3. Diagnose and fix `reference_date_alignment` for no-game days.
4. Decide on the shadow lanes (fix the validator, or set shadow to `off` until it is needed).
5. Fix throwing-hand creation; run the planned, confirmed backfill.
6. Close #909 with rationale and cherry-pick its three valid fixes.

*Exit:* seven consecutive scheduled cycles with all jobs green or explicitly skipped; a new snapshot published on its natural cadence; zero "missing throwing-hand" limitations for active relievers; the health check alerting on a deliberately stale read in a non-production test.

**Initiative 2 — Security baseline (P0-5). About 1 week, can run alongside Initiative 1.**
1. Branch protection compatible with the automation push.
2. A production environment for secrets.
3. Rate limiting or gating on the four endpoints.
4. One restore drill, recorded.

**Initiative 3 — 2027 season transition (P0-4). About 2–3 weeks, January–February; rehearsal in March.**
1. Game-type policy plus tests.
2. Season-driven History.
3. Spring-training behaviour: rosters and transactions visible, no Team State from `S`/`E` games.
4. An explicit Opening Day switch-on.
5. A dry run against real spring data.

**Initiative 4 — Team Board and daily reason to return (P1-6 → P1-1 → P1-2 / P1-3 → P1-4, P1-5). Remaining time to Opening Day.**
1. Read the demand baseline first.
2. Then the first-screen refinement.
3. Then whichever of named-arm What Changed or the late-inning block the founder decides (O-011 / O-009) after the readout.
4. Probable starters and failure-state hygiene are small and can slot in anywhere.

Everything in P2 waits until Initiative 1 has held for a natural week. Everything in P3 waits for in-season evidence.

---

## 9. What Not to Build

| Do not build (now) | Why |
|---|---|
| **Merge `feat/sync-pipeline` or finish the continuous / live-game lane** | Two replacement pipelines are already unfinished. The legacy writer works and its failures are specific and fixable. A live lane adds cost and risk for a pregame/postgame product. Archive it. |
| **New infrastructure** (queues, caches, Redis, workers, microservices, a new DB) | No observed problem requires it. Latency is unmeasured (measure first, P2-3). |
| **"Likely to pitch" / predictive availability / public fatigue score** | Violates the constitution. Inside the Pen already sells it. The descriptive posture is the differentiator. |
| **Leverage index model or custom WPA engine** | No authoritative public LI in the current sources; O-004 is unresolved. The descriptive late-inning block (P1-3) answers the user need without it. |
| **Pitch-analytics surfaces** (pitch mix, spin, movement pages) | Savant does this better. It broadens scope beyond bullpen state. |
| **Accounts, Follow My Team, newsletters, push, personalization** | No demonstrated retention evidence (O-006). The magic-link auth surface is already a liability without rate limits. |
| **Stories expansion / more editorial generators** | About 15 `story_*_v1` modules already exist; their value is unmeasured. |
| **Prospects** | Seed-only, unused, outside bullpen scope. Remove the routes (P2-6). |
| **TypeScript migration, design-system rewrite, framework change** | High cost, no user-visible benefit this offseason. Converge the two visual systems opportunistically through P1-1. |
| **Public API, exports, embeds, sponsorship and monetization tests** | Parked until P1-6 shows demand. |
| **Additional governance documents or audit series** | The canonical ledger already lags the code by two months. Update the existing ledger once after Initiative 1, instead of adding documents. |
| **Rebuilding the Team Board** | The read model and section isolation are sound. Refine presentation only (P1-1). |
| **Changing the Team State rule or vocabulary** | Simple and explainable. Validate it with the backtest instead of re-tuning it. #909's alternative semantics should not be revived. |

---

## 10. Risks and Unknowns

| Unknown | Why it matters | How to resolve |
|---|---|---|
| Live public experience (all surfaces) | Product findings are code- and build-based | Allow `baseballos.app` in the session network, or run the existing Playwright suite against production |
| Root cause of the 10-30 availability reference date | Determines whether P0-1 is a one-line date-owner fix or a deeper phase-model change | Read-only diagnosis of the date authorities on the 11-17 summary |
| Shadow validator per-check detail | Whether to fix the shadow lanes or switch them off | Download the run artifact |
| Whether spring or exhibition games enter workload | P0-4 scope | A test with an `S`-type boxscore through the postgame path |
| Production table sizes and egress | Whether retention (P2-9) is urgent | Read-only size queries |
| Team Board / dashboard latency | Whether P2-3 is needed | Server-timing measurement |
| Backup and PITR status on Supabase | Recovery assurance | Provider dashboard plus a restore drill |
| Render cron configuration | Lives outside the repo; cannot be audited | Export it into the repo as documentation |
| Actual usage and returners | Prioritization between P1-2 and P1-3, and whether distribution matters | P1-6 |
| Competitor details | From search snippets only | Manual review |
| Whether the APScheduler `AUTO_SYNC` is set on Render | Possible duplicate writer | Render environment check |
| Opening Day 2027 date | Sequence timing | MLB schedule (not verified here) |

---

## 11. Evidence Register

**Commit basis:** `a16209afc5356f1fc229e24bd7bf9001757b5cf0` (`main`, 2026-11-18). Previous distribution commit: `7a5fde1e` (2026-11-11, Snapshot 5827, data through 2026-10-28).

**Code**

| Topic | Location |
|---|---|
| Team State rule | `backend/team_operations/bullpen_readiness.py:487-644`; `backend/team_operations/contracts.py:67-98` |
| Data gate (handedness) | `backend/team_operations/bullpen_readiness.py:348-373,515-560` |
| Availability ladder | `backend/services/availability.py:31,50-80,139-177,245-317` |
| Fatigue | `backend/services/fatigue.py:43-69,191-216,228` |
| Roles | `backend/services/role_authority.py:64-70,102`; `backend/services/pitcher_role.py:28-57` |
| Throwing-hand defect | `backend/seed.py:93`; `backend/services/canonical_transaction_pitcher_acquisition.py:69-84`; `backend/services/pitcher_identity_reconciliation.py:258-278`; `backend/models/pitcher.py:20` |
| Publication | `backend/services/dashboard_snapshot.py:331-495`; `backend/services/sync_metadata.py:137-325`; `backend/services/team_state_vnext_production_proof.py:20-30,329-352,1205-1213` |
| Competition status | `backend/services/club_competition_status.py:84,172` |
| Season hardcodes | `frontend/src/components/history/TeamHistoryPage.jsx:448`; `frontend/src/utils/api.js:542`; `backend/api/team_history.py:16`; `backend/services/availability_backtest.py:35` |
| MLB client | `backend/services/mlb_api.py:20-30,181-350,562-577,618-630` |
| Sync | `backend/services/sync.py:118,436-455,3858-4065,4634-4699,4691` |
| Pitch data | `backend/models/play_by_play_foundation.py:183-226`; `backend/services/play_by_play_foundation.py:794` |
| Auth / security | `backend/api/auth.py:43-59`; `backend/utils/auth_tokens.py:13-110`; `backend/api/bullpen.py:2646,2780,2849,3796-3812`; `backend/app.py:86-88,125-139,215-246,288`; `backend/config.py:78,96-102,203-219` |
| Claim-guard defect | `backend/services/evidence_language.py:38` |
| Workflows | `.github/workflows/baseballos-sync.yml:3-6,33-41,131-133,140,161-191,270,323,964-965,1299-1304`; `.github/workflows/ci.yml`; `.github/dependency-audit-accepted.json` |
| Frontend | `frontend/src/App.jsx:32-57`; `Dashboard.jsx:56-60,72-93`; `TonightsBullpenBoard.jsx:60,133-160`; `MatchupPage.jsx:19-24`; `PitcherDetail.jsx:102,119-120`; `Methodology.jsx:118`; `Stories.jsx:92`; `hooks/useFetch.js:54`; `utils/api.js:360-441`; `frontend/vercel.json`; `frontend/public/robots.txt` |
| Performance metrics | `backend/services/performance_metrics.py:75-103` |

**Executed in this session**
- `flask db upgrade` on a disposable local PostgreSQL 16 (single head `a7c3e9f1d2b5`).
- `scripts/ci_shard.py verify` (PASS).
- The backend pytest suite in 4 shards (see §2.3).
- `npm ci`, `npm test` (1,303/1,303), `npm run build` (707.98 kB single chunk).
- `npm audit --omit=dev` plus `verify_dependency_audit.py` (FAIL, 3 expired).
- Headless Chromium against `vite preview` at 390 px and 1280 px, with the API aborted and with repository fixtures.
- `grep` counts over `frontend/public/share` (6,209 handedness-evidence pages).

**GitHub (retrieved 2026-11-18)**
- Sync runs: 44281693317, 44190544519, 44155845626, 44066699503, 43950384156, 43616548098, 43739811835, 43475897204, 43278766091, 41297054942, 41518566489, 42080329415, 40727951878, 38227789525.
- Jobs: 134296232317, 134724304149, 134724304248, 134300933289.
- CI runs: 42102540444 (last green), 44305413660 (dependency-audit fail).
- Distribution run: 43001135457.
- PRs #909, #911, #913.
- Issues #589, #596, #597, #645, #662, #906.
- Branch protection: 404 / rulesets `[]`.

**Repository documents consulted (as context, not as proof of current behaviour)**
- `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md` (v5.16, Sep 4)
- `docs/current/REPOSITORY_HANDOFF_BASELINE.md`
- `docs/current/SYNC_PIPELINE.md`
- `docs/audits/2026-end-of-season/wp01/WP-0.1_CURRENT_READ_INTEGRITY.md`
- branch `audit/2026-end-of-season-platform-audit` (`988421e7c`, 10-29)

**External references (search results, 2026-11-18)**
- [1] https://blogs.fangraphs.com/fangraphs-feature-focus-closer-depth-chart/
- [2] https://fangraphs.com/roster-resource/closer-depth-chart/braves
- [3] https://insidethepen.com/bullpen-availability-today.html
- [4] https://insidethepen.com/premium.html
- [5] https://www.espn.com/fantasy/baseball/flb/story/_/page/REcloserorgchart
- [6] https://baseballreplayjournal.substack.com/p/baseball-reference-and-pitching
- Also: https://baseballsavant.mlb.com/leaderboard/pitch-arsenals?year=2026 · https://cleatz.com/mlb-bullpen-fatigue/ · https://closermonkey.com/

---

## 12. Final Recommendation

### The single most valuable next objective

**Make the existing daily pipeline publish correctly and visibly from today through Opening Day 2027.** This is Initiative 1, carried through the season-transition checks of Initiative 3.

**Justification.** Every product strength BaseballOS has depends on one thing: a correct read published on time.
- That is not happening today: no new snapshot since 11-11, daily publication failing since 11-12.
- Failure is invisible: three jobs are red by habit, there is no alerting, and CI is red on every build.
- The next natural stress test is Opening Day, when every arm returns from a five-month layoff, spring games sit in the source data, and the date authorities that already disagree on no-game days must all agree.
- A named-arm What Changed or a better Team Board built on this foundation would publish nothing, or publish something wrong, on the day that matters most.

The fixes are specific, mostly located, and partly already written (#911). The return per unit of effort is the highest on the platform.

### Proposed acceptance criteria

1. CI on `main` is green, including `dependency-audit`, with **no** renewed risk acceptance for the React Router advisories.
2. PR #911 is re-validated against current `main` and merged. PR #909 is closed with a recorded rationale, and its three still-valid defects are fixed or ticketed.
3. The `reference_date_alignment` failure has a written root cause and a fix with a regression test that covers a no-game day, a single-game day and the first day after a multi-day gap.
4. **Seven consecutive naturally scheduled sync cycles** in which `public-sync`, `internal-enrichment` and the shadow job (or its explicit removal) are green or explicitly skipped by design, and a new trusted snapshot is published on its natural cadence. No manual dispatch, replay or forced publication is used as evidence.
5. An external health check runs on schedule and is proven to alert, in a non-production test, on a stale `data_through`, a missed publication and API unavailability.
6. Every active reliever on all 30 clubs has a stored throwing hand. New pitcher creation populates it (regression test). Newly published artifacts carry no "missing throwing-hand data" limitation for active relievers.
7. A written, tested competitive-game-type policy exists: an `S`/`E` appearance cannot change workload, arm read, role or Team State. History requests the backend's current season. A dated spring-training rehearsal confirms the Season Complete → spring → Opening Day state sequence before the first regular-season game.
8. The canonical ledger is updated once to reflect #880–#913 and this objective's closeout. No new canonical document is created.
