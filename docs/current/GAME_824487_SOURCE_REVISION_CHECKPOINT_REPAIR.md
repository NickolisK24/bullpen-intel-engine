# Game 824487 source-revision checkpoint repair

**Status: package implemented and validated locally. The repair has NOT been
executed. No production database session has been opened by this package. No
production row has been mutated. Nothing here is authorization to run it.**

This document describes a reviewable repair package: what it may change, what
it may never change, every precondition it re-observes before it changes
anything, how it proves afterwards that it changed nothing else, and how to
remove it when it is done.

Running it is a separate decision. The merged source-revision audit authorizes
no mutation — a recommendation is not approval — and this document does not
convert one into the other.

---

## 1. The exact scope

One column, on one already-existing row.

| | value |
| :--- | :--- |
| game | 824487 |
| represented date | 2026-07-29 |
| table | `game_ingestion_work_items` |
| identity column | `mlb_game_pk` |
| target column | `source_revision` |
| expected existing value | `90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0` |
| intended new value | `a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4` |
| rows the run may affect | exactly 1 |
| permitted changed columns | `source_revision`, `updated_at` |

Every one of these is a reviewed literal in code. None of them is an input,
an argument, or an environment variable. A dispatch cannot select **what**
runs — only **whether** it runs, and which of two operations it runs.

---

## 2. Why `updated_at` is in the permitted set

`GameIngestionWorkItem.updated_at` is declared
`onupdate=utc_now_naive`, which fires on **any** UPDATE of the row. The single
permitted change therefore moves two columns, not one.

That is disclosed rather than hidden:

* the permitted changed-column set is exactly `{source_revision, updated_at}`;
* `source_revision` is the **governed** change — the one decision under review;
* `updated_at` is an **automatic bookkeeping side effect** of making it;
* any third changed column is a contract violation and fails the run.

Pinning `updated_at` back to its old value was considered and rejected.
Falsifying a bookkeeping timestamp to make a diff look smaller is worse than
disclosing the timestamp. A package contract test asserts the model really
declares `onupdate`, so if that ever stopped being true the disclosure would
fail rather than quietly become wrong.

---

## 3. Why this is a checkpoint repair and not a data repair

`source_revision` is
`game_appearance_extraction.appearance_set_fingerprint` — SHA-256 over the
deterministic normalized appearance matrix over 14 governed fields. It is an
observed-content **marker on the ingestion checkpoint**, not a baseball value.

Moving it changes no pitching line, no inning, no earned run, no roster
association, and no public artifact. What it changes is what the daily lane
believes it has already observed for this game.

That is exactly why the repair is gated on the canonical appearance data being
**already correct**. A checkpoint may only be advanced to describe evidence
that has actually been observed and already agrees with storage. If the data
were wrong, the correct response would be a data repair — and this package
refuses rather than becoming one.

---

## 4. The two operations

```
Workflow: Manual Game 824487 Source Revision Checkpoint Repair
File:     .github/workflows/manual-game-824487-source-revision-checkpoint-repair.yml
Trigger:  workflow_dispatch ONLY
```

| operation | what it does | writes |
| :--- | :--- | :--- |
| `verify` | Re-observes every precondition live and reports whether the change is currently required and currently safe. | never, under any outcome |
| `apply` | Performs the one approved change — and only after re-observing every precondition again against a row it holds a lock on. | at most one row, one governed column |

Required inputs:

* `operation` — a closed choice of exactly `verify` or `apply`, defaulting to
  `verify`;
* `expected_main_sha` — full 40-character lowercase SHA; must equal the
  resolved `github.sha`;
* `confirmation` — **per-operation**, matched against the selected operation
  only:
  * `VERIFY_GAME_824487_SOURCE_REVISION_CHECKPOINT`
  * `APPLY_GAME_824487_SOURCE_REVISION_CHECKPOINT`
* `operator_note` — optional, sanitized, informational, and incapable of
  affecting authorization or any verdict.

A confirmation reviewed and typed for a verify run **cannot** start an apply
run. That is checked twice: once in the workflow preflight before checkout,
and again in the runner's own authorization.

The run refuses, before any database session is opened, when the repository is
not `NickolisK24/bullpen-intel-engine`, the ref is not `refs/heads/main`, the
actor is not the repository owner, the SHA does not match, the operation is not
in the closed vocabulary, the confirmation does not match that operation
exactly, or any required secret is absent.

