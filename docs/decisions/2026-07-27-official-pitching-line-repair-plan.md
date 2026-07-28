# Decision: official pitching-line repair plan (2026)

- **Date:** 2026-07-27
- **Status:** Implemented (read-only planner, plus the one-time fingerprint-locked apply
  path in §17-§17n). No backfill, no reconciliation, no deletion, no change to the
  completeness diagnostic, the canonical aggregation, or any validation threshold. The apply
  workflow has not been dispatched and production data is unchanged.
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

## 14f. Baseline lineage: V1 retained, V2 active

The accepted defect baseline is no longer a single constant that can be edited in place. It is
a versioned lineage.

**V1** is the population accepted from the merged completeness diagnostic and independently
reproduced by four retained production artifacts: 13,301 official lines, 12,697 exact matches,
445 missing lines, 159 defective matched lines, 604 defect-line actions, plus the eleven other
governed counts. It is **retained unmodified, forever**. A reconciliation compares
`ACCEPTED_DEFECT_BASELINE_V1` against an independent literal copy, so editing V1 in place
fails closed rather than silently redefining what was originally accepted.

**V2** is the active planning baseline. It is constructed *from* V1 plus the amendment record,
not typed out separately, so it cannot drift from V1 in any field the amendment does not name.

`ACCEPTED_DEFECT_BASELINE` points at V2. `ACTIVE_ACCEPTED_DEFECT_BASELINE_VERSION` is `v2`,
`PRIOR_ACCEPTED_DEFECT_BASELINE_VERSION` is `v1`, and `defect_baseline_lineage` reports the
whole history in every artifact so a reviewer never has to consult a prior commit.

## 14g. Why exactly three counts changed

`DEFECT_BASELINE_AMENDMENT_1` names three fields and three deltas:

```
exact_match_count             12,697 -> 12,696   (-1)
defective_matched_line_count     159 -> 160      (+1)
defect_line_action_count         604 -> 605      (+1)
```

Sixteen governed values are byte-identical between V1 and V2 — the official line count, the
missing-line count, the role-correction count, the duplicate, extra, appearance-team-mismatch
and evidence-availability counts, and every game/side/local total. One line changed
classification from exact to defective; nothing appeared, disappeared, or moved teams. The
amended population still partitions the same official evidence: 12,696 + 445 + 160 = 13,301,
and 445 + 160 = 605.

The line is official MLB person **805299, Brandyn Garcia**, relieving for official team **109**
in game **825058** on 2026-07-20, stored locally as **GameLog 43765**, on field
`hits_allowed` — official `hits` 0 against local 1, reason `hits_mismatch`, one update action
`gamelog:update:43765:825058:805299`. Its stable key `825058:805299:109` is recorded in the
amendment and reconciled against the observed population at plan time.

## 14h. The bounded transition window, and why causation stays unprovable

Five retained artifacts bound when the divergence became observable:

```
2026-07-27T16:20:04.642412Z  completeness 30284218611  line exact
2026-07-27T18:51:16.974117Z  repair plan  30295617314  line exact
2026-07-27T23:44:58.208999Z  repair plan  30315122495  line exact
2026-07-28T00:57:38.449240Z  repair plan  30318846061  line exact
2026-07-28T10:22:18.985546Z  repair plan  30350475893  line defective
```

The window is therefore after `2026-07-28T00:57:38.449240Z` and on or before
`2026-07-28T10:22:18.985546Z`, with each report's SHA-256 recorded in the amendment.

That bounds *when*. It does not establish *which side moved*, and nothing in this amendment
claims to. The pre-transition artifacts record only that the line was exact — never the value
it was exact **at**. Exactness at 1/1 and exactness at 0/0 are indistinguishable in every
retained artifact, because the completeness report sorts findings ahead of exact matches and
truncates to 100 details (all 100 were findings), and the repair manifest contains actions
only. Absence of a repair action proves the line was not a defect then; it proves nothing about
its values.

So the amendment records `historical_transition_classification: historical_state_unprovable`,
`confidence: not_provable_from_retained_evidence`, `causation_claimed: false`,
`official_source_change_claimed: false`, and `local_game_log_change_claimed: false`. **This is
not a claim that MLB changed its box score, and not a claim that the local ledger was
mutated.** Both remain possible; neither is asserted.

## 14i. Why current official authority is sufficient for current repair planning

Two different questions are being answered by two different components, and conflating them
is what a versioned amendment prevents.

