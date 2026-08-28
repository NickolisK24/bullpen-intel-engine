# CU-01R — Continuous Reliever Ingestion Blocker Remediation

## Decision

**ACCEPT CU-01.**

CU-01R removes the three correctness blockers recorded by CU-01P and passes the
exact original 15-game proof set. The game-driven lane remains shadow/write
proof infrastructure only. It does not publish, become authoritative, poll,
enqueue work, rebuild read models, invalidate caches, or alter frontend or
workflow behavior.

## 1–4. Repository checkpoints

| Item | Value |
|---|---|
| Branch | `feat/continuous-reliever-ingestion` |
| Starting HEAD | `8be2d6afe47906b4be2155238cc07142fdfaa15e` |
| CU-01 checkpoint | `1bf3978663d2ef0fb562cc49e2b1dea411d03214` |
| CU-01P checkpoint | `8be2d6afe47906b4be2155238cc07142fdfaa15e` |
| Final implementation HEAD | Recorded in the delivery closeout after the commit is created |
| `origin/main` | `90de9d83b75b20e19378a714c107f73139aa8bb3` |
| Divergence before CU-01R commit | Feature branch 2 commits ahead, 6 behind |

`origin/main` was fetched for read-only relationship evidence. It was not
merged or rebased. The named CU-01 and CU-01P commits remain unchanged.

The pre-existing untracked
`BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` was not read, edited, staged,
or removed.

## 5–7. Original blockers, causes, and remediations

### Blocker 1 — no-op replay emitted affected entities

Root cause: `build_game_impact()` derived affected pitchers and teams by
scanning every observed relief appearance. `game_driven_ingestion` invoked it
before reconciliation and folded those observed entities into the run report.
Canonical reconciliation could correctly return all rows unchanged while the
impact report still described the whole game as affected.

Remediation:

- GameLog impact now consumes canonical row plans and accepts only `insert` or
  `update` actions.
- Pitch reconciliation returns the pitcher and historical fielding-team IDs
  associated with inserted, updated, or superseded pitch rows.
- The impact service filters those mutation IDs to relief appearances and maps
  teams from extracted game-side appearance ownership.
- Shadow mode derives projected impact from the canonical planner; write mode
  derives observed impact from the canonical writer and normalized-pitch
  reconciliation result.
- Observed entities remain separately visible and do not imply invalidation.

### Blocker 2 — last-observation-wins pitch correction

Root cause: the normalized pitch reconciler compared content fingerprints but
unconditionally applied any differing payload received later. MLB's official
`/game/{gamePk}/playByPlay` response contains gameplay event times but no
monotonic feed revision, update timestamp, or correction sequence. The existing
`source_revision` and `pitch_fingerprint` values are content hashes; hashes
establish identity, not order. Local acquisition time cannot establish MLB
authority order.

Remediation: a persisted fail-closed partial order now gates PBP reconciliation
before any play or pitch mutation:

- No existing canonical observation: accept as the initial observation.
- Same content fingerprint: classify as identical and perform no canonical
  pitch mutation.
- Different content with the same accepted source authority and a greater
  governed observation sequence: accept as newer and reconcile.
- Lower sequence: reject as stale.
- Equal sequence with different content: reject as ambiguous.
- Missing sequence on either side of differing content: reject as ambiguous.
- Different/weaker source authority: reject before content can supersede the
  accepted authoritative source.

The ordinary MLB acquisition path does not fabricate a sequence. Therefore a
differing ordinary re-fetch whose upstream order is unknowable fails closed.
The controlled proof uses an explicit capture-manifest sequence and is labeled
controlled evidence, not a naturally observed MLB revision.

### Blocker 3 — plate-appearance result copied to every pitch

Root cause: pitch normalization read `play.result.eventType`, which is a
plate-appearance result, inside the loop over every `playEvent`. As a result,
all pitches inherited the eventual strikeout, walk, out, or hit result.

Remediation:

- `batted_ball_event_type` is populated from the plate-appearance result only
  when that pitch event's `details.isInPlay` is explicitly `true`.
- Event-owned `hitData` fields—trajectory, hardness, launch speed/angle,
  distance, and location—continue to come only from that individual pitch
  event's `hitData` object.
- Non-owning pitches retain nulls. No empty strings, zeroes, or fabricated
  categories are introduced.

## 8. Files changed

- `backend/models/play_by_play_foundation.py`
- `backend/migrations/versions/b4e7c9d2a1f6_add_pbp_observation_order.py`
- `backend/services/play_by_play_foundation.py`
- `backend/services/continuous_reliever_ingestion.py`
- `backend/services/game_driven_ingestion.py`
- `backend/services/source_correction_policies.py`
- `backend/scripts/run_cu01p_proof.py`
- `backend/tests/test_continuous_reliever_ingestion.py`
- `backend/tests/test_phase0e_exit_docs.py`
- `docs/current/CU_01R_CONTINUOUS_RELIEVER_INGESTION_REMEDIATION.md`

