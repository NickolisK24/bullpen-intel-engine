# Game 824487 source-revision audit

**Status: audit package implemented and evidence-integrity corrected. The
production audit has NOT been executed. No conclusion has been reached. No
repair is authorized. Review verdict: HOLD pending a NEW independent
evidence-integrity review of the second correction pass.**

Nothing in this document states a root cause, because the audit has not run in
production yet. It describes what the package does, how to read what it will
produce, and how to remove it afterwards.

A first evidence-integrity review found four ways the package could reach a
completed conclusion from evidence it had not positively observed: Question 10
read its activation values from locked expectations and from artifact presence;
artifact identity fell back to the expected branch because no retained document
carries one; a failed advisory-lock release never reached the verdict; and
historical field identification could fire from a row-shaped structure rather
than from exact values.

An **independent** review of that correction confirmed all four were repaired
and found a fifth path, plus a completion-gate defect and three smaller
hardening and documentation issues:

* **A fetched-but-incomplete official source could still exit 0.** A box score
  that returned HTTP 200 and parsed cleanly but yielded zero — or only some —
  pitching appearances was treated as current official evidence. Because
  `differing_rows` only ever counted rows that were comparable on both sides,
  an empty official set and a six-of-twelve set both produced
  `current_target_exactly_matches_storage`. Membership deficits were computed
  and reported but gated nothing.
* **Fingerprint determinism was not load-bearing.** `Q5` was not mandatory and
  the classifier reacted only to a *proven-false* determinism result, so a run
  that never established determinism at all could still complete.
* **The state reducer defaulted into VERIFIED** for an empty observation set
  and for values that were read but never compared.
* **The registry's documented scope** was wider than its 26 rows.
* **A workflow comment** described the scan step as failing the workflow
  itself.

All nine findings are repaired. The sections below describe the corrected
behaviour rather than the original.

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

The audit does not assume this. It runs a real extractor that requires a
candidate to positively associate **all four coordinates at once** — exact run
id, exact game 824487, exact pitcher MLB id, exact governed field — before any
value counts. Ordering, display names, roster membership, and co-occurrence
prove nothing and are not consulted. For these two artifacts the extractor
correctly returns nothing, and that absence is recorded as `not_retained`.

Historical states are distinct and never collapsed: `proven`, `proven_null`,
`absent`, `not_retained`, `unproven`, `inconsistent`, `identity_missing`,
`wrong_game`. A value the extractor can see but cannot safely associate is
`unproven` — **not** `not_retained`, because something value-shaped was there.

A field delta is `identified` only when two exact retained values for the SAME
run/game/pitcher/field actually differ. Artifact presence, a row-shaped object,
a list of field names, a digest, a correction count, and a timestamp identify
nothing, and none of them can reach that classification.

---

## Artifact requirements

Both artifacts are **downloaded by exact repository, exact run id, and exact
artifact name**, BEFORE any database advisory lock is acquired. The artifact
**id** and **digest** are then verified against GitHub artifact metadata, and
the **branch** against GitHub workflow-run metadata. Downloading and verifying
are different steps with different sources, and this document does not blur
them.

### Where each mandatory fact comes from

Facts are not all "inside the documents". Three sources exist, and each fact
names exactly one:

| source | facts | enforced by |
| :--- | :--- | :--- |
| `handoff-metadata.json` | run id, head SHA, cycle kind, handoff status | `MANDATORY_FIELDS` |
| `*-activation-summary.json` | activation result, runner exit code, configured mode, `writes_enabled`, `publication_authoritative`, the whole `realization` block, and the later run's 94/94/778 accounting | `MANDATORY_FIELDS` |
| GitHub workflow-run metadata | **branch** (and a corroborating head SHA) | `MANDATORY_FIELDS` |
| `*-sync-summary.json` | game 824487 membership, source revision, plan fingerprint, appearances, unchanged, insert/update/block | `_CONTENT_GAME_FIELDS`, separately |
| GitHub artifact metadata | artifact id, digest | their own comparisons |

**The branch is in neither retained document.** The handoff metadata schema
(`scripts/prepare_shadow_handoff.build_metadata`) carries a schema version, run
id, repository SHA, cycle kind, runner exit code, an expected filename, and
three booleans — no branch and no ref. It is therefore read from GitHub
workflow-run metadata (read-only, covered by the existing `actions: read`
permission) or it is reported **unverified**. It is never filled in from what
the audit expected it to be.

