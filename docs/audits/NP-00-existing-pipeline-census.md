# NP-00 · BaseballOS production pipeline census

**Review baseline:** main `2160a66848f87a348e57667a7a3160ba5d560a79`, November 21, 2026 UTC. Historical runtime inspected at `617ab650febc1b6a8567fba264150353b2f4b3c4`. Live catalog head `e241f709cd36`. This inventory is a replacement contract for review. It grants no execution, migration, queue or publication authority.

## Decision

Reuse the baseball calculations, evidence contracts, validation and rehearsal fixtures. Isolate **all** replacement writes, including queue claims, source fetch receipts, canonical selectors, candidate artifacts and distribution. The current system already contains two implementations that share physical state. Giving a third runtime its own scheduler or a new lane label would still allow it to affect the other two.

The repository and live checks identify the serving pipeline and the historical worker's allowed handlers. The retirement inventory remains open on the disposition of historical obligations and on attribution of any out-of-band writers using shared database credentials. Neither gap requires a production repair to conduct this census.

## Production execution map

Render service listing and latest live deployments were checked in My Workspace. Only services connected to this repository are included. Times are UTC.

| Actor | Trigger and entry | Responsibility the replacement must preserve |
|---|---|---|
| Daily Primary | 10:05, `run_due_sync.py --mode daily --public-only` | Acquire roster, transactions, schedule and pitching evidence, derive the eligible cohort, attempt fully proven publication. Preserve an explicit withheld outcome. |
| Postgame Primary | 02:05, 04:05, 06:05, same runner, postgame | Reconcile official completed games, account for missing or conflicting lines, preserve valid no-game outcomes and bounded retries. |
| Morning Primary | 14:05, same runner, morning | Refresh schedule and Tonight coherence without taking daily ingestion authority. |
| GitHub fallback | `baseballos-sync.yml`, daily 10:17, morning 14:23, postgame 02/04/06:11 | Same durable window, execution-source validation and nonblocking PostgreSQL advisory lock. Fallback may record already satisfied. Governed incident recovery requires its own authority and receipt. |
| Continuous Updates | Every 15 minutes, `scripts/run_continuous_cycle.py` | Live **full_live** lane. Detect changes, evaluate canonical work, rebuild affected facts, run admission and conditional publication/cache handoff. Sync runs 98399 and 98400 each made one source request, saw zero changed games and published nothing. Preserve the distinction between an idle cycle and authority to act on a changed game. |
| Historical continuous-shadow-detect | Every three minutes, historical `run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation` | Its handler allowlist covers schedule, roster, transactions, pregame, live delta, final reconciliation, canonical impact and derived intelligence. Derived publication candidates disabled there. Those handlers can produce durable canonical effects. Gate fails before dispatch at current schema. Separate from the GitHub shadow validator. |
| API | `scripts/render_start.sh` → migration authority → Gunicorn/Flask | Schema owner/verify-only contract, serving selectors, protected operator endpoints. `app._init_scheduler` also contains a conditional 06:00 Eastern APScheduler. Production runbook requires AUTO_SYNC=false. Keep the replacement out of web startup. |
| GitHub follow-up jobs | Team State proof, shadow activation health, internal enrichment, static team/story preview, intraday audit | Preserve job conditions and evidence separately. Internal enrichment checkpoints can write evidence and backtests. Observers validate executed cycles or record legitimate no-ops. Static delivery can write repository artifacts. |
| Distribution, maintenance and repairs | Workflow inventory below; `backend/scripts/` also has standalone operators | Exact publication ID and generation checks on exports. Keep approved dry-run, plan, apply and recovery boundaries for each operator. A manually dispatchable workflow confers no scheduled writer authority. |
| Browser/edge | React/Vite plus generated preview pages | Snapshot-bound HTTP representations, coherent caches and immutable citations. Account, editorial, traffic, signup and share-interaction writes are independent application responsibilities. Keep them outside baseball-data ownership. |

Five Render components ran the main revision above. The sixth, `crn-da98kclg1s2s739k0870`, remained scheduled with a live September deploy. Event `evt-dc0g8pgae00c73b6mcqg` ended unsuccessfully at 02:39:34 UTC. Its application log reports `expected_migration_head_b6c9d2e5f8a1_got_('e241f709cd36',)`. A live deployment and a successful execution are separate facts.

On November 20 the 10:05 external daily attempt recorded verified publication **5842 → 5843**. The 10:17 GitHub attempt recorded already satisfied. On November 21 the 02:05 external postgame attempt recorded executed, no candidate expected, **5843 → 5843**. These are three different parity cases.

## Acquisition, canonical writers and correction contracts

Paths below are relative to `backend/services/` unless qualified. Historical paths refer to the pinned historical commit.

| Domain | Source and current owner | Contract to carry forward |
|---|---|---|
| Club directory, affiliate and people identity | MLB Stats API teams, team metadata, people/batch/search, minor-league teams and prospect stats in `mlb_api.py`; `mlb_club_directory.py`, `team_directory.py`, `pitcher_identity_reconciliation.py` | Separate MLB club, affiliate, person, pitching participant and current projection. Retain season and team-at-appearance. Prospect capability alone cannot prove organizational coverage. |
| Schedule, finality, venue, game sides and probable starters | MLB schedule, linescore, boxscore, live feed; `schedule_ingestion.py`, `schedule_authority.py`, `game_finality.py`, `starter_assignment_context.py` | Canonical gamePk and side, game dates vs start instant, doubleheaders, postponements, suspended/resumed games and off-days. Schedule writers declare owners. A failed request cannot establish an empty slate. |
| Roster membership and assignment | MLB active, 40Man, fullRoster and nonRosterInvitees; `roster_evidence.py`, `primary_roster_inputs.py`, `roster_status_sync.py`, `team_assignment_sync.py`; historical `roster_transaction_authority.py` | Retain complete represented-date views, SHA-256, acquisition times and observation IDs. Active and forty-man are independent. Current projection, point observation and half-open membership interval have different meanings. Preserve affiliate precedence, stale suppression and both clubs' evidence on transfers. |
| Transactions and historical repairs | MLB transactions with date and entity filters; `transaction_ingestion.py`, `transaction_participant_qualification.py`, historical versioned writer and `repair_orchestration.py`; migration `c71b09e45a82_burgos_history_repair.py` | Keep source-effective and observation dates, versions, supersession, idempotence and explicit scope. A primary transaction already versioned by the historical writer remains fenced. The Burgos exception cannot become generic backdating authority. |
| Appearances, official lines and starter identity | Pitcher game logs plus official final boxscore; `sync.py` daily and `process_completed_game_for_postgame_refresh`, `game_appearance_extraction.py`, `gamelog_source_authority.py`, `appearance_team_authority.py` | Key by player and game, preserve side, finality, starter/reliever and unknown stats. Compare official lines. Current historical final versions fence primary mutations to game logs, processed markers and PBP. Governed repairs invalidate dependent evidence via `sync.direct_game_log_evidence_registry`. |
| Plays, pitches, leverage and game context | Official play-by-play/live feed, linescore and boxscore; `play_by_play_foundation.py`, `completed_game_context_service.py`, `team_game_pitching_splits.py`, `game_observation_states` | Preserve event identity, observation ordering, coverage/completeness and side. Pitch events can supply measured pitch speed and classification. Complete multi-season Statcast movement, release and extension coverage requires independent acquisition and retention proof. |
| Observations and receipts | `models/source_observation.py` (in backend), primary roster input writer and historic source adapters | Stable subject → attempted fetch → versioned observation → content-addressed JSON. A normalized roster input can reproduce membership; a projection, error, digest alone or fetch timestamp cannot. A generic artifact table does not prove each adapter persisted a replayable response. |
| Job control, retries, backfill | `sync_due.py`, `sync_execution_context.py`, `sync_jobs.py`, `dead_letter.py`, `game_ingestion_planner.py`, `postgame_recovery.py`, historical leased job executor | Distinguish product window, job, claim, retry, heartbeat, failure, baseball mutation and publication. Preserve per-operation identities and retry bounds. Daily/postgame game-driven shadow observations do not imply general automatic write/backfill approval. |
| Continuous and selector fences | `continuous_execution.py`, `continuous_game_work.py`, `continuous_publication_admission.py`, `continuous_production_publication.py`, `fence_audit.py` | Reuse deterministic change checks and scoped invalidation. Count suppressed physical writes. A repeated slate rejection is reusable only for the same dependency signature. The signature reads historical roster and final-version relations absent from main's ORM. |
| Atomic and progressive publication | `sync.complete_sync_run_with_snapshot`, `dashboard_snapshot.publish_dashboard_snapshot`, `sync_publication_proof.py`, `team_progressive_publication.py`, `team_publication_storage.py`, historical `atomic_publication*.py` | Distinguish global trusted Dashboard, per-team pointers, Tonight editions and historical atomic selectors. Validate all 30 teams including governed withholding, freshness, reference dates, roster and ledger coverage. Persist proof with promotion. Post-commit delivery must use the committed generation. |
| Distribution and editorial | `distribution_delivery.py`, `share_artifact_publication_hook.py`, `share_artifact_repository.py`, `export_team_story_pages.py` and `export_share_artifact_pages.py` under scripts | Pin outputs to accepted publication and preserve original share evidence. Static files and web caches are additional output boundaries. A candidate must never enqueue production distribution. |

