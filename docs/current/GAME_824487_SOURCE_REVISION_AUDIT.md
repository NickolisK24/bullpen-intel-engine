# Game 824487 source-revision audit

**Status: audit package implemented. The production audit has NOT been executed.
No conclusion has been reached. No repair is authorized.**

Nothing in this document states a root cause, because the audit has not run in
production yet. It describes what the package does, how to read what it will
produce, and how to remove it afterwards.

---

## The exact scope

One game and two retained scheduled daily runs. Nothing else.

| | value |
| :--- | :--- |
| `game_pk` | 824487 |
| represented game date | 2026-07-29 |
| appearances extracted, both runs | 12 |
| reconciliation status, both runs | all 12 unchanged |
| per-game reconciliation-plan fingerprint, both runs | `8cb7eacbc0e0a6da908ea759c836e585a2e690a99280cd8f274275fc7d1709ec` |

### Prior clean scheduled daily run

| | value |
| :--- | :--- |
| workflow run id | 30902544622 |
| branch / head | `main` / `59176cc7076b5d22a6542a491cc93e9710b9b267` |
| artifact | `game-driven-shadow-30902544622` (id 8889875247) |
| expected digest | `sha256:2d5d9584eee09b7a2719efa4c33d0b0bbeea85ddc6b5fb74874db81fb4693199` |
| observed source revision | `90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0` |
| activation result | PASS |

### Failed observer scheduled daily run

| | value |
| :--- | :--- |
| workflow run id | 30999087370 |
| branch / head | `main` / `a27631d9d954c65f6a9aae79d0e1df6774719305` |
| artifact | `game-driven-shadow-30999087370` (id 8927687851) |
| expected digest | `sha256:adecc4bbe15b3f64ed60cccd46a0f370355018aae01079fa65d2cb5f8a8446de` |
| observed source revision | `a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4` |
| activation result | FAILED (`source_revision_match` false, `all_projected_targets_realized` false) |

Everything else about that run was clean: the trusted public daily sync
succeeded, snapshot 353 was published and selected for serving with its
publication proof verified, the appearance ledger reconciled 120/120 games and
1012/1012 appearances with zero mismatches, and the game-driven shadow lane
completed all 94 planned games — 778 expected rows, 778 unchanged, zero
inserts, zero updates, zero blocks, zero writes, zero commits, zero per-run
dead letters. The only state marked changed was game 824487's source revision.

These facts are treated as EXPECTATIONS the audit verifies against the retained
artifacts. They are not copied into its result.

---

## Why `source_revision` is not a raw-payload hash

MLB publishes no box-score revision number. Rather than invent one, the
repository derives an observed-content marker from the canonical extracted
fields themselves:

```
services.game_appearance_extraction.appearance_set_fingerprint(appearances)
```

That is SHA-256 over the deterministic **normalized appearance matrix**, not
over the MLB response. Cosmetic payload churn — display names, hydration
changes, ordering — cannot move it. A governed field changing does.

### The 14 governed fingerprint fields

1. `pitcher_mlb_id`
2. `team_id`
3. `opponent_team_id`
4. `appearance_role`
5. `games_started`
6. `outs_recorded`
7. `earned_runs`
8. `runs_allowed`
9. `hits_allowed`
10. `walks`
11. `strikeouts`
12. `home_runs_allowed`
13. `batters_faced`
14. `pitches_thrown`

The audit reads this list from the code at each historical SHA rather than
assuming it was the same list on both dates.

### Why two hashes cannot reveal a field delta

Two different digests prove that exactly one of these is true, and nothing
finer:

* the normalized fingerprint input differed;
* the fingerprint constructor or an upstream normalization function differed;
* a retained artifact is internally inconsistent;
* the computation was nondeterministic or defective.

SHA-256 is not invertible and carries no field structure. The audit therefore
never reverses a digest and never guesses a field from one. Where positive
retained evidence does not exist, it says so.

### The evidence limit this audit expects to hit

The retained per-game entry in a shadow artifact carries aggregate counts, the
observed source revision, and the per-game plan fingerprint. Row-level detail
is retained only for rows whose projected action is **not** `unchanged`. A game
whose 12 appearances were all unchanged therefore retains no per-appearance
values at all in either run.

The audit does not assume this — it scans both documents for any structure
pairing a pitcher identity with a governed field VALUE and reports what it
found. If nothing is found, that absence is itself a material finding, recorded
as `not_retained`.

---

## Artifact requirements

Both artifacts are downloaded by exact repository, exact run id, exact artifact
id, and exact name, BEFORE any database advisory lock is acquired. Each is then
verified from INSIDE its documents — never from a directory name:

