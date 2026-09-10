# CU-01P — Continuous Reliever Ingestion Production Proof

**Verdict:** BLOCKED
**Acceptance statement supported:** No
**Proof execution date:** 2026-08-28
**Official source capture:** 2026-08-28T11:18:41.848077-04:00
**Official source fingerprint:** `7308dc8fde66bd3206c3de175ca34383d1c806e203e00ce4a0130acce4c8b761`

## 1. Branch, commits, and remote relationship

- Branch: `feat/continuous-reliever-ingestion`
- Recorded CU-01 starting SHA: `74addba25f6113b7fb9ca943ee4e2b5a67bd6351`
- CU-01 commit and proof execution HEAD: `1bf3978663d2ef0fb562cc49e2b1dea411d03214`
- At proof start, `origin/main` was `90de9d83b75b20e19378a714c107f73139aa8bb3`.
- Relationship at proof start: this branch was one commit ahead and six commits behind `origin/main`.
- No merge, rebase, authority change, workflow change, or production deployment was performed.
- The pre-existing untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` remained untouched.

The proof tooling and this report are the only CU-01P changes after the named
execution HEAD. The final local commit is reported in the task closeout because
a commit cannot contain its own SHA.

## 2. Proof environment

The proof runner used three disposable local SQLite files under an OS temporary
directory:

1. an authoritative-postgame baseline database;
2. a CU-01 game-driven database;
3. an optional-PBP-failure database.

Official MLB schedule, box-score, linescore, play-by-play, and three player
identity responses were acquired through the existing resilient MLB client.
Payloads existed only for the lifetime of the proof process and were not stored
in the repository or a production database. Subsequent passes used exact deep
copies of that captured official evidence, preventing a changing network
response from invalidating replay comparisons.

`APP_ENV=test`, `AUTO_SYNC=false`, a local SQLite URL, and
`SHARE_ARTIFACT_AUTOGENERATION=false` were set explicitly. No production
credential, production database, public endpoint, publication pointer, cache,
workflow, or frontend payload was in scope.

The current authoritative comparison was produced in its own database by
calling `process_completed_game_for_postgame_refresh` for the same 15 official
games. It created 146 canonical pitcher/game rows with baseline fingerprint
`a4dd34416a28b7c5f75ed64fe9eaeba3a737e4335bc7b1da5a1413f96a709fa3`.

## 3. Migration status

Each of the three disposable databases independently completed:

`parent-shaped fixture -> CU-01 upgrade -> CU-01 downgrade -> CU-01 re-upgrade`

Observed results in all three databases:

- `game_pitch_events` appeared on upgrade, disappeared on downgrade, and
  reappeared on re-upgrade;
- `GameLog.hit_batters`, `wild_pitches`, and source revision columns followed
  the same cycle;
- the processed-game pitch marker columns followed the same cycle;
- the final recorded Alembic head was exactly `f1c2d3e4a5b6`;
- no production or historical database was accessed.

This deliberately avoided the pre-existing full SQLite chain blocker in
`c7f1b408d93a`; that unrelated migration was not changed.

## 4. Selected real-game dataset

All 15 games were official finals from 2026-08-25 through 2026-08-27. The set
was selected before write execution from a bounded three-day schedule scan.

| gamePk | Date | Matchup | Selection reason |
|---:|---|---|---|
| 823826 | 2026-08-25 | Boston Red Sox @ Miami Marlins | 11 innings; 12 relievers; blown save; inherited runners; wild pitch |
| 823989 | 2026-08-25 | Cleveland Guardians @ Los Angeles Angels | 10 innings; 11 relievers; save, hold, blown save, and hit batter |
| 823180 | 2026-08-26 | Cincinnati Reds @ San Francisco Giants | Nine relievers; save, hold, blown save, hit batter, and wild pitch |
| 824878 | 2026-08-26 | Los Angeles Dodgers @ Atlanta Braves | Nine relievers; multi-inning and consecutive-day arms |
| 823016 | 2026-08-25 | Baltimore Orioles @ St. Louis Cardinals | Position player Pedro Pagés pitched; multi-inning relief |
| 822692 | 2026-08-26 | Colorado Rockies @ Washington Nationals | Position player Jorbit Vivas pitched; inherited runners and hit batters |
| 822771 | 2026-08-27 | Kansas City Royals @ Toronto Blue Jays | Position player Myles Straw pitched; multi-inning relief |
| 823014 | 2026-08-27 | Baltimore Orioles @ St. Louis Cardinals | Seven relievers; consecutive-day arms; save, hold, and wild pitch |
| 823825 | 2026-08-26 | Boston Red Sox @ Miami Marlins | Consecutive-day relievers; hold; multi-inning relief |
| 822773 | 2026-08-25 | Kansas City Royals @ Toronto Blue Jays | Nine relievers; save, hold, hit batter, and wild pitch |
| 823585 | 2026-08-25 | Milwaukee Brewers @ New York Mets | 10 innings; blown save; hold; multi-inning relief |
| 823505 | 2026-08-25 | Houston Astros @ New York Yankees | Save and blown save; inherited runners |
| 824963 | 2026-08-26 | Minnesota Twins @ Athletics | Save, hold, blown save, and consecutive-day reliever |
| 822694 | 2026-08-27 | Colorado Rockies @ Washington Nationals | Recent normal nine-inning game with seven relievers |
| 823179 | 2026-08-27 | Arizona Diamondbacks @ San Francisco Giants | Seven relievers; consecutive-day and multi-inning arms |

Both left- and right-handed relievers appeared in the dataset. Fourteen games
contained both hands; game 823179's selected relievers were right-handed in the
official PBP matchups.

No naturally partial pitch-tracking game was found in this bounded set. No
naturally observed MLB correction with a source revision sequence was found.
Those conditions are not promoted to PASS.

## 5. Per-game proof results

Every row below passed canonical finality, expected-versus-stored reliever
count, game-side ownership, presence-aware line persistence, initial affected
entity resolution, six-field workload parity, optional PBP completion, and
`publication_affected=false`.

`GameLog I/U/N` includes starters because the canonical writer persists every
pitching appearance. `Pitch I/U/N/S` is insert/update/unchanged/superseded.

| gamePk | Relievers expected/stored | GameLog I/U/N | Pitches | Pitch I/U/N/S | Affected pitchers | Affected teams | Workload parity | PBP |
|---:|---:|---:|---:|---:|---:|---|---|---|
| 823826 | 12/12 | 14/0/0 | 365 | 365/0/0/0 | 12 | 111, 146 | PASS | PASS |
| 823989 | 11/11 | 13/0/0 | 395 | 395/0/0/0 | 11 | 108, 114 | PASS | PASS |
| 823180 | 9/9 | 11/0/0 | 356 | 356/0/0/0 | 9 | 113, 137 | PASS | PASS |
| 824878 | 9/9 | 11/0/0 | 343 | 343/0/0/0 | 9 | 119, 144 | PASS | PASS |
| 823016 | 6/6 | 8/0/0 | 310 | 310/0/0/0 | 6 | 110, 138 | PASS | PASS |
| 822692 | 6/6 | 8/0/0 | 303 | 303/0/0/0 | 6 | 115, 120 | PASS | PASS |
| 822771 | 7/7 | 9/0/0 | 309 | 309/0/0/0 | 7 | 118, 141 | PASS | PASS |
| 823014 | 7/7 | 9/0/0 | 290 | 290/0/0/0 | 7 | 110, 138 | PASS | PASS |
| 823825 | 5/5 | 7/0/0 | 271 | 271/0/0/0 | 5 | 111, 146 | PASS | PASS |
| 822773 | 9/9 | 11/0/0 | 323 | 323/0/0/0 | 9 | 118, 141 | PASS | PASS |
| 823585 | 8/8 | 10/0/0 | 314 | 314/0/0/0 | 8 | 121, 158 | PASS | PASS |
| 823505 | 8/8 | 10/0/0 | 325 | 325/0/0/0 | 8 | 117, 147 | PASS | PASS |
| 824963 | 5/5 | 7/0/0 | 242 | 242/0/0/0 | 5 | 133, 142 | PASS | PASS |
| 822694 | 7/7 | 9/0/0 | 326 | 326/0/0/0 | 7 | 115, 120 | PASS | PASS |
| 823179 | 7/7 | 9/0/0 | 281 | 281/0/0/0 | 7 | 109, 137 | PASS | PASS |

Totals: 146 pitching appearances, 116 reliever appearances, 4,753 pitch
events, 15 processed-game markers, zero initial workload-parity differences,
and zero initial unrelated-team emissions.

## 6. Workload parity

For each of the 116 official reliever appearances, CU-01 was compared with the
separate authoritative-postgame database on:

- appearance date;
- canonical outs;
- pitches;
- batters faced;
- starter/reliever signal;
- historical appearance-team ownership.

All 696 comparable values matched. Classification: **PASS** for these legacy
equivalent fields.

Additional CU-01 canonical fields were hit batters, wild pitches, first-write
source authority/endpoint/revision, and normalized pitch data. Decimal innings,
fatigue, rest/availability, Team State, Team Board, League, Matchup, Tonight,
and Why explanations remained derived or out of scope.

## 7. Idempotency replay

Games 823826, 823989, 823180, 823016, and 822694 were replayed after their first
write.

Observed before and after the second pass:

- GameLog rows: 55 -> 55
- pitch rows/current pitch rows: 1,752/1,752 -> 1,752/1,752
- processed-game markers: 5 -> 5
- fact fingerprint:
  `88d72fffa1ecff99ab78780e210e7534ba9c91424ef1a0a2bccb858c72b84c05`
  before and after
- GameLog mutations: 0
- pitch inserts/updates/supersessions: 0

Canonical replay idempotency therefore passed. However, the unchanged replay
still emitted 45 `affected_pitcher_mlb_ids` and 10 `affected_team_ids`. These
entities belonged to the processed games, so they were not unrelated teams,
but no canonical fact changed. The interface currently means “relievers/teams
present in this processed game,” not “entities whose canonical facts changed.”
That violates the CU-01P no-op affected-entity requirement and is a blocker.

## 8. Application restart

After the controlled correction was restored to the official source state, the
proof removed the active SQLAlchemy session, disposed the SQLite engine, built
a new Flask application, reconnected to the same durable database, and ran the
same five-game reviewed shadow/write sequence.

- GameLog mutations after restart: 0
- pitch inserts/updates/supersessions after restart: 0
- rows and fingerprints before/after the third pass: identical
- duplicate detection and marker interpretation required no application-memory
  state

Classification: **PASS** for application restart semantics. This was an
application/engine restart in one operator process, not a host reboot.

## 9. Correction and supersession

No natural MLB correction sequence was observed. A controlled proof used the
captured official game 823826 payload:

- changed pitch natural key: `(atBatIndex=33, playEventIndex=2)`;
- removed pitch natural key: `(33, 3)`;
- controlled apply: 1 update, 1 supersession, 363 unchanged;
- restore official payload: 2 updates, 363 unchanged;
- identical replay after restore: 365 unchanged and zero mutations;
- all neighboring pitch fingerprints remained unchanged.

This proves scoped correction, supersession, restoration, identical replay,
and neighboring-event isolation.

It does **not** prove stale-revision rejection. MLB supplies observed PBP
content but no monotonic revision identifier, and the current reconciler is
last-observation-wins. An older captured payload processed later can be applied
as another correction. Classification: **CONTROLLED PARTIAL**, and this is a
CU-01P blocker.

## 10. Null and source-coverage audit

| Canonical field/domain | Present | Null | Coverage |
|---|---:|---:|---:|
| start velocity | 4,753 | 0 | 100% |
| spin rate | 4,753 | 0 | 100% |
| horizontal/vertical movement | 4,753 | 0 | 100% |
| release X/Y/Z | 4,753 | 0 | 100% |
| extension | 4,753 | 0 | 100% |
| zone | 4,753 | 0 | 100% |
| plate X/Z | 4,753 | 0 | 100% |
| pitch type | 4,753 | 0 | 100% |
| pitch call/result code | 4,753 | 0 | 100% |
| launch speed | 844 | 3,909 | 17.76% |
| launch angle | 844 | 3,909 | 17.76% |
| hit batters, reliever appearances | 116 | 0 | 100% |
| wild pitches, reliever appearances | 116 | 0 | 100% |
| inherited runners, reliever appearances | 116 | 0 | 100% |
| inherited runners scored, reliever appearances | 116 | 0 | 100% |

Zeros in the four appearance fields above were explicit official values, not
substitutions for missing data. Launch facts correctly remained null for most
pitches. Naturally partial tracking was not observed, so behavior against a
real partial-tracking game remains unproven.

The audit also exposed a canonical-scope problem: only 846 pitches were marked
in play, but `batted_ball_event_type` was populated on all 4,753 pitches,
including 3,907 non-in-play pitches. The normalizer copies the eventual plate
appearance result to every pitch in that plate appearance. That is not a valid
pitch-level batted-ball fact. Classification: **FAIL**, and this is a CU-01P
blocker.

## 11. Pitch volume and storage

- games: 15
- reliever appearances: 116
- all pitch events: 4,753
- reliever pitch events: 2,239
- average all pitch events per game: 316.87
- average reliever pitch events per reliever appearance: 19.30
- disposable SQLite allocation before ingestion: 917,504 bytes
- allocation after ingestion and proof metadata: 5,046,272 bytes
- approximate growth: 4,128,768 bytes (about 3.94 MiB)

The growth figure includes canonical appearances, identities, PBP plate-
appearance rows, pitch rows, work items, markers, dead-letter/proof evidence,
and SQLite page overhead; it is not a pure pitch-table measurement.

Indexes exercised/present:

- `ix_game_pitch_events_game_order`
- `ix_game_pitch_events_pitcher_date`
- `ix_game_pitch_events_team_date`

No obvious bounded-query failure occurred. Storage volume is material but does
not justify optimization from this sample alone.

## 12. Affected-entity and position-player proof

Initial processing identified exactly every official reliever and exactly the
game-side teams with relief appearances. No unrelated team appeared.

For a controlled current-team mutation, one reliever's mutable
`Pitcher.team_id` was set to `999999`. Historical `GameLog.appearance_team_id`
remained unchanged, and `999999` did not enter the affected-team result.
Classification: **PASS** for historical ownership.

Three official current non-pitcher identities were seeded from MLB people
evidence before processing their real pitching appearances:

| Player | Current position before/after | Current team preserved | Appearance team stored |
|---|---|---|---|
| Pedro Pagés | C / C | Yes | 138 |
| Jorbit Vivas | 3B / 3B | Yes | 120 |
| Myles Straw | CF / CF | Yes | 141 |

Their pitching GameLogs did not rewrite current roster position or team.
Classification: **PASS** for the tested existing-identity path. The missing
local-identity position-player path was not separately production-proven.

The no-op replay emission described in section 7 remains a blocker: initial
entity accuracy is correct, but mutation-scoped affected entities are not.

## 13. Optional PBP failure

A separate disposable database processed game 822694 with its official final
box score while the existing client seam raised a controlled PBP timeout.

- overall game-driven run: complete
- canonical GameLogs: 9
- affected relievers: 7
- affected teams: 115 and 120
- PBP marker: `incomplete`
- reason: `play_by_play_fetch_failed`
- pitch rows: 0
- `publication_affected`: false

Classification: **PASS**. The optional source failed observably and
nonblockingly without weakening core finality or pitching-line persistence.

## 14. Publication and historical safety

Before CU processing, the proof database stored one published dashboard
sentinel. Before/after row counts and full-row fingerprints were identical for:

- dashboard snapshots: 1 -> 1, sentinel fingerprint unchanged;
- intelligence-surface snapshots: 0 -> 0;
- Tonight snapshots: 0 -> 0;
- share artifacts/assets/evidence/relations/audits: 0 -> 0;
- progressive team publications: 0 -> 0.

No workflow, cache, Team State, Team Board, League, Matchup, Tonight, What
Changed, share-artifact, frontend, or publication function was invoked by the
proof runner or CU game-driven call. `publication_affected` was false in every
per-game result and in the optional failure result.

Classification: **PASS in the isolated environment**. This is not a claim that
production historical tables were queried. Existing snapshot/history tests
supplement the isolated sentinel evidence.

## 15. Tests and validation

Executed before proof work:

- `tests/test_continuous_reliever_ingestion.py`: 7 passed.

Executed after proof tooling was added:

- `tests/test_cu01p_proof.py` plus CU-01 tests: 13 passed;
- CI shard verification: PASS, 392 files and 8,963 node IDs assigned exactly
  once;
- proof runner: completed all 15 games and intentionally exited nonzero with a
  structured `BLOCKED` verdict;
- migration upgrade/downgrade/re-upgrade: PASS in three disposable databases.

Relevant ingestion/finality/authority/provenance/shadow/postgame/snapshot/
governance suite, including CU-01P: **332 passed, 1 skipped**.

The branch-local full backend diagnostic produced **8,829 passed, 73 skipped,
61 failed**. CU-01 recorded 8,828 passed, 73 skipped, and 55 failed. The net
increase of six is explained by two independently verified changes:

- CU-01 intentionally retired one obsolete Phase 0C text-ban failure;
- seven performance-intelligence readiness fixture tests now fail consistently
  on this preserved branch (7 failed, 334 passed when their surrounding read
  contracts were run in isolation).

Those seven failures are unrelated to CU-01P and correspond to the performance-
freshness fixture work included in the six commits already on `origin/main` but
not integrated here. The remaining full-suite failures stayed in the previously
recorded Windows `bash -n` path, branch/freeze/source-hash, roadmap/base drift,
and order-dependent runtime clusters. No CU-01P test failed in focused or
relevant execution. No unrelated failure was fixed or claimed resolved.

## 16. Proven claims

- all 15 official games passed canonical finality;
- all 116 expected reliever appearances were stored;
- the six comparable workload inputs matched the authoritative postgame path;
- game-side historical ownership did not follow mutable current team state;
- initial pitch insertion, identical replay, scoped update, supersession, and
  restoration were idempotent at the row level;
- application restart preserved duplicate detection and fingerprints;
- position-player current identity was preserved for three seeded existing
  identities;
- optional PBP failure did not block core GameLogs;
- no proof-run publication or historical-sentinel mutation occurred;
- normalized tracking/source nulls were retained rather than converted to zero.

## 17. Unproven or failed claims

- **FAILED:** unchanged replay does not emit affected entities. It currently
  emits all relievers/teams present in the reprocessed games.
- **FAILED:** pitch-level batted-ball event ownership. The plate-appearance
  result is over-attributed to non-in-play pitches.
- **UNPROVEN:** stale observed PBP content is rejected. No monotonic MLB source
  revision exists in the stored contract; reconciliation is last-observation-
  wins.
- **UNPROVEN:** a naturally partial pitch-tracking game; all selected pitches
  carried the main tracking domains.
- **UNPROVEN:** a naturally observed MLB correction sequence.
- **UNPROVEN:** missing local identity for a position player under realistic
  roster state; the safer existing-identity path was tested.
- **UNPROVEN:** production-database performance, PostgreSQL storage growth, and
  production-history immutability. This proof was intentionally isolated.

## 18. Risks

1. A future incremental recomputation consumer could do unnecessary work or
   generate false downstream change candidates from no-op affected IDs.
2. Consumers could read an eventual plate-appearance result as if it belonged
   to each preceding pitch.
3. Delayed or out-of-order captured payloads can reverse a newer correction
   because observed content fingerprints do not establish revision order.
4. Pitch storage is roughly hundreds of rows per game and needs PostgreSQL
   measurement before wider operation.
5. Partial tracking behavior has only fixture coverage, not natural proof.

## 19. Recommendation

**BLOCK CU-01 from acceptance for authority-migration purposes.**

The canonical GameLog, ownership, workload parity, pitch-row idempotency,
restart, optional-source, and publication boundaries are strong. The final
acceptance statement is nevertheless not supported because three material
parts are false or unproven. Scheduled daily and postgame ingestion must remain
authority, and CU-02 must not begin.

## 20. Branch-integration recommendation

Do not rebase this branch: that would rewrite the named CU-01 audit commit.
After the three proof blockers are repaired and this exact proof reruns, merge
current `origin/main` into the feature branch with a normal merge commit. That
preserves `1bf3978663d2ef0fb562cc49e2b1dea411d03214` as an immutable audit point.
Resolve the expected CI shard manifest overlap by preserving both upstream and
CU test assignments, then rerun focused, relevant, manifest, and broad tests.

No integration was performed in CU-01P.

## 21. Exact next slice

The next slice is a bounded **CU-01 proof-blocker remediation**, not CU-02:

1. separate “examined game participants” from mutation-scoped affected
   pitchers/teams, emitting an empty mutation set for a complete no-op;
2. persist batted-ball outcome only on the in-play pitch/event that owns it;
3. define and enforce a local observation-order contract so an older captured
   source observation cannot overwrite a newer accepted observation;
4. add regression tests for those three contracts;
5. rerun this same 15-game proof, five-game replay/restart sequence, controlled
   correction, optional failure, publication sentinel, and workload baseline.

Do not change authority or begin continuous polling after that rerun.
