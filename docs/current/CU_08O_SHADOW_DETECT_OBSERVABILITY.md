# CU-08O Shadow Detect Observability

## Scope and repository state

- Branch: `fix/shadow-detect-observability`
- Starting `main`: `4ba77a9b272bf3d21c871050f9db84641216d6d7`
- Main drift from the prior CU-08 checkpoint: one unrelated generated Team
  Preview publication commit
- Schema changes: none

CU-08O changes command output only. It does not change CU-02 detection, CU-08
cycle behavior, Render cadence, activation mode, downstream orchestration,
publication, cache behavior, authority, or frontend behavior.

## Files changed

- `backend/scripts/run_continuous_cycle.py`
- `backend/tests/test_continuous_execution_command.py`
- `backend/tests/ci_shard_manifest.json`
- `docs/current/CU_08O_SHADOW_DETECT_OBSERVABILITY.md`

## Output contract

The existing one-shot command now emits compact single-line JSON by default.
Every cycle emits exactly one `continuous_cycle` record containing the existing
result's mode, run identity, checked/changed/unchanged/rejected counts, source
failures and request/retry counts, runtime, status/reason, and hard safety
sentinels.

When `changed_games > 0`, the command additionally emits one `game_changed`
record for each existing detection result whose `changed` value is true. These
records contain only the existing game identity, classification, finality state,
and difference keys. Unchanged observations are not emitted individually.

No value is recomputed from MLB source data and no detector meaning is parsed in
the command.

## Examples

Unchanged cycle:

```json
{"event":"continuous_cycle","mode":"shadow_detect","sync_run_id":1125,"games_checked":15,"changed_games":0,"unchanged_games":15,"rejected_observations":0,"source_failures":0,"failures":0,"source_requests":16,"source_retries":0,"runtime_ms":1225.0,"status":"complete","reason_code":"cycle_complete","canonical_actions":0,"canonical_mutation_games":0,"live_publications":0,"cache_handoffs":0,"production_authority_affected":false,"timeout_reached":false,"source_budget_exhausted":false,"circuit_breaker_open":false}
```

Changed observation, following the cycle summary:

```json
{"event":"game_changed","game_pk":824392,"classification":"changed","finality":"not_final","differences":["status","inning"]}
```

Failure summary uses the same cycle record and directly surfaces non-success
status plus `reason_code`, source/failure counts, timeout, source-budget, and circuit-
breaker state. Failed and blocked statuses retain a nonzero process exit.

## Full JSON/debug mechanism

`--full-json` preserves the complete prior pretty-printed result:

```text
python backend/scripts/run_continuous_cycle.py --full-json
```

Compact output is the default, so the current production Render command requires
no edit after merge.

## Semantic regression proof

Focused command tests prove:

- unchanged cycles produce one summary and no per-game lines;
- changed cycles produce only changed-game records after the summary;
- gamePk, classification, difference keys, and finality are preserved;
- safety and failure fields are copied from the cycle result;
- full JSON round-trips to the complete original payload;
- `off`, `complete`, and `skipped` remain successful exits;
- `partial` and `blocked` remain failed exits;
- the actual CLI defaults to compact output and honors `--full-json`.

Existing CU-08 tests remain the authority for game selection, fingerprints,
classification, downstream gating, source budgets, publication behavior, and
cycle locking. CU-08O does not edit those services.

## Validation

Validation completed:

- command, continuous-execution, and game-change detection selection: **51
  passed, 1 skipped**; the skip is the existing PostgreSQL-only lock case under
  the local SQLite test database;
- scheduling, activation, summary-output, and deployment-profile selection:
  **197 passed, 1 deselected**; the deselection is the established Windows
  shell-path case;
- CI shard verification: **PASS**, 401 files and 9,124 tests assigned exactly
  once across four shards;
- Python compilation: **PASS**;
- whitespace/diff checks: **PASS** (Git emitted only expected LF-to-CRLF working
  copy notices).

The full backend suite was **NOT RUN**. This bounded output-only patch changes no
service, detector, scheduler, persistence, or publication logic.

## Render command impact and verdict

Render command impact: **none after merge**. The current command gains compact
default output without a flag or schedule change. Production must remain at
`SHADOW_DETECT` on its existing three-minute cadence.

Final verdict: **PASS — CU-08O ACCEPTED**.

The exact recommendation is a normal push/PR/merge of this small branch with no
Render configuration change. Do not progress to `SHADOW_FULL_CHAIN`.