The **transition diagnostic** answers historical causation. Its verdict is unchanged and is not
retroactively upgraded by this amendment: `historical_state_unprovable`, `inconclusive`. This
branch does not weaken or remove it.

The **planner amendment** answers what governs the repair now. For that, current official MLB
box-score evidence is sufficient and is the stated authority (`current_authority_basis:
current_official_mlb_boxscore_evidence`). The proposed write is `hits_allowed` 1 → 0 because
the official box score currently reports 0. That would be the correct proposed value under
either history: if MLB revised the line, the ledger is stale and should follow; if ingestion
wrote a wrong value, the ledger is wrong and should be corrected. The remedy for *this line*
is the same either way — which is precisely why accepting current state does not require
resolving the past, and why doing so makes no claim about it.

What the unresolved history still costs is scope. If the cause was an ingestion fault, other
rows could carry the same fault, and that question stays open. The amendment covers one
reviewed line and grants nothing beyond it: any further movement in any governed count is
ordinary baseline drift and still fails closed.

## 14j. Why the fingerprint remains unapproved and every gate stays blocked

`3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b` came from an `inconclusive`
run. The amended planner may reproduce that exact value if the normalized 675-action manifest
is byte-identical, and it still inherits no approval — a fingerprint is approved by review of a
**passing** artifact, never by resemblance to a prior one. It joins `9b8ab677…` and
`dd453cd6…` as pinned and refused.

Approval requires a newly generated production artifact with `result: pass`, every
reconciliation true, and that exact fingerprint reviewed after that passing run. No
fingerprint-acceptance input, fingerprint-approval constant, apply input, writer, or automatic
dispatch was added. `repair_apply_gate` remains `blocked_pending_fingerprint_review` on a clean
plan and is never `open`. Foundation 3B, the public reader, Team State performance, Share Card
performance, and SC-05 all remain blocked.

## 14k. Why a full-season plan must prove the reviewed line, not merely fail to contradict it

The first cut of the amendment decided whether to check the reviewed line by asking whether
it was present:

```
amendment_applicable = official_line_occurrences > 0
```

with each per-line check written as `(not amendment_applicable) or condition`. That fails
open. If the line vanished, `amendment_applicable` went false and all six checks passed
vacuously.

The consequence is not theoretical. A full-season population could keep every accepted
aggregate — 12,696 exact, 445 missing, 160 defective, 605 defect-line actions — while
`825058:805299:109` quietly became exact and some unrelated line became defective in its
place. The counts reconcile, the baseline matches, and a presence-gated check never runs.
A one-line reviewed amendment would have become a blanket approval of any population with
the same totals.

Applicability is therefore decided by **scope and governance**, never by presence. The
amendment is part of V2's definition, so it governs a full-season run whose active
acceptance is V2 *and* whose observed population matches it — which is exactly the dangerous
case. In that situation `required_for_scope` is true and absence is a failure, not a bypass.
A run whose population has already drifted is inconclusive on the baseline comparison
regardless and can never be apply-review ready, so nothing is laundered through it.

A full-season governed run must prove, unconditionally: the official key occurs exactly once;
exactly one update action maps to it; the action id is `gamelog:update:43765:825058:805299`;
it targets GameLog 43765; `changed_fields` is exactly `['hits_allowed']`; current is 1 and
proposed is 0; `reason_codes` is exactly the governed `hits_mismatch`, so no unrelated reason
can satisfy the amendment; the action is safe with no blocking reasons; its person, game, and
appearance team match the stable key; and no second action claims the reviewed key or the
reviewed action id.

`defect_baseline_amendment_line_validation` reports the outcome as `validated`,
`missing_from_full_season_population`, `contradictory`, `not_applicable_to_subset`, or
`not_applicable_to_unamended_baseline`, alongside every observed value. Only `validated`
means the line was actually checked and passed.

Two of the earlier structural reconciliations restated the production literals 13,301 and
605. Those now assert the invariant — the partition sums, and missing plus defective equals
the action count — while the production values stay pinned by V2 itself and by a direct test.
A reconciliation that merely repeats a constant proves nothing the constant does not already
state, and is unusable at any other scale.

## 14l. Why a scoped run may report non-applicability but can never be approved

A subset run's scope may genuinely exclude game 825058, and a line outside the scope was
never examined. Reporting that as a successful validation would be a lie; it is reported as
`not_applicable_to_subset` with `validated: false`.

A subset that *does* contain the line must still validate it exactly — a scoped run cannot be
used to launder a contradictory line into an accepted state. And in every case a subset
remains `result: inconclusive`, never reaches `plan_status: ready_for_apply_review`, and keeps
`repair_apply_gate: blocked_subset_not_apply_eligible`. Non-applicability is a statement about
what was examined, never a grant of approval.

