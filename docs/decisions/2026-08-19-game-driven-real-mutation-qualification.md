# D-056 — Manual exact-one-game real-mutation qualification mechanism

- **Date:** 2026-08-19
- **Status:** Approved founder decision. **Mechanism authority only.** No production qualification run has occurred and none is authorized by this decision.
- **Scope:** One new manual qualification path and one new read-only candidate audit for the game-driven ingestion lane. No change to baseball semantics, to the canonical lane, planner, comparator, realization or identity services, to publication authority, to D-051, D-052, D-053, D-054 or D-055, or to any schema.

## Context

D-052 closed Phase 1A by proving the game-driven lane can enter its governed
write-capable path for exactly one completed game while mutating **zero** baseball
data. Every governed assertion in that contract is an assertion of *absence*: every
counter zero, every digest identical, every field unchanged.

O-008 — "Game-driven automated write and later publication-authority transfer" —
remains open. Its gate names five things: **real-mutation proof**, scheduled write
stability, rollback, observability, and explicit founder approval. Real-mutation
proof is one of the five, and nothing in the repository could produce it.

What existed was an operator CLI procedure — an exclusive shadow, a human-reviewed
plan fingerprint, then `--mode write --only-game-pk … --expected-plan-fingerprint`.
The lane primitives underneath it are sound: exact one-game scope that bypasses the
correction horizon, a mandatory reviewed fingerprint, a recompute-and-compare that
refuses before the first mutation, the production writer guard, the realization
proof, and a work-item ledger that already distinguishes a correction from a no-op.
An August 2026 read-only audit traced each one and found no defect.

What the CLI lacked was every governance property the no-op stage established:
owner/ref/event/SHA authorization, a typed confirmation, an evidence artifact, a
forbidden-content scan gate, an exact expected-mutation contract, hard post-write
failure semantics, a replay guard, and a durable decision record. A CLI path
existing is not an approved qualification stage.

The historical case that made this necessary is game `824969`, pitcher `656240`,
field `inherited_runners` — the one real correction candidate shadow has surfaced.
It is deliberately **not** the production candidate for this mechanism, and this
decision encodes the reason rather than working around it.

## Decision

### 1. A manual exact-one-game real-mutation qualification mechanism may exist

`workflow_dispatch` only, `main` only, repository-owner only, expected-HEAD-SHA
bound, reviewed-fingerprint bound, exactly one game, and limited to **one
statistical correction to one existing GameLog row on one field whose source
authority the repository has resolved**.

Two phases, following the D-041 shape:

```text
shadow   exclusive to the requested game, read-only, produces the plan and its
         fingerprint, and validates the plan is exactly one safe correction
write    exclusive to the same game, authorized by that reviewed fingerprint;
         the canonical lane re-fetches, re-plans, and refuses before its first
         mutation if the source revision or the plan moved
```

### 2. The expected mutation is exact, and it was measured

For a reviewed single-field statistical correction the canonical lane produces:

```text
game_log_rows_written              1
pitcher_rows_written               0
appearance_team_rows_written       0
correction_provenance_rows_written 1
dead_letters_created               0
work_items_created                 0
work_items_updated                 1
work_items_completed               1
checkpoints_advanced               1
commits_performed                  1
correction_count delta            +1
```

Exact integers, never `>= 1`: the reviewed plan named one row and one field, so any
other count is a different mutation than the one a human authorized.

`correction_provenance_rows_written = 1` was **measured, not assumed**. The lane
records that counter as `provenance_only_updates + statistical_corrections`, so a
genuine correction necessarily stamps provenance on the row it corrects. The
implementation initially pinned it to zero by analogy with D-052 and the canonical
path refused that contract on first execution. The same measurement showed the
canonical planner appends `provenance_only_update` to the mutation categories of
every real correction. Both are recorded here because both are the kind of
assumption that reads as safe and is wrong.

The plan-level `provenance_only_updates` counter must still be zero, and a row the
planner marks `is_provenance_only` is refused: it corrects no baseball value.

### 3. The lane bookkeeping contract is its own, not D-052's

A real correction legitimately moves work-item fields a no-op run does not.
`correction_count` is in D-052's *required-unchanged* set and in this contract's
*required-to-advance* set. Reusing D-052's bookkeeping assumptions would fail every
correct run.

### 4. Unresolved source authority is a hard refusal

A correction may only be applied to a field whose source authority the repository
has actually resolved. `inherited_runners` and `inherited_runners_scored` are
refused, because `docs/current/GAME_DRIVEN_DAILY_INGESTION.md` carries a live
section titled "GameLog `inherited_runners` — field authority UNRESOLVED", status
*unresolved, failed closed*, and the deciding diagnostic
(`scripts/inspect_gamelog_field_authority.py`) has never been run against
production.

