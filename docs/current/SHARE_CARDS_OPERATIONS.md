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

## Two authorization boundaries, one read model

The same operational read model is exposed through **two** authorization
boundaries that share one service, one view-model, one set of validation and
pagination rules, and one status vocabulary (via the shared response builders in
`backend/api/share_artifact_operations_api.py`). Only the authorization differs:

- **Admin-token boundary (SC-03B-03A)** — `require_admin_token` / `X-Admin-Token`
  on `/api/internal/share-artifacts/operations/*`. Backend/curl only; the admin
  token is never placed in the browser bundle (test-enforced by
  `frontend/tests/apiAdminToken.test.mjs`).
- **Browser-session boundary (SC-03B-03B)** — the existing production-proven
  browser-safe internal gate on `/api/internal-browser/share-artifacts/operations/*`
  (`backend/api/share_artifact_operations_browser.py`): a signed-in user's
  magic-link **Bearer** session (`resolve_current_user`) plus a founder/internal
  **email allowlist** (`parse_internal_emails` + `normalize_email`), exactly as the
  existing internal Traffic admin surface. **No admin token is ever required from,
  or delivered to, the browser.** Unauthenticated → 401 (`authentication_required`);
  a valid session not on the allowlist → 403 (`operations_forbidden`); both fail
  closed, server-side. Authenticated responses are `Cache-Control: no-store, private`
  so operational data is never publicly cached.

The email allowlist reuses `TRAFFIC_INTERNAL_EMAILS` by default; a dedicated
`SHARE_ARTIFACT_OPERATIONS_EMAILS` may override it without introducing a new
authentication mechanism.

## Internal operator page (SC-03B-03B)

Route `/internal/share-artifacts/operations`
(`frontend/src/components/admin/ShareArtifactOperations.jsx`), registered in
`App.jsx` but **absent from public navigation** (`navigation.js` / `Sidebar` /
`Footer`) and from analytics (`canonicalPage` only tracks `/bullpen`); it carries
a `noindex,nofollow` robots meta and is never statically pre-rendered with
privileged data. There is no sitemap in the repo to update.

Access is gated client-side by `useAuthState()` (checking → unauthenticated →
authorized) and enforced server-side by the browser boundary above; a 401 renders
the sign-in state and a 403 the forbidden state — neither leaks previously fetched
data. The page fetches only the browser-safe endpoints, attaching the user's Bearer
session (`frontend/src/utils/shareArtifactOperations.js`) and **never** an admin token.

Sections (read-only): a header (operational status, automatic-generation
enabled/disabled, latest snapshot id, product date, snapshot publication time, last
generation activity); a coverage summary (all counts); a per-canonical-team
coverage table (deterministic order; generated/reused/refused/failed/missing shown
as text, not color alone; reason/failure codes; integrity state); recent generation
attempts; and recent artifacts (never the raw payload). Honest loading / complete /
complete-with-refusals / degraded / incomplete / disabled / unavailable / empty /
authorization-failure / API-failure states; no fabricated numbers; semantic tables
with scoped headers, one page `h1`, and `<time>` timestamps.

**Read-only:** the page contains no generate, regenerate, retry, publish, withdraw,
supersede, repair, recalculate, delete, or configuration control, and issues only
`GET` requests. Automatic-generation state is display-only. The admin
batch-generation endpoint is never reachable from the page.

## Deployment / configuration

The browser boundary requires an authorized operator to sign in (magic link) and
their email to be present in `TRAFFIC_INTERNAL_EMAILS` (or the dedicated
`SHARE_ARTIFACT_OPERATIONS_EMAILS`). The admin-token boundary requires
`ADMIN_API_TOKEN`. No new secret is delivered to the browser.

## Status record

- **SC-03B-03A — Operational Read Model and Admin API: COMPLETE.**
- **SC-03B-03B — Authenticated Browser Operator UI: COMPLETE.**
- SC-03B operational rollout is complete.

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

- Alerting/notifications, scheduling/retries, and everything else already out of
  scope. This surface performs **detection and visibility only** — no alerting,
  no retries, no public share pages, no social rendering, no Product Intelligence,
  no artifact mutation.