`MANDATORY_FIELDS` — **26 rows**, 8 identity and 18 content — declares, for
each of the facts it governs: the document, the exact evidence path, the
expected type, the expected value or validator, which conclusions it gates
(identity / content / Question 10), whether it applies to the later run only,
and what its absence means. It is emitted into the evidence artifact so a
reader can check the audit's requirements against its results.

Its scope is exactly the retained handoff metadata, the retained activation
summary, and GitHub workflow-run metadata. Two mandatory groups are enforced
**outside** it, and this document does not present them as registry rows:

* **The game-scoped sync-summary facts** — game 824487 membership, source
  revision, plan fingerprint, appearances, unchanged, and insert/update/block —
  are observed and compared by their own contract (`_CONTENT_GAME_FIELDS`) and
  folded into the **content** verdict. A difference of one in any of them
  blocks verified content exactly as a registry row would.
* **Artifact id and digest** are compared against GitHub artifact metadata as
  their own checks. Under the current contract an artifact id that is exposed
  and differs, or is malformed, **fails** identity; an artifact id GitHub does
  **not** expose is reported as `not_exposed_by_github` and does not on its own
  make identity unproven. The digest is its own third verdict and is reported
  `unverified` when GitHub no longer exposes it — never as a match.

Every mandatory registry row must resolve a validator. A row naming an
expectation no run carries would be observed and never compared, so
`registry_expectation_defects()` reports any such row, a package contract test
asserts the list is empty, and the state reducer refuses to call an
uncompared value verified even if one ever slipped through.

### Three separate verdicts

Identity, digest, and content answer three different questions and are reported
separately. They can legitimately disagree — a correctly-identified artifact
whose digest GitHub no longer exposes is a real and common state.

| verdict | verified when | failed when | unproven when |
| :--- | :--- | :--- | :--- |
| identity | every mandatory identity field positively observed AND matched | any observed identity field contradicts its expectation, or the artifact id is exposed and differs | any mandatory identity field was not observed, or a required file is missing |
| digest | GitHub exposed it and it matches | GitHub exposed it and it differs | GitHub did not expose it |
| content | every mandatory content field positively observed AND matched | any observed content field contradicts | any mandatory content field was not observed |

A field that was never observed is **never** listed among the verified fields.

| observation | outcome |
| :--- | :--- |
| required artifact missing | UNPROVEN |
| required file missing inside an artifact | UNPROVEN |
| mandatory field not observed | UNPROVEN |
| observed field contradicts its expectation | FAILED |
| digest exposed by GitHub and different | FAILED |
| digest no longer exposed by the API | UNVERIFIED, reported honestly |
| later-run lane accounting off by one | FAILED |

### The later run's 94/94/778 accounting is compared, not reported

`games_planned`, `games_fetched`, `games_completed`, `games_failed`,
`rows_expected`, `rows_unchanged`, `rows_inserted`, `rows_updated`, and
`rows_blocked` are each read at a named path in the activation summary and
compared exactly. A difference of one is visible and blocks a verified content
verdict.

### Observation states

Every fact carries a state, and the states are deliberately finer than
present/absent:

`verified` · `observed` · `mismatch` · `absent` · `container_absent` ·
`container_malformed` · `malformed` · `source_unavailable`

A retained `null` is `observed`. A missing key is `absent`. A missing parent
object is `container_absent`. A parent that is not a mapping is
`container_malformed`. None of these collapse into a bare `None` that could
later read as agreement.

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

   The full lifecycle is recorded and **gates the verdict**: acquire attempted,
   acquired, acquisition reason, release required, release attempted, release
   proven, release reason, rollback attempted, rollback result. A completed
   result requires the guard to have been acquired AND positively released.

   | lifecycle | outcome |
   | :--- | :--- |
   | never attempted / not acquired | UNPROVEN — the audit observed nothing |
   | acquired, released | eligible to complete |
   | acquired, release raised | **FAILED** — the audit breached its own safety contract |
   | acquired, release never attempted | **FAILED** |
   | acquired, release outcome never established | UNPROVEN |

   Process or context termination is **not** release evidence. A failed release
   is preserved alongside any earlier failure rather than hidden behind it, and
   rollback still runs in `finally` either way.
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

### The current-source completeness gate

All three exit-zero results are statements about game 824487 as it stands
today, so every one of them is gated on a single flag —
`current_source_completeness.conclusion_eligible` — which is true only when the
box score was fetched, parsed, produced a **non-empty** appearance set, and
that set's pitcher membership matches canonical storage **exactly in both
directions**. The gate is applied in `decide()` before any classification
branch, so no branch can route around it, and it contributes an explicit
reason code rather than silently downgrading.

