# Freshness Regression Assessment

Audit date: 2026-06-02 UTC

## Expected Behavior

Docs and code expect the dashboard sync pill to show:

- `Last synced: <timestamp>` when a successful sync status exists.
- `Snapshot · through <latest_game_date>` when data exists but no sync has run.
- `Last sync failed` when the latest sync status is an error.
- `No data loaded` when neither sync metadata nor game logs exist.

## Current Public Behavior

The public API shows:

| Signal | Value |
| --- | --- |
| Latest successful GitHub Actions sync | 2026-06-01T21:39:56Z |
| Latest fatigue calculation | 2026-06-01T21:39:55.153933 |
| Latest game date | 2026-05-31 |
| Public `/sync/status.last_sync` | null |
| Public `/sync/status.status` | never |
| Dashboard label selected by current code | `Snapshot · through May 31, 2026` |

## Regression Checks

| Question | Finding | Result |
| --- | --- | --- |
| Did data freshness regress? | No. Public data includes May 31 game logs and fatigue calculations from June 1. | No data regression found |
| Did sync execution regress? | No evidence of sync failure. Latest public workflow run succeeded. | No sync failure found |
| Did metadata regress? | Yes. Dashboard-readable sync metadata is absent despite a successful sync and updated DB data. | Metadata issue found |
| Did UI labeling regress? | The UI branch is working as coded, but it falls back because metadata is missing. | Secondary clarity issue |
| Is snapshot metadata being shown instead of sync metadata? | The label uses `data.latest_game_date`, not `/fatigue/snapshot` metadata. | No snapshot-mode leak found |

## Assessment

The system is not losing workload data. The dashboard is communicating poorly
because the sync timestamp is missing from the public `/sync/status` response.
That endpoint currently presents the system as `never` synced even though the
database and GitHub Actions evidence show a successful June 1 sync.

## Regression Status

`METADATA_ISSUE`
