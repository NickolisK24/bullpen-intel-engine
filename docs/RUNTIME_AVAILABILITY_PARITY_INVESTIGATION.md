# Runtime Availability Parity Investigation

## 1. Executive summary

Local and Render availability distributions can diverge even when they are using the same code and the same durable workload data.

The confirmed cause is runtime reference-date drift. The current availability path evaluates workload windows against `date.today()` from the running process. At the time of reproduction, local Python resolved `date.today()` to `2026-06-08`, while the deployed Render API reported freshness with `reference_date: 2026-06-09`. Recomputing locally with `reference_date=2026-06-09` exactly matched the Render distribution.

The Availability Engine, fatigue scoring, thresholds, classification rules, frontend rendering, and bullpen health logic are not implicated. The mismatch is caused by the date used to evaluate already-correct workload data.

## 2. Confirmed facts

- Base commit for the investigation was `a954dd9021036b401ae9c7f4d5bc447e73d50a82`.
- `main`, `dev`, `origin/main`, and `origin/dev` were aligned at `a954dd90` before the investigation branch was created.
- The investigation branch is `investigate/runtime-availability-parity`.
- The live Render API health endpoint reported `environment: production` and `debug: false`.
- The live Render sync endpoint reported durable sync metadata from `sync_runs`, not `sync_status.json`.
- The live Render sync endpoint reported:
  - `status: success`
  - `sync_authority: sync_runs`
  - `last_successful_sync: 2026-06-08T11:43:43.58887`
  - `latest_game_date: 2026-06-07`
  - `latest_workload_date: 2026-06-07`
  - `latest_fatigue_calculated_at: 2026-06-08T11:43:43.500956`
  - `freshness.reference_date: 2026-06-09`
  - `freshness.data_age_days: 2`
  - `freshness.freshness_state: current`
- Local diagnostics against the configured database reported:
  - `date.today(): 2026-06-08`
  - local current time: `2026-06-08T21:22:01.788203`
  - UTC current time: `2026-06-09T01:22:01.788206+00:00`
  - latest workload date: `2026-06-07`
  - latest fatigue calculation: `2026-06-08T11:43:43.500956`
  - active pitchers: `724`
  - latest fatigue rows: `680`
- The same local diagnostic produced the following fixed-reference distributions:

| Reference date | Available | Monitor | Limited | Avoid | Unavailable | Health |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `2026-06-07` | 53 | 78 | 84 | 19 | 9 | elevated |
| `2026-06-08` | 94 | 79 | 48 | 18 | 4 | elevated |
| `2026-06-09` | 130 | 70 | 39 | 1 | 3 | manageable |
| `2026-06-10` | 150 | 60 | 30 | 3 | 0 | manageable |

- The live Render dashboard distribution was:

| Source | Available | Monitor | Limited | Avoid | Unavailable | Health |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Render dashboard | 130 | 70 | 39 | 1 | 3 | manageable |
| Local fixed `2026-06-09` | 130 | 70 | 39 | 1 | 3 | manageable |

## 3. Reproduction steps

1. Verify the live backend environment:

   ```powershell
   Invoke-RestMethod -Uri 'https://baseballos-api.onrender.com/api/health'
   ```

2. Capture the live dashboard distribution:

   ```powershell
   Invoke-RestMethod -Uri 'https://baseballos-api.onrender.com/api/bullpen/dashboard' |
     ConvertTo-Json -Depth 8
   ```

3. Capture the live durable freshness state:

   ```powershell
   Invoke-RestMethod -Uri 'https://baseballos-api.onrender.com/api/bullpen/sync/status' |
     ConvertTo-Json -Depth 8
   ```

4. Run the local backend diagnostic against the same configured database, with background sync disabled:

   ```powershell
   cd backend
   $env:AUTO_SYNC = 'false'
   .\venv\Scripts\python.exe <diagnostic script>
   ```

5. In the diagnostic, recompute dashboard availability records with explicit reference dates:
   - `2026-06-07`
   - `2026-06-08`
   - `2026-06-09`
   - `2026-06-10`

6. Compare Render's distribution to the fixed-reference local outputs.

The key reproduction result is that Render matched local `reference_date=2026-06-09`, while normal local execution used `date.today() == 2026-06-08`.

## 4. Code path trace

The league dashboard endpoint is `backend/api/bullpen.py:get_bullpen_dashboard()`.

Current path:

1. `get_bullpen_dashboard()`
2. `availability_latest_fatigue_rows()`
   - alias for `services.availability_snapshot.latest_fatigue_rows()`
