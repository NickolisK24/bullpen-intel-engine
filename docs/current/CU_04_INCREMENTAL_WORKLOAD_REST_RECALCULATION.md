# CU-04 Incremental Workload & Rest Recalculation

## 1. Branch

`feat/incremental-workload-rest`

## 2. Starting main SHA

`455615560442a7add364c0df2a9a930adfaedf31`

## 3. Current post-CU-03 main/CI status

CU-03 PR #770 is on `main`. Its post-merge CI run `33221650622` completed
successfully. At CU-04 proof closeout, `origin/main` remained exactly the
starting SHA; it did not advance during implementation.

## 4. Targeted workload/rest audit

The current production path has one pitcher workload calculator and one team
workload-window author:

- `services.fatigue.calculate_fatigue` computes pitcher 7/14-day supporting
  workload facts from canonical `GameLog` rows.
- `services.availability` derives yesterday, 3-day, 5-day, days-rest, and usage
  pattern inputs. CU-04 extracts this existing derivation as
  `derive_workload_rest_inputs`; `classify_availability` still calls the same
  code and retains unchanged semantics.
- `services.public_team_relief_work.author_workload_windows` authors the
  governed 7/14-day team relief windows from resolved historical game-side
  ownership.
- `services.sync.recalculate_all_fatigue` is the scheduled persisted writer. It
  recalculates all active pitchers after daily or postgame canonical changes and
  commits `FatigueScore` rows.

Availability status, fatigue risk labels, Team State, public summaries, and
deployment/role interpretation are later-domain outputs and are excluded.

## 5. Current authoritative calculators

Pitcher authority is the existing `calculate_fatigue` plus the workload/rest
input derivation already used by `classify_availability`. Team authority is
`author_workload_windows`. CU-04 contains no replacement formula and compares
its bounded output by invoking those same authoritative seams independently in
shadow mode.

## 6. Represented-date contract

The caller supplies explicit `data_through`; CU-04 never uses server-local
`now`. Existing `trusted_slate_reference_dates` splits the date correctly:

- team membership/workload windows: the represented `data_through` date;
- pitcher availability/workload reference: `data_through + 1 day`.

All rolling windows retain existing inclusive calendar-day behavior. The
fatigue calculator's 7/14-day bounds and the team author's 7/14-day bounds are
not normalized into a new formula; each remains exactly as currently governed.

## 7. Active-bullpen/group contract

Pitcher recomputation consumes only CU-03's exact mutation-scoped pitcher IDs.
It does not discover or expand membership. Team workload uses all official
relief appearances owned by the team inside the window, as the current team
author does. Historical ownership is `GameLog.appearance_team_id` with resolved
status, never mutable `Pitcher.team_id`. Current roster membership is not used
to rewrite history.

## 8. CU-04 service architecture

`recompute_workload_rest_impact` performs:

`CU-03 mutation result -> validate actual mutation -> exact pitcher/team IDs ->`
`bounded authoritative calculations -> field parity -> structured result -> STOP`

The result is pure, in-memory, internal, and non-public. It carries requested
and recomputed IDs, workload facts, parity entries/mismatches, failures,
timings, and explicit false flags for Team State, read models, publication,
cache invalidation, and downstream recomputation.

## 9. Affected-entity input contract

Required input is CU-03's `canonical_mutation_performed`, `game_pk`,
`affected_pitcher_ids`, and `affected_team_ids`, plus explicit `data_through`.
CU-04 never rebuilds impact from game participants, schedule teams, or current
pitcher teams. No canonical mutation or no affected entities returns
`no_action` before any pitcher/team query.

## 10. Pitcher workload fields recomputed

Comparable pitcher facts are:

- latest appearance and days rest;
- pitches yesterday, 3 days, 5 days, and 7 days;
- appearances in 3, 5, 7, and 14-day windows;
- 7-day innings derived by the existing outs-safe utility;
- back-to-back, 3-in-4, and current authoritative 4-in-5 pattern;
- freshness/data state and explicit reference dates.

The repository does not currently own 4-in-6, 30-day pitcher accumulation, or
a separate persisted pitch-spike workload fact. They remain unsupported rather
than being invented.

## 11. Team workload fields recomputed

The existing team authority provides exact 7/14-day relief appearances,
represented relief pitchers, pitch totals with null completeness, appearances
with pitch evidence, unknown start/relief counts, and represented dates. Team
outs/innings, 3-day, and 30-day totals are not fields in this governed workload
window carrier and are not added here.

## 12. Explicitly excluded later-domain fields

CU-04 does not calculate availability status, arm reads, fatigue risk labels,
Clean Options, Team State, workload concentration interpretation, deployment
roles, public summaries, Team Board, League, Matchup, Tonight, Pitcher read
models, History, or What Changed.

## 13. Files changed

- `backend/services/availability.py`
- `backend/services/incremental_workload_rest.py`
- `backend/scripts/prove_incremental_workload_rest.py`
- `backend/scripts/run_cu04_proof.py`
- `backend/tests/test_incremental_workload_rest.py`
- `backend/tests/ci_shard_manifest.json`
- `docs/current/CU_04_INCREMENTAL_WORKLOAD_REST_RECALCULATION.md`

