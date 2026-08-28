# CU-01 — Continuous Reliever Ingestion Foundation Audit

**Status:** Pre-implementation repository audit
**Audit base:** `74addba25f6113b7fb9ca943ee4e2b5a67bd6351`
**Scope:** Canonical ingestion and shadow proof only. No serving-authority, Team State, frontend, or publication change.

## 1. Current authoritative ingestion path

The scheduled daily sync remains authoritative. `.github/workflows/baseballos-sync.yml` runs `run_due_sync.py`, which dispatches `run_daily_sync.py`. `services.sync.run_daily_sync` refreshes schedule/finality, roster and team-assignment evidence, transactions, and then runs two coexisting appearance lanes:

1. `services.game_driven_ingestion` runs first in configured `shadow` mode. It plans by final game, fetches each box score once, extracts appearances, and asks the canonical reconciliation planner what would happen without writing.
2. `services.sync.sync_recent_logs` remains the production writer. It requests player game logs, applies the same canonical `GameLog` reconciliation rules (with governed box-score fallback), and remains the publication-critical authority while the game-driven mode is not `authoritative`.

Both lanes target `game_logs`; there is no separate appearance-ledger table. `GameLog` is the canonical appearance grain, uniquely keyed by `(pitcher_id, mlb_game_pk)`. The appearance ledger is a completeness audit over scheduled final games, stored appearance counts, and durable postgame markers—not an alternate record store.

## 2. Current postgame path

Scheduled postgame runs call `services.sync.run_postgame_refresh`. It discovers completed games in a bounded lookback, fetches one box score per unprocessed/retryable game, calls `process_completed_game_for_postgame_refresh`, resolves or minimally creates canonical pitcher identity, upserts `GameLog`, writes a `PostgameProcessedGame` marker, recomputes team-game pitching splits, and best-effort processes linescore/final play-by-play context. It then recalculates fatigue/rest for the canonical rows and may build/publish a dashboard snapshot if every existing gate passes.

The postgame game-driven lane runs only in `shadow`. The postgame coordinator explicitly refuses game-driven `write` or `authoritative` modes because that cycle has no second-writer exclusion mechanism. Daily write mode has a `skip_game_pks` exclusion for the legacy loop, but it is not enabled in production.

## 3. Current final-game detection behavior

`services.game_finality` is the shared authority. Terminal non-final states, postponed/suspended/cancelled games, missing identifiers, and status conflicts fail closed. `abstractGameState=Final` alone is insufficient. A game is usable for canonical ingestion only when the final status is safe and a supplied box score contains usable pitching identities for both sides. Schedule refresh persists finality evidence in `scheduled_games`; the game planner consumes that ledger and preserves represented-date handling for suspended/resumed games.

## 4. Existing canonical reliever fields

`GameLog` already stores canonical pitcher identity, game identity/date/type, game-side appearance team authority and resolution provenance, opponent metadata, official starter signal, integer outs plus derived decimal innings, pitches, strikes, hits, runs, earned runs, walks, strikeouts, home runs, batters faced, balls, games finished, inherited runners/scored, save opportunity, hold, blown save, win/loss/save, leverage, and correction metadata. `Pitcher.mlb_id` is the canonical external identity; mutable current-team fields are not appearance ownership.

Team assignment history is represented by correction-aware `PlayerTransaction` rows plus dated `RosterStatusSnapshot` rows and current `Pitcher` assignment authority. `TeamGamePitchingSplit` stores purpose-built derived game/team totals. `CompletedGameContext` and normalized final play-by-play events store coarse game state and pitcher-change context.

## 5. Existing derived-only reliever fields

Decimal innings is a stored compatibility companion derived from canonical outs. Starter/reliever identity is derived per appearance from `games_started` (with the existing first-pitcher fallback when MLB omits the flag). Fatigue, recent workload windows, rest/availability reads, appearance leverage/context evidence, inherited-traffic evidence, entry-band usage, team relief composition, Team State, team/pitcher reads, Matchup/Tonight composition, and public “Why” explanations are downstream computations or immutable read artifacts—not canonical source facts to duplicate on ingestion rows.

Entry/exit inning and score context are derivable only when normalized final play-by-play is complete. Unknown or ambiguous play context must remain unavailable; it must not be inferred from current roster state or a pitching line alone.

## 6. Missing reliever facts

The final box-score pitching section reliably supplies two requested facts that `GameLog` does not normalize: hit batters (`hitBatsmen`/`hitByPitch`) and wild pitches (`wildPitches`). Existing source probes and a current final-game read also show the already-normalized pitching-line facts above.

Existing writers incorrectly collapse absence to zero for several numeric and boolean fields (`strikes`, runs, earned runs, strikeouts, home runs, save/hold/outcome flags). CU-01 must make source presence authoritative so omitted or malformed optional values remain null/unknown.

Appearance rows also lack first-write source endpoint, acquisition timestamp, and observed-content revision. Correction metadata alone cannot identify the evidence/version behind an unchanged first write.

Box-score fields such as air/ground/fly outs, doubles/triples, stolen-base bookkeeping, sacrifice outcomes, and rate summaries are not required first-class appearance facts for the current/future bullpen workload seam: most are batter/team bookkeeping or derivable aggregates, and source-provided rates can be recomputed from canonical counts. They should not be copied blindly.

## 7. Existing pitch-level support

