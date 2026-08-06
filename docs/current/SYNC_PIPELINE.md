# BaseballOS Sync Pipeline — Execution Order, Authority, and Trust Gates

**Status:** Current operational runbook  
**Owner:** Nickolis Kacludis  
**Reviewed:** August 6, 2026  
**Workflow authority:** `.github/workflows/baseballos-sync.yml`

This document describes the current production sync/publication workflow and
its operational boundaries. The canonical Architecture & Operations Manual owns
the durable architecture. The canonical Roadmap owns current sequence and
accepted authority decisions.

## 1. Current Authority Posture

The most important facts are:

- the **legacy daily/postgame path remains the production baseball-data writer**;
- game-driven **daily** ingestion operates in `shadow`;
- game-driven **postgame** ingestion operates in `shadow`;
- automatic game-driven backfill authority is **off**;
- automated game-driven write mode is **unapproved**;
- game-driven publication-authority transfer is **unapproved**;
- the existence of qualification machinery does not grant broader mutation authority.

Do not describe the game-driven lane as `off`: daily and postgame are actively
observed in shadow. Do not describe the legacy per-pitcher GameLog lane as
retired: it remains authoritative until a separate explicit authority-transfer
decision is made.

## 2. Operating Modes

| Mode | Trigger | Current meaning |
|---|---|---|
| `daily` | scheduled morning run or manual dispatch | legacy writer authoritative; game-driven lane shadow-observed; trusted snapshot/public cache attempted after gates |
| `postgame` | scheduled overnight passes or manual dispatch | completed-game reconciliation; game-driven lane shadow-observed after the legacy path; trusted publication follows existing gates |
| `backfill` | manual only with explicit date | governed historical replay; no automatic broad backfill authority |
| `intraday` | manual/read-only unless separately authorized | audit/reconciliation; does not silently gain write authority |

Exact cron values are runtime configuration in the workflow file and may change
without changing the mode semantics above.

## 3. Public Sync Order

Conceptually:

```text
schedule/finality preflight
-> source acquisition and canonical writes
-> derived workload/current state
-> trusted snapshot build
-> publish or withhold
-> team-progressive publication where eligible
-> Tonight/slate refresh
-> deep appearance-ledger audit
-> dashboard/public-cache verification
-> downstream enrichment/static publication
```

A later successful stage cannot erase an earlier failed trust gate.

For the current daily path, expensive upstream work includes team assignment,
roster status, transactions, schedule/finality and slate work before the
publication-critical legacy GameLog lane receives its runtime remainder. That
ordering is currently the subject of OPS-002.

## 4. Appearance Ledger Gate

The appearance ledger is publication-critical.

A candidate trusted league snapshot remains pending/withheld when the required
recent window contains any condition that prevents proof, including:

- a final game with zero required appearance rows;
- fewer stored appearance rows than the official completed pitching lines require;
- incomplete/failed postgame evidence;
- unresolved participating teams;
- source/finality conflict that prevents proof.

The previous trusted published snapshot continues serving with its original
`data_through` date. It must not be relabeled as current merely because it is the
latest safe artifact available.

The workflow independently re-proves eligibility through the deep appearance
ledger audit. A failed or unrun required audit fails the workflow loudly.

## 5. `public-sync` and `shadow-activation-health` Are Separate Verdicts

OPS-001 separated two questions that were previously coupled:

| Job | Question |
|---|---|
| `public-sync` | Did trusted public synchronization and every publication-critical proof succeed? |
| `shadow-activation-health` | Did the game-driven shadow cycle satisfy its observer/qualification contract? |

A shadow-only failure must not rewrite publication truth. A public-sync failure
must not be blamed on shadow when publication-critical work failed on its own
merits.

The observer job may still make the overall workflow red when shadow evidence
is failed or unproven. That is intentional. The important boundary is that
publication-dependent jobs use the `public-sync` verdict, not the observer
verdict.

The shadow observer carries no production credential and performs no production
mutation. Missing or unsafe observer evidence resolves `UNPROVEN`, not success.