## 14. Schema changes

None. CU-04 creates no table, migration, snapshot, or derived persisted row.
The single Alembic head remains `c6d8e1f3a5b7`.

## 15. Proof dataset

The proof reused the exact accepted 15 official finals from CU-01/CU-03:
823826, 823989, 823180, 824878, 823016, 822692, 822771, 823014, 823825,
822773, 823585, 823505, 824963, 822694, and 823179. The source was reacquired
into a disposable local database; temporary raw responses were removed with the
temporary directory. Source fingerprint:
`c537233816b017af0e4868d60fc8f8bd2402a3f86b951e68eb913b06187f7929`.

This natural finalized-game set covers multi-reliever and extra-inning games,
consecutive usage, multi-inning work, and three position-player pitching cases.
Correction, optional-PBP failure, and transition routing remain controlled
real-shape proofs.

| gamePk | Date | Pitchers | Teams | Compared fields | Mismatches |
|---:|---|---:|---|---:|---:|
| 822773 | 2026-08-25 | 9 | 118, 141 | 224 | 0 |
| 823016 | 2026-08-25 | 6 | 110, 138 | 164 | 0 |
| 823505 | 2026-08-25 | 8 | 117, 147 | 204 | 0 |
| 823585 | 2026-08-25 | 8 | 121, 158 | 204 | 0 |
| 823826 | 2026-08-25 | 12 | 111, 146 | 284 | 0 |
| 823989 | 2026-08-25 | 11 | 108, 114 | 264 | 0 |
| 822692 | 2026-08-26 | 6 | 115, 120 | 164 | 0 |
| 823180 | 2026-08-26 | 9 | 113, 137 | 224 | 0 |
| 823825 | 2026-08-26 | 5 | 111, 146 | 144 | 0 |
| 824878 | 2026-08-26 | 9 | 119, 144 | 224 | 0 |
| 824963 | 2026-08-26 | 5 | 133, 142 | 144 | 0 |
| 822694 | 2026-08-27 | 7 | 115, 120 | 184 | 0 |
| 822771 | 2026-08-27 | 7 | 118, 141 | 184 | 0 |
| 823014 | 2026-08-27 | 7 | 110, 138 | 184 | 0 |
| 823179 | 2026-08-27 | 7 | 109, 137 | 184 | 0 |

## 16. Strongest end-to-end proof

The integrated test executes a controlled real-shape CU-02 live-to-final
transition, reviewed CU-03 authorization, and actual CU-01 reconciliation.
Observed: 4 GameLogs, 4 pitch events, 2 affected relievers, and 2 historically
owning teams. CU-04 recomputed exactly those 2 pitchers and 2 teams; every
supported field matched; Team State and publication remained false.

The 15-game disposable proof then exercised the same canonical writer followed
by CU-04 for all natural finals: 116 pitcher recomputations and 30 team
recomputations, exactly matching the canonical mutation scopes.

## 17. Pitcher parity matrix

All 2,320 pitcher comparisons matched (116 recomputations x 20 fields).

| Field family | Result |
|---|---|
| identity and represented/reference dates | MATCH |
| latest appearance / days rest | MATCH |
| appearances 3/5/7/14 | MATCH |
| pitches yesterday/3/5/7 | MATCH |
| innings 7 | MATCH |
| back-to-back / 3-in-4 / 4-in-5 | MATCH |
| freshness/null state | MATCH |

## 18. Team parity matrix

All 660 team comparisons matched (30 recomputations x 22 fields).

| Field family | Result |
|---|---|
| carrier status and represented date | MATCH |
| 7-day appearances/pitchers/pitches/completeness | MATCH |
| 14-day appearances/pitchers/pitches/completeness | MATCH |
| official relief/start classification | MATCH |

## 19. Overall parity percentage

**2,980 / 2,980 comparable fields matched: 100%.** Mismatch handling was also
tested: one intentionally altered authoritative value produced `partial`, an
explicit field path, and no downstream stage.

## 20. No-op proof

The exact five-game replay produced zero canonical mutations, zero affected
pitchers, and zero affected teams. The proof router made zero CU-04 calls.
Directly presenting a no-mutation result to the service also performs zero
pitcher/team recomputations and writes nothing.

## 21. Restart proof

After `db.session.remove()`, unchanged CU-02/CU-03 state still routes to zero
CU-01 and CU-04 calls. A direct bounded recomputation after session restart
returned identical pitcher results, team results, parity entries, and parity
status from durable canonical facts.

## 22. Window-boundary proof

Focused tests pin exact inside/outside boundaries for 7 and 14 days, the
existing fatigue-window inclusivity, same-day/doubleheader appearances,
yesterday, off-days, and represented-date rollover. Existing authority has no
3/30-day team carrier or 30-day pitcher field to compare.

## 23. Rest-pattern proof

