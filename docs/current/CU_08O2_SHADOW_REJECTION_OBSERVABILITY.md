# CU-08O2 Shadow Detect Rejection Observability

## Repository state and scope

- Branch: `fix/shadow-detect-rejection-observability`
- Starting `main`: `69cfc211b2340d705e83886ffe52e3522e1db151`
- Schema changes: none

CU-08O2 changes only compact command formatting and its tests. It does not
change CU-02 classification or observation ordering, CU-08 cycle execution,
activation mode, Render cadence or configuration, downstream behavior,
canonical actions, publication, cache behavior, authority, or frontend behavior.

## Files changed

- `backend/scripts/run_continuous_cycle.py`
- `backend/tests/test_continuous_execution_command.py`
- `docs/current/CU_08O2_SHADOW_REJECTION_OBSERVABILITY.md`

## Boolean safety-field root cause and correction

Starting `main` constructed the four safety fields with ordinary dictionary
lookups, and a local `json.dumps` reproduction emitted valid JSON booleans. The
reported production keys-without-values symptom therefore cannot be reproduced
or attributed to Python serialization from repository evidence alone.

The repository did have a concrete observability-contract gap: compact output
did not enforce that these safety values were booleans, and tests did not prove
both false and true values for all four fields. CU-08O2 adds a strict formatter
boundary that accepts only `bool` values and adds explicit false/true coverage.
It does not coerce missing, string, or numeric values into reassuring falsehoods.

Correct compact output includes:

```json
{"event":"continuous_cycle","mode":"shadow_detect","sync_run_id":1163,"games_checked":15,"changed_games":8,"unchanged_games":5,"rejected_observations":2,"source_failures":0,"failures":0,"source_requests":16,"source_retries":0,"runtime_ms":1476.797,"status":"complete","reason_code":"cycle_complete","canonical_actions":0,"canonical_mutation_games":0,"live_publications":0,"cache_handoffs":0,"production_authority_affected":false,"timeout_reached":false,"source_budget_exhausted":false,"circuit_breaker_open":false}
```

## Rejected-observation visibility

The cycle already retained complete CU-02 detection dictionaries but compact
output emitted only changed observations. CU-08O2 now formats one
`game_rejected` line for each detection result whose existing classification is
`stale_observation` or `ambiguous_observation`.

The command copies existing values directly. It does not rerun ordering logic,
infer rejection state, or rename weaker authority: CU-02 continues to represent
weaker authority as `stale_observation` with reason
`weaker_source_authority`.

Example:

```json
{"event":"game_rejected","game_pk":823665,"classification":"stale_observation","reason":"weaker_source_authority","finality":"final_pending_data","source_authority":"mlb_statsapi_live_feed_v1_1","previous_observation_identity":"accepted-fingerprint","current_observation_identity":"incoming-fingerprint"}
```

## Unchanged, changed, full-JSON, and exit behavior

- Unchanged games remain summary-count-only and produce no per-game line.
- Changed games retain the accepted `game_changed` format unchanged.
- `--full-json` still returns the complete existing cycle result without compact
  formatting.
- Successful and unsuccessful exit-code behavior is unchanged.

Given one cycle, operators can now distinguish a missing follow-up
`game_changed` line caused by an unchanged observation from a stale, ambiguous,
or weaker-authority rejection without opening full JSON or querying persistence.

## Semantic regression proof

The formatter consumes the existing `ContinuousCycleResult.to_dict()` value.
No service or model changes were made. Existing CU-08 and CU-02 tests continue
to own and prove games checked, changed/unchanged/rejected counts,
classifications, downstream gating, canonical actions, source requests,
publication/authority isolation, source budgets, and cycle locking.

Validation completed:

- CU-08O2 command tests: **14 passed**;
- command, CU-08 continuous execution, and CU-02 game-change detection:
  **58 passed, 1 skipped**; the skip is the existing PostgreSQL-only lock case
  under the local SQLite test database;
- scheduling, activation, deployment-profile, and summary-output contracts:
  **197 passed, 1 deselected**; the deselection is the established Windows
  shell-path case.

- CI shard verification: **PASS**, 401 files and 9,131 tests assigned exactly
  once across four shards;
- Python compilation: **PASS**;
- whitespace/diff checks: **PASS** (Git emitted only expected LF-to-CRLF working
  copy notices).

The full backend suite was **NOT RUN**. This bounded patch changes no service,
detector, cycle, persistence, scheduler, authority, or publication logic.

## Render command impact and verdict

Render command impact: **none after merge**. The existing command remains:

```text
python backend/scripts/run_continuous_cycle.py --mode shadow_detect
```

No Render configuration or schedule edit is required. Production must remain in
`SHADOW_DETECT`; CU-08O2 does not authorize `SHADOW_FULL_CHAIN`.

Final verdict: **PASS — CU-08O2 ACCEPTED**.

The exact recommendation is a direct push, focused PR, hosted PostgreSQL/CI
validation, and normal merge with no Render change.
