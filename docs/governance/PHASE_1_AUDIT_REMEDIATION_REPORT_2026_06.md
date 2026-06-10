# Phase 1 Audit Remediation Report — June 2026

Companion to `docs/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md`. This records the
Phase 1 "polish, proof, and trust cleanup" work: small, reviewable changes that
improve correctness and user-facing clarity without rewriting systems, adding
recommendation/ranking/selection behavior, or adding new certified surfaces.

Branch: `claude/baseballos-full-audit-5VinP` (existing branch reused; no new
branch created).

---

## 1. What Was Changed

### Freshness reporting (Task 1)
- **`backend/api/bullpen.py`** — added an explicit "Authority" note to the
  `GET /api/bullpen/sync/status` docstring documenting that durable `sync_runs`
  metadata is the source of truth and `backend/logs/sync_status.json` is
  cache-only (consulted only when no durable run exists).
- **`backend/tests/test_sync_status.py`** — added
  `test_durable_metadata_overrides_a_conflicting_cache_file`: writes a stale,
  conflicting status file, inserts a successful `SyncRun`, and asserts the
  endpoint reports the durable success (`status: success`, non-null `last_sync`
  / `last_successful_sync`) and ignores the cache file. This is the regression
  guard for the freshness finding.

No production code logic changed here — see findings (§3): the durable-authoritative
behavior already existed; this closes the missing *proof* and documents the
contract.

### User-facing de-jargon (Task 3)
- **`frontend/src/components/observations/BullpenIntelligencePanel.jsx`**
  - Replaced per-observation `ranking_applied === … / selection_made === …`
    footer with plain copy: **"Context only — not a ranking or selection."**
  - Replaced the Governance metadata-cell subtext (same raw fields) with the
    same plain copy.
  - Removed the raw route badge **"GET /api/observations · {status}"** → now
    shows just the status label.
  - Rewrote the protected/unavailable state copy: dropped "frontend contract
    guard did not verify the current payload" and the "Diagnostics detected: N"
    debug line in favor of "Observation details are withheld until the latest
    data passes BaseballOS safety checks. Nothing is shown unless it can be
    trusted." Removed the now-unused diagnostics computation.
- **`frontend/src/components/dashboard/OperationalReadinessSection.jsx`**
  - Replaced the two prominent green `ranking_applied === … / selection_made === …`
    chips with a single plain, safety-aware line: **"Context only — no pitcher is
    ranked or selected."** (falls back to "Governance state unavailable …; treat
    as context only." if the booleans are ever not both `false` — preserving
    fail-closed intent).
- Tests updated to assert the new plain copy instead of the raw fields:
  `frontend/tests/bullpenIntelligencePanel.test.mjs`,
  `frontend/tests/operationalReadinessSection.test.mjs`,
  `frontend/tests/explanationSurface.test.mjs`.

The raw governance booleans remain in the API payloads, the normalized view
models, the contract/normalization tests, and the opt-in "Evidence & Metadata"
drawers (V2 panel) and explanation metadata grid — so nothing about
auditability is lost; the debug vocabulary is just off the primary surfaces.

### Documentation corrections (Task 4)
- **`README.md`** — rewrote the "Current Platform Status" table to separate
  **governance maturity** from **what each surface runs on today**, with an
  explicit legend distinguishing *implemented / tested / rollout-approved /
  sample state*. Specifically:
  - V5 Bullpen Intelligence Surface is now labeled **"Governance-certified
    foundation / Deterministic sample state — not yet wired to live MLB data"**
    instead of "Full Production Rollout Approved" with no data caveat.
  - V2 is labeled as presenting **governed context/evidence only — it does not
    rank, select, or name a pitcher.**
  - Added a note that rollout/certification labels are the project's own ledger
    milestones, not third-party audits.
- Tightened the V2 Core Capabilities bullet to state it surfaces context and
  evidence only.

