# Tonight v1 date rollover (TN-11.8)

## Production bug

After the Sep 29 manual recovery, production was in this state:

- The trusted Dashboard publication was snapshot 4094 (`data_through`
  2026-09-27, `availability_reference_date` 2026-09-28).
- The only `tonight_v1` row was `(2026-09-28, 4094)` with `game_count` 0.
- `slate_games` already held the four Sep 29 Wild Card games.

So the site presented Sep 28 as "No MLB games are on tonight's slate".

## Root cause

Tonight's baseball date was derived only from the Dashboard snapshot:

- The builder and generator dated the edition with
  `snapshot.availability_reference_date`.
- TN-11.7's operational ensure (`ensure_tonight_v1_for_publication`) did the
  same.
- Serving selected `(snapshot.availability_reference_date, snapshot)`.

When the calendar moves on while the trusted bullpen publication stays current,
nothing could create, or select, the new day's edition. The morning schedule
refresh updated `slate_games` but could only reuse the Sep 28 row.

## Authority model

| Question | Authority |
| --- | --- |
| Which bullpen state is authoritative? | The current trusted (published, ready) Dashboard snapshot. |
| Which MLB day is presented? | The BaseballOS product day, i.e. the Eastern calendar date. Governed runs use `context.scheduled_for` in ET; serving uses `product_current_date()`. |

Tonight identity stays `(reference_date, dashboard_snapshot_id, contract)`. No
schema change was needed: the existing unique constraint already allows one
snapshot to own an immutable edition per date.

A rolled-forward row:

- presents `reference_date`, which is `edition.baseball_date`;
- keeps the snapshot's own `availability_reference_date` and `data_through`
  (in the row and in the edition);
- keeps the snapshot's frozen Team Board package.

The Dashboard snapshot is never republished, re-dated or mutated.

## Changes

| Area | Before | After |
| --- | --- | --- |
| `build_tonight_v1` / `generate_tonight_v1_for_snapshot` | Dated by the snapshot. | Optional explicit `reference_date`. The publication-time output is byte-identical (the default is the snapshot date). |
| `ensure_tonight_v1_for_date(snapshot, reference_date, *, source)` (new) | none | See the behavior list below. |
| Serving | `(snapshot.availability_reference_date, snapshot)` | `(product_current_date(), snapshot)`. Yesterday's edition is never served on a new day. A missing current-date row fails closed (`tonight_v1_publication_missing`). The identity check accepts rollover rows: row date equals the requested date, and the availability date matches the snapshot's. |
| Morning (natural) | Schedule refresh, then reuse of the snapshot-date row. | Schedule refresh for the intended ET date, then ensure that date's edition. The result reports `tonight_edition` with `schedule_date`, `trusted_snapshot_id`, `tonight_publication_id`, `reference_date`, `status` and `game_count`. |
| Daily / Postgame | Ensure the publication-date row. | Keep the publication-date ensure (reported as `publication_edition`) and also ensure the intended ET date's edition. Still reported only; it never gates sync success (TN-11.7). |
| `recovery_morning` (new dispatch mode) | none | See the list below. |
| Footer copy | "Every game above links…" rendered on zero-game days. | Rendered only when games render. "Browse Team Boards" remains. |

`ensure_tonight_v1_for_date` behaves as follows:

- It requires a published, ready snapshot and a `date`.
- It honors the projection off-switch.
- It reuses the exact stored row unchanged, or creates it exactly once.
- It never overwrites, and never builds or compares another date.
- It never raises.
- It logs one line of the form
  `tonight_v1 date ensure … status=created|reused … legacy_tonight_v5=not_generated`.

`recovery_morning` works like this:

- It runs the same morning path under `execution_source=incident_recovery`.
- It keeps the existing recovery governance: `scheduled_for`,
  `recovery_reason`, `confirm_recovery=RECOVER`, the operator, and the
  production dispatch, ref and repository checks.
- It takes the public writer lock.
- It never runs Daily or Postgame ingestion and never publishes.
- A morning recovery skips the "already satisfied" short-circuit. The run is
  idempotent, and the natural morning may have executed before the fix it
  recovers from.

## Lane dates

| Lane | `scheduled_for` (UTC) | Tonight date (ET) |
| --- | --- | --- |
| Daily | 10:05 / 10:17 | same day |
| Morning | 14:05 / 14:23 | same day |
| Postgame | 02:05–02:11 | the previous ET day (22:xx ET) |
| Postgame | 04:05–04:11 / 06:05–06:11 | the new ET day (00:xx / 02:xx ET) |

During daylight time, the first post-midnight postgame window rolls the
current trusted publication forward into the new day's edition. Daily's
publication then creates the new snapshot's own edition, and serving follows
the new snapshot.

## Operations after deploy

Run the `BaseballOS Bullpen Sync` workflow (`workflow_dispatch`) with:

- `mode=recovery_morning`
- `scheduled_for=<current Sep 29 UTC instant>`, for example
  `2026-09-29T16:00:00Z`
- `recovery_reason="TN-11.8: Tonight still on Sep 28 while Sep 29 Wild Card slate is current"`
- `confirm_recovery=RECOVER`

Expected:

- `publication_proof.tonight_v1.status=created`, with
  `reference_date=2026-09-29`, `dashboard_snapshot_id=4094` and `game_count=4`.
- The Sep 28 row is unchanged.
- The Tonight endpoint serves Sep 29 with "Data through Sep 27".

## Limitations

- Between ET midnight and the first operational run of the new day, today's
  edition may not exist yet, and serving fails closed rather than showing
  yesterday. In daylight time that run is the 04:05 UTC postgame window, about
  five minutes. In standard time it is up to about an hour.
- A rolled-forward edition presents the new day's schedule with the frozen
  bullpen state of the trusted publication. The edition shows its
  `data_through`, and the next Daily publication supersedes it.
