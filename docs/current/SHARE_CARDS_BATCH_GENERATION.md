# Share Cards — Batch Team State Generation (SC-03B-01)

This note documents the batch generation foundation and the canonical evidence
authority added in SC-03B-01. It is backend operational foundation only: there is
**no** scheduling, public API, renderer, PNG/Open Graph rendering, share page,
distribution action, or Product Intelligence event here. Those remain deferred to
later SC branches.

## What this branch adds

1. **`services/evidence_authority.py`** — one canonical resolver for trusted,
   current governed evidence for a `(subject, product_date)`.
2. **`services/share_artifact_batch_generation.py`** — a batch orchestration
   layer around the existing SC-03A single-team generation service.
3. **`POST /api/internal/share-artifacts/team-state/batch`** — an internal,
   admin-token-gated invocation surface (added to the existing admin blueprint).

## Canonical evidence authority (Workstream A)

`resolve_subject_current_evidence(subject_type, subject_id, product_date, *, read=None)`
(with `resolve_current_team_evidence` / `resolve_current_pitcher_evidence`
wrappers) is now the single owner of the governed `EvidenceObject` authority
query that was previously duplicated inline in two readers:

- `services/internal_team_evidence.py::_evidence_objects`
- `services/internal_pitcher_evidence.py::_evidence_objects`

These two were byte-for-byte identical except for the subject type, and both also
duplicated the identical "merge in the composed read's cited evidence, then
re-sort" step (`cited_evidence_objects`). Both readers now delegate to the
canonical module; behavior is unchanged.

The authority it owns (and preserves exactly):

| Concern            | Rule |
| ------------------ | ---- |
| subject identity   | `subject_type` + `subject_id == str(id)` (exact) |
| product date       | `product_date == <the caller's trusted reference date>` (exact — never another date) |
| trust / freshness  | `recompute_status == RECOMPUTE_CURRENT` (excludes stale/superseded/needs-recompute) |
| public eligibility | `posture == internal_only` (the governed posture for every stored row today) |
| ordering           | `(evidence_type, rule_id, id)` ascending |

It **fails closed**: a malformed subject/date raises `EvidenceAuthorityError`
rather than masquerading as "no evidence"; a no-match returns an empty list; it
never falls back to a different date, subject, snapshot, or stale row.

What it deliberately does **not** do:

- It does not own evidence *policy*. The rule → classification verdicts remain in
  `services/evidence_classification.py` and are untouched.
- It does not invent a snapshot cross-check the readers never had (date alignment
  is exact equality on the caller-resolved product date).
- It does not fold in the two *drifted* readers
  (`team_daily_read._team_evidence` / `reliever_daily_read._pitcher_evidence`),
  which deliberately include superseded rows and flag them with a governed reason
  code — migrating them would silently drop that governed nuance.
- Note: today every stored `EvidenceObject` is `internal_only`; the rule →
  public-candidate classification is advisory rule metadata, not a stored-row
  posture. The `posture` argument defaults to the governed value and is the seam
  a later branch would use once a public posture exists.

## Batch generation service (Workstream B)

`generate_team_state_artifacts_batch(*, source_snapshot_id, product_date, actor, team_ids=None)`
returns a `BatchGenerationResult`.

The batch layer owns none of the intelligence. It only: validates one shared
source authority, enumerates teams, calls the single-team service once per team,
captures each outcome, and summarizes coverage.

### Required source authority

An explicit trusted source authority is required: `source_snapshot_id` and
`product_date`. The batch resolves the current latest published daily snapshot
through the same seam single-team generation uses
(`team_state_source.resolve_latest_trusted_snapshot`) and validates, **before any
team is attempted**, that it is present, trusted, and matches both the declared
`source_snapshot_id` and `product_date`. If not, the whole batch is refused with
a `BatchSourceAuthorityError` (`snapshot_missing` / `snapshot_untrusted` (or the
governed unavailable reason) / `snapshot_id_mismatch` / `product_date_mismatch`)
— so one invalid global source never becomes N misleading per-team failures.

The validated snapshot is then threaded into every per-team
`generate_team_state_artifact(..., snapshot=...)` call, so every team is generated
against the identical shared authority (the snapshot is not independently
re-inferred per team). `product_date` is passed as each call's `requested_date`,
so the existing SC-02 requested-date/snapshot alignment gate applies per team.

### Team enumeration and deterministic order

Teams come from the existing canonical team authority
(`services/team_directory.valid_team_ids` — the same universe the public team
surfaces are built from; no second registry), processed in stable ascending
team-id order. The same inputs against the same authoritative source produce the
same ordered result. An optional `team_ids` subset (for tests / controlled
operator runs) is de-duplicated and sorted; malformed ids raise
`BatchValidationError`; a well-formed but unknown team id is attempted and
governed-refused by the single-team path (so it stays accounted for, never
"missing").

