# Decision: committed pitching-line repair closeout contract (2026)

- **Date:** 2026-07-29
- **Status:** Implemented. The approved 675-action repair is **committed** and is not repeated,
  reversed, or modified by anything in this change. No production data is written. The
  historical apply artifact is immutable and is not rewritten. Every downstream gate stays
  blocked. The closeout workflow has **not** been dispatched.
- **Scope:** Correct a post-commit false negative caused by mode-blind reconciliation
  evaluation, correct skipped-check semantics, and add a read-only closeout verifier that
  proves the committed repair independently.

## 1. What actually happened

The production apply committed successfully: `transaction_committed=true`,
`database_writes_performed=true`, `rollback_performed=false`, `execution_ledger_id=1`,
regenerated fingerprint equal to the approved fingerprint, 70 identities + 445 insertions +
160 updates = 675 actions applied, 160 rows stamped with correction metadata, 1,606 dependent
evidence objects marked across 160 rows, `update_readback_mismatches: []`, and all 38
in-transaction verification checks true. The reviewed Brandyn Garcia line committed as
reviewed: GameLog 43765 (`825058:805299:109`), `hits_allowed` 1 → 0,
`stat_correction_count` 0 → 1, source `official_pitching_line_repair`.

Every post-commit check also passed on its own terms:

- completeness — `pass`, exit 0, zero missing / stat / role / extra / duplicate /
  appearance-team defects;
- canonical aggregation **official validation** — `pass`, exit 0, 30 teams complete, 30
  matched, 0 partial, 0 unavailable, 0 mandatory metric mismatches, no failed
  reconciliations;
- canonical aggregation **local-only** — `pass`, exit 0, 30 complete, 0 partial, 0
  unavailable, 0 mandatory metric mismatches.

The wrapper nevertheless reported the run failed.

## 2. The exact defect

`season_bullpen_aggregation_2026` defines one reconciliation map for both audit modes, and
within it:

```python
'all_mandatory_metrics_match': (
    include_official_validation and result == RESULT_PASS
    and validation['teams_mismatched'] == 0),
```

In local-only mode `include_official_validation` is false, so this is **false by design**. It
is an official-validation reconciliation that local-only cannot evaluate — not a local
reconciliation that failed.

`run_post_commit_verification` extracted every boolean reconciliation and required them all to
be true, applying that identical rule to both modes. It therefore converted an intentionally
non-applicable value into a failure. The artifact then read:

- `post_commit_verification_was_executed: true`
- `every_governed_post_commit_check_is_present: true`
- `every_governed_post_commit_check_passed: false`
- `no_post_commit_check_was_skipped: false`

Nothing was skipped. One completed check was judged with the wrong mode's vocabulary.

## 3. Mode-specific reconciliation vocabularies

The vocabularies are now pinned **exactly**, per mode — not by name pattern, and not by a rule
that ignores false values:

- **Local-only requires** `canonical_outs_match`, `team_totals_reconcile`,
  `league_totals_reconcile`, `bullpen_outs_reconcile`; plus `result == pass`,
  `exit_code == 0`, 30 complete / 0 partial / 0 unavailable teams. It does **not** require
  `all_mandatory_metrics_match`, and reports it as `applicable: false`,
  `status: not_applicable_to_local_only`, `observed_value: false`. The stored aggregation
  value is never rewritten from false to true to satisfy the wrapper.
- **Official validation requires** all four structural reconciliations **and**
  `all_mandatory_metrics_match`; plus `result == pass`, `exit_code == 0`, 30 complete / 0
  partial / 0 unavailable, 30 matched, 0 mismatched, 0 mandatory metric mismatches, 0
  unavailable evidence, 0 official games missing a unique starter, and 0 with multiple
  starters.

It fails closed when a required reconciliation is missing or false, when an **unexpected**
false boolean appears that is neither required nor explicitly classified as governed
non-applicable, when the result is not pass, when the exit code is nonzero, when team counts
disagree, when official evidence is incomplete, or when the ledger does not prove the repair.

## 4. Corrected skipped-check semantics

`no_post_commit_check_was_skipped` measured outcome; it now measures **execution and
presence**. Four facts are kept separate and reported separately: **executed**, **present**,
**passed**, **skipped**. Each check records `executed` and `execution_state` alongside its
verdict, and a check that raises is recorded as not executed rather than aborting the others.
A check that ran and failed is a failure — never a skip.

## 5. Read-only closeout verifier

`official_pitching_line_repair_closeout_2026` proves the committed repair after the fact and
writes nothing. It queries the execution ledger read-only for the approved fingerprint and
requires exactly one completed row with matching fingerprints, season 2026, as-of 2026-07-25,
baseline v2, the reviewed amendment id, counts 70/445/160/675, and a populated `committed_at`
(the ledger id is a surrogate key: the expected value 1 is recorded and the observed id is
reported authoritatively). It reads GameLog 43765 and requires game 825058, person 805299,
appearance team 109, `hits_allowed == 0`, `stat_correction_count == 1`, the governed correction
source, a populated timestamp, and a populated governed operation id. It then runs the
completeness diagnostic and both aggregation modes, judging each with its own applicable
contract.

It PASSES only when the ledger and the amendment row are proven, all three post-commit checks
pass, every check is present and executed, and `database_writes_performed == false` — decision
`foundation_3a_repair_closeout_ready_for_review`. It is INCONCLUSIVE when a required read-only
source cannot be observed, and FAILS when the committed record or a repaired row contradicts
the approved result.

## 6. Why the historical artifact stays immutable

The apply artifact accurately records the decision that run made with the vocabulary it had. It
is evidence of what happened, not a claim to be corrected later. Rewriting it would destroy the
record of the false negative and the reason this contract changed. The closeout publishes a
**separate** artifact with its own capability and mode.

## 7. Why the apply must never be rerun

The repair committed. The ledger holds exactly one completed execution for the approved
fingerprint, protected by a unique constraint, and the apply path refuses a second execution
with `repair_already_completed_for_this_approved_fingerprint`. Re-running it is therefore both
forbidden and unnecessary: the closeout proves the outcome from the durable record and live
evidence without touching a row.

## 8. Downstream gates

`foundation_3b_gate`, `public_reader_gate`, `team_state_performance_gate`,
`share_card_performance_gate`, and `sc_05_gate` remain **blocked** on every closeout outcome. A
passing closeout makes Foundation 3A *eligible* for a separately reviewed gate decision; it
never opens a gate or activates a public surface.

## 9. Closeout workflow

`Official Pitching-Line Repair Closeout Verification (2026)` is `workflow_dispatch` only, with
its own concurrency group and `cancel-in-progress: false`. Its confirmation phrase
`VERIFY-2026-PITCHING-LINE-REPAIR-CLOSEOUT` is deliberately **distinct** from the apply phrase,
so a read-only closeout can never be confirmed with the phrase that authorises a write.
Confirmation is validated in the first step, ahead of checkout; secrets are checked for presence
and never printed. It invokes the closeout command exactly once — no retry, no re-dispatch — and
never invokes the apply entrypoint, the apply CLI, any mutation service, or Alembic. It uploads
one complete private JSON artifact with 30-day retention and prints a bounded summary. The
approved apply fingerprint and confirmation phrase are unchanged.
