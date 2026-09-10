# BaseballOS Full Program Audit — June 2026

> **Scope & method.** This audit was produced by reading the repository end to
> end on the `claude/baseballos-full-audit-5VinP` branch: backend services,
> models, migrations, recommendation/observation/explanation engines, API
> routes, the React frontend, the test suites, and the documentation corpus. It
> distinguishes **confirmed implementation** (code I read and tests I ran) from
> **documented intention** (claims made in docs that I could not verify against
> a running production system). The backend test suite (391 tests) and frontend
> test suite (138 tests) were both executed and **pass cleanly** as part of this
> audit. No branch, commit, or code change was made.

---

## 1. Executive Summary

BaseballOS is, at its **core**, a genuinely solid piece of baseball software:
a deterministic fatigue engine, a fail-closed availability classifier, a clean
React dashboard, an honest methodology page, and an unusually disciplined
trust/freshness posture. The pitcher-fatigue flow (`Bullpen` list →
`PitcherDetail` drawer) is well-engineered, well-tested, and exactly the kind of
transparent, no-fake-certainty tool the product vision calls for. **The
foundation is real and trustworthy.**

The problem is **proportion and proof**. Around that solid core, the project has
accreted an enormous governance/certification apparatus — ~160 markdown files
(a 7,782-line "project state" file, ~87 phase docs, 31 backend reports), two
parallel recommendation engines, a 1,263-line V2 panel that **by design shows no
recommendation**, and a self-issued ledger that stamps surfaces
"Production Ready" and "Full Production Rollout Approved." Much of this is
**ceremony, not capability**. The certifications grade the project's own
homework; the only externally confirmable production fact is that a Render
health endpoint returns `ok`.

Two honest, load-bearing facts cut against the "production ready" framing, and
both come from the project's **own** reports:

1. The V5 "Bullpen Intelligence Surface" — labeled *Full Production Rollout
   Approved* — serves **deterministic sample data**, not live observations
   (`backend/api/observations.py:37`, `build_sample_observation_collection()`).
2. On live data, the Availability Engine currently classifies **all 704
   pitchers as `Monitor`** (`backend/reports/availability_threshold_audit.md`),
   and the public `/api/bullpen/sync/status` endpoint reports `never` because
   sync metadata is written to a git-ignored, ephemeral file
   (`backend/reports/data_freshness_validation_summary.md`).

**Bottom line:** The engineering you'd show a skeptical professional is ~30% of
this repo. The other ~70% is process scaffolding that currently obscures the
good work rather than showcasing it. The next phase should be **consolidation
and proof**, not new surfaces.

---

## 2. Original Starting Point

This began as a **bullpen-focused baseball intelligence tool** — a portfolio
project to prove the author could build real, trustworthy baseball software. The
original scope is still visible in the codebase:

- A **Prospect Pipeline** ("Pipeline / Preview" in the nav) that tracks
  minor-league development on **hand-entered sample data**, explicitly labeled
  "early prototype · illustrative sample data" (`frontend/src/components/prospects/Prospects.jsx:25`).
  This is leftover scaffolding from the original portfolio app — orthogonal to
  bullpen intelligence but honestly marked.
- A **Methodology** page that transparently documents the fatigue model.
- The fatigue engine itself (`backend/services/fatigue.py`).

From there it has progressed **substantially**: a fail-closed availability
engine, a V1 candidate recommendation engine, a V2 bullpen-state context engine,
a V3 team-operations readiness surface, a V4 explanation layer, and a V5
observation surface — each with API routes, frontend panels, and test coverage.
The *implementation* progression is real. The *maturity* progression is
overstated by the docs (see §13).

---

## 3. True End Goal

BaseballOS is trying to become a **professional-grade bullpen intelligence and
decision-support system** — the kind of tool that could credibly sit in front of
someone like Trevor May, support real baseball workflows, and serve as the
foundation for serious analytics work. The defining product principles are:

