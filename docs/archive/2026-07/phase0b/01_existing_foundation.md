# Phase 0B-02 - Existing Foundation Inventory

Status: `AUDIT-ONLY-0B`

Categories covered:

- Category 1: Existing BaseballOS data foundation
- Category 19: Data correction and provenance

This inventory documents what BaseballOS already stores, derives, publishes,
and withholds before Phase 0B audits new source candidates. It does not approve
new ingestion, schema changes, source adoption, probes, API behavior, UI
behavior, public claims, or product work.

## Scope Guardrails

- This branch is documentation only.
- Existing runtime behavior is described, not modified.
- Existing public language is mapped to evidence and gaps, not newly approved.
- Public display posture remains `INTERNAL-ONLY` unless a later Phase 0B
  decision explicitly advances it.
- Legal posture remains `needs-legal-review` where the repo does not cite
  source terms, attribution, storage, or redistribution permission.
- New candidate sources are out of scope for this branch.

## Evidence Method

Evidence links cite current repository files by path and line range where the
path was inspected with line numbers. Longer services are cited by symbol when
that is clearer than repeating large line ranges.

## 1. Executive Baseline

BaseballOS already has a substantial stored bullpen foundation:

- Pitcher identity, team assignment, roster status, and active-state fields.
- Stored pitching game logs with nullable pitch-count handling.
- Stored workload/fatigue component scores.
- Durable sync-run state, sync-failure dead letters, and write exclusion.
- Completed-game processing markers with retry and failure lifecycle.
- Scheduled-game records and completed-game context records.
- Published dashboard snapshots and intelligence-surface snapshots.
- Slate coverage and freshness metadata used to fail closed.
- Public copy guards for availability, freshness, and change-read claims.

The strongest Phase 0A foundation areas are final-game gating, unknown-safe
pitch counts, stat correction propagation, postgame marker lifecycle, slate
coverage, durable sync metadata, and published snapshot authority. The main
Phase 0B risks are legal posture, public wording that can overclaim, public
score/framing leakage, and source-specific correction/finality details that
still need later audits.

## 2. Current Stored Data Models

| area | stored evidence | current use | evidence |
| --- | --- | --- | --- |
| Pitcher identity and assignment | `pitchers` stores MLB id, name, team assignment, team source/update time, roster status/source/raw fields, handedness, active state, and timestamps. | Foundation for bullpen boards, workload joins, roster availability, and public pitcher labels. | `backend/models/pitcher.py:4-34`; `backend/services/team_assignment_sync.py:314-346`; `backend/services/roster_status_sync.py:273-337` |
| Pitching game logs | `game_logs` stores game identity, team/opponent/date, bullpen/starter fields, innings/outs, nullable pitches/strikes, run prevention stats, leverage proxies, inherited/save/hold/outcome fields, and correction provenance. | Foundation for workload windows, availability classification, What Changed comparisons, and completed-game context. | `backend/models/game_log.py:4-71`; `backend/services/sync.py:920-980` |
| Nullable pitch counts | `game_logs.pitches_thrown` is nullable, preserving missing pitch counts as unknown rather than zero. | Prevents false workload certainty and excludes unknown pitch-count teams from concentration calculations. | `backend/migrations/versions/e3b7a9c4d2f6_preserve_unknown_pitch_counts.py:1-24`; `backend/tests/test_unknown_safe_ingestion.py:68-121`; `backend/tests/test_workload_concentration.py:59-99` |
| Fatigue/workload scores | `fatigue_scores` stores raw score, component scores, workload windows, and risk level. | Internal scoring and availability classification foundation. Public Phase 0B posture remains internal because public fatigue-score framing is disallowed. | `backend/models/fatigue_score.py:4-33`; `backend/services/availability.py:176-328`; `backend/services/availability_snapshot.py:52-120` |
| Postgame processing markers | `postgame_processed_games` stores game identity, final-state marker data, logs added, pitchers touched, sync run, processing status, attempts, incomplete reasons, correction failures, and lifecycle timestamps. | Prevents duplicate processing, supports retry, and makes incomplete/failed final-game processing visible. | `backend/models/postgame_processed_game.py:5-42`; `backend/services/sync.py:963-1085`; `backend/tests/test_postgame_marker_lifecycle.py:266-443` |
| Sync runs | `sync_runs` stores job/status/stage/source, run dates, latest data dates, counts, API request counts, failure details, and published dashboard snapshot id. | Durable authority for sync status, freshness, pipeline health, and cache publication. | `backend/models/sync_run.py:5-46`; `backend/services/sync_metadata.py:22-57`; `backend/services/sync_metadata.py:396-549` |
| Sync failures | `sync_failures` stores job/entity reference, payload, error, resolution state, and sync run link. | Dead-letter trail for rejected corrections, marker failures, and refresh errors. | `backend/models/sync_failure.py:5-40`; `backend/migrations/versions/d8f1a2b6c40e_add_sync_failures.py:3-38`; `backend/services/sync.py:400-429` |
| Scheduled games | `scheduled_games` stores team/game/date, opponent, home/away, raw status code, normalized status state, doubleheader metadata, source, and timestamps. | Tonight board and schedule context foundation. | `backend/models/scheduled_game.py:5-68`; `backend/services/schedule_ingestion.py:1-163`; `backend/scripts/run_tonight_refresh.py:75-113` |
| Completed game context | `completed_game_contexts` stores team/game/date, final scores, starter, bullpen entry and margin, late runs, protected/lost/comeback flags, game shape, story tag, confidence, and generated time. | Contextual story and team-game read foundation, with fail-closed extraction when identity or boxscore evidence is insufficient. | `backend/models/completed_game_context.py:5-83`; `backend/services/completed_game_context_service.py:195-512`; `backend/services/completed_game_context_payload_adapter.py:1-181` |
| Dashboard snapshots | `dashboard_snapshots` stores snapshot type, sync run, status, published flag/time, payload JSON, payload version, data-through date, availability reference date, generated time, source, and error message. | Published cache authority for `/api/bullpen/dashboard`, prior snapshot comparison, and data provenance display. | `backend/models/dashboard_snapshot.py:5-33`; `backend/migrations/versions/f4c2b8a9d1e3_add_dashboard_snapshots.py:20-46`; `backend/api/bullpen.py:2373-2864` |
| Intelligence snapshots | `intelligence_surface_snapshots` and `tonight_intelligence_snapshots` store dated response JSON, status, card/story counts, metadata, source, and generated time. | Cache-backed public surfaces with bounded fallback and fail-closed empty responses. | `backend/models/intelligence_surface_snapshot.py:5-52`; `backend/models/tonight_intelligence_snapshot.py:5-50`; `backend/services/intelligence_surface_snapshot.py:87-308`; `backend/services/tonight_intelligence_snapshot.py:51-261` |

