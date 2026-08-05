# Game 824487 source-revision checkpoint repair

**Status: package implemented and validated. The repair has NOT been executed.
No production database session has been opened by this package. No production
row has been mutated. No workflow has been dispatched. Nothing here is
authorization to run it.**

---

## 1. Incident summary

Game 824487 (represented date 2026-07-29) recorded two different source
revisions across scheduled daily runs 30902544622 and 30999087370 while
agreeing on everything else about it: 12 appearances both times, all 12
classified unchanged both times, and an identical per-game
reconciliation-plan fingerprint both times. The later run's shadow activation
observer FAILED on `source_revision_match`.

The durable consequence is narrow. The `GameIngestionWorkItem` for game 824487
still stores the prior source revision while the current official source
produces the later one. The checkpoint is stale relative to the source; every
canonical row is unchanged.

## 2. Audit evidence

The controlled read-only audit (PR #613, merged as
`cb4ec4ae4d78910bb44207df01e0c1aba93f5958`) ran as workflow run 31044299167 and
produced artifact `game-824487-source-revision-audit-31044299167`
(id 8945806046, digest
`sha256:fe8949b410fdeb092cb744d1341d385b2e9c28fc0ce06d5cd61d1b42031df64a`).

Verdict: `COMPLETE_SCOPE_AND_MATERIALITY_IDENTIFIED_FIELD_DELTA_UNAVAILABLE`,
exit 0, with no failed and no unproven reasons.

| dimension | value |
| :--- | :--- |
| root condition | `official_appearance_set_changed` |
| current materiality | `non_material_to_canonical_writer_target` |
| current source completeness | `complete_and_comparable` |
| persistence | `matches_later_revision` |
| checkpoint state | `checkpoint_stale_relative_to_current_source` |
| historical field identification | `not_retained` |

The audit also positively established: current official appearance count 12,
retained verified expectation 12, exact official/stored membership, no
duplicate identities on either side, a canonical reconciliation plan of 12
unchanged with zero inserts, updates, deletes, and blocked rows, and no
semantic code drift in the source-revision path.

The exact historical field transition could **not** be recovered, because
neither retained artifact kept normalized row-level values for a game whose
appearances were all unchanged. This package does not attempt to infer it.

**The audit is evidence, not standing authority.** Nothing in this package
reads the audit's conclusion, and no audit output is a precondition. Every
precondition is re-observed live at execution time. If the audit had never run,
this package would behave identically.

## 3. Why GameLog is not being repaired

The canonical reconciler, run against today's box score, proposes zero inserts,
zero updates, and zero blocked rows for this game. Canonical storage is already
correct. There is no canonical writer repair to perform, and this package
refuses rather than becoming one.

The six official-versus-storage differences the audit found are confined to the
derived `innings_pitched` display value — for example official
`1.3333333333333333` against stored `1.33333333333333`. Integer recorded outs
are the innings authority, and `innings_pitched` is deliberately **not** one of
the 14 governed fingerprint fields, so those differences cannot move the digest
and are classified `derived_display_only`.

**Rewriting stored values to eliminate a floating-point display difference
would be a fabricated correction.** This package never does it. If any
*governed* fingerprint field ever differs, the correct response is a data
repair — which this package is not — so it refuses.

## 4. Why only the checkpoint is stale

`source_revision` is
`game_appearance_extraction.appearance_set_fingerprint` — SHA-256 over the
deterministic normalized appearance matrix over 14 governed fields. It is an
observed-content **marker on the ingestion checkpoint**, not a baseball value.

Moving it changes no pitching line, no inning, no earned run, no roster
association, and no public artifact. What it changes is what the daily lane
believes it has already observed for this game.

That is exactly why the repair is gated on the canonical appearance data being
already correct. A checkpoint may only be advanced to describe evidence that
has actually been observed and already agrees with storage.

## 5. Exact old and new revision

