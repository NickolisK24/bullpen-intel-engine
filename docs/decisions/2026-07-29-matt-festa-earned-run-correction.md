# Decision: one reviewed Matt Festa earned run, applied once, by a dedicated capability

- **Date:** 2026-07-29
- **Status:** Implemented. **Not dispatched.** No production data has been changed by this
  work. The approved 675-action repair, its fingerprint, its confirmation phrase, its
  entrypoint, its execution-ledger row, and the migration revision are untouched, and the
  original apply is never rerun. Every downstream gate stays blocked.
- **Scope:** A separate, one-time, immutable apply capability whose only possible effect on
  baseball data is `GameLog 44140.earned_runs 0 -> 1`.

## 1. What the closeout found

The approved 675-action official pitching-line repair committed and is permanently closed. The
later read-only closeout and the full-season completeness diagnostic (season 2026, as of
2026-07-25) then reported exactly one remaining discrepancy in 13,301 official pitching lines:

```
822952:670036:114   earned_runs_mismatch   local 0   official 1
```

That is Matt Festa's relief appearance for Cleveland on 2026-07-24, local `GameLog 44140`,
local pitcher row 169, official person 670036. Every other governed stat on the line already
agrees — five outs, one run, two hits, no walks, two strikeouts, no home runs — and the other
13,300 lines are exact.

## 2. What was corrected before approval

The first targeted plan for this line contained **two** actions. The second was false:

```
innings_pitched: 1.66666666666667 -> 1.6666666666666667
```

The governed workload authority agreed on both sides at `innings_pitched_outs = 5`; the
difference was PostgreSQL's 15-significant-digit float8 rendering compared against Python's
derived binary float. `innings_pitched` is a derived companion of the integer outs, never an
independent authority, and the planner no longer compares it when its controlling authority
matches. That correction is recorded in
`docs/decisions/2026-07-29-planner-derived-innings-semantics.md`.

The fingerprint of the pre-fix two-field manifest,
`257ff3a64261d69908248de81e6c67a83d1e0357241cacab897fe610f91cb838`, is named in the service as
explicitly **not approved**: it reviewed a mutation this capability may not make.

## 3. The approved contract

Approved targeted manifest fingerprint:

```
903766c4d71652d102410d924d1adf2479f21b07a6742e2ce407385a06ac8f2b
```

Capability `official_pitching_line_matt_festa_apply_2026_v1`. Every governed value is stated as
a literal in `IMMUTABLE_CONTRACT` in
`backend/services/official_pitching_line_matt_festa_apply_2026.py` rather than derived, and the
entrypoint accepts **no** governed input — no season, date, scope, team, game, field, value,
fingerprint, count, force, or override parameter exists. A dispatch can choose only whether it
runs, never what it does.

- planning authority: `official_pitching_line_repair_plan_2026_v1`, season 2026, as of
  2026-07-25, team 114, game 822952, migration head `c7b3e5a91d48`
- expected plan: `diagnostic_subset` / `diagnostic_subset_not_apply_eligible` /
  `inconclusive`, decision reason `accepted_baseline_drift`
- action `gamelog:update:44140:822952:670036`, stable key `822952:670036:114`
- `changed_fields: ['earned_runs']`, `{0} -> {1}`, reason `earned_runs_mismatch`,
  `safe_to_apply: true`, no blocking reasons, no dependencies, no null-guarded fields
- counts: 0 identities, 0 insertions, 1 update, 1 total
- comparison fingerprint `cd77ae197a37d37a7622e9708c2b227e64c44e3ec26384d6940083e1c4adf40b`,
  source fingerprint `1daec972ba85b257beaac0b401631b62e4c1f669eb4568ea60d805926a890571`

## 4. Why the generic planner is still not apply-eligible

A team- or game-scoped plan observes a fraction of the season, so it cannot reconcile against
the accepted full-season defect baseline. It therefore reports `diagnostic_subset` and
`diagnostic_subset_not_apply_eligible`, with the repair-apply gate
`blocked_subset_not_apply_eligible`, and that is unchanged here. Making subset plans generally
apply-eligible would let any narrow slice authorize a write.

This capability is the reviewed exception, not a loosening of that rule. It does not accept a
scope; it *asserts* one. It regenerates that exact scope itself, requires the manifest
fingerprint to be byte-for-byte the approved one, and additionally requires every field of the
single action to equal the reviewed contract. It is bound to a fingerprint the generic apply
service cannot execute, and the generic apply service's own approved fingerprint and
675-action contract are untouched.

## 5. Separation from the closed repair

The original approved fingerprint is unchanged:

```
3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b
```

