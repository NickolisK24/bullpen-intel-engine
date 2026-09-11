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

The report uses the canonical 30 MLB clubs. It fails nonzero unless complete active and 40-man evidence exactly matches the corresponding current non-void membership sets and boundary authority is valid. It exposes source/interval member IDs, missing/extra members, exact-match counts, source mismatches, and affiliate-ownership violations. Partial, failed, and missing acquisition remain explicit; complete-empty evidence is evaluated as an exact empty set.

Before a permanent Render service is reviewed, the bounded path can be invoked against the production application database through the manual `shadow_sp` mode of `.github/workflows/baseballos-sync.yml`. That mode skips the public-sync and other legacy workflow jobs, applies additive migrations, runs the allowlisted worker, captures the read-only health report, and retains both JSON artifacts for 30 days. It is not a scheduler and must not be treated as recurrent activation.

Stopping acquisition does not release canonical ownership. After the AUDIT-R2
writer-fencing migration, changing pipeline flags alone cannot return SP-owned
compatibility records to legacy writers. Preserve evidence and use an explicit
owner/recovery decision; do not remove the database guards to make a legacy write
succeed. The R2 package itself changes no flags or schedules.

## Shared writer ownership during coexistence

The temporary authority map is
[AUDIT-R2 shared writer fencing](AUDIT-R2_SHARED_WRITER_FENCING.md#5-new-ownership-model).
Final GameLog/PBP projections use one game fence. MLB pitcher organization/status
and exact-date snapshots use the SP-05 authority boundary. Transactions use a
scoped event lock and a captured predecessor version. Expected suppression is an
operational event, not a failed baseball source.

Inspect `writer_ownership` in certification health and recent
`compatibility_write_events` for `stale_suppressed` / `final_superseded`. A positive
suppression count is not itself unhealthy. Current Final/provisional overlap,
Final/GameLog disagreement, conflicting MLB claims, or governed pitcher team
mismatch remain blockers. Repeated active-job lock contention needs investigation.

R2 deployment must keep the integration entrypoint fail-closed until schema
`e3f6a9b2c5d8` is present. Verify that earlier integration invocations have ended
before applying the migration; an in-flight older SP owner lacks the scoped
transaction markers. Do not manufacture a production race. After migration,
verify the pointer and flags, inspect current conflicts read-only, and correct
affected roster projections through bounded SP-13 → SP-05 work. Observe natural
recurring cycles before claiming coexistence PASS. The migration refuses a
downgrade that would discard suppression history, unattributed legacy transaction
baselines, or repeated transaction fact versions.

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

A correction must produce closed â†’ reopened â†’ closed history; never overwrite the original closure evidence.

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

For atomic-reader rollback, explicitly set both
`SYNC_PIPELINE_ATOMIC_READS_ENABLED=false` and
`SYNC_PIPELINE_PUBLICATION_ENABLED=false`. Existing SP-11 manifests and
artifacts remain immutable; no database downgrade or evidence deletion is needed.

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

The queue proof must include SP-09/SP-10 progress. A cycle that drains live or
pregame acquisition while `process_derived_intelligence` grows is not stable
enough for publication, even when the overall worker result is `success`.

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

## Atomic publication reader readiness

Run the read-only atomic reader proof only after a current SP-11 publication
exists:

```powershell
python backend/scripts/run_atomic_reader_proof.py
```

The command must report complete generation-wide coverage and bind every tested
route to the current publication before `SYNC_PIPELINE_ATOMIC_READS_ENABLED` is
enabled. Required coverage includes all 30 Team Board v2 and What Changed
payloads, every published pitcher-current payload, game/matchup artifacts, and
the 30-team league generation. A 503 with
`atomic_publication_reader_coverage_incomplete` is a protective block, not a
reason to add a mutable-latest or legacy fallback inside an atomic request.

Reader-ready generations expose distinct artifact types for
`team_board_v2_publication`, `pitcher_current_publication`, and
`what_changed_publication`. Inspect their counts before controlled publication:

```sql
SELECT artifact_type, COUNT(*)
FROM atomic_publication_artifacts
WHERE publication_id = <publication-id>
GROUP BY artifact_type
ORDER BY artifact_type;
```

The expected team counts are 30 for Team Board v2 and What Changed. Pitcher
coverage is measured against active-bullpen pitcher IDs frozen inside those 30
Team Board artifacts, not every historical pitcher. Never repair a deficit by
editing an artifact or pointer; allow SP-10 to create an immutable successor
and publish it through SP-11.

Publication `1` is valid immutable SP-11 evidence but is not reader-cutover
ready: it has baseline team, pitcher, and game artifacts while the Team Board
v2, What Changed, and public pitcher-current payload families are absent.
Leave atomic reads false until a later reviewed CR-04 change produces and proves
those artifacts.

To roll back publication/read experimentation without deleting evidence:

```text
SYNC_PIPELINE_ATOMIC_READS_ENABLED=false
SYNC_PIPELINE_PUBLICATION_ENABLED=false
```

Restart only affected services. Do not edit `atomic_publication_current`
directly and do not remove publication history.

## AUDIT-R1 roster authority repair

Keep publication and atomic reads disabled. Before applying repair, inspect the complete interval/source census and confirm the exact integration deployment and migration `d2e5f8a1b4c7`. Do not repair only the four original Pittsburgh examples without checking the rest of the ledger.

Use SP-13 targeted roster repair with explicit MLB club IDs and the disputed baseball date:

```powershell
python scripts/run_sync_repair.py targeted --start-date YYYY-MM-DD --domain roster --team-id 134 --reason "AUDIT-R1 official MLB roster authority correction" --requested-by Nikko
```

Review the durable dry-run scope; add `--apply` only for the reviewed clubs. Dispatch its SP-13 planner through the repair worker. The ordinary non-publishing shadow worker consumes the resulting SP-05 owner jobs and SP-09/SP-10 descendants. Inspect/check the exact SP-13 request through its owner service; recurring shadow does not automatically consume SP-13 checker jobs. Do not enable publication or closure to finish roster repair.

SP-05 revalidates complete official MLB sources and the applied request scope. It supersedes invalid affiliate claims with explicit void versions, restores false MLB closure boundaries only with retained dated source proof, and emits new correction mutations. It does not delete history or manually move a publication pointer. A conflicting later stint, missing historical roster, or unresolved affiliate parent blocks automatic correction and requires evidence review.

Require 30/30 exact active and 30/30 exact 40-man sets, zero unresolved current affiliate claims, valid current MLB organization projections, correction-to-impact/cohort lineage, and naturally recurring cycles without new violations. Historical invalid versions remain visible as superseded evidence; zero means zero unresolved current claims, not deletion of old closures. Verify publication 1 is unchanged.