Permissions are `contents: read` and nothing else. No `actions: write`, no
`contents: write`, no `pull-requests: write`, no `deployments: write`, no
`id-token`. No existing deployment mechanism requires any of them, so none was
added. `ADMIN_API_TOKEN` is present only because `config.py` refuses to boot
under `APP_ENV=production` without it; this package never reads the value,
makes no HTTP call to this service, and invokes no admin endpoint.

The workflow shares the `baseballos-sync` concurrency group with the production
sync lane, with `cancel-in-progress: false` — so this run can never overlap a
production writer, and a repair halfway through its own transaction can never
be cancelled by a later dispatch.

---

## 5. The sixteen preconditions

Every one is re-observed live at execution time. None is read from the audit's
conclusion, from a retained artifact, or from a stored belief. **A conclusion
is not a precondition.**

| precondition | requirement |
| :--- | :--- |
| `target_row_exists` | exactly one existing row for game 824487 |
| `target_row_is_unique` | candidate row count is 1 |
| `target_row_is_the_target_game` | `mlb_game_pk == 824487` |
| `target_row_represented_date_matches` | `represented_date == 2026-07-29` |
| `target_row_status_is_completed` | `status == 'completed'` |
| `existing_revision_is_the_expected_old_value` | the stored value is the expected old digest |
| `intended_revision_differs_from_existing` | the intended value is not already stored |
| `appearance_population_size_verified` | the population size is verified from live durable state |
| `stored_appearance_count_matches_population` | stored canonical rows equal that size |
| `current_official_source_observed` | today's box score was fetched and extracted |
| `current_official_source_conclusion_eligible` | completeness is `complete_and_comparable` |
| `current_official_revision_is_the_intended_value` | today's set fingerprints to the intended digest |
| `no_governed_fingerprint_field_differs` | no governed field differs from storage |
| `every_difference_is_derived_display_only` | every observed difference is `derived_display_only` |
| `canonical_plan_proposes_no_mutation` | the canonical reconciler proposes no insert, update, or blocked row |
| `governed_scope_fingerprints_observed` | per-table digests were computed |

Each carries a **three-way state**, never a boolean:

`satisfied` · `violated` · `not_observed`

`violated` and `not_observed` are different facts and contribute **different**
reason codes. "The stored value is some third digest" and "the database was
never opened" both sound negative and mean completely different things. A
package contract test asserts that no precondition's refusal reason and
unproven reason are ever the same code.

### Two preconditions that are easy to get backwards

**`no_governed_fingerprint_field_differs` is not "the differing-row list is
empty."** The merged audit observed six `innings_pitched` differences on this
game and still classified current materiality as
`non_material_to_canonical_writer_target`, because integer recorded outs are
the innings authority and `innings_pitched` is deliberately **not** a
fingerprint field. Requiring an empty differing-row list would make this repair
refuse forever on a difference that cannot move the digest. The requirement is
therefore two separate claims: no **governed** field differs, and every
observed difference is **`derived_display_only`**.

**`intended_revision_differs_from_existing` is the one violated precondition
that is not a refusal.** A row already holding the intended value means there
is nothing to do. That is `REPAIR_NOT_REQUIRED` with exit 0 — resolved ahead of
`REPAIR_REFUSED` so an already-applied repair reads as done rather than as
declined. It is still reported as a violated precondition rather than quietly
reclassified.

---

## 6. Where the population size comes from, and why not from the audit

The merged audit establishes "how many appearances this game has" from the two
retained shadow artifacts. **Those artifacts expire** — the current pair expires
2026-11-03. A repair that may be dispatched later must not depend on evidence
with an expiry date.

This package therefore sources the expected population size from **live durable
state**:

* the checkpoint's own `rows_expected`;
* `rows_reconciled`, which must equal it;
* the count of canonical appearance rows actually stored, which must equal both.

All three are re-observed at execution time, and all three must agree before
the number is usable. The audit's locked `EXPECTED_APPEARANCE_COUNT` is
deliberately **not** consulted: a constant is not an observation.

The table's completion CHECK constraint already ties `rows_reconciled` to
`rows_expected` for a completed row. It is checked here anyway — a guard that
trusts a constraint it never checked is not a guard.

---

## 7. The current-source completeness gate

