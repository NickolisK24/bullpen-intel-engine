# Cancelled game slate coverage (2026-09-27 incident)

## Incident

The 2026-09-28 Daily Primary withheld candidate snapshot 3954
(`data_through` 2026-09-27, `availability_reference_date` 2026-09-28) with
`dashboard_snapshot_slate_coverage_incomplete`.

- Every 2026-09-27 candidate was withheld. The published pointer stayed on
  snapshot 3896 (`data_through` 2026-09-26).
- The 2026-09-28 off-day was not involved. The gate evaluates the
  `data_through` slate only, and a verified empty date was already
  publishable.

The stored coverage for 3954 showed:

- `games_scheduled` 15, `games_final` 14, `games_fully_ingested` 14,
  `games_incomplete` 1.
- `reason_codes`: `scheduled_games_not_final`, `completeness_unknown`,
  `validations_failed`.

The outlier was game 823490 (teams 110 / 147). MLB cancelled it (raw statusCode
`CR`), and both `scheduled_games` rows stored `status_state='other'`.

## Root cause: an authority inconsistency

| Layer | Treatment of an MLB cancellation |
| --- | --- |
| `game_finality.classify_status` | Decision `cancelled` (detailedState contains "cancel", or statusCode `C`). Stored `status_state='other'`. |
| `schedule_authority.normalize_slate_state` | `slate_games.normalized_state='cancelled'` (terminal). |
| `game_ingestion_planner` | `other` → `EXCLUDED_CANCELLED` (terminal; no unresolved finality). |
| `slate_coverage.compute_slate_coverage` (before) | `other` counted as a non-final included game → validations failed → the publication gate withholds forever. |

A cancellation never becomes final, so the slate could never publish.

`scheduled_games` has no detailedState column, so `other` alone cannot
distinguish cancelled from live or unrecognized.

## Fix: cancelled is terminal non-played, proven by evidence

There is no migration and no rewrite of any stored state.

- `game_finality.is_cancelled_status(status)` is the one predicate. It is True
  only when the existing `classify_status` authority returns `cancelled`.
- `slate_coverage` marks a game cancelled only when all of the following hold:
  1. Every `scheduled_games` row for the game is `other`.
  2. Those rows carry one agreeing, non-empty raw `status_code`.
  3. Resumed linkage is resolved.
  4. The `slate_games` row exists for the same `game_pk` with the same raw
     `status_code`. The same `ingest_games` call writes both ledgers from one
     MLB payload.
  5. `is_cancelled_status` returns True for that row's raw MLB status
     (`statusCode`, `detailedState`, `abstractGameState`).
- Cancelled games are excluded from `games_included`, the finality checks and
  the postgame-marker requirement. They are counted in `games_cancelled`, never
  in `games_final`.
- The payload adds `games_cancelled` and `cancelled_game_pks`, plus the
  evidence code `cancelled_games_excluded` (not a blocker). Diagnostics no
  longer list a cancelled game as non-final.
- `dashboard_snapshot` logs one line per candidate when a cancellation was
  excluded.

Everything else is unchanged:

- `other` without that evidence still blocks. That covers a bare unknown code,
  live, a manager challenge, a missing `slate_games` row, disagreeing codes and
  unresolved linkage.
- Suspended and scheduled games still block.
- Postponed exclusion is unchanged.
- Final games still require a fully processed marker.
- The zero-row branch is not touched.

For the 2026-09-27 shape:

- `games_final` 14, `games_cancelled` 1, `games_included` 14,
  `games_incomplete` 0.
- `reason_codes`: `slate_complete`, `cancelled_games_excluded`.
- The gate passes.

## Recovery

Do not edit snapshot 3954, flip 823490, or insert a marker. After deploy, a
normal governed Daily recovery rerun builds a fresh candidate under the
corrected coverage.
