# Decision: official pitching-line repair plan (2026)

- **Date:** 2026-07-27
- **Status:** Implemented (read-only planner). No apply mode, no write, no backfill, no
  reconciliation, no deletion, no change to the completeness diagnostic, the canonical
  aggregation, or any validation threshold.
- **Scope:** A deterministic, production-capable but strictly read-only generator that turns
  the accepted completeness proof into a reviewable repair manifest.

## Decision statement

The repair is planned in full, fingerprinted, and reviewed before a single row is written.
This branch produces the manifest. It does not, and cannot, apply it.

## 1. Why the bounded diagnostic artifact cannot be a repair source

The merged completeness diagnostic returns `bounded_details` capped at 100 entries. The
accepted production run found **604** defect lines, so the artifact can name at most a sixth
of them. A bounded report is sound evidence for an accepted **count** — the counters are
computed over the whole population and only the returned detail list is truncated — but it is
never an acceptable source of proposed **writes**. Planning 604 actions from 100 details would
mean inventing the other 504.

The planner therefore re-derives official evidence from scratch: fresh schedule fetch, fresh
box-score fetch, fresh enumeration. Every proposed value in the manifest traces to a source
document fetched during that run, not to a summary of an earlier one.

## 2. Why official evidence is re-derived rather than reinterpreted

Re-derivation is not re-implementation. Official game selection, box-score pitching-section
enumeration, unique-starter identification (`gamesStarted == 1`), official stat parsing,
identity matching, local row matching, and defect classification are all delegated to the
merged `official_pitching_line_completeness_2026` module. The planner adds only the planning
layer on top of those governed results.

That delegation is the point. Two modules that each decide independently what an official
starter is, or what counts as a stat mismatch, will eventually disagree — and the disagreement
would surface as a manifest that repairs something the diagnostic never found. A test asserts
the planner's observed population equals the diagnostic's on identical evidence.

## 3. Why the accepted baseline is fail-closed

The accepted production population is pinned in `ACCEPTED_BASELINE`. If re-derivation observes
any different governed count, the plan sets `result=inconclusive`,
`plan_status=blocked_by_baseline_drift`, `repair_apply_gate=blocked`, and reports each
expected value, observed value, and difference.

The reason is narrow and important: a manifest built against a population that has moved is
not the manifest that was reviewed. Games get replayed, box scores get corrected, and the
ledger receives ongoing ingestion. If any of that shifts the population between review and
apply, the reviewed fingerprint is stale and the review is void. There is deliberately **no
override input** in this branch — an operator who wants to plan against a moved population
must re-establish a new accepted baseline first.

## 4. The 445 missing-line population

445 official pitching lines have no local `GameLog` counterpart. Each becomes exactly one
`game_log_insert_required` action, with every field derived from official evidence:
appearance team from the official box-score side, `games_started` from the unique official
starter, and the seven counting stats from the official pitching line. `innings_pitched` is
derived from the integer outs solely to satisfy the database CHECK constraint that holds the
two representations equal; it is not independently sourced.

Nothing is invented. `Pitcher.team_id`, current team, current organization, current roster
status, current bullpen role, and active status are never written by an insert action, and an
absent official stat blocks the action rather than defaulting to zero.

## 5. The 159 update-row population

159 stored rows exist but differ from official evidence. Each becomes exactly one
`game_log_update_required` action — **one per row, not one per differing field**. A row with
four stat mismatches produces one action listing four changed fields. A row with both a role
mismatch and stat mismatches produces one action containing both.

Identity and provenance are never touched: `pitcher_id`, `appearance_team_id`, the
appearance-team provenance triple, `mlb_game_pk`, and `game_date` are not in the supported
change set. A present local value is never replaced with null, and absent official evidence
never becomes zero.

## 6. Why the metric reason counts overlap

The completeness diagnostic reports `counts_by_reason` over *reason occurrences*, and a single
defective row can carry several — a row that is wrong on runs, earned runs, and hits
contributes three stat-mismatch reasons. Those counts describe how the population is wrong,
not how many rows are wrong. Adding them together would triple-count that row and produce a
manifest with more actions than there are rows to change.

The governing quantity is therefore the **defect line**: 445 missing + 159 defective = 604.
That, not the sum of reason counts, is what `defect_line_action_count` reconciles against.

## 7. Why identity actions are prerequisites, not defect lines

342 of the 445 missing lines belong to people with no local `Pitcher` row. 342 is a count of
*appearances*, not of *people* — one person who pitched in five games contributes five
dependent appearances and needs one identity created.

