# SP-07 Final Game Reconciliation

## 1. Objective

SP-07 turns an SP-04 `reconcile_final_game` job into immutable, correction-aware final game and pitching-appearance facts. It revalidates official Final status, records exact MLB source observations, invokes the existing canonical GameLog and final-PBP writers, versions only changed final facts, and emits one bounded SP-09 handoff. It does not derive bullpen intelligence or publish anything.

## 2. Existing Infrastructure Reused

| Existing component | Disposition | SP-07 use |
|---|---|---|
| `services.sync.process_completed_game_for_postgame_refresh` | REUSE / WRAP | Sole GameLog compatibility writer and pitcher-identity resolver. |
| `services.game_appearance_extraction` | EXTEND | Canonical official appearance projection and fingerprint; `balks` joins the retained official fields. |
| `GameLog` | REUSE AS CURRENT PROJECTION | Existing `(pitcher_id, mlb_game_pk)` readers and correction behavior remain compatible. |
| `services.play_by_play_foundation` | REUSE / WRAP | Existing final play, pitch, correction, and reconciliation storage remains the PBP foundation. |
| `GameIngestionWorkItem`, `PostgameProcessedGame` | REUSE / COEXIST | Existing CU/daily completion evidence remains intact. A proven completed matching work item permits no-impact bootstrap of immutable versions. |
| SP-03 source subjects, observations, artifacts, attempts | REUSE AS-IS | Own raw evidence, content dedupe, completeness, fingerprints, and source correction lineage. |
| SP-02 `SyncJob` | REUSE AS-IS | Consumes `reconcile_final_game`; creates one deduplicated `process_canonical_impact` handoff. |
| SP-01 `SyncRun` | REUSE AS-IS | Records final-run lifecycle, counters, scopes, parent/correlation lineage, partial success, and zero-mutation success. |
| `CompletedGameContext` and derived split builders | DO NOT TOUCH | They remain legacy derived behavior; SP-10 owns future derivation from final facts. |
| CU incremental workload, Team State, reads, publication | DO NOT TOUCH | SP-09 through SP-11 own later activation and convergence. |

No second boxscore parser, pitcher dimension, GameLog writer, PBP store, queue, or run system was introduced.

## 3. Final Source Authority

Official MLB status is the finality authority. A job is not sufficient proof: SP-07 refetches the game-grain schedule record and requires the existing `FINAL_AND_USABLE` decision with a complete official boxscore.

Official final boxscore pitching sections own participation, game side, actual starter signal, official line totals, decisions, saves, holds, blown saves, and inherited-runner totals when those keys are present. Final MLB play-by-play owns entrance sequence and reproducible event state. SP-06 probable starters and SP-05 rosters are context only and cannot establish actual participation.

## 4. Source Observation Contract

One execution uses three independent SP-03 identities:

| Subject | Domain | Endpoint | Grain | Raw retention |
|---|---|---|---|---|
| `game:{gamePk}:finality` | `schedule` | `/schedule?gamePk=...&hydrate=team` | game/fetch | Content-addressed JSON |
| `game:{gamePk}:final-boxscore` | `boxscore` | `/game/{gamePk}/boxscore` | game/final revision | Content-addressed JSON |
| `game:{gamePk}:final-play-by-play` | `play_by_play` | `/game/{gamePk}/playByPlay` | game/final revision | Content-addressed JSON |

Each observation retains its request identity, fingerprint/version, completeness, payload schema, fetch attempt, run/job links, observed time, and predecessor. Identical responses reuse the current observation and artifact. A changed post-final response is recorded as a correction candidate; SP-07 then compares canonical fact fingerprints independently.

## 5. Core vs Optional Domains

Core is fail-closed: exact game identity, official Final status, both game-side teams, a usable pitching section for each side, pitcher identities, actual starter/reliever classification, official basic lines, and resolved team-at-appearance. No GameLog or immutable final version commits if any core condition fails.

Final PBP is degraded-but-servable. A failed, partial, absent, or ambiguous PBP attempt cannot erase or zero a complete boxscore line. Core commits with `pbp_completeness` preserving the limitation and the run ends `partial`; context/order fields unsupported by complete PBP remain null/unknown.

## 6. Actual Starter Contract

