# CU-06 Incremental Team Board / League / Matchup Read-Model Rebuild

## Verdict

**PASS — CU-06 ACCEPTED**

CU-06 rebuilds bounded, in-memory serving payloads from the exact trusted CU-05
result, delegates baseball semantics to the current backend builders, proves
semantic parity, and stops before publication, cache invalidation, frontend
work, or scheduling.

## Repository state

- Branch: `feat/incremental-read-models`
- Starting main SHA: `cfa09692a9ef0a32f8179732c80304da7ccd1d33`
- `origin/main` at branch creation: `cfa09692a9ef0a32f8179732c80304da7ccd1d33`
- Main drift during implementation: none at the final pre-commit audit
- Schema changes: none
- Alembic head: `c6d8e1f3a5b7`

The unrelated untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md`
remained untouched.

## Targeted read-model audit

### Team Board

The current frozen serving authority is
`services.public_serving_authority.build_published_team_board`. It selects one
trusted Dashboard snapshot, projects one frozen per-team package through
`services.bullpen_board.build_board_payload`, attaches published Team State,
and returns a payload without writing. The on-request Team Board v2 composer
(`services.team_board_v2.build_team_board_v2_payload`) remains unchanged. CU-06
does not call its independent What Changed builder; existing What Changed is not
regenerated or represented as a new transition.

CU-06 adds optional snapshot and Team State override parameters to the frozen
Team Board builder. Defaults are unchanged. The override path reads the copied
snapshot's frozen currentness instead of consulting a second live snapshot.

### League / Dashboard

`services.league_team_state_listing.build_league_team_state_listing` remains the
30-club serving authority. CU-06 extracts its existing row projection into
`build_league_team_state_row`, and the broad listing now calls that same helper.
An affected row can therefore be replaced without recomputing Team State for
the other 29 clubs or changing ordering/identity semantics.

### Matchup

`services.trusted_compare_authority.build_scheduled_game_matchup_payload` and
`services.current_bullpen_comparison.build_current_bullpen_comparison` remain
the game and comparison authorities. Optional Team State overrides let the
same comparison builder consume CU-05's governed state while workload, rest,
rotation, availability, identity, and no-edge fields remain owned by their
existing projectors. Matchups are selected by the affected game and deduplicated
by `gamePk`.

### Tonight

`services.tonight_intelligence_service.serve_tonight` remains the read-only
Tonight composer. It already accepts schedule, bullpen-context, Team State,
workload, rotation, and rest providers. CU-06 supplies the single affected game,
the affected teams' shadow contexts, and sidecars projected from the copied
snapshot. It extracts only that game's entry. No cache-aware Tonight snapshot
writer is called.

### Pitcher decision

No separate Pitcher read-model rebuild is required by the Team Board, League,
Matchup, or Tonight dependency graph. Affected Arm Reads are carried into team
records; the public Pitcher detail path is structurally separate. CU-06 reports
zero Pitcher models rebuilt rather than widening scope.

## Storage, publication, and currentness

Current serving models combine immutable Dashboard snapshot JSON, published
Team State Share Artifacts, on-request pure composition, and cache-aware wrappers.
CU-06 does not replace any of those authorities. It copies the selected trusted
snapshot in memory, deep-copies its payload, and overlays only affected facts.
The copy is never added to a session, persisted, published, cached, or installed
as a current pointer.

The represented date comes from the accepted CU-05 result. Snapshot
`data_through`, availability reference date, workload-window authority stamps,
Team State data-through values, matchup identity, and Tonight reference date are
preserved. Build time is never substituted for baseball time.

## CU-06 architecture and dependency graph

`services.incremental_read_model_rebuild.rebuild_read_model_impact` implements:

`trusted CU-05 result -> copied trusted snapshot -> affected Team Boards -> affected League rows -> one affected Matchup -> one affected Tonight entry -> semantic parity -> STOP`

Input is accepted only when CU-05 is complete, parity-matched, and performed
real recomputation. Inputs are CU-05's exact recomputed pitcher/team IDs, Arm
Reads, Team States, carried CU-04 workload/rest results, gamePk, and represented
date. CU-06 never rediscovers affected entities.

Deduplication is by sorted ID sets:

- one team -> one Team Board
- one team -> one League row
- both game teams -> one Matchup
- both game teams -> one Tonight entry

No trusted CU-05 work means zero builders and a `no_action` result.

## Shadow snapshot overlay

The CU-05 result now carries three additive internal-only maps required by the
next stage:

- classified availability results
- CU-04 pitcher workload/rest results
- CU-04 team workload-window results

The copied frozen package receives only affected record availability/workload,
affected team workload windows, and recomputed D-055 Rest Status. Existing
roster, role, rotation, performance, transaction, and other optional domains
remain unchanged. `bullpen_context` gained an optional classified-record
override that merges with, rather than replaces, existing eligibility and
roster evidence. Default production calls are unchanged.

Partial or unknown domains remain governed by their existing builders. Missing
values are not changed to zero and an unavailable surface becomes a structured
partial CU-06 result.

## Files changed

- `backend/services/incremental_read_model_rebuild.py`
- `backend/services/incremental_arm_read_team_state.py`
- `backend/services/public_serving_authority.py`
- `backend/services/league_team_state_listing.py`
- `backend/services/current_bullpen_comparison.py`
- `backend/services/trusted_compare_authority.py`
- `backend/services/bullpen_context.py`
- `backend/scripts/run_cu05_proof.py`
- `backend/scripts/run_cu06_proof.py`
- `backend/tests/test_incremental_read_model_rebuild.py`
- `backend/tests/ci_shard_manifest.json`
- `docs/current/CU_06_INCREMENTAL_READ_MODEL_REBUILD.md`

Schema changes: **none**.

## Proof dataset and evidence boundary

The exact accepted 15-game dataset was reused.

- Canonical acquisition, reconciliation, affected entities, and CU-04 workload:
  captured real-game evidence.
- Current membership and CU-05 Team State: controlled real-shape overlay, as in
  the accepted CU-05 proof, because historical current-roster snapshots are not
  reproducible from the capture.
- CU-06 current serving composition: controlled real-shape builder injection.
- Existing real Board and Matchup builders' shadow override seams: separately
  exercised against their actual frozen-package fixtures.

Controlled evidence is not claimed as naturally observed production serving or
publication.

## Strongest end-to-end proof

The focused chain proves:

`CU-02 finality -> CU-03 authorization -> CU-01 canonical mutations -> CU-04 parity -> CU-05 parity -> CU-06 bounded read models -> parity -> STOP`

Observed representative chain:

- GameLogs inserted: 4
- pitch events inserted: 4
- affected pitchers: 2
- affected teams: 2
- CU-04: parity MATCH
- CU-05: parity MATCH
- Team Boards rebuilt: 2
- League rows rebuilt: 2
- Matchups rebuilt: 1
- Tonight entries rebuilt: 1
- publication/cache work: 0

## Fifteen-game parity matrices

| Surface | Rebuilt objects | Semantic mismatches | Result |
|---|---:|---:|---|
| Team Board | 30 | 0 | MATCH |
| League row | 30 | 0 | MATCH |
| Matchup | 15 | 0 | MATCH |
| Tonight affected entry | 15 | 0 | MATCH |
| Pitcher model | 0 | 0 | NOT REQUIRED |
| **Total** | **90** | **0** | **100%** |

Comparison removes only understood incidental fields: `generated_at`,
`elapsed_ms`, and `served_from`. Ordered lists, represented dates, player lists,
counts, states, workload/rest, and all baseball values remain material.

The coupled upstream proof also remained exact:

- CU-05: 3,006 / 3,006 fields, 0 mismatches
- Arm Reads recomputed: 113
- Team States recomputed: 30

## Replay, determinism, restart, and correction

- Five-game exact replay: canonical mutations 0, CU-04 calls 0, CU-05 calls 0,
  CU-06 calls 0.
- Direct repeated rebuild: semantic Team Board, League, Matchup, and Tonight
  results were identical.
- Fresh service-call/restart-shaped rebuild: no in-memory registry or prior run
  state was required.
- Controlled correction: only the requested team's Board and League row changed;
  the unrelated team remained absent and both before/after payloads matched their
  broad comparison.
- Unrelated-team sentinel: team 30 produced no matchup or Tonight rebuild for a
  game between teams 10 and 20.

## Historical and identity safety

The position-player cases remained unchanged:

- Pedro Pagés remained C
- Jorbit Vivas remained 3B
- Myles Straw remained CF

CU-06 writes no Pitcher/roster state and does not infer current membership from
a historical pitching appearance.

## Publication, cache, frontend, and scheduling safety

Before/after publication fingerprints in the disposable proof database were
identical. Result flags were false for publication, cache invalidation,
scheduling, frontend changes, What Changed generation, and downstream work.
Static call-boundary tests reject publication, cache, daily-sync, cached-Tonight,
or polling calls from the CU-06 service.

No Render configuration, GitHub workflow, cron expression, worker, daemon,
polling loop, frontend file, or public route contract was changed. Existing
scheduled syncs remain production authority. CU-06 has no scheduled command and
remains dormant unless invoked explicitly in proof/developer code.

## Incremental efficiency and query observations

Across 15 changed games:

- 30 Team Boards instead of 450 team-board work units (6.7%)
- 30 League rows instead of 450 team-row work units (6.7%)
- 15 deduplicated Matchups, one per affected game
- 15 Tonight entries, one per affected game
- measured controlled composition time: 1.911 ms total

The current builders still read shared league baselines and snapshot sidecars;
CU-06 does not optimize those established queries. It does not introduce a
full-league semantic recomputation or a new N+1 loop beyond the bounded teams.

## Validation

Focused CU-06:

- 13 passed

Focused/shared read-model selection:

- 305 passed before the known remote-database environment group
- working-directory-qualified trusted Team Board group: 33 passed
- combined relevant coverage: 338 passed

Exact 15-game proof:

- PASS
- 90 / 90 comparable objects MATCH

CI shard verification:

- 398 files
- 9,067 tests
- every test assigned exactly once

Migration head:

- `c6d8e1f3a5b7`
- no CU-06 migration

Python compilation and whitespace checks: PASS.

Full backend diagnostic: **NOT RUN**. The initial broad relevant selection's 32
errors were all the known safety refusal against the inherited remote Supabase
test URL; the same file passed 33/33 with an explicit disposable SQLite test
database. No CU-06 regression was found.

## Remaining known gaps and risks

- Natural production Team Board/Matchup/Tonight propagation remains unproven;
  CU-06 is deliberately shadow-only.
- Historical proof cannot reconstruct natural current-roster membership and
  continues to use the accepted controlled overlay.
- Team Board v2 optional What Changed remains outside CU-06. It is not regenerated
  or claimed as incrementally updated.
- Public Pitcher detail remains a separate future dependency.
- Snapshot overlay correctness now has strong fixture and 15-game proof, but
  hosted PostgreSQL validation belongs to the later merge task.
- Shared league-baseline reads may be optimized later only if production
  measurement demonstrates need.

## Proven and unproven claims

Proven:

- trusted CU-05 no-op produces zero CU-06 work
- affected teams/games are deduplicated
- existing backend Board, League, Matchup, and Tonight seams accept bounded
  shadow inputs
- comparable rebuilt objects have 100% semantic parity
- unrelated teams/games are not rebuilt
- replay, restart-shaped calls, and corrections are deterministic
- no schema, publication, cache, frontend, or scheduling mutation occurs

Unproven:

- natural live production propagation
- atomic replacement of currently served models
- cache handoff or publication activation
- natural historical roster membership for captured games
- incremental What Changed and public Pitcher detail

## Recommended integration and next slice

Because `origin/main` did not advance and the focused semantic, shared builder,
15-game, shard, compilation, migration-head, and whitespace gates are green,
the recommended next repository action is a separate safe push/PR/hosted
PostgreSQL validation/normal-merge task for `feat/incremental-read-models`.

Only after CU-06 is safely merged should the next slice be considered:

**CU-07 — Atomic Incremental Publication & Cache Handoff**

CU-07 is not implemented here.
