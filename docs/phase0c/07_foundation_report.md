# Phase 0C Foundation Report

## Purpose

Phase 0C built source and schema foundations for later reliever appearance
evidence. It stores final, typed, provenance-carrying facts only. It does not
create public evidence interpretation, public payload fields, public copy,
frontend surfaces, pitch-level ingestion, paid-provider adoption, or Phase 0D
logic.

Result: PASS - Phase 0C can close after this branch's validation passes.

## Source Coverage Integration

Internal pipeline health now carries the Phase 0C readiness inventory through
`source_readiness.source_readiness_payload()` and
`sync_metadata.pipeline_health_payload()`. The diagnostic surface is internal
through `/api/system/pipeline-health`; public sync status remains unchanged and
does not expose `source_readiness`.

| Source family | Readiness family | Coverage/provenance signals | Fail-closed behavior | Public posture |
| --- | --- | --- | --- | --- |
| finality/status authority | `finality_authority` | Loaded finality rules and status requirements | Unsafe final status cannot become usable final evidence | Internal rule only |
| MLB Stats API core / boxscore | `statsapi_core` | Latest successful sync run, attempted run, unresolved failures, source, `sync_run_id` | Missing/stale/failed sync degrades or blocks current public gates | Existing ingestion dependency only |
| game logs and boxscore expansion | `game_logs` | latest workload date, row count, unresolved game-log/correction failures, source, `sync_run_id` | Missing provenance, stale data, or dead letters fail closed | Existing public consumers unchanged |
| slate coverage | `slate_coverage` | scheduled/final/fully ingested counts and publishability result | Incomplete slate remains not publishable | Existing public gate unchanged |
| dashboard snapshots | `dashboard_snapshots` | published snapshot timestamp, data-through date, source, `sync_run_id` | Missing or unprovenanced published snapshot blocks current public gates | Existing snapshot contract unchanged |
| roster status snapshots | `roster_status_snapshots` | latest snapshot date, active-team coverage, cache divergence, failures, source, `sync_run_id` | Missing, stale, incomplete, or divergent snapshots degrade/block | Internal foundation only |
| player transactions / IL typed facts | `player_transactions` | bounded window, fetched/stored counts, unknown-type/alignment counts, failures, source, `sync_run_id` | Failed windows, stale data, unknown types, or alignment gaps degrade/block | Internal foundation only |
| final play-by-play foundation | `final_play_by_play` | marker counts, event count, incomplete/failed/absent/ambiguous counts, reconciliation counts, source, `sync_run_id` | No fully processed final PBP, mismatches, or identity gaps fail closed | Internal foundation only |
| team game pitching splits | `team_game_pitching_splits` | expected rows, complete/partial/unknown/missing counts, reason counts, correction counts, source, `sync_run_id` | Missing, partial, unknown, or unprovenanced rows degrade | Internal foundation only |
| calendar context | `calendar_context` | expected rows, complete/partial/unknown/missing counts, reason counts, correction counts, source, `sync_run_id` | Missing, partial, unknown, or unprovenanced rows degrade | Internal foundation only |

The current blocking family set intentionally remains limited to current public
gates: finality authority, Stats API core, game logs, slate coverage, dashboard
snapshots, roster snapshots, and player transactions. Final PBP, team-game
splits, and calendar context report readiness for future consumers but do not
weaken existing slate coverage, dashboard publishability, freshness, or What
Changed gates.

## Foundation Families

### finality/status authority

- Stored or derived: finality classification, not a table.
- Code: `services.game_finality`, `services.source_readiness`.
- Source dependency: Stats API schedule/status plus boxscore when required.
- Finality gate: usable final requires safe final status; abstract final alone
  is not enough.
- Correction policy: not table-backed; downstream source-backed rows own their
  correction policies.
- Provenance behavior: reported as a readiness family with explicit rule
  details.
- Readiness diagnostics: `finality_authority` reports module readiness and rule
  flags.