### Other persistent writers and indirect effects

| Records | Writer or entry point | Replacement obligation |
|---|---|---|
| Historical pregame versions, provisional appearance states, final versions, canonical impact plans and derived cohorts | At `617ab650`, the allowlisted handlers in `sync_pipeline_shadow.production_shadow_handlers` dispatch to `pregame_context.py`, `live_game_delta.py`, `final_game_reconciliation.py`, `canonical_impact.py` and `derived_intelligence.py`. | Preserve provisional/final separation, supersession and affected subjects. Replaying a shadow job into a shared table can alter which later primary write is eligible. |
| Baseball-date closures, repair requests/chunks/blockers, certification checks and legacy transition state | Historical `daily_reconciliation.py`, `repair_orchestration.py`, `sync_pipeline_certification.py` and `atomic_publication_cutover.py`. The deployed shadow allowlist covers only a subset of historical job types. | Preserve audit records and scope; distinguish an executable handler from an installed model. No automatic takeover of historical operators. |
| Gate-suppression audit | PostgreSQL trigger bodies in migrations `e3f6a9b2c5d8`, `a5b8c1d4e7f0` and `f4a7b0c3d6e9`; `fence_audit.py` reads suppression counts. | Compare accepted physical mutations. An ORM reporting success can conceal a suppressed write. |
| Evidence objects and citations, composed reads and legacy divergence audits | `evidence_contract.py`, `evidence_composition_service.py`, `composed_read.py`, `legacy_read_reconciliation.py`, internal enrichment in `sync.py`. | Reuse rule versions, source identity, dependent citations, missing-data behavior and correction policies. The direct GameLog invalidation registry separately names workload, appearance context, inherited traffic, entry-band usage and team relief composition. |
| Availability backtests, internal surfaces and historical ledgers | `availability_backtest.py`, `intelligence_surface_snapshot.py`, `tonight_intelligence_snapshot.py`, `pitcher_season_ledger_coverage.py`. | Preserve sample boundaries, historical rows and the different failure policies for internal products and public promotion. |
| Publication-derived side effects | `tonight_read_model.py`, `share_artifact_generation.py`, `share_artifact_batch_generation.py`, `team_progressive_publication.py`, `distribution_delivery.py`. | Include Tonight rows, per-team artifacts, static exports, generation audits and share hooks in the parity inventory. Isolate candidate sinks as well as the trusted pointer. |
| Other application state | `backend/api/{auth,me,private_posts,traffic,audience}.py`, `services/slate_briefing.py`, `backend/seed.py` and prospect routes. | Preserve application ownership and API contracts. Seed and operator scripts are distinct from scheduled acquisition. Independent data such as users, audience and traffic does not belong in a replacement baseball-data backfill. |

## Intelligence and consumer contracts

The public selection and frozen-package boundaries are `public_serving_authority.py`, `public_surface_projections.py`, `team_board_delivery.py` and `frontend/src/utils/api.js`. Main's browser route table is `frontend/src/App.jsx`. Preserve identity-bound core/details requests, current alias vs immutable snapshot caching, stable public vocabulary and unavailable reasons.

| Consumer or field family | Inputs → existing implementation | Required comparison |
|---|---|---|
| Workload, rest, concentration, clean options | Dated relief appearances, pitches, outs, rest days, active roster → `workload_appearance.py`, `ledger_confirmed_rest.py`, `workload_concentration.py`, `team_board_workload_coverage.py` | Compare covered windows, named arms, missing vs zero, comparable prior windows and exact baseball dates. |
| Arm reads, availability and Team State | Workload, roster, availability reference date, competition status → `availability.py`, `availability_reference_date.py`, `team_state_eligibility.py`, `team_state_vnext_production_proof.py` | Same eligible population, classification and withholding for season-complete teams. Preserve stale data-through without assigning current readiness. |
| Deployment, roles and movement | Inning-entry evidence, leverage, saves/holds and season baseline → `pitcher_role_authority.py`, `role_movement.py`, `team_board_public_deployment_context.py` | Compare named-arm samples, evidence-supported movement, and explicit unknowns. |
| Qualified performance, pitch characteristics | Official lines, active-group selection, PBP coverage and verified samples → `team_performance_evidence.py`, `public_team_performance.py`, `pitcher_performance.py`, `pitcher_trends.py` | Compare denominators, K-BB%, HR, inherited runners, velocity and mix including withheld values and source coverage. |
| Rotation, schedule and depth | Official starters, game splits, calendar and roster evidence → `rotation_context.py`, `rotation_support_pressure.py`, `schedule_context.py`, `roster_depth_evidence.py` | Short starts, transferred innings, off-days, doubleheaders, depth and handedness require supporting records. |
| Tonight, League, Team Board and Matchup | Slate, team states, active arms and comparable publication → `tonight_v1_serving.py`, `league_team_state_listing.py`, `team_board_v2.py`, `trusted_compare_authority.py` | Played and quiet slates, all 30 distinct clubs, team core/details agree on generation, both matchup sides carry aligned evidence. |
| Pitcher and Search | Identity, published performance/reads, appearance ledger, retained velocity/mix and role history → `public_recent_work.py`, `pitcher_publication_history.py`, `discovery_search.py` | Preserve historical team-at-appearance, null vs zero, dated claims and canonical destinations. |
| What Changed and History | Prior comparable generations, transactions and dated game events → `team_board_what_changed.py`, `team_state_history.py`, `team_history_context.py` | Same event, entity, dates and citation on both surfaces. Preserve gaps, corrections and superseded claims. |
| Stories, Share, Methodology and Trust | Published observations, governed language, manifests and proof → `story_intelligence_service_v1.py`, `share_artifact_public.py`, `backend/api/methodology.py` | Historical links remain reproducible. Distinguish published facts, eligibility and editorial copy. Keep account and traffic data outside parity fixtures. |