## 6. D-044 — Observation Backlog Is Not a Baseball Publication Deficit

The shadow game-driven lane may contain work-item bookkeeping that is incomplete
relative to the authoritative writer.

In shadow mode:

- missing shadow work-item proof is an observer/backlog condition;
- it does **not** automatically become a public baseball-data deficit;
- genuine finality, schedule-authority, appearance-row, and material-correction deficits remain blocking.

The authoritative-mode projection remains stricter. Do not weaken blocker scope
merely to make shadow activation look healthier.

## 7. Current Daily Runtime-Budget Model

The August 6 incident investigation proved that three runtime quantities had
been conflated in prior discussion.

The current pre-mitigation model is:

```text
combined_ingestion_pool = min(
    configured_ingestion_cap,
    max(total_budget - elapsed_before_ingestion, 0) - final_phase_reserve
)

shadow_configured_allocation = combined_ingestion_pool * shadow_share

legacy_gamelog_budget = combined_ingestion_pool - shadow_actual_elapsed
```

At the incident baseline:

- total internal budget: `1080 s`;
- final-phase reserve: `300 s`;
- combined ingestion cap: `720 s`;
- shadow share: `25%` in non-authoritative shadow mode.

The configured ingestion cap is **not** the legacy GameLog budget. The shadow
lane consumes from the same pool and returns unused time only when it finishes
early.

## 8. August 6 OPS-002 Incident

Four full daily syncs were examined.

Three failed closed because publication-critical GameLog work exhausted the
runtime available to it. One recovery run succeeded after a prior failed pass
had already performed durable upstream/partial work.

Critical production facts:

- candidates `359`, `361`, and `362` were withheld;
- snapshot `360` remained the last trusted served snapshot;
- the appearance-ledger proof remained safe;
- no shadow write or authority transfer occurred;
- the processes were not killed by the shell timeout — they completed and
  returned non-zero because required publication proof failed.

This is a success of **fail-closed safety**, not proof of healthy current
operation.

### Degradation boundary

During the failed runs:

- Dashboard safely continued serving snapshot `360`, but it was frozen at its existing data-through date;
- live Team Board reads could consume partially updated GameLog state;
- Compare could become asymmetrically fresh between teams;
- Tonight refresh was skipped on the failed cycles;
- downstream enrichment/static preview jobs were skipped because `public-sync` failed.

Therefore:

> **Safe historical serving is not equivalent to healthy current serving.**

Any operational report must state both when they differ.

## 9. OPS-002 Immediate Mitigation Contract

Issue #620 owns the bounded mitigation. The approved scope is runtime headroom
and observability only:

- `DAILY_SYNC_TOTAL_BUDGET_SECONDS`: `1080 -> 2200`;
- daily command/shell timeout: `20 min -> 40 min`;
- `public-sync.timeout-minutes`: `40 -> 60`;
- `DAILY_SYNC_INGESTION_BUDGET_SECONDS`: `720 -> 1500`;
- `DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS`: remains `300`;
- report the configured cap, combined pool, shadow configured allocation,
  shadow actual elapsed, and legacy GameLog remainder separately.

This mitigation grants **no** change to:

- game-driven mode;
- legacy writer authority;
- publication gates;
- snapshot eligibility;
- backfill authority;
- schema/migrations;
- retry semantics;
- continuation/resume semantics.

It is explicitly a reliability bridge, not the permanent architecture.

## 10. OPS-002 Production Proof

Do not close the incident when implementation merges.

Required proof:

1. one separately authorized controlled manual daily recovery run succeeds;
2. `budget_exhausted_pitchers == 0`;
3. `publication_critical_failed == 0`;
4. a new candidate snapshot is published, selected, and served;
5. appearance-ledger proof passes;
6. dashboard-cache proof passes;
7. shadow remains zero-write;
8. three consecutive **scheduled** daily runs satisfy the same completion criteria.

The manual recovery run does not substitute for the three-scheduled-run window.