3. `_eligible_classified_records(latest_rows, include_stale=True)`
4. `classify_latest_fatigue_rows(rows, mode=CURRENT_AVAILABILITY_MODE)`
5. `services.availability_snapshot.classify_fatigue_rows()`
6. `services.availability_snapshot.evaluation_date_for_mode()`
7. `services.availability.classify_availability()`
8. `services.availability._derive_inputs()`
9. `summarize_availability_records()`
10. `build_team_context(groups, freshness=freshness)`
11. `classify_bullpen_health(groups, freshness=freshness)`

Important date defaults in the path:

- `backend/api/bullpen.py:_eligible_classified_records()` calls `classify_latest_fatigue_rows()` without an explicit `reference_date`.
- `backend/api/bullpen.py:_eligible_classified_records()` separately sets `today = date.today()` for bullpen eligibility context.
- `backend/api/bullpen.py:get_bullpen_dashboard()` separately sets `today = date.today()` for usage-role classification.
- `backend/services/availability_snapshot.py:classify_fatigue_rows()` defaults `current_reference_date = reference_date or date.today()`.
- `backend/services/availability_snapshot.py:evaluation_date_for_mode()` defaults `current_reference_date = current_reference_date or date.today()`.
- `backend/services/availability.py:classify_availability()` defaults `ref = reference_date or date.today()`.
- `backend/services/bullpen_population.py` defaults `reference_date` to `date.today()` for active-window and roster-context filtering.

The most sensitive calculation is in `backend/services/availability.py:_derive_inputs()`, where `reference_date` defines:

- yesterday workload window
- last 3 days workload window
- last 5 days workload window
- days of rest
- back-to-back and multi-appearance flags

Changing the reference date from `2026-06-08` to `2026-06-09` changes those windows without changing any thresholds or classification logic.

## 5. Environment/config findings

- `backend/config.py` loads `.env` via `load_dotenv()`.
- Development uses a default local database only when `DATABASE_URL` is absent.
- Production requires `APP_ENV=production`, `DATABASE_URL`, `ADMIN_API_TOKEN`, and a non-default `SECRET_KEY`.
- `backend/app.py:create_app()` defaults to `APP_ENV=development` unless configured otherwise.
- `backend/app.py` registers the bullpen API at `/api/bullpen`.
- `backend/app.py` starts the background scheduler only when `AUTO_SYNC` is truthy.
- Local diagnostics disabled background sync with `AUTO_SYNC=false`.
- `frontend/vite.config.js` proxies local frontend `/api` requests to `http://127.0.0.1:5000`.
- `frontend/src/utils/api.js` uses `VITE_API_BASE_URL` when set; otherwise it calls relative `/api`.

No frontend route, proxy, or API-base configuration explains the mismatch. The Render API response itself matched the `2026-06-09` backend recomputation.

## 6. Database/query findings

The dashboard uses durable database-backed workload and sync sources:

- `fatigue_scores`
- `pitchers`
- `game_logs`
- `sync_runs`

`backend/services/availability_snapshot.py:latest_fatigue_rows()` selects the max `FatigueScore.calculated_at` per pitcher and joins those rows to `Pitcher`.

`backend/services/sync_metadata.py:build_sync_status_payload()` ignores legacy local status input and builds the public sync payload from durable sync metadata plus persisted game/fatigue coverage.

The live Render sync endpoint confirmed:

- metadata source: `sync_runs`
- sync authority: `sync_runs`
- last successful sync present
- latest workload date present
- fatigue timestamp present

The local diagnostic found the same latest workload and fatigue timestamps. This rules out stale `sync_status.json` and missing durable sync metadata as the cause of this specific local-vs-Render distribution mismatch.

One lower-priority query detail remains worth keeping in the later fix audit: `latest_fatigue_rows()` joins on `max(calculated_at)` only. If duplicate max timestamps exist for one pitcher, the query can return more than one row for that pitcher. That was not the observed cause here because the fixed `2026-06-09` local distribution exactly matched Render.

## 7. Date/time findings

This is the decisive section.

At the same investigation moment:

- Local Python reported `date.today() == 2026-06-08`.
- Local UTC time was already `2026-06-09T01:22:01.788206+00:00`.
- Render `/api/bullpen/sync/status` reported `freshness.reference_date == 2026-06-09`.
- Render freshness reported `latest_workload_date == 2026-06-07` and `data_age_days == 2`, which is consistent with reference date `2026-06-09`.

The current availability path uses host-local `date.today()` rather than a single product-defined availability reference date. During the evening local window after UTC midnight, local and Render can evaluate the same workload data against different dates.

Because workload windows and days rest are reference-date dependent, this changes availability distribution and the derived bullpen health label.

Do not rely on PowerShell-rendered JSON timezone conversions for `generated_at` analysis. PowerShell can deserialize and reserialize ISO timestamps in local time. The reliable evidence is the API's explicit `freshness.reference_date` and the fixed-reference distribution match.

## 8. Caching/process findings

No caching explanation was confirmed.