## 3. Phase 0A-Relevant Migrations

| migration | foundation added | evidence |
| --- | --- | --- |
| `e3b7a9c4d2f6_preserve_unknown_pitch_counts` | Makes `game_logs.pitches_thrown` nullable without a default so missing pitch counts remain unknown. | `backend/migrations/versions/e3b7a9c4d2f6_preserve_unknown_pitch_counts.py:1-24` |
| `f6a2c9d8e1b3_add_game_log_correction_provenance` | Adds game-log stat correction count, last correction time, source, and sync run id. | `backend/migrations/versions/f6a2c9d8e1b3_add_game_log_correction_provenance.py:1-39` |
| `c2f6a9d8e4b1_add_postgame_marker_lifecycle` | Adds postgame marker processing status, attempt count, attempt/failure timestamps, incomplete reason, pitching-line counts, and correction failure counts. | `backend/migrations/versions/c2f6a9d8e4b1_add_postgame_marker_lifecycle.py:19-92` |
| `f2a9c7d1e8b5_publish_consistent_sync_snapshots` | Adds published dashboard snapshot flags, sync-run stages, failed stage, and published snapshot id. | `backend/migrations/versions/f2a9c7d1e8b5_publish_consistent_sync_snapshots.py:19-49` |
| `f4c2b8a9d1e3_add_dashboard_snapshots` | Creates dashboard snapshot storage with payload, version, data-through, availability reference, source, and error fields. | `backend/migrations/versions/f4c2b8a9d1e3_add_dashboard_snapshots.py:20-46` |
| `41f4f9a8d6c2_add_sync_runs` | Creates durable sync-run status, date, count, and error storage. | `backend/migrations/versions/41f4f9a8d6c2_add_sync_runs.py:20-35` |
| `d8f1a2b6c40e_add_sync_failures` | Creates dead-letter storage for unresolved source or processing failures. | `backend/migrations/versions/d8f1a2b6c40e_add_sync_failures.py:3-38` |
| `c5b1e9a2f7d4_add_scheduled_games` | Creates scheduled-game storage and indexes. | `backend/migrations/versions/c5b1e9a2f7d4_add_scheduled_games.py:20-48` |
| `b9e4c1f7a2d6_add_completed_game_contexts` | Creates completed-game context storage. | `backend/migrations/versions/b9e4c1f7a2d6_add_completed_game_contexts.py:19-56` |
| `a7f2c1d4e9b6_add_intelligence_surface_snapshots` | Creates stored intelligence-surface snapshots. | `backend/migrations/versions/a7f2c1d4e9b6_add_intelligence_surface_snapshots.py:20-35` |
| `d4a8c2e6b1f9_add_tonight_intelligence_snapshots` | Creates stored Tonight intelligence snapshots. | `backend/migrations/versions/d4a8c2e6b1f9_add_tonight_intelligence_snapshots.py:20-31` |

