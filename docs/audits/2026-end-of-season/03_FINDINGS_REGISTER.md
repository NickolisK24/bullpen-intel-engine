# 03 — Findings Register

**Audit:** BaseballOS 2026 End-of-Season Platform Audit
**Audit date:** 2026-10-29 (World Series in progress: Milwaukee vs Tampa Bay)
**Repository state:** `main` @ `0c90be9b` (shallow clone, 64 commits, 2026-10-02 → 2026-10-28)
**Mode:** Read-only. No production system, database, configuration, branch, or deployment was changed.

This is the single numbered register for the audit. Every other deliverable cites
these IDs. The register is split into three parts:

- **Part A: Confirmed defects.** Something is wrong today.
- **Part B: Missing capabilities.** Something required for 2027 does not exist.
- **Part C: Optional improvements.** Worth doing, not required.

## Conventions

**Verification status**

| Status | Meaning |
|---|---|
| VERIFIED | Directly demonstrated: code read, test run, production artifact, or GitHub API response |
| INFERRED | Supported by indirect evidence |
| UNVERIFIED | Insufficient access or evidence |
| NOT IMPLEMENTED | Confirmed absent |
| BLOCKED | Verification needs access this audit did not have (production, MLB API, Render, Vercel, Supabase) |

**Severity**

| Severity | Meaning |
|---|---|
| Critical | Public baseball claims are false, or a credible path to unrecoverable loss exists |
| High | Materially degrades correctness, reliability, security, or 2027 viability |
| Medium | Real weakness with bounded impact |
| Low | Hygiene |

**Effort:** S ≤ 2 engineer-days · M 3–7 days · L 8–15 days · XL > 15 days. This assumes one founder-engineer already familiar with the codebase.

**Production evidence used throughout.** The repository contains production outputs:

- **Generated route-preview pages.** `frontend/public/team/<ABBR>/index.html` and `frontend/public/share/<id>/index.html` are generated from the trusted production snapshot and committed by `BaseballOS Automation`. Their commit trailers record `Snapshot-ID`, `Data-Through` and `Workflow-Run`. This audit treats them as VERIFIED production publications.
- **GitHub Actions run history** for Oct 7–28, read through the GitHub API.

---

# Part A — Confirmed Defects

### EOS-001 — Inactivity is scored as bullpen constraint
- **Category:** Baseball intelligence
- **Severity:** Critical
- **Status:** VERIFIED (code and production artifacts)
- **Evidence:**
  - `backend/services/availability.py:206-220` labels an arm `stale` when its last appearance is more than 14 days before the reference date.
  - `availability.py:391-399` returns `STATUS_MONITOR` (public: *On Watch*) for stale arms; `:367-375` does the same for `missing`.
  - `backend/team_operations/bullpen_readiness.py:490-502` places Monitor in the *moderate* bucket, so these arms are never *clean*.
  - `bullpen_readiness.py:599` combined with `team_operations/contracts.py:76`: `clean_count <= 2` gives **Vulnerable** (`operationally_stressed`).
  - Production results, from the committed `frontend/public/team/*` history:

    | Data-through | Fresh | Stretched | Vulnerable |
    |---|---|---|---|
    | 2026-10-01 | 25 | 5 | 0 |
    | 2026-10-10 | 6 | 15 | 9 |
    | 2026-10-11 | 3 | 8 | 19 |
    | 2026-10-27 (snapshot 5656) | 1 | 1 | 28 |

  - Washington, whose last game was 2026-09-27, went from *Stretched* to *Vulnerable* in the data-through-2026-10-11 publication. That is exactly 14 days after its last game. Its On-Watch count rose from 9 to 19.
- **Consequence:**
  - BaseballOS publicly told readers that fully rested bullpens were "Vulnerable" and had "fewer clean options available after recent work". That is false.
  - It breaks Constitution 01:140 ("quieter under uncertainty, never wronger"), Intelligence Standard 02:676 ("Staleness degrades scope. It never silently degrades accuracy") and 02:685 ("A stale value is never presented as current").
  - The same defect hits any idle stretch: injured-list returns, the All-Star break if an arm sits out, and Opening Day 2027, when every reliever's last appearance will be about five months old.
- **Root cause:**
  - "No recent observation" and "recent workload constraint" are collapsed into one status.
  - The trust gate treats an old appearance as valid *observed rest* (`api/team_operations.py:509-523`, decision 2026-07-24 "Rest ≠ stale"), but the state classifier treats it as *not clean*.
- **Proposed resolution:**
  - Separate the two axes. An arm with no appearance inside the window is *rested by absence*: an observable fact, not a constraint.
  - During an active competitive window it should count toward clean coverage, carrying a "no recent appearances" qualifier.
  - Outside an active window (EOS-002), no current Team State is published at all.
  - This needs an amendment to Standard 02 (see DEC-02).
- **Dependencies:** DEC-01 and DEC-02. Implement together with EOS-002.
- **Effort:** M
- **Acceptance criteria:**
  1. A fixture with a club idle for 15, 30 and 150 days yields no *On Watch*, *Limited Read*-as-constraint or *Vulnerable* driven by inactivity.
  2. Replaying the snapshot-5656 inputs gives no "Vulnerable" for a club whose last game was more than 14 days earlier.
  3. A regression test asserts that the `stale` data state never enters the moderate or severe partition.

### EOS-002 — No season-phase or club-status model; idle and eliminated clubs are published as current pregame reads
- **Category:** Baseball intelligence / publication
- **Severity:** Critical
- **Status:** VERIFIED
- **Evidence:**
  - `backend/services/availability_reference_date.py:99-143` computes **one league-wide** reference date, which advances only across league-wide no-game days.
  - During the postseason, every club, including the 18 that never qualified, is read "as of" the next postseason day.
  - A grep for offseason / season-state / eliminated finds only:
    - `slate_coverage.py:48`, where the offseason is the months {1, 2, 11, 12}, so October is "in season";
    - an offseason skip message at `sync.py:7340-7349`.
  - There is no notion of regular season / postseason / complete / offseason / spring, of a club being eliminated, or of "no next game" anywhere in intelligence, publication or frontend (frontend grep: `04_frontend` notes §5).
  - Published copy for Washington, 2026-10-28, share `178c7a7f…`: *"The Washington Nationals' bullpen has fewer clean options available after recent work." Data through October 27, 2026.*
- **Consequence:**
  - A month-old roster state is presented as a current operating read, dated with *yesterday's* league data-through date.
  - A reader cannot tell that the club's season ended weeks earlier.
  - This is precisely the failure the audit brief warned against.
- **Root cause:**
  - The product was designed for a 30-club daily slate and never modelled seasonality.
  - `data_through` is league-wide freshness, not club-level baseball context.
- **Proposed resolution:**
  - Introduce a backend-owned season-phase contract: `regular_season`, `postseason`, `season_complete`, `offseason`, `spring_training`, `opening`.
  - Add a per-club competitive status: `active`, `eliminated(at date)`, `champion`, `not_qualified`.
  - Team State and arm reads are published only for clubs in an active competitive window.
  - All other clubs show "Season complete. Final read: <last game date>" plus archive links.
  - See DEC-01 and roadmap WP-0.1 / WP-1.1.
- **Dependencies:** DEC-01.
- **Effort:**
  - S for the emergency suppression;
  - M for the full phase model.