- **Trust-first** bullpen intelligence.
- **Explainable** recommendations — no black boxes.
- **Deterministic, auditable** decision logic.
- **Clear freshness/sync visibility.**
- **Fail-closed** when data is missing, stale, incomplete, or low-confidence.
- **No fake certainty.**
- An architecture strong enough to add **ranking, matchup, leverage, and
  game-context intelligence** cleanly later.

The architecture genuinely *supports* this goal. The current product does not
yet *feel* like it — because the most impressive layer (a defensible,
explainable recommendation) is deliberately withheld, while the supporting
governance metadata is pushed to the foreground.

---

## 4. Current System Map

### Backend (`backend/`, Flask + SQLAlchemy)
- **App factory** (`app.py`): registers seven blueprints — `bullpen`,
  `prospects`, `methodology`, `recommendations`, `team-operations`,
  `explanations`, `observations` — plus `/api/health`. An optional in-process
  APScheduler daily job exists but is gated behind `AUTO_SYNC` and is **not** the
  production sync path.
- **Engines / services** (`backend/services/`, `backend/recommendation/`,
  `backend/team_operations/`, `backend/explanations/`, `backend/observations/`).
- **Models** (`backend/models/`): `Pitcher`, `GameLog`, `FatigueScore`,
  `Prospect`, `SyncRun`. Migrations under `backend/migrations/versions/` (4
  revisions, including a durable `sync_runs` table and a game-log uniqueness
  constraint).

### Frontend (`frontend/`, React 18 + Vite + Tailwind)
- Real routing (`react-router-dom`) with **four routes**: `/` (Dashboard),
  `/bullpen`, `/prospects`, `/methodology` (`App.jsx:14`, `Sidebar.jsx:4`).
- Within-screen navigation is **state-based**, not URL-based — there is no
  deep-link for a selected pitcher, team, or prospect; selection is lost on
  refresh.
- `utils/api.js` (1,470 lines) holds all routes plus heavy response
  normalization and contract guards.

### Database
- PostgreSQL in production; SQLite-free pure-Python unit tests
  (`backend/tests/conftest.py` uses in-memory stubs — no DB/Flask/network).
- Seeded from the MLB Stats API for 2024–2025 (`backend/seed.py`).

### Sync pipeline & freshness
- Production sync is **external**: `.github/workflows/baseballos-sync.yml` POSTs
  the admin-protected `/api/bullpen/sync` endpoint daily at 10:00 UTC. This is
  the correct design (a free Render instance spins down, so an in-process
  scheduler is unreliable — documented in the workflow header).
- Sync writes a status file to `backend/logs/sync_status.json`, **which is
  git-ignored and ephemeral** (`.gitignore`). A durable DB-backed alternative
  (`services/sync_metadata.py`, `models/sync_run.py`) exists but the public
  status endpoint still degrades to "never" when the file is gone (see §11).

### Engines
- **Fatigue Engine** (`services/fatigue.py`): deterministic 0–100 score.
- **Availability Engine V1** (`services/availability.py`): five statuses,
  fail-closed.
- **Recommendation Engine V1** (`recommendation/`): candidate-level category
  eligibility, fail-closed, no ranking/selection.
- **Recommendation Engine V2** (`recommendation/v2.py`, `v2_assembly.py`):
  bullpen-state context with mandatory trust metadata.
- **Team Operations Readiness** (`team_operations/`): team-level readiness.
- **Explanation Layer V4** (`explanations/`): adapter that builds explanation
  objects from existing availability/readiness payloads.
- **Observation Surface V5** (`observations/`): descriptive observations — but
  served from **sample state** (see §11/§12).

### Recommendation layer
- Two coexisting systems. **V1** is surfaced only as a small embedded
  "Evaluate Candidate" control inside `PitcherDetail`; its standalone layout is
  **dead code**. **V2** is the certified one, mounted on the Dashboard inside
  `OperationalReadinessSection`, but renders context/evidence only.

### Trust / freshness layer
- Surfaced **everywhere**: sync status, season banner (live vs snapshot),
  "data through {date}", per-row stale states, confidence chips, refusal blocks,
  fail-closed states, limitations lists. This is the app's strongest theme — and
  its most over-invested one (see §8/§12).