| | value |
| :--- | :--- |
| expected existing value | `90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0` |
| intended new value | `a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4` |

Both are reviewed immutable literals in code. Neither is an input, an argument,
or an environment variable. The intended value is never *assumed* from the
literal either: it is recomputed from today's source through the canonical
extractor and must reproduce the literal exactly, or the run refuses.

Two further reviewed literals are checked the same way:

| | value |
| :--- | :--- |
| expected appearance count | 12 |
| expected plan fingerprint | `8cb7eacbc0e0a6da908ea759c836e585a2e690a99280cd8f274275fc7d1709ec` |

## 6. Exact target model and field

| | value |
| :--- | :--- |
| model | `GameIngestionWorkItem` |
| table | `game_ingestion_work_items` |
| identity column | `mlb_game_pk` (UNIQUE) |
| target column | `source_revision` (`String(64)`, nullable) |
| game | 824487 |
| represented date | 2026-07-29 |
| rows the run may affect | exactly 1 |
| permitted changed columns | `source_revision`, `updated_at` |

### Why `updated_at` is in the permitted set

The model declares `updated_at` with `onupdate=utc_now_naive`, which fires on
**any** UPDATE of the row. The single permitted change therefore moves two
columns, not one. That is disclosed rather than hidden:

* `source_revision` is the **governed** change — the one decision under review;
* `updated_at` is an **automatic bookkeeping side effect** of making it;
* any third changed column is a contract violation and fails the run.

Pinning `updated_at` back to its old value was considered and rejected.
Falsifying a bookkeeping timestamp to make a diff look smaller is worse than
disclosing the timestamp. A package contract test asserts the model really
declares `onupdate`, so if that ever stopped being true the disclosure would
fail rather than quietly become wrong.

## 7. Verify mode

`verify` is read-only under every outcome. It acquires the shared public sync
advisory lock, opens a PostgreSQL read-only transaction, proves that
transaction read-only with a bounded refused write probe, observes every live
precondition, builds the exact proposed one-field transition, compares
before/after fingerprints, releases the lock and proves the release, writes its
artifacts, and mutates nothing.

Outcomes: `VERIFIED_REPAIR_REQUIRED_AND_SAFE` (exit 0),
`REPAIR_NOT_REQUIRED` (exit 0), `REPAIR_REFUSED` (exit 2), `UNPROVEN`
(exit 2), `FAILED` (exit 1).

A verify run never reports a mutation, and its artifact says **proposed**,
never executed.

## 8. Apply mode

`apply` repeats every verification step from scratch. It never consumes a
cached verify result, and no verify artifact is read.

Only after every precondition is satisfied does it open a writable transaction.
It then takes the target row with `SELECT … FOR UPDATE NOWAIT` — never
waiting — and re-validates every row-level precondition against the **locked**
row, because the read-only observation and the write transaction are not the
same instant.

The commit is conditioned on the in-transaction post-state: the row read back
inside the open transaction must already show the intended value, exactly one
row must have been affected, exactly one write statement must have been issued,
and the ORM scope guard must show zero creations, zero deletions, and exactly
`['source_revision']`. Anything short of that is **rolled back** rather than
committed and reported.

After the commit, still holding the advisory lock, it opens a fresh transaction,
sets it read-only, and re-reads the committed state to prove the new value, the
row count, and the unchanged scopes.

Outcomes: `REPAIR_APPLIED` (exit 0), `REPAIR_NOT_REQUIRED` (exit 0),
`REPAIR_REFUSED` (exit 2), `UNPROVEN` (exit 2), `FAILED` (exit 1).

## 9. Authorization contract

```
Workflow: Manual Game 824487 Source Revision Checkpoint Repair
File:     .github/workflows/manual-game-824487-source-revision-checkpoint-repair.yml
Trigger:  workflow_dispatch ONLY
```

Inputs: `operation` (a closed choice of `verify` or `apply`, defaulting to
`verify`), `expected_main_sha`, `confirmation`, `operator_note`.