Identity creations are therefore counted separately by unique MLB person and are **not** added
to `defect_line_action_count`, which stays at 604. The total manifest size is
`unique_identities_requiring_creation + 445 + 159`, and the unique-identity count is computed,
never hardcoded. Each insert whose person is absent carries a dependency on exactly one
identity action, and each identity action lists every appearance depending on it.

## 8. Why position-player pitching must not force position P

The official pitching section includes position players who pitched — the accepted artifact
names Tyler Callihan, Jorbit Vivas, Tyler Heineman, Miguel Rojas, Austin Hedges, Kyle
Higashioka, and Adam Frazier among others. Appearing in a pitching section proves that a person
pitched in one game. It does not prove a primary position of P.

Both existing approved creation paths fall back to `position=... or 'P'`, and the `Pitcher`
model itself defaults `position` to `'P'`. Reusing either would permanently reclassify a
catcher as a pitcher on the strength of one mop-up inning. The planner therefore requires
direct official `primaryPosition` evidence from `/people/{id}`; when that evidence is absent it
emits `official_position_evidence_absent` plus
`identity_creation_blocked_by_model_requirement` and the plan goes inconclusive rather than
guessing.

## 9. Why historical team cannot populate current-team fields

`GameLog.appearance_team_id` records the team a pitcher represented *in that game*. A
`Pitcher` row's team, roster, and activity fields describe the present. A 2026 appearance is
evidence for the former and no evidence at all for the latter — the player may since have been
traded, released, or retired.

Every mutable field is therefore listed explicitly on each identity action under
`explicitly_omitted_mutable_fields` rather than silently skipped, so the omission is auditable.
Two model defaults would otherwise invent state and are named in `model_default_hazards`:
`position` defaults to `'P'`, and `active` defaults to `True`. `active` is proposed as an
explicit NULL — the column is nullable, and every current-roster consumer filters
`Pitcher.active == True`, so an unknown-activity historical identity stays out of every current
read rather than silently joining the active population.

## 10. Why no deletion is authorized

The accepted baseline reports zero extra local lines, zero duplicate local lines, and zero
local identities missing from joined `Pitcher` rows. There is nothing to delete, so no delete
action type exists in the vocabulary — not disabled, absent. If re-derivation ever discovers an
extra or duplicate row, the plan does not invent a deletion: it returns `result=fail`,
`plan_status=blocked_by_contradictory_population`, and reports the exact lines for human
judgement.

## 11. Why no appearance-team repair is authorized

The accepted baseline reports zero appearance-team mismatches. Appearance-team authority is
Foundation 1 governed territory with its own resolver contract, backfill, and audit; a
pitching-line repair is not the place to re-adjudicate it. No action changes
`appearance_team_id` or its provenance, and a discovered mismatch is a hard fail rather than a
planned correction.

## 11a. Why defect-line coverage is proved by keys, not counts

An earlier form of this plan recorded every compared official line in one set and reconciled
`len(all_lines) >= action_count`. That proves almost nothing: with 13,301 official lines and
604 actions the inequality holds even if an action is missing, or if an action targets a line
that was never a defect.

Coverage is therefore proved with three typed populations keyed by
`(game_pk, official_mlb_person_id, appearance_team_id)`:

- `observed_official_line_keys` — every compared official line;
- `observed_defect_line_keys` — only missing lines and defective matched lines;
- `planned_defect_line_keys` — derived only from insert and update actions.

An exact match never enters either defect population. The governing reconciliation is set
**equality** between observed and planned defect keys, plus uniqueness on both sides. That
fails when an action is omitted, when an action targets a different line even though the
counts still agree, and when a line is planned twice. A duplicate official source line is a
contradiction and fails closed rather than being planned.

## 11b. Why dependency existence is not dependency safety

An insertion whose person has no `Pitcher` row carries a dependency on an identity action.
Carrying that reference is not the same as the reference being applicable: an identity blocked
by absent official position evidence still produces a dependency id, and an insertion that
merely *had* a dependency could report `safe_to_apply: true` while the row it would create has
no pitcher to reference.

Safety is therefore propagated explicitly after identity actions are built. For every
dependent insertion the dependency must exist exactly once, be `safe_to_apply`, and carry no
blocking reasons; otherwise the insertion is marked unsafe with a typed
`identity_dependency_blocked` reason (or `identity_dependency_unresolved` when the dependency
is absent or ambiguous). The insertion keeps its dependency ids and stays in the manifest — it
is a real defect that still needs repairing — and no local `Pitcher` id is invented to route
around the block. Because `safe_to_apply` and `blocking_reasons` are both fingerprinted, the
propagation moves the manifest fingerprint, so a reviewed fingerprint can never silently cover
an unsafe dependency.