### Documentation / governance
- `docs/` (~160 files), `backend/reports/` (31 files), `docs/governance/`,
  `docs/operations/`, `docs/monitoring/`. The governance spine
  (`ranking_applied === false`, `selection_made === false`) is **genuinely
  enforced in code and tests**; the surrounding certification narrative is
  largely self-attested ceremony.

---

## 5. What Is Already Strong

1. **The Fatigue Engine** (`services/fatigue.py`). Clean, deterministic,
   well-documented, and **intellectually honest**: when it found the MLB gameLog
   endpoint doesn't expose Leverage Index, it *dropped* the component and
   redistributed its weight rather than faking a constant (`fatigue.py:12-27`).
   That single decision embodies the whole "no fake certainty" principle.
2. **The Availability Engine V1** (`services/availability.py`). Centralized,
   tunable thresholds in one frozen dataclass (`AvailabilityThresholds`), a clear
   `data_state` ladder (`fresh`/`stale`/`incomplete`/`missing`), and genuine
   fail-closed behavior — missing/stale data downgrades to `Monitor`/`low`
   confidence instead of inventing a status.
3. **The PitcherDetail flow** (`frontend/.../bullpen/PitcherDetail.jsx`). The
   best part of the UI: score + risk badge, an explicit workload-only
   disclaimer, availability summary, a "Why this availability?" explanation
   disclosure, a 4-factor weighted breakdown, radar chart, trend line with a
   CRITICAL reference line, and a spring-training-tagged appearances table.
4. **The trust/freshness plumbing.** Freshness, confidence, refusal, and
   limitations are real, consistent, and threaded end-to-end.
5. **Test discipline on the core.** 391 backend tests pass; the fatigue engine
   is tested as pure Python with deterministic fixtures. 138 frontend tests pass
   (after a clean `npm install`).
6. **The `backend/reports/` corpus.** These tool-generated, evidence-bearing
   audits are the **most useful and most honest** documents in the repo — they
   openly diagnose the stale-data and sync-metadata problems.
7. **Correct production sync architecture.** Externalizing the daily sync to
   GitHub Actions (rather than trusting an in-process scheduler on a sleeping
   free-tier instance) is the right call and is well-reasoned in the workflow.

---

## 6. What Is Currently Complete

**Truly complete and verified (code + passing tests):**
- Fatigue scoring engine and its risk tiers.
- Availability Engine V1 classification and fail-closed states.
- Recommendation Engine V1 candidate evaluation (gates → categories → builder),
  including refusal and governance-flag enforcement.
- Recommendation Engine V2 bullpen-state context assembly with mandatory trust
  metadata and forbidden-field guards (`recommendation/v2.py`).
- Team Operations Readiness backend + internal route + frontend panel.
- V4 explanation builders and explanation API.
- The Bullpen list / PitcherDetail / Methodology screens and shared UI
  primitives (loading/empty/error states).
- Durable sync metadata model + migration (`sync_runs`).

**Foundation / partial only (built, but not load-bearing in production):**
- **V5 Observations**: full contract/builder/API/panel stack exists and is
  tested, but the live endpoint returns **sample data**
  (`api/observations.py:37`). It is a foundation, not a live feature, despite
  the "Full Production Rollout Approved" label.
- **Recommendation V1 UI**: complete component, but the standalone variant is
  dead code; only the embedded button path runs.
- **Prospect Pipeline**: functional UI against sample data; explicitly a
  prototype.
- **Durable freshness end-to-end**: the model/migration exist, but the public
  status endpoint still degrades to "never" in the field (§11) — the fix is
  built but not fully closing the loop.

---

## 7. What Is Not Yet Complete

Specific, real gaps that matter:

1. **Live freshness loop is broken in production.** `/api/bullpen/sync/status`
   returns `last_sync: null, status: never` because `sync_status.json` is
   ephemeral and git-ignored; the durable `sync_runs` metadata is not the
   authoritative source for that endpoint's headline state
   (`api/bullpen.py:451`, `services/sync.py:349`). Result: the dashboard shows a
   "snapshot" label even right after a successful sync.
