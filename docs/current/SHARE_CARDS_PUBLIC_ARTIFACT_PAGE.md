# Share Cards — Public Share Artifact API + Immutable Share Page (SC-04)

The permanent public citation destination for a published immutable Team State
Share Artifact: a read-only public API and a public page at `/share/{public_id}`.
BaseballOS does not share graphics — it shares immutable, evidence-backed baseball
intelligence. The page answers *what BaseballOS published, for which team, what the
bullpen state was, why, on what evidence, when the data was current, and what
limitations applied* — read entirely from the frozen artifact. It never
recalculates, rewrites, or replaces the historical claim with live data.

## Architecture

```
Published immutable Share Artifact
  -> repository lookup by public_id (services.share_artifact_repository, verify=False)
  -> integrity verification (services.share_artifacts.verify_share_artifact_integrity)
  -> public field whitelist + view model (services/share_artifact_public.py)
  -> public API (GET /api/share-artifacts/<public_id>, api/share_artifacts_public.py)
  -> /share/:publicId page (components/share/PublicShareArtifactPage.jsx)
```

The canonical immutable artifact remains the sole source of meaning (identity,
state, explanation, evidence, freshness, trust, limitations, routes, copy,
versions, source snapshot, product date). The service reuses the existing
repository, integrity verifier, and lifecycle vocabulary — it introduces no second
repository, integrity implementation, payload normalizer, eligibility engine,
evidence resolver, or copy engine.

## Public read service (`services/share_artifact_public.py`)

`load_public_share_artifact(public_id) -> PublicArtifactResult(status, view)`:

- validates `public_id` (bounded URL-safe `[A-Za-z0-9._-]{1,64}`; malformed → 404);
- fetches with `verify=False` so it controls lifecycle + integrity itself;
- verifies integrity **before** returning any meaning-bearing content;
- projects only a whitelisted public subset of the immutable `payload` document +
  a few artifact columns.

## Public field whitelist

Exposed: `public_id`, `artifact_type`, `schema_version`, `render_version`,
`payload_version`, `lifecycle_state`, `is_historical`, `generated_at`,
`published_at`, `product_date`; `team` (id/name/abbreviation); `authority`
(source_snapshot_id, source_sync_run_id, data_through, published_at); `team_state`
(status_code/label/summary/contract_state); `trust` (confidence, data_state,
freshness_state, trust_state); `freshness`; ordered `evidence` receipts; ordered
`limitations` (incl. the medium partial-coverage copy); `copy`; `routes`
(share/team/methodology/data-trust — approved first-party constants, never
artifact-provided URLs); and, when superseded, a `superseded` replacement pointer.

Never exposed: raw `payload`/`payload_json`, internal DB ids, `equivalence_key`,
`integrity_hash`, `trust_metadata`, audit rows, actor/admin metadata, tokens, raw
snapshot objects, or raw exception detail.

## Lifecycle contract (one contract, shared by API + page)

| Lifecycle | Result | HTTP | Body |
| --------- | ------ | ---- | ---- |
| published | `ok` | 200 | full public view |
| superseded | `superseded` | 200 | original frozen view + replacement public_id/url + notice; original unchanged |
| withdrawn | `withdrawn` | 410 | minimal audit-safe (public_id, reason, home) — never the claim |
| draft / unknown / malformed id | `not_found` | 404 | draft is never publicly discoverable |
| integrity mismatch / verifier error | `integrity_error` | 503 | fail closed; no meaning-bearing content; logged; not cached |

## Public API (`GET /api/share-artifacts/<public_id>`)

Unauthenticated, GET only (other methods → 405). No generation, no mutation, no
current-state lookup, no admin metadata, no raw payload, no audit exposure. It is a
purpose-built public boundary that calls the canonical read service — not an admin
endpoint with auth removed. Sanitized errors. Cache-Control:

- published → `public, max-age=3600, s-maxage=86400, immutable` + ETag (immutable
  content never changes in place);
- superseded → `public, max-age=300, must-revalidate` (replacement pointer may
  appear);
- withdrawn / integrity 503 → `no-store` (never cached as a successful artifact);
- not found → short `public, max-age=60`.

## Public page (`/share/:publicId`)

Renders from the public API only — never internal/admin endpoints, Team Operations
Readiness, current team-state endpoints, the batch generator, or deprecated
client-side generators (`evidenceCardModel.js` / `evidenceCardStory.js` are not
imported). Sections: historical label (explicitly "not a live current read"),
artifact hero (from the immutable projected view), original read, ordered evidence,
trust & freshness, limitations (medium partial-coverage counts/copy exact),
methodology + Data & Trust + current-live-bullpen destinations (the team link is
labeled current/live; the page is historical). Honest states: loading (skeleton, no
fake data), published, superseded (banner + replacement, original intact),
withdrawn (no claim), not-found, integrity-failure (no meaning-bearing content),
API-error (no stale fallback; retry repeats the same public read). No
current-versus-shared, no share/download/native-share/copy-link controls.

Accessibility: one H1, logical headings, semantic evidence list, keyboard links,
status conveyed in text (not color alone), explicit `<time>` timestamps; the page
is understandable without the hero. Missing values render as placeholders — never
a fabricated team/state/count/label/timestamp or invented "Unknown" copy.

## Presentation boundary

The compatibility projection (`share_card_compatibility.py`) and the current
browser renderer remain temporary presentation infrastructure. SC-04 renders the
hero from immutable projected data; it does not begin the canonical renderer
replacement and deletes nothing (compatibility layer, `EvidenceShareMenu`,
`evidenceCardModel.js`, `evidenceCardStory.js` all remain).

## Basic metadata / SEO

Published/superseded pages set an artifact-specific `<title>`, canonical URL, a
description from frozen copy, and `index,follow`. Withdrawn/not-found/error pages
are `noindex,nofollow`. No Open Graph/X-Card images, no server-side PNG (SC-07
owns those). **Limitation:** the app is client-rendered (no SSR), so this metadata
is set at runtime and is not reliably crawler-visible without server rendering; no
new SSR framework was introduced this sprint.

## Security

`public_id` is an identifier, not a secret; it is strictly validated (no injection
or path surface). Routes are approved first-party constants — an artifact-provided
URL is never trusted as a navigation target. Draft artifacts are never discoverable
by a known public_id. No admin token, private actor/email, or sequential internal id
is exposed. Published artifacts require no authentication.

## Deferred (NOT in SC-04)

SC-05 current-versus-shared / "what changed"; SC-06+ renderer replacement; SC-07
server-side PNG / Open Graph / X-Card images / image storage; share/download/
native-share/copy-link controls; Product Intelligence; a public archive; partner
API; public-request generation; supersede/withdraw controls. SC-08–SC-10 remain
unstarted.

## Production smoke procedure (post-deploy)

1. Pick a legitimate published production artifact; record its `public_id`.
2. Open `https://baseballos.app/share/{public_id}`: loads unauthenticated; correct
   team; historical label visible; state/explanation match the artifact; evidence
   ordered; freshness/trust/limitations visible; integrity succeeds; methodology,
   Data & Trust, and team links work; no current-state comparison; no admin data.
3. `GET https://baseballos-api.onrender.com/api/share-artifacts/{public_id}` returns
   only whitelisted fields.
4. Verify a superseded and a withdrawn fixture in staging/test if production has
   none (do not mutate a production artifact to create test data).
5. Confirm the existing Share Card entry point still renders via the compatibility
   projection.

## Status record

- **SC-04 — Public Share Artifact API + immutable historical share page:
  IMPLEMENTED; COMPLETE after controlled production verification.**
- SC-05 through SC-10 remain deferred / not started.
