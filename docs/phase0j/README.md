# Phase 0J Starter Exposure Context

Phase 0J status: complete.

This document records Branch 1:
`phase-0j-starter-exposure-contract-verification`.
It also records Branch 2:
`phase-0j-starter-support-closeout`.

Branch 1 is the backend starter-exposure contract verification branch. Branch 2
is the frontend closeout branch. Together they complete Phase 0J.

## What Already Existed

- The Team Board and dashboard already served `rotation_support_pressure_v1`.
- The public window was seven days.
- A short start was already defined as fewer than five innings:
  fewer than 15 recorded outs, or 14 recorded outs or fewer.
- Existing game-shape logic separated normal starts, short starts,
  opener/bulk games, and bullpen games when complete game-log shape evidence
  was available.
- Phase 0D documented `team_game_pitching_splits` as the internal authority for
  team-game starter, reliever, split-validity, provenance, and calendar facts.

## Historical Attribution Defect

The served public starter-exposure path queried `game_logs` through the
pitcher's current `Pitcher.team_id` and `Pitcher.active` fields. A starter who
pitched for Team A and was later traded, optioned, placed inactive, or otherwise
reassigned could disappear from Team A's historical seven-day window.

That could silently change games analyzed, starter innings, average starter
length, short-start count, bullpen innings required, and the game-shape read.

## Branch 1 Correction

The public Team Board and dashboard starter-exposure path now uses:

- `scheduled_games` final team-game rows as the expected team-at-game window
  when available;
- stored `team_game_pitching_splits` rows keyed by `team_id` and `mlb_game_pk`
  for starter and bullpen arithmetic;
- reconciled game logs only to verify opener/bulk or bullpen-game shape when a
  split row alone cannot prove that distinction.

The public calculation no longer decides whether a historical team game belongs
to a team by filtering on the pitcher's current team or active status.

## Why The New Behavior Is Trustworthy

- Historical team inclusion comes from team-game rows, not current roster
  assignment.
- Expected final team games expose missing split rows instead of letting games
  disappear.
- Starter outs, bullpen outs, and total team outs come from stored split rows.
- Missing starter identity, missing split rows, unknown team-game attribution,
  partial source coverage, and unverified opener/bulk shape produce a Limited
  Read with typed reason codes.
- Unknown values are not counted as zero.
- No migration, production backfill, new endpoint, or sync rewrite is included.

## Definitions Frozen

- Window: seven days, inclusive of the reference date.
- Short start: fewer than five innings, meaning fewer than 15 recorded outs.
- Equivalent short-start threshold: 14 recorded outs or fewer.
- Completed-game posture remains in force.

## Limitations Contract

The served `rotation_support_pressure_v1` payload keeps existing compatibility
fields and adds a clearer backend contract:

- `limitations` is the unified served limitation list.
- `source_limitations` remains for compatibility.
- `limitation_reasons` carries typed reason codes for deterministic tests and
  downstream handling.
- `source_window` records whether the window came from scheduled final team
  games or split rows only.

The contract represents:

- insufficient trustworthy games;
- incomplete starter identification;
- incomplete historical team attribution;
- opener/bulk and bullpen-game handling limits;
- partial source coverage;
- no recent games.

## Founder Decisions Applied

- The public starter-exposure window remains seven days.
- Short start remains fewer than five innings.
- Public presentation should move to factual baseball language, not graded
  starter-support labels.
- `supportive`, `neutral`, `moderate_pressure`, and `heavy_pressure` are not
  added to the public BaseballOS dictionary.
- Recent Bullpen Work remains the canonical game-level receipts layer.
- The Team Board remains the canonical public home of starter-exposure context.
- Today may tease the context and link to the Team Board, but should not restate
  the complete read.
- `rotation_context` remains story-lane logic.
- The Phase 0D starter-exposure evidence family remains internal-only.
- A public league-wide starter-exposure strip is deferred.
- The Phase 0B public evidence gate remains closed.
- No probable-starter ingestion or forward-looking starter analysis is added.

## Remaining Frontend Closeout

Branch 2 completed the frontend closeout:

- public display of graded starter-support status labels was retired;
- the Team Board now renders factual recent starter-length language from games
  analyzed, average starter innings, short starts, bullpen innings covered, and
  the seven-day window;
- limited starter-length states render a quiet explanation instead of hiding;
- the Team Board starter-length read links into the existing Recent Bullpen Work
  receipts layer rather than duplicating game-level rows or calling another API;
- Today keeps starter-length context as a teaser toward the Team Board and does
  not restate the complete Team Board read;
- final public copy avoids public vocabulary for `supportive`, `neutral`,
  `moderate_pressure`, and `heavy_pressure`.

## Deferred Work

- No public league-wide starter-exposure strip in this branch.
- No probable-starter ingestion.
- No forward-looking rotation analysis.
- No production backfill.
- No sync-pipeline rewrite.
- No public Phase 0D evidence exposure.

## Tests Added Or Updated

- `backend/tests/test_rotation_support_split_window.py` freezes transaction,
  inactive, optioned/reassigned, zero-out, missing-starter, ambiguous-starter,
  insufficient-context, unknown-share, opener/bulk, bullpen-game, normal-start,
  short-start threshold, and partial-window behavior.
- Team Board and dashboard contract fixtures now seed scheduled final games and
  `team_game_pitching_splits` rows for starter-exposure assertions.
- Backend contract tests assert the served Team Board payload carries the
  split-backed source limitations and no longer carries current-assignment
  source wording for starter exposure.
- Frontend adapter and Team Board component tests freeze factual starter-length
  copy, limited-state copy, in-page receipts linking, and retirement of public
  graded starter-support vocabulary.
- Team Relief Work tests freeze the focusable Recent Bullpen Work anchor target.
- Today/Intelligence Surface tests freeze the starter-length teaser behavior and
  prevent raw starter-dependency detail from becoming the complete read.

## Known Limits

This branch does not rewrite how split rows are derived or backfill production
data. If the stored team-game split source cannot prove complete historical
attribution or cannot reconcile opener/bulk or bullpen-game shape, the public
read fails closed as a Limited Read instead of inferring from current roster
assignment.