## 4. Sync Sources And Cadence

| path | current behavior | evidence |
| --- | --- | --- |
| Local scheduler | Starts only when `AUTO_SYNC=true`; local default path can leave it disabled. Cron trigger runs at 6:00 ET with coalescing and single-instance guard. | `backend/app.py:20-29`; `backend/app.py:58-68` |
| GitHub workflow daily sync | Scheduled daily at `0 10 * * *`, runs `run_daily_sync.py --days-back 7 --source github_actions`, then warms schedule/Tonight context and verifies dashboard cache. | `.github/workflows/baseballos-sync.yml:20-27`; `.github/workflows/baseballos-sync.yml:72-134`; `.github/workflows/baseballos-sync.yml:136-217` |
| GitHub workflow postgame refresh | Scheduled at `0 2,4,6 * * *`, runs `run_postgame_refresh.py --source github_actions`, then warms Tonight context and verifies dashboard cache. | `.github/workflows/baseballos-sync.yml:20-27`; `.github/workflows/baseballos-sync.yml:104-134`; `backend/scripts/run_postgame_refresh.py:21-68` |
| Manual dispatch | Workflow supports manual `daily` or `postgame` mode. | `.github/workflows/baseballos-sync.yml:29-38` |
| Writer exclusion | Sync workflow uses a workflow concurrency group; runtime sync code also uses durable/advisory/process-lock guards. | `.github/workflows/baseballos-sync.yml:40-42`; `backend/services/sync_metadata.py:151-283`; `backend/api/bullpen.py:152-166` |
| Daily sync script | Disables auto scheduler in-process, accepts source argument, calls `sync_service.run_daily_sync`, and exits nonzero unless status is successful. | `backend/scripts/run_daily_sync.py:13-61` |
| Postgame script | Disables auto scheduler in-process, accepts date/source arguments, calls `sync_service.run_postgame_refresh`, and exits nonzero unless status is successful. | `backend/scripts/run_postgame_refresh.py:14-68` |
| Tonight script | Disables auto scheduler in-process, ingests schedule context, warms Tonight snapshot, and treats schedule errors as partial rather than hiding them. | `backend/scripts/run_tonight_refresh.py:14-113` |

Current source posture:

- Existing game, roster, and schedule evidence appears sourced through current
  MLB Stats API paths already used by the application, but this branch does not
  perform a legal or source-contract review.
- Existing derived data is useful for Phase 0B inventory only until source
  authority, legal posture, public-display posture, and fail-closed behavior are
  decided in later Phase 0B branches.

## 5. Publish And Snapshot Metadata

| mechanism | current behavior | evidence |
| --- | --- | --- |
| Published dashboard snapshot | A dashboard snapshot can be marked published and linked from `sync_runs.published_dashboard_snapshot_id`. Published snapshots become the current dashboard authority when valid enough. | `backend/models/dashboard_snapshot.py:20-33`; `backend/models/sync_run.py:26`; `backend/api/bullpen.py:210-223`; `backend/api/bullpen.py:2634-2864` |
| Snapshot validity gate | Dashboard serving prefers a latest valid published snapshot; unavailable reasons are surfaced rather than silently claiming current data. | `backend/services/dashboard_snapshot.py:get_latest_valid_dashboard_snapshot`; `backend/services/dashboard_snapshot.py:latest_dashboard_snapshot_unavailable_reason`; `backend/api/bullpen.py:2845-2864` |
| Freshness overlay | Board freshness combines durable sync metadata with published snapshot metadata and marks previous-published-view states when a later sync is running or failed. | `backend/services/board_freshness.py:24-167` |
| Slate coverage | Slate coverage appends complete-enough-to-publish metadata and degrades freshness when final-game coverage is incomplete. | `backend/services/slate_coverage.py:509-544`; `backend/tests/test_slate_coverage.py:76-166` |
| What Changed baseline | What Changed compares against trusted published snapshots only and withholds reads when snapshots are missing, partial, stale, or incomparable. | `backend/services/what_changed_since_yesterday.py:54-80`; `backend/services/what_changed_since_yesterday.py:249-309`; `backend/services/what_changed_since_yesterday.py:898-945` |
| Intelligence surface snapshots | Intelligence snapshots are read from cache or generated on demand; errors return fail-closed empty responses, and snapshot metadata is stripped or normalized for public payloads. | `backend/services/intelligence_surface_snapshot.py:73-308` |
| Tonight snapshots | Tonight snapshots support cache hit/miss, bounded live fallback, empty-state caching, and no write on error payloads. | `backend/services/tonight_intelligence_snapshot.py:38-261`; `backend/tests/test_tonight_intelligence_snapshot.py:87-334` |