- Fail-closed behavior: postponed, cancelled, in-progress, missing boxscore, or
  ambiguous states do not become usable final evidence.
- Public display posture: no new public display.
- Phase 0D may build: interpretation only after finality-certified stored rows.
- Phase 0D must avoid: live or in-progress public evidence.
- Legal review: inherited Stats API legal/storage/redistribution/SLA posture
  remains needs-legal-review.
- Known gaps: no source legal clearance decision is made here.

### boxscore expanded fields

- Stored or derived: extended `GameLog` fields such as `games_started`,
  `pitches_thrown`, `batters_faced`, `balls`, `games_finished`, and inherited
  runner fields.
- Code: `models.game_log`, sync/postgame ingestion paths, correction policy
  registry, `source_readiness`.
- Source dependency: finality-certified Stats API boxscore/pitching lines.
- Finality gate: completed-game ingestion requires safe final game status and a
  usable boxscore.
- Correction policy: `game_log_pitching_line_corrections`.
- Provenance behavior: correction counters, correction source, correction time,
  sync run, and source readiness link the field family back to sync runs and
  failures.
- Readiness diagnostics: `game_logs` reports row count, latest workload date,
  dead letters, source, `sync_run_id`, and stale status.
- Fail-closed behavior: missing provenance, stale workload, unresolved
  correction failures, or incomplete slate coverage prevent ready claims.
- Public display posture: existing public consumers are unchanged; no new public
  evidence interpretation is added.
- Phase 0D may build: completed-game reliever usage evidence after consumer
  gates are designed.
- Phase 0D must avoid: confidence scores, pressure labels, role claims, and
  unsupported usage interpretations.
- Legal review: Stats API usage remains needs-legal-review.
- Known gaps: public evidence language and consumer gates are Phase 0D or later.

### inherited-runner fabricated-zero repair

- Stored or derived: `GameLog.inherited_runners` and
  `GameLog.inherited_runners_scored` now preserve unknown as `NULL`.
- Code: `models.game_log`, migrations from 0C-03, correction policy registry.
- Source dependency: finality-certified boxscore fields only when present.
- Finality gate: same game-log finality gate as boxscore expansion.
- Correction policy: `game_log_pitching_line_corrections` marks both inherited
  runner fields updateable and unknown-safe on unsafe conflict.
- Provenance behavior: repaired/corrected values carry correction metadata on
  the game-log row.
- Readiness diagnostics: covered by `game_logs` source readiness and game-log
  dead-letter counts.
- Fail-closed behavior: absence remains unknown instead of becoming zero.
- Public display posture: no inherited-runner public display is added.
- Phase 0D may build: inherited traffic attribution only after explicit
  evidence rules exist.
- Phase 0D must avoid: treating unknown inherited traffic as clean or zero.
- Legal review: source posture remains needs-legal-review.
- Known gaps: attribution semantics are intentionally deferred.

### roster status snapshots

- Stored or derived: durable dated roster status snapshots and a derived pitcher
  row cache.
- Code: `models.roster_status_snapshot`, `services.roster_status_sync`,
  `services.source_readiness`.
- Source dependency: Stats API roster endpoints.
- Finality gate: roster snapshots are dated source state, not game finality
  evidence.
- Correction policy: `roster_status_snapshot_corrections`.
- Provenance behavior: snapshot rows carry source, `sync_run_id`, first-seen,
  last-corrected, correction count, and correction source.
- Readiness diagnostics: `roster_status_snapshots` reports latest snapshot date,
  team coverage, cache divergence, failure reason, source, and `sync_run_id`.
- Fail-closed behavior: missing, stale, incomplete, unprovenanced, or divergent
  snapshots degrade readiness.
- Public display posture: no new public evidence or roster interpretation is
  added.
- Phase 0D may build: roster availability context only after wording and source
  limits are approved.
- Phase 0D must avoid: health claims from missing IL data or unavailable roster
  facts.
- Legal review: source posture remains needs-legal-review.
- Known gaps: roster status can be source-limited and must not become a health
  claim.