2. **V5 observations are not wired to live data.** The certified surface emits
   `build_sample_observation_collection()`. Runtime observation generation from
   MLB data is explicitly *not* certified (the V5 docs admit this).
3. **The Availability Engine produces a degenerate live result.** Per its own
   audit, **704/704 pitchers classify as `Monitor`**
   (`backend/reports/availability_threshold_audit.md`). Whether that's
   freshness-window-driven or threshold-driven, the user-facing output currently
   carries **no discriminating signal** — every arm looks the same.
4. **No deep-linking / shareable state.** You cannot link to a pitcher, a team
   bullpen, or a prospect; refresh loses selection.
5. **No actual recommendation is ever shown.** V2 — the centerpiece — renders
   "context and evidence only" by design. The product promises
   "explainable recommendations" but currently delivers explainable
   *non-recommendations*.
6. **Dead/vestigial V1 recommendation UI** never reachable in-app.
7. **No CI** running the test suites on push (no test workflow alongside the
   sync workflow), so the green suites aren't enforced.
8. **Documentation is not navigable** by a newcomer (see §13).

---

## 8. Gaps Between Current State and "Amazing"

What stops this from *feeling* like a polished, impressive baseball product
today:

1. **It withholds its own punchline.** A coach opening the app gets workload
   numbers and a wall of governance metadata, but never a crisp, defensible
   "here's who's fresh and why." The discipline is admirable; the restraint has
   gone one notch too far for a *demo*.
2. **Internal vocabulary leaks to the user.** End-user surfaces print
   `ranking_applied === false`, `selection_made === false`, "Neutral Candidate
   Groups", "Fail-Closed state", "Diagnostics detected: N", and raw route badges
   like "GET /api/observations" (`RecommendationV2BullpenStatePanel.jsx`,
   `BullpenIntelligencePanel.jsx`). This reads as engineer-facing contract
   output, not product.
3. **Disclosure overload.** The Dashboard nests disclosures within disclosures
   within compact embedded panels — deep click-to-reveal trees that bury the
   actual data.
4. **The flagship signal is currently flat** (all-`Monitor`), so even the parts
   that *do* work look uninformative on live data.
5. **Portfolio framing in product chrome.** The sidebar footer hardcodes a
   personal bio ("Army Vet · Developer · Building to break in.",
   `Sidebar.jsx:63`). Fine for a portfolio; out of place if shown as a product.
6. **The 1,263-line V2 panel is the largest single piece of UI** yet delivers
   the least direct user value — a reviewer who opens the code will feel the
   imbalance.

---

## 9. Product Gaps (user-facing / workflow / UX)

- **No "who can I use tonight?" view.** The most natural bullpen workflow — a
  ranked-or-grouped, at-a-glance availability board for one team — does not
  exist as a first-class screen. Availability is shown per-row and per-pitcher,
  never as a clean "tonight's board."
- **No game-context entry point.** There's no notion of "it's the 7th, I need a
  high-leverage arm" — leverage/role/matchup context is absent by design, but
  there's also no scaffolding placeholder communicating "coming."
- **Recommendation UI is not a decision aid.** It's a contract viewer. A user
  cannot answer "who's my freshest arm?" from it.
- **Two recommendation systems with no shared model** confuse the mental model
  (V1 candidate-eval vs V2 bullpen-state, both called "Recommendation Engine").
- **Prospects screen dilutes focus.** It's clearly labeled as a prototype, but
  it still occupies a top-level nav slot and a Dashboard panel, splitting
  attention from the flagship.
- **No empty-but-guided onboarding.** When data is stale (the current reality),
  the app explains *why* well, but doesn't guide the operator to a useful action.
- **No mobile-optimized decision flow** beyond responsive layout; the
  disclosure-heavy panels are awkward on phones.

---

## 10. Technical Gaps

- **Authoritative freshness source is split** between an ephemeral JSON file and
  a durable DB table; the endpoint should read the durable table as the source
  of truth and treat the file as a cache, not vice-versa
  (`api/bullpen.py:451-479`).