## 11c. Why the first production fingerprint was not approved

The first production planner run completed cleanly: manifest fingerprint
`dbbc063a0711e57b0dc2d858b7d1d291c568c4990ecff7c9ebf3d1b138cbb2d6`, 71 identity actions,
445 inserts, 159 updates, 675 total actions, every reconciliation true, zero blockers, zero
writes. It was still not approved for apply, because of what its actions contained.

Every planned insertion carried only the seven mandatory season-aggregation counting metrics
plus role and identity. Those seven exist to validate a *bullpen aggregate*; they are not a
complete pitching line. An insertion built from them alone would have created a `GameLog` row
permanently missing `opponent`, `opponent_abbreviation`, `pitches_thrown`, `strikes`,
`batters_faced`, `balls`, `games_finished`, `inherited_runners`,
`inherited_runners_scored`, `save_situation`, `hold`, `blown_save`, `win`, `loss`, and
`save` — and updates never evaluated those fields at all.

Approving that fingerprint would have written 445 rows that satisfy the aggregation and fail
everything else. The fingerprint is therefore superseded rather than advanced, and the
planner now pins the old value so a run can prove it is no longer the manifest under review.

## 11d. Why mandatory season metrics alone cannot complete a GameLog repair

`GameLog` is not an aggregation input; it is the shared appearance ledger. Bullpen
aggregation reads seven of its columns, but fatigue scoring, workload evidence, availability,
inherited-traffic evidence, and appearance context read others. A row that is correct for one
consumer and empty for the rest is not repaired — it is repaired *for one reader*.

Pitch count is the clearest case. `pitches_thrown` is a primary fatigue input: recovery and
availability read pitch counts per appearance, so 445 rows inserted with a NULL pitch count
would be invisible to fatigue evidence for the whole 2026 season while looking complete to
the aggregation that motivated the repair. `strikes`, `batters_faced`, and the
inherited-runner pair carry the same problem for workload and inherited-traffic evidence.

## 11e. Why the 604-line action population is unchanged

This correction enriches the *contents* of the already governed actions. It does not widen the
population: still 445 inserts, still 159 updates, still 604 defect-line actions, and still no
action for any of the 12,697 exact mandatory-metric lines.

A row that matches on all seven mandatory metrics is not promoted to a defect because a
workload field also differs — the defect-line population remains defined by the completeness
diagnostic's classification, and the defect keys still reconcile by set equality. What changes
is that an update already required for a mandatory metric now also carries the workload
corrections for that same row, in the same single action.

## 11f. Why raw official evidence is retained before normalization

The completeness diagnostic normalizes an official pitching line to the seven mandatory
comparison metrics, which is correct for comparison and lossy for repair. The planner
therefore retains the raw official stat object for every defect line, alongside the normalized
metrics, and derives proposed values from the raw object using the production ingestion
contract (`sync._game_log_values_from_stats`, `sync._correction_source_state`,
`sync._authoritative_correction_fields`) rather than a second parser.

Those helpers are reused unchanged rather than extracted: extraction would move code on the
live daily-ingestion path for no behavioural gain, and a regression test pins their output so
ingestion cannot drift silently.

Required-key safety comes from the same contract. A line missing any of `inningsPitched`,
`strikes`, `hits`, `runs`, `earnedRuns`, `baseOnBalls`, `strikeOuts`, or `homeRuns` proposes
nothing, is marked unsafe, and makes the plan inconclusive. Optional fields appear only when
their official source key is genuinely present, so an official zero stays distinct from
official absence — and `numberOfPitches`, which official completed-game lines sometimes omit,
stays NULL and is reported through `workload_field_coverage` instead of being manufactured.

Opponent comes from the opposing official box-score side, never from a mutable player or
current-team assignment.

## 11g. How correction metadata and dependent evidence invalidation must work

A future apply step must follow the correction-metadata contract already implemented by
`sync._upsert_game_log_from_authoritative_values`: `stat_correction_count` increments once per
updated row (never once per changed field), `last_stat_correction_source` records the repair
source identifier, `last_stat_correction_sync_run_id` comes from the apply operation, and
`last_stat_correction_at` is stamped at apply time — which is exactly why it is excluded from
the manifest fingerprint, so a reviewed manifest does not change identity because time passed.

Dependent evidence must be invalidated through the existing governed notification path
(`sync._notify_workload_evidence_game_log_correction`), marking workload, appearance-context,
and inherited-traffic evidence for recomputation. The planner declares this policy as data so
review can approve it with the manifest, and executes none of it: no action proposes
correction metadata, and no action proposes a generated timestamp.