Every non-refusal outcome depends on a single flag,
`conclusion_eligible`, which is true only for `complete_and_comparable`.

| completeness state | conclusion eligible |
| :--- | :--- |
| `complete_and_comparable` | **yes** |
| `source_unavailable` | no |
| `empty_official_set` | no |
| `database_unavailable` | no |
| `matrix_unproven` | no |
| `population_expectation_unproven` | no |
| `current_count_contradicts_population` | no |
| `duplicate_official_identities` | no |
| `duplicate_stored_identities` | no |
| `duplicate_identities_both_sides` | no |
| `official_only_members_present` | no |
| `stored_only_members_present` | no |
| `both_directions_mismatch` | no |

**Exact membership equality is necessary and not sufficient.** Two
symmetrically truncated sets match each other while both remain incomplete: a
payload carrying six of twelve appearances compared against storage holding
exactly those same six produces matching membership and zero differing rows
while the game still has twelve. The observed count is therefore compared
against the live population expectation **before** membership is consulted.

This package is protected twice over against that case: the population
expectation itself notices that storage no longer holds the number of
appearances the checkpoint recorded, so a symmetrically truncated pair never
reaches the membership test at all.

---

## 8. Read-only guarantees during observation

Every observation happens inside a proven read-only transaction — **including
in apply mode**. The writable transaction is opened only after every
precondition has already been satisfied, and it does exactly one thing.

Three controls, all reused from the merged packages rather than reinvented:

1. **Acquire-only public sync advisory lock.** The same lock identity the
   daily, postgame, and backfill writers take. It never creates, reclaims, or
   updates a `SyncRun`. Contention returns UNPROVEN immediately — this package
   never waits and never queues. The full lifecycle gates the verdict: a lock
   that was acquired and never provably released is a contract violation, and
   process termination is not release evidence.
2. **PostgreSQL read-only transaction with a bounded refused write probe.**
   Exactly one SQL write statement is issued during observation: the proof
   itself, bounded by `WHERE 1 = 0`, expected to be REFUSED, and rolled back
   either way. A probe that is ACCEPTED is a contract violation.
3. **Before/after scoped content fingerprints.** Full governed row content and
   timestamps — not row counts — across every scope the game touches. During
   the read phase, any changed table is a contract violation on a verify run
   and a refusal on an apply run.

### The source-call budget

One bounded box-score call, through the merged audit's counting guard installed
over the canonical MLB client. A duplicate or hidden call is caught rather than
assumed away, and reported counts and actual counts are the same numbers by
construction.

---

## 9. How the apply proves it stayed in scope

The apply transaction is guarded four independent ways, and every one of them
is a positive observation rather than an absence of an error.

1. **Row lock and re-validation.** The row is taken with
   `SELECT ... FOR UPDATE NOWAIT` — never waiting — and every row-level
   precondition is re-checked against the **locked** row. The read-only
   observation and the write transaction are not the same instant; a checkpoint
   that moved in between is a different row than the one that was approved, and
   it is refused. Any column at all differing from the observed snapshot
   triggers `target_row_modified_concurrently`.
2. **Full-column snapshot diff.** Every mapped column is snapshotted before and
   after, read by SQLAlchemy inspection rather than by a hand-written list — a
   hand list silently stops covering a column somebody adds later, and the whole
   scope proof rests on this snapshot being complete. The observed delta must be
   exactly `{source_revision, updated_at}`.
3. **ORM mutation-scope guard.** A `before_flush` listener records every
   creation, deletion, and changed-attribute set. It must observe zero
   creations, zero deletions, exactly the target object, and exactly
   `['source_revision']`. (`updated_at` does not appear here: the model's
   `onupdate` default is applied by the flush process *after* `before_flush`
   runs, which is why the snapshot diff — not this guard — is the authoritative
   claim.)
4. **Statement accounting.** An `after_cursor_execute` listener records every
   SQL write statement the connection actually issued. It must observe exactly
   one UPDATE naming the target table, with a row count of exactly one, and no
   other write statement of any kind. This proves what the **database** was
   told, which is a stronger claim than what the session intended: a raw
   statement issued from anywhere is visible here even though no ORM object was
   made dirty. Statement **text** is never retained — only a class, a row count,
   and one boolean.

Plus two fingerprint proofs after the commit:

* **In-scope**: exactly one `[scope, table]` pair may have moved, and it must be
  `[exact_game_824487, game_ingestion_work_items]`. A target table that did
  **not** move is equally a violation — a repair that reported itself without
  moving the row is not a repair.
* **Out-of-scope**: a full-content digest and row count of every row in
  `game_ingestion_work_items` that is **not** game 824487, before and after.
  Another game's checkpoint moving is a contract violation. This complement
  proof covers the one table any statement in this package names; no statement
  here names any other table.

**A scope violation observed before the commit is rolled back, not committed
and reported.** The guard checks run after the flush and before the commit, and
that is the last point at which undoing is still possible, so it is taken.

---

## 10. Result vocabulary and exit codes

| result | exit | meaning |
| :--- | :--- | :--- |
| `VERIFIED_REPAIR_REQUIRED_AND_SAFE` | 0 | Every precondition satisfied on a verify run. Evidence for a human decision, not that decision. |
| `REPAIR_NOT_REQUIRED` | 0 | The checkpoint already holds the intended value. |
| `REPAIR_APPLIED` | 0 | The one approved change was made and proven in scope. |
| `FAILED` | 1 | This package violated its **own** safety contract. |
| `UNPROVEN` | 2 | Required evidence could not be obtained. No claim is made. |
| `REPAIR_REFUSED` | 3 | A precondition was positively observed not to hold. Nothing was written. |

`REPAIR_REFUSED` has its own exit code on purpose. A refusal is a **correct
outcome of a correctly-working package**, and collapsing it into `FAILED` would
make failure meaningless while collapsing it into `UNPROVEN` would claim
ignorance about something the run knew exactly.

`FAILED` is reserved for violations of this package's own contract: a mutation
outside the permitted set, an unexpected creation or deletion, an affected row
count other than one, a post-state that is not the intended value, an
out-of-scope table moving, an accepted write probe, a mutation during a verify
run, a failed advisory-lock release, or a hidden source call. **A platform
condition this package successfully discovered is never `FAILED`.** A package
contract test asserts that no platform-shaped reason code appears in the FAILED
family, and that the three reason families do not overlap.

### The completion gate

The verdict reducer re-derives its facts from the evaluated precondition
objects rather than reading the summary booleans the evaluator also produces. A
summary flag is a claim; the check list is the evidence, and the reducer that
decides whether production may be written reads the evidence.

An evaluation that does not positively cover **every** governed precondition
id, with a recognised state on each, is `UNPROVEN` before any classification
branch is reached. An empty, partial, malformed, or non-list evaluation can
never reach a success result by having nothing to object with — and a forged
`all_satisfied: True` cannot override what the checks actually say.

An apply that was attempted but whose commit outcome was never established is
`UNPROVEN`, never applied: a commit nobody observed is not a commit.

---

## 11. What this package never does

No work-item insert, no checkpoint creation, no second work-item update, no
other column on the work item, no `GameLog` insert or update, no
`ScheduledGame` mutation, no `SyncRun` creation or update, no correction-
provenance write, no dead-letter write or clear, no snapshot generation,
publication, or selection, no serving-state change, no team-intelligence
change, no player-intelligence change, no mode change, no authority change, no
sync, backfill, or replay trigger, no rerun of a historical workflow, no source
data modification, no canonical appearance-row modification, no public snapshot
generation, no publication, no validator weakening, no migration, and no schema
change.

Standing production state is unchanged by this package: the daily and postgame
game-driven lanes remain shadow, backfill remains off, automated writes remain
prohibited, authoritative publication mode remains prohibited, and publication
authority remains with the existing trusted path.

**The global dead-letter backlog remains 1,389.** This package may report only
that it created zero dead letters. It never reports the backlog as zero.

---

## 12. Reusing the canonical authorities

This package OBSERVES nothing on its own. The runner supplies observations
produced by the **merged audit's own observation functions**, which call:

* the canonical game-ingestion planner;
* the single MLB client, behind the audit's counting guard;
* the single box-score parser;
* the canonical appearance extractor;
* the canonical reconciliation planner.

The judgement module reuses the audit's `matrix_row`, `validate_matrix`,
`field_materiality`, `scoped_fingerprints`, `fingerprint_scope_plan`,
`enforce_read_only`, `probe_evidence`, `evaluate_probe_evidence`, and the
shared acquire-only public sync lock.