Confirmation phrases are **per operation**, matched against the selected
operation only:

* `VERIFY_GAME_824487_SOURCE_REVISION_CHECKPOINT`
* `APPLY_GAME_824487_SOURCE_REVISION_CHECKPOINT`

A confirmation reviewed and typed for a verify run **cannot** start an apply
run. This is checked twice: once in the workflow preflight, before checkout,
Python, or dependencies; and again in the runner's own authorization, before
the Flask application is created or any database session is opened.

The run refuses when the repository is not `NickolisK24/bullpen-intel-engine`,
the ref is not `refs/heads/main`, the actor is not the repository owner, the
SHA is not a full 40-character lowercase hex string equal to the resolved
`GITHUB_SHA`, the operation is not in the closed vocabulary, the confirmation
does not match that operation exactly, or any required secret is absent.

Permissions are `contents: read` and nothing else — no `actions: write`, no
`contents: write`, no `pull-requests: write`, no `deployments: write`, no
`id-token`. No existing deployment mechanism requires any of them.
`ADMIN_API_TOKEN` is present only because `config.py` refuses to boot under
`APP_ENV=production` without it; this package never reads the value, makes no
HTTP call to this service, and invokes no admin endpoint. There is no sync URL,
no publication token, no writer endpoint, and no snapshot token.

The workflow shares the `baseballos-sync` concurrency group with the production
sync lane, with `cancel-in-progress: false` — so it can never overlap a
production writer, and a repair halfway through its own transaction can never
be cancelled by a later dispatch.

## 10. Live preconditions

Nineteen, all re-observed in the same execution. **A conclusion is not a
precondition.**

| precondition | requirement |
| :--- | :--- |
| `target_row_exists` | at least one existing row for game 824487 |
| `target_row_is_unique` | no more than one candidate row |
| `target_row_is_the_target_game` | `mlb_game_pk == 824487` |
| `target_row_represented_date_matches` | `represented_date == 2026-07-29` |
| `target_row_status_is_completed` | `status == 'completed'` |
| `target_row_carries_no_unresolved_error_state` | `error_class` absent, `completed_at` present |
| `existing_revision_is_the_expected_old_value` | the stored value is the expected old digest |
| `intended_revision_differs_from_existing` | the intended value is not already stored |
| `appearance_population_size_verified` | population size verified from live durable state |
| `stored_appearance_count_matches_population` | stored canonical rows equal that size |
| `current_official_source_observed` | today's box score was fetched and extracted |
| `current_official_source_conclusion_eligible` | completeness is `complete_and_comparable` |
| `current_official_revision_is_the_intended_value` | today's set fingerprints to the intended digest |
| `no_governed_fingerprint_field_differs` | no governed field differs from storage |
| `every_difference_is_derived_display_only` | every observed difference is `derived_display_only` |
| `canonical_plan_proposes_no_mutation` | zero inserts, updates, and blocked rows |
| `reconciliation_plan_fingerprint_unchanged` | the plan fingerprint still equals the reviewed value |
| `current_appearance_count_is_the_reviewed_count` | official and stored counts are both exactly 12 |
| `governed_scope_fingerprints_observed` | per-table digests were computed |

Each carries a **three-way state**, never a boolean:

`satisfied` · `violated` · `not_observed`

`violated` and `not_observed` contribute **different** reason codes. "The
stored value is some third digest" and "the database was never opened" both
sound negative and mean completely different things. A contract test asserts
that no precondition's refusal reason and unproven reason are ever the same
code.

### Three that are easy to get backwards

**`no_governed_fingerprint_field_differs` is not "the differing-row list is
empty."** Requiring an empty list would make this repair refuse forever on the
six `innings_pitched` display differences, which cannot move the digest. The
requirement is two separate claims: no governed field differs, **and** every
observed difference is `derived_display_only`.