## 6. Unknown, Stale, And Fail-Closed Handling

| failure case | current fail-closed behavior | evidence |
| --- | --- | --- |
| Non-final games | Non-final/statusless splits are excluded from ingestion and workload evidence. | `backend/services/sync.py:128-156`; `backend/tests/test_unknown_safe_ingestion.py:101-121` |
| Missing pitch count | Missing pitch counts remain `NULL`, downstream workload concentration marks totals unknown, and league comparisons exclude unknown teams. | `backend/tests/test_unknown_safe_ingestion.py:68-89`; `backend/services/workload_concentration.py:64-91`; `backend/services/workload_concentration.py:176-195` |
| Unsafe stat correction | Partial or unsafe correction source payloads are dead-lettered and do not overwrite existing rows. | `backend/services/sync.py:306-318`; `backend/services/sync.py:400-493`; `backend/tests/test_stat_correction_propagation.py:247-375` |
| Incomplete postgame processing | Incomplete final-game processing retries without duplicating logs, then stops at a visible failed marker after repeated attempts. | `backend/services/sync.py:229-244`; `backend/services/sync.py:963-1085`; `backend/tests/test_postgame_marker_lifecycle.py:329-443` |
| Missing or stale sync metadata | Freshness degrades to unavailable or incomplete instead of claiming current data. | `backend/services/sync_metadata.py:287-354`; `backend/services/sync_metadata.py:666-780`; `backend/services/board_freshness.py:75-107` |
| Snapshot unavailable | Dashboard serving returns an unavailable payload when production live fallback is disabled and no valid snapshot is available. | `backend/api/bullpen.py:2634-2698`; `backend/api/bullpen.py:2845-2864` |
| Roster status unknown | Missing roster evidence becomes unknown; team assignment clears stale assignment and marks inactive when authority is missing or ambiguous. | `backend/services/roster_status_sync.py:188-229`; `backend/services/team_assignment_sync.py:343-346` |
| Completed-game context identity missing | Context extraction returns an empty result when required identity evidence is missing, and low-confidence boxscore-only paths fail closed. | `backend/services/completed_game_context_service.py:195-233`; `backend/services/completed_game_context_service.py:392-512` |
| Intelligence read/build failure | Intelligence and Tonight snapshot services return empty fail-closed responses or propagate read failure rather than inventing cards. | `backend/services/intelligence_surface_snapshot.py:87-126`; `backend/services/tonight_intelligence_snapshot.py:51-135`; `backend/tests/test_tonight_intelligence_snapshot.py:187-241` |
| Public copy guard failure | What Changed public copy strips private fields and fails closed when banned public-copy checks trigger. | `backend/services/what_changed_since_yesterday_public.py:140-142`; `backend/services/what_changed_since_yesterday_public.py:318-376`; `backend/services/what_changed_since_yesterday_copy.py:26-39`; `backend/services/what_changed_since_yesterday_copy.py:144-145` |

## 7. Public Claim And Evidence Mapping

This section maps current user-facing claims to their stored evidence and Phase
0B risk. It does not newly approve any claim for future public expansion.

