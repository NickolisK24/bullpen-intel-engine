# BaseballOS Sync Pipeline — Execution Order, Authority, and Trust Gates

**Status:** Current operational runbook  
**Authority:** Secondary to `docs/canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md`, which owns the current sync and publication authority posture. This document owns execution order and trust-gate detail.  
**Owner:** Nickolis Kacludis  
**Last reviewed:** August 31, 2026
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
- production execution is authorized by an explicit source contract:
  `github_schedule`, `external_schedule`, or governed `incident_recovery`;
- scheduled intraday repair is retired for the remainder of 2026; its governed
  implementation remains available only through controlled manual dispatch;
- the existence of qualification machinery does not grant broader mutation authority.

Do not describe the game-driven lane as `off`: daily and postgame are actively
observed in shadow. Do not describe the legacy per-pitcher GameLog lane as
retired: it remains authoritative until a separate explicit authority-transfer
decision is made. Ordinary manual production execution remains prohibited;
incident recovery is a distinct, confirmed, permanently recorded authority.

## 2. Operating Modes

| Mode | Trigger | Current meaning |
|---|---|---|
| `daily` | Render primary, GitHub fallback, or governed recovery | legacy writer authoritative; game-driven lane shadow-observed; trusted snapshot/public cache attempted after gates |
| `postgame` | Render primary, GitHub fallback, or governed recovery | completed-game reconciliation; game-driven lane shadow-observed after the legacy path; trusted publication follows existing gates |
| `morning` | Render primary or GitHub fallback | rolling schedule correction and Tonight cache coherence |
| `backfill` | manual only with explicit date | governed historical replay; no automatic broad backfill authority |
| `intraday` | manual dispatch only; no scheduled repair for the remainder of 2026 | read-only audit or separately governed dormant repair; does not silently gain write authority |

Exact cron values are runtime configuration in the workflow file and may change
without changing the mode semantics above.

### Scheduled delivery reliability

Render Cron is the primary trigger authority. GitHub Actions remains a delayed
fallback while the independent lane establishes production proof. Both call
`run_due_sync.py`; BaseballOS, not either scheduler, decides whether the durable
window is due. All cron expressions are UTC and do not observe DST.

| Mode | Render primary | GitHub fallback | EDT primary / fallback | EST primary / fallback |
|---|---|---|---|---|
| `postgame` | `5 2,4,6 * * *` | `11 2,4,6 * * *` | 10:05/10:11 PM, 12:05/12:11 AM, 2:05/2:11 AM | 9:05/9:11 PM, 11:05/11:11 PM, 1:05/1:11 AM |
| `daily` | `5 10 * * *` | `17 10 * * *` | 6:05/6:17 AM | 5:05/5:17 AM |
| morning correction | `5 14 * * *` | `23 14 * * *` | 10:05/10:23 AM | 9:05/9:23 AM |

The fallback gaps are shorter than the longest lane budgets. If the primary is
still running, the database advisory lock produces a controlled, non-destructive
blocked result; it never permits overlapping publication. A wider gap can be
adopted later from observed production runtimes without changing window identity.

`.github/workflows/baseballos-scheduler-health.yml` provides a manual, read-only
diagnostic with separate `github_scheduler`, `external_scheduler`, and
`production_freshness` verdicts. A failed GitHub run is still an observed
GitHub attempt; only an `executed` durable schedule attempt satisfies production
freshness. The diagnostic does not publish or enter the writer lane.

This repository still cannot provide a truly independent automatic watchdog
using GitHub Actions. Render or another external monitor must invoke
`check_scheduled_sync_health.py` and alert on its nonzero result. The diagnostic
is evidence tooling; alert routing remains an external configuration task.

### Execution authority and durable reconciliation

`sync_schedule_attempts` records execution source, mode, intended window,
scheduled/start/finish timestamps, executed/no-op/blocked/failed outcome,
linked `SyncRun`, snapshots before/after, publication outcome, and governed
recovery metadata. A successful attempt satisfies its window. A later trigger
for the same window records `already_satisfied` without entering baseball work.

The existing public PostgreSQL advisory lock remains authoritative across
GitHub, Render, recovery, and web processes. It is nonblocking and releases on
normal completion, exceptions, or database disconnect, so it cannot leave a
stale lock after process death. GitHub's `baseballos-sync` concurrency group is
retained as useful local protection, not cross-scheduler authority.

Scheduler != publication authority. A scheduler requests work. BaseballOS
validates the source, locks the public writer lane, reconciles the intended
window, and then applies every existing publication proof and integrity guard.

For production snapshot publication, the Team State proof is mandatory database
state, not runner-local output. The publisher resolves the all-30-team decisive
evidence, validates the partition and Contract A result, and flushes the
snapshot-linked proof row in the same transaction that advances the trusted
snapshot pointer. If proof generation or persistence fails, that transaction
does not commit and the previous trusted snapshot remains current. The optional
`TEAM_STATE_VNEXT_PROOF_PATH` export is downstream convenience only.

