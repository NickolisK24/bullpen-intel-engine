# Tonight v1 featured games (TN-06)

Status: tonight_v1 selects at most four featured games at build/publication
time. It uses fixed rule priority over facts already frozen in the same
payload. The default Tonight response is still legacy `tonight_v5`, and the
frontend is unchanged (TN-08).

Featured games are a descriptive "where to look first" set of games with
notable bullpen operating conditions. They are not a ranking, score,
probability, prediction, edge, or betting/fantasy signal.

## Authority

These helpers in `tonight_read_model` are pure:

- `featured_reasons_for_game(game, league_changes_by_id)`
- `select_featured_games(games, league_changes, *, max_featured=4)`
- `apply_featured_games(games, league_changes)`

They read only the stored game card's two TeamSides and the retained TN-05
`league_changes` that `change_refs` point to. They issue no query and do no
baseball calculation. The TN-04 `context` is not consulted, and the TN-03
overlay plays no part: selection runs once, at build.

## Eligibility and rules

A game is eligible only if its publication-time `state` is `scheduled` or
`uncertain`. Live, final, postponed and suspended games are never featured.

Rules, in priority order (the index is the only order; there is no score):

| # | Reason code | Frozen fact |
| --- | --- | --- |
| 1 | `vulnerable_team` | a side's available Team State is `vulnerable` |
| 2 | `team_state_change` | a side's `change_refs` resolve to a retained `team_state_changed` change for that team |
| 3 | `multiple_back_to_back_arms` | a side's available rest has `back_to_back_count >= 2` |
| 4 | `three_in_four_pressure` | a side's known `multi_day_usage.three_in_four_count >= 1` |
| 5 | `short_start_transfer` | a side's rotation is present (complete/partial) with `short_start_count >= 1` |
| 6 | `bullpen_membership_change` | a side's refs resolve to a retained `active_bullpen_joined` / `active_bullpen_left` change |

Evidence handling:

- Rules reuse the TN-04 fact readers, so a withheld Team State, unavailable
  rest, unknown 3-in-4 count, null rotation or unavailable side never
  qualifies, and `None` is never zero.
- A ref must resolve to a retained change of the same team. Other change
  classes (transactions, workload starts) do not qualify.

## Selection and ordering

Order key:

1. the highest-priority rule the game meets;
2. `first_pitch_utc` ascending (unknown last);
3. `game_number`;
4. `game_pk`.

At most 4 games are selected. There is no padding, and none selected gives
`[]`.

Contract (no migration; the contract stays `tonight_v1`):

- `featured_game_pks` lists the selected games in selection order.
- Each game gets `featured` (bool) and a new `featured_reason_codes` list.
  For a featured game it holds every rule the game meets, in priority order;
  otherwise it is `[]`. A game that qualified but fell below the cap is not
  featured and carries `[]`.
- `summary`, `league_changes`, `change_refs` and `context` are not touched.

## Serving

- TN-03 copies each game card and changes only state, time, `state_as_of`
  and the TN-04 context presentation.
- `featured`, `featured_reason_codes` and `featured_game_pks` pass through
  unchanged. A featured game that goes live, final, postponed or suspended
  keeps its frozen identity, and nothing is reselected at request time.
- The presentation layer may read a live featured game as a pregame
  selection.
- Serving stays at 3 statements, with 0 GameLog, 0 FatigueScore and 0 writes.
- Build adds 0 queries.

## Compatibility

Rows built before TN-06 (for example production row 1) keep
`featured_game_pks: []` and have no `featured_reason_codes` field. They are
not regenerated or backfilled.

## Verification

- `backend/tests/test_tonight_v1_read_model.py` covers:
  - every rule, including negatives: 1 back-to-back arm, unsupported change
    classes, withheld Team State or rest, null 3-in-4, null rotation, no rule,
    and unresolved or foreign refs;
  - every reason retained in priority order;
  - exclusion of live, final, postponed and suspended games;
  - priority order A/B/C/D;
  - the cap with seven qualifying games, with time, `game_number` and
    `game_pk` tie-breaks and unknown times last;
  - fewer than four staying fewer;
  - an AST check that the helpers have no score, weight or rank identifiers;
  - a production-shaped six-game fixture using real TB-09 league changes,
    with exact order [1, 2, 3, 4] and parity to stored fields;
  - a real build over a TB-09 pair giving [1, 2].
- `backend/tests/test_trusted_publication_rehearsal.py::test_rehearsal_tonight_v1_league_changes`:
  - The real publication features [7600001, 7600003]: `team_state_change` +
    `three_in_four_pressure`, and `bullpen_membership_change`.
  - The postponed game is excluded.
  - A rebuild reuses the row.
  - Serving through scheduled, live and final leaves `featured_game_pks` and
    every card's featured fields identical, with no GameLog/FatigueScore reads.
