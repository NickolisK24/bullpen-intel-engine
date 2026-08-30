# CU-08U — Production Governed Replay Discovery Audit

## Verdict

**PASS — CONFIGURATION ISSUE IDENTIFIED**

CU-08S can replay an unchanged stored-final game during an ordinary
`shadow_full_chain` cycle. The exact production-shaped configuration for game
`823665` reached CU-03 once, completed as `authorized_no_op`, and became inert
on the following cycle in the regression proof.

Production runs `1268` and `1269` did not create or claim a replay checkpoint.
The target therefore disappeared at the effective replay request/pre-creation
authorization boundary, before `_ensure_replay_job`. Given the verified game
state and the code/proof below, the executing Cron process did not have the
complete effective replay authorization described in the Render control plane,
or it refused that authorization before checkpoint creation. The old compact
command output discarded `replay_results`, so the historical runs cannot reveal
which individual configuration gate was absent. CU-08U closes that bounded
observability gap without changing replay eligibility or execution semantics.

## 1. Repository state

- Branch: `fix/governed-replay-discovery`
- Current main SHA at branch creation:
  `0b1c6b0c6547c52c0e2c2793d5c7429b80eec2df`
- CU-08S is present at that SHA.
- The unrelated untracked
  `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` was not modified.

## 2. Production configuration under audit

```text
BASEBALLOS_CONTINUOUS_ALLOWLIST_GAME_PKS=823665
BASEBALLOS_CONTINUOUS_PLAN_FINGERPRINTS={"823665":"53c269913f3ccaaabca551e8a5d16f0ace42cb11b3ac72ff8532c0ddc424a043"}
BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS=823665
BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED=false
```

The production command and schedule remained:

```text
python backend/scripts/run_continuous_cycle.py --mode shadow_full_chain
*/3 * * * *
```

CU-08U did not modify Render, its command, its cadence, or any environment
variable.

## 3. Observed failed production cycles

Read-only production inspection of sync runs `1268` and `1269` found:

- status `success`, stage `continuous_complete`;
- 15 records processed and 16 source API calls;
- zero retries and zero failures;
- zero canonical actions/mutation games;
- zero updated pitchers;
- no published snapshot;
- mode recorded as `shadow_full_chain`.

The compact logs reported 14 unchanged observations and one rejection for the
unrelated game `822690`. They contained no replay lifecycle evidence for
`823665`.

## 4. Configuration parsing proof

`ContinuousExecutionConfig.from_environment` parses the CSV game lists with
integer conversion and parses the JSON fingerprint map before converting each
key to `int`. The exact strings above produce:

```text
allowlist_game_pks = (823665,)
replay_game_pks = (823665,)
expected_plan_fingerprints[823665] =
  53c269913f3ccaaabca551e8a5d16f0ace42cb11b3ac72ff8532c0ddc424a043
production_publication_enabled = false
```

The regression sets the environment mode to `off` and supplies the production
CLI override `shadow_full_chain`. The override replaces only `mode`; it
preserves the allowlist, replay request, fingerprint map, and publication gate.
`python-dotenv` uses its default non-overriding behavior, so a process-level
Render value is not replaced by a local dotenv value.

## 5. Mode-gating trace

`shadow_full_chain` is an accepted chain mode. Governed stored-observation
replay is intentionally restricted to this exact mode and publication disabled.
It is not restricted to `proof_publication`, `limited_live`, or `full_live`.

The production sync metadata confirms the CLI override reached the cycle as
`shadow_full_chain`.

## 6. Cycle wiring trace

The command calls:

```text
run_continuous_cycle(mode="shadow_full_chain")
```

`run_continuous_cycle` first builds the complete environment configuration and
then applies the mode-only dataclass replacement. `_execute_cycle` receives the
same configuration object and calls `_prepare_governed_replays` with it. No
intermediate layer reconstructs or drops the replay list, game allowlist, or
fingerprint map.

## 7. Replay discovery trace

Replay discovery is driven by `config.replay_game_pks`, not by current changed
games or by a pre-existing `SyncJob`. It runs immediately after CU-02 detection:

```text
CU-02 results
→ _prepare_governed_replays(config, detection_results)
→ pre-creation authorization checks
→ _ensure_replay_job
→ durable claim
→ CU-03 handoff
```

The cycle subsequently iterates over the union of current accepted changes and
prepared replay changes. Replay discovery is not nested under `if changed_games`
or equivalent. An unchanged target is therefore supported by design.

## 8. Production state for game 823665

Read-only production evidence found one persisted accepted observation with:

- classification `finalized`;
- finality `final_pending_data`;
- source authority `mlb_statsapi_live_feed_v1_1`;
- upstream revision `2026-08-29T20:46:54`;
- observation fingerprint
  `77ba60bec8a1c026931e4bc140c53c77b43aca2bddfb2dfaa19edb50c83cb6c5`;
- official date `2026-08-29`;
- Minnesota (`142`) home and Chicago (`145`) away.

Both schedule-authority rows were final. Canonical state contained seven
GameLogs and 289 current normalized pitch events. PBP was fully processed.

`final_pending_data` is explicitly accepted by the CU-08S replay contract,
along with `final_and_usable`. The postgame schedule refresh therefore did not
invalidate replay eligibility.

## 9. SyncJob evidence and first disappearance point

There was no `continuous_game_replay` `SyncJob` for game `823665`: no ID,
scope key, status, attempt, claim, completion, failure, stale claim, or consumed
checkpoint existed.

An eligible request creates and commits the durable job before attempting the
claim and before CU-03. A CU-01 plan mismatch or execution failure would still
leave a durable failed checkpoint. Therefore production did not reach job
creation, claim, CU-03, or canonical reconciliation.