### transaction and IL typed facts

- Stored or derived: bounded transaction windows, typed transaction categories,
  IL placement/activation flags, IL list type, roster-snapshot alignment, and
  sync-window counters.
- Code: `models.player_transaction`, `services.transaction_ingestion`,
  `services.source_readiness`.
- Source dependency: Stats API transactions endpoint.
- Finality gate: transaction facts are dated source facts, not game finality
  evidence.
- Correction policy: `player_transaction_corrections`.
- Provenance behavior: transaction rows and sync windows carry source endpoint,
  query window, source, `sync_run_id`, first-seen/correction fields, and window
  counts.
- Readiness diagnostics: `player_transactions` reports window status, fetched
  and stored counts, unknown-type counts, roster-alignment counts, failures,
  source, and `sync_run_id`.
- Fail-closed behavior: failed windows, stale windows, unknown transaction
  types, roster-alignment gaps, or missing provenance degrade readiness.
- Public display posture: no public transaction, IL, health, depth, or
  availability claim is added.
- Phase 0D may build: typed roster movement context after wording and evidence
  rules exist.
- Phase 0D must avoid: free-text injury descriptions, health claims, return
  timetables, and IL/depth pressure reads without approved evidence.
- Legal review: source posture remains needs-legal-review.
- Known gaps: typed transactions are explanatory candidates only; roster
  snapshots remain the current-state authority.

### final play-by-play foundation

- Stored or derived: normalized final PBP event rows and per-game processing
  markers.
- Code: `models.play_by_play_foundation`,
  `services.play_by_play_foundation`, `services.source_readiness`.
- Source dependency: Stats API final play-by-play endpoint plus boxscore
  reconciliation.
- Finality gate: PBP storage runs only after `FINAL_AND_USABLE` classification
  with required boxscore evidence.
- Correction policy: `game_play_by_play_event_corrections` and
  `play_by_play_processed_game_corrections`.
- Provenance behavior: event and marker rows carry source endpoint, source,
  `sync_run_id`, first-seen/correction fields, retry counts, and fingerprints.
- Readiness diagnostics: `final_play_by_play` reports marker statuses, event
  counts, retry counts, reconciliation mismatches, unresolved pitcher counts,
  source, and `sync_run_id`.
- Fail-closed behavior: missing, absent, incomplete, failed, ambiguous, or
  reconciliation-mismatch markers do not look ready.
- Public display posture: no public PBP payload or event text is added.
- Phase 0D may build: entry/exit context, inherited traffic context, and clean
  or traffic inning context only after interpretation rules exist.
- Phase 0D must avoid: live PBP, raw source exposure, role inference, pressure
  claims, or public evidence from in-progress games.
- Legal review: source posture remains needs-legal-review.
- Known gaps: no inherited-runner attribution or public event narration is
  implemented.

### team game pitching splits

- Stored or derived: starter/bullpen outs, pitches, batters faced, balls,
  reliever count, total team pitching facts, starter identity status, split
  completeness status, and reason codes.
- Code: `models.team_game_pitching_split`,
  `services.team_game_pitching_splits`, `services.source_readiness`.
- Source dependency: final scheduled games plus final stored game logs.
- Finality gate: derivation requires final schedule rows or a safe final
  fallback; unresolved resumed-game linkage becomes ambiguous or fails closed.
- Correction policy: `team_game_pitching_split_corrections`.
- Provenance behavior: rows carry source, `sync_run_id`, first-seen,
  last-derived, correction count, last-corrected, and correction source.
- Readiness diagnostics: `team_game_pitching_splits` reports expected rows,
  complete/partial/unknown/missing counts, reason-code counts, dead letters,
  source, and `sync_run_id`.
- Fail-closed behavior: nullable arithmetic keeps missing components unknown;
  missing, partial, unknown, or unprovenanced rows degrade readiness.
- Public display posture: no public starter exposure, bullpen share, or team
  structure read is added.