No frontend, workflow, publication, Team State, Team Board, League, Matchup,
Tonight, cache, polling, queue, or event-bus file changed.

## 9. Schema changes

Migration `b4e7c9d2a1f6`, down-revision `f1c2d3e4a5b6`, adds two nullable fields
to `play_by_play_processed_games`:

- `accepted_pitch_observation_sequence INTEGER NULL`
- `accepted_pitch_source_authority VARCHAR(100) NULL`

Null is intentional for observations that have no defensible upstream order.
The accepted content remains identified by the existing persisted
`pitch_fingerprint`. Upgrade, downgrade, and re-upgrade passed in all three
disposable proof databases. Flask-Migrate reports exactly one head:
`b4e7c9d2a1f6`.

The migration does not rewrite existing pitch or publication rows. Existing
markers begin with unknown ordering metadata and therefore fail closed on a
differing unordered replay.

## 10–13. Canonical contracts

### Observation-order contract

The order relation is `(source authority, governed observation sequence)` and
is evaluated only after source authority equality. Content fingerprints decide
identical versus different. They never decide older versus newer. Local
acquisition timestamps are excluded from ordering.

Unknown/incomparable order is non-destructive: canonical facts remain intact,
the result reports `ambiguous_rejected`, mutation counts are zero, affected
entities are empty, and publication remains false.

### Persisted order evidence

`PlayByPlayProcessedGame` persists the accepted sequence, accepted source
authority, and accepted pitch fingerprint. These values survive session,
engine, and Flask application reconstruction. Stale input is observable through
the structured result as `stale_rejected`.

### Mutation-scoped affected entities

“Affected” means at least one CU-01-supported canonical mutation occurred for
the reliever. Unchanged GameLogs and pitch events contribute nothing. Team
ownership comes from the game's extracted canonical side/appearance ownership,
not mutable `Pitcher.team_id`. The opposing club is included only if one of its
own relief facts changed.

### Batted-ball mapping

`play.result` is plate-appearance scope. `play.playEvents[n].details` and
`hitData` are event scope. A pitch owns the normalized plate-appearance outcome
only when `details.isInPlay is true`; related tracking remains scoped to that
event's `hitData`.

## 14. Focused tests

The CU-01R coverage proves:

1. First ingestion emits both clubs' changed relievers.
2. Exact second ingestion emits no affected pitcher or team.
3. Session restart and exact third ingestion emit none.
4. A one-reliever GameLog correction emits only that reliever.
5. Its affected team remains the historical game-side owner after current
   `Pitcher.team_id` is changed.
6. Unrelated pitchers and teams are absent.
7. Optional PBP failure on an unchanged replay creates no pitch-level impact.
8. A → identical A → newer B → older A classifications are durable.
9. Older A remains rejected after restart.
10. Different/weaker authority and ambiguous ordering fail closed.
11. The B fingerprint remains canonical after stale replay.
12. Multi-pitch field-out and home-run shapes attribute batted-ball facts only
    to the owning pitch; strikeout, walk, and HBP PAs do not inherit outcomes.
13. Corrected normalization remains idempotent.

Focused CU-01/CU-01P/CU-01R result: **16 passed**.

## 15. Exact 15-game CU-01P replay

Official source capture:

- Captured: `2026-08-28T16:33:19.766716+00:00`
- Capture fingerprint:
  `632dd0f5dfe7b413570617eb8f992dcf2450b2abdc2311a06e3b095e72376061`
- Environment: three disposable local SQLite databases
- Production access: false
- Raw source retention: temporary process/filesystem scope only

The exact game list was retained:

| gamePk | Date | Expected/canonical relievers | Pitch events | GameLog first-pass action | Workload values | Result |
|---:|---|---:|---:|---|---:|---|
| 823826 | 2026-08-25 | 12 / 12 | 365 | 14 insert | 72 | PASS |
| 823989 | 2026-08-25 | 11 / 11 | 395 | 13 insert | 66 | PASS |
| 823180 | 2026-08-26 | 9 / 9 | 356 | 11 insert | 54 | PASS |
| 824878 | 2026-08-26 | 9 / 9 | 343 | 11 insert | 54 | PASS |
| 823016 | 2026-08-25 | 6 / 6 | 310 | 8 insert | 36 | PASS |
| 822692 | 2026-08-26 | 6 / 6 | 303 | 8 insert | 36 | PASS |
| 822771 | 2026-08-27 | 7 / 7 | 309 | 9 insert | 42 | PASS |
| 823014 | 2026-08-27 | 7 / 7 | 290 | 9 insert | 42 | PASS |
| 823825 | 2026-08-26 | 5 / 5 | 271 | 7 insert | 30 | PASS |
| 822773 | 2026-08-25 | 9 / 9 | 323 | 11 insert | 54 | PASS |
| 823585 | 2026-08-25 | 8 / 8 | 314 | 10 insert | 48 | PASS |
| 823505 | 2026-08-25 | 8 / 8 | 325 | 10 insert | 48 | PASS |
| 824963 | 2026-08-26 | 5 / 5 | 242 | 7 insert | 30 | PASS |
| 822694 | 2026-08-27 | 7 / 7 | 326 | 9 insert | 42 | PASS |
| 823179 | 2026-08-27 | 7 / 7 | 281 | 9 insert | 42 | PASS |