| current surface or claim family | current evidence path | current guardrail | Phase 0B gap |
| --- | --- | --- | --- |
| Data freshness labels such as `Healthy`, `Limited`, `Not Current`, data-through date, sync label, and coverage helper text. | Durable sync metadata, dashboard snapshot metadata, slate coverage, and board freshness view. | Missing/stale/failed states become limited or not current; metadata-unavailable states show limited availability. | The word `Healthy` can overclaim because health wording is disallowed unless injury/IL/depth support is explicit. Rewording decision belongs to a later public-language phase. Evidence: `frontend/src/components/dashboard/syncStatusView.js:50-127`. |
| Bullpen availability buckets such as `Available`, `On Watch`, `Limited`, and `Unavailable`. | `FatigueScore`, `GameLog`, roster status, workload windows, and availability classifiers. | Incomplete/stale data forces at least monitored/limited states; board frontend maps internal `Avoid` to `Unavailable` in key places. | Internal availability status `Avoid` can be action-like if exposed raw through an API or copy path. Evidence: `backend/services/availability.py:33-328`; `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js:28-63`. |
| Pitcher role/read labels such as `Trust Arm`, `Bridge Arm`, `Coverage Arm`, `Depth Arm`, `Limited Read`, `Rested`, `Watch Arm`, `Rest-Restricted`, and `Unavailable`. | Public label service maps workload, role, roster, and availability evidence into label families. | Roster unavailable and limited data paths degrade labels to limited/unavailable reads. | Role labels are not direct manager intent. Later branches should keep them descriptive and evidence-backed. Evidence: `backend/services/pitcher_public_labels.py:13-280`. |
| Team shape and trust labels such as `Healthy Rested Bullpen`, `Limited Late-Inning Availability`, coverage safety, and trust availability labels. | Team shape service, team scoring utility, resource-health classifications, injured-list roster status counts, unknown counts, and stored workload. | Resource-health service records limitations and uses unknown/depleted capacity states when evidence is incomplete. | Current `Healthy` wording needs review under the Phase 0B content trust rules. Evidence: `backend/services/team_bullpen_shape.py:17-109`; `backend/services/bullpen_resource_health.py:30-428`; `frontend/src/utils/teamBullpenScoring.js:10-82`. |
| Data provenance labels such as `No data loaded`, `Last published view`, `Sync in progress`, `Outdated data`, `Current stored data`, and `Sample data`. | Dashboard snapshot metadata, sync status, board freshness, and sample-data flags. | Stale or missing evidence displays provenance rather than current-certainty language. | Good fail-closed pattern; still requires later source/legal review for the underlying data. Evidence: `frontend/src/components/bullpen/board/tonightsBullpenBoardView.js:457-544`. |
| What Changed public reads. | Trusted published dashboard snapshots, comparable baselines, public-copy transforms, and freshness metadata. | Withholds reads when snapshots are not trusted, comparable, finality-safe, or sufficiently complete. | Depends on prior published snapshot consistency; no new source evidence is added by this branch. Evidence: `backend/services/what_changed_since_yesterday.py:54-80`; `backend/services/what_changed_since_yesterday.py:898-945`; `frontend/src/components/dashboard/WhatChangedCard.jsx:103-157`. |
| Team game context notes. | Scheduled games, completed-game contexts, final score, starter/bullpen entry context, and stored game logs. | Missing schedule/context fields render unavailable states; notes state stored-game-log-only and no advice/predictions. | The stored `confidence` field should remain internal unless later public framing is explicitly approved. Evidence: `frontend/src/components/bullpen/board/TeamGameContextCard.jsx:6-85`; `backend/models/completed_game_context.py:33-83`. |
| Pipeline health and sync failure information. | Durable `sync_runs`, `sync_failures`, stage metadata, dead letters, and pipeline health payload. | Admin/status paths surface metadata unavailable states and dead-letter counts. | Treat as internal operational evidence unless a later branch approves a user-facing data-trust surface. Evidence: `backend/services/sync_metadata.py:604-658`; `backend/api/bullpen.py:806-858`. |

## 8. Current Bullpen Question Coverage

| question | existing evidence coverage | Phase 0B posture |
| --- | --- | --- |
| Q1: Which bullpens are fresh tonight? | Partial existing coverage from game logs, workload windows, roster status, scheduled games, board freshness, and snapshots. | `INTERNAL-ONLY`; public phrasing needs legal/source review and no score framing. |
| Q2: Which bullpens are stretched? | Partial existing coverage from workload windows, concentration service, nullable pitch counts, and recent appearance logs. | `INTERNAL-ONLY`; unknown pitch counts must keep reads incomplete. |
| Q3: Which teams have late-game margin? | Partial existing coverage from role labels, trust availability labels, and team shape. | `INTERNAL-ONLY`; avoid manager-intent certainty. |
| Q4: Which teams lack clean options? | Partial existing coverage from team shape, resource health, roster status, and availability group counts. | `INTERNAL-ONLY`; clean/messy appearance detail still needs later source audit. |
| Q5: Which arms are being leaned on too heavily? | Existing coverage from game logs, pitch counts when known, appearance recency, and fatigue/workload components. | `INTERNAL-ONLY`; no public fatigue-score framing. |
| Q6: Which arms are rested but not trusted? | Partial existing coverage from rest/read labels and role buckets. | `INTERNAL-ONLY`; role evidence is inferential. |
| Q7: Which arms are trusted but rest-restricted? | Existing coverage from role labels, recent workload, roster status, and rest-restricted labels. | `INTERNAL-ONLY`; no public score/confidence framing. |
| Q8: Which teams are being pressured by short starts? | Partial existing coverage from completed-game context, starter innings, bullpen entry context, and game logs. | `INTERNAL-ONLY`; starter and bullpen context needs source/finality review. |
| Q9: Which teams are pressured by injuries/IL/depth loss? | Partial existing coverage from roster status, injured-list counts, unavailable counts, and unknown counts. | `INTERNAL-ONLY`; no private injury claims and no unsupported `healthy` wording. |
| Q10: What changed since yesterday? | Strong existing guardrail coverage through trusted published snapshots and comparable baseline gates. | `INTERNAL-ONLY`; public reads remain bounded by trusted snapshot availability. |

