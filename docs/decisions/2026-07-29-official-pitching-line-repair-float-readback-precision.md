# Decision: exact PostgreSQL float readback for the pitching-line repair (2026)

- **Date:** 2026-07-29
- **Status:** Implemented. Root cause reproduced and proven against PostgreSQL 16. No change to
  the approved manifest, fingerprint, confirmation phrase, action counts, execution-ledger
  schema, advisory-lock contract, evidence-family registry, strict invalidation, transaction
  ordering, post-commit verification, or any downstream gate. Equality semantics are unchanged
  and remain type-exact. The apply workflow has **not** been dispatched; production data is
  unchanged.
- **Scope:** Make the repair's authoritative readback lossless so verification compares stored
  values instead of truncated renderings of them.

## Decision statement

The second production apply rolled back safely with 55 mismatches, every one on
`innings_pitched`, every one shaped identically: the manifest proposed value equalled the
update-record after value, and both differed from the stored readback by ~1e-15. The stored
readbacks were the proposed values rendered to **15 significant decimal digits**.

The database was never wrong. The *reading* was. PostgreSQL renders `float8` as text on the
wire, and with `extra_float_digits <= 0` that text is rounded to 15 significant digits, which
does not round-trip every IEEE-754 double. The repair therefore compared a full-precision
proposed value against a truncated rendering of the value it had just written, and correctly
reported a mismatch that does not exist in storage.

The fix makes the database return the exact double. It does not make different values compare
as equal.

## 1. Reproduction (proven, not assumed) — PostgreSQL 16.13 / psycopg2 2.9.9

One transaction, one set of rows, three settings, **no rewrite between reads** — which proves
the stored bits never changed and only the rendering differed:

| outs | proposed (`outs/3.0`) | readback at `extra_float_digits = 0` | production artifact |
|---|---|---|---|
| 14 | `4.666666666666667`  | `4.66666666666667`  | `4.66666666666667`  |
| 11 | `3.6666666666666665` | `3.66666666666667`  | `3.66666666666667`  |
| 10 | `3.3333333333333335` | `3.33333333333333`  | `3.33333333333333`  |
| 2  | `0.6666666666666666` | `0.666666666666667` | `0.666666666666667` |
| 1  | `0.3333333333333333` | `0.333333333333333` | `0.333333333333333` |

Every value matches the production artifact exactly, and the maximum absolute difference is
`3.552713678800501e-15` — also exactly the value the artifact reported. At
`extra_float_digits = 0` the type-exact comparison reports 5/5 mismatches; at `1` and at `3`
the same rows read back bit-for-bit identical (`float.hex()` equal) and 0/5 mismatch.

`extra_float_digits = 1` is sufficient on this server: PostgreSQL 12+ selects shortest-precise
output for any value ≥ 1. The repair nevertheless governs **3** — the maximum supported value,
identical in behavior wherever it is accepted, and not dependent on the server being 12 or
newer.

## 2. What was changed

`_configure_exact_postgres_float_readback(session)` reads `extra_float_digits`, applies
`SET LOCAL extra_float_digits = 3`, reads it back, and requires the observed value to be the
governed one. It returns a structured `float_readback_contract` (dialect, setting, observed
value before, governed value requested, observed value after, `transaction_local`,
`exact_float_readback_enabled`). If the setting cannot be applied or verified, the repair
aborts **FAIL** and rolls back — verifying against renderings that cannot be trusted is not
verification. On a non-PostgreSQL dialect the readback is already exact and nothing is applied.

`SET LOCAL` is confined to the one repair transaction and is discarded by its single commit or
its rollback. No `ALTER DATABASE`, `ALTER ROLE`, `ALTER SYSTEM`, connection-string mutation,
hosting-provider setting, or committed session state is touched, and no other connection is
affected. A test parses the module and asserts that the only `SET` statement it emits is this
one `SET LOCAL`.

## 3. Why the placement is exactly where it is

Required order, unchanged except for step 11:

1. Regenerate the planner under production's existing connection behavior.
2. Validate the exact approved fingerprint and all pre-write preconditions.
3. End the planner's read transaction.
4. Open the governed mutation transaction. 5. Acquire the advisory lock.
6. Revalidate mutation preconditions (including the reviewed amendment's before-state).
7. Identities. 8. Insertions. 9. Updates + strict evidence invalidation. 10. Flush.
11. **`SET LOCAL extra_float_digits = 3`, and verify it took effect.**
12. All authoritative readbacks. 13. Every in-transaction verification.
14. Execution-ledger row. 15. One commit.

The approved manifest was generated while production rendered existing floats under its own
connection behavior. Raising the render precision before planner regeneration, or before any
planned-current comparison, would change the Python representation of **already-stored** values
and could manufacture fingerprint or precondition drift that production does not have. The
setting is needed only to read back the values *this* transaction staged, so it is turned on
after the last pre-write comparison and before the first authoritative readback. A test asserts
this ordering from the source.

## 4. Verification semantics are untouched

`_same_governed_value(left, right)` remains exactly `type(left) is type(right) and left == right`.
No tolerance, no rounding of manifest values, no approximate equality, no coercion, no
null-equivalence, no ignored field, and `innings_pitched` is not exempted. After exact readback
is established, all three authorities agree exactly and by type. A new named check,
`exact_float_readback_is_established`, joins the in-transaction verifications, so a run can
never pass without proving the readback was lossless.

## 5. Artifact and summary

`float_readback_contract` is written into the payload **before** the abort/rollback decision, so
a failed run retains the setting evidence. The bounded workflow summary reports the dialect,
setting, before/after values, transaction-local flag, and whether exact readback was enabled —
never a credential or connection detail.

## 6. Post-commit

`SET LOCAL` ends with the repair transaction, so post-commit verification does not run under it
and must not rely on it. Post-commit checks remain mandatory, unchanged, and with no skip flag.
If a future post-commit check needs precise float reads, that must be governed separately.
