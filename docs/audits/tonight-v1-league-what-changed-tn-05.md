# Tonight v1 league What Changed (TN-05)

Status: tonight_v1 fills `league_changes`, `summary.change_count` and each
TeamSide's `change_refs` at build/publication time. It aggregates the frozen
Team Board What Changed (TB-09) of the same trusted snapshot. The default
Tonight response is still legacy `tonight_v5`, and the frontend is unchanged
(TN-08).

## Authority

- The only source is each canonical team's `frozen_what_changed` carrier in
  the snapshot's `trusted_team_boards` package. TB-09
  (`team_board_what_changed.build_frozen_what_changed`) builds that carrier
  over one exact trusted snapshot pair inside the publication proof.
- Each carrier is admitted through the Team Board serving validator
  (`public_serving_authority._frozen_what_changed_for_view`). A carrier that
  does not match this publication (contract, method, team, snapshot ids,
  represented date, comparison identity) or holds any malformed event
  contributes nothing.
- Tonight never compares snapshots, never looks up a predecessor, and never
  reads live rows, transactions, Team State or legacy Since Yesterday. It only
  filters, normalizes, dedupes, orders and caps.
- Helpers:
  - `_frozen_what_changed_by_team(snapshot, package)` selects the validated
    carriers.
  - `build_league_changes(carriers, *, max_per_team=2, max_total=12)` is pure.
  - `attach_change_refs(sides, league_changes)` is pure.
- None of them issues a query.

## Change classes (canonical TB-09 `event_type` → Tonight priority)

| Priority | change_class | Tonight class |
| --- | --- | --- |
| 1 | `team_state_changed` | Team State change |
| 2 | `active_bullpen_joined` / `active_bullpen_left` | Active bullpen membership |
| 3 | `verified_transaction` | Verified bullpen transaction |
| 4 | `back_to_back_started` | Back-to-back transition |
| 5 | `three_in_four_started` | 3-in-4 transition |
| 6 | `high_pitch_outing_started` | High-pitch event |
| 7 | `new_short_start` | Short-start / rotation transfer |

Every other type is excluded, including TB-09's `four_in_six_started`, which
is not a Tonight class. TB-09 itself never emits role, closer, performance or
raw-score changes; those domains are `not_comparable` there.

## Item contract

```
{change_id, team_id, team_abbreviation, change_class, headline, detail,
 occurred_on, evidence_state, source_ref, game_pks}
```

- `headline`:
  - Team State uses the fixed template `"{TEAM} moved from {previous} to {current}."`, built from the frozen labels.
  - Every other class uses the first sentence of the frozen TB-09 `summary`.
- `detail`: the frozen summary's second sentence, when present (for example
  "Verified transaction: Recalled." on a linked membership change); otherwise
  `null`.
- `occurred_on`: the frozen `event_date` when it is a valid ISO date;
  otherwise `null`.
- `evidence_state`: the frozen `evidence_status`. The validator admits only
  `complete`.
- `game_pks`: integer `facts.mlb_game_pk` or `facts.game_pks`; otherwise `[]`.
- `change_id`: the first 24 hex characters of the SHA-256 of
  `["tonight_league_change_v1", receipt, event_type, subject_id, event_date,
  previous_value, current_value, transaction_id]`. Here `receipt` is
  `team_board_what_changed_v1:{current_snapshot_id}:{previous_snapshot_id}:{team_id}`.
  There is no array position, no `generated_at` and no randomness, so the same
  frozen change always gets the same id.
- `source_ref`: that receipt, plus `#transaction:{id}` when the frozen event
  carries a verified transaction id. Both identifiers are already public in the
  frozen Team Board carrier; there are no internal database keys.

## Filtering and dedupe

An event is excluded if any of these hold:

- its carrier is not `state='changes'`;
- its `team_id` does not match, or the team is non-canonical;
- the class is unsupported;
- `evidence_status` is not `complete`;
- the summary is blank;
- a Team State change is missing its labels;
- it trips the copy guard.

Unavailable or quiet carriers produce no items, and nothing is inferred from
current state.

Dedupe is evidence-based:

- TB-09 already links a verified transaction to its matching membership delta.
- Tonight additionally drops a standalone `verified_transaction` whose
  transaction id is already carried by a membership change.
- Tonight drops any repeated `change_id`.
- Distinct events with the same copy stay distinct, because their identity
  differs.

## Caps and ordering

Order key (no score):

1. class priority;
2. `occurred_on` descending (undated after dated);
3. `team_abbreviation`;
4. `change_id`.

Caps:

- Per team: the first 2 by that key.
- League: the first 12 of all per-team survivors by the same key.

A small day is never padded, and an empty day is `[]` with no placeholder.

`summary.change_count` is `len(league_changes)`.

TeamSide `change_refs` are that team's retained ids, in list order, so there is
never a ref to a capped-out change. They are `[]` otherwise.

TB-09 itself keeps at most 5 events per team, so a team's candidates are
already bounded at the source.

## Copy guard

`LEAGUE_CHANGE_BANNED_TERMS` is scanned with the shared
`editorial_voice_contract_v1.find_editorial_violations`, including plural
variants. An item that trips it is dropped (fail-closed), never rewritten. The
terms are: advantage, edge, favorite, favored, likely, will, should win,
target, fade, bet, betting, fantasy, pick, prediction, gassed, exhausted,
hurt, injured. "injured" and "hurt" are allowed only on items carrying a
verified transaction, so a factual injured-list move can be stated.

## Interactions

- TN-03 overlay: it never touches `league_changes` or `change_refs`. The
  served changes are byte-identical to the stored changes across scheduled,
  live and final.
- TN-04 context: it is authored from TeamSide facts only and ignores changes.
  Changes never alter `context`.
- Lead and featured are untouched. `change_id` is stable for later reference.

## Queries, storage, compatibility

- Build issues 0 added queries: carriers come from the already-loaded snapshot
  payload.
- Serving is unchanged at 3 statements, with 0 GameLog, 0 FatigueScore and 0
  writes.
- There is no migration, and the contract stays `tonight_v1`.
- Pre-TN-05 rows (for example production row 1 / snapshot 3568) keep
  `league_changes: []` and are not backfilled or regenerated.

## Verification

- `backend/tests/test_tonight_v1_read_model.py` covers:
  - every class, a linked membership change with its transaction detail, and
    exclusion of unsupported, malformed and non-canonical events;
  - unavailable or quiet carriers yielding no items;
  - dedupe of a duplicate move, and distinct same-copy events staying distinct;
  - the priority/team cap (a team with all seven classes gives Team State then
    membership), the league cap of 12 with ordering and refs, and no padding;
  - `change_id` determinism and the copy guard;
  - a production-shaped six-team TB-09 pair built through the real
    `attach_frozen_what_changed`, with parity to the frozen events;
  - a build that populates changes, refs and count, keeps TN-04 context
    independent, and is content-stable on rebuild.
- `backend/tests/test_trusted_publication_rehearsal.py::test_rehearsal_tonight_v1_league_changes`:
  - Setup: an exact predecessor is injected at the real proof seam, and the
    canonical publication and projection then run.
  - Frozen changes: Team State, active bullpen join and back-to-back start.
  - Asserted: parity to TB-09, refs resolve, and a rebuild reuses the row.
  - Serving through scheduled, live and final leaves changes byte-identical in
    at most 3 statements, with no GameLog/FatigueScore reads and no writes.