## 11h. Why a local foreign key cannot exist before its identity prerequisite is applied

The enriched planner's first production run failed on two reconciliations —
`every_safe_insert_contains_every_required_correction_field` and
`no_required_official_value_is_defaulted` — with an otherwise clean artifact: 40 of 42
reconciliations true, no blocking reasons, no database writes, and the accepted baseline
matched. Artifact inspection showed exactly 342 safe insertions carrying
`proposed_values.pitcher_id = null`, and those 342 were precisely the insertions dependent on
identity creation. Every one had exactly one dependency, every dependency existed exactly once,
was safe and unblocked, and carried the same official MLB person id as its insertion, with the
identity reciprocally naming its dependent insertion. No other required field was missing.

The null was correct and the validation was wrong.

`GameLog.pitcher_id` is not an official value. Official evidence supplies innings, outs,
strikes, hits, runs, opponent, and the rest; it never supplies a row id in this database.
`pitcher_id` is a **local foreign key** into `Pitcher`, and for an official person with no
local `Pitcher` row that primary key does not exist yet. It is created by the database when
the identity prerequisite is applied. A read-only planner cannot know a future autoincrement
value, and it must not guess one.

`REQUIRED_INSERT_FIELDS` treated `pitcher_id` like any other immediately-available value:
present as a key, non-null, non-empty. That test is right for an official value and wrong for
a deferred relationship. Applying it to all 445 insertions rejected the 342 that were correct
precisely *because* they refused to invent a primary key.

## 11i. Official MLB identity is not a local primary key

Two identifiers are involved and they are never interchangeable.

`official_mlb_person_id` is MLB's stable external identifier for a person. It is authoritative
evidence, it appears on every action, and it is what `Pitcher.mlb_id` stores.

`Pitcher.id` is this database's own autoincrement primary key. It is meaningless outside this
database and is what `GameLog.pitcher_id` references.

Writing the MLB person id into `GameLog.pitcher_id` would produce a foreign key pointing at
whichever unrelated local row happens to hold that primary key — silent, plausible-looking,
and wrong in a way no count-based check would notice. Zero, a negative number, a temporary
number, a guessed local id, and any other placeholder are forbidden for the same reason.

Numeric coincidence is not a defence: a small local id can equal a small MLB id by accident.
The planner therefore accepts a proposed `pitcher_id` only when it equals a `local_pitcher_id`
that was resolved from the local `Pitcher` table **for this official identity** — recorded on
the action as `local_pitcher_mlb_id`, which must equal `official_mlb_person_id`. That is what
`no_insert_uses_an_external_id_as_a_local_pitcher_id` proves.

## 11j. The two valid pitcher-reference states

Every planned insertion resolves its pitcher in exactly one of two ways, recorded on the action
as `pitcher_reference_state`. Anything else is `invalid_pitcher_reference` and unsafe.

**State A — `existing_local_identity`.** The official person already has a local `Pitcher` row.
Required: `local_pitcher_id` is a positive local primary key, `proposed_values.pitcher_id`
equals it, that local row's MLB id equals the insertion's `official_mlb_person_id`, and no
identity-create dependency is present.

**State B — `deferred_identity_creation`.** The official person has no local row.  Required:
`proposed_values.pitcher_id` is null, `local_pitcher_id` is null, exactly one
`dependency_action_id` exists, it resolves to exactly one `identity_create_required` action,
that action is `safe_to_apply` with no blocking reasons, its `official_mlb_person_id` equals
the insertion's, and it reciprocally lists the insertion's action id. The insertion is safe
only while every one of those conditions holds.

A future apply step must, for State B, create the identity dependency first, read back the
newly created local `Pitcher` primary key, and inject that real primary key before constructing
the `GameLog` row. This branch is read-only and does not implement that resolution; the policy
ships as data in `pitcher_reference_resolution_policy`.

The fail-closed cases are typed, not silently recounted: neither a local id nor a dependency
(`local_pitcher_reference_unresolvable`); both at once, a proposed id that differs from the
local id, or a local row belonging to a different identity (`local_pitcher_reference_conflict`);
more than one dependency or a duplicated dependency (`identity_dependency_ambiguous`); an
absent dependency (`identity_dependency_unresolved`); a blocked dependency
(`identity_dependency_blocked`); a dependency for a different person
(`identity_dependency_mlb_identity_mismatch`); an identity that does not name the insertion back
(`identity_dependency_not_reciprocal`); and an MLB person id substituted for the primary key
(`external_mlb_id_used_as_local_pitcher_id`).