- Phase 0D may build: starter exposure context and bullpen share evidence after
  explicit interpretation rules exist.
- Phase 0D must avoid: short-start pressure, opener/bulk inference, role
  claims, team structure claims, and prediction.
- Legal review: derived rows inherit source legal posture from schedule and game
  logs.
- Known gaps: interpretation and public language are not designed in this
  branch.

### calendar context

- Stored or derived: off-day before/after, consecutive game-day count entering,
  series game number, games in series, doubleheader flag/code, game number,
  postponed/makeup indicator, suspended/resumed linkage status, extra-inning
  indicator, calendar completeness status, and reason codes.
- Code: `models.team_game_pitching_split`,
  `services.team_game_pitching_splits`, `services.source_readiness`.
- Source dependency: final schedule rows and stored game-log context.
- Finality gate: same final schedule and safe final fallback gate as team-game
  splits.
- Correction policy: `team_game_pitching_split_corrections`.
- Provenance behavior: shared team-game split provenance and correction fields.
- Readiness diagnostics: `calendar_context` reports expected rows,
  complete/partial/unknown/missing counts, reason-code counts, dead letters,
  source, `sync_run_id`, correction count, and `travel_context_inferred=False`.
- Fail-closed behavior: missing or ambiguous schedule context remains partial
  or unknown; no travel effect is inferred.
- Public display posture: no public calendar context display is added.
- Phase 0D may build: calendar-density reads only after evidence and wording
  rules exist.
- Phase 0D must avoid: travel fatigue, rest advantage, manager intent,
  availability, pressure, prediction, or result-impact claims.
- Legal review: derived rows inherit source legal posture from schedule and game
  logs.
- Known gaps: travel/source-location facts are not present and must not be
  inferred.

### source readiness/provenance framework

- Stored or derived: readiness states, reason codes, coverage/details payloads,
  source provenance, correction-policy registry, and source-writer guard
  behavior.
- Code: `services.source_readiness`, `services.source_provenance`,
  `services.source_correction_policies`, `services.sync_metadata`,
  `api.system`.
- Source dependency: source-backed model rows, sync runs, dead letters, slate
  coverage, and published snapshots.
- Finality gate: readiness does not override family-specific finality gates.
- Correction policy: registry requires explicit policies for
  correction-sensitive models and fails unregistered contracts.
- Provenance behavior: families report source, `sync_run_id`, last attempted,
  last successful, dead letters, and coverage/details where available.
- Readiness diagnostics: all ten Phase 0C families appear in internal pipeline
  health.
- Fail-closed behavior: missing, stale, incomplete, failed, ambiguous, unknown,
  or unprovenanced families do not look ready.
- Public display posture: internal/admin diagnostics only.
- Phase 0D may build: consumer gates that require ready source families.
- Phase 0D must avoid: treating diagnostics as public evidence language.
- Legal review: readiness does not resolve source legal posture.
- Known gaps: readiness reports evidence quality, not source licensing approval.

### public payload isolation

- Stored or derived: no storage; this is a contract boundary.
- Code: public surfaces remain `api.bullpen`, dashboard snapshot, bullpen board,
  What Changed, and Tonight snapshot modules.
- Source dependency: existing public data contracts only.
- Finality gate: existing slate coverage, dashboard publishability, freshness,
  and What Changed gates remain the public guardrails.
- Correction policy: not table-backed.
- Provenance behavior: no new Phase 0C provenance is serialized publicly.
- Readiness diagnostics: internal pipeline health only.
- Fail-closed behavior: invariant tests fail if public dashboard/board/snapshot
  or What Changed modules start consuming 0C-new tables.
- Public display posture: unchanged.
- Phase 0D may build: public evidence surfaces only after an approved Phase 0D
  plan and consumer gates.
- Phase 0D must avoid: unsupported claims, raw source exposure, and public
  fatigue/confidence/trust score framing.
- Legal review: public reuse of new source-backed facts remains
  needs-legal-review.