| | 675-action repair | this correction |
|---|---|---|
| capability | `official_pitching_line_repair_apply_2026_v1` | `official_pitching_line_matt_festa_apply_2026_v1` |
| approved fingerprint | `3ee2ea06…` | `903766c4…` |
| confirmation phrase | `APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06` | `APPLY-2026-MATT-FESTA-ER-903766C4` |
| advisory lock | `official_pitching_line_repair_2026.…` | `official_pitching_line_matt_festa_2026.transaction_advisory_lock` |
| entrypoint | `backend/scripts/run_official_pitching_line_repair_apply_2026.py` | `backend/scripts/run_official_pitching_line_matt_festa_apply_2026.py` |
| workflow | Official Pitching-Line Repair Apply (2026) | Official Pitching-Line Matt Festa Apply (2026) |

Neither confirmation phrase appears in the other's command or workflow, so neither can be
started from the other's dispatch form. The advisory-lock contracts differ, so the keys differ
and neither capability can be mistaken for the other's serialization guarantee.

## 5a. Three commits are three different facts

The execution ledger's `planner_git_sha` means *the commit where the approved plan was
generated*; `apply_git_sha` means *the commit that executed the apply*. Those are different
commits, and a third — the commit the planner happens to be running from at apply time — is
different again.

The apply capability necessarily lives at a **later** commit than the plan it applies: the
moment this branch merges, the deployed tree can never again be `c4a0b3e4…`. So the runtime
SHA is **recorded, not required**. Requiring equality would make the capability
permanently unrunnable.

| fact | value | where it goes |
|---|---|---|
| approved plan-generation commit | `c4a0b3e4e33d64c5cecea3151ff3c30df7e0c5fa` | ledger `planner_git_sha`, artifact `approved_planner_git_sha` |
| runtime planner commit | whatever the deployed tree is | artifact `regenerated_planner_git_sha`, ledger `execution_summary.regenerated_planner_git_sha` |
| apply commit | the workflow's `GITHUB_SHA` | ledger `apply_git_sha`, artifact `apply_git_sha` |

What *is* required is that the planner **implementation** is unchanged. The contract pins the
SHA-256 of the exact bytes of `backend/services/official_pitching_line_repair_plan_2026.py`
as they existed at `c4a0b3e4…`:

```
65fef8d3d104faf4186005e7602ac871c5eb61f11647690ef230629cfe92668d
```

Immediately before regeneration — and therefore before a changed planner can even produce a
manifest to compare — the loaded planner module's own file is hashed and compared at full
length against that constant. Never a prefix. No Git command is involved: a shallow checkout,
a detached HEAD, or an absent repository directory must not be able to turn the proof into a
silent pass. Both hashes and the boolean go into the artifact and the ledger summary; a
mismatch refuses before any write.

The generic planner is untouched by this: it holds no approved fingerprint, no confirmation
phrase, and no capability name, and it does not know it is being verified.

## 6. Gates before the first write

0. **Runtime planner source.** The loaded planner must be byte-identical to the reviewed
   planner, as described above. Checked before regeneration.
1. **Regenerated plan.** The planner is rerun read-only at the pinned scope, and the whole
   reviewed envelope must hold — not a subset of it:

   - capability `official_pitching_line_repair_plan_2026_v1`, mode `read_only`,
     result `inconclusive`, exit code `2`
   - inputs exactly season 2026, as of 2026-07-25, game type `R`, team 114, game 822952
   - scope `diagnostic_subset`, status `diagnostic_subset_not_apply_eligible`,
     generic gate `blocked_subset_not_apply_eligible`
   - `decision_reasons` **exactly** `['accepted_baseline_drift']` — equality, not
     membership, so a plan that decided the reviewed thing *and something else* refuses
   - `blocking_counts_by_reason` empty, `duplicate_action_ids` empty,
     `database_writes_performed` false, migration head exactly `[c7b3e5a91d48]`
   - the regenerated fingerprint equal to the approved constant, one update action, zero
     identities, zero insertions, every planner reconciliation true, and every reviewed
     field of the single action — including both the comparison and source fingerprints.
2. **Current population.** The full-season completeness diagnostic must still report the
   reviewed single-defect population: 1,570 games selected and fetched, 13,301 official and
   13,301 local lines, 13,300 exact matches, one stat mismatch, and zero of everything else.
   The one defect must be `822952:670036:114`, its only reason `earned_runs_mismatch`, local
   earned runs 0 against official 1, with every other official stat already agreeing.
3. **Original repair.** Exactly one completed ledger row for `3ee2ea06…`, counts
   70 / 445 / 160 / 675, season 2026, as of 2026-07-25; and `GameLog 43765` still holding the
   reviewed Brandyn Garcia state — `hits_allowed 0`, one stat correction, correction source
   `official_pitching_line_repair`. Read-only. Neither record is modified.