Focused proofs cover one, two, and four days rest; worked yesterday;
back-to-back; 3-in-4; authoritative 4-in-5; doubleheader counts; and no-prior
appearance. No-prior remains `None`/missing, never zero or rested. Three
consecutive days is represented by existing 3-in-4/back-to-back inputs; there
is no separately owned `three_straight` field.

## 24. Historical-team attribution proof

A pitcher currently assigned to team 999 with a historical resolved appearance
for team 10 recomputed pitcher facts plus team 10 only. Team 999 and an
unrelated team 20 were untouched. The team query remains indexed on
`appearance_team_id, game_date`.

## 25. Position-player proof

Pedro Pagés (C), Jorbit Vivas (3B), and Myles Straw (CF) retained their current
positions, team IDs, and active identities in the real proof. Controlled CU-04
coverage also proved a historical relief row can contribute under existing team
authority without changing current roster identity.

## 26. Correction proof

A controlled canonical correction changed one appearance from 18 to 19 pitches.
CU-04 recomputed only that pitcher and historical team. Both pitcher 7-day and
team 7-day totals changed by exactly +1; unrelated pitcher/team results were
absent.

## 27. Optional-PBP failure proof

A controlled CU-03 result with optional PBP `incomplete` and valid core
GameLog mutation recomputed workload/rest successfully from core pitching-line
facts with complete parity. No pitch-tracking fallback value was invented.

## 28. Zero-Team-State proof

CU-04 imports no Team State or arm-read engine and never invokes availability
classification. The shared extraction stops before `_evaluate_workload`.
Result and sentinel tests keep `team_state_recomputed=false` and downstream
recomputation false.

## 29. Zero-read-model/publication proof

No `FatigueScore` row, public snapshot, historical snapshot, share artifact,
read model, publication pointer, What Changed record, or cache action is written.
The 15-game publication-table fingerprints were identical before and after.

## 30. Zero-scheduling proof

No Render file, cron expression, GitHub workflow, worker, daemon, or polling
loop changed. Both developer proof scripts disable `AUTO_SYNC`; they are
standalone and require explicit invocation.

## 31. Incremental performance measurements

The 15-game shadow run spent 91.813 ms in pitcher recomputation and 16.472 ms
in team recomputation. Shadow parity intentionally repeats the authoritative
calculations and issued 756 database queries; this is bounded but is an obvious
per-pitcher query pattern to monitor before activation.

The proof database contained 138 canonical pitchers and 21 represented teams.
Fifteen broad cycles would perform 2,070 pitcher and 315 team work units;
CU-04 performed 116 and 30 respectively (5.6% and 9.5% of those broad units).
One pure broad calculation measured 106.191 ms for pitchers and 10.721 ms for
teams. These are local disposable-SQLite measurements, not production latency.

## 32. Focused tests

- CU-04 focused: **23 passed**.
- CU-04 plus authoritative fatigue/availability: **93 passed** before the final
  focused expansion.
- Exact real-game proof: **PASS**, 15 games, 2,980/2,980 fields.

## 33. Broader relevant tests

- CU-01/CU-02/CU-03, ingestion, finality, workload, ownership: **394 passed,
  1 skipped**.
- Scheduling/publication/governance selection: **189 passed**.
- CI shard verification: **PASS**, 396 files and 9,035 tests exactly once.
- Python compilation: **PASS**.
- Diff/whitespace: **PASS**.
- Migration head: **PASS**, one head `c6d8e1f3a5b7`.

The entire approximately 9,000-test backend suite was not rerun; the requested
single broader relevant selection was used after focused development.

## 34. Remaining known gaps

- No new 3/30-day team, 30-day pitcher, 4-in-6, pitch-spike, or team-outs fact
  exists because current authority does not own those fields in this layer.
- Real-game correction and optional-PBP effects remain controlled rather than
  naturally observed revisions.
- Query count is bounded to affected entities but parity doubles the reads; a
  future activated path may batch pitcher reads after measuring PostgreSQL.
- CU-04 is dormant and has no natural scheduled-production latency evidence.

## 35. Proven claims

- Exact mutation-scoped pitcher/team recomputation.
- Explicit represented-date authority and restart determinism.
- Existing historical-team and relief-membership semantics.
- 100% comparable-field parity across the exact 15-game dataset.
- Incremental correction behavior and strict no-op routing.
- Null preservation and position-player identity safety.
- Zero Team State, read-model, publication, cache, and scheduling effects.

## 36. Unproven claims

- Production PostgreSQL performance under recurring live orchestration.
- Natural MLB post-final correction and optional-PBP failure timing.
- Any CU-05 arm-read or Team State behavior.

## 37. Final verdict

**PASS — CU-04 ACCEPTED**

## 38. Exact recommended integration action

`origin/main` did not advance materially during CU-04 and all directly relevant
integration suites are green. Use a direct safe push/PR/normal-merge task for
`feat/incremental-workload-rest`; a separate heavy CU-04I ceremony is not
recommended unless main advances into workload/rest code before that task.

## 39. Exact next slice only after safe merge

After CU-04 is safely on main, the next bounded objective may be CU-05 —
Incremental Arm Reads & Team State Recalculation. Do not begin CU-05 before the
repository integration is complete and separately authorized.