The official per-game `gamesStarted` value determines actual starter. The established boxscore-list first-pitcher fallback remains only for payloads omitting that signal, matching the existing GameLog contract. Classification never reads roster role, current `Pitcher.team_id`, rotation history, or SP-06 probable identity.

If probable starter A differs from actual starter B, SP-06 history remains unchanged and SP-07 records B. Openers credited with the official start are starters; following bulk arms are relievers.

## 7. Reliever Appearance Contract

`final_pitching_appearance_versions` stores one immutable version for each official game/pitcher fact revision:

- gamePk, baseball date, canonical and MLB pitcher identity;
- official game-side `team_id_at_appearance`, opponent, side, and starter/reliever class;
- PBP-proven appearance order where available;
- integer outs, pitches, strikes, balls, batters faced, hits, runs, earned runs, walks, strikeouts, home runs, HBP, wild pitches, balks, and games finished;
- direct boxscore saves, holds, blown saves, decisions, save opportunity, inherited runners, and inherited runners scored when supplied;
- nullable entry/exit context, explicit context completeness, provenance, fingerprint/version, predecessor, and current/superseded state.

Missing optional keys stay null. They never become zero merely because the provider omitted them.

## 8. Appearance Order

Starter order is `0`. With complete final PBP, each team’s pitchers are ordered by the first official plate appearance carrying that pitcher; relievers receive `1..n`. This avoids treating boxscore array position as independently proven entrance authority. When final PBP is unavailable or incomplete, reliever order remains null.

## 9. Entry / Exit Context

For complete PBP, the first and last plate appearances credited to a pitcher support inning, half, outs, and cumulative home/away scores. Entry state uses the preceding completed play on the same inning half (or zero outs at a new half); exit state uses the final credited play. The model deliberately records context as `partial`: the v1 implementation does not claim exact base occupancy from MLB runner-movement payloads, so `entry_base_state` remains null. Direct boxscore inherited-runner totals remain separate from event-context reconstruction.

This boundary retains reliable deployment facts without inventing base/out state. SP-10 may derive leverage only from fields whose completeness permits it.

## 10. GameLog Compatibility

`GameLog` remains the current compatibility projection and is still written by its established governed writer. `final_pitching_appearance_versions` is the append-only historical truth. A complete official correction updates GameLog and appends V2; V1 remains stored. If a complete official appearance set removes an old phantom row, its immutable version is superseded and the GameLog projection is removed; its nullable `game_log_id` uses `ON DELETE SET NULL` so history survives.

## 11. Immutable Appearance Versioning

The current version is uniquely constrained per `(game_pk, pitcher_id)` through a PostgreSQL/SQLite partial unique index. Per-pitcher version numbers and predecessor links are append-only. The fact fingerprint covers line, role/team, order, and retained context—not acquisition time or source transport metadata.

Identical current facts create no new row. Changed facts append only that pitcher’s next version. A later reversion to earlier content is still a new version; fingerprints are not globally unique across history.

`final_game_versions` gives each meaningful game reconciliation one current, append-only generation. Its fingerprint covers bounded final game context plus the complete appearance projections. This provides a stable downstream generation without copying full source payloads.

## 12. Correction Contract

For V1 → V2:

1. SP-03 retains a new source observation linked to V1’s predecessor observation.
2. SP-07 locks the game, calculates source-independent canonical fact fingerprints, and invokes the existing governed GameLog correction decision.
3. Only changed appearance rows are superseded/versioned.
4. GameLog updates to the current official projection.
5. Structured correction mutations cite old/new version IDs and the exact boxscore observation.
6. One version-grain SP-09 handoff is enqueued.

An identical recheck is successful with zero versions, mutations, affected entities, or downstream jobs. A matching, completed legacy/CU `GameIngestionWorkItem` permits SP-07 to materialize the immutable baseline without falsely describing already-realized baseball facts as new mutations.

## 13. Field-Level Source Authority