- **Acceptance criteria:**
  1. With the schedule as of 2026-10-28, exactly 2 clubs (MIL, TB) receive a current read. The other 28 render a season-complete state carrying their final regular-season or postseason game date.
  2. No public string pairs a non-active club with "today", "tonight" or "after recent work".
  3. The phase is served by the API and the frontend renders it without deriving it.

### EOS-003 — Frozen share artifacts permanently record the defective October claims
- **Category:** Publication integrity / editorial
- **Severity:** High
- **Status:** VERIFIED
- **Evidence:**
  - Of the committed `frontend/public/share` pages with data-through ≥ 2026-09-29, there are **1,436 `team_state` artifacts: 747 Vulnerable, 393 Fresh, 296 Stretched**.
  - Each page states "Frozen historical observation … preserved as a historical artifact".
  - The `share_artifacts` model already carries `superseded_at`, `withdrawn_at` and `withdrawn_reason` (`backend/models/share_artifact.py:240-242`). No correction has been issued.
- **Consequence:**
  - Permanent citation destinations carry claims BaseballOS would not stand behind.
  - Under the Constitution's correction rule ("Corrections preserve history … superseded or withdrawn rather than edited in place"), these need a visible correction.
- **Root cause:** EOS-001 and EOS-002, plus the absence of a plausibility gate (EOS-004).
- **Proposed resolution:**
  - After EOS-001 and EOS-002 ship, run a governed correction.
  - Mark the affected artifacts *superseded*, with a public correction note and a link to the corrected archive read. Do not delete them.
  - Re-export their static pages.
- **Dependencies:** EOS-001, EOS-002, DEC-03.
- **Effort:** S–M
- **Acceptance criteria:**
  1. Every team-state artifact for a non-active club with product date after that club's final game shows a correction banner.
  2. The integrity hash of the original payload is unchanged.
  3. The correction is listed on the Data & Trust page.

### EOS-004 — Publication plausibility gate accepts a 28-of-30 Vulnerable league
- **Category:** Publication integrity
- **Severity:** High
- **Status:** VERIFIED
- **Evidence:**
  - `backend/services/team_state_vnext_production_proof.py:641`: `distribution_degenerate = bool(teams) and counts['fresh'] == 0`, so a league with 1 Fresh club passes.
  - This check lives in the *proof* path. In run 40656367563 the "Export durable Team State production proof" step was **skipped**.
  - The June 2026 audit recorded the same failure class: 704 of 704 arms Monitor (`docs/governance/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md:39-41`).
- **Consequence:**
  - A systematically wrong league picture publishes for weeks.
  - No human was alerted.
- **Root cause:** Gates validate structure and completeness, not baseball plausibility.
- **Proposed resolution:**
  - Add publication-blocking plausibility checks on the trusted path, separate from the proof export:
    1. A day-over-day league distribution shift greater than 2σ of the 2026 history.
    2. More than 50% of active clubs Vulnerable.
    3. Any club Vulnerable whose decisive inputs are majority `stale` or `missing`.
    4. Any current read for a club outside its active window (EOS-002).
  - A blocked publication alerts (EOS-008) and keeps serving the previous trusted snapshot.
- **Dependencies:** EOS-008 for alerting.
- **Effort:** S–M
- **Acceptance criteria:** Replaying snapshots 4731 (data-through 2026-10-10) through 5656 through the gate blocks or alerts on every one of them.

### EOS-005 — Public explanation names the wrong cause and cites irrelevant evidence
- **Category:** Baseball intelligence / editorial
- **Severity:** High
- **Status:** VERIFIED
- **Evidence:**
  - `backend/services/team_story_previews.py:256-263` always ranks a nonzero "Unavailable" count first. That count includes *Avoid* (`bullpen_board.py:206, 236-242`).
  - So the MIL and TB pages say "Vulnerable. One reliever is Unavailable", while the decisive rule is `clean_count <= 2` (EOS-001).
  - The Washington artifact's only "Evidence behind the read" is "4 active relievers are missing throwing-hand data", a data-quality note that has nothing to do with the claim.
  - The board's "N relievers are in the On Watch group" count comes from a different population and classifier than Team State (`publication_truth_certification.py:544-568`; EOS-018).
- **Consequence:**
  - The "I can see why it is true" promise (README) fails.
  - An analyst checking the evidence finds it does not support the claim.
- **Root cause:** Explanation copy is selected by a separate ranking, not derived from the decisive rule that produced the state.
- **Proposed resolution:**
  - The decisive rule (`DECISIVE_RULE_*` in `bullpen_readiness.py`) and its inputs become the mandatory first evidence item, with named arms.
  - Data-quality notes become limitations, never evidence.
- **Dependencies:** EOS-001
- **Effort:** S
- **Acceptance criteria:**
  1. For every published Team State, evidence item #1 restates the decisive rule with its counts and the named arms.
  2. A test fails if any evidence item's key belongs to the data-quality family.

### EOS-006 — Roles are built from regular-season logs only; postseason arms decay to "Role Unclear"
- **Category:** Baseball intelligence
- **Severity:** High
- **Status:**
  - VERIFIED in code.
  - INFERRED for public effect: production role payloads were not observable.
- **Evidence:**
  - `backend/services/pitcher_role_authority.py:76-109` keeps only `game_type == 'R'`.
  - The 21-day confirmation window (`pitcher_role.py:33`) and the stale flag (`:157-158`) then cap confidence at low (`:405-407`), which maps to Role Unclear.
  - `bullpen_eligibility.py:47-64, 107-122` flags active postseason arms as low-confidence "inactive context".
  - By contrast, workload windows include postseason games, because there is no game-type filter (`availability_snapshot.py:195-245`).
- **Consequence:**
  - World Series relievers working nightly can read as Role Unclear, while their workload correctly counts.
  - The product's deepest October bullpen moments are where its role intelligence is weakest.
- **Root cause:** Performance policy ("season ERA excludes postseason", Standard 02:269) was applied to deployment evidence, where it does not belong.
- **Proposed resolution:**
  - Phase-scoped role evidence. Postseason deployment is valid role evidence *within* the postseason phase, and role movement already refuses cross-phase comparison (`role_movement.py:26, 133-135`).
  - Keep the ERA and WHIP exclusion.
- **Dependencies:** EOS-002 (phase model)
- **Effort:** M
- **Acceptance criteria:** A fixture of a closer with 6 postseason saves in 10 days and his last regular-season save 25 days earlier yields Trusted Arm with non-low confidence during the postseason.

### EOS-007 — The sync workflow is red by construction (shadow validator reads the wrong summary shape)
- **Category:** Operations / pipeline
- **Severity:** High
- **Status:** VERIFIED (code and the GitHub Actions API)
- **Evidence:**
  - "BaseballOS Bullpen Sync" scheduled runs between 2026-10-07 and 10-28: **22 success, 43 failure**.
  - In failed run 40656367563, job `public-sync` **succeeded** and job `shadow-activation-health` failed with `Activation health is FAILED (reason=validator_reported_failure)`.
  - Root cause in code:
    - `backend/scripts/run_due_sync.py:77-84` writes `{status, mode, …, result:{…}}` with status `executed` or `already_satisfied`.
    - `backend/scripts/validate_game_driven_shadow_cycle.py:142-150` reads `summary['sync']['status']` or `summary['status']` and requires `sync_metadata.SUCCESSFUL_STATUSES`, so it always fails.
    - It also reads a top-level `publication_proof`, which is absent.
  - The only "successful" runs are the 14:23 UTC morning slot, which has no shadow job (`baseballos-sync.yml:718`).
