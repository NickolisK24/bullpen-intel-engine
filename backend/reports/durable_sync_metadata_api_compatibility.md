# Durable Sync Metadata API Compatibility

## Scope

This audit reviews whether `/api/bullpen/sync/status` remains compatible with
existing dashboard consumers while exposing durable sync metadata.

Endpoint reviewed:

```text
GET /api/bullpen/sync/status
```

## Backward-Compatible Fields

The response preserves existing top-level and nested fields:

| Field | Status |
| --- | --- |
| `status` | Preserved |
| `last_sync` | Preserved |
| `pitchers_updated` | Preserved |
| `new_logs_added` | Preserved |
| `errors` | Preserved |
| `message` | Preserved |
| `finished_at` | Preserved |
| `data.game_logs` | Preserved |
| `data.latest_game_date` | Preserved |

## Additive Fields

The response adds durable metadata fields:

| Field | Purpose |
| --- | --- |
| `last_successful_sync` | Latest successful durable sync completion timestamp. |
| `data.latest_workload_date` | Latest workload date represented by the data. |
| `data.latest_fatigue_calculated_at` | Latest fatigue calculation timestamp. |
| `freshness.is_current` | Whether data is current for the configured freshness window. |
| `freshness.label` | Human-readable freshness summary. |
| `freshness.limitations` | Trust-first limitations and caveats. |
| `sync` | Latest sync-run metadata. |
| `last_successful_sync_run` | Latest successful sync-run metadata. |

## Status Values

Existing dashboard code accepts both legacy and durable status values:

| Status Family | Values |
| --- | --- |
| Success | `success`, `ok` |
| Failure | `failed`, `error` |
| No metadata | `never`, `metadata_unavailable` |

The durable implementation uses `success` and `failed` for persisted run states.
Consumers that compare exact string values should accept the durable values
before deployment.

## Compatibility Examples

Successful durable sync:

```json
{
  "status": "success",
  "last_sync": "2026-06-01T21:39:12",
  "last_successful_sync": "2026-06-01T21:39:56",
  "data": {
    "game_logs": 35768,
    "latest_game_date": "2026-05-31",
    "latest_workload_date": "2026-05-31",
    "latest_fatigue_calculated_at": "2026-06-01T21:39:55"
  },
  "freshness": {
    "is_current": true,
    "label": "Current baseball data through 2026-05-31.",
    "limitations": []
  }
}
```

Metadata unavailable with data coverage:

```json
{
  "status": "metadata_unavailable",
  "last_sync": null,
  "last_successful_sync": null,
  "data": {
    "game_logs": 35768,
    "latest_game_date": "2026-05-31"
  },
  "freshness": {
    "is_current": true,
    "limitations": [
      "Sync metadata unavailable; data coverage is based on game logs."
    ]
  }
}
```

## Dashboard Consumers Reviewed

| Consumer | Compatibility Finding |
| --- | --- |
| `frontend/src/components/dashboard/SyncStatus.jsx` | Uses the view helper and supports durable, failed, unavailable, and empty states. |
| `frontend/src/components/dashboard/Dashboard.jsx` | Uses `last_successful_sync` first, then falls back to legacy successful `last_sync`. |
| `frontend/src/utils/api.js` | Endpoint path unchanged. |

## Risk Assessment

The endpoint change is additive for the dashboard. The only compatibility risk is
external or future internal consumers that require exact legacy status strings.
No such consumer was found in the current frontend.

## Readiness Verdict

```text
PASS_WITH_COMPATIBILITY_NOTE
```