## 17. Why the fingerprint is now approved, and what "approved" means

The read-only planner ran in production at merge commit
`b0850719c7ab2c4e9ee232758cd57ba25030364b` with `season=2026`, `as_of_date=2026-07-25`,
`game_type=R`, no team filter, no game filter, and full-season scope. That run returned
`result: pass`, `exit_code: 0`, `plan_status: ready_for_apply_review`,
`database_writes_performed: false`, every reconciliation true, empty
`blocking_counts_by_reason`, and empty `duplicate_action_ids`. Its manifest fingerprint is

```
3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b
```

covering 675 actions: 70 identity creations, 445 GameLog insertions, 160 GameLog updates,
605 of which are defect-line actions.

Approval is **exact and one-time**. It is not a pattern, a prefix, an action-count range, an
alternate fingerprint, a regenerated equivalent, or a semantically similar plan. It applies
only to season 2026, as-of 2026-07-25, full-season scope, the V2 defect baseline, amendment
`defect_baseline_amendment_1_brandyn_garcia_hits_allowed`, and that exact 675-action
manifest. Any other fingerprint aborts before the first write.

The constant lives in the apply service, not in the planner. A planner that knows which of
its outputs is approved is no longer a plan generator; it is a plan generator with an opinion
about its own authority. It is also a single narrowly named constant rather than a registry
entry: a registry would be a reusable approval mechanism, and this approval is not reusable.
A second repair requires a second review, not a second row.

## 17a. Why the earlier inconclusive artifacts did not approve anything

Three fingerprints exist in this lineage and only the third is approved.

`dbbc063a0711e57b0dc2d858b7d1d291c568c4990ecff7c9ebf3d1b138cbb2d6` came from the first
production planner run. That manifest carried only the seven mandatory season metrics plus
role and identity, so applying it would have written permanently incomplete GameLog rows.

`9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7` came from the enriched
planner's first production run, which **failed**: required-insert validation treated
`pitcher_id` as an ordinary immediately-available value and so rejected the 342 legitimately
deferred insertions. A failed run is evidence of a defect, never an approval.

Both are pinned in the planner as `prior_production_manifest_fingerprint` and
`failed_production_manifest_fingerprint`, with
`failed_production_manifest_fingerprint_approved: false`, so the record of what was *not*
approved is as durable as the record of what was.

## 17b. Why the planner is regenerated instead of replaying a stored manifest

A stored manifest is a claim about a database that has since moved on. Replaying it would
write values derived from a state that may no longer exist.

The apply command therefore regenerates the planner from live production state immediately
before opening the mutation transaction. Regeneration proves the same 675 actions are still
the right 675 actions against the rows that exist right now; the fingerprint proves the
regenerated plan is the *reviewed* plan rather than a fresh plan that merely resembles it.
Neither property is sufficient alone.

The gate requires all of: planner capability, `result: pass`, `exit_code: 0`,
`mode: read_only`, `database_writes_performed: false`, `plan_scope: full_season`,
`plan_status: ready_for_apply_review`, the approved inputs, active baseline version `v2` with
prior `v1`, `defect_baseline_matches_accepted_diagnostic`,
`identity_resolution_partition_valid`, every reconciliation true, empty blocking counts,
empty duplicate action ids, 675 total actions split 70/445/160, 605 defect-line actions, the
identity partition 341/104/70, the governed migration head, the reviewed amendment line
`validated` and `required_for_scope`, the amendment action matching the approved record
field for field, and finally exact fingerprint equality.

There is **no operator override**. `apply_reviewed_repair` takes no force, override, or
skip parameter, and the workflow exposes no input that could carry one. An override would
convert an exact approval into a discretionary one, which is the whole thing this design
exists to prevent.

## 17c. Why the migration head contract had to change

The apply path needs a durable execution ledger, and a ledger needs a table, and a table
needs a migration. Adding one moves the Alembic head off `a4f1c7e9b3d2`.

`EXPECTED_MIGRATION_HEAD` is not decorative: the completeness diagnostic and the canonical
season aggregation audit both add `migration_head_mismatch` to their **fail** reasons when
the observed head differs. Both are required post-commit verifications for this repair.
Leaving the constant pinned to the prior revision would have made every post-commit check
fail by construction, so the expected head moves forward to `c7b3e5a91d48` across the
services, the coverage-audit script, the production-maintenance workflow, and the tests that
pin it.