* internal run id and head SHA (`handoff-metadata.json`);
* cycle kind and runner exit code (`*-activation-summary.json`);
* configured mode, `writes_enabled: false`, `publication_authoritative: false`,
  game 824487 membership, source revision, plan fingerprint, 12 appearances,
  12 unchanged, and zero insert/update/block (`*-sync-summary.json`).

| observation | outcome |
| :--- | :--- |
| required artifact missing | UNPROVEN |
| required file missing inside an artifact | UNPROVEN |
| metadata mismatch (run id, head, cycle, branch, mode, counts) | FAILED |
| digest exposed by GitHub and different from the expected digest | FAILED |
| digest no longer exposed by the API | UNVERIFIED, reported honestly |

---

## Workflow and confirmation

```
Workflow: Manual Game 824487 Source Revision Audit
File:     .github/workflows/manual-game-824487-source-revision-audit.yml
Trigger:  workflow_dispatch ONLY
```

Required inputs:

* `expected_main_sha` — full 40-character lowercase SHA; must equal the
  resolved `github.sha`;
* `confirmation` — must be exactly
  `AUDIT_GAME_824487_SOURCE_REVISION_30999087370`.

The run refuses, before any artifact download or database access, when the
repository is not `NickolisK24/bullpen-intel-engine`, the ref is not
`refs/heads/main`, the actor is not the repository owner, the SHA does not
match, the confirmation does not match exactly, or any required secret is
absent.

Permissions are `contents: read` and `actions: read`. Checkout uses
`fetch-depth: 0`, because the audit compares code at both historical SHAs.
`ADMIN_API_TOKEN` is present only because `config.py` refuses to boot under
`APP_ENV=production` without it; the audit never reads it, makes no HTTP call
to this service, and invokes no admin endpoint.

---

## Read-only guarantees

Three independent controls, all reused from the merged audit packages rather
than reinvented:

1. **Acquire-only public sync advisory lock.** The same lock identity the
   daily, postgame, and backfill writers take. It never creates, reclaims, or
   updates a `SyncRun`. Contention returns UNPROVEN immediately — the audit
   never waits and never queues.
2. **PostgreSQL read-only transaction with a bounded refused write probe.** The
   audit issues exactly one SQL write statement: the proof itself, bounded by
   `WHERE 1 = 0`, expected to be REFUSED, and rolled back either way. A probe
   that is ACCEPTED is FAILED.
3. **Before/after scoped content fingerprints.** Full governed row content and
   timestamps — not row counts — across every scope the game touches:
   `scheduled_games`, `game_logs`, `game_ingestion_work_items`,
   `postgame_processed_games`, `team_game_pitching_splits`,
   `completed_game_contexts`, `game_play_by_play_events`, `sync_failures`, plus
   the local `Pitcher` identity rows for the official pitchers. Correction
   provenance and appearance-team authority are COLUMNAR in this schema, so
   full-row digests of `game_logs` and `game_ingestion_work_items` already
   cover them; there is no separate history table.

Any changed scoped fingerprint is FAILED. An uncomputable required fingerprint
is UNPROVEN.

### Source-call budget

The canonical extraction path was inspected, not guessed: the lane synthesizes
its game payload from the durable schedule ledger and makes exactly **one**
upstream request per game — the box score. The budget is therefore one
box-score call (required) and one corroborating exact-game schedule call
(optional, and not needed on the normal path).

Every call goes through a counting guard installed over the canonical MLB
client, so a call the budget refuses never reaches the wire even when it is
attempted from deep inside the canonical reconciliation path. Reported counts
and actual counts are the same numbers by construction. Spending an allowance
exactly is a correct run; only a REQUIRED call that is refused or fails makes a
conclusion unproven.

### What the audit never does

No GameLog insert or update, no `ScheduledGame` or `GameIngestionWorkItem`
mutation, no `source_revision` update, no work-item creation, no checkpoint
advancement, no correction-provenance write, no pitcher or appearance-team
mutation, no `SyncRun` creation, no snapshot generation/publication/selection,
no Tonight refresh, no fatigue recalculation, no marker reset, no backfill, no
replay, no rerun of either historical daily sync, no call to the production
ingestion writer, no repair function, no mode change, no activation, no
rollback, no validator weakening, no migration, and no schema change.

Standing production state is unchanged by this package: the daily and postgame
game-driven lanes remain shadow, backfill remains off, automated writes remain
prohibited, authoritative publication mode remains prohibited, and publication
authority remains with the existing trusted path.

**The global dead-letter backlog remains 1,389.** The audit may report only
that it created zero dead letters. It never reports the backlog as zero.

---

## Result vocabulary and exit codes