## 9. Gap Register

| claim_or_surface | current_evidence | gap | risk | current_fail_closed_behavior | recommended_phase_for_decision | notes |
| --- | --- | --- | --- | --- | --- | --- |
| `Healthy` freshness/team labels | `syncStatusView.js`, `team_bullpen_shape.py`, `teamBullpenScoring.js`, `bullpen_resource_health.py` | Health wording can imply medical or complete-depth certainty beyond displayed evidence. | public overclaim | Degrades to limited/not-current/unknown in stale or incomplete states, but wording remains when evidence passes current guards. | Later public language pass after 0B source decisions | Quote as existing label only; do not expand. |
| Public fatigue/workload score framing | `fatigue_scores`, availability services, board card fields | Internal score tables and fields exist; public Phase 0B rule disallows fatigue-score framing. | score overconfidence | Availability copy often translates score into labels; incomplete/stale data limits reads. | 0B-07 strategy, then later presentation work | Keep raw score concepts internal unless explicitly re-approved. |
| Raw `Avoid` availability status | Availability service and board view mapping | `Avoid` is action-like if exposed outside frontend mapping. | advice language | Frontend bucket copy maps to unavailable in board presentation. | 0B-07 or public language phase | Audit API clients before public expansion. |
| Manager-intent role labels | `pitcher_public_labels.py`, role/trust services | Role labels infer usage patterns; they are not direct manager intent. | unsupported certainty | Labels degrade to limited reads when evidence is stale, incomplete, or roster-unavailable. | 0B-06 / 0B-07 | Keep language descriptive. |
| IL/depth and health context | Roster sync, resource health, team shape | Existing evidence can count public roster/unavailable states but not private injury details or severity. | medical overclaim | Unknown roster evidence becomes unknown; missing assignment clears stale state. | 0B-04 / 0B-07 | Never claim injury-free status from absence of IL evidence. |
| What Changed comparisons | Published dashboard snapshots and trusted comparison gate | Requires comparable published snapshots; cannot compare partial or incompatible days. | misleading deltas | Withholds stale, missing, partial, or incomparable comparisons. | 0B-07 | Strong existing fail-closed pattern. |
| Completed-game context `confidence` | Completed game context model/service | Field exists as stored metadata; public confidence-score framing is not approved. | confidence-score framing | Missing or ambiguous context returns empty/low-context output. | 0B-06 / 0B-07 | Treat as internal until reviewed. |
| Existing Stats API-derived storage legal posture | Current models and sync services | Repo does not cite source terms, attribution requirements, storage rights, or redistribution rights. | legal/source risk | No Phase 0B row advances to public candidate here. | 0B-03 / 0B-04 / 0B-07 | Mark `needs-legal-review`. |
| Pitch-level evidence | No current pitch-level source inventory in this branch | Phase 0B-02 does not audit pitch-level candidate sources. | incomplete evidence expansion | Leave as unknown. | 0B-05 | Out of scope here. |
| Paid or optional sources | No current paid-source inventory in this branch | No acquisition decision exists. | acquisition risk | Leave as unknown/internal-only. | 0B-07 | Out of scope here. |

## 10. Source Category Matrix Rows

These rows follow `docs/phase0b/templates/source_category_matrix.md`. They are
inventory rows only. `public_display` remains `INTERNAL-ONLY` because legal,
source, and public-display decisions are not made in this branch.