The migration is purely additive — one new table, no existing table touched, no existing row
modified, no backfill, independently reversible — so no diagnostic's reading of `game_logs`
or `pitchers` changes. The apply gate additionally requires that
`c7b3e5a91d48`'s declared `down_revision` is `a4f1c7e9b3d2`, which is what proves no
*unreviewed* schema change landed between the approved plan and the apply.

## 17d. Transaction boundaries

One transaction covers every mutation. The planner's read-only queries run first, in whatever
transaction was ambient; that transaction is explicitly ended before the advisory lock is
taken, so the boundary is exact: everything from the lock to the single `session.commit()` is
one transaction.

Inside it, in this order and never interleaved:

1. `identity_create_required` — 70 identities, flushed so each real local primary key exists
2. `game_log_insert_required` — 445 rows
3. `game_log_update_required` — 160 rows
4. in-transaction read-back verification of everything written
5. the durable execution-ledger row
6. commit

There is no intermediate commit anywhere. Any failure at any step rolls back all 675 actions,
including the ledger row, so a rolled-back attempt leaves the database exactly as it was.

## 17e. Advisory locking

A dedicated PostgreSQL **transaction-level** advisory lock
(`official_pitching_line_repair_2026.transaction_advisory_lock`) is acquired before any
mutation precondition is read. Its key is derived deterministically from the contract name
rather than being a magic number, so a reader can reproduce it.

`pg_try_advisory_xact_lock` is used rather than `pg_advisory_lock`: it returns immediately.
Waiting would let a second operator queue behind a repair that is about to change the very
rows their run planned against. Unavailable means abort without writes, and the correct
response is to regenerate the plan, not to wait.

Transaction-level rather than session-level means the lock is released by the same commit or
rollback that decides the repair. A crashed process can never strand it.

The lock serializes this apply path against a second invocation of itself and against any
future official pitching-line repair that adopts the same lock contract. On a dialect with no
transaction-level advisory lock — the single-writer test target — the status is reported as
`single_writer_dialect_no_advisory_lock` with `acquired: false`, so it can never be misread
in an artifact as a real acquisition.

## 17f. Identity dependency resolution

An identity is resolved by exact `Pitcher.mlb_id` equality and by nothing else. Name
similarity, current team, organization, roster status, and active status are all irrelevant
to a historical appearance and are never consulted; the service contains no reference to
`Pitcher.full_name`, `Pitcher.team_id`, or `Pitcher.roster_status`.

Before creating any identity the apply path verifies no local `Pitcher` carries that
`mlb_id`, that exactly one identity action exists for it, that the action's official person
evidence still hashes to its recorded source fingerprint, that every dependent insertion is
present in the manifest, and that every dependent insertion points reciprocally back at this
action and carries the same official person id.

Only `proposed_identity_fields` are written. The official primary position is preserved
verbatim **including a non-pitcher position** — appearing in a pitching section does not
reclassify a position player. `team_id`, `team_name`, `team_abbreviation`, the team-assignment
fields, the roster fields, `age`, and `jersey_number` are never populated.

`active` is written as an explicit SQL `NULL`. This required `sqlalchemy.null()` rather than
Python `None`: assigning `None` to a column carrying a Python-side default leaves the
attribute unset as far as the insert is concerned and the default fires anyway, so
`Pitcher.active` would have been stored as `True` — asserting current activity that a
historical appearance cannot prove. Every current-roster read filters `active == True`, so
`NULL` keeps an unknown-activity historical identity out of all of them. The same hazard and
the same fix apply to the optional `GameLog` booleans, where a default would have turned
official *absence* into an official `False`.

If an identity now exists because another process created it after planning, the repair
aborts and rolls back. The reviewed action said "create"; silently converting it to "reuse"
would apply a manifest nobody reviewed.

For insertions, the deferred foreign key is resolved from the identity created earlier in the
same transaction and injected only when constructing the row — the reviewed manifest itself is
never mutated. An existing-identity insertion uses the local primary key the manifest carries,
and that key is accepted only after the row it points at is row-locked and proven to carry the
matching `mlb_id`. A numeric coincidence between a local primary key and an official MLB
person id is not an identity and never satisfies the check.

## 17g. Update preconditions

Each of the 160 updates locks its exact `GameLog` by `local_game_log_id` with a row-level
lock, then requires: exactly one row exists; its id matches; its `mlb_game_pk` matches; the
joined `Pitcher.mlb_id` equals the official person id; `appearance_team_id` equals the
approved official team; every field in `current_values` still holds the planned current
value; every changed field appears in both value maps; no proposed value would replace a
non-null stored value with null; the action's official source evidence still hashes to its
recorded fingerprint; and the action is safe with no blocking reasons.

