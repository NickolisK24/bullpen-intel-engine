# Decision: official pitching-line completeness diagnostic (2026)

- **Date:** 2026-07-27
- **Status:** Implemented (read-only diagnostic). No repair, no backfill, no reconciliation
  write, no change to the canonical aggregation, no change to any official-validation
  threshold or gate.
- **Scope:** A private, read-only diagnostic that identifies exactly which official MLB
  box-score pitching lines are absent, extra, misclassified, misassigned, duplicated, or
  statistically different in the local `GameLog` ledger.

## Decision statement

Local *scheduled-game* coverage is not evidence of local *pitching-line* coverage. Before any
repair is designed, the missing population must be identified line by line against official
box-score evidence. This branch adds that diagnostic and nothing else.

## 1. Why the existing local audit was insufficient

The production official-validation run for the canonical 2026 bullpen aggregation returned:

| signal | value |
| --- | --- |
| result | `fail` |
| decision reason | `official_mandatory_metric_mismatch` |
| official games fetched | 1,570 |
| official games missing unique starter | 0 |
| official games with multiple starters | 0 |
| teams matched | 0 |
| teams mismatched | 30 |
| mandatory metric mismatches | 228 |
| bounded mismatches with local below official | 60 of 60 |
| local GameLog source rows | 12,856 |
| local relief rows | 9,746 |
| local starter rows excluded | 3,110 |
| expected team-game starter lines from 1,570 games | 3,140 |

The local-only audit passed against the same data. It passed because its
`complete_team_games` count is derived from the canonical schedule authority: it counts
**team-games whose `ScheduledGame` rows are final regular-season games**. That proves a game
happened and is final. It says nothing about whether every official pitching line in that
game exists locally.

Concretely, the local aggregation's per-team coverage sets `eligible_team_games ==
complete_team_games` and `excluded_team_games == 0` for every team, because eligibility is a
property of the *schedule*, not of the *ledger*. A team-game with six official relief lines
and four stored relief lines is still "complete" under that definition. The canonical
reconciliations behave the same way: `canonical_game_grain_bullpen_outs ==
canonical_team_grain_bullpen_outs` compares the stored rows to themselves, so it holds
exactly when the ledger is internally consistent — including when the ledger is uniformly
short of the official truth.

The direction of the failure confirms this. All 60 bounded mismatches had local values
**below** official values, and local starter rows (3,110) fall short of the 3,140 starter
lines implied by 1,570 official games. That is the signature of missing lines, not of wrong
arithmetic on present lines. Nothing in the local-only audit can distinguish the two, so a
new authority — the official box-score pitching section itself — is required.

## 2. What the diagnostic establishes

For every final regular-season game through the as-of date it:

1. fetches the official MLB box score;
2. resolves both official team sides;
3. enumerates every identity in each official pitching section;
4. identifies the unique official starter using exactly `gamesStarted == 1`;
5. treats every other official pitching identity as a relief appearance;
6. compares official lines to local `GameLog` rows on
   `mlb_game_pk` + official MLB pitcher id + `appearance_team_id`.

`Pitcher.team_id`, current roster, and current organization are never consulted as historical
authority; identity is matched by official MLB id only, and a missing identity is never
inferred from a name.

## 3. Typed classification vocabulary

`exact_match`, `official_line_missing_local_game_log`,
`local_line_not_in_official_pitching_section`, `local_pitcher_identity_missing`,
`official_pitcher_identity_missing_from_pitcher_table`, `appearance_team_mismatch`,
`starter_relief_classification_mismatch`, `innings_outs_mismatch`, `runs_mismatch`,
`earned_runs_mismatch`, `hits_mismatch`, `walks_mismatch`, `strikeouts_mismatch`,
`home_runs_mismatch`, `local_duplicate_line`, `official_starter_missing`,
`official_starter_contradictory`, `official_evidence_unavailable`.

## 4. Comparison population

A team-game side is **compared** only when its box score was fetched, its team id resolves,
and it has exactly one `gamesStarted == 1` starter. A side without a unique starter cannot
have its roles classified, so its official lines are excluded from comparison and reported
as `official_starter_missing` / `official_starter_contradictory` instead.

Identity enumeration, however, is complete for any fetched box score. A local line whose
official MLB id appears in **neither** official pitching section of that game is therefore
proven extra regardless of starter identity. A game whose box score could not be fetched
proves nothing about its local rows, so those rows are excluded from the population entirely.

## 5. Missing values are never zero

An absent official stat is reported as `official_evidence_unavailable` for that line and
compared against nothing. An absent local `games_started` is a role mismatch, never a relief
appearance. An absent local stat is a mismatch against a present official value, never a
zero.

## 6. Reconciliations

`official_games × 2 == official_team_game_sides`; every side has exactly one official
starter; `official_starter_lines == official_team_game_sides`;
`official_starter_lines + official_relief_lines == official_pitching_lines`; the compared
official lines partition into exact matches, missing local lines, and defective matched
lines; the local population partitions into lines present in an official pitching section,
extra lines, and identity-unresolvable lines; and the detail list reconciles to the sum of
game-level, side-level, compared-line, and local-direction classifications.

## 7. Result semantics

- **fail** — official evidence proves a missing, extra, duplicate, misassigned,
  misclassified, or differing local line. Contradictory official starter evidence (more than
  one `gamesStarted == 1` on a side) is also a fail, matching the canonical aggregation's
  existing precedence, which this diagnostic does not weaken.
- **inconclusive** — required official evidence could not be fetched, or a side has no unique
  official starter, and no defect was proven.
- **pass** — every official pitching line has exactly one exact local counterpart and no
  unmatched local line exists.

A proven defect outranks an evidence gap: an unfetchable game elsewhere never masks a line
that official evidence has already disproved. Evidence gaps are still reported in
`counts_by_reason` and in the reconciliations.

Details are ordered deterministically — findings first, then game, team, and identity — so a
bounded window always surfaces defects rather than the first game's clean lines. Bounding
changes only the returned detail list, never a count.

## 8. Safety boundary

Read-only. No inserts, updates, deletes, commits, autofixes, backfills, or reconciliation
writes; `database_writes_performed` is always `false`. The canonical aggregation and every
official-validation threshold are untouched. The repair is deliberately **not** implemented
in this branch. Foundation 3B, the public reader, Team State performance, Share Card
performance, and SC-05 remain blocked.

## 9. Operation

- Service: `backend/services/official_pitching_line_completeness_2026.py`
- CLI: `backend/scripts/run_official_pitching_line_completeness_2026.py`
- Workflow: `.github/workflows/official_pitching_line_completeness.yml` (dispatch-only)
- Tests: `backend/tests/test_official_pitching_line_completeness_2026.py`

Production run: dispatch the workflow with `season=2026`, `as_of_date=2026-07-25`,
`detail_limit=100`, `team_id` and `game_pk` blank. The deterministic JSON artifact is
uploaded privately and retained for 14 days.