## Architectural constraints and acceptance evidence

1. **Shared ownership is material.** The production catalog contains 89 public tables. Historical tables and columns survive newer main migrations. `sync_jobs` includes lease and worker columns beyond main's model. A bounded query below returned 173 pending historical jobs, comprising 152 September 24 pregame fetches, 16 September 9–24 schedule fetches and five September 4–12 repair checks. The deployed shadow handler allowlist excludes repair checks. Independent internal enrichment had 14 pending rows. Pending status alone cannot decide whether work is still required. Preserve IDs and lineage while comparing each obligation to later accepted evidence.
2. **Source retention differs by domain and era.** The primary roster writer now stores normalized dated inputs with companion observations. Existing historic projections, including September roster evidence, cannot inherit those guarantees retroactively. Certify adapters on retained samples, not table presence.
3. **A parity oracle needs more than equality.** Include a legitimately withheld offseason cohort, an unchanged retained generation, an executed final, a suppressed write, a doubleheader, a trade/affiliate transaction, a corrected line, an incomplete official response and a failed promotion. Distinguish unexplained differences from evidence-backed corrections to legacy output.
4. **The latency target needs a distribution.** Previously sampled Boston requests of 5.24 s core and 8.87 s details were concurrent individual requests. They do not establish a fleet percentile or database bottleneck. Measure matched cold/warm requests per route, payload identity, bytes, CPU/memory and source calls, separating live and backfill budgets.
5. **Acceptance boundary.** Jobs, relations, triggers and application entry points below are inspectable. A database login with shared credentials is insufficient to identify a human or external process. Keep an explicit open item for deployment-owner confirmation of external schedulers, shared writer principals and ad hoc scripts. Record disposition of historical obligations before treating any previous writer as replaceable. An isolated replay may reuse pure calculations; no new runtime is approved by this census.

Read-only evidence queries (2026-11-21 UTC):

```sql
SELECT version_num FROM public.alembic_version LIMIT 1;
SELECT mode,source,scheduled_for,outcome,publication_outcome,snapshot_before_id,snapshot_after_id
FROM public.sync_schedule_attempts ORDER BY id DESC LIMIT 8;

SELECT job_name,count(*),min(product_date),max(product_date)
FROM (SELECT job_name,product_date FROM public.sync_jobs
      WHERE status='pending' AND lane='sync_pipeline' ORDER BY id LIMIT 500) j
GROUP BY job_name ORDER BY job_name;

SELECT c.relname,p.proname,t.tgenabled FROM pg_trigger t
JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_proc p ON p.oid=t.tgfoid
WHERE c.relnamespace='public'::regnamespace AND NOT t.tgisinternal ORDER BY 1,2 LIMIT 240;
```

The visible PostgreSQL privilege catalog listed `postgres` and `service_role` with relation-level write grants on all 89 public tables. This describes potential access subject to effective role, RLS and triggers. It cannot establish which deployments hold a credential or whether an operator used it. `to_regclass('cron.job')` returned NULL. The repository's `frontend/vercel.json` contains delivery configuration and declares no cron. These observations narrow the scheduler inventory without establishing that an external caller is impossible.

## Writer attribution follow-up

On November 21 the operator reported that out-of-band writer use is unknown. A read-only check of the preceding 24 hours (November 20 02:45 to November 21 02:45 UTC) found 358 PostgreSQL log entries. The application label was empty on 334, Supavisor on 22 and PostgREST on two. Of 2,904 pooler log entries, 2,194 identified Supavisor and 710 had no application label. The 48 edge entries included zero POST, PUT, PATCH or DELETE requests to a path starting with `/rest/v1/`. These are counts of log entries. No statement text, client addresses or credential values were exported.

The window includes a known daily publication. None of the 358 PostgreSQL log entries had an INSERT, UPDATE or DELETE command tag. This log stream cannot enumerate even the known publication writes; extending the same query cannot establish the absence of other writers. A point-in-time session inventory likewise showed infrastructure labels and could not attribute past writers. Retain this as an unresolved authority question.

## Historical reuse evidence

The historical [SP-00 census](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/docs/sync-pipeline/SP-00_BULLPEN_DATA_CENSUS_AND_ACQUISITION_CONTRACT.md) inventories source grain, fields and potential coverage as of September 5. Its claims about current storage and roster support require reconciliation with the newer schema and primary roster input writer above.

The [CR-04 decision](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/docs/sync-pipeline/CR-04_INTEGRATION_DEPLOYMENT_ATOMIC_PUBLICATION_CUTOVER.md) records an actual withheld reader cutover. Historical atomic publication 1 lacked public Team Board v2, What Changed and pitcher-current artifacts. Preserve this exact refusal case in the replacement comparison set. The historical [full-chain test](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/tests/test_sync_pipeline_full_chain.py) supplies a fixture domain executor for read models. It exercises orchestration; product parity requires the real current builders.

## Operator and workflow index

All versioned GitHub workflows at the baseline. Links include their input confirmations, exact commands, conditions, secrets by name, and allowed modes. CI uses disposable services. Distribution can write generated files. Other jobs derive authority from their entry point and inputs.