**The plan fingerprint refuses on its own.** A plan can report zero inserts,
zero updates, and zero blocked rows while its fingerprint has moved — which
would mean the plan this repair was reviewed against is not the plan the
reconciler produces today. The fingerprint is therefore checked separately from
the action counts, and either failing refuses.

**`intended_revision_differs_from_existing` is the one violated precondition
that is not a refusal — but only when nothing else is wrong.** A row already
holding the intended value means there is nothing to do. That is
`REPAIR_NOT_REQUIRED` at exit 0, resolved ahead of `REPAIR_REFUSED`. It is
still reported as a violated precondition rather than quietly reclassified.

A clean no-op tolerates exactly two violations, and they are the two that are
arithmetically forced by the row already holding the intended value:
`intended_revision_differs_from_existing`, and
`existing_revision_is_the_expected_old_value` — the two governed revisions
differ by contract, so a row holding the intended value cannot also hold the
expected old value. **Any other violated precondition, any not-observed
precondition, and any failed or unproven reason makes the result
`REPAIR_REFUSED` or worse.** "The checkpoint already says what we wanted" is
not a safe conclusion when the evidence around it is contradictory, and exit 0
would announce success on a state nobody verified.

That tolerance is **regime-scoped**. When the row is *not* at the intended
value, a violated `existing_revision_is_the_expected_old_value` means the
checkpoint holds some third unexpected value — the primary thing this package
refuses on — and it stays blocking.

### Where the population size comes from

The merged audit establishes the appearance population size from the two
retained shadow artifacts. **Those artifacts expire** (2026-11-03). A repair
that may be dispatched later must not depend on evidence with an expiry date,
so this package sources it from **live durable state**: the checkpoint's own
`rows_expected`, `rows_reconciled`, and the count of canonical appearance rows
actually stored. All three are re-observed and all three must agree.

The reviewed literal 12 is then checked **in addition**. The live check proves
the checkpoint and storage still agree with each other; the literal proves they
still agree with what was reviewed. Either failing refuses.

## 11. Refusal conditions

Stable, safe reason codes. Exception text is never serialized — every caught
error becomes a closed code.

**Refusal** — a precondition was positively observed not to hold:
`target_work_item_missing`, `multiple_candidate_work_items`,
`work_item_is_not_the_target_game`, `work_item_represented_date_mismatch`,
`work_item_status_not_completed`, `target_status_unexpected_error_state`,
`existing_source_revision_not_expected`,
`checkpoint_already_at_intended_revision`,
`appearance_population_expectation_unverified`,
`stored_appearance_count_disagrees_with_checkpoint`,
`current_official_source_not_conclusion_eligible`,
`current_source_count_unexpected`,
`current_official_revision_is_not_the_intended_revision`,
`governed_fingerprint_field_differs`, `non_display_difference_present`,
`canonical_plan_proposes_a_baseball_mutation`, `reconciliation_plan_changed`,
`target_row_modified_concurrently`, `governed_scope_moved_before_apply`,
`prohibited_scope_changed`, `post_commit_verification_failed`,
`mutation_row_count_zero`.

**Unproven** — required evidence was never obtained:
`public_sync_advisory_lock_unavailable`, `advisory_lock_release_unproven`,
`read_only_transaction_unavailable`, `read_only_probe_evidence_missing`,
`required_database_evidence_unavailable`,
`current_official_source_unavailable`,
`canonical_reconciliation_plan_unavailable`,
`scoped_fingerprint_uncomputable`, `out_of_scope_fingerprint_uncomputable`,
`target_row_not_lockable_without_waiting`, `repair_execution_error`,
`mandatory_precondition_not_observed`, `apply_outcome_never_established`.