The first disappearance point is the boundary at or before
`_prepare_governed_replays`' pre-creation authorization checks. The remaining
possible historical states were:

1. the executing process parsed an empty `replay_game_pks`; or
2. it parsed the request but refused it for a missing/mismatched pre-creation
   gate, most plausibly the effective game allowlist or fingerprint map.

The target's observation, finality, authority, official date, and unchanged
status were independently verified and do not explain the refusal. Publication
configuration also did not block the whole cycle. Consequently this is an
effective runtime replay-authorization discrepancy, not a defect in unchanged
game discovery.

The old command rendered only cycle totals, changed observations, and CU-02
stale/ambiguous rejections. It discarded the returned replay result. Its
separate replay logger used `INFO`, while the command installed no logging
configuration that guaranteed those messages. The two historical alternatives
above cannot be distinguished retroactively.

## 10. Fingerprint revalidation

The production-authoritative CU-01 shadow planner was rerun read-only for only
game `823665`. It produced:

- status `complete`;
- exact exclusive scope with one game;
- seven appearances, all unchanged;
- five relief appearances;
- zero affected pitchers and teams;
- zero writes or commits;
- complete reconciliation fingerprint
  `53c269913f3ccaaabca551e8a5d16f0ace42cb11b3ac72ff8532c0ddc424a043`.

The configured reviewed fingerprint is still current. No replacement
fingerprint was generated or authorized.

## 11. Production-shaped reproduction

The regression uses the literal game ID and fingerprint strings from Render,
sets publication false, stores an accepted final observation, returns zero
changed games from CU-02, and applies the CLI mode override.

First cycle:

```text
unchanged CU-02 target
→ game_replay_requested
→ game_replay_authorized
→ CU-03 called exactly once with reviewed fingerprint
→ authorized_no_op
→ game_replay_completed
→ durable checkpoint succeeded
```

Second cycle:

```text
same unchanged target
→ replay_already_consumed
→ CU-03 calls = 0
→ no downstream work
```

This directly answers the primary question: **yes, CU-08S can replay an
unchanged stored-final game in a normal `shadow_full_chain` cycle.**

## 12. Bounded fix

The replay result now carries a compact lifecycle event list produced at the
same transitions that already emitted structured logger messages. The command's
compact renderer emits only approved fields for those events:

- `game_replay_requested`;
- `game_replay_authorized` with reviewed fingerprint;
- `game_replay_completed` with outcome;
- or `game_replay_refused` with one bounded reason code;
- and `game_replay_failed` with only the exception class.

Checkpoint payloads, source payloads, and verbose orchestration data are not
printed. Discovery, eligibility, SyncJob identity, claim, retry, CU-03, CU-01,
publication, and cache behavior are unchanged. No schema change was made.

## 13. Regression proof

The new production-shaped regression proves:

- `shadow_full_chain` with zero changed games;
- unchanged target `823665` with an accepted stored-final observation;
- literal production allowlist, replay request, and reviewed fingerprint;
- publication disabled;
- replay discovery and one CU-03 call;
- `authorized_no_op` completion;
- durable consumption and no second execution.

Existing CU-08S coverage continues to prove wrong/missing game authorization,
missing/malformed or stale reviewed fingerprints, revoked/missing replay
request, publication-gate refusal, bounded retry, restart/inertness, lock
behavior, and mutation-scoped downstream work.

The command regressions prove all three successful lifecycle lines and explicit
refusal reasons appear in compact output without leaking the durable checkpoint.

## 14. Publication and cache safety

The production-shaped proof retained:

```text
BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED=false
live_publications = 0
cache_handoffs = 0
production_authority_affected = false
```

CU-08U changes no publication or cache branch.

## 15. Validation

- CU-08U/CU-08S command and governed replay tests: included below.
- Focused replay, CU-03, CU-01 fingerprint, SyncJob, publication, cache, and
  read-model safety selection: **157 passed, 4 skipped**.
- The four skips include the PostgreSQL-only independent-process concurrency
  proof; claim/discovery semantics were not changed by CU-08U.
- CI shard accounting: **402 files / 9,155 tests**, every test assigned exactly
  once.
- Python compilation: **PASS** for all changed Python files.
- Whitespace/diff checks: **PASS**; only expected CRLF conversion notices were
  emitted by Git on Windows.

## 16. Merge recommendation

Push `fix/governed-replay-discovery`, open a focused PR to `main`, require the
hosted PostgreSQL replay/concurrency selection and all required CI, audit the
final diff, and merge with a normal merge commit. Do not squash or rebase.

## 17. Exact production retry instructions

After the focused PR is merged and the normal existing deployment has completed:

1. Do not change the authorized game, fingerprint, publication flag, mode,
   command, or cadence.
2. Observe one natural `*/3` Cron execution.
3. Require compact lines for `823665`:
   `game_replay_requested`, then either an explicit refusal reason or
   `game_replay_authorized` and `game_replay_completed` with
   `authorized_no_op`.
4. If no replay line appears, the executing Cron process has no effective
   `BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS=823665` value or is not on the merged
   command build. Stop; do not authorize another game.
5. If refused, use the emitted reason to correct only the named Render Cron
   service variable in a separate production task. Do not guess.
6. On success, verify one succeeded `continuous_game_replay` SyncJob with one
   attempt, zero canonical mutations, zero affected entities, zero live
   publications, and zero cache handoffs.
7. Observe the following natural cycle and require
   `game_replay_refused` with `replay_already_consumed`, zero CU-03 execution,
   and no downstream work.
8. Remove/revoke the replay request only in a separately authorized Render
   configuration task after the evidence is captured.

Do not move beyond `shadow_full_chain` and do not authorize another game.