Only `changed_fields` are written. Appearance-team authority is never rewritten by a repair,
so a row attributed to a different official team is a contradiction to abort on rather than a
field to correct.

A changed stored value is **drift**, not a defect: it means something legitimately moved
between planning and applying, so the result is inconclusive with nothing written. A wrong
identity, a wrong appearance team, an ambiguous target, or a tampered source fingerprint is a
**contradiction**, and the result is fail.

## 17h. Correction metadata and dependent-evidence invalidation

Every updated row gets `stat_correction_count` incremented **once per row, never per changed
field**, `last_stat_correction_at` set to the apply timestamp,
`last_stat_correction_source` set to `official_pitching_line_repair`, and
`last_stat_correction_sync_run_id` set to a governed operation id derived deterministically
from the approved fingerprint.

That id is deliberately not a `SyncRun` id — no sync run performs this repair, and borrowing
one would attribute the correction to ingestion. It is recorded on the ledger row so the two
join.

Dependent evidence is invalidated through the **existing** governed contract,
`sync._notify_workload_evidence_game_log_correction`, which marks workload, appearance-context,
and inherited-traffic evidence for recomputation. Calling the existing path rather than
reimplementing it is the point: a repair that defined its own invalidation rules would become
a second, divergent definition of what a correction invalidates. No replacement evidence is
fabricated.

## 17i. The reviewed Brandyn Garcia line, proven twice

The pre-write gate checks the planner's own `defect_baseline_amendment_line_validation`
object. Inside the transaction, under the lock, the apply path checks the **database
directly**: GameLog 43765 exists, game 825058, `Pitcher.mlb_id` 805299, `appearance_team_id`
109, `hits_allowed` currently 1, exactly one update action, `changed_fields` exactly
`['hits_allowed']`, proposed exactly 0, reason exactly `hits_mismatch`, no blocker,
`safe_to_apply` true.

The duplication is deliberate. The first check reads a planner claim; the second reads the
rows. One reviewed line is worth proving twice, from two different sources.

After mutation and before commit it requires `hits_allowed == 0`, every unrelated field
byte-identical to a snapshot taken before the write, `stat_correction_count` increased by
exactly one, correction metadata populated, and dependent-evidence invalidation requested.
Any failure rolls back all 675 actions.

## 17j. The durable execution ledger

`official_pitching_line_repair_executions` (migration `c7b3e5a91d48`) records one governed
repair: capability, approved and regenerated fingerprints stored **separately** so a reviewer
sees both rather than a single value asserting they agreed, planner and apply git SHAs,
season, as-of date, baseline version, amendment id, status, the four action counts, the three
timestamps, and three bounded JSON summaries.

Three invariants are enforced at the database rather than by writer discipline:

- `status` may only ever be `completed`. A repair that did not commit performs no writes, so
  it has nothing to record here; a row asserting an execution that never happened would be
  worse than no row. Failed and rolled-back attempts are evidenced by the private workflow
  artifact instead.
- `approved_manifest_fingerprint` is UNIQUE, so a second completed execution of the same
  approved manifest is impossible even under concurrent dispatch. The apply path also checks
  for an existing completed row immediately after taking the lock and aborts without writes.
- the three action counts must sum to the recorded total, so a miscounted row cannot be
  stored.

The row is written inside the repair transaction and commits with it: either the ledger row
and the mutated rows both exist, or neither does.

## 17k. In-transaction verification

Before the commit, every written row is read back **from the database** rather than trusted
from the in-memory objects, and the run requires: the exact identity, insert, and update
counts, each applied exactly once and summing to the approved total; every created identity
holding a real local primary key, the right `mlb_id`, `active` null, and no team or roster
field set; every inserted row matching its `proposed_values` field for field, with every
deliberately-omitted optional field stored as `NULL`; every stable GameLog key occupied
exactly once; no external MLB id stored as a local foreign key; every updated field matching
its proposed value and every untouched field unchanged; every corrected row carrying the
governed correction source; the reviewed amendment line verified; no delete of any kind; no
existing `Pitcher` row mutated and no current-team or roster field changed; and ledger counts
equal to the counts actually applied.

The delete and pitcher-mutation guarantees are proven from observed session state via a
`before_flush` listener, not asserted by reading the code.

## 17k-i. Why the production entrypoint accepts no governed argument

