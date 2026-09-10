# 2026 unresolved appearance-team repair

## Production finding

Foundation 3A local-only aggregation found one explicit unresolved 2026 appearance:

- GameLog id: 41040
- MLB gamePk: 824262
- Official game date: 2026-06-23
- Pitcher id: 218
- Stored status: `unresolved`
- Stored reason: `appearance_team_unresolved`

The Foundation 2 historical backfill correctly did not touch it because that contract targets only legacy NULL rows and explicitly excludes already-unresolved rows. A normal June 23 postgame replay also left it unchanged because the completed-game marker already represented the slate and did not reopen the row for authority-only correction.

## Decision

Add a one-row governed repair that:

1. Requires the exact GameLog id, gamePk, and official game date.
2. Requires the row to still be an explicit unresolved 2026 record with no team id.
3. Loads the pitcher's stable MLB id but never reads the pitcher's mutable current team.
4. Fetches the official MLB box score and requires exactly one matching pitching line.
5. Requires a valid home/away side and consistent official team identities.
6. Reuses the Foundation 1 schedule/box-score authority resolver.
7. Produces a deterministic SHA-256 plan fingerprint in dry-run mode.
8. Applies only with the exact confirmation phrase and approved fingerprint.
9. Locks and revalidates the target immediately before writing.
10. Writes only the four `appearance_team_*` columns and commits one row.

## Scope

This does not reopen the Foundation 2 campaign, change the canonical aggregation, alter pitching statistics, add a migration, change public surfaces, rankings, Team State, Share Cards, Foundation 3B, or SC-05.

## Required production sequence

1. Run the repair workflow in `dry_run` mode and review the official team, side, source, and fingerprint.
2. Run it in `apply` mode with the exact confirmation phrase and approved fingerprint.
3. Re-run the Foundation 1 appearance-team production audit and require 2026 unresolved = 0 and resolved = 13016.
4. Re-run Foundation 3A local-only and require PASS.
5. Run Foundation 3A official validation only after the local-only gate passes.
