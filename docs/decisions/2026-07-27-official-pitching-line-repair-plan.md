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
