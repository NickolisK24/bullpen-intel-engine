# Phase 0F Internal Pitcher Evidence Review

## Branch 01: Internal Pitcher Evidence Endpoint

This branch adds the first Phase 0F surface as an internal/admin-only backend endpoint:

`GET /api/system/internal/pitcher-evidence`

The endpoint is for Nickolis/editorial/legal review only. It is protected by the existing `X-Admin-Token` admin-token guard used by other system routes.

## Public Gate

The Phase 0B legal/source review gate remains closed. This branch does not expose evidence publicly, does not add public UI, and does not change Pitcher Detail, Today, team pages, Data & Trust, or public freshness behavior.

## Endpoint Contract

The endpoint accepts a pitcher identifier plus a date/data-through value and returns stored internal rows for that pitcher/date:

- pitcher identity
- target date/data-through date
- reliever daily composed read, when present
- read components, component states, reasons, and limitations
- cited evidence rendered claims
- workload evidence references
- entry/exit context references
- roster/depth/IL context references, when already stored
- reconciliation divergences, when already stored
- internal-only watermark metadata

The endpoint is read-only. It does not create, update, recompute, or publish evidence.

## Quote-Only Rule

The endpoint serializes existing stored fields and existing rendered claims. It does not author new baseball explanations, summaries, recommendations, predictions, or public-facing copy.

## Non-Goals

- No public Pitcher Detail evidence panel.
- No frontend imports or route links.
- No public evidence objects.
- No Data & Trust changes.
- No migrations.
- No sync cadence changes.
