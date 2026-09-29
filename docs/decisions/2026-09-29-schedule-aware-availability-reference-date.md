# Schedule-Aware Availability Reference Date

Date: 2026-09-29

## Defect

On 2026-09-29 the Chicago Cubs at San Diego Padres matchup showed data through
Sep 27 and `Worked Yesterday: 2` for both clubs. There were no MLB games on
Sep 28. Sep 27 was each club's previous game, not yesterday.

## Root cause

Every bullpen rest fact is calendar arithmetic against one availability
reference date. `days_since_last_appearance`, `pitches_yesterday`,
`back_to_back`, 3-in-4 and the D-055 Rest Status counts all use calendar
arithmetic correctly. The reference date was wrong.

`product_availability_reference_date` was always `max(GameLog.game_date) + 1`
("a data set through June 7 describes the next availability read on June 8").
On a day with no games, `max(game_date)` does not move. So the Sep 29 daily sync
recalculated fatigue and published a snapshot anchored to Sep 28. Tonight then
rolled that snapshot forward to the Sep 29 edition (TN-11.8), and the matchup
paired Sep 29's game with Sep 28-anchored rest counts. A Sep 27 appearance was
`days_since_last_appearance == 1`, which counted as "worked yesterday".

The same assumption appeared in four more places:

- `sync.py` postgame candidate: `data_through = reference - 1`.
- Recent Usage & Rest: required `reference == data_through + 1`, and read
  `pitched_yesterday` and 3-in-4 / 4-in-6 as "appeared on `data_through`".
- `readiness_snapshot_freshness`: `availability_reference_date = data_through + 1`.
- `trusted_slate_reference_dates` callers that reread a snapshot (Team State
  readiness, Team State card metrics, the vNext proof): recomputed
  `data_through + 1` instead of reading the snapshot's own date.

## Sources of truth

- **Schedule / off-days:** `scheduled_games` (per team, MLB `officialDate`,
  normalized `status_state`, doubleheaders, postponements, resumed linkage).
- **Appearances:** `game_logs` (`game_date`, pitch counts, outs).
- **Snapshot dates:** `DashboardSnapshot.data_through` (latest ingested
  workload) and `availability_reference_date` (the day the read describes).
  Both are frozen at publication and never mutated.

## Decision

`services.availability_reference_date.schedule_aware_availability_reference_date`
is the one authority for the availability reference date.

- It starts at `data_through + 1`.
- It advances one calendar day at a time, never past an explicit as-of product
  day.
- It advances only across dates that `scheduled_games` confirms were league-wide
  no-game dates:
  - no row other than a postponed game on that date; and
  - rows exist on a later date, which proves the ingested window covered it.
- It stops at any other gap date:
  - a final game there means data lag (played but not ingested);
  - a scheduled, live, suspended or unknown game is unresolved.

  When it stops, the read keeps its own honestly labelled earlier date. It never
  claims a recovery day it cannot prove.

The as-of day is explicit and never read from the wall clock at read time:

- **Fatigue recalculation:** the product day the batch is written in. Every
  score in a batch carries one `calculated_at`.
- **Reads** (`build_sync_status_payload`, and through it the snapshot freshness
  block and every API): the product day of `latest_fatigue_calculated_at`.

Stored `days_since_last_appearance` and the published availability date
therefore always describe the same day. A historical rebuild resolves the same
date on any machine and on any date.

Downstream consumers use that one date:

- **FatigueScore and availability inputs:** anchored on the resolved date.
- **D-055 Rest Status:** counts `days_since == 1` as "worked yesterday",
  relative to the resolved date.
- **Recent Usage & Rest:** windows and patterns end on `reference - 1`, the true
  previous calendar day. Schedule-confirmed gap days are covered, no-appearance
  days. When `reference == data_through + 1`, output is byte-identical to before.
- **Snapshot rereads:** these pass the snapshot's stored
  `availability_reference_date` to `trusted_slate_reference_dates`. The Team
  State card and the readiness sync-status anchor follow it.
- **Tonight:** a rollover edition whose baseball date differs from the
  snapshot's availability date withholds rest, 3-in-4 and key-arm rest patterns
  with `rest_reference_date_mismatch`. It never relabels them. Team State, 7-day
  workload and rotation stay as published.
- **Matchup:** withholds only the rest domain with `rest_reference_date_mismatch`
  when the game's date differs from the publication's availability date.
  Manual comparison, which has no game date, is unchanged.

Definitions preserved:

- **Back-to-back:** appearances on two consecutive calendar dates within the
  five-day window, per `BULLPEN_AVAILABILITY_ENGINE_V1`. It is never inferred
  from consecutive team games.
- **3-in-4 and 4-in-6:** calendar windows that must include the previous
  calendar day.

## Migration and history

- No schema change.
- Published snapshots, sidecars and Tonight rows are immutable and are not
  touched.
- A snapshot published before this change keeps its stored date. Readers show it
  under that date, or withhold it on a date mismatch.

## Tests

- `backend/tests/test_schedule_aware_day_context.py` covers:
  - consecutive games, one or several off-days, doubleheaders,
    postponed/rescheduled games, data lag and the current day;
  - that results do not depend on the wall clock;
  - mixed team schedules, availability recovery and What Changed across an
    off-day;
  - a synthetic Sep 29 Cubs-at-Padres production fixture, before and after the
    fix.
- Tonight rollover and Matchup date-guard cases are in
  `test_tonight_v1_read_model.py` and `test_current_bullpen_comparison.py`.
