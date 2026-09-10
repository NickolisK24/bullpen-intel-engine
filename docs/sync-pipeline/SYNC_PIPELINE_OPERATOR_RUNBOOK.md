# Sync Pipeline Operator Runbook

## Safety rules

Run operational commands from `backend`. Set `AUTO_SYNC=false`. Default certification and repair commands are non-destructive. Never update `game_logs`, Team State, current publication pointers, roster membership, or closure rows directly. Route corrections through the owner package.

## Inspect system health

```powershell
$env:APP_ENV = 'production'
$env:AUTO_SYNC = 'false'
python scripts/run_sync_pipeline_certification.py --environment production --expected-sha <deployed-sha>
```

This command is read-only by default and exits nonzero when a critical gate is failed or blocked. It reports queue status, stale leases, source failures/partials, overdue games, unreconciled Finals, pending plans/cohorts/publications, cache handoffs, closures, repairs, activation controls, and the legacy transition map.

Persisting a production evidence record requires both `--record` and `--allow-production-record`. Use it only after reviewing an evidence JSON document.

## Run one production shadow cycle

The dedicated shadow entrypoint consumes only the non-publishing SP-04 through SP-10 allowlist. With `--include-morning`, it plans SP-12 acquisition once per baseball date, including all 30 roster jobs and a bounded transaction window. It never claims SP-11 publication, cache handoff, morning orchestration, or closure work.

```powershell
$env:SYNC_PIPELINE_ENABLED = 'true'
$env:SYNC_PIPELINE_SHADOW_MODE = 'true'
$env:SYNC_PIPELINE_PUBLICATION_ENABLED = 'false'
$env:SYNC_PIPELINE_MORNING_ENABLED = 'false'
$env:SYNC_PIPELINE_CLOSURE_ENABLED = 'false'
$env:BASEBALLOS_LEGACY_PUBLICATION_ENABLED = 'true'
$env:BASEBALLOS_LEGACY_SCHEDULERS_ENABLED = 'true'
python scripts/run_sync_pipeline_shadow.py --max-jobs 24 --include-morning
```

The command fails closed unless the database is at the expected Alembic head and the exact shadow safety posture is valid. Its JSON output includes processed job, run, source observation, mutation, impact-plan, and cohort IDs plus publication-pointer before/after values. A nonzero exit indicates a partial or rejected cycle.

Inspect exact 30-team evidence without a source read or write:

```powershell
python scripts/report_roster_authority_coverage.py --baseball-date <yyyy-mm-dd>
```

The report fails nonzero unless the latest shadow morning run enumerated exactly 30 teams and every team has a complete authoritative active-roster attempt plus current SP-05 pitcher membership. Forty-man coverage is reported separately. Partial, failed, missing, and suspicious empty active rosters remain explicit.

Before a permanent Render service is reviewed, the bounded path can be invoked against the production application database through the manual `shadow_sp` mode of `.github/workflows/baseballos-sync.yml`. That mode skips the public-sync and other legacy workflow jobs, applies additive migrations, runs the allowlisted worker, captures the read-only health report, and retains both JSON artifacts for 30 days. It is not a scheduler and must not be treated as recurrent activation.

Rollback sets `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false`. Leave the two legacy controls true. Existing shadow evidence is retained.

## Inspect the durable queue

```sql
SELECT job_name, status, count(*)
FROM sync_jobs
GROUP BY job_name, status
ORDER BY job_name, status;

SELECT id, job_name, scope_key, attempts, max_attempts, lease_until, error_type
FROM sync_jobs
WHERE status IN ('retry_wait', 'dead')
ORDER BY updated_at DESC;
```

A running job with `lease_until < now()` is stale. Do not edit it manually; let SP-02 lease recovery reclaim it. A dead job requires source/canonical inspection and then a governed repair.

## Inspect a game lineage

```sql
SELECT game_pk, operational_state, game_state_fingerprint, source_observation_id
FROM scheduled_games WHERE game_pk = <game-pk>;

SELECT id, version_number, predecessor_version_id, core_completeness,
       boxscore_observation_id, play_by_play_observation_id, is_current
FROM final_game_versions WHERE game_pk = <game-pk>
ORDER BY version_number;

SELECT id, mutation_type, team_id, pitcher_id, source_observation_id
FROM final_game_mutations WHERE game_pk = <game-pk> ORDER BY id;

SELECT id, authority_class, status, affected_domains_json
FROM canonical_impact_plans
WHERE affected_game_ids_json::text LIKE '%<game-pk>%'
ORDER BY id;
```

For exact mutation-to-plan lookup, use `canonical_impact_plan_mutations`; do not rely on JSON text matching for a repair decision.

## Inspect pitcher/team derivation

```sql
SELECT c.id, c.authority_class, c.status, c.input_manifest_json,
       c.method_versions_json, c.predecessor_cohort_id, c.supersedes_cohort_id
FROM derived_intelligence_cohorts c
JOIN canonical_impact_plan_entities e ON e.impact_plan_id = c.impact_plan_id
WHERE e.entity_type = 'pitcher' AND e.entity_key = '<pitcher-id>'
ORDER BY c.id DESC;
```

Use `entity_type='team'` for a team. Inspect `derived_cohort_inputs` and `derived_intelligence_cohort_domains` before accepting a cohort as reproducible.

## Inspect publication consistency