**Failed** — this package violated its own contract:
`event_not_workflow_dispatch`, `repository_not_authorized`,
`actor_not_authorized`, `ref_not_main`, `expected_main_sha_malformed`,
`expected_main_sha_mismatch`, `operation_not_in_closed_vocabulary`,
`confirmation_does_not_match_operation`, `mutation_scope_exceeded`,
`unexpected_row_created`, `unexpected_row_deleted`,
`work_item_outside_target_mutated`, `affected_row_count_not_exactly_one`,
`post_state_is_not_the_intended_revision`, `out_of_scope_table_changed`,
`unpermitted_fingerprint_scope_changed`,
`target_table_fingerprint_unchanged_after_apply`,
`read_only_probe_accepted_not_refused`, `mutation_attempted_during_verify`,
`advisory_lock_release_failed`, `advisory_lock_release_not_attempted`,
`mutation_row_count_multiple`, `artifact_generation_failed`.

A contract test asserts the three families do not overlap and that no
platform-shaped condition appears in the FAILED family.

**Zero and more-than-one affected rows are different outcomes.** Zero rows
under an exclusive lock this transaction just re-validated against is read as
"the row moved" — a concurrency refusal, and never a claim that the repair was
already applied without a fresh read establishing it. More than one row is
structurally impossible under a UNIQUE constraint and a primary-key predicate,
and is still guarded, as a contract violation.

**A run whose evidence could not be written is not a successful run.** An
artifact-generation failure returns `FAILED` with a closed reason code rather
than an uncaught traceback, whatever the verdict said.

### Traceability to the governing specification

The repair specification names a minimum set of conditions that must carry a
stable, safe reason code. This package's own codes are more specific in several
places — `current_official_revision_is_not_the_intended_revision` says more
than `current_source_revision_unexpected` — so rather than rename them down to
the specification's granularity, the mapping is published in
`SPECIFIED_REASON_CODES` and travels in the preconditions artifact alongside
the full reason vocabulary. A contract test asserts every listed condition maps
to a code that really exists, so the map cannot rot into a list of names for
conditions nobody detects.

## 12. Concurrency control

Three layers.

1. **Shared advisory lock.** The same identity every public sync writer takes
   (`SYNC_WRITER_LOCK_KEY` under `LOCK_SCOPE_PUBLIC`), acquire-only: it never
   creates, reclaims, or updates a `SyncRun` row. Contention stops the run
   immediately — this package never waits and never queues. The full lifecycle
   gates the verdict: acquired-and-never-provably-released is a contract
   violation, and process termination is not release evidence.
2. **Row lock.** `SELECT … FOR UPDATE NOWAIT` on the target row. A row this
   package cannot lock without waiting is UNPROVEN, never forced.
3. **Snapshot re-validation.** Every mapped column observed in the read-only
   pass is compared against the locked row. Any difference at all —
   not merely `source_revision` — is `target_row_modified_concurrently`, and
   the transaction is rolled back. The approved change was reviewed against the
   row as it was observed; a row that is no longer that row is refused.

## 13. Mutation scope

The only permitted production mutation is
`game_ingestion_work_items.source_revision` on the one existing row for game
824487, plus the automatic `updated_at` bookkeeping timestamp.

Prohibited, and named explicitly in the artifact of every run: inserting a work
item, creating a missing checkpoint, updating more than one work item, updating
any other column, updating `GameLog`, `ScheduledGame`, or `SyncRun`, writing
correction provenance, writing or clearing dead letters, generating or
publishing a snapshot, changing serving or publication state, changing team or
player intelligence, changing ingestion mode or publication authority,
triggering a sync, backfill, or replay, rerunning a historical workflow,
modifying source data, modifying a canonical appearance row, running a
migration or schema change, and weakening a validator.

Standing production state is unchanged: the daily and postgame game-driven
lanes remain shadow, backfill remains off, automated writes remain prohibited,
authoritative publication mode remains prohibited, and publication authority
remains with the existing trusted path.

**The global dead-letter backlog remains 1,389.** This package may report only
that it created zero dead letters. It never reports the backlog as zero.

