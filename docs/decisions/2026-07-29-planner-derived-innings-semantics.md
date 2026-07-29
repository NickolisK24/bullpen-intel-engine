# Decision: planned innings are derived from canonical outs (2026)

- **Date:** 2026-07-29
- **Status:** Implemented in the READ-ONLY repair planner only. No production data is written.
  The original approved 675-action repair, its fingerprint, its execution-ledger row, its
  confirmation phrase, and the migration revision are untouched, and the original apply is
  never rerun. No fingerprint is approved. Every downstream gate stays blocked. No workflow has
  been dispatched.
- **Scope:** Stop the planner from independently proposing `innings_pitched` when the governed
  integer outs already match.

## 1. What the targeted plan found

The read-only planner, scoped to team 114 / game 822952, correctly identified the one real
discrepancy on the Matt Festa relief line (local GameLog 44140, official person 670036):

```
earned_runs: 0 -> 1
```

It also proposed a second, false mutation:

```
innings_pitched: 1.66666666666667 -> 1.6666666666666667
```

The governed workload authority already agreed on both sides: `innings_pitched_outs = 5`,
official `inningsPitched = "1.2"`, official `outs = 5`. The completeness diagnostic reported
exactly one governed mismatch — `earned_runs_mismatch` — and no innings-outs mismatch.

## 2. Root cause

`_update_action` compares the mandatory integer-outs authority first. When
`innings_pitched_outs` differs it correctly proposes both the corrected outs and the derived
`innings_pitched = outs / 3.0`, under the governed outs-mismatch reason.

The later workload-field loop then independently compared every correctable field with
`current_value == proposed_value`. `innings_pitched` is in that correctable set, so when outs
MATCHED — and the derived block had therefore proposed nothing — the loop compared PostgreSQL's
float8 text rendering against Python's derived binary float:

```
1.66666666666667      (PostgreSQL, extra_float_digits <= 0, 15 significant digits)
1.6666666666666667    (Python, 5 / 3.0)
```

and emitted an `official_workload_field_mismatch`. That is a representation difference, not a
baseball workload difference.

## 3. The governed rule

`innings_pitched` is **not** an independent official workload authority. The semantic authority
is the integer `innings_pitched_outs`; the float exists only as the model-compatible derived
companion, kept consistent so the stored-state CHECK constraint holds.

- When `innings_pitched_outs` differs: propose `innings_pitched_outs` from official outs,
  propose `innings_pitched` as official `outs / 3.0`, and give both the governed outs-mismatch
  reason. **Unchanged behavior.**
- When `innings_pitched_outs` matches: do not compare `innings_pitched`, do not add it to
  `changed_fields`, and do not emit a workload-field mismatch for it.

## 4. Implementation

A governed derived-field vocabulary in
`backend/services/official_pitching_line_repair_plan_2026.py`:

```python
DERIVED_FIELD_AUTHORITY = {'innings_pitched': 'innings_pitched_outs'}
DERIVED_FIELDS = frozenset(DERIVED_FIELD_AUTHORITY)
```

The workload-field loop skips `DERIVED_FIELDS`. Reaching that loop for a derived field means
its controlling authority matched, so any remaining difference is a rendering artifact.

The correction is **semantic, not numeric**. No approximate equality, no tolerance, and no
rounding of either value was introduced: the comparison that produced the false action is not
softened, it is removed, because it was never a meaningful comparison to make. Only
`innings_pitched` is excluded; every other workload field is still compared exactly as before.
The completeness diagnostic's integer-outs comparison is unchanged.

## 5. Corrected targeted plan

For stable key `822952:670036:114` the plan now contains exactly one update action:

- `changed_fields`: `['earned_runs']`
- `current_values`: `{'earned_runs': 0}`
- `proposed_values`: `{'earned_runs': 1}`
- `reason_codes`: `['earned_runs_mismatch']`
- `safe_to_apply`: true, `blocking_reasons`: empty
- zero identity creations, zero insertions, zero deletes, no appearance-team change, no
  pitcher-identity change, no current-team or roster change

## 6. Fingerprints

The diagnostic fingerprint observed before this correction,
`257ff3a64261d69908248de81e6c67a83d1e0357241cacab897fe610f91cb838`, is explicitly **not
approved**. The corrected one-field manifest necessarily fingerprints differently, and that
fingerprint is **also not approved**: it is not added to the apply service, and no apply path is
created here. A team/game-scoped plan is `diagnostic_subset` /
`diagnostic_subset_not_apply_eligible` by design and can never be apply-eligible.

The original approved fingerprint
`3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b` is unchanged, as are the
approved execution contract, the 675-action counts (70/445/160), the confirmation phrase
`APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06`, migration revision `c7b3e5a91d48`, the
execution-ledger row, the closeout artifact, and every byte of committed repair data.

## 7. Why rendering can no longer move the manifest

Proven on PostgreSQL 16: with the session at `extra_float_digits = 0` and again at `3`, the
scoped plan produces the identical manifest and the identical manifest fingerprint. When the
governed outs match, the precision the database happens to render a float at cannot change what
the planner proposes.
