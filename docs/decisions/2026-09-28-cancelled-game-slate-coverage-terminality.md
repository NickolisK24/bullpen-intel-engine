Decision: Cancelled Game Slate Coverage Terminality

Date: September 28 2026. Incident: Daily Primary candidate 3954
(`data_through` 2026-09-27) was withheld with
`dashboard_snapshot_slate_coverage_incomplete`. MLB cancelled game 823490
(raw statusCode `CR`), and it was stored as `status_state='other'`.

## Decision

An authoritative MLB cancellation is a terminal, never-played game for slate
coverage. `backend/services/slate_coverage.py` may exclude it from the finality
and postgame-marker requirements. That is the only frozen path this decision
changes.

A cancelled game is never counted as final. It is counted in
`games_cancelled`, reported in `cancelled_game_pks`, and marked by the
non-blocking evidence code `cancelled_games_excluded`. No stored schedule row
is rewritten, and no marker or game log is fabricated.

## Evidence required

Cancellation needs positive evidence, re-classified through the existing
`game_finality.classify_status` authority. There is no new status vocabulary
and no fuzzy match of our own. All of the following must hold:

1. Every `scheduled_games` row for the game stores `status_state='other'`.
2. Those rows carry one agreeing, non-empty raw `status_code`.
3. Suspended or resumed linkage is resolved.
4. The `slate_games` row exists for the same `game_pk` with the same raw
   `status_code`. The same schedule ingest writes both ledgers from one MLB
   payload.
5. That row's raw MLB status (`statusCode`, `detailedState`,
   `abstractGameState`) classifies as `cancelled`.

## Unchanged

- `other` without cancellation evidence still blocks. That includes live
  games, unknown codes, a missing `slate_games` row, disagreeing codes and
  unresolved linkage.
- Suspended, scheduled and postponed handling is unchanged.
- Final games still require a fully processed postgame marker.
- The zero-row branch, the publication gate, Team State proof, artifact gates,
  the canonical modules `game_finality.py` and `dashboard_snapshot.py`, and the
  schema are unchanged. No migration is added.