This mechanism encodes that refusal. It does not resolve the question and must not
be used to. Nothing is added to `APPROVED_FALLBACK_FIELDS` by this decision. A
field may leave the refused set only by a later decision that records how its
authority was resolved.

Game `824969` is retained as the **negative** example, in the runbook and in two
regression tests.

### 5. Four terminal results, and a replay is never a PASS

```text
PASS                exit 0   exactly the reviewed mutation happened, nothing else
FAILED              exit 1   a definite contract violation was observed
UNPROVEN            exit 2   trustworthy evidence could not be completed
NO_LONGER_MUTATING  exit 3   the candidate became already-correct before execution
```

Precedence is FAILED, then UNPROVEN, then NO_LONGER_MUTATING, then PASS. UNPROVEN
outranks NO_LONGER_MUTATING because "already applied" is itself a positive claim
about production state that untrustworthy evidence cannot support.

A re-run against an already-corrected row resolves `NO_LONGER_MUTATING`, and the
workflow's final gate refuses to report success on exit 3. One correction can
never be counted twice.

### 6. Post-write failure: fail hard, preserve evidence, no compensating write

If the mutation commits and realization verification fails, the verdict is FAILED,
the artifact is still scanned and uploaded, and **no automatic rollback or
compensating mutation is attempted**. Any correction from there uses the canonical
governed correction path. Rollback is separately named in O-008's gate; inventing
it here would pre-decide part of an open decision.

### 7. Candidate selection belongs to a bounded read-only audit

D-042 established that operator intuition cannot pick a qualification candidate.
That applies with more force here: a no-op candidate is a settled game, while a
real-mutation candidate is a game the lane intends to *change*.

The audit reuses the no-op candidate audit's proven read-only machinery — the
acquire-only public sync lock, the read-only transaction with a refused write
probe, and the before/after table fingerprints. Finding zero eligible candidates
is a COMPLETED audit, not a failure; given a clean shadow corpus, zero is the
expected first answer.

The audit reports the stored value of the reviewed field and the plan's target
digest. It deliberately does **not** re-derive the value the plan would write:
the lane's safe row report keeps intended values in-process and exports only their
digest, and re-deriving them would mean a second comparator. A human sees the
change itself in the qualification's own reviewed shadow plan.

### 8. What this decision does not authorize

Its existence authorizes **no production qualification run**. It grants no
automated write authority, no scheduled write authority, no postgame or daily
game-driven write authority, no publication authority, no backfill authority, no
multiple-game scope, no identity-mutation authority, and no legacy-writer
retirement. Daily and postgame lanes remain `shadow`; backfill remains `off`; the
legacy writer remains authoritative for baseball-data mutation.

**O-008 remains open.** A successful production PASS would be its own separate
evidence-backed decision, and would still grant none of the above.

## Consequences

A real-mutation candidate is a *found* object with a short life: it exists only
while shadow has caught a divergence the legacy writer has not yet resolved. The
mechanism therefore has to exist and be dormant before a candidate appears, because
there is no way to hold one open. That is why it is built ahead of need.

The immediate expected state is **zero eligible candidates**. That is the correct
reading of a clean shadow corpus, not a defect in the audit.

## Evidence

Repository implementation only. No production execution occurred.

| Item | Value |
| --- | --- |
| Qualification service | `backend/services/real_mutation_qualification.py` |
| Qualification runner | `backend/scripts/run_game_driven_real_mutation_qualification.py` |
| Candidate audit service | `backend/services/real_mutation_candidate_audit.py` |
| Candidate audit runner | `backend/scripts/run_real_mutation_candidate_audit.py` |
| Qualification workflow | `.github/workflows/manual-game-driven-real-mutation-qualification.yml` |
| Candidate audit workflow | `.github/workflows/manual-real-mutation-candidate-audit.yml` |
| Qualification type | `manual_game_driven_real_mutation_qualification_v1` |
| Confirmation string | `QUALIFY_REAL_MUTATION_GAME_<game_pk>` |
| Audit confirmation string | `AUDIT_REAL_MUTATION_CANDIDATES` |
| Evidence artifact | `game-driven-real-mutation-qualification-<run_id>`, 30-day retention, scanned before upload |

Canonical primitives reused and **unchanged**: `game_driven_ingestion`,
`game_log_reconciliation`, `game_ingestion_planner`, `game_driven_realization`,
`pitcher_identity_reconciliation`, `sync_metadata`, `gamelog_source_authority`.