## 11k. Why `pitcher_id: null` is intentional only for a safe deferred dependency

A null foreign key is not self-justifying. It is legitimate only as the visible consequence of
a reviewed, safe, matching, reciprocal identity dependency — which is why the required-value
contract was **split** rather than simply relaxed.

`REQUIRED_INSERT_VALUE_FIELDS` holds the 19 ordinary official values, each still required
present and non-empty, checked by `every_safe_insert_contains_every_required_non_fk_value` and
`no_required_official_value_is_defaulted`. `pitcher_id` moved out of that check and into the
pitcher-reference contract, not out of validation altogether. Dropping it from the required set
with nothing in its place would have accepted an insertion with no pitcher at all.

`pitcher_reference_coverage` reports the derived shape of the population:
`insert_actions_with_existing_local_pitcher_id`,
`insert_actions_with_deferred_identity_dependency`,
`deferred_identity_inserts_with_safe_dependency`,
`deferred_identity_inserts_with_unresolved_dependency`,
`deferred_identity_inserts_with_mismatched_identity`, and
`inserts_with_invalid_pitcher_reference`. For the accepted production population these are 103,
342, 342, 0, 0, and 0. Those numbers are derived from the manifest and compared in tests; none
of them is hardcoded as a planner result.

The 445 insert, 159 update, and 604 defect-line populations are unchanged. Reference validation
decides whether an insertion is *safe*, never whether a line is a *defect*.

## 11l. Why the failed production fingerprint is not approved

The failed run's manifest fingerprint,
`9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7`, is pinned in the planner as
`FAILED_PRODUCTION_MANIFEST_FINGERPRINT` and reported with
`failed_production_manifest_fingerprint_approved: false`.

It is evidence of the failure under repair, not an approval. A `result: fail` artifact cannot
confer approval on its manifest, however clean the rest of it looks: the run's own
reconciliations declared the manifest not reviewable, and approval that ignores a failing
reconciliation is not approval at all.

This change also adds two evidence fields to every insertion — `local_pitcher_mlb_id` and
`pitcher_reference_state` — so a reviewer can see from the action itself which of the two
resolution paths applies and why a null foreign key is correct. Those fields are part of the
manifest, so the fingerprint changes normally, as it must whenever manifest content changes.

Either way, approval requires a **newly generated production artifact** whose `result` is
`pass`, with every reconciliation true, and its exact fingerprint reviewed again after that
passing run. Had the fix been purely semantic and the manifest byte-identical, the unchanged
fingerprint still would not have inherited approval from a failed run — a fingerprint is
approved by review of a passing artifact, never by resemblance to a prior one.

## 11m. Why the 604-line defect population is immutable for this review

The dependency-aware planner ran cleanly in production at `6a8e7f4`: 1,570/1,570 games,
13,301 official lines, 12,697 exact matches, 445 inserts, 159 updates, 604 defect-line
actions, zero blocking reasons, every reconciliation true, no database writes. It still
returned `inconclusive` / `blocked_by_baseline_drift` on exactly one comparison:

```
missing_lines_dependent_on_identity_creation   expected 342   observed 341   difference -1
```

The defect population is what review approves. Each of the 604 lines is a claim about
official MLB evidence and about what the stored `GameLog` ledger does or does not contain:
which games were played, which pitchers appeared, which lines are absent locally, which
stored rows disagree with official evidence. None of that can move without the reviewed
repair meaning something different, so all of it stays pinned to exact equality —
`official_pitching_lines`, `exact_match_count`, `missing_line_count`,
`defective_matched_line_count`, `defect_line_action_count`, the game and side counts, the
local line counts, `role_corrections_planned`, and every count that must remain zero.

## 11n. Why local identity availability is mutable

`missing_lines_dependent_on_identity_creation` is not in that category, and pinning it was a
category error.

It does not describe official evidence and it does not describe the defect. It describes the
**local `Pitcher` table at the instant the plan runs** — a partition of the same 445 missing
lines into "this official person already has a local row" and "this official person does
not yet". The 445 is fixed; the boundary inside it is not.

Identity rows are created by ordinary, governed, synchronized operation. Daily ingestion
meets a pitcher for the first time and stores the identity. That is the system working, not
drifting. Between two planner runs a local `Pitcher` row can legitimately appear for an
official person who previously had none, and when it does the correct plan changes shape:
one fewer identity prerequisite, one fewer deferred insertion, one more existing-identity
insertion. The official line, its statistics, its role, its game, its appearance team, and
its defect classification are all untouched.