## 11. Permanent Work-Reduction Direction

Longer timeouts are not the intended end state.

After mitigation receives production proof, permanent correction should reduce
work volume. Approved investigation directions are:

- prefilter GameLog candidates before one-call-per-pitcher season-log work;
- make roster synchronization incremental rather than repeatedly fetching the
  same full roster families;
- make transaction synchronization incremental rather than replaying a fixed
  window every full run.

Stage reordering, retries, continuation/resume machinery, schema changes, and
broader authority transfer remain separate decisions.

Manual retry must not remain load-bearing recovery behavior.

## 12. Publication Failure Isolation

A failed downstream artifact or presentation step must not roll back completed
canonical game ingestion.

League snapshot and team-progressive publication remain independent lanes with
separate gates. One may act as an availability backstop for the other, but
neither is allowed to weaken the other's evidence contract.

## 13. Team State Population Contract

The Team State population must be the same canonical current active bullpen
population whose coverage authorizes the read.

Do not derive Team State from every team-associated pitcher carrying a fatigue
row. Starters, injured/off-active arms, and other pitchers outside the canonical
active bullpen may remain visible as context but must not decide the team's
Fresh / Stretched / Vulnerable state.

If membership authority is incomplete, the dependent Team State fails closed.

## 14. GameLog Balls Fallback

When the canonical GameLog split omits `balls`, the completed-game official box
score may supply that field only when the official pitch-accounting triple
validates under the governed fallback contract.

This is a field-specific source-authority rule. It does not permit wholesale
source substitution or choosing the more convenient value.

## 15. Retired Game 824487 Repair

The single-purpose game `824487` source-revision checkpoint repair is complete.
It was:

1. audited read-only;
2. verified as repair-required and safe;
3. applied through the exact one-row governed path;
4. independently re-observed as already applied with zero additional writes;
5. retired from the repository.

The retired workflow must not be dispatched or reintroduced. It grants no
broader correction, game-driven write, or publication authority.

## 16. Operator Response to a Failed Daily Sync

When a daily run fails:

1. identify whether `public-sync`, `shadow-activation-health`, or both failed;
2. read the publication-critical summary before reading observer health;
3. verify which trusted snapshot is currently selected/served and its
   `data_through` date;
4. determine whether the failure is a real baseball deficit, runtime/budget
   exhaustion, source conflict, or observer-only evidence problem;
5. preserve logs/artifacts and exact run identifiers;
6. do not weaken a gate or broaden a write path to make the next run green;
7. do not dispatch an old repair workflow merely because a similarly named
   incident occurred before;
8. follow the active issue/runbook acceptance criteria for recovery.

If the failure mode does not have a governed procedure, stop at read-only
investigation rather than inventing a production mutation.

## 17. Definition of a Healthy Daily Cycle

A healthy cycle is more than “the previous snapshot still loads.”

At minimum:

- required acquisition completes within its governed budget;
- publication-critical GameLog work has no budget-exhausted pitchers;
- publication-critical failure count is zero;
- candidate snapshot gates pass or withhold for a real, explained baseball
  deficit;
- deep appearance-ledger proof passes;
- the intended published snapshot is selected and served;
- Dashboard cache verification passes;
- Tonight/current downstream products refresh when the mode requires them;
- shadow remains zero-write and reports its own verdict independently;
- public surfaces expose the correct represented baseball date.

## 18. Related Current Authorities

- [Platform Architecture & Operations Manual](../canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md)
- [Bullpen Intelligence Standard](../canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md)
- [Product Roadmap & Decision Ledger](../canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md)
- [Daily publication-critical contract](DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md)
- [Game-driven daily ingestion subsystem](GAME_DRIVEN_DAILY_INGESTION.md)
- [August 6 runtime-budget incident evidence](../audits/DAILY_SYNC_RUNTIME_BUDGET_EXHAUSTION_2026-08-06.md)
- GitHub issue `#620` — OPS-002
- GitHub issue `#593` — OPS-001 scheduled observation closeout