## 14. Before/after proof

Four independent controls on the apply, every one a positive observation rather
than the absence of an error.

1. **Full-column snapshot diff.** Every mapped column, read by SQLAlchemy
   inspection rather than a hand-written list — a hand list silently stops
   covering a column somebody adds later, and the whole scope proof rests on
   this snapshot being complete. The observed delta must be exactly
   `{source_revision, updated_at}`.
2. **ORM mutation-scope guard.** A `before_flush` listener recording every
   creation, deletion, and changed-attribute set. Zero creations, zero
   deletions, exactly the target object, exactly `['source_revision']`.
   (`updated_at` does not appear here: the `onupdate` default is applied by the
   flush process *after* `before_flush` runs, which is why the snapshot diff —
   not this guard — is the authoritative claim.)
3. **Statement accounting.** An `after_cursor_execute` listener recording every
   SQL write statement the connection actually issued. Exactly one UPDATE
   naming the target table, row count exactly one, and no other write statement
   of any kind. This proves what the **database** was told, which is stronger
   than what the session intended: a raw statement issued from anywhere is
   visible here even though no ORM object was made dirty. Statement **text** is
   never retained — only a class, a row count, and one boolean.
4. **Scope fingerprints.** Full governed row content and timestamps — not row
   counts — across `scheduled_games`, `game_logs`, `game_ingestion_work_items`,
   `postgame_processed_games`, `team_game_pitching_splits`,
   `completed_game_contexts`, `game_play_by_play_events`, `sync_failures`, and
   the local `Pitcher` identity rows. Exactly one `[scope, table]` pair may have
   moved, and it must be
   `[exact_game_824487, game_ingestion_work_items]`. A target table that did
   **not** move is equally a violation — a repair that reported itself without
   moving the row is not a repair. Plus an out-of-scope digest and row count
   over every row of the target table that is *not* game 824487.

Correction provenance and appearance-team authority are COLUMNAR in this
schema, so full-row digests of `game_logs` and `game_ingestion_work_items`
already cover them; there is no separate history table.

During the read-only phase of either operation, **any** changed governed table
is a contract violation on verify and a refusal on apply.

## 15. Artifact schema

`game-824487-source-revision-checkpoint-repair-<run id>`, retained 90 days:

| file | contents |
| :--- | :--- |
| `game-824487-source-revision-checkpoint-repair.json` | the full evidence document |
| `game-824487-source-revision-checkpoint-repair-summary.md` | the human-readable summary, in fifteen numbered sections |
| `game-824487-source-revision-checkpoint-repair-proof.json` | read-only proof, advisory-lock lifecycle, source-call accounting, prohibited-mutation manifest |
| `game-824487-source-revision-checkpoint-repair-preconditions.json` | the whole requirement model plus this run's evaluation |
| `game-824487-source-revision-checkpoint-repair-fingerprints.json` | before/after scope digests and the scope evaluation |
| `game-824487-source-revision-checkpoint-repair-mutation-ledger.json` | what was written, **or the explicit record that nothing was** |
| `game-824487-source-revision-checkpoint-repair-field-comparison.json` | the field-level comparison and its gates |

The mutation ledger always exists, and carries the run's own identity —
operation, workflow run id, main SHA, actor, operator note, advisory-lock
state, transaction state, commits performed, rollback performed, mutation
status, mutation timestamp, target row identity, previous value, proposed
value, observed value before and after, and affected row count — so a reader
never has to correlate it against another file to know which run wrote it.

A ledger that appeared only on success would make "no ledger" ambiguous between
"did not run" and "ran and wrote nothing".

The repository's established secret scanner runs BEFORE upload and gates it. A
scanner failure means the artifact never leaves the runner and the final gate
fails the workflow. Raw MLB payloads, database URLs, tokens, environment dumps,
connection strings, stack traces, authorization headers, SQL statement text,
and raw production table dumps are never written.