- **Consequence:**
  - Red is the normal state, so a real publication failure is visually identical to the daily noise.
  - The shadow-lane qualification evidence that decisions D-034/D-040 rely on has not actually been validated since the Render-primary cutover (INFERRED: late August).
- **Root cause:** `run_due_sync.py` replaced the legacy runners without updating the downstream validator. The validator's tests use only the legacy shape.
- **Proposed resolution:** Choose one:
  - adapt the validator to the `run_due_sync` shape and add a contract test; or
  - preferred, per DEC-04: remove the shadow-activation job while the shadow lane is retired.
- **Dependencies:** DEC-04
- **Effort:** S
- **Acceptance criteria:**
  1. Seven consecutive days of scheduled runs are green unless public-sync fails.
  2. A contract test feeds the real `run_due_sync` summary into any remaining consumer.

### EOS-008 — No backend alerting or monitoring; failures reach no one
- **Category:** Operations
- **Severity:** High
- **Status:** NOT IMPLEMENTED (VERIFIED absence)
- **Evidence:**
  - No Slack, email, PagerDuty, webhook or Sentry integration in backend code or workflows.
  - `backend/scripts/check_scheduled_sync_health.py` is manual-only.
  - Frontend Sentry is active only if `VITE_SENTRY_DSN` is set (`frontend/src/utils/errorMonitoring.js:86`); its production value is UNVERIFIED.
  - Render Cron jobs are configured in the Render dashboard only; there is no `render.yaml`.
  - The prior audit's F-04 (2026-09-24) recorded the same gap, and it is unchanged.
- **Consequence:**
  - The September 10–21 stale-publication incident and the October drift (EOS-001) both ran for days to weeks undetected.
  - Combined with EOS-007, the founder has no usable failure signal.
- **Root cause:** Alert routing was described as "external" and never built.
- **Proposed resolution:**
  - One external synthetic check, such as a free uptime service or a GitHub scheduled job hitting the public API.
  - It alerts by email or phone when:
    1. served `data_through` is older than the club-phase-appropriate maximum;
    2. no publication occurs inside the expected window on a game day;
    3. the API is unhealthy;
    4. the plausibility gate (EOS-004) blocks.
  - Add backend Sentry, or an equivalent, for unhandled exceptions.
- **Dependencies:** None
- **Effort:** S
- **Acceptance criteria:** Deliberately pausing the daily cron in a test environment, or simulating a stale `data_through`, produces an alert within 6 hours.

### EOS-009 — Backups, restore and staging are undocumented and unproven
- **Category:** Operations / data durability
- **Severity:** High. It escalates to Critical if backups are found absent.
- **Status:**
  - UNVERIFIED for backup existence: Supabase and Render were not accessible.
  - NOT IMPLEMENTED for any repository procedure.
- **Evidence:**
  - No `pg_dump`, PITR, restore or disaster-recovery runbook anywhere in the repository.
  - `PRODUCTION_MIGRATION_AUTHORITY.md` treats a database restore as "a separate incident decision".
  - No staging environment: only development, test and production configurations exist.
  - Repairs run directly against production behind dry-run and fingerprint gates.
  - The production database is INFERRED to be Supabase Postgres, from RLS migration `e5b9c3a7d1f4`.
- **Consequence:**
  - The entire 2026 season record — appearance ledger, roster history, transactions, published snapshots and share artifacts — lives in one database with no proven recovery path.
  - Its value compounds into 2027 ("year two"), and that value is unrecoverable if lost.
- **Root cause:** Durability was assumed to be the provider's job.
- **Proposed resolution:**
  - Confirm the provider's PITR tier.
  - Take an off-provider logical dump of the canonical tables now, before any offseason refactor.
  - Write a one-page restore runbook and run a restore drill into a scratch database.
- **Dependencies:** None. This is a Phase 0 blocker for every other data-touching change.
- **Effort:** S
- **Acceptance criteria:**
  1. A restore of last night's dump into a scratch database reproduces exactly:
     - the `game_logs` row count for 2026;
     - the `scheduled_games` final count;
     - the `share_artifacts` count.
  2. The runbook is committed.

### EOS-010 — Repository and credential exposure
- **Category:** Security
- **Severity:** High
- **Status:** VERIFIED through the GitHub API and workflow files. Impact INFERRED.
- **Evidence:**
  - The repository is **public**, and `main` has **no branch protection and no rulesets** (`list_branches`: `"protected": false`).
  - The production `DATABASE_URL` is provided to **25 of 27** workflows. That includes "read-only" diagnostics, where read-only is enforced only in Python.
  - No workflow uses a GitHub `environment:`. In-workflow `refs/heads/main` checks can be bypassed by pushing a branch with an edited workflow.
  - `SECRET_KEY` signs user tokens when `USER_AUTH_SECRET` is unset (`backend/config.py:157-160`).
  - The Render-held `BASEBALLOS_DISTRIBUTION_GITHUB_TOKEN` has Actions:write. A fine-grained token cannot scope that to one workflow.
  - 20 of 27 workflows are one-off 2026 repair or diagnostic workflows; 8 of them can write.
- **Consequence:**
  - Anyone with push access, or a stolen owner credential, gets production database read/write and auto-deploying code.
  - The blast radius is the whole platform.
- **Root cause:** Repo-wide secrets plus no branch protection, accumulated over a season of incident-driven workflows.
- **Proposed resolution:**
  1. Protect `main` (allow the automation bot until DEC-05 removes bot commits).
  2. Move production secrets into an environment restricted to `main`, with required reviewers for write-mode workflows.
  3. Create a read-only database role for diagnostics.
  4. Set a distinct `USER_AUTH_SECRET`.
  5. Delete the closed one-off workflows.
- **Dependencies:** DEC-05 for bot commits.
- **Effort:** S–M
- **Acceptance criteria:**
  1. A workflow on a non-`main` branch cannot read the production secrets.
  2. `main` rejects direct pushes from non-allowlisted actors.
  3. The workflow count is ≤ 8.

### EOS-011 — No rate limiting; sign-in endpoint creates users and sends mail for any address
- **Category:** Security / abuse
- **Severity:** High
- **Status:** VERIFIED
- **Evidence:**
  - `backend/api/auth.py:45-61`: `POST /api/auth/request-link` creates a `User` row *before* verification and sends mail.
  - `services/audience_signup.py:86-126` sends a welcome email with no double opt-in.
  - `api/traffic.py:42-95` accepts unauthenticated inserts.
  - There is no rate limiting or request-size limit anywhere.
  - The API runs 2 Gunicorn workers with a 60-second timeout (`scripts/render_start.sh:80-84`).
  - Unchanged since prior audit F-17.
- **Consequence:**
  - Email-bombing third parties burns sender reputation and quota, and once quota is exhausted no one can sign in.
  - Table growth.
  - Easy saturation of 2 workers.
- **Root cause:** No abuse model.
- **Proposed resolution:**
  - Per-IP and per-email limits (for example, Flask-Limiter with a Postgres or in-memory store).
  - Do not create a user before verification.
  - Global `MAX_CONTENT_LENGTH`.
  - Remove the unused public MLB proxy routes (`api/bullpen.py:3758-3790`).