| Workflow | Triggers | Job IDs |
|---|---|---|
| [appearance_team_backfill_2026.yml](../../.github/workflows/appearance_team_backfill_2026.yml) | workflow_dispatch | backfill-2026 |
| [baseballos-generated-distribution.yml](../../.github/workflows/baseballos-generated-distribution.yml) | workflow_dispatch | deliver-generated-content |
| [baseballos-intraday-repair.yml](../../.github/workflows/baseballos-intraday-repair.yml) | workflow_dispatch | intraday-roster-repair |
| [baseballos-production-maintenance.yml](../../.github/workflows/baseballos-production-maintenance.yml) | workflow_dispatch | maintain-production |
| [baseballos-scheduler-health.yml](../../.github/workflows/baseballos-scheduler-health.yml) | workflow_dispatch | scheduled-run-health |
| [baseballos-sync.yml](../../.github/workflows/baseballos-sync.yml) | schedule, workflow_dispatch | public-sync, team-state-vnext-proof, shadow-activation-health, internal-enrichment, static-team-story-preview, intraday-audit |
| [canonical_season_bullpen_aggregation.yml](../../.github/workflows/canonical_season_bullpen_aggregation.yml) | workflow_dispatch | aggregate |
| [ci.yml](../../.github/workflows/ci.yml) | push, pull_request, workflow_dispatch | postgres-migrations, backend-collection-accounting, backend-postgres-tests, frontend-tests, browser-quality, dependency-audit |
| [inherited-runners-authority-diagnostic.yml](../../.github/workflows/inherited-runners-authority-diagnostic.yml) | workflow_dispatch | inherited-runners-authority-diagnostic |
| [manual-game-driven-noop-qualification.yml](../../.github/workflows/manual-game-driven-noop-qualification.yml) | workflow_dispatch | noop-write-qualification |
| [manual-noop-qualification-candidate-audit.yml](../../.github/workflows/manual-noop-qualification-candidate-audit.yml) | workflow_dispatch | candidate-audit |
| [manual-postgame-publication-incident-audit.yml](../../.github/workflows/manual-postgame-publication-incident-audit.yml) | workflow_dispatch | incident-audit |
| [manual-publication-truth-certification.yml](../../.github/workflows/manual-publication-truth-certification.yml) | workflow_dispatch | publication-truth-certification |
| [manual-team-state-coverage-diagnostic.yml](../../.github/workflows/manual-team-state-coverage-diagnostic.yml) | workflow_dispatch | team-state-coverage-diagnostic |
| [official-starter-alignment-audit.yml](../../.github/workflows/official-starter-alignment-audit.yml) | workflow_dispatch | audit |
| [official_pitching_line_completeness.yml](../../.github/workflows/official_pitching_line_completeness.yml) | workflow_dispatch | diagnose |
| [official_pitching_line_matt_festa_apply.yml](../../.github/workflows/official_pitching_line_matt_festa_apply.yml) | workflow_dispatch | apply |
| [official_pitching_line_repair_apply.yml](../../.github/workflows/official_pitching_line_repair_apply.yml) | workflow_dispatch | apply |
| [official_pitching_line_repair_closeout.yml](../../.github/workflows/official_pitching_line_repair_closeout.yml) | workflow_dispatch | closeout |
| [official_pitching_line_repair_plan.yml](../../.github/workflows/official_pitching_line_repair_plan.yml) | workflow_dispatch | plan |
| [official_pitching_line_transition_diagnostic.yml](../../.github/workflows/official_pitching_line_transition_diagnostic.yml) | workflow_dispatch | diagnose |
| [phantom_game_log_guard.yml](../../.github/workflows/phantom_game_log_guard.yml) | pull_request | focused-postgres-tests |
| [phantom_game_log_reconciliation.yml](../../.github/workflows/phantom_game_log_reconciliation.yml) | workflow_dispatch | reconcile |
| [team-state-history-export.yml](../../.github/workflows/team-state-history-export.yml) | workflow_dispatch | export |
| [team-state-population-compare.yml](../../.github/workflows/team-state-population-compare.yml) | workflow_dispatch | compare |
| [unresolved_appearance_team_diagnostic_2026.yml](../../.github/workflows/unresolved_appearance_team_diagnostic_2026.yml) | workflow_dispatch | diagnose |
| [unresolved_appearance_team_repair_2026.yml](../../.github/workflows/unresolved_appearance_team_repair_2026.yml) | workflow_dispatch | repair |

Standalone acquisition, backfill, reconciliation, repair and publication operators also exist outside scheduled workflows. Each entry below links to its actual guard and defaults. Historical operator availability does not confer permission to run it.