| Fact | Authority | Treatment |
|---|---|---|
| Final status, official/baseball date, teams, score | MLB game-grain schedule status | Revalidated each job; schedule observation cited. |
| Pitcher participation, game side, actual starter, official line/decision totals | MLB final boxscore | Core, fail-closed, boxscore observation cited. |
| Appearance entrance sequence | Final MLB PBP | Stored only when complete and pitcher coverage is usable. |
| Entry/exit inning, half, outs, running score | Final MLB PBP | Deterministically reproduced; nullable when not proven. |
| Base occupancy at entry | UNKNOWN / REQUIRES PROOF | Schema reserved; v1 never guesses. |
| Inherited runners / scored | Direct boxscore keys | Nullable when absent; PBP derivation deferred. |
| Current roster/team | Not appearance authority | Never overwrites game-side participation. |
| Probable starter | Pregame history only | Never overwrites actual starter. |

## 14. Final Game Context

`final_game_versions` retains final score, official baseball date, teams, innings played when PBP or official team pitching totals support it, extra-inning flag when innings are known, game type, game number, and doubleheader marker. Starter and bullpen outs, pitches, batters faced, and reliever counts are reproducible sums over the current appearance facts, so SP-07 does not duplicate derived aggregates.

Official shortened finals are accepted because finality is status-based, not `innings == 9`. Extra innings is stored only from the observed final inning count. Suspended games do not reconcile until MLB again supplies authoritative Final under the same gamePk. Doubleheaders remain independent gamePk grains.

## 15. Canonical Mutation Facts

`final_game_mutations` uses the controlled vocabulary:

- `final_game_ingested`
- `starter_appearance_added`
- `reliever_appearance_added`
- `pitching_line_corrected`
- `appearance_context_corrected`
- `final_play_by_play_corrected`
- `final_game_context_corrected`

Each row has a database-unique mutation key, game/date, optional team/pitcher, old/new appearance versions, final-game generation, exact source observation, run, and bounded structured details. A pitch/event-only official PBP correction receives its own mutation and final-game generation even when the boxscore line is unchanged. These are facts for SP-09, not derived intelligence.

## 16. Affected Entity Contract

Initial authoritative ingestion affects both participating teams and every actual pitcher. A correction affects only pitchers whose canonical projection changed or disappeared and their game-side teams; a game-context-only correction affects both teams. Unchanged pitchers never receive new appearance versions and do not enter the affected set.

## 17. Queue Worker Flow

The one-shot `run_next_final_game_job` claims only `reconcile_final_game` work through SP-02. The worker creates a child `final_game_reconciliation` SyncRun when the SP-04 job still points to its completed schedule run, preserving correlation and parent lineage. It then:

1. revalidates finality and records all source attempts/observations;
2. heartbeats the fenced lease;
3. reconciles core GameLog and immutable versions under a game-scoped transaction;
4. runs optional final PBP within the same attempt without making it core authority;
5. records exact run counters/scopes/outcome;
6. enqueues one `process_canonical_impact` job when mutation facts exist;
7. returns so SP-02 settles the current lease.

The impact job dedupe is `CANONICAL_IMPACT:final-game:{gamePk}:v{final_game_version}`. Its payload schema v1 contains game/date, final-game version, mutation IDs, and source observation—not raw source payloads. SP-09 owns its worker.

## 18. CU Coexistence / Migration

Existing CU detection, reviewed write authorization, game-driven work obligations, source-order checks, postgame markers, and incremental services are unchanged. SP-07 directly wraps the same canonical writer/PBP foundation. It does not activate its queue worker in production or retire CU. During coexistence, an already-current matching CU work item results in a no-impact immutable bootstrap; later SP-09/SP-14 packages can converge operational ownership only after parity and production certification.

## 19. Failure / Partial Behavior

- Finality or boxscore fetch failure records an SP-03 failed attempt, creates no fake observation, leaves prior truth intact, and lets SP-02 retry.
- A non-Final revalidation or incomplete core boxscore writes no core canonical state.
- Pitcher identity or team-at-appearance ambiguity fails and rolls back the entire game’s core mutation.
- PBP failure records failed evidence, keeps valid core boxscore authority, leaves context unknown, and makes the SyncRun partial.
- Partial PBP never becomes authoritative context and never clears a prior complete line.
- Identical final content succeeds with zero mutation.

## 20. Concurrency / Crash Recovery

PostgreSQL `pg_advisory_xact_lock` is keyed only by gamePk, so unrelated games remain concurrent. Row locks and partial unique indexes protect current game/appearance versions. SP-02’s lease token separately fences job settlement.

