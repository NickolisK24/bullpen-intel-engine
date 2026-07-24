# Share Cards — Internal Operations & Coverage Monitoring (SC-03B-03)

A read-only internal surface that answers one question for the operator: are
immutable Team State Share Artifacts being generated correctly after trusted
snapshot publication? It observes the existing system — it recalculates no
baseball intelligence, invokes no generation, mutates nothing, and creates no
Product Intelligence events. No new persistence, audit, analytics, scheduler, or
renderer was introduced.

## Authoritative data sources (all reused, none re-implemented)

| Question | Source |
| -------- | ------ |
| Which teams exist? | `services.team_directory` (`valid_team_ids` / `valid_team_directory`) — the same active-pitcher universe, one registry |
| Latest trusted snapshot | `services.team_state_source.resolve_latest_trusted_snapshot` (the existing snapshot authority) |
| What was attempted? | `models.share_artifact_generation_audit` (the SC-03A durable audit) via the repository |
| What artifacts exist? | `models.share_artifact` via `services.share_artifact_repository` |
| Integrity | `services.share_artifacts.verify_share_artifact_integrity` (the existing verifier) |
| Outcome / refusal / failure vocabulary | the existing audit + batch outcome codes |
| Automatic generation on/off | `SHARE_ARTIFACT_AUTOGENERATION_ENABLED` app config (SC-03B-02) |

The read model lives in `services/share_artifact_operations.py`. It owns only the
summarization; it owns none of the intelligence, generation, or persistence.

## Coverage model

Coverage is always tied to **one** source snapshot authority — the latest trusted
published snapshot (`source_snapshot_id` + `product_date`). For each canonical
team, the operator-facing terminal state is:

- `generated` — a new immutable artifact was published for this snapshot
- `reused` — an equivalent published artifact was reused for this snapshot
- `refused` — a governed trust/eligibility/evidence gate declined publication
- `failed` — an otherwise-valid attempt failed for a technical reason
- `missing` — no terminal generation attempt for this snapshot **and** no
  equivalent published artifact tied to this same authority

The current team state is the **most recent terminal audit** for that team and
this source snapshot (all four audit outcomes are terminal). Earlier attempts are
never erased — they remain in the audit list. An artifact or audit from a
different snapshot or product date **never** satisfies current coverage, and there
is no silent fallback to an older artifact.

`missing` vs `refused` vs `failed`: a refused or failed team is *accounted for*
(the system reached a governed terminal decision). Only a team with no terminal
result at all — and no equivalent published artifact for this authority — is
missing. Missing/incomplete coverage is operationally unsuccessful even if other
teams generated.

## Accounting invariants (enforced — fail closed)

```
canonical_team_count == generated + reused + refused + failed + missing
accounted_team_count == generated + reused + refused + failed
```

Each canonical team increments exactly one state, and an unexpected/uncounted
state raises `ShareArtifactOperationsError` rather than presenting a
plausible-but-wrong summary.

## Operational status (plain, non-numeric — no health score)

Precedence: `unavailable` → `disabled` → `incomplete` → `degraded` →
`complete_with_refusals` → `complete`.

- `complete` — every team accounted, 0 failed, 0 missing, 0 integrity problems, 0 refusals
- `complete_with_refusals` — every team accounted, ≥1 governed refusal, 0 failed/missing/integrity
- `degraded` — every team accounted, ≥1 failed team or integrity problem, 0 missing
- `incomplete` — ≥1 missing/unaccounted canonical team
- `disabled` — automatic post-publication generation is intentionally disabled
- `unavailable` — no trusted published snapshot / the read cannot be safely built

A run is not unhealthy merely because a team was correctly refused.

## Artifact integrity visibility

Each accounted published artifact reports `verified`, `mismatch`, or `error`
(verification unavailable), via the existing verifier. The surface **detects and
displays** integrity problems — it never repairs, rewrites, replaces, or hides a
mismatched artifact, and never exposes it on a public path.

