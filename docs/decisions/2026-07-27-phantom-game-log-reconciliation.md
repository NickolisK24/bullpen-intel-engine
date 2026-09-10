# Phantom GameLog reconciliation and zero-out ingestion authority

## Production finding

Foundation 3A identified one explicit unresolved 2026 row: GameLog `41040`, Kenley Jansen (`mlb_id=445276`), game `824262`, June 23, 2026. The private identity diagnostic proved that the final official box score contained eight pitching identities, did not contain Jansen, and contained no exact pitching-stat match for the stored all-zero row.

The row is therefore not eligible for team attribution. Assigning either Detroit or New York would turn a non-appearance into trusted workload evidence.

## Reconciliation decision

BaseballOS may delete this row only through the governed `phantom_game_log_reconciliation_v1` contract:

- exact GameLog, gamePk, game date, and stable MLB pitcher ID guards;
- explicit unresolved state with no attributed team;
- strict all-zero, zero-out stored pitching signature;
- complete final official box-score pitching sections for both teams;
- the target MLB pitcher ID absent from all official pitching lines;
- no foreign-key dependent rows;
- read-only dry run producing a deterministic evidence fingerprint;
- apply requiring the exact confirmation phrase and approved fingerprint;
- row lock and complete revalidation immediately before deleting exactly one GameLog.

Missing, partial, duplicate, contradictory, or changed evidence refuses the operation. No current-team assignment is consulted.

## Forward ingestion decision

The per-pitcher MLB gameLog feed is not sufficient authority to create a new all-zero, zero-out appearance. Such a listing may represent a player attached to the game without an official pitching appearance.

A new all-zero row therefore requires `boxscore_side` authority. Schedule-only or unresolved all-zero listings fail closed before INSERT and are visible through the sync failure lane. The final postgame box-score pitching section owns legitimate 0.0-IP appearances, including pitchers who entered but recorded no outs. Once an official row exists, the daily gameLog lane may re-read it idempotently without creating a duplicate.

Nonzero gameLog appearances and all existing Foundation 1 source-precedence rules remain unchanged.

## Scope

No migration, ranking, public reader, frontend, Team State, Share Card, Foundation 3B, or SC-05 change is included. The production delete is not executed by the repository change and remains dry-run-first after merge.