| category | field_group | source | retrieval_path | availability | update_timing | finality_safe | correction_behavior | failure_modes | historical_coverage | legal_posture | attribution_req | storage_risk | reliability_grade | maintenance_burden | bullpen_relevance | public_display | fail_closed_rule | priority_class | evidence_link | decided_in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1_existing_foundation | pitcher_identity_team_roster | statsapi_v1 | `pitchers`; `team_assignment_sync`; `roster_status_sync` | available | daily | UNKNOWN | roster/team evidence can update on later sync | stale assignment, unknown roster evidence, source ambiguity | current stored roster/team state; historical depth limited by stored rows | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | mark roster/team UNKNOWN or inactive when authority is missing or ambiguous | AUDIT-ONLY-0B | `backend/models/pitcher.py:4-34`; `backend/services/team_assignment_sync.py:314-346`; `backend/services/roster_status_sync.py:188-337` | 0B-02 |
| 1_existing_foundation | pitching_game_logs | statsapi_v1 | `game_logs`; `sync_service.process_completed_game` | available | at-final | corrected-after-final | stat correction provenance increments on safe overwrite | non-final game, unresolved pitcher, partial correction payload | stored completed-game logs only | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | exclude non-final games; dead-letter unsafe corrections; keep unknown fields unknown | AUDIT-ONLY-0B | `backend/models/game_log.py:4-71`; `backend/services/sync.py:920-1085`; `backend/tests/test_stat_correction_propagation.py:155-375` | 0B-02 |
| 1_existing_foundation | nullable_pitch_counts | statsapi_v1 | `game_logs.pitches_thrown`; workload concentration | partial | at-final | corrected-after-final | missing counts preserved as unknown; corrections can update known/unknown | missing pitch count, partial source payload | stored logs where source supplied or omitted pitch count | needs-legal-review | TBD | raw-cache-risk | B | medium | core | INTERNAL-ONLY | store NULL for missing pitch count; exclude unknown teams from pitch-count concentration | AUDIT-ONLY-0B | `backend/migrations/versions/e3b7a9c4d2f6_preserve_unknown_pitch_counts.py:1-24`; `backend/tests/test_unknown_safe_ingestion.py:68-121`; `backend/tests/test_workload_concentration.py:59-99` | 0B-02 |
| 19_correction_provenance | stat_correction_fields | derived_internal | `game_logs.stat_correction_count`; `last_stat_correction_*` | derivable | final+lag(observed) | corrected-after-final | safe corrections update row and provenance; unsafe corrections dead-letter | partial source, missing required correction keys, source mismatch | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | medium | supporting | INTERNAL-ONLY | reject unsafe correction and preserve prior row | AUDIT-ONLY-0B | `backend/migrations/versions/f6a2c9d8e1b3_add_game_log_correction_provenance.py:1-39`; `backend/services/sync.py:306-493`; `backend/tests/test_stat_correction_propagation.py:247-375` | 0B-02 |
| 19_correction_provenance | postgame_marker_lifecycle | derived_internal | `postgame_processed_games`; marker retry lifecycle | available | final+lag(observed) | yes | incomplete markers retry until failure threshold; failed markers stay visible | empty boxscore, unresolved pitchers, repeated incomplete attempts | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | medium | supporting | INTERNAL-ONLY | retry incomplete final games without duplicate logs, then stop at visible failed marker | AUDIT-ONLY-0B | `backend/models/postgame_processed_game.py:5-42`; `backend/services/sync.py:229-244`; `backend/tests/test_postgame_marker_lifecycle.py:266-443` | 0B-02 |
| 1_existing_foundation | sync_run_state | derived_internal | `sync_runs`; `sync_metadata` | available | daily | yes | later runs supersede metadata; failed stage retained | stale running run, concurrent writer, missing durable row | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | low | supporting | INTERNAL-ONLY | reject active writer conflict; degrade freshness when metadata unavailable | AUDIT-ONLY-0B | `backend/models/sync_run.py:5-46`; `backend/services/sync_metadata.py:151-283`; `backend/services/sync_metadata.py:396-549` | 0B-02 |
| 1_existing_foundation | sync_failure_dead_letters | derived_internal | `sync_failures` | available | final+lag(observed) | yes | unresolved failure records remain until resolved | unsafe correction, processing error, retry exhaustion | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | low | contextual | INTERNAL-ONLY | dead-letter unsafe or exhausted work instead of overwriting or hiding it | AUDIT-ONLY-0B | `backend/models/sync_failure.py:5-40`; `backend/migrations/versions/d8f1a2b6c40e_add_sync_failures.py:3-38`; `backend/services/sync_metadata.py:604-658` | 0B-02 |
| 1_existing_foundation | scheduled_games | statsapi_v1 | `scheduled_games`; `schedule_ingestion` | available | daily | no(live) | statuses can update before final | postponed/status changes, missing schedule context | stored schedule rows only | needs-legal-review | TBD | raw-cache-risk | B | medium | supporting | INTERNAL-ONLY | schedule-only context remains unavailable when status/context is missing | AUDIT-ONLY-0B | `backend/models/scheduled_game.py:5-68`; `backend/services/schedule_ingestion.py:1-163`; `backend/tests/test_tonight_intelligence_snapshot.py:264-284` | 0B-02 |
| 1_existing_foundation | completed_game_context | derived_internal | `completed_game_contexts`; context service/adapter | derivable | at-final | corrected-after-final | regenerated context can reflect corrected logs/source payloads | missing identity, boxscore-only ambiguity, incomplete play data | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | medium | supporting | INTERNAL-ONLY | return empty or low-context output when identity/context evidence is missing | AUDIT-ONLY-0B | `backend/models/completed_game_context.py:5-83`; `backend/services/completed_game_context_service.py:195-512`; `backend/services/completed_game_context_payload_adapter.py:1-181` | 0B-02 |
| 1_existing_foundation | slate_coverage_metadata | derived_internal | `slate_coverage`; freshness metadata | derivable | daily | yes | later postgame markers can move slate from incomplete to complete | final game without marker, incomplete marker, failed marker | derived for current served slate | needs-legal-review | TBD | derived-aggregate-ok | B | low | core | INTERNAL-ONLY | mark slate incomplete and not complete enough to publish when final-game coverage is missing | AUDIT-ONLY-0B | `backend/services/slate_coverage.py:509-544`; `backend/tests/test_slate_coverage.py:76-166` | 0B-02 |
| 1_existing_foundation | dashboard_snapshot_metadata | derived_internal | `dashboard_snapshots`; `/api/bullpen/dashboard` | available | daily | yes | newer published snapshot supersedes older snapshot | no valid snapshot, stale snapshot, snapshot generation error | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | serve latest valid published snapshot or return unavailable payload | AUDIT-ONLY-0B | `backend/models/dashboard_snapshot.py:5-33`; `backend/api/bullpen.py:2373-2864`; `.github/workflows/baseballos-sync.yml:136-217` | 0B-02 |
| 1_existing_foundation | what_changed_baseline | derived_internal | published dashboard snapshots; What Changed services | derivable | daily | yes | compares only trusted comparable published snapshots | missing prior snapshot, stale baseline, partial slate, incompatible windows | limited to retained published snapshots | needs-legal-review | TBD | derived-aggregate-ok | B | medium | contextual | INTERNAL-ONLY | withhold change read when snapshots are partial, stale, missing, or incomparable | AUDIT-ONLY-0B | `backend/services/what_changed_since_yesterday.py:54-80`; `backend/services/what_changed_since_yesterday.py:898-945`; `frontend/src/components/dashboard/WhatChangedCard.jsx:103-157` | 0B-02 |
| 1_existing_foundation | workload_availability_scores | derived_internal | `fatigue_scores`; availability services | derivable | daily | yes | recalculated from stored logs and roster/freshness state | missing logs, unknown pitches, stale freshness, roster unavailable | starts when migration is present | needs-legal-review | TBD | derived-aggregate-ok | B | medium | core | INTERNAL-ONLY | degrade to monitored/limited/unknown states when evidence is stale, incomplete, or unavailable | AUDIT-ONLY-0B | `backend/models/fatigue_score.py:4-33`; `backend/services/availability.py:152-328`; `backend/services/availability_snapshot.py:52-120` | 0B-02 |
| 1_existing_foundation | intelligence_snapshots | derived_internal | `intelligence_surface_snapshots`; `tonight_intelligence_snapshots` | available | daily | yes | newer generated snapshot supersedes old snapshot | cache miss, read failure, build timeout, empty schedule context | starts when migrations are present | needs-legal-review | TBD | derived-aggregate-ok | B | medium | contextual | INTERNAL-ONLY | return empty fail-closed payload or avoid writing error responses | AUDIT-ONLY-0B | `backend/models/intelligence_surface_snapshot.py:5-52`; `backend/models/tonight_intelligence_snapshot.py:5-50`; `backend/tests/test_tonight_intelligence_snapshot.py:87-334` | 0B-02 |

## 11. Out-Of-Scope And UNKNOWNs

- No new source candidate is approved here.
- No probe evidence is produced here.
- No pitch-level feasibility decision is made here.
- No paid-source or optional-source decision is made here.
- No legal conclusion is made here.
- No public-display expansion is made here.
- No schema, ingestion, API, or UI behavior is changed here.

## 12. Phase 0B-02 Decision

The existing BaseballOS foundation is strong enough to support later Phase 0B
audits because it already preserves unknowns, tracks corrections, records
durable sync state, publishes snapshot metadata, and fails closed for stale or
incomplete evidence.

This branch does not advance any row beyond audit status. The next Phase 0B
branches should audit the underlying source authority, legal posture, finality,
correction behavior, and public-display safety before any richer evidence is
adopted.