| completeness state | meaning | conclusion eligible |
| :--- | :--- | :--- |
| `complete_and_comparable` | Non-empty, membership matches exactly. | **yes** |
| `empty_official_set` | Fetched and parsed, zero pitching appearances. A final game has pitchers, so this is missing evidence — not an observation that the game had none. | no |
| `official_only_members_present` | The official set carries a pitcher storage does not hold. Canonical storage may be incomplete: reported as **material**. | no |
| `stored_only_members_present` | Storage holds a pitcher the observed official set does not. Either the payload was truncated or the stored row is extraneous; one bounded call cannot tell them apart, so neither is asserted. | no |
| `both_directions_mismatch` | Membership differs both ways at once. Neither side is established as complete. | no |
| `source_unavailable` | The source was never observed. | no |
| `database_unavailable` | Storage was never observed, so membership had nothing to compare against. | no |
| `matrix_unproven` | The matrix did not validate structurally. | no |

An empty `differing_rows` list proves only that the rows which were
**comparable on both sides** carried no governed field difference. It says
nothing about appearances that had no counterpart on one side and so were never
comparable at all, and it can never on its own establish an exact match. The
field matrix therefore reserves `complete_for_observed_evidence` for exactly
matching membership and reports
`comparable_rows_only_membership_incomplete` otherwise, so no reader can
mistake "the observed rows agreed" for "the official set was complete".

Because the audit spends exactly **one** bounded box-score call and never
retries, an incomplete payload is a realistic outcome rather than a hypothetical
one. The correct response is to reduce scope and report UNPROVEN — not to add
retries, a second source authority, or a wider call budget.

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

Every question reports an **answer state**, not a boolean, plus its required
inputs, the inputs actually observed, the inputs missing, its evidence sources,
and its limitations:

`observed_yes` · `observed_no` · `observed_but_insufficient` ·
`not_observed` · `unavailable` · `unproven`

Only the first three count as an answer. "The database said there is no
provenance" and "the database was never opened" both sound negative and are
completely different facts.

* **Q1 / Q2** require **verified identity AND verified content** on both
  artifacts. Required files merely existing is not evidence about what they
  say.
* **Q4** is `unavailable` when the current official source was not fetched. A
  source that was never read is never a match.
* **Q7 / Q8** are `not_observed` when the database was never opened. Q8 is
  `observed_but_insufficient` when correction provenance exists but records
  only counts, timestamps, a source label, and a sync run id — never a field
  name, an old value, or a new value.
* **Q10** consumes only positively parsed activation values —
  `source_revision_match`, `safe_digest_match`,
  `all_projected_targets_realized`, `unresolved_rows`,
  `prohibited_identity_actions` — each at a named path in
  `realization.*`. A counter nobody read is not zero, and artifact presence
  proves none of them. The single causal-chain conclusion requires every one of
  them observed, with no competing deficit.
* **Q11 / Q12** are `unproven` whenever any required classification dimension
  is unavailable. A compound conclusion is not complete because some of its
  dimensions were.

Nine questions (Q1, Q2, Q4, **Q5**, Q6, Q7, Q10, Q11, Q12) are mandatory for
completion. Any one of them unanswered closes the exit-zero path.

Q5 is mandatory because the fingerprint is this audit's only instrument: a
conclusion that game 824487 is currently fine may not rest on a digest nobody
proved was reproducible. Q5 is answered only from a **non-empty** observed
appearance set — recomputing the digest of an empty set agrees with itself
trivially and establishes nothing. Q3 stays outside the mandatory set because
an incomplete code comparison already forces `ROOT_UNPROVEN` structurally and
reaches the same verdict through classification.

### Early stops

When execution halts, the halt stage is recorded and every unanswered question
carries it as a limitation. Downstream absences are read against that stage
rather than mistaken for observations: a checkpoint nobody read is not a
missing checkpoint, and an empty field matrix reports
`not_generated_no_observed_evidence` rather than masquerading as a complete
matrix that found no differences.

A source that was **not fetched, failed parsing, yielded zero usable
appearances, or failed exact membership completeness** cannot support a
current-match conclusion. A successful fetch proves the transport worked; it
never proves the payload described the whole game.

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

Historical values are resolved **per coordinate** by the extractor, not by one
blanket status stamped on every cell. A retained `null` keeps its value AND a
`proven` status; a value that was never retained is `null` with
`not_retained`; a value seen but not safely associable is `null` with
`unproven`. `null` is a legitimate baseball value, so the status — not the
value — is what distinguishes them.

When the artifacts themselves are not verified, every historical cell is
`unproven`: "not retained" is a claim about a document, and it requires a
document proven to be the right one.

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