- **`utils/api.js` (1,470 lines)** and **`RecommendationV2BullpenStatePanel.jsx`
  (1,263 lines)** and **`recommendation/v2_assembly.py` (1,941 lines)** are
  oversized modules that will be hard for a collaborator to navigate.
- **Duplicated frontend helpers.** `asArray`/`asObject`/`displayValue`/
  `labelize`/`titleize` are re-implemented across at least five components with
  *subtly different* fallback strings ("Not provided" vs "Unavailable" vs
  "missing"). `utils/displayText.js` exists but isn't used everywhere — a clean
  consolidation target.
- **Forbidden-term scrubber is fragile.** The V2 panel regex-strips banned words
  (best/top/rank/score/…) from displayed values and silently falls back to
  "Unavailable" — it can blank legitimate content invisibly.
- **No CI test gate.** Tests pass locally but nothing enforces them on push.
- **Frontend install is brittle.** A stock `npm test` hit the known
  `@rollup/rollup-linux-x64-gnu` optional-dependency bug; a clean reinstall
  fixed it. A committed lockfile fix or CI install step would prevent
  "14 tests failing" false alarms.
- **Tests skew to contract/governance, not flows.** No routing tests, no
  `Bullpen`/`PitcherDetail` interaction tests (selection, sort, pagination,
  recalculate), no Dashboard integration test. The flagship flow is the least
  tested at the UI level.
- **The in-process APScheduler path is now redundant** with the GitHub Actions
  sync; keeping both invites drift (`app.py:_init_scheduler`).

---

## 11. Data and Trust Gaps

This is where documented intention and confirmed reality diverge most, and the
project's own reports are the witnesses:

- **Freshness visibility is broken at the seam.** `data_freshness_validation_summary.md`
  states plainly: the DB *has* data through May 31, 2026 and a successful June 1
  sync ran, but `/api/bullpen/sync/status` reports `last_sync: null, status:
  never` because the dashboard-readable sync metadata is missing (ephemeral file
  on a spun-down instance). So the **trust UI under-reports its own freshness** —
  ironic for a trust-first product.
- **Live availability output is degenerate.** `availability_threshold_audit.md`
  (generated 2026-06-02, ref date 2026-06-01): **704 pitchers, 704 `Monitor`.**
  The report's own trust note warns these are dominated by stale/missing data
  states, not workload signal. Either way, the live signal currently carries no
  discrimination.
- **V5 is "production approved" but serves sample data.**
  `api/observations.py:37` returns a deterministic sample collection. The V5
  governance doc concedes "live runtime observation generation from MLB data is
  not certified." A "Full Production Rollout Approved" badge on a sample-data
  endpoint is the single most misleading status in the repo.
- **Fail-closed behavior is genuinely good** where it's wired: availability
  downgrades on missing/incomplete/stale data; V2/observations refuse on invalid
  state; the status endpoint has a `try/except` that never lets a DB hiccup turn
  the pill into a hard error (`api/bullpen.py:464`).
- **Confidence logic is sound but currently pinned low** because the data is
  treated as stale — so "high confidence" availability is effectively
  unreachable in the field right now.
- **Source visibility is strong**: MLB Stats API attribution, "data through
  {date}", live-vs-snapshot banner, and admin-gated write endpoints.

Net: the *mechanisms* for trust are excellent; the *live data state* and the
*freshness reporting seam* currently undermine them, and the docs paper over
that with approval language.

---

## 12. Recommendation Engine Assessment

### What it does well
- **V1** is a clean, fail-closed, candidate-level eligibility engine: gates →
  category assignment → response builder, with refusal on low confidence/stale
  freshness and hard enforcement of `ranking_applied=False`/`selection_made=False`
  (`recommendation/builder.py:127`, `categories.py`). It never pretends.
- **V2** assembles real bullpen-state context from the DB
  (`latest_fatigue_rows`) and attaches mandatory, validated trust metadata, with
  a recursive forbidden-field guard that will *raise* if a ranking/selection/
  prediction field name ever appears in a payload (`recommendation/v2.py:38-117`).
  As a **governance substrate**, this is impressive and genuinely defensible.