| Operator family | Versioned entry points |
|---|---|
| audit | [appearance_ledger_audit.py](../../backend/scripts/appearance_ledger_audit.py), [audit_availability_explanations.py](../../backend/scripts/audit_availability_explanations.py), [audit_availability_post_adoption_readiness.py](../../backend/scripts/audit_availability_post_adoption_readiness.py), [audit_availability_thresholds.py](../../backend/scripts/audit_availability_thresholds.py), [run_2026_residual_audit.py](../../backend/scripts/run_2026_residual_audit.py), [run_appearance_team_coverage_audit.py](../../backend/scripts/run_appearance_team_coverage_audit.py), [run_internal_snapshot_audit.py](../../backend/scripts/run_internal_snapshot_audit.py), [run_official_starter_alignment_audit.py](../../backend/scripts/run_official_starter_alignment_audit.py), [verify_dependency_audit.py](../../backend/scripts/verify_dependency_audit.py) |
| backfill | [backfill_completed_game_context.py](../../backend/scripts/backfill_completed_game_context.py), [backfill_game_log_innings_outs.py](../../backend/scripts/backfill_game_log_innings_outs.py), [backfill_games_started.py](../../backend/scripts/backfill_games_started.py), [backfill_pitcher_game_logs.py](../../backend/scripts/backfill_pitcher_game_logs.py), [recalculate_after_games_started_backfill.py](../../backend/scripts/recalculate_after_games_started_backfill.py), [recalculate_after_innings_backfill.py](../../backend/scripts/recalculate_after_innings_backfill.py), [run_2026_appearance_team_backfill.py](../../backend/scripts/run_2026_appearance_team_backfill.py) |
| diagnos | [diagnose_slate_coverage.py](../../backend/scripts/diagnose_slate_coverage.py), [diagnose_team_state_coverage.py](../../backend/scripts/diagnose_team_state_coverage.py), [run_official_pitching_line_transition_diagnostic_2026.py](../../backend/scripts/run_official_pitching_line_transition_diagnostic_2026.py), [run_unresolved_appearance_team_diagnostic_2026.py](../../backend/scripts/run_unresolved_appearance_team_diagnostic_2026.py) |
| export | [export_bullpen_identity_distribution_review.py](../../backend/scripts/export_bullpen_identity_distribution_review.py), [export_consequence_intelligence_review.py](../../backend/scripts/export_consequence_intelligence_review.py), [export_context_explanation_editorial_review.py](../../backend/scripts/export_context_explanation_editorial_review.py), [export_four_beat_real_quality_audit.py](../../backend/scripts/export_four_beat_real_quality_audit.py), [export_share_artifact_pages.py](../../backend/scripts/export_share_artifact_pages.py), [export_team_state_history.py](../../backend/scripts/export_team_state_history.py), [export_team_story_pages.py](../../backend/scripts/export_team_story_pages.py), [export_todays_story_editorial_review.py](../../backend/scripts/export_todays_story_editorial_review.py), [export_what_changed_since_yesterday_review.py](../../backend/scripts/export_what_changed_since_yesterday_review.py) |
| ingest | [game_driven_ingestion.py](../../backend/scripts/game_driven_ingestion.py), [ingest_schedule.py](../../backend/scripts/ingest_schedule.py), [inspect_game_ingestion_writes.py](../../backend/scripts/inspect_game_ingestion_writes.py), [profile_daily_ingestion_readonly.py](../../backend/scripts/profile_daily_ingestion_readonly.py) |
| other | [build_composed_reads.py](../../backend/scripts/build_composed_reads.py), [build_dashboard_snapshot.py](../../backend/scripts/build_dashboard_snapshot.py), [build_team_state_correction_manifest.py](../../backend/scripts/build_team_state_correction_manifest.py), [ci_shard.py](../../backend/scripts/ci_shard.py), [compare_team_state_populations.py](../../backend/scripts/compare_team_state_populations.py), [database_migrations.py](../../backend/scripts/database_migrations.py), [detect_game_changes.py](../../backend/scripts/detect_game_changes.py), [evaluate_shadow_activation_gate.py](../../backend/scripts/evaluate_shadow_activation_gate.py), [experiment_unavailable_thresholds.py](../../backend/scripts/experiment_unavailable_thresholds.py), [generate_coin_story_corpus.py](../../backend/scripts/generate_coin_story_corpus.py), [inspect_coin_story.py](../../backend/scripts/inspect_coin_story.py), [inspect_first_write_pitcher_identity.py](../../backend/scripts/inspect_first_write_pitcher_identity.py), [inspect_gamelog_field_authority.py](../../backend/scripts/inspect_gamelog_field_authority.py), [orchestrate_game_change.py](../../backend/scripts/orchestrate_game_change.py), [plan_boxscore_balls_fallback_impact.py](../../backend/scripts/plan_boxscore_balls_fallback_impact.py), [prepare_daily_edition_snapshot.py](../../backend/scripts/prepare_daily_edition_snapshot.py), [prepare_shadow_handoff.py](../../backend/scripts/prepare_shadow_handoff.py), [prove_incremental_workload_rest.py](../../backend/scripts/prove_incremental_workload_rest.py), [render_read_review_packet.py](../../backend/scripts/render_read_review_packet.py), [render_start.sh](../../backend/scripts/render_start.sh), [resolve_github_scheduled_for.py](../../backend/scripts/resolve_github_scheduled_for.py), [review_unavailable_boundary_cases.py](../../backend/scripts/review_unavailable_boundary_cases.py), [roster_readiness_dead_letter_report.py](../../backend/scripts/roster_readiness_dead_letter_report.py), [run_2026_season_bullpen_aggregation.py](../../backend/scripts/run_2026_season_bullpen_aggregation.py), [run_continuous_cycle.py](../../backend/scripts/run_continuous_cycle.py), [run_internal_enrichment.py](../../backend/scripts/run_internal_enrichment.py), [run_official_pitching_line_completeness_2026.py](../../backend/scripts/run_official_pitching_line_completeness_2026.py), [run_official_pitching_line_matt_festa_apply_2026.py](../../backend/scripts/run_official_pitching_line_matt_festa_apply_2026.py), [scan_forbidden_artifact_content.py](../../backend/scripts/scan_forbidden_artifact_content.py), [validate_game_driven_shadow_cycle.py](../../backend/scripts/validate_game_driven_shadow_cycle.py), [validate_intraday_artifact.py](../../backend/scripts/validate_intraday_artifact.py), [verify_generated_share_previews.py](../../backend/scripts/verify_generated_share_previews.py), [verify_generated_team_previews.py](../../backend/scripts/verify_generated_team_previews.py) |
| proof | [run_cu01p_proof.py](../../backend/scripts/run_cu01p_proof.py), [run_cu04_proof.py](../../backend/scripts/run_cu04_proof.py), [run_cu05_proof.py](../../backend/scripts/run_cu05_proof.py), [run_cu06_proof.py](../../backend/scripts/run_cu06_proof.py), [validate_team_state_vnext_proof.py](../../backend/scripts/validate_team_state_vnext_proof.py) |
| publication | [bootstrap_team_publications.py](../../backend/scripts/bootstrap_team_publications.py), [certify_publication_truth.py](../../backend/scripts/certify_publication_truth.py), [daily_publication_memory_harness.py](../../backend/scripts/daily_publication_memory_harness.py), [export_team_state_publication_proof.py](../../backend/scripts/export_team_state_publication_proof.py), [rehearse_trusted_publication.py](../../backend/scripts/rehearse_trusted_publication.py), [resolve_distribution_publication.py](../../backend/scripts/resolve_distribution_publication.py), [run_postgame_publication_incident_audit.py](../../backend/scripts/run_postgame_publication_incident_audit.py) |
| qualif | [run_game_driven_noop_qualification.py](../../backend/scripts/run_game_driven_noop_qualification.py), [run_noop_qualification_candidate_audit.py](../../backend/scripts/run_noop_qualification_candidate_audit.py) |
| reconcil | [production_accuracy_reconciliation.py](../../backend/scripts/production_accuracy_reconciliation.py), [run_intraday_reconcile.py](../../backend/scripts/run_intraday_reconcile.py), [run_phantom_game_log_reconciliation.py](../../backend/scripts/run_phantom_game_log_reconciliation.py), [run_reconciliation_audit.py](../../backend/scripts/run_reconciliation_audit.py) |
| refresh | [refresh_availability_backtest.py](../../backend/scripts/refresh_availability_backtest.py), [refresh_share_preview_presentation.py](../../backend/scripts/refresh_share_preview_presentation.py), [refresh_slate_schedule.py](../../backend/scripts/refresh_slate_schedule.py), [run_postgame_refresh.py](../../backend/scripts/run_postgame_refresh.py), [run_tonight_refresh.py](../../backend/scripts/run_tonight_refresh.py) |
| repair | [repair_current_team_state_artifacts.py](../../backend/scripts/repair_current_team_state_artifacts.py), [repair_daily_edition_context.py](../../backend/scripts/repair_daily_edition_context.py), [run_2026_opening_week_schedule_repair.py](../../backend/scripts/run_2026_opening_week_schedule_repair.py), [run_intraday_completed_game_repair.py](../../backend/scripts/run_intraday_completed_game_repair.py), [run_intraday_repair.py](../../backend/scripts/run_intraday_repair.py), [run_official_pitching_line_repair_apply_2026.py](../../backend/scripts/run_official_pitching_line_repair_apply_2026.py), [run_official_pitching_line_repair_closeout_2026.py](../../backend/scripts/run_official_pitching_line_repair_closeout_2026.py), [run_official_pitching_line_repair_plan_2026.py](../../backend/scripts/run_official_pitching_line_repair_plan_2026.py), [run_unresolved_appearance_team_repair_2026.py](../../backend/scripts/run_unresolved_appearance_team_repair_2026.py) |
| sync | [check_scheduled_sync_health.py](../../backend/scripts/check_scheduled_sync_health.py), [run_daily_sync.py](../../backend/scripts/run_daily_sync.py), [run_due_sync.py](../../backend/scripts/run_due_sync.py), [sync_trace.py](../../backend/scripts/sync_trace.py) |

## Source adapter methods

These are the callable acquisition methods of the current MLB client. Local wrappers can compose multiple endpoints. Each link shows request parameters and normalization; calling a method does not establish historical retention.