BaseballOS currently stores one normalized `GamePlayByPlayEvent` per plate appearance/pitching-change context, not one row per pitch. Raw play-by-play is not retained. The MLB final play-by-play response supplies stable game/at-bat/event ordering plus pitch type, call/outcome, start/end velocity, spin, movement/break measures, release position, extension, zone/plate coordinates, count, and batted-ball measurements/outcome where present. No current table preserves those pitch events.

CU-01 therefore requires normalized, correction-aware pitch-event storage. A game-local natural key must prevent duplicate pitches on replay. Missing tracking fields remain null. The plate-appearance foundation remains intact and continues to support coarse entry/exit derivation.

## 8. Duplicate or competing ingestion paths

There are three related paths, but only one canonical row planner/writer:

- legacy player-driven daily game-log acquisition (`sync_recent_logs`), currently authoritative;
- postgame box-score acquisition (`process_completed_game_for_postgame_refresh`), currently authoritative on scheduled postgame cycles;
- game-driven incremental ingestion (`game_driven_ingestion`), automated in read-only shadow mode and capable of reviewed write mode.

The game-driven lane intentionally reuses `process_completed_game_for_postgame_refresh`, `_extract_pitching_lines_from_boxscore`, pitcher identity reconciliation, `game_log_reconciliation.plan_row`, and `_upsert_game_log_from_authoritative_values`. CU-01 must extend this seam rather than introduce another framework or writer.

## 9. Current database ownership of appearance/team attribution

`GameLog.appearance_team_id` owns historical game-side team attribution. `appearance_team_status/source/reason` fail closed on missing or conflicting official evidence. The database check constraint forbids a resolved row without a team and forbids unresolved/conflict rows from carrying one. `Pitcher.team_id` owns mutable current assignment only and must never rewrite historical appearance ownership. Team IDs are canonical MLB integers; the repository has no `teams` dimension foreign key.

## 10. Historical/snapshot boundaries that must not be disturbed

CU-01 must mutate only current canonical source rows under existing correction rules. It must not rewrite `DashboardSnapshot`, `IntelligenceSurfaceSnapshot`, `TonightIntelligenceSnapshot`, Team State history, progressive team publications, share artifacts, or previously published payloads. Publication remains a separate gated transaction; failed candidates continue serving the prior trusted snapshot. New pitch/source facts are internal canonical evidence and are not added to frontend or public payloads in CU-01.

## 11. Exact CU-01 attachment seam

Attach at the existing final-game boundary:

`game change -> game_ingestion_planner -> game_finality -> game_driven_ingestion -> process_completed_game_for_postgame_refresh/game_log_reconciliation`

Extend the canonical pitching-line value builder and planner with the missing supported appearance facts and first-write provenance. Extend the existing final play-by-play foundation with normalized pitch rows. Add one explicit, read-only impact/comparison result constructed from the extracted final-game appearances:

`affected game -> relief appearances -> canonical pitcher ids -> appearance team ids -> workload-input comparison`

The outer daily/postgame coordinators already invoke the existing fatigue/rest computation after ingestion. CU-01 should report affected identities for future targeted recomputation but must not change Team State methodology or create an event bus.

## 12. Schema changes actually required

Required:

- nullable `GameLog.hit_batters` and `GameLog.wild_pitches`;
- first-write source metadata/revision fields on `GameLog`;
- normalized `GamePitchEvent` storage with a game-local unique key, canonical pitcher linkage, game-side team attribution, supported pitch/trajectory fields, source metadata, correction counters, and current/superseded state;
- pitch counts/fingerprint on the existing play-by-play processed-game marker so complete/no-op/correction behavior is observable.

Not required: a new game table, a second appearance table, raw unlimited JSON payload storage, a teams dimension, new read models, an event bus, or any snapshot/publication migration.

Raw box-score/play-by-play persistence is unnecessary for CU-01. The normalized rows retain every supported fact in scope plus endpoint, acquisition time, sync run, and content fingerprints; source data remains reacquirable by `gamePk`. Retaining unlimited payload JSON would add unbounded storage and governance cost without improving this acceptance gate.

## 13. Risks

- MLB can omit tracking fields for individual pitches; nullability and presence-driven correction are mandatory.
- Play-event indexes may change after an official correction. Reconciliation must supersede stale current rows and upsert the corrected set idempotently.
- A partial play-by-play endpoint must not make the authoritative pitching line fail; it is an observable optional-domain failure and pitch comparison remains incomplete.
- Expanding the governed `GameLog` field vocabulary without updating correction, fingerprint, and parity contracts would recreate the prior shadow/write drift.
- Pitch rows can be materially larger than appearance rows. Game-scoped acquisition and indexes must remain bounded; no full-season pitch rescans are introduced.
- Existing consumers may assume false/zero defaults. Targeted contract tests must prove unknown handling without changing public semantics.

## 14. Tests required before authority can ever migrate

CU-01 requires finalized multi-reliever ingestion; replay/no-op behavior; canonical identity; game-side ownership despite current-team changes; null preservation; full supported pitching-line storage; normalized pitch storage and duplicate prevention; stale-pitch supersession on correction; affected pitcher/team resolution; overlapping workload input comparison with explicit equivalent/new/unsupported classifications; optional play-by-play failure evidence; and proofs that publication, snapshots, history, and frontend behavior are untouched.

Before a later authority migration, production shadow evidence must additionally prove complete schedule/finality coverage, source-revision stability, correction replay, suspended/resumed and doubleheader handling, identity and team-attribution closure, pitch-domain completeness/volume, zero unexplained comparison differences, durable restart behavior, and a rollback procedure. CU-01 does not authorize that migration.