### What it intentionally does not do
- It does not rank, select, predict, or recommend a "best" arm. This is a
  deliberate, well-defended product boundary — and the right one for *trust*.

### What V2 needs (V2 → V2 "policy")
- **A user-facing decision layer that stops short of selection but stops short
  of nothing.** The gap isn't "add ranking"; it's "present the eligible,
  fresh, high-confidence arms as a clean grouped board with reasons" — which the
  category system already computes but the UI buries. Translate contract fields
  into human language; remove `ranking_applied === false` from the user's view
  (keep it in metadata/API).
- **Collapse the dual engines** into one conceptual model so collaborators and
  users aren't navigating V1-candidate vs V2-bullpen-state.
- **Wire to fresh data** so the output isn't uniformly `Monitor`.

### What must not be added too early
- Outcome/injury/save prediction, matchup advice, leverage-based "use this arm"
  selection, or any hidden priority ordering. The governance guards exist
  precisely to prevent this drift — keep them. The discipline is the moat; don't
  trade it for a flashy but unfounded "best arm" feature.

---

## 13. Documentation Assessment

**Canonical / keep (genuinely useful):**
- `README.md` (good front page — but fix the status table, §11).
- `docs/SETUP.md`, `docs/CHANGELOG.md`, `docs/ROADMAP.md` (trim duplication).
- `docs/BULLPEN_AVAILABILITY_ENGINE_V1.md` (real engine spec).
- `backend/reports/*` — the honest ground truth; promote these, don't bury them.
- `docs/governance/CERTIFICATION_LEDGER.md` as the **single** status source.

**Stale / misleading (fix or annotate):**
- README status table and ledger rows asserting V4/V5 "Full Production Rollout
  Approved" — contradicted by the reports and by V5's own sample-data caveat.
- The ledger itself has internal contradictions (V5 recorded "rollout not
  approved" in one phase, "approved" two phases later on the basis of a
  document asserting the blocker was cleared).

**Bloated / too long (split or truncate):**
- `docs/PROJECT_STATE_2026_06.md` — **7,782 lines**; only the first ~451 are a
  real state snapshot. The rest is an append-only changelog that duplicates
  `CHANGELOG.md`/`ROADMAP.md`. Truncate to the snapshot; archive the tail.
- `docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md` (1,793 lines).
- `docs/ROADMAP.md` lines ~109–303 (verbatim milestone re-paste).

**Should become an archive, not front-line docs:**
- The ~87 phase docs (`V3_PHASE_*`, `V4_PHASE_*`, `V5_PHASE_*`,
  `V25_PHASE_*`, `RECOMMENDATION_ENGINE_V2_PHASE_*`). These are
  **certification theater**: each follows the same template, each re-pastes the
  same "does not authorize ranking/selection/…" boilerplate, and many produce no
  code (V5 Phases 1–3 are "capability definition / taxonomy / architecture" with
  *no implementation*). Real content is perhaps 10–20% of their volume. Move them
  to `docs/history/` and drop them from the main INDEX listing.

**Would confuse a future collaborator:**
- The sheer volume. To learn that there is *one* explanation API, a newcomer must
  wade through ~13 V4 phase files. The doc-to-code ratio (≈160 md files for
  ≈9k LOC frontend + comparable backend) inverts the usual signal: someone will
  reasonably assume the system is far larger and more mature than it is.

**Tell:** of 62 commits, the large majority are "V4 Phase N" / "docs:" /
governance commits. The development cadence itself is dominated by ceremony.

---

## 14. Testing Assessment

**Strengths:**
- **Backend: 391 tests, all passing.** The fatigue engine is tested as pure
  Python with deterministic fixtures (`conftest.py`), and governance invariants
  (no forbidden fields, fail-closed refusal, trust-metadata presence) are
  asserted directly.
- **Frontend: 138 tests, all passing** (after a clean install). Strong coverage
  of API-contract normalization and **governance-safety** — e.g. tests assert
  forbidden display terms never appear in rendered HTML and that
  `ranking_applied === false` strings render.