### Reuse, isolation, idempotency, concurrency

- Every team is delegated to the existing `generate_team_state_artifact`. No
  eligibility, payload, evidence-selection, audit, dedup, publication, or
  integrity logic is duplicated.
- Each team is an independent atomic attempt (the single-team service commits its
  publication + durable audit atomically and fails closed on its own). One team's
  refusal or failure never skips another; an unexpected exception from a team is
  caught and recorded as an accounted `failed` result so later teams still run.
- Re-running the same batch against the same authoritative source safely reuses
  equivalent published artifacts through the existing SC-01 deduplication (the
  second run reports `reused`, creates no duplicates).
- The batch adds no transaction of its own and no second audit log; it inherits
  the single-team service's concurrency/duplicate protections unchanged. The
  audit actor/source are `admin_batch_api` / `internal_admin_batch_api`.

### Outcome contract

Each team maps to exactly one terminal `BatchTeamResult.outcome`:

| Batch outcome | From single-team outcome | Meaning |
| ------------- | ------------------------ | ------- |
| `generated`   | `published`              | a new immutable artifact was published |
| `reused`      | `reused`                 | an equivalent published artifact already existed |
| `refused`     | `refused`               | a trust/eligibility/evidence/freshness gate intentionally declined publication |
| `failed`      | `failed_closed` (or unexpected raise) | an otherwise-valid attempt could not complete for a technical/operational reason |

Refusal vs failure is preserved end to end: refusals are typed and not retried;
technical problems are sanitized `failed` results; exceptions are never converted
into a successful "unavailable". Per-team fields: `team_id`, `outcome`,
`public_id` (generated/reused), `reason_code` (refused), `failure_code` (failed),
`audit_id`, `source_snapshot_id`, `product_date`. No stack traces, raw
exceptions, private payloads, or internal ORM objects are exposed.

### Coverage / accounting

The summary reports `source_snapshot_id`, `product_date`, `canonical_team_count`
(full-league expected size), `attempted_count`, `generated_count`,
`reused_count`, `refused_count`, `failed_count`, `missing_count` /
`missing_team_ids`, `is_complete`, `started_at` / `completed_at` /
`duration_seconds` (operational metadata, excluded from the deterministic
contract), and the ordered `results`.

Accounting invariant (enforced in the result constructor —
`BatchAccountingError` if violated):

```
attempted_count == generated_count + reused_count + refused_count + failed_count
```

Coverage: a **missing** team is a canonical/expected team with no terminal result
of any kind. A refused or failed team is *accounted for*, not missing. A batch
with any missing team is `is_complete == False` and operationally unsuccessful
even if some artifacts were generated. For a full-league run,
`canonical_team_count == attempted_count`; for a subset run, the subset is the
expected set and `canonical_team_count` is still reported for context.

## Internal invocation surface

`POST /api/internal/share-artifacts/team-state/batch` (admin-token gated, no
public route). Request:

```json
{ "source_snapshot_id": 12345, "product_date": "2026-07-23", "team_ids": [optional subset] }
```

Responses:

- `200` with the coverage summary and `"status": "completed"` (or `"incomplete"`
  if any team is unaccounted for).
- `409` `{"status": "failed", "reason": "<snapshot_missing|snapshot_untrusted|snapshot_id_mismatch|product_date_mismatch>"}`
  when the shared source authority is globally unusable.
- `400` `{"status": "failed", "error": "<code>"}` for malformed input.
- `503` `{"status": "failed", "error": "internal_error"}` on an unexpected
  failure (sanitized).

### Running a controlled subset

```
POST /api/internal/share-artifacts/team-state/batch
{ "source_snapshot_id": 12345, "product_date": "2026-07-23", "team_ids": [147, 121] }
```

### Running a full-league attempt

```
POST /api/internal/share-artifacts/team-state/batch
{ "source_snapshot_id": 12345, "product_date": "2026-07-23" }
```

## Deferred to later SC-03B branches

- ~~Post-publication automatic invocation~~ — done in SC-03B-02: a committed
  trusted-snapshot publication now automatically invokes this batch service. See
  `SHARE_CARDS_PUBLICATION_HOOK.md`.
- Scheduled invocation (cron, GitHub Actions, queues) remains deferred.
- Operator surfacing UI / read-only listing of recent artifacts + audit attempts
  (the `list_recent_team_state_artifacts` / `list_generation_audits` repository
  queries already exist to back it).
- A comparison Team State artifact type.
- The public artifact API, `/share/{public_id}`, renderer replacement, and
  everything else already out of scope for this branch.