| result | exit | meaning |
| :--- | :--- | :--- |
| `COMPLETE_ROOT_CAUSE_IDENTIFIED` | 0 | Positive evidence identifies the root condition and materiality. |
| `COMPLETE_SCOPE_AND_MATERIALITY_IDENTIFIED_FIELD_DELTA_UNAVAILABLE` | 0 | The revision change is proven, code drift is ruled in or out, current materiality is established, and the exact historical field cannot be recovered because prior normalized row-level evidence was not retained. |
| `COMPLETE_NO_CURRENT_DEFECT` | 0 | Current source and current canonical state are clean; there is no currently actionable baseball defect. |
| `FAILED` | 1 | The audit's own safety or integrity contract was violated. |
| `UNPROVEN` | 2 | Required evidence could not be obtained or validated. |

`FAILED` is reserved for violations of the audit's own contract: a database
mutation, an accepted write probe, a changed before/after fingerprint, wrong
artifact identity, a digest mismatch, the wrong game, a hidden or unbudgeted
source call, a nondeterministic fingerprint over identical normalized content,
a secret-scan failure, or a workflow safety violation.

**A platform defect discovered by a successful read-only audit is not a FAILED
audit.** If the exit code meant "the platform is broken" in one run and "the
audit is broken" in another, it would mean nothing in either.

### Reading an evidence-limit conclusion

`COMPLETE_SCOPE_AND_MATERIALITY_IDENTIFIED_FIELD_DELTA_UNAVAILABLE` is a
success, not a shrug. It means the audit **proved** the evidence limit rather
than merely failing to find something: it verified both artifacts, scanned both
for row-level values and found none, compared every relevant symbol at both
historical SHAs, established what the source says today, and established
whether the current state is materially wrong. What it declines to do is name a
baseball field it cannot source. Question 9 lists exactly which evidence was
available and exactly which evidence would have been required.

### The twelve questions

The audit answers each independently: (1) artifact revision change,
(2) plan stability, (3) code-path drift, (4) current official revision,
(5) fingerprint determinism, (6) current official versus stored canonical
state, (7) durable checkpoint evidence, (8) correction and historical evidence,
(9) exact historical field delta, (10) activation-failure causality,
(11) materiality across five independent dimensions, (12) operational
consequence.

Question 11 never collapses into a single label. It reports root condition,
current materiality, persistence, historical field identification, and
checkpoint state separately.

Question 12 is informational only. **The audit authorizes no mutation, a
recommendation is not approval, and any future repair requires a separate
exact-scope package and separate explicit approval.**

---

## Uploaded artifact

`game-824487-source-revision-audit-<run id>`, retained 90 days, containing:

* `source-revision-audit.json` — the full evidence document;
* `source-revision-audit-summary.md` — the human-readable summary;
* `source-revision-field-matrix.json` — the machine-readable field matrix;
* `source-revision-code-drift.json` — the symbol-level comparison;
* `source-revision-read-only-proof.json` — read-only controls and source-call
  accounting.

The repository's established secret scanner runs BEFORE upload and gates it. A
scanner failure fails the workflow and the artifact never leaves the runner.
Raw MLB payloads, database URLs, tokens, environment dumps, connection strings,
stack traces, authorization headers, and raw production table dumps are never
written.

### The field matrix

One row per pitcher per governed field. Every row carries
`participates_in_source_revision`, `participates_in_writer_target` (from the
canonical plan), the current official and current stored values, the historical
values, and — always — an explicit evidence status drawn from `proven`,
`absent`, `not_retained`, `inconsistent`, `unproven`.

A historical value that was never retained is reported as `null` **with** a
status of `not_retained`. `null` is a legitimate baseball value, so the status,
not the value, is what distinguishes "absent from the source" from "never
recorded anywhere".

Integer recorded outs are the innings authority. A decimal innings display
difference is classified `derived_display_only` and is never called a baseball
correction.

---

## How to remove this package later

It is additive and self-contained. Deleting these files removes it completely,
and nothing in production imports any of them:

```
.github/workflows/manual-game-824487-source-revision-audit.yml
backend/services/game_source_revision_audit.py
backend/scripts/run_game_source_revision_audit.py
backend/tests/test_game_source_revision_audit_contract.py
backend/tests/test_game_source_revision_audit_artifacts.py
backend/tests/test_game_source_revision_audit_execution.py
backend/tests/test_game_source_revision_audit_classification.py
backend/tests/test_game_source_revision_audit_code_drift.py
docs/current/GAME_824487_SOURCE_REVISION_AUDIT.md
```

Then remove the five test paths from `backend/tests/ci_shard_manifest.json` and
re-run `python scripts/ci_shard.py verify` from `backend/`. No migration is
involved, no production module changes, and the Alembic head is untouched.