- The live sync endpoint returned current durable metadata from `sync_runs`.
- The Render dashboard distribution exactly matched a local fixed-reference recomputation.
- The Vite proxy only forwards `/api` to the local Flask server.
- The dashboard route performs live database reads through `latest_fatigue_rows()` and live classification.
- The frontend was not needed to reproduce the mismatch; the Render API response alone showed it.

Background sync process state is also not the cause of the observed mismatch. Sync metadata showed a successful June 8 sync, and both local and Render saw data through June 7.

## 9. Root cause assessment

Root cause:

The current availability surfaces do not share an explicit, stable availability reference date. They default to `date.today()` in multiple backend modules. Render and local development can resolve `date.today()` differently around UTC midnight or any runtime timezone difference.

Impact:

- Local and Render can show different availability counts from identical workload data.
- Bullpen health can change because it is derived from availability counts.
- Users can see a believable but inconsistent condition read.
- The issue is most visible when data through the latest completed MLB day is evaluated once as "today" and once as "tomorrow."

Not root cause:

- Not fatigue scoring.
- Not availability thresholds.
- Not availability classification rules.
- Not recommendation logic.
- Not frontend rendering.
- Not durable sync metadata.
- Not `sync_status.json` for this specific mismatch.

## 10. Recommended fix plan

Do not change the engine, thresholds, fatigue weights, or classification rules.

Recommended implementation plan:

1. Add a single backend helper that returns the product availability reference date.
2. Make the helper explicit and testable.
3. Choose one authority for "current availability" date:
   - Preferred: a configured BaseballOS product timezone using `zoneinfo`, such as an MLB-facing timezone.
   - Alternative: a data-anchored date, such as `latest_workload_date + 1 day`, if the product decision is that "tonight" always means the day after the latest completed workload date.
4. Pass that explicit reference date through dashboard, board, landscape, comparison, game-context, team operations, explanation, and recommendation-readiness surfaces that currently rely on implicit `date.today()`.
5. Include the chosen reference date in freshness/context payloads where users or operators need auditability.
6. Add regression tests that freeze runtime time near UTC midnight and assert local/production parity.

The fix should be a reference-date plumbing correction, not an availability-engine redesign.

## 11. Exact files likely involved

Likely implementation files:

- `backend/services/availability_reference_date.py` or equivalent new helper
- `backend/api/bullpen.py`
- `backend/services/availability_snapshot.py`
- `backend/services/availability.py`
- `backend/services/bullpen_population.py`
- `backend/services/game_context.py`
- `backend/services/pitcher_role.py`
- `backend/services/sync_metadata.py`
- `backend/api/team_operations.py`
- `backend/api/recommendations.py`
- `backend/api/explanations.py`

Likely test files:

- `backend/tests/test_bullpen_dashboard.py`
- `backend/tests/test_bullpen_board.py`
- `backend/tests/test_bullpen_comparison.py`
- `backend/tests/test_game_context.py`
- `backend/tests/test_sync_status.py`
- `backend/tests/test_freshness_deploy_correctness.py`
- `backend/tests/test_team_operations_bullpen_readiness_api.py`
- `backend/tests/test_recommendation_v2_api_contract.py`
- `backend/tests/test_v4_explanation_api_routes.py`

Likely frontend files only if the reference date is newly surfaced or labeled:

- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/src/components/dashboard/SyncStatus.jsx`
- `frontend/src/components/bullpen/board/BullpenBoardView.jsx`
- `frontend/src/components/bullpen/board/TeamBullpenComparison.jsx`

## 12. Validation plan

Minimum backend validation:

1. Unit test the reference-date helper with fixed runtime datetimes around UTC midnight.
2. Unit test availability classification with explicit reference dates and verify unchanged classification behavior for unchanged inputs.
3. Dashboard API test: freeze runtime date/time to local evening after UTC midnight and verify the endpoint uses the product reference date, not host-local `date.today()`.
4. Board API test: verify team board and dashboard use the same reference date.
5. Landscape/game-context test: verify landscape output uses the same records/reference date as dashboard.
6. Sync status test: verify freshness `reference_date`, `active_cutoff_date`, and `data_age_days` are consistent with the same product reference date.
7. Failure-path test: verify metadata-unavailable and no-data states still fail closed.

Production validation:

1. Deploy the fix to Render.
2. Call `/api/bullpen/sync/status` and record `freshness.reference_date`.
3. Call `/api/bullpen/dashboard` and record availability distribution and health.
4. Run the same local diagnostic with the same explicit reference date.
5. Confirm local and Render distributions match.
6. Repeat the check during the local-evening/UTC-next-day window that reproduced the mismatch.

Non-goal validation:

- Confirm thresholds were not changed.
- Confirm fatigue scoring was not changed.
- Confirm availability classifications were not changed.
- Confirm recommendation behavior was not changed.
- Confirm no new product feature was introduced.
