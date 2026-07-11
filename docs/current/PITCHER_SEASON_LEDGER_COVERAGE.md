# Pitcher Season Ledger Coverage

Pitcher season ledger coverage proves one narrow claim: for a pitcher, regular
season, and target game, BaseballOS has reconciled the exact MLB game-log
appearance set through that target against stored `game_logs` rows.

The proof compares normalized tuples:

```text
(mlb_game_pk, game_date, games_started)
```

Counts are stored as diagnostics, but counts alone do not authorize public
starter-assignment prose. The source and stored manifest fingerprints must
match, and the coverage status must be `complete`.

## What It Guarantees

- The target game is present in the MLB game-log source manifest.
- Every finalized regular-season appearance through that target is present
  locally.
- Each compared appearance has a known `gamesStarted` value.
- Missing relief appearances, missing intervening starts, wrong game IDs, and
  wrong start/relief classifications fail closed.

## What It Does Not Guarantee

- Career-first-start claims.
- First-start-for-team claims.
- Managerial intent.
- Injury, opener, or spot-start explanations.
- Postseason or spring-training coverage in V1.

## Operator Command

Backfill requires `scheduled_games` coverage for the same historical window,
because statusless MLB game-log splits are finality-gated through the stored
schedule ledger. Populate that first when the local database does not already
have the window:

```powershell
python scripts\ingest_schedule.py --start-date 2026-03-30 --end-date 2026-07-09 --source starter_assignment_coverage
```

Dry run:

```powershell
python scripts\backfill_pitcher_game_logs.py --season 2026 --through-date 2026-07-09 --source starter_assignment_coverage
```

Apply:

```powershell
python scripts\backfill_pitcher_game_logs.py --season 2026 --through-date 2026-07-09 --source starter_assignment_coverage --apply
```

Optional single-pitcher verification:

```powershell
python scripts\backfill_pitcher_game_logs.py --season 2026 --through-date 2026-07-09 --source starter_assignment_coverage --pitcher-mlb-id 621112 --apply
```

## Failure Behavior

Coverage status is `complete`, `incomplete`, or `unknown`. Only `complete`
authorizes starter-assignment prose. Missing game IDs, missing dates, unknown
`gamesStarted`, unresolved finality, source/stored manifest mismatch, and stale
stored manifests all suppress the narrative.

The public endpoint does not expose coverage fingerprints, status, or reason
codes.

## Corrections

Daily sync and the backfill command rebuild coverage from the current MLB
game-log source response. Public reads also recompute the current stored
manifest fingerprint for the target before authorizing prose, so a later
`game_logs` correction cannot leave an old complete marker authorizing a stale
historical claim.