**Missing categories:**
- **No UI flow / interaction tests** for the flagship `Bullpen`/`PitcherDetail`
  (selection, sort, pagination, recalculate) — the most important user path is
  the least tested at the component level.
- **No routing tests** (`App`/`Sidebar`), no Dashboard integration test, nothing
  for Prospects/Methodology.
- **No backend integration test with a real DB session** — unit tests
  deliberately avoid the DB, so the SQLAlchemy query layer (the `/fatigue`,
  `/teams/.../bullpen`, sync-status payload joins) is unverified by tests.
- **No CI gate.** Nothing runs these suites automatically; the green state isn't
  enforced.
- **No end-to-end / smoke test** against a running app, despite extensive manual
  "smoke review" documents.

The testing energy mirrors the codebase: heavily invested in governance
correctness, under-invested in the actual product flow.

---

## 15. Readiness Assessment

| Category | Rating | Rationale |
| --- | --- | --- |
| **Portfolio demo** | **Close** | The Bullpen/PitcherDetail/Methodology core is genuinely impressive; needs the all-`Monitor` live data fixed and the governance jargon toned down before it shines. |
| **Trevor May review** | **Needs Work** | A baseball professional would respect the fatigue model and honesty, but would immediately notice it never actually recommends anyone and that the live board is flat. The depth is in metadata, not baseball insight. |
| **Real user demo** | **Needs Work** | No "who can I use tonight?" board; recommendation UI is a contract viewer; freshness mis-reports itself. |
| **Production deployment** | **Not Ready** | V5 serves sample data, freshness endpoint reports "never," no CI, live availability signal is degenerate — despite docs labeling these "production." |
| **Future paid collaboration** | **Needs Work** | The core architecture is a strong foundation to build on, but a collaborator would first have to dig out from under the documentation and dual-engine complexity. |

---

## 16. Recommended Roadmap

**Phase 1 — Polish & audit cleanup (highest priority, low risk).**
- Fix the freshness seam: make `/sync/status` read durable `sync_runs` as the
  source of truth so a successful sync stops reporting "never."
- Truncate `PROJECT_STATE_2026_06.md` to its snapshot; move ~87 phase docs to
  `docs/history/`; correct the README/ledger status language to match reality
  (mark V5 as "foundation / sample-data," not "production").
- Remove dead V1 standalone recommendation layout; consolidate duplicated
  frontend display helpers into `utils/displayText.js`.
- Add a CI workflow that runs backend + frontend tests on push.
- Remove governance vocabulary (`ranking_applied === …`, route badges) from
  end-user surfaces; keep it in API/metadata.

**Phase 2 — Recommendation Engine V2 policy (the unlock).**
- Add a thin, human-readable **decision presentation** over the existing
  category eligibility: a grouped "Available / Monitor / Limited / Avoid" board
  per team with plain-language reasons — *without* crossing into ranking or
  selection. The data already exists; only the presentation is missing.
- Collapse V1/V2 into one conceptual surface.

**Phase 3 — Ranked-but-governed bullpen recommendations.**
- Introduce *transparent ordering within a status tier* (e.g. "freshest first,"
  with the sort key shown) — explicitly labeled as a sort, not a selection — so
  the product finally answers "who's my freshest arm?" while preserving "the
  user decides."

**Phase 4 — Matchup / context expansion.**
- Add game-context inputs (inning/leverage/role) as *filters and context*, not
  predictions. Re-introduce leverage data ingestion (the schema column already
  exists) from a defensible source.

**Phase 5 — Polished demo / productization.**
- A dedicated "Tonight's Bullpen Board" landing view, deep-linkable
  pitcher/team URLs, mobile decision flow, and a demo dataset that shows
  discriminating availability (not all-`Monitor`).

---

## 17. Highest-Leverage Next 10 Tasks

1. **Fix `/api/bullpen/sync/status` to read durable `sync_runs`** so freshness
   stops self-reporting "never" right after a good sync. (Trust-critical,
   small.)