Upload happens **before** the final gate, so a refused, failed, or unproven run
still leaves reviewable evidence. Evidence survival never converts a non-zero
result into success.

## 16. Result vocabulary

| result | exit | meaning |
| :--- | :--- | :--- |
| `VERIFIED_REPAIR_REQUIRED_AND_SAFE` | 0 | Every precondition satisfied on a verify run. Evidence for a human decision, not that decision. |
| `REPAIR_NOT_REQUIRED` | 0 | The checkpoint already holds the intended value. |
| `REPAIR_APPLIED` | 0 | The one approved change was made and proven in scope. |
| `FAILED` | 1 | This package violated its **own** safety contract. |
| `UNPROVEN` | 2 | Required evidence could not be obtained. |
| `REPAIR_REFUSED` | 2 | A precondition was positively observed not to hold. |

**Three exit codes, and only three.** Exit 0 means the repair is eligible,
applied, or already applied. A refused run is not eligible, so it must not be
distinguishable from UNPROVEN by exit status — anything reading only the exit
code must treat both identically, which is to say: do not proceed. The
distinction is preserved where it actually matters, in the result name and the
reason codes a reviewer reads, and it is never flattened there.

`FAILED` is reserved for violations of this package's own contract. **A
platform condition this package successfully discovered is never `FAILED`.**

### The completion gate

The verdict reducer re-derives its facts from the evaluated precondition
objects rather than from the summary booleans the evaluator also produces. A
summary flag is a claim; the check list is the evidence, and the reducer that
decides whether production may be written reads the evidence.

An evaluation that does not positively cover **every** governed precondition
id, with a recognised state on each, is `UNPROVEN` before any classification
branch is reached. An empty, partial, malformed, or non-list evaluation can
never reach a success result by having nothing to object with, and a forged
`all_satisfied: True` cannot override what the checks actually say.

An apply that was attempted but whose commit outcome was never established is
`UNPROVEN`, never applied: a commit nobody observed is not a commit.

Failing to establish the post-commit read-only transaction is `UNPROVEN` — the
same code the pre-observation path uses for the same condition. The mutation
may already be committed and cannot be taken back; what is withheld is the
success verdict, not the evidence. `mutation_performed` reports what **durably
happened**, not whether the run succeeded, so a commit that landed and then
failed a safety check is still reported as a mutation. The ledger keeps
`committed`, `commits_performed`, and the observed before/after values in full.

## 17. Test coverage

| file | owns |
| :--- | :--- |
| `test_game_source_revision_checkpoint_repair_contract.py` | the governed scope as reviewed literals, the permitted changed-column set against the real schema, the closed operation vocabulary, per-operation confirmations, the three-code exit contract, reason-family disjointness, the precondition mapping, the completion gate, reducer precedence, the advisory-lock lifecycle, the whole workflow contract, and package hygiene including adversarial scope scans |
| `test_game_source_revision_checkpoint_repair_classification.py` | the live population expectation, the completeness gate and its ordering, the field comparison and its display-only distinction, every precondition transition, and the mutation-scope evaluator |
| `test_game_source_revision_checkpoint_repair_execution.py` | real PostgreSQL: the real lane writing the checkpoint, verify writing nothing, apply changing exactly one column on one row, statement accounting, pre-commit and post-commit verification, the neighbour checkpoint staying still, idempotence, every refusal, authorization, and concurrency |
| `test_game_source_revision_checkpoint_repair_artifacts.py` | every file under every outcome, the always-present ledger and its governed fields, the fifteen numbered markdown sections, the `updated_at` disclosure, and the repository scanner run against a real artifact directory — including a planted credential that must fail it |

Two properties worth naming because they are easy to test badly:

* **The governed literals are monkeypatched in tests, never parameterized.**
  Production has no way to supply a different value: they are reviewed literals
  with no input, no argument, and no environment variable that can reach them.
  A test that needs different values reaches into the module, which is exactly
  the kind of access production does not have. The plan fingerprint a test pins
  is read through the same canonical path the package uses, so it is a real
  observation of the fixture rather than a number copied from production into a
  test that could then never fail.