The concrete case: official MLB person **681806, Andrew Wantz**, appearing for official team
139 in game 822975. Action `gamelog:insert:822975:681806:139` previously carried a
`deferred_identity_creation` reference and depended on `identity:create:681806`. It now
resolves through local `Pitcher.id 804` with `Pitcher.mlb_id 681806` and carries an
`existing_local_identity` reference with no dependency at all. That is a correct plan
responding to a correct database.

The partition therefore moved from **342 deferred / 103 existing / 71 identity actions** to
**341 deferred / 104 existing / 70 identity actions**, while **445 missing lines, 159
defective rows, and 604 defect-line actions did not move at all**. One insertion changed how
it reaches its pitcher. Nothing changed about which lines need repairing.

**Appearances resolved is not identities resolved.** One official person may have many
dependent missing insertions, so resolving a single identity can move many deferred
appearances at once — 342 → 327 deferred alongside 71 → 70 identities is fifteen appearances
resolved by *one* identity. The Wantz case is one identity with one appearance, so both
numbers happen to be 1; that coincidence is not the contract.
`net_identities_resolved_since_snapshot` is therefore derived only from
`unique_identities_requiring_creation`, and
`net_deferred_appearances_resolved_since_snapshot` only from
`missing_lines_dependent_on_identity_creation`. Neither is computed from the other, and
`counts_are_distinct` records which partition field each one reads.

`transition_kind` accordingly does not require the identity delta to equal the appearance
delta, because the appearances-per-identity ratio is arbitrary. It requires only a
structurally valid direction: the appearance partition must balance (whatever leaves deferred
arrives at existing), and the appearance and identity movements must not point in
contradictory directions. `identity_resolution_advanced` needs a balanced partition with
`deferred_delta <= 0`, `identity_delta <= 0`, and at least one strictly negative;
`identity_resolution_regressed` is its mirror; anything contradictory or unbalanced is
`identity_resolution_mixed`. All of it remains observational and gates nothing.

## 11o. Why replacing 342 with 341 would have been the wrong fix

Editing the expected value to 341 would have made the next run pass and left the structure
exactly as wrong. The planner would still be asserting that a mutable property of the local
database must equal a historical snapshot, and the very next legitimate identity resolution —
one more pitcher learned, on any day, through normal ingestion — would fail the plan again
for the same non-reason. The number would be chased forever and would never be right for
longer than the interval between synchronizations.

`missing_lines_dependent_on_identity_creation`, `missing_lines_using_existing_identity`,
`unique_identities_requiring_creation`, and the pitcher-reference coverage counts are
therefore removed from immutable equality entirely. They remain fully reported, and the
accepted values (342 / 103 / 71) are retained in `PRIOR_IDENTITY_RESOLUTION_SNAPSHOT` as
**observational** evidence only, so a reviewer can see how identity resolution has advanced.
`identity_resolution_transition_from_prior_snapshot` classifies the movement and records
`snapshot_is_compared_for_equality: false`. Nothing gates on it.

## 11p. Why internal partition reconciliation is stronger than snapshot equality

Removing a check would be a weakening if nothing replaced it. What replaces it is strictly
stronger evidence.

Snapshot equality proved one thing: a count had not moved since a past run. It could not
detect an identity resolved to the wrong person, an identity action for a person who already
has a local row, a deferred insertion whose dependency does not name it back, or a local
primary key belonging to someone else — all of which preserve the count.

The partition reconciliations verify the current state directly:
`missing_lines_equal_existing_plus_deferred_identity_inserts`,
`identity_partition_covers_every_missing_line_when_baseline_matches`,
`every_insertion_has_exactly_one_valid_pitcher_reference_state`,
`unique_identity_actions_reconcile_to_deferred_official_identities`,
`no_identity_action_for_an_already_resolved_local_identity`,
`no_local_identity_is_accepted_through_name_matching`,
`current_team_and_roster_are_irrelevant_to_identity_resolution`, and
`every_identity_transition_is_a_verified_local_primary_key`.

A deferred insertion may become an existing-identity insertion only when the local row
exists, its `mlb_id` equals the official person id exactly, its primary key is positive, the
identity-create action is gone, the dependency is gone, and the insertion proposes that
verified primary key. Identity is resolved by `pitcher.mlb_id` equality and by nothing else —
never by name similarity, and never by current team, organization, or roster status, which
are irrelevant to a historical appearance. Every conflicting, duplicate, ambiguous,
mismatched, or unresolvable identity still blocks its action and the plan.