```sql
SELECT p.publication_id, a.status, a.publication_fingerprint, a.published_at
FROM atomic_publication_current p
JOIN atomic_publications a ON a.id = p.publication_id
WHERE p.singleton_id = 1;

SELECT publication_id, artifact_type, entity_type, entity_key,
       source_snapshot_id, inherited_from_artifact_id
FROM atomic_publication_artifacts
WHERE publication_id = <publication-id>
ORDER BY artifact_type, entity_type, entity_key;
```

All response components must resolve from the current publication once. Until public consumers use this path, the legacy publication remains authority.

## Inspect closure and correction history

```sql
SELECT id, baseball_date, status, current_version_number, publication_id,
       expected_games, reconciled_final_games, next_check_at
FROM baseball_date_closures
ORDER BY baseball_date DESC;

SELECT version_number, event_type, closure_fingerprint, publication_id, created_at
FROM baseball_date_closure_versions
WHERE baseball_date = '<date>' ORDER BY version_number;

SELECT blocker_type, entity_type, entity_key, retryable, details_json
FROM baseball_date_closure_blockers
WHERE closure_id = <closure-id>;
```

A correction must produce closed → reopened → closed history; never overwrite the original closure evidence.

## Targeted repair dry run

```powershell
python scripts/run_sync_repair.py targeted --start-date 2026-09-09 --domain final_game --game-pk <game-pk> --reason "verify official correction"
```

The default is dry-run. It cannot mutate canonical facts, publish, move a pointer, or reopen a date.

## Apply a targeted repair

```powershell
python scripts/run_sync_repair.py targeted --start-date 2026-09-09 --domain final_game --game-pk <game-pk> --reason "official line differs" --requested-by <operator> --apply
```

This dispatches SP-07 owner work. Follow the repair request, child jobs, SP-09 plan, SP-10 cohort, SP-11 publication, and SP-12 closure rather than editing rows.

For a production terminal final-game obligation, the internal GitHub workflow
also exposes `mode=repair_final`. It requires `backfill_date`, `repair_game_pk`,
`recovery_reason`, and `confirm_recovery=RECOVER`. The workflow creates the same
SP-13 request, explicitly gives its SP-07 owner job the first claim, drains only
the non-publishing shadow allowlist, and uploads request, shadow, and health
evidence. It never revives or edits the terminal job and cannot publish.

## Bounded backfill

```powershell
python scripts/run_sync_repair.py backfill --start-date 2026-09-01 --end-date 2026-09-07 --domain final_game --reason "bounded missing final history"
```

Review the dry-run plan before adding `--apply`. Scopes beyond the standard guard require `--confirm-broad-scope`. No unbounded default exists.

## Method replay

```powershell
python scripts/run_sync_repair.py replay --date 2026-09-09 --impact-plan-id <plan-id> --method-version workload=<version> --reason "governed method replay"
```

Review first, then add `--apply`. A replay creates no fake source mutation and preserves prior cohorts/publications.

## Dead final-game job

1. Inspect the job attempt history and source fetch attempts.
2. Confirm MLB still reports authoritative Final.
3. Check whether a complete current SP-07 version already exists; a no-op retry is valid.
4. Submit a targeted final-game repair.
5. Verify exact affected entities flow through SP-09/10/11.
6. Recheck the affected baseball-date closure.

## Partial source

Keep prior complete authority. Do not clear pitchers, roster memberships, or starters from a partial payload. Inspect `source_fetch_attempts`, wait for/retry the owner job, and leave closure blocked when the partial source is critical.

## Stuck Final or publication

For a Final, inspect SP-04 state, SP-07 version, mutation references, and active/dead jobs in that order. For publication, inspect cohort status and input watermark before the manifest. A preparation failure must leave the old pointer current; a cache failure retries handoff without creating a new publication.

## Emergency disable and rollback

1. Set all `SYNC_PIPELINE_*` controls false.
2. Stop only the new queue worker/planner services introduced by the later cutover.
3. Confirm legacy publication and schedulers are enabled.
4. Do not delete new tables or evidence.
5. Verify the public legacy publication identity and freshness endpoint.
6. Record the incident and open a bounded repair if authority work was interrupted.

SP-14 does not perform this cutover because the current certification verdict is NO-GO.

## Controlled integration deployment preflight

Before any atomic publication or reader cutover, verify all of the following
against the actual Render service rather than repository intent:

1. The dedicated shadow service reports `branch=feat/sync-pipeline` and the
   reviewed exact commit in `RENDER_GIT_COMMIT`.
2. Its command is
   `python backend/scripts/run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation`.
3. Existing database and secret-group wiring remains attached without printing
   values.
4. Publication, morning, and closure controls remain false during the first
   three recurring cycles; both legacy controls remain true.
5. Those cycles create SyncRuns, consume SP-02 jobs, preserve 30/30 roster
   authority, drain rather than grow the bounded queue, and leave
   `atomic_publication_current` unchanged.

The repoint gate was satisfied on 2026-09-10 for cron
`crn-da98kclg1s2s739k0870`, deploy `dep-dahc5i15efls73dfnub0`, and SHA
`63f87feb421eb446fae09d28ab86390ecbbbb8ed`. Operators must still run the full
list above after every deploy. A recurring service on an older integration SHA
does not prove later repair/publication code.

Do not enable publication merely because recurrence passes. Confirm
`blocking_dead_jobs=0`, `unreconciled_final_games=0`, 30/30 roster authority,
bounded queue progress, a selected/revalidated current SP-10 cohort, and a
deployed publication-bound consumer with a tested legacy rollback. A historical
dead row may remain only when health records a later succeeded owner job and a
current final version; otherwise it is still blocking.