### Render Cron primary setup

The existing Render web service is dashboard-managed; this repository has no
root `render.yaml`. Do not add a Blueprint merely to create these jobs, because
that could accidentally take ownership of the existing production service.
Create three Render **Cron Job** services from
`NickolisK24/bullpen-intel-engine`, branch `main`, with repository root left
blank. Use `pip install -r backend/requirements.txt` as the build command and
these UTC schedules/commands:

| Job | Cron | Command |
|---|---|---|
| BaseballOS Daily primary | `5 10 * * *` | `python backend/scripts/run_due_sync.py --mode daily --execution-source external_schedule --scheduled-for "$(date -u +'%Y-%m-%dT10:05:00Z')" --days-back 7 --public-only` |
| BaseballOS postgame primary | `5 2,4,6 * * *` | `python backend/scripts/run_due_sync.py --mode postgame --execution-source external_schedule --scheduled-for "$(date -u +'%Y-%m-%dT%H:05:00Z')" --public-only` |
| BaseballOS morning primary | `5 14 * * *` | `python backend/scripts/run_due_sync.py --mode morning --execution-source external_schedule --scheduled-for "$(date -u +'%Y-%m-%dT14:05:00Z')" --public-only` |

Reuse the web service's protected environment group for `DATABASE_URL`,
`SECRET_KEY`, `ADMIN_API_TOKEN`, and any production publication dependencies.
Set `APP_ENV=production`, `AUTO_SYNC=false`,
`BASEBALLOS_SCHEDULER_AUTHORITY=render_cron_v1`, and
`BASEBALLOS_PRODUCTION_BRANCH=main`. Render supplies `RENDER=true`. Preserve
the daily shadow and proof variables currently set on the GitHub Daily step
when creating the Daily Cron environment; the shared runner does not weaken
those proof paths. Expected command ceilings are 40 minutes Daily, 20 minutes
postgame, and 5 minutes morning. Render cron expressions are UTC.

Apply `flask db upgrade` as a release/pre-deploy migration before enabling the
Cron Jobs. The Cron commands deliberately do not run migrations concurrently
with production work.

The 2026 trade-deadline repair window has passed, so
`.github/workflows/baseballos-intraday-repair.yml` has no `schedule` trigger.
Its `workflow_dispatch` trigger, shared `baseballos-sync` concurrency group,
writer guard, timeout, production-secret requirements, and fail-closed repair
contract remain intact as a dormant diagnostic/repair capability. It is not a
prerequisite for daily publication, postgame publication, Team Board serving,
transaction ingestion, roster authority, Today, Tonight, or generated content.
Daily and postgame authority are unchanged.

Any 2027 preseason reactivation review must re-audit this capability against
the then-current canonical public-state preparation and snapshot-publication
contract before restoring a schedule. Reactivation requires a separate reviewed
operations change; retaining manual dispatch is not approval to restore cron.

For the remainder of 2026, the production cadence is:

```text
Daily sync -> canonical morning baseline
Postgame sync -> completed-game workload/public-state updates
Intraday repair -> dormant/manual-only seasonal capability
```

## 3. Public Sync Order

Conceptually:

```text
schedule/finality preflight
-> source acquisition and canonical writes
-> derived workload/current state
-> trusted snapshot build
-> mandatory Team State proof flush (same transaction)
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

Required proof, over three consecutive **scheduled**, first-attempt daily runs:

1. `budget_exhausted_pitchers == 0`;
2. `publication_critical_failed == 0`;
3. a new candidate snapshot is published, selected, and served;
4. appearance-ledger proof passes;
5. dashboard-cache proof passes;
6. shadow remains zero-write.

`docs/current/TRUSTED_PUBLIC_SERVING_AUTHORITY.md` owns the full current OPS-002
criterion set and is authoritative where the two differ.

**Historical note.** An earlier version of this proof opened with "one separately
authorized controlled manual daily recovery run succeeds". D-051 retired that
criterion, because authoritative manual daily execution is intentionally
prohibited. A manually re-run scheduled job is likewise not eligible proof.

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

## 18. Generated-Content Publication (`static-team-story-preview`)

This is the only job in the workflow that writes to the repository, and the only
automated path by which anything reaches `main` without a pull request. D-053
governs it.

**Job:** `static-team-story-preview`. Runs only after `public-sync` succeeds, and
only on the daily lane (`17 10 * * *` or `workflow_dispatch mode=daily`). It holds
`contents: write`; every other job in this workflow is `contents: read`.

### Generator

`backend/scripts/export_team_story_pages.py`, via
`services/team_story_previews.write_team_story_pages`. It resolves ONE trusted
published dashboard snapshot, takes every board from the trusted public-serving
path, and stamps each page with the snapshot it came from. With no valid
published snapshot it writes nothing and exits non-zero — there is no
live-builder fallback and no fabricated present-tense claim.

### Generated paths

```text
frontend/public/team/{ABBR}/index.html   one per MLB club
frontend/public/team/index.html          invalid-team fallback
```

Nothing else. `frontend/public/og/baseballos-card.svg` is a static committed
asset that the generator never writes, and it is not part of this commit.

### Gates, in order

```text
export (--result-out writes the exporter's structured result)
-> delivery gate      backend/scripts/verify_generated_team_previews.py
-> npm ci             frontend/
-> npm test           frontend/
-> npm run build      frontend/
-> stage + tree identity
-> commit + tree equality proof
-> fast-forward push
```

The frontend commands and Node major are mirrored from the `frontend-tests` job
in `.github/workflows/ci.yml` so the gate and canonical CI cannot drift. No step
on this path carries `continue-on-error`.

The **delivery gate** proves the filesystem agrees with what the exporter
declared: every declared page present and non-empty, the fallback intact, no
stale page left behind, receipts present on every dated claim, one publication
snapshot across the whole set, and the withheld set on disk matching the declared
one. It decides no baseball meaning and imports no service, model, or Flask app.

Its input is the file the exporter writes to `--result-out`, never the exporter's
stdout. stdout is a mixed human/diagnostic stream — importing the exporter prints
a scheduler banner before `main` runs — so capturing it produces a file that does
not parse. The gate parses strictly and refuses what it cannot read; the fix for
that is a separate channel, not a looser parser.

### Tree-exact provenance

The claim BaseballOS makes is deliberately precise:

> The filesystem tree that passed the delivery gate, the frontend test suite, and
> the production build is byte-for-byte the tree the generated commit carries.

It is not "the generated commit SHA was tested" — a SHA cannot be tested before
it exists. The proof has two links: a sha256 digest of the generated files taken
before the frontend gate and recomputed after it must match, and `git write-tree`
taken from the index before any commit must equal `HEAD^{tree}` after it. The
equality check runs **before** the push; a mismatch fails the job with nothing
pushed.

### Automation identity

Automated commits are authored and committed as:

```text
BaseballOS Automation <baseballoshq@gmail.com>
```

never as a person, and never with AI or vendor attribution. The commit body
carries `Workflow-Run`, `Workflow-Run-Attempt`, `Source-SHA`, `Validated-Tree`,
`Snapshot-ID`, and `Data-Through`, taken from the exporter's structured result
rather than scraped from the rendered HTML, so `git show --format=fuller`
explains the commit without anyone having to guess its origin.

### Fail-closed behaviour

Any failing gate means no commit and no push. The previously published pages stay
exactly where they are and continue to state the baseball date they actually
describe — which is honest, and is the designed outcome rather than a
degradation. There is no fallback commit and no forced publication.

A run that generates no change stages nothing, creates no empty commit, and
exits successfully. Change detection compares the index after staging, not the
working tree, so a newly generated page cannot be mistaken for "no changes".

### Non-fast-forward behaviour

The push is fast-forward only — no `--force`, no `--force-with-lease`, no reset,
no automatic rebase or merge. If `main` advanced while the run was generating,
the push is refused and the job fails loudly. Human work is never overwritten to
publish a preview. The correct response is to let the next authorized scheduled
run publish; do not re-run the daily workflow to force it, which D-051 forbids
in any case.

### What does not follow

The generated push is made with the default `GITHUB_TOKEN`, so it still does not
trigger a follow-up CI run — and it is not supposed to. The whole point of the
gate is that validation happens before the commit becomes public repository
state, so no PAT, GitHub App, `repository_dispatch`, or recursive workflow
mechanism is needed or used.

## 19. Related Current Authorities

- [Platform Architecture & Operations Manual](../canonical/04_PLATFORM_ARCHITECTURE_OPERATIONS.md)
- [Bullpen Intelligence Standard](../canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md)
- [Product Roadmap & Decision Ledger](../canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md)
- [Daily publication-critical contract](DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md)
- [Game-driven daily ingestion subsystem](GAME_DRIVEN_DAILY_INGESTION.md)
- [August 6 runtime-budget incident evidence](../audits/DAILY_SYNC_RUNTIME_BUDGET_EXHAUSTION_2026-08-06.md)
- [Generated-content CI gate and automation identity (D-053)](../decisions/2026-08-12-generated-content-ci-gate-and-automation-identity.md)
- GitHub issue `#620` — OPS-002
- GitHub issue `#593` — OPS-001 scheduled observation closeout
- GitHub issue `#598` — CI-003 generated-content CI validation