There is **no** second sync pipeline, no second MLB client, no second parser,
no second planner, and no second reconciler. A package contract test asserts
that none of those symbols is defined here.

What this package does own, and why: the precondition model, the live
population expectation, the mutation-scope controls, and the verdict reducer.
Those answer questions the audit does not ask.

---

## 13. Evidence artifact

`game-824487-checkpoint-repair-<run id>`, retained 90 days, containing:

* `source-revision-checkpoint-repair.json` — the full evidence document;
* `source-revision-checkpoint-repair-summary.md` — the human-readable summary;
* `source-revision-checkpoint-repair-preconditions.json` — the whole
  requirement model plus this run's evaluation, so a reader can check the
  package's requirements against its results;
* `source-revision-checkpoint-repair-mutation-ledger.json` — what was written,
  **or the explicit record that nothing was**;
* `source-revision-checkpoint-repair-field-comparison.json` — the field-level
  comparison and its gates.

The mutation ledger always exists. A ledger that appeared only on success would
make "no ledger" ambiguous between "did not run" and "ran and wrote nothing".

The repository's established secret scanner runs BEFORE upload and gates it. A
scanner failure means the artifact never leaves the runner, and the final gate
fails the workflow. Raw MLB payloads, database URLs, tokens, environment dumps,
connection strings, stack traces, authorization headers, SQL statement text,
and raw production table dumps are never written. Exception text is never
serialized — every caught error becomes a closed reason code.

Upload happens **before** the final gate, so a REFUSED, FAILED, or UNPROVEN run
still leaves reviewable evidence. Evidence survival never converts a non-zero
result into success.

---

## 14. Test coverage

| file | owns |
| :--- | :--- |
| `test_game_source_revision_checkpoint_repair_contract.py` | the governed scope as reviewed literals, the permitted changed-column set against the real schema, the closed operation vocabulary, per-operation confirmations, exit-code separation, reason-family disjointness, the precondition mapping, the completion gate, reducer precedence, the advisory-lock lifecycle, the whole workflow contract, and package hygiene |
| `test_game_source_revision_checkpoint_repair_classification.py` | the live population expectation, the completeness gate and its ordering, the field comparison and its display-only distinction, every precondition transition, and the mutation-scope evaluator |
| `test_game_source_revision_checkpoint_repair_execution.py` | real PostgreSQL: the real lane writing the checkpoint, verify writing nothing, apply changing exactly one column on one row, statement accounting, the neighbour checkpoint staying still, idempotence, every refusal, authorization, and concurrency |
| `test_game_source_revision_checkpoint_repair_artifacts.py` | every file under every outcome, the always-present ledger, the required markdown sections, the `updated_at` disclosure, and the repository scanner run against a real artifact directory — including a planted credential that must fail it |

Two properties worth naming because they are easy to test badly:

* **The two governed revisions are monkeypatched in tests, never
  parameterized.** Production has no way to supply a different value: the
  constants are reviewed literals with no input, no argument, and no
  environment variable that can reach them. A test that needs different digests
  reaches into the module, which is exactly the kind of access production does
  not have.
* **The scanner gate is exercised, not assumed.** A planted credential must
  make the scanner fail, or the pre-upload gate proves nothing.

---

## 15. Running it

Verify first. Always.

1. Dispatch **Manual Game 824487 Source Revision Checkpoint Repair** from
   `main`, with `operation = verify`, the current `main` SHA, and
   `VERIFY_GAME_824487_SOURCE_REVISION_CHECKPOINT`.
2. Read the artifact. A `VERIFIED_REPAIR_REQUIRED_AND_SAFE` result means every
   precondition was satisfied at that moment. It is **evidence for** a
   decision, not the decision.
3. If — and only if — a human decides to proceed, dispatch again with
   `operation = apply` and
   `APPLY_GAME_824487_SOURCE_REVISION_CHECKPOINT`.
4. Read the apply artifact's mutation ledger. Confirm
   `observed_changed_columns` is exactly `["source_revision", "updated_at"]`,
   `affected_row_count` is 1, and `unexpected_changed_fingerprint_tables` is
   empty.

A verify result does not expire into permission. The apply run re-observes
everything from scratch and refuses on its own if anything moved in between.

---

## 16. Reading each outcome

