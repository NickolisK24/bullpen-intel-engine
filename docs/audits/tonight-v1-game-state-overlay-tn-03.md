# Tonight v1 game-state overlay (TN-03)

Status: `contract=tonight_v1` serves the stored, publication-bound row with the
current schedule state of its games applied at serve time. The default Tonight
response is still legacy `tonight_v5`, and the frontend is unchanged (TN-08).

## Authority model

| Authority | Source | Fields |
| --- | --- | --- |
| Frozen | stored `tonight_publications` row (the trusted Team Board publication) | Both TeamSides (Team State, rest, workload, multi-day usage, key arms, rotation, change_refs), context, featured, links, lead, league changes, edition, and every bullpen summary field |
| Overlay | current `slate_games` row with the same `game_pk` | `game.state`, `game.first_pitch_utc`, `game.state_as_of` |

The overlay adds no baseball intelligence. The stored row is never mutated: the
overlay builds a new payload dict, and every unchanged game and TeamSide object
passes through as stored.

## Serving path

`services/tonight_v1_serving.serve_current_tonight_v1`:

1. Resolve the trusted Dashboard snapshot (unchanged from TN-02).
2. Read the `tonight_publications` row bound to that snapshot, and run the
   identity check (unchanged from TN-02).
3. Read the stored games' `game_pk`s and fetch their current schedule facts in
   one bounded query: `slate_games WHERE game_pk IN (...)`. The query selects
   only `game_pk`, `game_date_et`, `game_time_utc`, `normalized_state`,
   `status_detailed` and `last_synced`. An off-day payload has no games, so no
   schedule query is issued.
4. Apply `overlay_game_state` to a copy of the payload, then compute the
   served validator.

A hit issues 3 SQL statements, and so does a 304. Serving never reads
`game_logs`, `fatigue_scores`, `pitchers`, availability, builders,
`bullpen_context` or legacy selection, and it writes nothing.

## Overlay rule for one stored game

The overlay is applied only when all of these hold:

1. A current row exists. If not, the frozen game is served and
   `schedule_overlay_row_missing` is added to `limitations`. The game is never
   removed.
2. The row's `game_date_et` still equals the edition's `baseball_date`. If not,
   the frozen game is served and `schedule_overlay_game_date_moved` is added.
3. The row's `last_synced` is strictly newer than the stored game's
   `state_as_of`. If not, the source is stale or identical, and the frozen game
   is served with no limitation.
4. The row changes a served fact: the public state (the TN-01 `game_state`
   mapping, reused) or `first_pitch_utc`. A refresh that only bumps
   `last_synced` changes nothing, so the served body and ETag stay stable.
5. The stored-to-current state transition is allowed (matrix below). If it is
   not, the frozen game is served and `schedule_overlay_conflict` is added.

When the overlay is applied, `state_as_of` becomes the row's `last_synced`: the
canonical schedule update time, never the request time.

### State transition matrix (stored → current)

| Stored \ Current | scheduled | live | final | postponed | suspended | uncertain |
| --- | --- | --- | --- | --- | --- | --- |
| scheduled | = | yes | yes | yes | yes | yes |
| uncertain | yes | yes | yes | yes | yes | = |
| live | conflict | = | yes | conflict | yes | yes |
| suspended | conflict | yes | yes | conflict | = | yes |
| postponed | conflict | conflict | conflict | = | conflict | conflict |
| final | conflict | conflict | conflict | conflict | conflict | = |

Terminal states never regress. `final` is final. `postponed` is not undone on
the same `game_pk`: a rescheduled game is a different edition's membership.
`live` and `suspended` never go back to `scheduled` or `postponed`. A delayed
game maps to `uncertain` through the existing mapping. No new public state is
added.

## Membership, first pitch, summary

- Membership and order are frozen. A new `game_pk` on the slate is never
  injected; new membership needs a new tonight_v1 publication. Games keep
  their stored order, even when first pitch moves.
- `first_pitch_utc` follows an official time change on the same `game_pk`,
  under the rules above.
- Summary: only `summary.games_by_state` is recounted from the served games.
  `game_count`, `team_state_counts`, `clubs_with_back_to_back_arms` and
  `change_count` stay frozen, and `quiet_day` still means `game_count == 0`.

## Delivery

- Identity headers (`X-BaseballOS-Snapshot-ID`, `-Sync-Run-ID`,
  `-Data-Through`, `-Contract`) still name the frozen trusted publication. No
  new header is added.
- Served validator (`served_validator`):
  - With no overlay difference, the served body is byte-identical to the
    stored body, and the ETag is the stored `content_sha256`, exactly as in
    TN-02.
  - Otherwise the ETag is `sha256(json(["tonight_v1_served_overlay_v1",
    content_sha256, sorted overlay identity]))`.
  - The overlay identity has one entry per overlaid game
    (`game_pk, 'overlaid', state, first_pitch_utc, state_as_of`) and one per
    limitation (`game_pk, 'missing' | 'moved' | 'conflict'`).
  - A different publication, or any served schedule difference, changes the
    ETag. The same logical overlay gives the same ETag.
- `Cache-Control: public, max-age=0, must-revalidate`, unchanged.
- `If-None-Match` equal to the served ETag returns 304 after the same 3
  statements. No builder runs, nothing is written, and neither `game_logs`
  nor `fatigue_scores` is read.
- No migration. Storage digest semantics are unchanged.

## Verification

- `backend/tests/test_tonight_v1_serving.py`: the TN-02 suite plus the TN-03
  matrix covering transitions, conflicts, stale sources, missing rows, moved
  dates, first pitch, unrelated games, doubleheaders, off-days, ETag
  stability and change, summary recount, and a production-shaped 3-game
  overlay with a 304 and mutation proof.
- `backend/tests/test_trusted_publication_rehearsal.py`: the Tonight v1
  rehearsal moves only `slate_games` through scheduled → live → final. It
  proves the served state follows, the stored row and digest are unchanged,
  the TeamSides are unchanged, the pointer is unchanged, and three ETags are
  distinct, all with zero `game_logs`/`fatigue_scores` reads.
