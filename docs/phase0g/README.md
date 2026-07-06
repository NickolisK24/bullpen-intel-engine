# Phase 0G Internal Team Evidence Review

## Branch 01: Internal Team Evidence Endpoint

This branch adds the first Phase 0G surface as an internal/admin-only backend
endpoint:

`GET /api/system/internal/team-evidence`

The endpoint is for Nickolis/editorial/legal review only. It is protected by
the existing `X-Admin-Token` admin-token guard used by other system routes.

## Endpoint Contract

Required query parameters:

- `team_id` or `teamId`
- `date`, `data_through`, or `dataThrough`

The endpoint returns stored internal review data for one team and one product
date:

- team identity from stored pitcher rows
- target date/data-through date
- team daily composed read, when present
- read components and cited evidence references from the stored team read
- stored rendered claims from cited evidence
- full internal team evidence objects and citations
- pointer-only reliever daily read rows for pitchers on the team
- stored team-day reconciliation divergences
- internal-only watermark metadata

Reliever daily reads are exposed as pointers only: read id/key, pitcher identity,
completeness state, and recompute status. This branch does not implement the
deferred Phase 0E member-read rollup and does not aggregate reliever read
components, citations, or states.

## Quote-Only Rule

The endpoint serializes stored fields and stored `rendered_claim` strings. It
does not author new baseball explanations, summaries, recommendations,
predictions, or public-facing copy.

## Read-Only Rule

The endpoint is read-only. It does not create, update, delete, recompute,
publish, or trigger any build path.

## Public Gate

The Phase 0B public evidence gate remains closed. This branch does not expose
evidence publicly, does not add public UI, does not add a public route, and does
not change frontend, Data & Trust, sync, methodology, or migrations.

## Non-Goals

- No public team relief endpoint.
- No public team relief panel.
- No frontend changes.
- No member-read rollup.
- No new models, migrations, evidence rules, classifications, or read-contract
  changes.
- No sync cadence, flag, or rebuild changes.
- No public wording decisions for later Phase 0G surfaces.

## Branch 02: Public Team Relief Work Endpoint

This branch adds a public, backend-only team relief-work endpoint:

`GET /api/bullpen/teams/<team_id>/relief-work`

The endpoint is the team-grain sibling of the Phase 0F pitcher recent-work
endpoint. It uses only already-public game-log fields, stored pitcher roster
assignment fields, and the existing public freshness block. It does not expose
evidence objects, citations, read components, source-readiness details,
reconciliation content, or internal review payloads.

Relief classification is based only on the public `games_started` signal:
`0` rows are counted, `1` rows are excluded as starts, and `NULL` rows are
excluded and disclosed in window copy. Because game logs do not store
historical team assignment, team attribution is current-roster based and is
disclosed in the payload's scope sentence.

Frontend integration is deferred. The Phase 0B public evidence gate remains
closed, and this branch does not change frontend, Data & Trust, sync,
methodology, migrations, static team previews, or existing public route
behavior.

## Branch 03: Public Team Relief Work Panel

This branch adds a frontend-only Recent Bullpen Work panel that consumes the
Branch 02 endpoint and renders server-owned copy verbatim. It adds no backend,
Data & Trust, sync, methodology, static preview, Today, dashboard/board, or
legacy fatigue/availability changes. The Phase 0B public evidence gate remains
closed.
