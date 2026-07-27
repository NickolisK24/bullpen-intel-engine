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