An earlier version of `apply_reviewed_repair` accepted `contract`, `approved_fingerprint`,
and `run_post_commit`. None of them was named force or override, and all three were exactly
that.

A caller could pass a freshly generated fingerprint together with a contract whose action
counts, defect population, identity partition, amendment record, and migration expectation
all matched it. Every precondition would then compare the regenerated plan against values
nobody had reviewed, and all of them would pass. `run_post_commit=False` was worse in a
quieter way: the transaction committed and the function returned `result: pass` with
`decision_reasons: ['approved_manifest_applied_and_verified']` without any of the three
governed post-commit checks having run. The word "verified" was doing work the code had
not done.

The production signature is now wiring only:

```python
apply_reviewed_repair(*, generated_at=None, apply_git_sha=None, client=mlb_client,
                      session=None) -> dict
```

Every governed value is loaded inside the function from `APPROVED_EXECUTION_CONTRACT` and
`APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026`. The two are cross-checked
against each other before anything else happens — a contract restating a different fingerprint
means one half of the approval was edited alone, and that aborts as
`approved_contract_fingerprint_disagrees_with_constant`.

`_evaluate_preconditions` was renamed private for the same reason. It writes nothing, but a
publicly callable evaluator that accepts an alternate contract is a second, quieter approval
surface, and there is no reason for one to exist.

Tests reach the constants by monkeypatching the module, which no production call site can do.
That is the honest place for the seam: an approval a caller can supply is not an approval.

## 17k-ii. Why post-commit verification cannot be skipped

The three governed checks now always run after a successful commit, and PASS requires four
named reconciliations, reported individually so an artifact distinguishes "did not run" from
"ran but skipped a check" from "ran everything and one failed":

- `post_commit_verification_was_executed`
- `every_governed_post_commit_check_is_present`
- `every_governed_post_commit_check_passed`
- `no_post_commit_check_was_skipped`

A verification function that raises is not a pass either: the exception is caught, recorded as
`error_type`, and the reconciliations fail closed. A committed repair whose post-commit checks
fail stays FAIL with every downstream gate blocked, exactly as before — there is still no
automatic rollback after commit and no retry.

## 17k-iii. Why dependent-evidence invalidation is strict for the repair only

`sync._notify_workload_evidence_game_log_correction` catches every marker exception and logs a
warning. That is correct for daily ingestion: a sync must not stop ingesting official
corrections because an evidence table is momentarily unhappy, and it runs again tomorrow.

A one-time atomic repair has no tomorrow. If it commits 160 corrected rows while their
workload, appearance-context, or inherited-traffic evidence silently keeps a stale value,
nothing notices and nothing retries.

The helper therefore gained a `strict` keyword that DEFAULTS TO FALSE. Ordinary ingestion is
unchanged, down to its return shape — existing callers read exactly `marked_count` and
`evidence_ids`, and adding to a contract they already depend on is not free. The repair passes
`strict=True`, under which every required family must complete, the pending evidence writes are
flushed inside the repair's own transaction, and any failure raises
`WorkloadEvidenceInvalidationError` carrying the per-family evidence.

The three required families are `workload`, `appearance_context`, and `inherited_traffic`.
Strict mode distinguishes:

- **completed** — the marker ran and returned a well-formed result. `marked_count: 0` is a
  SUCCESS. A corrected line with no dependent evidence is ordinary, and equating "nothing to
  invalidate" with "invalidation failed" would fail the repair for a normal case.
- **failed** — `marker_raised`, `required_marker_absent`, `marker_result_malformed`, or
  `evidence_flush_failed`. Malformed means the result was not a mapping, was missing
  `marked_count` or `evidence_ids`, carried a non-integer or negative count, or carried a
  non-sequence id list. A marker that returns an unreadable result has not told us whether it
  did its job.

Before commit, for every corrected row, the repair requires exactly the three governed
families, every status `completed`, no failed family, the result's `game_log_id` equal to that
row, and the result's `sync_run_id` equal to the governed operation id — a family that
completed for a *different* row has not invalidated *this* row's evidence. Any failure aborts
as `dependent_evidence_invalidation_failed`, rolls back all 675 actions, and leaves no ledger
row, no created identity, no inserted GameLog, no updated field, and no correction metadata.

No replacement evidence is fabricated. The repair only requests invalidation.

## 17k-iii-b. Why strict invalidation had to become EXHAUSTIVE, not merely exception-strict

Making the markers raise instead of warn was necessary and not sufficient.