Totals remained the CU-01P baseline: 15 games, 146 canonical pitching
appearances, 116 reliever appearances, 4,753 pitch events, and 2,239 reliever
pitch events. All finality, line coverage, historical ownership, null handling,
affected-entity, optional-source, publication, and history checks passed.

## 16. Workload parity

The authoritative scheduled/postgame baseline contained 146 GameLogs with
fingerprint
`a4dd34416a28b7c5f75ed64fe9eaeba3a737e4335bc7b1da5a1413f96a709fa3`.

All **696 / 696** comparable reliever workload inputs matched:

- `game_date`
- `innings_pitched_outs`
- `pitches_thrown`
- `batters_faced`
- `games_started`
- `appearance_team_id`

No workload parity expectation was changed to obtain the pass.

## 17–18. No-op and restart results

Five-game replay set: `823826`, `823989`, `823180`, `823016`, `822694`.

Second pass:

- GameLog mutations: 0
- Pitch mutations: 0
- Affected pitchers: `[]`
- Affected teams: `[]`
- GameLogs before/after: 55 / 55
- Pitches before/after: 1,752 / 1,752
- Fingerprint before/after:
  `d2e219ff119a23107e81ef3f4f13634a8d4a926a3adc8e95b53a27b692bdffc8`

After engine disposal and new Flask application construction, third pass:

- GameLog mutations: 0
- Pitch mutations: 0
- Affected pitchers: `[]`
- Affected teams: `[]`
- Fingerprint before/after:
  `5ac0b72c88503af662ae40ef6956f51fecd9facb99964988da186be5e111b06b`

The third-pass fingerprint differs from the earlier replay fingerprint only
because the controlled correction proof intentionally superseded one pitch
between those phases. It remained stable across the restart replay itself.

## 19. Older-after-newer controlled proof

Game `823826`, using captured real MLB payload shape:

1. A was associated with governed sequence 1; identical reconciliation made
   zero mutations.
2. Controlled B, sequence 2, changed pitch `(33, 2)` and removed `(33, 3)`.
3. B was classified `newer_accepted`: 1 update, 1 supersession, 363 unchanged.
4. A, sequence 1, was classified `stale_rejected`: zero mutations and zero
   affected entities.
5. B replay was identical: 364 unchanged and zero mutations.
6. After application/engine restart, A was again `stale_rejected` with zero
   mutations and the same canonical fingerprint:
   `21746c2d13a5763f18ced18d79376b956bb42b5b29148ba9fe2e41a20e9a96e8`.
7. Neighboring pitch fingerprints remained unchanged.

This is **controlled replay proof**, not a naturally observed MLB revision.
The MLB endpoint did not expose sufficient ordering metadata for a natural
older/newer proof.

## 20. Batted-ball attribution proof

Across 4,753 real pitch events:

- In-play pitches: 846
- Pitches with `batted_ball_event_type`: 846
- Non-in-play pitches with `batted_ball_event_type`: **0**
- Launch speed present: 844; null: 3,909
- Launch angle present: 844; null: 3,909

Manual sample, game `822692`, at-bat 0:

| Event | Call | In play | Event type | Launch speed | Launch angle |
|---:|---|---|---|---:|---:|
| 3 | Called Strike | false | null | null | null |
| 4 | In play, no out | true | double | 60.7 | 24.0 |

The earlier pitch no longer inherits the eventual double.

## 21. Optional PBP proof

Controlled PBP timeout for game `822694`:

- Core run status: complete
- Canonical GameLogs: 9
- Changed relievers: 7
- Historically affected teams: 115 and 120
- Optional PBP status: incomplete / `play_by_play_fetch_failed`
- Pitch rows: 0
- Publication affected: false
- Result: PASS, partial/nonblocking

## 22–23. Publication and historical safety

Before/after row counts and full-row fingerprints were identical for:

- dashboard snapshots, including one published historical sentinel
- intelligence surface snapshots
- Tonight intelligence snapshots
- share artifacts and all share-artifact child/audit tables
- progressive team publications

No publication pointer, What Changed record, public read model, frontend
payload, or cache path was invoked. `publication_affected` remained false.

