# SP-08 Live Game Delta Pipeline

## 1. Objective

SP-08 adds durable, provisional bullpen evidence while an MLB game is in progress. It records the bullpen-relevant projection of the existing MLB live feed, reconciles a current provisional appearance per pitcher, retains meaningful live mutations, and schedules a single authority-labelled impact handoff. It does not create final baseball truth or derived bullpen intelligence.

## 2. Existing Infrastructure Reused

The implementation extends the existing CU live-feed path rather than adding another detector. `game_change_detection` remains the accepted source-order and material-fingerprint authority; `GameObservationState` remains the one current accepted feed state per `gamePk`; SP-03 retains immutable observations; SP-02 provides dedupe, claiming, leases, fencing, retries, and settlement; SP-01 provides the `live_game` run envelope. The official boxscore parser and the shared appearance/PBP context extractor are reused. Existing CU obligations remain unchanged and are not retired.

## 3. Live Authority Model

`authority_state = live` means that MLB exposed the fact in a structurally usable in-progress feed. It may establish observed participation, team-at-appearance, current official line counters, starter replacement, reliever entry, and provisional outing closure. It never establishes a final decision, save, hold, inherited-runner outcome, role judgment, performance record, or completed workload record.

The current provisional row is mutable because the live feed evolves. Every meaningful mutation retains its prior and new bounded state. Source observations remain immutable.

## 4. Final Authority Boundary

SP-07 remains the only authority for final and corrected-final appearances. On successful SP-07 reconciliation, current SP-08 rows are marked non-current and linked to the current `final_game_versions` row. They are not deleted or rewritten. A last-live value of 22 pitches and a final value of 23 therefore remain independently provable.

## 5. Live Source Observation Contract

The existing subject identity remains `MLB_STATS_API / LIVE_FEED / game:{gamePk}` at `/api/v1.1/game/{game_pk}/feed/live`. The normalized SP-03 payload schema is version 2 for non-final observations and retains a bounded `live_pitching` projection. Final observations keep the established schema because SP-07 owns their pitching authority.

Each worker links the observation/fetch attempt to its SyncRun and SyncJob. Exact normalized replay is `unchanged`. Older, weaker, equal-revision ambiguous, and final-evidence-regressing responses cannot replace accepted state. A transport failure records a failed fetch attempt and creates no observation or provisional mutation.

## 6. Provisional Appearance Model

`provisional_pitching_appearance_states` has one row per `(game_pk, pitcher_id)`. It retains baseball date, MLBAM/canonical identity, game-side team and opponent, side, starter/reliever observation, source-proven appearance order when available, outing status (`active`, `closed`, or `unknown`), official live pitching counters, inning/half, available entry context, first/latest observation pointers, upstream observation time, fact fingerprint/version, completeness, current/supersession state, and first/latest seen times.

Unknown remains unknown. Missing optional PBP context does not prevent retention of a usable official live pitching line. Pitch events remain in the existing PBP substrate and are not duplicated here.

## 7. Live Delta Model

`live_game_mutations` is compact and append-only. A unique mutation key combines game, source observation, mutation type, and pitcher. It retains authority state, exact game/team/pitcher scope, old/new fact fingerprints, old/new bounded state, source observation, SyncRun, and correction flag. Polls without a meaningful provisional fact change create no mutation.

## 8. Mutation Vocabulary

The controlled values are:

- `live_appearance_started`
- `live_appearance_updated`
- `live_appearance_completed`
- `live_starter_exited`
- `live_reliever_entered`
- `live_multi_inning_reached`
- `live_appearance_corrected`

These are observations, not workload, availability, deployment, role, or performance conclusions.

## 9. Starter Exit / Reliever Entry

Starter and reliever classification uses the official per-game `gamesStarted` fact with the existing positional fallback. Appearance order and replacement evidence come from PBP entrance sequence. Once a later pitcher for the same game side is observed, the prior pitcher is provisionally closed; a starter closure is `live_starter_exited`, and a newly observed relief appearance is `live_reliever_entered`.

Team-at-appearance always comes from the game side. Current `Pitcher.team_id` and current roster membership never override participation evidence.

## 10. Active vs Closed Outing

For each team, the latest PBP-proven pitcher remains active even while that team bats. A prior pitcher for that side is closed only when later entrance evidence exists. If the source cannot establish either state, `unknown` is retained. This prevents inning-half transitions or partial feeds from falsely closing an outing.

## 11. Polling Policy

Policy `live-game-delta-poll-v1` is centralized:

| State | Interval | Priority |
|---|---:|---:|
| resumed | immediate | 5 |
| live | 90 seconds | 10 |
| delayed after play began | 150 seconds | 15 |
| suspended, pregame, final, or other | no SP-08 follow-up | n/a |

Delayed games without accepted play/inning evidence are not SP-08 work. SP-04 remains game-state authority. The policy creates no busy loop and does not change any deployed scheduler.

