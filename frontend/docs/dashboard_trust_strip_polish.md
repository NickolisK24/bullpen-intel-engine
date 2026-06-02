# Dashboard Trust Strip Polish

## Scope

This polish changes only dashboard trust and freshness presentation. It does not
change sync logic, fatigue scoring, availability classification,
recommendations, APIs, or database schema.

## Before

The dashboard hero displayed the season badge and sync metadata in the same
compact row:

```text
LIVE - 2026 SEASON
Synced: June 1, 2026
Data Through: May 31, 2026
428 refreshed
```

The information was correct, but the trust signals were visually compressed and
easy to scan past.

## After

The hero now keeps the season badge focused on platform context, while a
dedicated trust strip sits directly below the hero:

```text
DATA STATUS: HEALTHY

Synced:
June 1, 2026

Data Through:
May 31, 2026

Refresh Coverage:
428 Pitchers Refreshed
```

The strip also supports lower-trust states without hiding data:

```text
DATA STATUS: LIMITED
Sync metadata: Unavailable
Data Through: May 31, 2026
Refresh Coverage: Not reported
```

```text
DATA STATUS: STALE
Synced: May 30, 2026
Data Through: May 31, 2026
Refresh Coverage: 429 Pitchers Refreshed
```

## Layout Rationale

- The trust strip is full-width within the dashboard content column so it reads
  as operational context for the entire dashboard, not as a small badge.
- It uses the existing BaseballOS palette: dugout/chalk surfaces, dirt borders,
  pine for healthy, amber for limited or stale, and red for failed sync states.
- It stays compact and information-dense: one status marker, three short
  metrics, and an optional helper line.
- It remains visually subordinate to the hero and avoids large-card treatment,
  motion, or high-saturation styling.

## Trust Messaging Rationale

The strip separates four trust questions:

| Question | Strip Field |
| --- | --- |
| Is the platform data state healthy, limited, or stale? | `DATA STATUS` |
| When was the system last synced? | `Synced` or sync-state label |
| What baseball data date does the dashboard represent? | `Data Through` |
| How much workload data was refreshed? | `Refresh Coverage` |

The health label is derived only from existing sync status, freshness metadata,
and limitation fields:

- `Healthy`: successful, current sync metadata with no freshness limitation.
- `Limited`: failed, unavailable, missing, or freshness-limited metadata.
- `Stale`: successful sync metadata older than the existing freshness target.

No new business logic or backend data source is introduced.

## Responsive Behavior

- Desktop: status marker and three trust metrics render in one compact row.
- Tablet: the strip keeps the same hierarchy while allowing the metric row to
  wrap within the available width.
- Mobile: the strip stacks the status and metrics vertically, preserving label
  and value pairing without horizontal scrolling.

## Validation Notes

Frontend tests cover:

- healthy trust strip rendering
- stale trust strip rendering
- metadata-unavailable fallback rendering
- failed sync with preserved data-through date
- successful sync without a data-through date
- no metadata and no data

Local browser validation covered desktop, tablet, and mobile widths.