So the planner still fails closed on anything that would change the repair, and no longer
fails on the database correctly learning who someone is.

## 11q. Why the current inconclusive fingerprint remains unapproved

The `6a8e7f4` production run produced manifest fingerprint
`dd453cd63b1e4ccc14b5ff97c962635d6c5eda296a4e4ef63066105eeec225c6` with `result:
inconclusive`. It is not approved and cannot be.

An inconclusive artifact is the planner declining to certify its own manifest. Approving a
fingerprint it refused to stand behind would invert the gate: review would be attaching to a
manifest whose own reconciliations reported it not reviewable. That the failure turned out to
be a validation defect rather than a data problem does not retroactively make the artifact a
passing one — it makes it an artifact that must be regenerated.

If the corrected planner produces a byte-identical manifest, the fingerprint may legitimately
be the same value. It still does not inherit approval from the inconclusive run. Approval
requires a newly generated production artifact whose `result` is `pass`, with every
reconciliation true, and that exact fingerprint reviewed again against that passing run. Any
change to manifest content changes the fingerprint normally, as it must.

## 12. Why the full manifest requires an exact reviewed fingerprint

The manifest is fingerprinted with SHA-256 over its complete normalized serialization: UTF-8,
sorted keys, deterministic array ordering, null preserved distinctly from zero, volatile fields
such as `generated_at` excluded. Every action additionally carries a source fingerprint over
its official evidence, and every update carries a comparison fingerprint over the local row id,
current values, proposed values, changed fields, reason codes, and official evidence.

The fingerprint changes if an action is added or removed, an action id changes, a source value
changes, a current or proposed value changes, a changed field or reason code changes, a
dependency changes, `safe_to_apply` changes, a blocking reason changes, or the normalized
ordering changes. The bounded preview is excluded from the fingerprint entirely, so summarizing
for a step summary can never alter what was reviewed.

A future apply step must require this exact reviewed fingerprint. That is what makes review
meaningful: approval attaches to a specific set of 604-plus actions with specific values, not
to the general idea of repairing the ledger.

## 13. Why the apply step must be a separate branch and gate

This branch produces a plan that a human has not yet read. Shipping the planner and the writer
together would mean the first run of the writer executes a manifest nobody reviewed, and the
review gate would exist only by convention.

Separating them makes the gate structural. This branch has no apply mode, no writer, no
`--apply` flag, and no workflow input that could accept a fingerprint — the capability simply
is not present. `repair_apply_gate` reports `blocked_pending_fingerprint_review` on a clean
full-season plan and `blocked` otherwise. A scoped `--team-id`/`--game-pk` run returns
`plan_scope=diagnostic_subset` and `blocked_subset_not_apply_eligible`, so a convenient partial
run can never be mistaken for the reviewable artifact.

## 14. Verification plan (descriptive)

After a future approved apply: rerun the completeness diagnostic and require every official
line to match; rerun the canonical aggregation in `local_only` mode and require PASS; rerun it
in `official_validation` mode and require PASS; review the generated artifacts; only then
consider Foundation 3B reader work. The planner returns these steps as data and executes none
of them.

## 14a. The Brandyn Garcia exact-to-defective transition

The repaired planner ran cleanly in production at `970664f` — 1,570/1,570 games, 13,301
official lines, 445 missing lines, a valid 341/104/70 identity partition, every reconciliation
true, no blocking reasons, no writes — and still returned `inconclusive` /
`blocked_by_baseline_drift`. Three immutable defect counts moved by exactly one:

```
exact matches            12,697 -> 12,696
defective matched lines     159 -> 160
defect-line actions         604 -> 605
```

The whole of that movement is a single line. Official MLB person **805299, Brandyn Garcia**,
relieving for official team **109** in game **825058** on 2026-07-20, stored locally as
**GameLog 43765**. The manifest carries one additional update action,
`gamelog:update:43765:825058:805299`, changing `hits_allowed` from 1 to 0 with reason
`hits_mismatch`, `safe_to_apply: true`, and no blocking reasons.

## 14b. Why the current mismatch does not prove historical causation

The artifact proves exactly one thing: right now the local row says one hit and the current
official box score says zero. That is a statement about two values at one moment. It is not a
statement about which value moved.

Two incompatible histories produce it identically:

- **An official stat correction.** MLB reported one hit when the line was ingested, the local
  row correctly recorded one hit, and MLB later revised the box score to zero. The ledger was
  right when written and is now stale. The repair is legitimate and the accepted baseline
  genuinely moved.
