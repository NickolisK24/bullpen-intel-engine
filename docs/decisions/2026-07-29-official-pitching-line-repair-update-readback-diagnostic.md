# Decision: official pitching-line repair update-readback diagnostic (2026)

- **Date:** 2026-07-29
- **Status:** Implemented (diagnostic hardening only). No equality semantics changed. The
  approved manifest, action counts, fingerprint, confirmation phrase, execution-ledger
  schema, advisory-lock contract, evidence-family registry, strict invalidation, transaction
  ordering, post-commit verification, and every downstream gate are unchanged. The apply
  workflow has **not** been dispatched; production data is unchanged.
- **Scope:** Make a future `every_updated_field_matches_proposed_values` failure legible, and
  force the update readback to be an authoritative database round-trip, without weakening any
  verification.

## Decision statement

The one production apply of "Official Pitching-Line Repair Apply (2026)" rolled back safely at
the in-transaction check `every_updated_field_matches_proposed_values`. Every mutation was
reverted (`transaction_committed=false`, `rollback_performed=true`,
`database_writes_performed=false`, `execution_ledger_id=null`, applied counts `0/0/0`). The
transaction had staged 70 identity creations, 445 GameLog insertions, 160 GameLog updates, and
strict invalidation of 1,593 evidence objects.

The failure was correct — nothing was committed — but **undiagnosable**. The artifact recorded
only the failed check *name*. It did not record which action, which row, which field, the
reviewed value, the assigned value, or the stored value. This change fixes the diagnostic gap.
It does **not** change what the check accepts as a match.

## 1. The two independent defects in the pre-hardening check

```python
for record in update_records:
    row = session.query(GameLog).filter(GameLog.id == record['local_game_log_id']).one_or_none()
    ...
    for field, value in record['after'].items():
        if field in record['changed_fields'] and getattr(row, field, None) != value:
            checks['every_updated_field_matches_proposed_values'] = False
```

1. **It did not force a database round-trip.** `session.query(GameLog).filter(id==...)`
   returns the object already in the session's identity map — the same object this run just
   assigned to and flushed. `getattr(row, field)` therefore returns the value the run
   *assigned*, never the value the database *stored*. A plain entity query cannot, by
   construction, catch a divergence between the two. (Proven in
   `tests/`: after a raw `UPDATE`, the entity query still returns the stale in-memory value
   while a column `SELECT` returns the stored value.)

2. **On failure it recorded a bare boolean.** The raise carried only
   `failed_verifications`, and the caller stored `verification_results` and `mutation_watch`
   into the artifact *after* the verifier returned — so a verification failure, which raised,
   lost them entirely. The artifact could not say what disagreed.

## 2. Reproduction against PostgreSQL 16 — not reproduced

Every changed field in an update action is an `int`, `bool`, or `str` except one:
`innings_pitched` (`db.Float` → `double precision`), whose proposed value is
`int(innings_pitched_outs) / 3.0` — a non-terminating binary fraction whenever
`outs % 3 != 0`. It is the only field whose value could, in principle, read back differently
than it was assigned, and the pre-hardening check used an exact `!=` with no tolerance, unlike
the insert verifier and the model's own CHECK constraint (both `1e-6`).

Tested directly on **PostgreSQL 16.13 / psycopg2 2.9.9**: `int(outs)/3.0` for every
`outs ∈ [0, 27]` round-trips through `double precision` **bit-for-bit** — identical `float.hex()`
before and after — across a plain identity-map re-query, a forced `expire`+`refresh`, and a
`populate_existing` narrow `SELECT`. Zero mismatches. The `innings_pitched` hypothesis does not
reproduce on the production database engine even with a forced round-trip, and no other field
type can differ under equality.

The repair's own code also contains no mechanism that would expire a loaded `GameLog` between
the assignment and the readback: dependent-evidence invalidation is ORM per-row `setattr` on
`EvidenceObject` (no bulk `synchronize_session`, no `game_logs` statement), and the only
`session.flush()` between apply and verify does not expire attributes.

**Conclusion:** the exact production mismatch cannot be reproduced from retained evidence. The
artifact did not capture the row-level values, and the code path plus the production engine's
float semantics do not, on their own, produce the observed failure. Per the governing
constraint, equality semantics were therefore **not** changed — no float tolerance, no
integer/boolean coercion, no string conversion, no null-equivalence, no ignored field, no
skipped check was introduced.

## 3. What the hardening does

- **Forced round-trip that bypasses the identity map.** The changed fields (and the
  correction-metadata fields) are read back with a narrow column `SELECT`
  (`sa.select(...).mappings()`), which returns the values PostgreSQL stored, not the object in
  the identity map.
- **Three authorities per changed field**, triangulated in one documented, deterministic
  helper `_readback_field_mismatch`: (1) the reviewed manifest proposed value (from the
  original UPDATE action), (2) the value this run assigned (the update record's `after`
  snapshot), (3) the value read back from the database. A field passes only when all three are
  equal in BOTH Python storage type and value — a type-exact `==` (`type(a) is type(b) and
  a == b`, via `_same_governed_value`), because plain `==` treats `True == 1` and `1 == 1.0`
  as true and would let a storage-type disagreement pass. This is a strengthening, not a
  normalization: no value is coerced, rounded, converted, or made null-equivalent. On any
  disagreement a structured item records the action id, row id, official person id,
  appearance-team id, field, planned-current value, all three values, all three Python type
  names, and all three (type-exact) pairwise equality booleans.
- **Artifact preserved before rollback.** The verifier now *returns* its full result; the
  caller records `verification_results`, `update_readback_mismatches`, `mutation_watch`, the
  **staged** action counts, and the staged dependent-evidence totals into the payload *before*
  deciding to abort. `_finalize_without_writes` preserves those fields, so a rolled-back run
  carries every named check, the exact row-level mismatch, and the distinction between staged
  (attempted) and applied (`0/0/0`, committed) counts.
- **Bounded run summary.** The workflow summary reports the mismatched-row count, the
  mismatched-field-reading count, the field names, and the local game-log ids only. Per-row
  stored values and Python types stay in the private artifact and are never printed.

## 4. Why another explicit dispatch is required

The retained artifact from the failed run does not contain the row-level values, and the
failure does not reproduce from code plus PostgreSQL float semantics. The only way to capture
the exact mismatch is a further governed dispatch of the apply workflow, which — with this
hardening in place — would now record precisely which action, row, field, and values
disagreed, and whether the manifest, the assigned value, and the stored value differ. That
dispatch is **not** authorized here and is not performed. Only after such evidence exists could
any field-specific normalization even be considered, and only if it were proven to represent
the model's governed storage semantics and incapable of hiding a materially different value.

## 5. Explicitly unchanged

Approved manifest and its fingerprint
`3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b`; the confirmation phrase
`APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06`; action counts and total (675); season, as-of date,
full-season scope; the V1/V2 accepted baseline and the Brandyn Garcia amendment; migration
revision `c7b3e5a91d48`; execution-ledger schema; advisory-lock contract; identity and
insertion behavior; the evidence-family registry and strict invalidation; transaction ordering;
the mandatory post-commit verification; and every downstream gate, which stays blocked.