Historical `appearance_team_id` values remained stable when current
`Pitcher.team_id` was changed to an unrelated team. Pedro Pagés remained a
catcher, Jorbit Vivas a third baseman, and Myles Straw a center fielder; their
pitching appearances did not turn them into current bullpen pitchers.

## 24. Validation and broader diagnostic

Passing validation:

- Focused CU-01/CU-01P/CU-01R: **16 passed**
- Relevant ingestion/finality/authority/provenance/PBP/shadow/postgame/
  snapshot/governance suite: **335 passed, 1 skipped**
- CI shard verification: **PASS** — 392 files and 8,966 node IDs assigned
  exactly once
- Python compilation: **PASS**
- Proof migration upgrade/downgrade/re-upgrade: **PASS** in three databases
- Single Flask-Migrate head: **PASS**, `b4e7c9d2a1f6`
- Diff whitespace check: **PASS**
- Exact 15-game replay verdict: **PASS**

Broader diagnostic context:

- A first environment-unqualified run completed with 8,760 passed, 73 skipped,
  101 failed, and 32 errors. Isolation showed the 32 trusted-board errors were
  cascading fixture/environment failures; that test file passed in the
  isolated cluster.
- Seventeen isolated share-artifact failures require a local `DATABASE_URL`
  when constructing the full test app. The `/proc` unwritable-path assertion is
  a Windows path-semantics mismatch.
- A second broad run was started with an explicit disposable local SQLite URL
  for comparability, but exceeded the 420-second command limit before pytest
  emitted its final summary. It is therefore **incomplete**, not a pass.
- The recorded CU-01P aggregate remains 8,829 passed, 73 skipped, 61 failed.
  CU-01R adds three focused tests; no CU-01R, relevant-suite, migration, or
  proof test failed. Existing Windows shell, source-hash/freeze, order-sensitive
  baseline, and the seven unintegrated performance-freshness fixture failures
  remain outside this slice.

No unrelated broad-suite failure was changed or dismissed as passing.

## 25. Remaining known gaps and risks

- MLB PBP does not provide a proven total correction order. Natural MLB
  older/newer revision behavior remains unproven.
- Differing content without governed sequence evidence now fails closed. An
  operator/source-specific ordered capture is required to accept such a
  correction through this lane.
- Existing markers migrated with null ordering metadata retain unknown order;
  unordered differing content will not rewrite them.
- Proof used isolated local SQLite databases, not production data. Historical
  safety combines isolated full-row sentinels with focused repository tests.
- The broad backend aggregate did not complete under the environment-corrected
  retry's time limit; relevant contract coverage and exact proof are complete.
- The feature branch still lacks six `origin/main` commits, including the known
  performance-freshness fixture alignment.

## 26. Proven claims

- Exact no-op replay produces zero canonical mutation and zero affected
  pitchers/teams, including after restart.
- A controlled demonstrably older PBP observation cannot overwrite a newer
  accepted observation, before or after restart.
- A governed newer observation can correct/supersede pitch facts and identifies
  only the relevant reliever/team.
- Batted-ball outcomes are limited to the owning pitch event.
- The exact 15-game CU-01P dataset retains all 696 workload comparisons.
- Historical game-side ownership and null semantics remain correct.
- Optional PBP remains nonblocking.
- Position-player pitching does not corrupt current roster identity.
- No CU-01/CU-01R path publishes or mutates the isolated historical sentinels.

## 27. Unproven claims

- A naturally observed MLB PBP correction with an upstream-issued monotonic
  revision was not available and is not claimed.
- Production-database execution and production-history comparison were not
  performed.
- CU-01 is not proven as production authority and is not promoted by this work.
- Continuous acquisition, polling, downstream incremental recomputation, and
  publication are not part of this evidence.

## 28. Final verdict

**ACCEPT CU-01.**

All twelve CU-01R acceptance conditions are supported by focused tests and the
exact real-game proof replay. Acceptance applies to the non-authoritative
ingestion foundation only.

## 29. Recommended integration action

After this remediation commit is reviewed, merge current `origin/main` into
`feat/continuous-reliever-ingestion` with a normal merge commit. Do not rebase:
the normal merge preserves the named CU-01 and CU-01P audit SHAs. Resolve the
migration-head guard and CI-manifest context by retaining both branches'
intent, then rerun the focused 16 tests, relevant 335-test suite, migration
checks, and exact 15-game proof.

No integration was performed during CU-01R.

## 30. Exact next slice

The next repository slice is **branch integration and post-merge validation of
CU-01 only**: merge `origin/main` into the feature branch with a normal merge
commit, resolve only direct conflicts, and rerun the accepted proof. Do not
begin CU-02, continuous polling, authority migration, downstream publication,
or cache invalidation as part of that slice.