- **Dependencies:** None
- **Effort:** S
- **Acceptance criteria:**
  1. The 6th `request-link` call for one email within an hour returns 429.
  2. No `users` row exists before link verification.

### EOS-012 — Accepted React Router risk expires 2026-11-13; CI will refuse every build
- **Category:** Dependencies / delivery
- **Severity:** High (date-bound)
- **Status:** VERIFIED
- **Evidence:**
  - `docs/decisions/2026-08-13-react-router-v7-security-defer.md:4`: "Expires 2026-11-13".
  - `.github/dependency-audit-accepted.json` sets the same expiry.
  - `backend/tests/test_dependency_audit_gate.py:54, 288`: 2026-11-13 is the first refused day.
  - `frontend/package.json:16`: `react-router-dom ^6.30.4`.
  - Production `npm audit --omit=dev` shows 2 moderate advisories, react-router and react-router-dom.
  - Roadmap queue item 7 (#645) is OPEN.
- **Consequence:**
  - From 2026-11-13, CI fails for every change, including fixes for EOS-001 and EOS-002.
  - Production is unaffected.
- **Proposed resolution:**
  - Migrate to React Router v7, which is API-compatible for the v6 feature set used, before 2026-11-10.
  - Alternatively, record a re-reviewed acceptance with a new expiry. That is a founder decision; see DEC-13.
- **Effort:** S–M
- **Acceptance criteria:** CI passes with the system clock set to 2026-11-14.

### EOS-013 — Generated distribution commits ~60 HTML pages a day to `main`; 10,042 share pages (119 MB) ship in every deploy
- **Category:** Architecture / distribution
- **Severity:** High
- **Status:** VERIFIED
- **Evidence:**
  - 47 of the 64 visible commits are `BaseballOS Automation` (`docs: publish generated route preview pages`), about 2 a day.
  - Each modifies the 30 `frontend/public/team/*` files and adds 30–47 new `frontend/public/share/*` directories.
  - Exactly 30 are added even on no-game days, because artifacts are generated **per publication, not per change**.
  - `frontend/public/share`: 10,042 directories, 119 MB. It was 7,873 / 93 MB on 2026-09-24 (prior audit F-28).
  - The built `dist` is 120 MB across 10,100 files.
  - `vercel.json` has no `ignoreCommand`, so every bot commit triggers a full deploy (INFERRED).
  - Bot pushes rely on `main` being unprotected (EOS-010).
- **Consequence:**
  - Unbounded repository and deploy growth: about 1,800 pages a month in season.
  - Twice-daily production redeploys driven by data, not code.
  - Possible redeploy of Render services on HTML-only commits (INFERRED).
  - The share archive is mostly identical duplicates; for example, 30 identical Washington reads in October.
- **Root cause:** Static-file distribution chosen for crawler-visible metadata (D-053), with no change detection and no storage tier.
- **Proposed resolution (DEC-05):**
  1. Generate share artifacts only when a club's public read *changes*, using the existing `equivalence_key`.
  2. Serve `/share/{id}` and `/team/{ABBR}` metadata from the API or an edge function instead of git.
  3. Move the historical pages to object storage.
  4. Stop bot commits to `main`.
- **Dependencies:** EOS-010 (branch protection after the bot is removed)
- **Effort:** M
- **Acceptance criteria:**
  1. Zero data-driven commits to `main` for 14 days.
  2. Every `/share/{id}` URL from the 10,042-page corpus still resolves with identical Open Graph metadata.
  3. No new artifact is created for an unchanged read.

### EOS-014 — Team Board deserializes the whole ~16.5 MB dashboard snapshot on every request; latency never measured
- **Category:** Performance
- **Severity:** High
- **Status:**
  - VERIFIED for the code path.
  - UNVERIFIED / BLOCKED for latency: production was unreachable.
- **Evidence:**
  - `backend/api/team_board_v2.py:47-58` calls `get_latest_valid_dashboard_snapshot()`, which loads the full row (`services/dashboard_snapshot.py:903-932`).
  - The board then selects one team (`public_serving_authority.py:863`) and deep-copies sections.
  - `board-v2/details` loads it again (`team_board_delivery.py:153-163`), and so does Compare.
  - The payload size of 16.5 MB comes from `docs/audits/daily-primary-memory-incident-2026-09-29.md:37`.
  - A JSON-path projection helper already exists (`dashboard_snapshot.py:1126`) and is used by Tonight, but not by the Board.
  - The per-team `team_public_publications` table is not used for serving.
  - No latency measurement exists anywhere in the docs; only request counts (PRE-02B) are recorded.
- **Consequence:**
  - The product's centre of gravity likely has multi-hundred-millisecond to multi-second server time, and memory spikes on a 2-worker service.
  - The historical "significant Team Board latency" lead remains plausible and unresolved.
- **Root cause:** A league snapshot is used as the per-team read model.
- **Proposed resolution:**
  - Serve the board from a per-team pre-assembled row, using `team_public_publications` or a JSON-path projection, keyed by snapshot.
  - Add server-timing headers and a p95 budget.
- **Dependencies:** None
- **Effort:** M
- **Acceptance criteria:** On production-size data, the board API p95 is under 300 ms warm and under 1.5 s cold, measured by an executable script (see `07` G-4).

### EOS-015 — No retention policy for snapshots, publications, fatigue scores or traffic rows
- **Category:** Database
- **Severity:** Medium
- **Status:** VERIFIED (absence)
- **Evidence:**
  - Nothing deletes from `dashboard_snapshots`, `team_public_publications`, `tonight_publications`, `fatigue_scores` or the `traffic_*` tables.
  - Snapshot IDs rise about 31–33 per publication cycle (5,625 → 5,656), roughly 60 a day.
  - Read-model columns are `json`, not `jsonb` (`models/dashboard_snapshot.py:26`).
  - `fatigue_scores` is scanned with `max(calculated_at) GROUP BY` per call (`api/bullpen.py:1285`).
- **Consequence:**
  - INFERRED growth of several GB per season.
  - Slower hot queries.
  - Provider egress and cost.
  - The September Supabase egress P0 shows this already bit once.
- **Proposed resolution:**
  - Retain every *published* snapshot (historical integrity).
  - Prune unpublished, failed and candidate snapshots after 30 days.
  - Compact superseded per-day duplicates.
  - Index `snapshot_generated_at`.
  - Retain traffic for 13 months.
- **Effort:** S–M
- **Acceptance criteria:**
  1. A documented retention table.
  2. A scheduled job.
  3. Database size measured before and after.
  4. No published snapshot deleted, verified by count.

### EOS-016 — Two unfinished replacement pipelines plus permanent database fences
- **Category:** Architecture / maintainability
- **Severity:** High
- **Status:**
  - VERIFIED: `feat/sync-pipeline` fetched read-only; CU docs.
  - UNVERIFIED: whether the Render shadow services still run.
- **Evidence:**
  - **Line 1: continuous updates on `main` (CU-01..CU-08).** Merged, shadow-only. CU-08S is "PARTIAL – hosted PostgreSQL proof pending"; CU-08U found the production replay never ran. Decision O-008 (authority transfer) is open.
  - **Line 2: the SP program on `feat/sync-pipeline` (SP-00..SP-14 plus AUDIT-R1/R2/R3).**
    - Last commit 2026-09-19.
    - **304 files / ~45k lines divergent from `main`.**
    - Its own manifest: "Until the SP-14 certification verdict becomes GO, the established … paths remain production authority". It records "NO-GO".
    - AUDIT-R3: "BLOCKED. F03 is still confirmed and unfixed".
    - SP-00 status: "Contract proposal; no runtime implementation".
  - **The branch's runtime left permanent database fences on `main`.** Migration `e3f6a9b2c5d8` triggers silently revert `main` writes to rows the integration runtime adopted (`docs/current/SYNC_PIPELINE.md` §15A–15D), which caused the Sep 25 and Oct 1 incidents.
  - Render cron `baseballos-continuous-shadow-detect` ran every 3 minutes from the branch (manifest table, 2026-09-09).
- **Consequence:**
  - Three ingestion architectures to understand: legacy (authoritative), CU shadow, and SP branch.
  - Invisible triggers that can veto corrections.
  - Continuous compute.
  - The founder's offseason could be consumed by finishing an infrastructure rewrite that has no user-visible benefit.
- **Root cause:** Rewrite-in-parallel without a kill or commit decision.
- **Proposed resolution (DEC-04):**
  - Declare the legacy writer the 2027 authority.
  - Archive the SP branch (tag it, document it, stop its Render service).
  - Freeze the CU shadow lanes and disable their crons for the offseason.
  - Audit and, where safe, drop the fence triggers so `main` can correct any row.
  - Reuse only proven pieces, such as the CU-04 incremental workload, if they materially reduce runtime.
- **Effort:**
  - S for the decision and service shutdown;
  - M for fence removal with verification.
- **Acceptance criteria:**
  1. Only one production writer is documented and configured.
  2. A fence audit query (`backend/services/fence_audit.py`) shows zero rows protected from `main`.
  3. The Render service inventory is recorded in-repo.

### EOS-017 — Workload rules are defined inconsistently across modules
- **Category:** Baseball intelligence
- **Severity:** Medium
- **Status:** VERIFIED
- **Evidence:**

  | Rule | Implementation A | Implementation B |
  |---|---|---|
  | 3-in-4 | `availability.py:166` counts *appearances*, so a doubleheader counts twice | public rule counts 3 *distinct days* (`public_team_relief_work.py:72-73`, `workload_recovery_evidence.py:46-47`) |
  | 4-in-5 vs 4-in-6 | availability uses 4-in-5 (`availability.py:167`) | public/spec uses 4-in-6 |
  | Multi-inning | 1.5 IP (`pitcher_role.py:51`) | 4 outs elsewhere |
  | High pitch count | Monitor at ≥15 pitches yesterday | public "high-pitch" at ≥25 |

  - There is no 2-day window, and no 30-day input to availability. Standard 02 asks for 2/3/5/7/14/30.
- **Consequence:**
  - The reasons a user reads on screen can disagree with the label next to them.
  - An analyst cannot reproduce a label from the public definitions.
- **Proposed resolution:**
  - One `workload_rules.py` module of named, versioned rule definitions consumed by availability, public copy, methodology and the frontend.
  - A methodology page generated from it.
- **Effort:** M
- **Acceptance criteria:**
  1. A single grep source per rule.
  2. Property tests showing every public reason string's rule matches the classifier's rule.

### EOS-018 — The board's On-Watch population and classifier differ from Team State's
- **Category:** Baseball intelligence / consistency
- **Severity:** Medium
- **Status:** VERIFIED
- **Evidence:**
  - `bullpen_board.py:150-217` is a second health-tier classifier with 40% and 20% thresholds, and it writes the reason sentences shown beside Team State.
  - The On-Watch sentence (`bullpen_board.py:256-261`) counts across the board population (active-roster flag plus eligibility, `bullpen_visibility.py:56-60`).
  - `publication_truth_certification.py:544-568` notes that this population need not equal the Team State population.
  - Washington shows "Nineteen relievers are in the On Watch group", more than any roster carries, so the population includes non-current members (INFERRED; a roster query is needed).
  - The same idle arm reads *On Watch* in one family and *Limited Read* in another (`pitcher_public_labels.py` `_read_label`).
- **Consequence:** Internal contradictions on one screen.
- **Proposed resolution:**
  - One population definition (the active-bullpen authority) and one classifier.
  - The board sentence derives from the Team State partition.
- **Effort:** M
- **Acceptance criteria:** For every published club, the board's On-Watch count equals the Team State partition's moderate count.

### EOS-019 — The frontend derives baseball meaning and converts unknowns to zero
- **Category:** Frontend / authority boundary
- **Severity:** Medium
- **Status:** VERIFIED
- **Evidence:**
  - `frontend/src/adapters/operatingStateReadModel.js:205-224` computes average starter innings with a hardcoded 7-day window and 3-game minimum.
  - `:314-380` composes "N of M relievers are…" claims and maps Monitor → On Watch locally (`:9-14`).
  - Unknown counts are coerced to 0 (`:49-52, :200-248`).
  - `pitcherLabels.js:17-60` and `bullpenConcepts.js:83-180` define Trusted Arm differently.
  - `appearanceLanguage.js:185-196` regex-rewrites backend reason strings.
- **Consequence:** These break the "baseball semantics remain backend-owned" and "no unknown-as-zero" rules (Constitution 01:148-158).
- **Proposed resolution:**
  - Move the sentences and definitions to the API.
  - The frontend renders them.
  - Delete the duplicate dictionary.
- **Effort:** M
- **Acceptance criteria:** A grep for numeric thresholds and `?? 0` / `|| 0` in `src/adapters` finds none applied to baseball counts.

### EOS-020 — Infrastructure language and raw errors reach public screens
- **Category:** UX / editorial
- **Severity:** Medium
- **Status:** VERIFIED (code; local screenshots with the API down)
- **Evidence:**
  - "Latest sync failed before publish; serving the last fully published view" (`tonightsBullpenBoardView.js:668`).
  - "Latest publication:" (`tonightView.js:145`).
  - "…in this snapshot" (`TeamBoardRolesDeployment.jsx:86`).
  - "Published BaseballOS Snapshot" (`PublicShareArtifactPage.jsx:182`).
  - "Checking sync status" / "Last sync failed".
  - The `/team/NYY` body says "from BaseballOS published snapshot 5656".
  - Stories renders a raw "API 500: Internal Server Error" (`hooks/useFetch.js:54`).
  - Trust renders "Computed Not computed".
- **Consequence:** Infrastructure-first presentation goes against Product Experience Standard 03 and the brief.
- **Proposed resolution:**
  - Public copy dictionary: "Updated through <date>", "We're showing yesterday's read while today's is checked."
  - Map errors to designed states.
- **Effort:** S
- **Acceptance criteria:** A test greps the built public bundle for a forbidden-term list (sync, snapshot, publication, payload, API 500), excluding admin chunks.

### EOS-021 — Admin and private code ship in the public bundle; the bundle is one 707 kB chunk
- **Category:** Frontend engineering / security hygiene
- **Severity:** Medium
- **Status:** VERIFIED (local build)
- **Evidence:**
  - `frontend/src/App.jsx:15-24, 50-54` statically imports `/admin/product-intelligence`, `/internal/share-artifacts/operations` and `/posts-bpen-7f3d9c` (`privatePostsView.js`, 1,308 lines).
  - There is no `React.lazy` anywhere.
  - Build output: one JS chunk of 707 kB (193 kB gzipped), plus 64 kB CSS.
- **Consequence:**
  - Slower mobile first load.
  - Internal operations surfaces are readable by anyone. Their data is server-protected (VERIFIED for private posts, `api/private_posts.py:47-57`).
- **Proposed resolution:** Route-level code splitting; admin and private routes in lazy chunks.
- **Effort:** S
- **Acceptance criteria:**
  1. Public entry chunk under 250 kB gzipped.
  2. Admin route strings absent from the entry chunk.

### EOS-022 — Search and crawler visibility are structurally weak
- **Category:** Distribution / SEO
- **Severity:** Medium
- **Status:** VERIFIED
- **Evidence:**
  - `/team/<ABBR>/index.html` is a stub with a self-canonical and a dated claim, then `window.location.replace("/bullpen?view=board&team=<ABBR>&source=share")`.
  - The SPA canonical for that URL is the query URL, which conflicts with the sitemap (`/team/<ABBR>`).
  - The `source=share` parameter mislabels organic visits as share landings (prior F-16; unchanged).
  - The 15 per-route entry pages have an empty `<div id="root">`, so crawlers see no Methodology, Trust or Stories content.
  - `robots.txt` advertises `/posts-bpen-7f3d9c`.
- **Consequence:** Team pages, the most natural search entry ("Yankees bullpen"), cannot rank.
- **Proposed resolution:**
  - Make `/team/<ABBR>` the real canonical board route, server-rendered or prerendered with the current or archive summary.
  - Remove `source=share` from organic redirects.
  - Prerender Methodology.
  - Remove the private path from robots.
- **Effort:** M
- **Acceptance criteria:**
  1. Fetching `/team/NYY` without JavaScript returns the club name, phase or state, the named key arms, and the date.
  2. Its canonical equals itself.
  3. Search Console shows impressions within 30 days (BLOCKED until production).

### EOS-023 — Ingestion has no game-type policy; spring and exhibition games risk entering 2027 workload
- **Category:** Data correctness
- **Severity:** Medium (becomes High in March 2027)
- **Status:** VERIFIED (code). Impact INFERRED.
- **Evidence:**
  - `backend/services/mlb_api.py:621`: `get_schedule` sends no `gameType`.
  - `:562-577`: `get_pitcher_game_logs` sends no `gameType` and uses `datetime.now().year`. The API default season type is UNVERIFIED.
  - Several modules treat a missing `game_type` as `R` (`bullpen_capacity.py:159-160`, `role_stability_context.py:85`, `rotation_context.py:85`, `bullpen_concentration_context.py:84`).
  - `scheduled_games.game_type` and `game_logs.game_type` exist (`models/scheduled_game.py:55`, `models/game_log.py:103`).
- **Consequence:**
  - Spring-training innings could count as workload, or as R, in March 2027.
  - The season year flips on host-local time.
- **Proposed resolution:**
  - An explicit allowlist per phase (`R`; `F/D/L/W` during the postseason; `S/E` never counted as workload).
  - Season derived from the schedule, not the clock.
  - A unit test per phase.
- **Effort:** S
- **Acceptance criteria:** A replay of a March 2026 date with spring games produces zero workload rows from `S/E` games.

### EOS-024 — Active relievers are missing throwing-hand data
- **Category:** Data completeness
- **Severity:** Medium
- **Status:**
  - VERIFIED (production artifact text).
  - UNVERIFIED (league-wide extent).
- **Evidence:** Washington artifact `178c7a7f…` (data-through 2026-10-27): "4 active relievers are missing throwing-hand data."
- **Consequence:**
  - Handedness coverage, a basic bullpen question, is incomplete.
  - The gap is surfaced as "evidence".
- **Proposed resolution:**
  - Backfill `pitchHand` from the MLB people endpoint for every pitcher with a 2026 appearance.
  - Add a completeness check to the publication gate.
- **Effort:** S
- **Acceptance criteria:** `SELECT count(*) FROM pitchers WHERE throws IS NULL AND id IN (SELECT pitcher_id FROM game_logs WHERE game_date >= '2026-01-01')` returns 0. `pitchers.throws` is confirmed at `models/pitcher.py:20`.

### EOS-025 — Session and auth hardening gaps
- **Category:** Security
- **Severity:** Medium
- **Status:** VERIFIED
- **Evidence:**
  - The bearer token is stored in `localStorage` (`frontend/src/utils/api.js:22, 109-127`).
  - There is no server-side revocation, and logout is a no-op (`api/auth.py:85`).
  - Magic links can be reused within 15 minutes.
  - `vercel.json` sets no CSP, HSTS or frame headers.
  - `app.py:85-88` treats any unknown `APP_ENV` as development.
  - CORS allows localhost in production (`app.py:125-139`).
  - The page-view beacon attaches the user's bearer token.
- **Proposed resolution:**
  - Single-use links (a nonce table).
  - A token version column for revocation.
  - Security headers in `vercel.json`.
  - Fail closed on unknown `APP_ENV`.
  - Remove localhost from the production CORS allowlist.
  - Strip auth from beacons.
- **Effort:** S–M
- **Acceptance criteria:**
  1. A reused link returns 401.
  2. `APP_ENV=prodution` refuses to boot.
  3. securityheaders.com grade A (BLOCKED until production).

### EOS-026 — Tests call the live MLB API and depend on today's date
- **Category:** Test reliability
- **Severity:** Medium
- **Status:** VERIFIED (a local run on PostgreSQL 16)
- **Evidence:**
  - The 4 tests in `backend/tests/test_postgame_lookback.py` take about 420 s each. Their fixture (`tests/test_postgame_refresh.py:246-271`) does not mock `get_team_roster`.
  - py-spy shows live calls through `sync.py:6025 → team_assignment_sync.py:449 → mlb_api.py:555`.
  - The window depends on the wall clock.
  - Overall local result: about 10,718 of 10,726 backend tests pass. The 8 failures are environment-caused: shallow git history (6) and the live MLB API (2).
  - Frontend: 1,299 of 1,299 pass. 3 needed sibling backend files, which an isolated copy lacked.
- **Consequence:**
  - CI is slow and flaky.
  - A real MLB API outage reads as a code failure.
- **Proposed resolution:** Mock the roster fetch, freeze the clock, and add a network-deny fixture to the test suite.
- **Effort:** S
- **Acceptance criteria:** The backend suite passes with outbound network blocked.

### EOS-027 — Internal enrichment runs near its timeout and intermittently fails
- **Category:** Operations
- **Severity:** Medium
- **Status:**
  - VERIFIED (runtime).
  - UNVERIFIED (failure cause).
- **Evidence:**
  - Run 40656367563: `internal-enrichment` took about 18.5 minutes against a 20-minute postgame timeout.
  - Run 40727951878: `internal-enrichment` failed.
  - The job runs only on GitHub Actions, even after a no-op sync, with `continue-on-error`.
- **Consequence:**
  - Non-public enrichment silently goes missing.
  - Wasted compute in the offseason.
- **Proposed resolution:**
  - Skip enrichment when the sync was a no-op.
  - Measure the step timings.
  - Disable it in the offseason.
- **Effort:** S
- **Acceptance criteria:** Enrichment either completes within 50% of its timeout or is skipped with a logged reason.

### EOS-028 — Failure-state UX defects
- **Category:** UX
- **Severity:** Medium
- **Status:** VERIFIED (local render with the backend down; screenshots `board-390.png`, `stories-*.png`, `trust-*.png` in the audit scratchpad)
- **Evidence:**
  - The Team Board at `/bullpen?view=board&team=NYY` shows "Teams unavailable." and then "Pick a team — Select a team above to see its current bullpen board", although the URL names NYY and no selector is rendered.
  - Stories shows a raw API 500.
  - Trust shows two red error cards plus a panel of "Unavailable" stamps.
  - There are three different error-card designs (spec 07 Part VIII requires one).
- **Proposed resolution:** One designed unavailable state per surface, which keeps the last good read where one exists.
- **Effort:** S
- **Acceptance criteria:** A Playwright test with the API mocked down asserts each route shows the designed state and no raw error text.

### EOS-029 — Governance has drifted from execution; the ledger stopped on Sep 4
- **Category:** Governance / maintainability
- **Severity:** Medium (High for solo-founder sustainability)
- **Status:** VERIFIED
- **Evidence:**
  - Roadmap 05 v5.16 (Sep 4): "No active implementation package" (05:9).
  - Work executed after that date without a ledger entry:
    - CU-01..CU-08;
    - Tonight v1 (TN-00..TN-12), including the root cutover that removed the Today page that Standard 03:124 and 07:130 still protect;
    - observed role movement (2026-10-06, no D-ID);
    - the truth-certification harness (PR #908).
  - Five post-D-058 decision records have no D-ID.
  - Standard 04 still describes GitHub Actions as the scheduler; Render Cron is primary (`SYNC_PIPELINE.md:52-54`).
  - The D-051 "no manual daily" rule conflicts with the governed `recovery_daily` path.
  - `docs/README.md:43` names HIST-01 as active.
  - The CHANGELOG stops at Aug 18.
  - Documentation runs to 420 `.md` files and 123,618 lines; Roadmap 05 alone is 131 KB.
  - Three documents say "six canonical documents" while seven are in `docs/canonical/`.
  - The 2026-09-24 viability audit (`claude/baseballos-viability-audit-8ufhk9`, unmerged) reached the same conclusion. Most of its P1 recommendations are not reflected in later work: alerting, demand baseline, postseason decision, indexable team pages.
- **Consequence:**
  - The governing documents no longer describe the product.
  - Audits are not converted into action.
  - The governance load exceeds what one person can sustain (Constitution 01:169).
- **Proposed resolution (DEC-08):**
  - One-day governance catch-up: ledger D-059…D-06x for the unrecorded decisions, update 03/04/05, mark the 21 `docs/current/CU_*` reports as audits.
  - Then reduce: one ≤3-page `CURRENT_STATE.md` plus the decision ledger as the only maintained operational truth.
- **Effort:** S (catch-up) + M (reduction)
- **Acceptance criteria:**
  1. Every route and scheduler in production is described by a canonical document.
  2. `docs/current` contains only procedures.
  3. The Roadmap names exactly one active objective.

### EOS-030 — Scheduler and infrastructure configuration lives outside the repository
- **Category:** Operations
- **Severity:** Medium
- **Status:** VERIFIED (absence of `render.yaml`)
- **Evidence:**
  - The Render Cron schedules (`5 10`, `5 14`, `5 2,4,6`, `*/3` ×2) are recorded only in docs as of a 2026-09-09 read-only inspection.
  - There is no infrastructure-as-code.
- **Consequence:**
  - The production configuration cannot be reviewed, diffed or restored.
  - It is a single point of knowledge.
- **Proposed resolution:** Commit a `render.yaml` (Blueprint) mirroring the current services, or at minimum a dated inventory refreshed each phase.
- **Effort:** S
- **Acceptance criteria:** A repository file enumerates every production service, schedule, branch and command, and it matches the Render dashboard (manual check).

### EOS-031 — Dead and one-off code and workflows
- **Category:** Maintainability
- **Severity:** Low
- **Status:** VERIFIED
- **Evidence:**
  - Backend code:
    - 12 one-off `*_2026.py` repair modules (12,296 lines) in `backend/services/`, each with a manual workflow; one exists for a single player (Matt Festa).
    - `services/` alone is 162,637 lines; `sync.py` is 7,792 lines.
    - `fatigue.py:228 recalculate_all_fatigue` is dead.
  - Frontend code: about 2,000 frontend lines are never imported (for example `BullpenBoardView.jsx`, `evidenceCardModel.js`, `SeasonBanner.jsx` with a hardcoded '2024').
  - Unused endpoints:
    - unused APIs: `/api/prospects/*`, recommendations, observations, v1 board/story/changes;
    - public live MLB proxies `/api/bullpen/mlb/*` with no consumer;
    - three public "internal" diagnostic routes that compute live (`api/bullpen.py:2628, 2762, 2831`).
- **Proposed resolution:** Archive the repair programs, by tag plus a doc, once their closeout is confirmed. Delete unused routes and modules.
- **Effort:** M
- **Acceptance criteria:** No `*_2026.py` remains in `services/`; the route count drops by at least 15; tests are green.

### EOS-032 — Privacy obligations unmet
- **Category:** Privacy / compliance
- **Severity:** Low–Medium
- **Status:** VERIFIED (absence)
- **Evidence:**
  - Traffic stores a random visitor ID, route, referrer domain, UTM tags and device class. It stores no IP address or user agent (`models/traffic_page_view.py:26-49`). That design is good.
  - What is missing:
    - a retention or purge job;
    - a consent banner and Do Not Track / GPC handling;
    - a privacy policy page;
    - an unsubscribe path for audience subscribers.
  - Unverified sign-in emails are stored.
  - Supabase RLS migration `e5b9c3a7d1f4`: applied in production is UNVERIFIED, and tables created later are not covered by its guard test.
- **Proposed resolution:**
  - A privacy page.
  - An unsubscribe link.
  - 13-month traffic retention.
  - Verify RLS on every table in production.
- **Effort:** S
- **Acceptance criteria:** A query listing `pg_tables` with `rowsecurity = false` in the public schema returns none (run against production read-only).

### EOS-033 — Timezone edge cases
- **Category:** Correctness
- **Severity:** Low
- **Status:** VERIFIED
- **Evidence:**
  - There are 14 `date.today()` calls. The one on a public route is `/pitchers/<id>/logs` (`api/bullpen.py:1243`), which is off by a day between 8 p.m. and midnight ET on a UTC host.
  - One `utcnow()` remains (`roster_depth_evidence.py:643`).
  - `game_change_detection.py:224` defaults to the UTC date.
  - The `EASTERN` constant is defined three times.
- **Proposed resolution:** A single `product_clock` module, plus a lint rule banning `date.today()` in `backend/`.
- **Effort:** S
- **Acceptance criteria:** A grep finds zero `date.today()` outside the clock module.

### EOS-034 — Automated accessibility coverage is limited to Tonight
- **Category:** Accessibility
- **Severity:** Low
- **Status:** VERIFIED
- **Evidence:**
  - axe runs only in the Tonight Playwright specs, scoped to `main`.
  - Team-switch via `?team=` is not announced.
  - What is good:
    - a skip link;
    - focus-to-main on navigation (`RouteAccessibility.jsx:9-26`);
    - no horizontal overflow at 390, 768 or 1440 px;
    - state colours always paired with text.
- **Proposed resolution:** axe on Team Board, Dashboard, Pitcher, Methodology, Trust and Share at 390 px and 1440 px.
- **Effort:** S
- **Acceptance criteria:** Zero serious or critical axe violations on those routes.

### EOS-035 — Documentation authority count and numbering inconsistent
- **Category:** Documentation
- **Severity:** Low
- **Status:** VERIFIED
- **Evidence:**
  - `docs/canonical/README.md:8`, `docs/README.md:3` and the documentation map `:20-27` say "six".
  - `07_FRONTEND_DESIGN_MIGRATION_SPECIFICATION.md` lives in `docs/canonical/` and calls itself "not a seventh canonical authority" (07:26).
  - File 05 is authority rank 6 and file 06 is rank 5.
  - The audit brief treats all seven as canonical.
- **Proposed resolution:** State "six canonical authorities plus one subsystem specification" consistently, or move 07 to `docs/current/`. See DEC-08.
- **Effort:** S

### EOS-036 — Generated social drafting uses prohibited vocabulary
- **Category:** Editorial
- **Severity:** Low
- **Status:**
  - VERIFIED (code).
  - UNVERIFIED (rendered output).
- **Evidence:**
  - The private posts board has an `era_elite` lead dimension (`frontend/src/components/posts/privatePostsView.js:52`).
  - The "Recommended" / "Ranked highest" labels conflict with the Editorial Standard 06:275 ban on "elite" and on ranking-forward framing.
- **Proposed resolution:** Rename the dimension and remove ranking labels from drafts.
- **Effort:** S

---

# Part B — Missing Capabilities

| ID | Capability | Severity | Status | Why it matters | Effort | Acceptance |
|---|---|---|---|---|---|---|
| EOS-M01 | **Season-phase and club competitive-status model** (backend-owned, served by the API) | Critical | NOT IMPLEMENTED | Prerequisite for EOS-001/002/006/023 and the whole offseason product | M | `GET /api/season/state` returns phase, per-club status, last/next game; the frontend renders it without deriving it |
| EOS-M02 | **2026 season finalization and archive record**: a declared final snapshot per club, reconciliation of every 2026 final game including the postseason, frozen season aggregates | High | NOT IMPLEMENTED | Preserves 2026 meaning before 2027 begins; enables year-two context | M | `07` G-1 checks pass; a `season_closures` record exists for 2026 with counts and hashes |
| EOS-M03 | **Offseason product**: per-club 2026 bullpen season summary (workload totals, concentration, multi-day patterns, role movement, Team State timeline with corrected semantics), reliever season pages, offseason transactions feed | High | NOT IMPLEMENTED (data exists; History surfaces partially exist) | Without it the site is either wrong (today) or empty from November to March | L | All 30 clubs have an archive page; home shows "2026 season complete" with archive entry |
| EOS-M04 | **Demand baseline and readout** from existing first-party traffic: external visitors, different-day returners, team-board repeat visits | High | NOT IMPLEMENTED (instrumentation exists, `services/traffic_reporting.py`; no number recorded anywhere) | Separates product failure from distribution failure; prerequisite for any growth spend | S | A dated readout committed; kill criteria adopted (DEC-09) |
| EOS-M05 | **Label outcome validation**: did "Unavailable" / "Limited Rest" arms pitch less often than Clean Options on the following day in 2026? | High | NOT IMPLEMENTED | The only evidence that the core label is informative; also calibrates thresholds | S–M | Report with rates per label and 95% CIs from the 2026 ledger |
| EOS-M06 | **Spring-training transition**: roster and transaction context in March, no Team State from S/E games, explicit Opening Day switch-on | High | NOT IMPLEMENTED | Avoids repeating EOS-001 at Opening Day, when every arm's last appearance is about 5 months old | M | Rehearsal on 2026-03 dates shows the correct phase states |
| EOS-M07 | **Descriptive late-inning hierarchy**: "who has been finishing games / entering in the 8th or later in the last 14 days" | Medium | PARTIAL (role movement and entry bands exist; O-004/O-009 open) | Answers fans' first question ("who's closing?") descriptively; closes the main gap against RosterResource and Closer Monkey | M | Team Board shows the named arms ranked by observed late-inning entries with counts and dates |
| EOS-M08 | **Retention of time-perishable source data**: probable-pitcher history, point-in-time roster and live states, raw payload archive for final games | Medium | NOT IMPLEMENTED | These cannot be reconstructed later; cheap to store | S–M | Daily probables table populated; raw final-boxscore JSON archived to object storage |
| EOS-M09 | **Pitch-level coverage before 2026-07-04** and prior-season (2025) backfill of the appearance ledger | Low–Medium | NOT IMPLEMENTED | Enables year-over-year context and velocity-under-workload studies; recoverable at any time from public sources, so not urgent | M | Coverage report by month |

---

# Part C — Optional Improvements

| ID | Improvement | Value | Effort |
|---|---|---|---|
| EOS-I01 | Mobile-first Team Board: active-bullpen table with inline receipts as the first screen at 390 px (prior F-09) | High UX | M |
| EOS-I02 | Named-arm What Changed ("Hader → Limited Rest after 31 pitches Monday") | High retention | M |
| EOS-I03 | Copy-ready citation line and embed for share artifacts (creator workflow) | Medium distribution | S |
| EOS-I04 | `jsonb` read-model columns plus `snapshot_generated_at` index | Low perf | S |
| EOS-I05 | Upgrade SQLAlchemy / alembic / psycopg (psycopg2 pin blocks Python 3.13) | Low | S |
| EOS-I06 | TypeScript migration | **Not recommended now.** Contract tests already pin payloads; cost exceeds offseason value | — |
| EOS-I07 | Velocity-under-workload context from stored pitch data | Medium differentiation (stretch) | L |

---

## Severity summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 2 defects + 1 capability | EOS-001, EOS-002, EOS-M01 |
| High | 13 defects + 5 capabilities | EOS-003…EOS-014, EOS-016; EOS-M02…M06 |
| Medium | 15 defects + 2 capabilities | EOS-015, EOS-017…EOS-030, EOS-032 (Low–Medium, rated Medium here); EOS-M07, EOS-M08 |
| Low | 5 defects + 1 capability | EOS-031, EOS-033…EOS-036; EOS-M09 (Low–Medium) |

## Historical leads: disposition

| Historical lead | Disposition now | Evidence |
|---|---|---|
| Team Board latency | **Still open, unmeasured.** The architecture still loads the full snapshot | EOS-014 |
| Render Tonight DB timeout | **Fixed** (pool pre-ping, recycle, 15 s statement timeout; Tonight serves an immutable row) | `backend/config.py:58-105`; `public_serving_authority.py:1457-1461` |
| Starter workload counted as bullpen (2026-09-23) | **Fixed in code**; production confirmation UNVERIFIED | `services/game_shape.py:305`; `team_board_v2.py:95-106` |
| Snapshot inconsistency (D-056, Sep 12 34-team universe) | Repository fixes present; natural-production proof never recorded; superseded in impact by EOS-001/002 | Roadmap 05:493; incident doc :3, :59 |
| Distribution handoff (Sep 12 skip; stale Open Graph) | **Working daily since at least Oct 2** (47 commits) but structurally unsound | EOS-013 |
| June "all arms Monitor" degeneracy | **Recurred** in a different form (stale → Monitor) | EOS-001, EOS-004 |
| Prior audit (2026-09-24) F-04 alerting, F-17 rate limits, F-18 router, F-28 share HTML in git, F-08 postseason decision | **All still open**; F-08 has now materialized as EOS-001/002 | This register |