- **A local ingestion mutation.** MLB reported zero hits all along and local ingestion wrote
  one — a parsing fault, a mis-keyed line, a backfill, or a correction that changed the wrong
  row. The ledger was never right, and the interesting question is what else that fault
  touched.

The remedies differ. The first is an ordinary re-sync of a corrected line. The second is a
defect in the ingestion path that a single-row repair would paper over. Choosing between them
by looking at today's values is guessing, and a repair approved on a guess is not a reviewed
repair.

## 14c. Which durable historical sources exist, and which do not

`services/official_pitching_line_transition_diagnostic_2026.py` searches every local store
that could establish a prior value, and reports each one whether or not it holds anything.

Sources that exist and are checked: `game_logs` correction metadata
(`stat_correction_count`, `last_stat_correction_at`, `last_stat_correction_source`,
`last_stat_correction_sync_run_id`); `evidence_citations.cited_values`, the only store that
can retain a prior field value; `evidence_objects` invalidation markers; `sync_runs`;
`postgame_processed_games`; `sync_failures`; and retained repository artifacts.

Sources that **do not exist**, reported as explicit limitations rather than silent gaps:

- **Official response snapshots.** No table retains the raw box-score response as fetched at
  ingestion time. A prior *official* value cannot be read back from local state at all.
- **Workflow run artifacts.** The private artifacts from the accepted diagnostic run are not
  reachable from application code or database state. They live in GitHub Actions under a
  14-day retention window and must be inspected there.

Two structural facts constrain what any local search can prove. `game_logs` has no
`updated_at` column and no row-version history, so the governed correction metadata is the
only durable record that a row was ever rewritten. And `stat_correction_count` increments once
per corrected **row**, never per field, so even a recorded correction does not say that
`hits_allowed` was the field that moved.

The consequence is that the expected production answer is `historical_state_unprovable` with
result `inconclusive`. The diagnostic classifies `official_source_changed` only when a durable
prior *official* value is retained and differs, and `local_game_log_changed` only when a
durable prior *local* value is retained and differs. **Absence of history is never reported as
proof that MLB changed the box score** — that rule is enforced by the reconciliation
`absence_of_history_is_not_reported_as_official_change`.

## 14d. Why the accepted baseline must not be edited before the transition is explained

Changing 12,697 / 159 / 604 to 12,696 / 160 / 605 would clear the drift and destroy the
evidence in one move.

The baseline exists so that the population under review cannot shift without someone noticing.
It has now noticed something real. Editing the expected numbers to match the observation
converts a detection into a rubber stamp: the planner would report a clean baseline while the
question of whether the local ledger contains an ingestion fault stays permanently unasked. If
the cause turns out to be a local mutation, the amended baseline would have accepted a
corrupted row as the new normal.

A baseline amendment may be considered only after the transition diagnostic runs in production
and its result is reviewed. This branch changes no baseline value, and a test asserts that the
diagnostic module never references `ACCEPTED_DEFECT_BASELINE` at all.

## 14e. Why the current fingerprint remains unapproved and every gate stays blocked

Manifest fingerprint `3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b` comes
from an `inconclusive` run and is not approved, joining
`9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7` and
`dd453cd63b1e4ccc14b5ff97c962635d6c5eda296a4e4ef63066105eeec225c6`. All three are pinned in
the diagnostic as known and refused, and none is wired to any apply path — because no apply
path exists.

The diagnostic is read-only in the same sense as the planner: no writer, no apply mode, no
repair, no baseline amendment, no fingerprint approval, and `database_writes_performed: false`
asserted by tests that capture emitted SQL. Identity is resolved by exact `pitcher.mlb_id`
equality; name similarity, current team, organization, and roster status are never consulted
for a historical appearance. Foundation 3B, the public reader, Team State performance, Share
Card performance, and SC-05 all remain blocked, and `repair_apply_gate` stays `blocked`.

## 15. Operation

- Service: `backend/services/official_pitching_line_repair_plan_2026.py`
- CLI: `backend/scripts/run_official_pitching_line_repair_plan_2026.py`
- Workflow: `.github/workflows/official_pitching_line_repair_plan.yml` (dispatch-only)
- Tests: `backend/tests/test_official_pitching_line_repair_plan_2026.py`

Production plan: dispatch with `season=2026`, `as_of_date=2026-07-25`, `preview_limit=100`,
`team_id` and `game_pk` blank. The full manifest ships in the private artifact and is never
truncated; the step summary carries the bounded preview only.

## 16. Boundary held

Read-only. Foundation 3B, the public reader, Team State performance, Share Card performance,
and SC-05 all remain blocked.