`mark_dependent_evidence_for_recompute` is a BOUNDED primitive. It queries citation rows with
`.limit(batch_size)` — default 100 — and only then deduplicates evidence-object ids. Two
consequences follow, and both were live defects:

1. A source row with more than `batch_size` citation rows leaves current dependent evidence
   behind after one call, and the call returns a perfectly well-formed success.
2. Because the limit is applied to CITATION rows and dedup happens afterwards, one batch can
   mark far FEWER than `batch_size` unique objects. A row whose evidence is cited five times
   each yields twenty unique objects per hundred-citation batch.

So a completed, well-formed, exception-free strict response proved only that one bounded batch
had run. A repair could commit 160 corrected GameLogs while their dependent evidence still
read `recompute_status = current`, and nothing downstream would ever notice.

Strict mode now loops. For every updated GameLog and every required family it reads the
authoritative residual population, runs the bounded marker, flushes, re-reads the residual,
and repeats until the residual is zero. The family is declared completed only when every
marker call returned a valid result, every flush succeeded, every batch strictly reduced the
residual, no returned id belonged to another source row or another family, no evidence object
was counted twice, every marked object carries the governed operation id, and the final
authoritative residual query — run twice and compared against itself — returns nothing.

Family membership needed an authority. The three GameLog markers previously called the shared
primitive with identical arguments, so "family" was three call sites over one dependency set
and a per-family claim could not be made at all. `rule_ids` is now an optional scope on the
primitive and on each marker, defaulting to `None` — the previous unscoped behaviour exactly —
and strict mode passes each family's own rule-id set, the same sets the per-family rebuild
paths already use. That is what makes "belongs to the requested family" a checkable claim
rather than a wish.

Ordinary ingestion is unchanged: one bounded call per family, warning and continuing on
failure, returning exactly `{'marked_count', 'evidence_ids'}`, no loop. That is right for a
process that runs again tomorrow, and turning it into a blocking exhaustive sweep would make
a daily sync's runtime a function of one row's citation count.

A zero-dependency family is a SUCCESS with `batch_count: 0`, `initial_current_dependency_count:
0`, `marked_unique_count: 0`, `remaining_current_dependency_count: 0`, `exhaustive: true`. No
work to do is not a failure to work.

Transaction binding is explicit. `session` is threaded from `apply_reviewed_repair` through the
strict contract into the primitive's reads, writes, residual queries, and flushes, and the
result reports the session it used so a pre-commit reconciliation can require it to be the
repair's own. The alternative — relying on the ambient scoped session — would be true today and
silently untrue the first time anything runs on a second session.

The governed operation id is deliberately NOT forwarded into the marker's `sync_run_id`.
`evidence_objects.sync_run_id` is a FOREIGN KEY into `sync_runs`, and the governed repair
operation id is not a sync run — no sync run performs this repair. Writing it there violates
the constraint on PostgreSQL and would have failed the production repair on its first marked
row. SQLite does not enforce foreign keys, so this only surfaced once strict mode actually
started marking rows, on the PostgreSQL job. The governed id stays where it belongs: on the
corrected GameLog's `last_stat_correction_sync_run_id`, which is a plain integer with no
foreign key, plus the strict result and the execution ledger. A strict check now fails closed
if the id is ever found in that foreign-key column.

Safety limit: `STRICT_INVALIDATION_MAX_BATCHES` (1000) bounds the loop deterministically.
Zero-progress detection already catches a stuck marker; the limit catches one that makes a
single row of progress forever.

Any of these failures raises `WorkloadEvidenceInvalidationError`, which the apply path
translates to `dependent_evidence_invalidation_failed` — FAIL, full rollback of all 675
actions, no ledger row, no created identity, no inserted row, no updated field, no correction
metadata, and no surviving evidence mutation.

## 17k-iv. Why the correction count is verified as an exact delta

The runtime reconciliation checked `stat_correction_count >= 1`. That is satisfied by a row
that was already corrected once and never touched by this repair, and equally by a row this
repair incremented twice. It proved neither that the increment happened nor that it happened
once.

Each update now captures `prior_stat_correction_count` before the mutation and records
`resulting_stat_correction_count` and `correction_count_delta` alongside it. Two
reconciliations replace the floor: the recorded delta must be exactly 1 for every row, and the
value read back FROM THE DATABASE before commit must equal `prior + 1`. A simulated double
increment fails in-transaction verification and rolls the whole repair back.

## 17l. Post-commit verification, and why there is no automatic rollback or retry