| you see | it means | do |
| :--- | :--- | :--- |
| `VERIFIED_REPAIR_REQUIRED_AND_SAFE` | The change is currently required and currently safe. | Decide. Nothing was written. |
| `REPAIR_NOT_REQUIRED` | The checkpoint already holds the intended value. | Nothing. The repair is complete. |
| `REPAIR_APPLIED` | The change was made and proven in scope. | Read the ledger, then remove the package. |
| `REPAIR_REFUSED` | A precondition was positively observed not to hold. | Read `refusal_reasons`. Nothing was written. Do not retry blindly. |
| `UNPROVEN` | Required evidence could not be obtained. | Read `unproven_reasons`. Nothing was written. A contended lock or an unavailable source is normal and safe to re-run later. |
| `FAILED` | This package broke its own contract. | Read `failed_reasons`. This says nothing about the platform. Treat the package as untrusted until the cause is understood. |

---

## 17. Rollback

The only durable change an apply can make is one column on one row, and the old
value is recorded in the mutation ledger's `old_value` field before the change
is made.

There is no automated rollback in this package, deliberately: a rollback path
is a second write path, and a second write path is a second thing to get wrong.
Reverting is a manual, separately-approved single-row UPDATE using the recorded
`old_value` — the same size of decision as the original, made the same way.

Reverting a checkpoint marker is not a data restoration. Nothing about the
canonical appearance rows changed, so nothing about them needs restoring.

---

## 18. Known limitations

* **The workflow has never been dispatched.** Every claim here about live
  production behaviour is a claim about what the code does, validated against a
  disposable local PostgreSQL database with the real lane, the real planner, the
  real extractor, and the real reconciler — not an observation of production.
* **The `verify` result does not bind the `apply` run.** Time passes between
  them. That is why the apply re-observes everything and re-validates under a
  row lock; it is also why a verify result must never be treated as standing
  permission.
* **The out-of-scope digest covers one table.** `game_ingestion_work_items` is
  the only table any statement in this package names. Every other governed table
  is covered by the in-scope fingerprints for this game. A whole-table digest of
  every governed table's complement was considered and rejected on cost:
  `game_play_by_play_events` can be very large, and a proof expensive enough to
  time out is not a proof.
* **One bounded box-score call, no retries.** An incomplete or unavailable
  payload is a realistic outcome. The correct response is to reduce scope and
  report UNPROVEN — not to add retries, a second source authority, or a wider
  call budget.
* **The retained audit artifacts are not consulted at all.** This is deliberate
  (§6), and it means this package cannot corroborate anything against the
  historical runs. It does not need to: it makes no historical claim.

---

## 19. Relationship to the merged audit

The audit (`docs/current/GAME_824487_SOURCE_REVISION_AUDIT.md`, merged in
PR #613) is read-only and authorizes nothing. Its Question 12 is informational
only and explicitly states that any future repair requires a separate
exact-scope package and separate explicit approval.

This is that separate package. It does **not** read the audit's conclusion, and
it does not treat any audit output as a precondition. Everything it acts on, it
re-observes. If the audit had never run, this package would behave identically.

The two packages share observation code, the read-only controls, and the
advisory-lock identity — deliberately, so there is one answer to each shared
question rather than two.

---

## 20. How to remove this package later

It is additive and self-contained. Deleting these files removes it completely,
and nothing in production imports any of them:

```
.github/workflows/manual-game-824487-source-revision-checkpoint-repair.yml
backend/services/game_source_revision_checkpoint_repair.py
backend/scripts/run_game_source_revision_checkpoint_repair.py
backend/tests/test_game_source_revision_checkpoint_repair_contract.py
backend/tests/test_game_source_revision_checkpoint_repair_classification.py
backend/tests/test_game_source_revision_checkpoint_repair_execution.py
backend/tests/test_game_source_revision_checkpoint_repair_artifacts.py
docs/current/GAME_824487_SOURCE_REVISION_CHECKPOINT_REPAIR.md
```

Then remove the four test paths from `backend/tests/ci_shard_manifest.json` and
re-run `python scripts/ci_shard.py verify` from `backend/`. No migration is
involved, no production module changes, and the Alembic head is untouched.

Remove it once the repair has been applied and its ledger reviewed. A
single-purpose write capability that outlives its purpose is a standing risk,
not a convenience.
