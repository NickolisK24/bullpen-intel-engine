# Tonight v1 serving (TN-02)

Status: `tonight_v1` is served on request from its stored, publication-bound
row. The default Tonight response is still legacy `tonight_v5`; the frontend
does not request v1 yet (TN-08).

## Contract selection

One URL, `GET /api/bullpen/intelligence/tonight`, selected by `contract`
(the key Team Board delivery already uses for its contract identity):

| Request | Serves |
| --- | --- |
| no `contract`, `contract=`, `contract=tonight_v5` | legacy `tonight_v5`, unchanged |
| `contract=tonight_v1` | the stored v1 projection of the current trusted publication |
| any other value | 400, Tonight shell, `reason_code=invalid_query_parameter`, `parameter=contract` |

Selection lives in `api.bullpen.tonight_contract_response`, called first by
both the original view and the production `trusted_tonight_view` override, so
production and non-production select identically. With `contract=tonight_v1`,
`reference_date`, `dashboard_snapshot_id` and `snapshot_id` are rejected (400):
v1 serves the current publication only. No existing public read route serves
explicit historical snapshots with immutable caching, so historical v1 access
is deferred.

## Serving path

`services/tonight_v1_serving.serve_current_tonight_v1`:

1. Current trusted Dashboard snapshot via
   `get_latest_valid_dashboard_snapshot_projection(('freshness',))`, the same
   selector and validity rules as the Home / League / Trust projections. Only
   metadata and the freshness domain are read.
2. Tonight date = that snapshot's `availability_reference_date` (never
   wall-clock today, never schedule `officialDate`).
3. The row with `contract='tonight_v1'`, `dashboard_snapshot_id=<current id>`,
   `reference_date=<that date>` (the TN-01 unique identity; `one_or_none`).
4. Identity check (below). 5. The stored payload is returned unchanged.

A v1 hit issues 2 SQL statements (snapshot projection, row lookup). It reads no
`game_logs`, `fatigue_scores`, `slate_games` or `pitchers`, issues no
INSERT/UPDATE/DELETE, and cannot call `build_tonight_v1`, the generator,
`load_slate_games`, `build_team_bullpen_context` or the legacy Tonight reader.

## Fail-closed behaviour

Missing row, a row bound only to an older snapshot, no trusted publication, or
an identity mismatch all return HTTP 200 (the legacy Tonight endpoint's
fail-soft convention) with `Cache-Control: no-store`, no ETag, and:

```
contract: tonight_v1, status: unavailable,
reason = empty_reason = trusted_tonight_v1_publication_unavailable,
reason_codes: [tonight_v1_publication_missing
               | trusted_dashboard_publication_unavailable
               | tonight_v1_publication_identity_mismatch],
edition: null, current_publication: {...} | null,
summary: {game_count: 0}, game_count: 0, games: [], lead: null,
featured_game_pks: [], league_changes: [], quiet_day: false,
limitations: [one factual sentence]
```

A v1 request never falls back to `tonight_v5` and never falls back to another
snapshot's row. A read failure (for example a missing table) is the normal 503
Tonight error shell, uncached. A stored `tonight_v1` payload has no `status`
key; an off-day payload (`games: []`, `quiet_day: true`) is served normally.

## Identity validation

Before serving, the row must agree with its payload and the current snapshot:
`contract` (row and payload), `dashboard_snapshot_id` (row, snapshot,
`edition.publication`), `sync_run_id` (row, snapshot, `edition.publication`),
`data_through` (row, snapshot, `edition.data_through`), reference date (row
`reference_date` and `availability_reference_date`, snapshot, and
`edition.baseball_date` / `edition.availability_reference_date`), and a
well-formed `content_sha256`. A disagreement is logged as
`tonight_v1 authority integrity failure` with the field name and withheld;
nothing is repaired on request. The payload is not re-hashed per request.

## Delivery

Through `services.public_delivery.apply_public_delivery_headers`, which now
accepts an explicit stored `validator`:

- `ETag: "<tonight_publications.content_sha256>"` (strong); `If-None-Match`
  returns 304 with an empty body after the same two reads.
- `Cache-Control: public, max-age=0, must-revalidate` (the existing
  current-alias policy): the current alias can advance to a newer publication.
- `X-BaseballOS-Snapshot-ID`, `X-BaseballOS-Sync-Run-ID`,
  `X-BaseballOS-Data-Through`, `X-BaseballOS-Contract: tonight_v1`, all from
  the served row, which the identity check has tied to the payload.
- Unavailable v1 responses: `no-store`, `X-BaseballOS-Contract` only.
- Legacy `tonight_v5` responses are unchanged (no new headers, no ETag).

## Production state at merge

`tonight_publications` exists (head `c3e7a1d9f5b2`) with 0 rows until the next
normal trusted publication; until then `contract=tonight_v1` answers the
fail-closed body with `tonight_v1_publication_missing`. No migration is
added. No frontend change: `getTonightIntelligence` still requests the default.