- Known gaps: public copy and product framing are intentionally deferred.

## Sync-Time Budget

The scheduled sync workflow `.github/workflows/baseballos-sync.yml` has
`timeout-minutes: 25`. The workflow comment records that 15 minutes was too
tight for expected production work, while 25 minutes provides headroom. The
workflow also records phase/elapsed timing and the
`POSTGAME_REFRESH_SNAPSHOT` skip lever for the homepage lead-story rebuild.

Phase 0C added bounded roster snapshot writing, a bounded transaction/IL stage,
final PBP marker/retry work, team-game split recomputation, and readiness
diagnostics. These are integrated into existing daily/postgame orchestration;
this branch does not redesign the scheduler.

Budget status: documented headroom, no new timeout fix required in this branch.
No fresh production-timed run is created by this documentation branch. If future
CI or scheduled runs become tight, the scoped follow-up options are to split
daily/postgame stages, isolate final PBP/backfill work, or make derived
recomputation more targeted. Those options are deferred because no critical
timeout problem is evidenced here.

## Phase 0C Exit Checklist

Result: PASS - Phase 0C can close.

- [x] One finality authority governs ingestion paths.
- [x] Postponed, suspended, cancelled, or empty-box states cannot classify as
  final usable evidence.
- [x] Resumed games attribute safely or fail closed.
- [x] Every new stored field is nullable or unknown-safe where appropriate.
- [x] Every new correction-sensitive field/table has a registered correction
  policy.
- [x] Boxscore expansion fields ingest unknown-safe.
- [x] Inherited-runner fabricated zeroes are repaired.
- [x] Roster snapshots are durable dated authority.
- [x] Pitcher-row roster status is a derived cache.
- [x] Transactions and IL facts are typed only.
- [x] No raw transaction JSON is persisted.
- [x] No free-text injury descriptions are persisted.
- [x] Roster snapshot precedence over transactions is preserved.
- [x] Final PBP storage is normalized typed rows only.
- [x] No raw PBP JSON cache exists.
- [x] PBP rows are final-only.
- [x] PBP readiness fails closed on missing, ambiguous, mismatch, incomplete,
  absent, or failed states.
- [x] Team-game pitching splits use nullable arithmetic.
- [x] Calendar context is descriptive only.
- [x] No travel inference is built.
- [x] Every new source family reports readiness, staleness or final coverage,
  coverage counts, reason codes, dead letters/failure counts, source, and
  provenance internally where applicable.
- [x] No public payload consumes Phase 0C-new data.
- [x] Public display posture is unchanged.
- [x] Legal-review flags remain recorded and unresolved where applicable.
- [x] Sync budget has documented headroom and documented follow-up options.
- [x] Full backend tests pass for this branch.
- [x] Phase 0C can close; no named blockers remain.

## Phase 0D Handoff

Phase 0D may later design evidence interpretation on top of the gated Phase 0C
foundation: entry/exit context, inherited traffic attribution, clean or traffic
inning context, pressure/leverage proxy, role inference, team bullpen structure
reads, starter exposure reads, IL/depth pressure reads, and pitch-level trends
only after legal/source/correction posture is cleared.

Phase 0D must still avoid unsupported public claims, betting/projection/odds
language, manager-intent certainty, health claims from missing IL data, public
fatigue/confidence/trust score framing, live/in-progress public evidence, raw
source exposure, and pitch-level public display until legal/source/correction
posture is cleared.

Do not start Phase 0D implementation from this branch. After merge, request and
approve a Phase 0D sequencing plan before implementation begins.

## Remaining Risks

- Stats API legal, attribution, storage, redistribution, and SLA posture remains
  needs-legal-review.
- Phase 0C readiness is point-in-time code coverage; production scheduled sync
  timing should continue to be watched.
- Final PBP, team-game split, and calendar readiness are future-consumer gates,
  not current public product gates.
- Public interpretation, public copy, methodology language, and frontend
  evidence surfaces are intentionally deferred.