After a successful commit the same operation runs three read-only checks: the completeness
diagnostic (pass, zero missing, zero defective matched, zero extra, zero duplicate, zero
appearance-team mismatches), the canonical season bullpen aggregation in `local_only` mode
(pass, 30 complete teams, zero partial, zero unavailable, all reconciliations true), and the
same audit in `official_validation` mode (pass, zero mandatory metric mismatches, all 30
teams matched).

If any fails the workflow reports failure and preserves the complete execution and
verification artifact.

There is **no automatic rollback after commit.** The commit is the point at which 675 reviewed
actions became the ledger's truth. An automatic undo would be an unreviewed 675-action reverse
mutation triggered by a diagnostic that has just told us something is not understood — the
worst possible moment to write more. Diagnosis comes first, separately reviewed.

There is **no automatic retry.** A retry is only ever correct when the failure is known to be
transient, and none of these failures are: an unavailable lock means another repair is
running, a fingerprint mismatch means the plan is not the reviewed plan, and a failed
post-commit check means the ledger is not in the expected state. Retrying any of them would
turn a clear refusal into a loop.

## 17m. Result semantics

`pass` requires all of: the exact approved fingerprint regenerated, every precondition
passed, the transaction committed, all 675 actions applied exactly once, all in-transaction
verification passed, and all post-commit diagnostics and aggregation validations passed.

`inconclusive` means **nothing was written**: a mutable precondition changed, the approved
fingerprint was not regenerated, the advisory lock was unavailable, or the repair was already
completed.

`fail` means a contradictory identity or row was found, a partial mutation was attempted, a
rollback occurred after writes began, an in-transaction verification failed, a post-commit
verification failed, or an unsupported mutation was requested.

A failed or inconclusive result never opens a downstream gate.

## 17n. Why Foundation 3B stays blocked, and why a dispatch is still required

Foundation 3B, the public reader, Team State performance, Share Card performance, and SC-05
all remain `blocked` after a successful apply, and the workflow fails if the artifact ever
reports otherwise. A green repair is a *precondition* for opening those gates, never the act
of opening one — the repair proves the pitching-line ledger matches official evidence, which
is a different claim from "the downstream surfaces built on that ledger are correct and
performant". Those need their own reviewed validation.

Implementing the apply path is likewise not executing it. The workflow is dispatch-only, has
no schedule, no push or pull-request trigger, and no automatic dispatch; the confirmation
phrase `APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06` is required, and validating it is the
literal first step of the job — ahead of `actions/checkout`, so a wrong phrase terminates the
job before the repository is fetched, before Python is set up, before dependencies are
installed, and therefore before the application can bootstrap or open a database connection.
The confirmation step needs no repository file, so there is nothing to gain from checking out
first. The apply command repeats the check ahead of its own imports, and a positional test
walks `jobs.apply.steps` and asserts the index ordering rather than comparing character
offsets in the file — an offset comparison is satisfied by any step order at all, as long as
the strings happen to appear in the right sequence in the text.

It has not been dispatched, no apply execution has occurred, and production data is
unchanged.

## 15. Operation

- Planner service: `backend/services/official_pitching_line_repair_plan_2026.py`
- Planner CLI: `backend/scripts/run_official_pitching_line_repair_plan_2026.py`
- Planner workflow: `.github/workflows/official_pitching_line_repair_plan.yml`
  (dispatch-only)
- Planner tests: `backend/tests/test_official_pitching_line_repair_plan_2026.py`
- Apply service: `backend/services/official_pitching_line_repair_apply_2026.py`
- Apply CLI: `backend/scripts/run_official_pitching_line_repair_apply_2026.py`
- Apply workflow: `.github/workflows/official_pitching_line_repair_apply.yml`
  (dispatch-only, one confirmation input, not dispatched)
- Execution ledger: `backend/models/official_pitching_line_repair_execution.py`,
  migration `c7b3e5a91d48`
- Apply tests: `backend/tests/test_official_pitching_line_repair_apply_2026.py`,
  `backend/tests/test_official_pitching_line_repair_execution_ledger.py`

Production plan: dispatch with `season=2026`, `as_of_date=2026-07-25`, `preview_limit=100`,
`team_id` and `game_pk` blank. The full manifest ships in the private artifact and is never
truncated; the step summary carries the bounded preview only.

## 16. Boundary held

The planner is read-only. The apply path writes only under the exact approved fingerprint,
performs no delete, no duplicate consolidation, no phantom-row deletion, no current-team or
roster update, no appearance-team rewrite on an existing row, and no public-surface
publication. Foundation 3B, the public reader, Team State performance, Share Card
performance, and SC-05 all remain blocked.
