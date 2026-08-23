# Intraday exact-date transaction roster repair

Date: 2026-08-22
Status: Accepted

## Decision

The governed intraday roster repair runs a dedicated current-window transaction
lane before its ordinary roster-assignment `no_change` exit. The lane repairs
only stored transactions that already have canonical pitcher identity,
pitcher-relevant participant authority, a governed event category, exact
transaction date and endpoint-team authority, and the typed blocker
`roster_snapshot_missing`.

For those rows, BaseballOS groups MLB endpoint requests by exact transaction
date and team, reads the canonical four roster views, and persists a snapshot
only when the official source explicitly contains the participant on exactly
one transaction endpoint. The canonical roster normalizer and missing-snapshot
writer remain the source of roster-status semantics and conflict protection.
The stored transaction is then re-aligned through the existing alignment rule,
with standard transaction correction provenance.

The production workflow enables this lane explicitly through
`--repair-transaction-roster-evidence`. Ordinary intraday behavior remains
unchanged when the flag is absent. A source-fetch failure makes the enabled lane
fail visibly. A source omission or conflict withholds only the affected row.

## Bounded population

The selector is limited to the latest successful or partial governed
transaction source window. It excludes unknown events, non-pitchers, unlinked
participants, historical windows, rows already carrying an exact snapshot, and
typed team-mismatch cases. Requests scale with unique exact-date MLB endpoint
pairs in that bounded candidate population, not with league rosters or season
history.

## Historical integrity

Transaction-time `from_team_id` and `to_team_id` remain the only ownership
authority. `Pitcher.team_id`, current roster state, descriptions, and nearest
prior or next snapshots are never used. Existing wrong-team or structurally
conflicting snapshots are not overwritten. No published Team Board package,
Share Artifact, delta sidecar, or frozen historical snapshot is rewritten.

## Publication and lifecycle

If the transaction lane produces no correction and the ordinary roster audit is
`no_change`, the intraday run records success without forcing publication. If a
transaction becomes aligned, the existing intraday refresh and publication
proof path runs; no publication bypass is added. Natural transaction windows
and normal correction provenance own lifecycle. This decision authorizes no
historical replay or bespoke backfill.

## Explicit non-goals

- wrong-team snapshot correction;
- nearest-date evidence;
- broad historical roster replay;
- event-taxonomy changes, including SFA, SC, or generic ASG;
- participant or canonical-pitcher qualification changes;
- current roster, Off-Active Count, workload, Rotation Impact, or frontend
  semantics.