| Method | Request construction | Direct backend callers (static method references) |
|---|---|---|
| `get_all_teams(sport_id)` | [mlb_api.py](../../backend/services/mlb_api.py#L516) | [bullpen.py](../../backend/api/bullpen.py), [seed.py](../../backend/seed.py), [intraday_identity_repair.py](../../backend/services/intraday_identity_repair.py), [intraday_reconcile.py](../../backend/services/intraday_reconcile.py), [official_pitching_line_repair_plan_2026.py](../../backend/services/official_pitching_line_repair_plan_2026.py), [roster_evidence.py](../../backend/services/roster_evidence.py) |
| `get_team_metadata(season)` | [mlb_api.py](../../backend/services/mlb_api.py#L523) | No direct call found |
| `get_team_roster(team_id, roster_type, season, date, hydrate)` | [mlb_api.py](../../backend/services/mlb_api.py#L543) | [seed.py](../../backend/seed.py), [roster_evidence.py](../../backend/services/roster_evidence.py) |
| `get_pitcher_game_logs(player_id, season)` | [mlb_api.py](../../backend/services/mlb_api.py#L576) | [bullpen.py](../../backend/api/bullpen.py), [inspect_gamelog_field_authority.py](../../backend/scripts/inspect_gamelog_field_authority.py), [plan_boxscore_balls_fallback_impact.py](../../backend/scripts/plan_boxscore_balls_fallback_impact.py), [profile_daily_ingestion_readonly.py](../../backend/scripts/profile_daily_ingestion_readonly.py), [seed.py](../../backend/seed.py), [games_started_backfill.py](../../backend/services/games_started_backfill.py), [pitcher_game_log_backfill.py](../../backend/services/pitcher_game_log_backfill.py), [sync.py](../../backend/services/sync.py) |
| `get_player_info(player_id)` | [mlb_api.py](../../backend/services/mlb_api.py#L593) | [run_cu01p_proof.py](../../backend/scripts/run_cu01p_proof.py), [seed.py](../../backend/seed.py), [intraday_identity_repair.py](../../backend/services/intraday_identity_repair.py), [intraday_reconcile.py](../../backend/services/intraday_reconcile.py), [official_pitching_line_repair_plan_2026.py](../../backend/services/official_pitching_line_repair_plan_2026.py), [team_assignment_sync.py](../../backend/services/team_assignment_sync.py) |
| `get_people_info(player_ids)` | [mlb_api.py](../../backend/services/mlb_api.py#L601) | [transaction_participant_qualification.py](../../backend/services/transaction_participant_qualification.py) |
| `get_pitching_stats(player_id, season, stat_type)` | [mlb_api.py](../../backend/services/mlb_api.py#L614) | No direct call found |
| `get_schedule(start_date, end_date, team_id)` | [mlb_api.py](../../backend/services/mlb_api.py#L635) | [run_cu01p_proof.py](../../backend/scripts/run_cu01p_proof.py), [run_postgame_publication_incident_audit.py](../../backend/scripts/run_postgame_publication_incident_audit.py), [completed_game_context_backfill.py](../../backend/services/completed_game_context_backfill.py), [game_change_detection.py](../../backend/services/game_change_detection.py), [intraday_completed_game_repair.py](../../backend/services/intraday_completed_game_repair.py), [intraday_reconcile.py](../../backend/services/intraday_reconcile.py), [intraday_schedule_repair.py](../../backend/services/intraday_schedule_repair.py), [mlb_api.py](../../backend/services/mlb_api.py), [official_pitching_line_completeness_2026.py](../../backend/services/official_pitching_line_completeness_2026.py), [official_pitching_line_repair_plan_2026.py](../../backend/services/official_pitching_line_repair_plan_2026.py), [opening_week_schedule_authority_repair_2026.py](../../backend/services/opening_week_schedule_authority_repair_2026.py), [production_accuracy_reconciliation.py](../../backend/services/production_accuracy_reconciliation.py), [publication_reconciliation.py](../../backend/services/publication_reconciliation.py), [schedule_ingestion.py](../../backend/services/schedule_ingestion.py), [season_bullpen_aggregation_2026.py](../../backend/services/season_bullpen_aggregation_2026.py), [sync.py](../../backend/services/sync.py) |
| `get_recent_schedule(days_back)` | [mlb_api.py](../../backend/services/mlb_api.py#L657) | No direct call found |
| `get_transactions(start_date, end_date, team_id, player_id)` | [mlb_api.py](../../backend/services/mlb_api.py#L663) | [intraday_reconcile.py](../../backend/services/intraday_reconcile.py), [transaction_ingestion.py](../../backend/services/transaction_ingestion.py) |
| `get_game_boxscore(game_pk)` | [mlb_api.py](../../backend/services/mlb_api.py#L700) | [appearance_ledger_audit.py](../../backend/scripts/appearance_ledger_audit.py), [inspect_gamelog_field_authority.py](../../backend/scripts/inspect_gamelog_field_authority.py), [run_cu01p_proof.py](../../backend/scripts/run_cu01p_proof.py), [run_postgame_publication_incident_audit.py](../../backend/scripts/run_postgame_publication_incident_audit.py), [sync_trace.py](../../backend/scripts/sync_trace.py), [appearance_team_backfill_2026.py](../../backend/services/appearance_team_backfill_2026.py), [completed_game_context_backfill.py](../../backend/services/completed_game_context_backfill.py), [game_driven_ingestion.py](../../backend/services/game_driven_ingestion.py), [mlb_api.py](../../backend/services/mlb_api.py), [official_pitching_line_completeness_2026.py](../../backend/services/official_pitching_line_completeness_2026.py), [official_pitching_line_repair_plan_2026.py](../../backend/services/official_pitching_line_repair_plan_2026.py), [official_pitching_line_transition_diagnostic_2026.py](../../backend/services/official_pitching_line_transition_diagnostic_2026.py), [phantom_game_log_reconciliation.py](../../backend/services/phantom_game_log_reconciliation.py), [season_bullpen_aggregation_2026.py](../../backend/services/season_bullpen_aggregation_2026.py), [sync.py](../../backend/services/sync.py), [unresolved_appearance_team_diagnostic_2026.py](../../backend/services/unresolved_appearance_team_diagnostic_2026.py), [unresolved_appearance_team_repair_2026.py](../../backend/services/unresolved_appearance_team_repair_2026.py) |
| `get_game_linescore(game_pk)` | [mlb_api.py](../../backend/services/mlb_api.py#L705) | [run_cu01p_proof.py](../../backend/scripts/run_cu01p_proof.py), [sync.py](../../backend/services/sync.py) |
| `get_game_play_by_play(game_pk)` | [mlb_api.py](../../backend/services/mlb_api.py#L714) | [run_cu01p_proof.py](../../backend/scripts/run_cu01p_proof.py), [game_driven_ingestion.py](../../backend/services/game_driven_ingestion.py), [sync.py](../../backend/services/sync.py) |
| `get_game_live_feed(game_pk)` | [mlb_api.py](../../backend/services/mlb_api.py#L724) | [game_change_detection.py](../../backend/services/game_change_detection.py) |
| `get_game_pitching_lines(game_pk)` | [mlb_api.py](../../backend/services/mlb_api.py#L733) | [plan_boxscore_balls_fallback_impact.py](../../backend/scripts/plan_boxscore_balls_fallback_impact.py), [production_accuracy_reconciliation.py](../../backend/services/production_accuracy_reconciliation.py), [sync.py](../../backend/services/sync.py) |
| `get_minor_league_teams()` | [mlb_api.py](../../backend/services/mlb_api.py#L763) | No direct call found |
| `get_prospect_stats(player_id, season)` | [mlb_api.py](../../backend/services/mlb_api.py#L770) | No direct call found |
| `search_player(name)` | [mlb_api.py](../../backend/services/mlb_api.py#L786) | No direct call found |

## Rehearsal and limits of verification

From `backend/`, on a dedicated loopback PostgreSQL 17.6 UTF-8 database named `np00_utf8_rehearsal_test`, with `APP_ENV=test`, `AUTO_SYNC=false` and `TEST_DATABASE_URL` set to that database:

```sh
python -m pytest -q tests/test_scheduled_sync_health.py tests/test_fenced_writer_contracts.py tests/test_mlb_roster_authority_universe.py tests/test_trusted_publication_rehearsal.py
```

**56 passed.** An initial default-SQLite invocation failed the rehearsal's PostgreSQL precondition. An initial local PostgreSQL database created as SQL_ASCII failed four Tonight checks when decoding Unicode in snapshot JSON. Creating the UTF-8 test database resolved all four without changing application code or tests. These tests exercise existing behavior in isolation. They do not certify any replacement or recreate a naturally played production slate.

The workflow and physical-table indexes reconcile to the checked-out YAML and live table catalog respectively. The inventory maps intelligence by owner and calculation family; the full field-by-field source, coverage and retention registry is the deliverable of NP-01. Dynamic SQL, imported helpers and out-of-band callers cannot be identified exhaustively from ORM declarations or literal call sites. The coverage gate remains open until production owners confirm the writer inventory.

## Physical table and guard inventory

All public base/partitioned tables returned by the production catalog. Links identify the model declaration on main or, where absent, the deployed historical commit. The final column lists distinct enabled non-internal trigger functions on each relation. Blank trigger coverage conveys no permission to write. Inspection includes application side tables to make the isolation boundary explicit.

| Relation | Model / schema owner | Production trigger routines (O = enabled) |
|---|---|---|
| `alembic_version` | [migration_authority.py](../../backend/services/migration_authority.py) | — |
| `atomic_publication_artifacts` | [atomic_publication.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/atomic_publication.py) | baseballos_guard_selector_generation (O) |
| `atomic_publication_cache_handoffs` | [atomic_publication.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/atomic_publication.py) | — |
| `atomic_publication_current` | [atomic_publication.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/atomic_publication.py) | baseballos_guard_selector_generation (O) |
| `atomic_publications` | [atomic_publication.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/atomic_publication.py) | baseballos_guard_selector_generation (O) |
| `audience_subscribers` | [audience_subscriber.py](../../backend/models/audience_subscriber.py) | — |
| `availability_backtest_results` | [availability_backtest_result.py](../../backend/models/availability_backtest_result.py) | — |
| `baseball_date_closure_blockers` | [daily_closure.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/daily_closure.py) | — |
| `baseball_date_closure_versions` | [daily_closure.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/daily_closure.py) | — |
| `baseball_date_closures` | [daily_closure.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/daily_closure.py) | — |
| `canonical_impact_plan_entities` | [canonical_impact.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/canonical_impact.py) | — |
| `canonical_impact_plan_mutations` | [canonical_impact.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/canonical_impact.py) | — |
| `canonical_impact_plans` | [canonical_impact.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/canonical_impact.py) | — |
| `compatibility_write_events` | [compatibility_write_event.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/compatibility_write_event.py) | — |
| `completed_game_contexts` | [completed_game_context.py](../../backend/models/completed_game_context.py) | — |
| `composed_read_components` | [composed_read.py](../../backend/models/composed_read.py) | — |
| `composed_read_evidence_citations` | [composed_read.py](../../backend/models/composed_read.py) | — |
| `composed_reads` | [composed_read.py](../../backend/models/composed_read.py) | — |
| `dashboard_snapshots` | [dashboard_snapshot.py](../../backend/models/dashboard_snapshot.py) | baseballos_guard_selector_generation (O) |
| `derived_cohort_inputs` | [derived_intelligence.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/derived_intelligence.py) | — |
| `derived_cohort_snapshots` | [derived_intelligence.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/derived_intelligence.py) | baseballos_guard_selector_generation (O) |
| `derived_intelligence_cohort_domains` | [derived_intelligence.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/derived_intelligence.py) | — |
| `derived_intelligence_cohorts` | [derived_intelligence.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/derived_intelligence.py) | baseballos_guard_selector_generation (O) |
| `editorial_post_history` | [editorial_post_history.py](../../backend/models/editorial_post_history.py) | — |
| `evidence_citations` | [evidence_contract.py](../../backend/models/evidence_contract.py) | — |
| `evidence_objects` | [evidence_contract.py](../../backend/models/evidence_contract.py) | — |
| `fatigue_scores` | [fatigue_score.py](../../backend/models/fatigue_score.py) | — |
| `final_game_mutations` | [final_game_reconciliation.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/final_game_reconciliation.py) | — |
| `final_game_versions` | [final_game_reconciliation.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/final_game_reconciliation.py) | baseballos_guard_canonical_selector (O) |
| `final_pitching_appearance_versions` | [final_game_reconciliation.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/final_game_reconciliation.py) | baseballos_guard_canonical_selector (O) |
| `game_ingestion_work_items` | [game_ingestion_work_item.py](../../backend/models/game_ingestion_work_item.py) | — |
| `game_logs` | [game_log.py](../../backend/models/game_log.py) | baseballos_guard_final_compatibility (O) |
| `game_observation_states` | [game_observation_state.py](../../backend/models/game_observation_state.py) | baseballos_guard_game_observation (O) |
| `game_pitch_events` | [play_by_play_foundation.py](../../backend/models/play_by_play_foundation.py) | baseballos_guard_final_compatibility (O) |
| `game_play_by_play_events` | [play_by_play_foundation.py](../../backend/models/play_by_play_foundation.py) | baseballos_guard_final_compatibility (O) |
| `game_pregame_context_versions` | [pregame_context.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/pregame_context.py) | baseballos_guard_canonical_selector (O) |
| `intelligence_surface_snapshots` | [intelligence_surface_snapshot.py](../../backend/models/intelligence_surface_snapshot.py) | — |
| `legacy_read_audit_runs` | [legacy_read_audit.py](../../backend/models/legacy_read_audit.py) | — |
| `legacy_read_divergences` | [legacy_read_audit.py](../../backend/models/legacy_read_audit.py) | — |
| `live_game_mutations` | [live_game_delta.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/live_game_delta.py) | — |
| `official_pitching_line_repair_executions` | [official_pitching_line_repair_execution.py](../../backend/models/official_pitching_line_repair_execution.py) | — |
| `pitcher_season_ledger_coverage` | [pitcher_season_ledger_coverage.py](../../backend/models/pitcher_season_ledger_coverage.py) | — |
| `pitchers` | [pitcher.py](../../backend/models/pitcher.py) | baseballos_guard_pitcher_projection (O) |
| `play_by_play_processed_games` | [play_by_play_foundation.py](../../backend/models/play_by_play_foundation.py) | baseballos_guard_final_compatibility (O) |
| `player_transaction_sync_windows` | [player_transaction.py](../../backend/models/player_transaction.py) | — |
| `player_transaction_versions` | [roster_membership.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/roster_membership.py) | — |
| `player_transactions` | [player_transaction.py](../../backend/models/player_transaction.py) | baseballos_guard_transaction_projection (O) |
| `postgame_processed_games` | [postgame_processed_game.py](../../backend/models/postgame_processed_game.py) | baseballos_guard_final_compatibility (O) |
| `pregame_context_mutations` | [pregame_context.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/pregame_context.py) | — |
| `prospects` | [prospect.py](../../backend/models/prospect.py) | — |
| `provisional_pitching_appearance_states` | [live_game_delta.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/live_game_delta.py) | baseballos_guard_canonical_selector (O) |
| `repair_request_blockers` | [repair_request.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/repair_request.py) | — |
| `repair_request_chunks` | [repair_request.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/repair_request.py) | — |
| `repair_requests` | [repair_request.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/repair_request.py) | — |
| `roster_membership_intervals` | [roster_membership.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/roster_membership.py) | baseballos_guard_canonical_selector (O) |
| `roster_membership_mutations` | [roster_membership.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/roster_membership.py) | — |
| `roster_status_snapshots` | [roster_status_snapshot.py](../../backend/models/roster_status_snapshot.py) | baseballos_guard_roster_snapshot (O) |
| `scheduled_games` | [scheduled_game.py](../../backend/models/scheduled_game.py) | baseballos_guard_schedule_projection (O) |
| `share_artifact_assets` | [share_artifact.py](../../backend/models/share_artifact.py) | — |
| `share_artifact_evidence` | [share_artifact.py](../../backend/models/share_artifact.py) | — |
| `share_artifact_generation_audits` | [share_artifact_generation_audit.py](../../backend/models/share_artifact_generation_audit.py) | — |
| `share_artifact_relations` | [share_artifact.py](../../backend/models/share_artifact.py) | — |
| `share_artifacts` | [share_artifact.py](../../backend/models/share_artifact.py) | baseballos_guard_selector_generation (O) |
| `slate_games` | [slate_game.py](../../backend/models/slate_game.py) | baseballos_guard_schedule_projection (O) |
| `source_fetch_attempts` | [source_observation.py](../../backend/models/source_observation.py) | — |
| `source_observations` | [source_observation.py](../../backend/models/source_observation.py) | — |
| `source_payload_artifacts` | [source_observation.py](../../backend/models/source_observation.py) | — |
| `source_subjects` | [source_observation.py](../../backend/models/source_observation.py) | — |
| `sync_certification_checks` | [sync_certification.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/sync_certification.py) | — |
| `sync_certification_runs` | [sync_certification.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/sync_certification.py) | — |
| `sync_failures` | [sync_failure.py](../../backend/models/sync_failure.py) | — |
| `sync_job_attempts` | [sync_job.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/sync_job.py) | — |
| `sync_jobs` | [sync_job.py](../../backend/models/sync_job.py) | — |
| `sync_legacy_transition_states` | [sync_certification.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/sync_certification.py) | — |
| `sync_run_scopes` | [sync_run.py](https://github.com/NickolisK24/bullpen-intel-engine/blob/617ab650febc1b6a8567fba264150353b2f4b3c4/backend/models/sync_run.py) | — |
| `sync_runs` | [sync_run.py](../../backend/models/sync_run.py) | — |
| `sync_schedule_attempts` | [sync_schedule_attempt.py](../../backend/models/sync_schedule_attempt.py) | — |
| `team_game_pitching_splits` | [team_game_pitching_split.py](../../backend/models/team_game_pitching_split.py) | — |
| `team_progressive_publications` | [team_progressive_publication.py](../../backend/models/team_progressive_publication.py) | — |
| `team_public_current_pointers` | [team_publication.py](../../backend/models/team_publication.py) | — |
| `team_public_publications` | [team_publication.py](../../backend/models/team_publication.py) | — |
| `team_state_publication_proofs` | [team_state_publication_proof.py](../../backend/models/team_state_publication_proof.py) | — |
| `tonight_intelligence_snapshots` | [tonight_intelligence_snapshot.py](../../backend/models/tonight_intelligence_snapshot.py) | — |
| `tonight_publications` | [tonight_publication.py](../../backend/models/tonight_publication.py) | — |
| `traffic_internal_visitors` | [traffic_internal_visitor.py](../../backend/models/traffic_internal_visitor.py) | — |
| `traffic_page_views` | [traffic_page_view.py](../../backend/models/traffic_page_view.py) | — |
| `traffic_share_actions` | [traffic_share_action.py](../../backend/models/traffic_share_action.py) | — |
| `user_followed_teams` | [user.py](../../backend/models/user.py) | — |
| `users` | [user.py](../../backend/models/user.py) | — |

## API contract index

Each row links the actual Flask handler module and lists its decorated handlers, including protected and non-baseball routes. Routes installed or wrapped by the app factory and public serving authority must also be exercised by parity clients. Browser aliases and request contracts live in [App.jsx](../../frontend/src/App.jsx) and [api.js](../../frontend/src/utils/api.js).

| Module | Route handlers |
|---|---|
| [audience.py](../../backend/api/audience.py) | `signup` |
| [auth.py](../../backend/api/auth.py) | `get_me`, `request_link`, `verify`, `logout` |
| [bullpen.py](../../backend/api/bullpen.py) | `get_reliever_finder`, `get_fatigue_scores`, `get_latest_workload_snapshot`, `get_pitcher_publication_history`, `get_pitcher_fatigue`, `recalculate_fatigue`, `sync_recent_logs`, `get_sync_status`, `get_pitchers`, `get_pitcher_logs`, `get_teams`, `get_team_bullpen`, `get_team_bullpen_board`, `get_team_changes`, `get_team_story`, `get_today_lead_story`, `get_tonight_intelligence`, `compare_team_bullpens`, `get_scheduled_game_matchup`, `get_narrative_memory_diagnostic`, `get_bullpen_context_diagnostic`, `get_role_authority_diagnostic`, `get_stats_overview`, `build_dashboard_snapshot_endpoint`, `get_bullpen_dashboard`, `get_public_home_projection`, `get_public_league_projection`, `get_public_stories_projection`, `get_public_trust_projection`, `get_league_team_states`, `get_bullpen_landscape`, `get_team_game_context`, `get_fatigue_era_insight`, `get_mlb_teams`, `get_mlb_pitcher_logs` |
| [explanations.py](../../backend/api/explanations.py) | `get_availability_explanation`, `get_team_readiness_explanation`, `get_team_readiness_explanation_for_scope`, `reject_uncertified_explanation_type` |
| [me.py](../../backend/api/me.py) | `list_followed_teams`, `follow_team`, `unfollow_team`, `set_primary_team` |
| [methodology.py](../../backend/api/methodology.py) | `get_availability_backtest`, `get_methodology` |
| [observations.py](../../backend/api/observations.py) | `get_observations`, `preview_observations` |
| [performance_intelligence_admin.py](../../backend/api/performance_intelligence_admin.py) | `get_active_bullpen_era` |
| [pitchers.py](../../backend/api/pitchers.py) | `search_pitchers` |
| [private_posts.py](../../backend/api/private_posts.py) | `get_private_posts_dashboard` |
| [prospects.py](../../backend/api/prospects.py) | `get_prospects`, `get_prospect`, `get_by_team`, `get_pipeline`, `compare_prospects`, `pipeline_overview` |
| [recent_work.py](../../backend/api/recent_work.py) | `pitcher_recent_work` |
| [recommendations.py](../../backend/api/recommendations.py) | `evaluate_candidate_recommendation`, `get_v2_bullpen_state` |
| [search.py](../../backend/api/search.py) | `search_entities` |
| [share_artifact_operations_browser.py](../../backend/api/share_artifact_operations_browser.py) | `operations_overview`, `operations_artifacts`, `operations_audits` |
| [share_artifacts_admin.py](../../backend/api/share_artifacts_admin.py) | `generate_team_state`, `generate_team_state_batch`, `operations_overview`, `operations_artifacts`, `operations_audits` |
| [share_artifacts_public.py](../../backend/api/share_artifacts_public.py) | `get_public_share_artifact` |
| [share_cards.py](../../backend/api/share_cards.py) | `get_team_state_share_card`, `get_since_yesterday_share_artifact` |
| [slate_briefing.py](../../backend/api/slate_briefing.py) | `get_slate_briefing`, `post_slate_briefing_receipt`, `get_slate_briefing_history` |
| [system.py](../../backend/api/system.py) | `get_email_delivery_health`, `get_pipeline_health`, `get_internal_team_evidence`, `get_internal_snapshot_audit`, `get_internal_pitcher_evidence` |
| [team_board_v2.py](../../backend/api/team_board_v2.py) | `get_team_board_core`, `get_team_board_details`, `get_team_board_v2` |
| [team_history.py](../../backend/api/team_history.py) | `get_team_state_history`, `get_team_history_pitcher` |
| [team_operations.py](../../backend/api/team_operations.py) | `get_team_operations_bullpen_readiness` |
| [team_recent_work.py](../../backend/api/team_recent_work.py) | `team_relief_work` |
| [traffic.py](../../backend/api/traffic.py) | `internal_summary`, `page_view`, `share_action` |
| [app.py](../../backend/app.py) | `health` |