**Bounded verification (chosen approach):** the overview verifies only the
coverage set for the latest snapshot (≈ the canonical team count, one artifact per
accounted team); the recent-artifacts list verifies only the returned page. There
is no unbounded history scan and no background worker/scheduler.
*Limitation:* integrity of artifacts outside the current snapshot / current page
is not proactively scanned — it is checked when that artifact appears in a bounded
read.

## Internal API (read-only, admin-token gated)

On the existing internal Share Artifact admin boundary
(`share_artifacts_admin_bp`, `require_admin_token` / `X-Admin-Token`), bare-JSON
responses, `{'error': code}` + status on failure, `query_params.py` validation,
deterministic ordering, bounded limits (default 25, max 100), no mutation, no
generation:

- `GET /api/internal/share-artifacts/operations/overview` — coverage + integrity
  summary for the latest trusted snapshot, with all counts and the invariant fields.
- `GET /api/internal/share-artifacts/operations/artifacts?limit=&offset=&team_id=`
  — bounded, newest-first recent immutable artifacts (safe projection; never the
  raw payload JSON).
- `GET /api/internal/share-artifacts/operations/audits?limit=&offset=&team_id=&outcome=&source_snapshot_id=&product_date=`
  — bounded, newest-first recent generation audit attempts; typed refusal/failure
  codes preserved; no stack traces. (Reason-code filtering is not offered —
  reasons are JSON, not an indexed column.)

There is no public equivalent of any of these routes.

## Access-control boundary — and why there is no operator UI page in this branch

The operations API is gated by the backend `ADMIN_API_TOKEN` (`X-Admin-Token`),
the same gate as the SC-03A/SC-03B-01 generation routes. Operators use it
server-side or via curl, exactly as the repository already documents for its other
privileged endpoints (`frontend/src/utils/api.js` states the admin token is never
placed in the browser bundle, and `frontend/tests/apiAdminToken.test.mjs`
test-enforces that `api.js` never sends `X-Admin-Token`).

**Access-control gap (documented, not worked around):** the existing frontend
cannot safely call an `X-Admin-Token` API — that is a deliberate, test-enforced
invariant. The one existing admin page (`TrafficIntelligenceAdmin`) instead uses a
different gate: a signed-in user's magic-link Bearer token plus a backend email
allowlist (`resolve_current_user()` + a `*_INTERNAL_EMAILS` config). Building an
operator UI page would therefore require either (a) putting the admin token in the
browser — explicitly forbidden and test-blocked — or (b) standing up a new
email-allowlist auth surface and config for share-artifact operations. Per this
sprint's ACCESS CONTROL instruction ("STOP before inventing a new authentication
design … implement only the safe backend read service/API portion"), the UI page
is intentionally **not** built here. The safe, complete backend read service +
admin API is delivered; the frontend page is deferred pending an explicit decision
on which existing gate it should adopt (admin-token via a server-side proxy, or
the email-allowlist pattern).

## Performance / query boundaries

Deterministic default/max limits (25 / 100); `offset` pagination; the overview is
scoped to the latest snapshot (one audit query + one artifact query + a bounded
per-team integrity check — no N+1); recent artifacts/audits are independently
pageable; no caching that could conceal current failures; no new infrastructure.

## Known limitations / operational gaps in current durable data

- Coverage uses `source_snapshot_id` as the authority key (each snapshot has one
  product date); a per-team artifact for a different snapshot is correctly not
  counted.
- Reason-code filtering on the audit list is not provided (JSON storage).
- Integrity is verified only within bounded reads (see above).

## Deferred

- The internal operator **UI page** (pending the access-control decision above).
- Alerting/notifications, scheduling/retries, and everything else already out of
  scope. This surface performs **detection and visibility only** — no alerting,
  no retries, no public share pages, no social rendering, no Product Intelligence.