## 12. Queue / Priority / Dedupe

The dedicated job type is `fetch_live_game_delta`. Payload schema version 1 carries `game_pk`, baseball date, expected game state, reason, and policy version. The active identity is `LIVE_GAME:{gamePk}:{available-minute}:{policy}`; follow-ups add the parent job identity so an executing generation cannot suppress its successor. SP-02's active partial unique index and lower-number-higher-priority ordering remain authoritative.

Meaningful live changes create one `process_canonical_impact` job with `authority_state = live`, mutation IDs, exact team/pitcher IDs, source observation, game, and baseball date. SP-08 does not execute that job.

## 13. Monotonicity / Corrections

Pitches, outs, and batters faced normally advance. A lower value from stale or ambiguous source order is rejected before provisional reconciliation. A lower value in a strictly newer accepted MLB revision is retained as a live correction: the current row changes, the old state survives in `live_game_mutations`, and `is_correction` is true. No blended value is invented.

## 14. Out-of-Order Protection

The current observation's upstream MLB timestamp and authority rank are checked before any provisional write. A game-scoped PostgreSQL advisory transaction lock serializes only the same `gamePk`. The mutable rows are then selected `FOR UPDATE`. Thus an older observation cannot regress current state and unrelated games remain concurrent.

## 15. Roster Boundary

A live participant absent from SP-05 roster authority is still retained. Missing canonical identity is created minimally with no current team or active-roster claim. SP-08 never mutates roster membership or a known pitcher's current assignment.

## 16. Live to Final Handoff

When SP-04 reports Final, SP-08 stops scheduling follow-ups and SP-07's existing `reconcile_final_game` job remains responsible. A successful SP-07 generation marks provisional rows non-current and links them to that final generation. Corrected finals remain entirely SP-07/SP-13 territory.

## 17. Failure / Partial Behavior

- Failed fetch: record failed SP-03 attempt, preserve known-good state, raise so SP-02 retries.
- Structurally partial live pitching projection: retain source evidence, create no appearance mutation, remove no pitcher, close no outing, reduce no counter.
- Unchanged accepted content: successful zero-mutation run and next poll.
- Final/unsupported state: successful no-fetch skip when known before work; no live mutation.

## 18. Concurrency / Fencing

SP-02 claim tokens are revalidated after acquisition and before commit. A reclaimed job cannot be settled by the stale owner. PostgreSQL `pg_advisory_xact_lock` scopes reconciliation to one game, row locks protect current provisional appearances, unique `(game_pk, pitcher_id)` and mutation-key constraints prevent duplicate current rows/mutations, and the downstream queue dedupe prevents duplicate impact work.

## 19. Database / Index Design

Migration `f9c2a7e4b1d6` is additive and reversible. It adds the two SP-08 tables and three nullable fields to `game_observation_states`: `live_bullpen_fingerprint`, `next_live_poll_at`, and `live_polling_policy_version`.

Indexes support due live work, game/team appearance order, active outings, team/date history, source provenance, and mutation queries by game/team/pitcher. JSON is limited to bounded entry/base state and old/new mutation state; it is not indexed and contains no raw feed duplication.

## 20. Explicit Non-Goals

SP-08 does not change production schedules, activate a continuous worker, implement final authority, infer roster membership, calculate workload/rest/Team State/arm reads/role/deployment/performance/rotation transfer, build read models, publish, ingest Savant/Statcast, or change frontend/API semantics.

## 21. SP-09 / SP-10 Handoffs

SP-09 receives one durable impact job for a meaningful live mutation set and must preserve `authority_state = live` when mapping effects. It will decide downstream impact and may not treat provisional facts as final.

SP-10 may later combine current provisional pitches, outs, observed appearance, multi-inning evidence, and team bullpen usage with authoritative historical facts. It must replace provisional inputs with SP-07 final facts when available and must not interpret observed work as medical readiness.

## 22. Acceptance Checklist

- [x] Existing CU live observation and source ordering are reused.
- [x] Live pitching evidence is source-provenanced and provisional.
- [x] Current appearances and meaningful mutations are durable.
- [x] Reliever entry, starter exit, closure, updates, and multi-inning transitions are representable.
- [x] Unchanged, partial, failed, corrected, stale, and out-of-order behavior fails safely.
- [x] Polling is one-shot, versioned, persistent, prioritized, and deduplicated.
- [x] Exact affected entities and one authority-labelled SP-09 handoff are retained.
- [x] SP-02 fencing and game-scoped PostgreSQL locking protect mutable state.
- [x] SP-07 supersedes without deleting live evidence.
- [x] Migration round-trip and focused SQLite/PostgreSQL contracts are covered.
- [x] Production scheduling, baseball semantics, publication, Statcast, frontend, and main remain untouched.