2. **Diagnose and fix the all-`Monitor` availability output** — confirm whether
   it's freshness-window or threshold-driven, and make the live board show real
   discrimination. (The flagship signal is currently flat.)
3. **Build "Tonight's Bullpen Board"** — a per-team grouped availability view
   with plain-language reasons, from data that already exists.
4. **De-jargon the user-facing panels** — strip `ranking_applied === false` and
   contract field names from V2/observations UI; move them to metadata only.
5. **Truncate `PROJECT_STATE_2026_06.md` and archive the ~87 phase docs** to
   `docs/history/`; reduce INDEX to the canonical set.
6. **Correct the README/ledger status table** to distinguish *built* from
   *live/production* (especially V5 sample-data).
7. **Add a CI workflow** running backend (`pytest`) + frontend (`npm test`) on
   push, with a clean-install step to dodge the rollup bug.
8. **Remove dead V1 standalone recommendation UI** and unify V1/V2 into one
   conceptual recommendation surface.
9. **Consolidate duplicated frontend display helpers** into `utils/displayText.js`
   with one consistent fallback string.
10. **Add UI flow tests** for `Bullpen`/`PitcherDetail` (selection, sort,
    pagination, recalculate) — cover the flagship path.

---

## 18. Risks

- **Trust erosion from overstated status.** The single biggest risk: a reviewer
  who discovers V5 serves sample data while labeled "Production Ready," or that
  the freshness pill says "never" on fresh data, will discount *all* the
  project's honesty claims — including the genuinely honest ones. Overstatement
  is the most dangerous thing in a trust-first product.
- **Documentation rot.** The doc corpus grows faster than the code; every new
  surface spawns ~13 phase files. Left unchecked, the repo becomes
  unmaintainable-by-inspection and scares off collaborators.
- **Complexity without payoff.** The dual recommendation engines and the
  1,000+-line governance panels add maintenance burden while delivering little
  user value; further "certified surfaces" deepen the hole.
- **Governance theater displacing product work.** The phase/certification
  cadence consumes the development energy that should go into the
  "who-can-I-use-tonight" feature that would actually impress.
- **Degenerate live data masking real bugs.** While everything is `Monitor`,
  threshold/classification regressions can hide in plain sight.
- **No CI** means the passing suites can silently break.

---

## 19. Final Verdict

**Where BaseballOS is now:** It has a *real, trustworthy, well-engineered core* —
a deterministic fatigue engine, a fail-closed availability classifier, a polished
pitcher-detail flow, honest methodology, and genuinely good trust plumbing —
wrapped in a *disproportionately large governance and certification apparatus*
that currently overstates the product's maturity and withholds its most valuable
output.

**How impressive it currently is:** The foundation would impress an engineer who
reads `services/fatigue.py` and `PitcherDetail.jsx`. The *product*, as it
presents today, would underwhelm a baseball professional: it shows workload
numbers and governance metadata but never a defensible recommendation, and on
live data every arm looks identical. The honesty is its best feature; the
overstated "production approved" docs are its worst, because they undercut that
honesty.

**How far it is from "amazing":** Closer than the doc sprawl suggests —
**weeks, not months**, because the hard part (the engines, the data model, the
trust layer) is done. The missing pieces are mostly *presentation and proof*: a
tonight's-board view, de-jargoned panels, a working freshness pill, a
non-degenerate live signal, and a documentation diet.

**What should happen next:** Stop adding certified surfaces. Spend the next phase
on **consolidation and proof** — fix the freshness seam and the all-`Monitor`
output, build the one decision board the product has been carefully avoiding,
strip the contract vocabulary from the user's view, archive the phase-doc
mountain, and align the README/ledger with reality. Do that, and the same core
that exists today will finally *look* as trustworthy and capable as it actually
is.

---

*Audit produced read-only. Backend tests (391) and frontend tests (138) were
executed and pass. No branch, commit, or code change was made; transient
dependency installs (`pytest`, a clean frontend `npm install`) were used only to
run the suites and do not alter tracked source.*
