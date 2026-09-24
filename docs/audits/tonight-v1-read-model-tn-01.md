# Tonight v1 read model (TN-01)

Status: backend read model and immutable storage added; not served publicly
yet (legacy `tonight_v5` remains the public Tonight response until TN-02).

## What it is

`tonight_v1` is a game-oriented projection of **one** trusted Dashboard /
Team Board publication, plus the `slate_games` rows for that publication's
baseball date. Team Board owns bullpen truth; Tonight only rearranges it
around tonight's games. Builder: `backend/services/tonight_read_model.py`.

## Field authority

Every TeamSide field is read from the frozen `trusted_team_boards` package of
the selected snapshot, through the same validators Team Board serving uses.

| Field | Authority |
| --- | --- |
| team identity | package `by_team_id[id].team`; the governed club directory only when the club has no package |
| team_state | `team_board_snapshot_team_state.receipt_value` (snapshot-bound receipt). A package without receipts, or a missing/invalid receipt, is withheld; ShareArtifacts are never read |
| rest | frozen `rest_status` via `_frozen_rest_status_for_view`; unavailable → all counts `null`, never `0` |
| workload_7d | frozen workload overview `window_7` via `_frozen_workload_overview_for_view`; per-fact values only when that fact is `complete`, and the worst fact status is kept |
| multi_day_usage.three_in_four_count | count of Active Bullpen arms whose frozen `recent_usage_rest` `three_in_four` fact is complete and true; any incomplete arm makes the count `null` |
| key_arms | the exact Team Board Active Bullpen arm set (`_records_for_view` → `group_cards` → `team_board_v2._active_arms`) filtered to governed `trust_arm` then `bridge_arm`, name order, at most 3; pattern `B2B` (frozen back-to-back) or `3-in-4` (frozen fact) |
| rotation | frozen rotation impact via `_frozen_rotation_impact_for_view`; projected only when `short_start_count >= 1` |

No FatigueScore, GameLog, live roster, `current_availability_records`,
legacy `bullpen_context`, or candidate selection is read. Generation issues 4
queries in the test fixture (slate read, identity lookup, insert).

## Schedule and date

The edition's baseball date is the snapshot's `availability_reference_date`
(the date a data-through-yesterday publication describes before first pitch).
Slate membership is `slate_games.game_date_et` equal to that date. Games with a
non-MLB organization on either side are excluded with a limitation. Game state
is mapped once in `tonight_read_model.game_state` from `normalized_state` and
the MLB detailed status (postponed and suspended are distinguished; a cancelled
game that is not postponed reads `uncertain`). Order: known first pitch, then
unknown, then game number, then `game_pk`. A row without a first-pitch time is
kept with reason `first_pitch_time_unconfirmed`; note that schedule ingestion
currently skips MLB games that arrive without a time, so such rows only occur
if ingestion changes.

## Storage and immutability

New table `tonight_publications` (migration `c3e7a1d9f5b2`), unique on
`(reference_date, dashboard_snapshot_id, contract)`, indexed on each. A new
table rather than widening `tonight_intelligence_snapshots`: the legacy table
is keyed by `(reference_date, snapshot_version)` and overwritten in place, so
binding immutable per-publication rows there would require replacing its
unique constraint and mixing two write semantics in one table.

Rows are written once. `content_sha256` hashes the payload without
`edition.generated_at`. Rebuilding the same publication with identical content
reuses the row; different content raises `TonightPublicationConflict` and
leaves the row untouched; an ORM update of a stored row raises. A new trusted
snapshot for the same date gets its own row.

## Publication integration

`dashboard_snapshot.run_post_commit_snapshot_publication` (called once after
every committed trusted publication) now also runs the tonight_v1 projection,
gated by `TONIGHT_V1_PROJECTION_ENABLED` (on in `create_app`, env
`TONIGHT_V1_PROJECTION`). It never raises: a failure is logged, rolled back,
and leaves the publication, earlier tonight_v1 rows, and legacy Tonight alone.

## Temporary contract (later packages)

`lead` is `null`; `featured_game_pks`, `league_changes`, and every side's
`change_refs` are empty; `summary.change_count` is `0`; every card's
`context.sentence` is `null`; `quiet_day` means only `game_count == 0`.
Intraday game-state overlays, delivery headers, and the endpoint cutover are
not part of TN-01.

## Rollout note

The migration is additive. Production applies it at startup only in
`DATABASE_MIGRATION_MODE=owner`, or through the Production Maintenance
`migrate` operation (see `docs/current/PRODUCTION_MIGRATION_AUTHORITY.md`).
Until the table exists the projection hook fails non-fatally and publication
is unaffected.
