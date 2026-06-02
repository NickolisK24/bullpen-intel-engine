# API Freshness Payload Audit

Audit date: 2026-06-02 UTC

## Endpoints Reviewed

| Endpoint | Freshness fields | Current public values | Consumers |
| --- | --- | --- | --- |
| `GET /api/bullpen/sync/status` | `last_sync`, `status`, `finished_at`, `pitchers_updated`, `data.game_logs`, `data.latest_game_date` | `last_sync: null`, `status: never`, `game_logs: 35768`, `latest_game_date: 2026-05-31` | Dashboard sync pill, SeasonBanner, risk distribution through label |
| `GET /api/bullpen/stats/overview` | `availability_summary.mode`, `availability_summary.is_current_availability`, `availability_summary.data_state` | current availability, 428 fresh, 251 stale | Dashboard overview and availability summary |
| `GET /api/bullpen/fatigue?limit=750&include_stale=true&with_meta=true` | `meta.latest_game_date`, `meta.active_cutoff_date`, `meta.fresh_filtered_pitchers`, `meta.stale_filtered_pitchers`, row `calculated_at`, `availability.inputs.latest_game_date` | `latest_game_date: 2026-05-31`, `active_cutoff_date: 2026-05-19`, `fresh: 428`, `stale: 251`, max `calculated_at: 2026-06-01T21:39:55.153933` | Bullpen page, dashboard top-fatigue card, empty-state metadata |
| `GET /api/bullpen/fatigue/snapshot` | `meta.snapshot_date`, `meta.mode`, `meta.is_current_availability`, `meta.reference_strategy` | Public endpoint returned 401 without admin token | Admin/development validation only |

## Public `/sync/status` Payload

```json
{
  "data": {
    "game_logs": 35768,
    "latest_game_date": "2026-05-31"
  },
  "last_sync": null,
  "message": "No sync has run yet.",
  "pitchers_updated": 0,
  "status": "never"
}
```

## Public `/stats/overview` Freshness Summary

| Field | Value |
| --- | --- |
| Total pitchers | 728 |
| Scored pitchers | 679 |
| Total game logs | 35,768 |
| Availability mode | current_availability |
| Current availability | true |
| Fresh classifications | 428 |
| Stale classifications | 251 |

## Public `/fatigue` Metadata

| Field | Value |
| --- | --- |
| `meta.latest_game_date` | 2026-05-31 |
| `meta.active_cutoff_date` | 2026-05-19 |
| `meta.total_scored_pitchers` | 679 |
| `meta.fresh_filtered_pitchers` | 428 |
| `meta.stale_filtered_pitchers` | 251 |
| Max sampled `calculated_at` | 2026-06-01T21:39:55.153933 |
| Max sampled `availability.inputs.latest_game_date` | 2026-05-31 |

## API Audit Conclusion

Dashboard-related APIs expose current workload data and data-through dates, but
the public sync-status endpoint does not expose the latest successful sync
timestamp. The inconsistency is isolated to sync metadata, not workload data.
