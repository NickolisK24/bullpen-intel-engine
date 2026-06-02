# Durable Sync Metadata Frontend Fallbacks

## Scope

This audit reviews dashboard rendering behavior for durable sync metadata,
partial metadata, missing metadata, and failed syncs.

Files reviewed:

```text
frontend/src/components/dashboard/SyncStatus.jsx
frontend/src/components/dashboard/syncStatusView.js
frontend/src/components/dashboard/Dashboard.jsx
frontend/tests/syncStatus.test.mjs
```

## Rendering States

| State | Expected UI | Coverage |
| --- | --- | --- |
| Successful sync with data date | `Synced` and `Data Through` both visible. | Frontend test coverage. |
| Successful sync without data date | `Synced` visible; `Data Through` omitted instead of showing a false date. | Added frontend test coverage. |
| Metadata unavailable with data date | `Sync metadata: Unavailable` and `Data Through` both visible. | Frontend test coverage. |
| Failed latest sync with data date | `Last sync failed` and preserved `Data Through` visible. | Frontend test coverage. |
| No metadata and no data | `No data loaded`. | Frontend test coverage. |

## Trust-First Behavior

The dashboard now distinguishes:

```text
Synced: June 1, 2026
Data Through: May 31, 2026
```

If durable sync metadata is unavailable but baseball data exists, the dashboard
does not imply that no sync has ever occurred. It shows:

```text
Sync metadata: Unavailable
Data Through: May 31, 2026
```

If the latest sync fails, the dashboard preserves data coverage and shows the
failed attempt separately.

## Dashboard Integration Finding

`Dashboard.jsx` prefers `last_successful_sync` when deciding whether the season
is live. It falls back to legacy successful `last_sync` only when the response
status is `success` or `ok`.

This preserves compatibility while avoiding the previous confusion between sync
timestamp and baseball data coverage.

## Mobile and Layout Risk

This audit did not introduce additional layout changes. The sync indicator uses
the existing dashboard component structure. No horizontal-overflow risk was
identified from the metadata label changes.

## Readiness Verdict

```text
PASS
```