If execution fails after GameLog writes but before core completion, the transaction rolls back GameLog changes, immutable versions, supersession flags, mutations, PBP rows, and downstream enqueue together. Durable SP-03 observations remain available for the retry. The retry creates one coherent version set; identical concurrent workers converge to one game version and one mutation set.

## 21. Database / Index Design

Migration `e8b4c2d6f1a9` is additive and creates:

- `final_game_versions`: one current game generation plus predecessor/source/run lineage;
- `final_pitching_appearance_versions`: per-pitcher immutable lines and optional context;
- `final_game_mutations`: compact SP-09 mutation facts.

Indexes support current game/appearance lookup, game/team/pitcher date history, appearance order, source observation provenance, and run-scoped mutations. No JSON payload column is indexed. Existing rows are neither rewritten nor guessed; SP-13 owns historical backfill. Downgrade removes only SP-07 tables.

## 22. Explicit Non-Goals

- No production scheduler, Render, or GitHub Actions change.
- No live/provisional ingestion or adaptive polling change.
- No new MLB endpoint family or Baseball Savant acquisition.
- No workload, rest, Team State, arm read, role, deployment, performance, rotation-transfer, matchup, Tonight, read-model, or publication execution.
- No frontend/API/public semantic change.
- No historical season backfill and no legacy retirement.

## 23. SP-08 / SP-09 / SP-10 / SP-13 Handoffs

**SP-08:** attach provisional live observations to game/pitcher identity; SP-07 remains the only final authority and may confirm or supersede provisional facts.

**SP-09:** implement the `process_canonical_impact` worker, consume mutation IDs, and map exact affected entities to bounded derived obligations. It must not reinterpret source authority.

**SP-10:** derive arbitrary workload, deployment, performance, inherited-runner, and rotation-transfer context from current immutable appearances and only sufficiently complete PBP context.

**SP-13:** backfill pre-SP-07 history, reconcile legacy rows without proven game work evidence, generalize correction/repair controls, and prove base-state reconstruction before populating reserved entry-base fields.

## 24. Acceptance Checklist

- [x] SP-04 `reconcile_final_game` has a canonical one-shot worker.
- [x] Official Final is refetched and revalidated.
- [x] Finality, boxscore, and PBP attempts use immutable SP-03 evidence.
- [x] Actual starters and game-side appearance teams are authoritative.
- [x] GameLog remains the current compatibility projection.
- [x] Immutable V1/V2 appearance and game versions preserve corrections.
- [x] Identical reconciliation is zero-mutation success.
- [x] Only changed pitcher facts version on correction.
- [x] Complete source removal supersedes history without losing it.
- [x] PBP failure degrades independently and never creates zero facts.
- [x] PBP-proven order/context is retained; unsupported base state remains unknown.
- [x] Exact affected entities and structured mutation facts are durable.
- [x] One bounded, deduplicated SP-09 handoff is produced.
- [x] Game-scoped concurrency and transactional crash recovery are tested.
- [x] Doubleheader, extra-inning, shortened-final, and baseball-date contracts do not assume UTC completion or nine innings.
- [x] No later-package behavior or public surface is activated.

## Appendix A — Natural Read-Only MLB Proof

Accessed 2026-09-09. These were read-only requests; no production BaseballOS state was mutated.

- [MLB schedule for 2026-09-08](https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-09-08&hydrate=team) returned 15 official Final games. Late UTC starts such as gamePk `823250` remained on MLB official/baseball date `2026-09-08`, confirming that completion timestamp cannot own baseball date.
- [MLB boxscore for gamePk 824063](https://statsapi.mlb.com/api/v1/game/824063/boxscore) identified actual starters Corbin Burnes (`669203`) and Michael Wacha (`608379`), twelve relievers, official per-pitcher outs/pitches/BF, game-side pitcher arrays, and populated holds, blown saves, and inherited-runner keys.
- [MLB final PBP for gamePk 824063](https://statsapi.mlb.com/api/v1/game/824063/playByPlay) returned 93 completed plays through inning 11. The repository’s existing parser projected 14 pitching appearances, 12 relievers, both official game-side teams, 14 known pitch totals, and 66 combined recorded outs.

The endpoints are official public observations, not a documented service-level guarantee. Source correction timing, event-level base-state reconstruction, and unusual suspended/resumed payload variants remain future proof obligations.