### Dead-code marker (Task 5)
- **`frontend/src/components/recommendations/RecommendationPanel.jsx`** — added a
  comment documenting that the default standalone/header configuration is not
  reachable in the running app (only the embedded `showHeader={false}` path via
  `RecommendationPitcherDetailSection` is mounted), and that promoting the
  embedded mount to canonical is deferred to a separate test-coupled pass.

### CI test gate (Task 6)
- **`.github/workflows/ci.yml`** — new workflow running backend (`pytest`) and
  frontend (`node --test`) suites on push / PR / manual dispatch. The frontend
  job removes the checked-in `node_modules/` and `package-lock.json` and runs a
  fresh `npm install` on the Linux runner to avoid the known
  `@rollup/rollup-linux-x64-gnu` optional-dependency bug.

### New diagnostic report (Task 2)
- **`backend/reports/availability_all_monitor_diagnosis.md`** — see §5.

---

## 2. What Was Intentionally Not Changed

- **Availability thresholds / classification logic.** The all-Monitor output is
  correct fail-closed behavior on stale data, not a defect (§5). Loosening
  thresholds would manufacture fake certainty — explicitly out of bounds.
- **Recommendation behavior.** No ranking, selection, prediction, or "best arm"
  logic was added anywhere. Governance invariants (`ranking_applied=False`,
  `selection_made=False`) are untouched and still enforced.
- **No new certified surfaces**; no V5 live-data wiring (that requires separate
  governed authorization).
- **Dead standalone V1 recommendation layout — not removed.** It is an unused
  prop configuration of a *live* component that the test suite renders by
  default (9+ tests). Removing it means rewriting ~half the component and its
  tests — a broad, test-coupled refactor the task scope excludes. Marked with a
  comment and deferred.
- **Frontend display-helper consolidation — deferred.** The shared
  `utils/displayText.js` helpers (`humanizeLabel`, `summarizeDisplayValue`) have
  *different* semantics and fallback strings ("Not provided" vs "Unavailable" vs
  "missing") than the per-component `displayValue`/`asArray` helpers. A blanket
  consolidation would change rendered output across many tested components — not
  low-risk. Recommended as its own scoped pass.
- **Deep "Evidence & Metadata" drawers (V2 panel, Team Operations panel).** Left
  as the deliberate home for raw governance fields, for audit/trust. Only the
  always-visible primary surfaces were de-jargoned.
- **Bloated docs (e.g. the 7,782-line `PROJECT_STATE`, ~87 phase docs).** Not
  archived in this pass to avoid moving history without explicit sign-off; the
  README legend now frames the status language honestly. Archiving is a
  recommended Phase 1.5 item.

---

## 3. Freshness-Status Findings

- The durable, DB-backed sync metadata path **already exists and is
  authoritative**: `services/sync_metadata.build_sync_status_payload()` reads
  `sync_runs` first and only falls back to the JSON file when no durable run
  exists. It was added 2026-06-03, **one day after** the freshness report
  (`data_freshness_validation_summary.md`, 2026-06-02) that observed
  `status: never`. So that report's root cause is already addressed in code.
- With current code, a backend whose `sync_runs` migration is applied and which
  has run a sync will report the real `status`/`last_sync`/`last_successful_sync`
  from durable metadata, regardless of the ephemeral file.
- The residual risk is **operational, not code**: if the `sync_runs` migration
  has not been applied in an environment, the durable query fails (caught) and
  the endpoint falls back to the cache file. When game logs exist it now reports
  `metadata_unavailable` (honest) rather than `never`.
- Phase 1 added the missing regression proof
  (`test_durable_metadata_overrides_a_conflicting_cache_file`) and documented
  the cache-only contract in the route. The earlier full audit's statement that
  the pill "reports never on fresh data" reflected the 06-02 report and is now
  corrected by this finding.

**Action for operators:** ensure the `sync_runs` migration
(`backend/migrations/versions/41f4f9a8d6c2_add_sync_runs.py`) is applied in
production; after one sync, the freshness pill will reflect durable metadata.

---

## 4. Availability All-Monitor Findings

Full detail in `backend/reports/availability_all_monitor_diagnosis.md`. Summary:

- **Cause: correct fail-closed behavior on a stale dataset**, not a threshold
  bug. In the 2026-06-02 threshold audit, all 704 "Monitor" rows are `stale`
  (640) or `missing` (64), with current-window pitch counts all zero and the
  reason "Latest workload data is outside the 14-day freshness window."
- **Proof the engine works:** the same 704 pitchers in latest-workload snapshot
  mode (anchored to each pitcher's own last game) produce a full spread —
  Monitor 268 / Limited 174 / Avoid 156 / Unavailable 106.
- **Safest fix path:** improve freshness *visibility* (Task 1, done) and add an
  availability staleness banner (deferred, UX-scoped); keep demo data fresh. Do
  **not** loosen thresholds. No classifier code change was justified.

---

## 5. User-Facing Copy Cleanup Summary

Removed from primary, always-visible surfaces and replaced with plain baseball/
product language:

| Before (raw/debug) | After (plain) |
| --- | --- |
| `ranking_applied === false` / `selection_made === false` chips (Dashboard) | "Context only — no pitcher is ranked or selected." |
| `ranking_applied === … / selection_made === …` per-observation footer & governance subtext (V5 panel) | "Context only — not a ranking or selection." |
| "GET /api/observations · {status}" route badge | "{status}" |
| "frontend contract guard did not verify the current payload" + "Diagnostics detected: N" | "Observation details are withheld until the latest data passes BaseballOS safety checks. Nothing is shown unless it can be trusted." |

Governance booleans remain in API payloads, view models, contract tests, and the
opt-in Evidence & Metadata drawers.

---

## 6. Documentation Status Corrections

- README status table now separates governance maturity from live-data reality,
  with a legend.
- V5 explicitly labeled sample-state, not production/live-ready.
- V2 explicitly labeled context/evidence only (no ranking/selection/naming).
- Added that certification/rollout labels are self-recorded ledger milestones.

---

## 7. Tests Run and Results

| Suite | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest tests -q` (in `backend/`) | **392 passed** (was 391; +1 new sync-status test) |
| Frontend | `npm test` (clean install, in `frontend/`) | **138 passed**, 0 failed |
| Frontend build | `npm run build` | Built successfully (pre-existing >500 kB chunk-size warning only) |
| Lint/format | n/a | No ESLint/Prettier config exists in the repo (nothing to run) |

Note: the frontend's checked-in `node_modules/` is a non-Linux install; a clean
`npm install` is required on Linux to run the suite (the CI workflow does this).
The clean install and `dist/` build output are environment artifacts and were
not committed.

---

## 8. Remaining Risks

- **Operational, not code:** the freshness pill is only correct once the
  `sync_runs` migration is applied in each environment. Unapplied → falls back to
  honest `metadata_unavailable`.
- **V5 still serves sample data.** The README now says so; wiring live data
  remains a separate, governed effort.
- **Demo data staleness** will still render an all-Monitor availability board
  (correctly). Until a staleness banner ships, this can look uninformative to a
  first-time viewer even though it is behaving correctly.
- **Deferred cleanups** (standalone V1 layout removal, display-helper
  consolidation, doc archiving) remain and will keep adding mild collaborator
  friction until done.
- **CI not yet proven green on GitHub.** The workflow is added but its first
  real run happens on push; the clean-install strategy is validated locally.

---

## 9. Recommended Next Phase

1. **Availability staleness banner** (UX-only): when the active list is
   empty/all-stale, show one explicit "Availability paused — workload data is N
   days old" message instead of identical Monitor rows.
2. **Keep a fresh demo dataset** so the engine's real discrimination is visible.
3. **Phase 2 (from the audit): a plain-language "Tonight's Bullpen Board"** that
   presents the already-computed availability groups with reasons — still no
   ranking/selection.
4. **Scoped frontend cleanup pass:** promote the embedded RecommendationPanel
   mount to canonical and remove the standalone layout; consolidate display
   helpers into `utils/displayText.js` with one consistent fallback string.
5. **Doc diet:** archive the ~87 phase docs under `docs/history/` and truncate
   `PROJECT_STATE` to its snapshot.