* **The scanner gate is exercised, not assumed.** A planted credential must
  make the scanner fail, or the pre-upload gate proves nothing.

## 18. Rollout plan

1. Independent code and evidence-integrity review.
2. Merge only after approval.
3. Dispatch `verify` from `main` with the current `main` SHA and
   `VERIFY_GAME_824487_SOURCE_REVISION_CHECKPOINT`.
4. Review the production verify artifact.
5. If and only if verify returns `VERIFIED_REPAIR_REQUIRED_AND_SAFE` and the
   evidence is accepted, separately authorize `apply`.
6. Dispatch `apply` with `APPLY_GAME_824487_SOURCE_REVISION_CHECKPOINT`.
7. Review the apply artifact.
8. Confirm `observed_changed_columns` is exactly
   `["source_revision", "updated_at"]`, `affected_row_count` is 1, and
   `unexpected_changed_fingerprint_tables` is empty.
9. Allow the next normal scheduled sync to run.
10. Confirm game 824487 no longer creates a source-revision activation
    mismatch.
11. Confirm zero GameLog writes.
12. Confirm zero new dead letters.
13. Do not manually rerun historical workflows.
14. Do not backfill.
15. Do not publish a repair snapshot manually.

A verify result does not expire into permission. The apply run re-observes
everything from scratch and refuses on its own if anything moved in between.

## 19. Rollback and containment

The only durable change an apply can make is one column on one row, and the old
value is recorded in the mutation ledger's `observed_value_before` field before
the change is made.

There is no automated rollback in this package, deliberately: a rollback path is
a second write path, and a second write path is a second thing to get wrong.
Reverting is a manual, separately-approved single-row UPDATE using the recorded
old value — the same size of decision as the original, made the same way.

Reverting a checkpoint marker is not a data restoration. Nothing about the
canonical appearance rows changed, so nothing about them needs restoring.

**A release failure after a successful commit cannot be rolled back**, and the
package does not pretend otherwise: the final result is `FAILED`, and the
mutation ledger still discloses the committed one-field change rather than
hiding it behind the safety failure.

Containment if an apply goes wrong: the advisory lock is released in a
`finally` block either way, the change is bounded to one column on one row, and
every other governed scope is fingerprint-proven unchanged in the same
artifact.

## 20. Status boundary

* **Implementation does not execute the production repair.** No production
  workflow has been dispatched.
* **No production database session was opened** during implementation.
  Everything was validated against disposable local PostgreSQL databases with
  the real ORM, the real lane, the real planner, the real extractor, and the
  real reconciler.
* **No production mutation occurred.**
* **The verify/apply workflow remains manual** and undispatched.
* **Separate independent review is required before any dispatch.**
* **Verify mode must be dispatched before apply mode.**
* **Apply mode needs separate explicit approval** after the verify evidence has
  been reviewed.
* No migration was added; the Alembic head is unchanged.

### Known limitations

* Every claim here about live production behaviour is a claim about what the
  code does, not an observation of production.
* The out-of-scope digest covers `game_ingestion_work_items`, the one table any
  statement in this package names. Every other governed table is covered by the
  in-scope fingerprints for this game. A whole-table digest of every governed
  table's complement was considered and rejected on cost:
  `game_play_by_play_events` can be very large, and a proof expensive enough to
  time out is not a proof.
* One bounded box-score call, no retries. An incomplete or unavailable payload
  is a realistic outcome; the correct response is to reduce scope and report
  UNPROVEN, not to add retries, a second source authority, or a wider budget.
* The retained audit artifacts are not consulted at all. This is deliberate,
  and it means this package cannot corroborate anything against the historical
  runs. It does not need to: it makes no historical claim.

### Removing this package

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