4. **Target row**, under the dedicated advisory lock: `GameLog 44140`, game 822952, local
   pitcher 169, `Pitcher.mlb_id` 670036, appearance team 114, and the exact reviewed stored
   line including `earned_runs 0`.

Any mismatch aborts before the first write and reports the failing check names.

## 7. The transaction

One atomic transaction: dedicated `pg_try_advisory_xact_lock`; ledger check for the approved
fingerprint; `SELECT … FOR UPDATE` reread of the row and its pitcher; the single
`earned_runs 0 -> 1`; governed correction metadata; strict dependent-evidence invalidation
through the same shared path the 675-action repair used; a direct column `SELECT` that bypasses
the ORM identity map; verification of every mutation and every non-mutation; the new ledger
row; one commit.

Correction metadata: `stat_correction_count` increases by exactly one from whatever it was —
no starting value is invented — `last_stat_correction_at` becomes the apply timestamp,
`last_stat_correction_source` becomes `official_pitching_line_repair`, and
`last_stat_correction_sync_run_id` becomes a deterministic operation id derived from THIS
approved fingerprint, so the corrected row points back at exactly one approved manifest.

Verification is type-exact (`type(l) is type(r) and l == r`), so a stored `1.0` or `"1"` is a
disagreement rather than a pass. Every other stored column is compared against its own
pre-mutation snapshot. A `_TargetedMutationWatch` observes the flush and proves, from session
state rather than from reading the code, that exactly one existing `GameLog` changed, that its
changed baseball-stat fields were exactly `['earned_runs']`, that nothing beyond the governed
correction metadata was added, that no other game log moved, that exactly one ledger row was
created, that nothing was deleted, and that no existing `Pitcher` row was mutated. No float
column is written at all.

Any pre-commit failure rolls back everything: no stat change, no metadata change, no evidence
invalidation, no ledger row.

## 8. The ledger, reused

No migration is added, and none is added for the provenance evidence either: the runtime
planner SHA and the two source hashes live in the existing `execution_summary` JSON column,
not in new columns.

The existing `OfficialPitchingLineRepairExecution` table records the new
execution with a distinct capability, the new approved and regenerated fingerprints, the
approved plan-generation `planner_git_sha` and the deployed `apply_git_sha` kept as separate
facts, season 2026, as of 2026-07-25, accepted baseline version `v2`, amendment id
`post_repair_matt_festa_earned_runs_2026`, counts 0 / 0 / 1 / 1, status `completed`, populated
`started_at` / `completed_at` / `committed_at`, and bounded precondition, execution, and
verification summaries. Its numeric id is not assumed: the committed value is read back from
the row and reported.

The unique constraint on `approved_manifest_fingerprint` makes a second completed execution for
`903766c4…` impossible at the database level, and a pre-existing row for that fingerprint
returns an already-completed, no-write result. Row 1 — the 675-action repair — is neither
altered nor deleted, and the existing read-only closeout still isolates and validates it by
fingerprint despite the second row.

## 9. After the commit

Post-commit verification is read-only and always runs: the completeness diagnostic must report
`pass` with every line now exact and zero mismatches; canonical local-only aggregation must
report 30 complete teams and every locally applicable reconciliation true; canonical official
validation must report 30 teams matched with zero mandatory-metric mismatches, zero unavailable
official evidence, and zero starter contradictions; and the original repair record and the
Brandyn Garcia row must still pass their exact checks.

A post-commit failure cannot undo a committed transaction and does not try to. It produces a
failed artifact, reports the failing checks, and keeps every gate blocked. A check that could
not run is reported as not executed — which is not the same fact as passing, and is not treated
as one.

## 10. Historical causation stays unproven

Nothing here establishes why the local row ever held zero earned runs. Current official
evidence is the repair authority; no claim is made that the official source changed, that the
local ledger was previously written differently, or that any particular ingestion run caused
it. The correction is what current official scoring says, applied once, with its provenance
recorded.

## 11. Gates

`foundation_3b_gate`, `public_reader_gate`, `team_state_performance_gate`,
`share_card_performance_gate`, and `sc_05_gate` are reported `blocked` in every outcome,
including a fully successful apply. A successful targeted apply does not close Foundation 3A.
The existing read-only closeout workflow is run later, under separate authorization.

## 12. Dispatch

The workflow `Official Pitching-Line Matt Festa Apply (2026)` is `workflow_dispatch` only, with
the confirmation phrase as its single input, validated as the literal first step ahead of
checkout. It has no schedule, push, or pull-request trigger, a dedicated concurrency group with
`cancel-in-progress: false`, no loop, no retry, and no automatic redispatch. It invokes the
apply exactly once and fails on any nonzero exit. It uploads one private complete JSON artifact
with 30-day retention; the job summary is bounded and prints no secret, URL, or connection
detail.

It has not been dispatched.
