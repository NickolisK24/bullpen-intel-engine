# Tonight v1 lead development (TN-07)

Status: tonight_v1 fills `lead` at build/publication time with **zero or one**
frozen bullpen development, chosen by strict rule priority. `lead = null` is
correct and expected on a quiet or ordinary day. There is no filler, fallback,
score, ranking or prediction. The default Tonight response is still legacy
`tonight_v5`, and the frontend is unchanged (TN-08).

## Authority

- `tonight_read_model.select_lead(games, league_changes)` is pure. It reads
  only the stored game cards (publication-time state, TeamSides) and the
  retained TN-05 `league_changes`.
- It issues no query and never compares snapshots again.
- It never uses TN-03 overlay state, featured status or ordering, the TN-04
  context, standings, or intent.
- It runs after league changes, change refs and featured selection, and
  depends on none of their outputs except the retained changes.

Team State values come from a new frozen field on TN-05 Team State items:
`state_change: {"from", "to"}`. It is copied at build from the same TB-09
event's `previous_value`/`current_value` labels, and is `null` for every other
class. The lead never parses prose and never recomputes a comparison. A Team
State change that TN-05 capped out is not in `league_changes`, so it can never
lead.

## Schema

```
lead: null | {
  lead_type, headline, detail|null, team_ids: [id], game_pk,
  change_refs: [change_id...], reason_codes: [lead_type], evidence_state: "complete"
}
```

## Rules (fixed priority; the first rule with any candidate wins)

| # | lead_type | Eligibility (frozen facts only) | Headline |
| --- | --- | --- | --- |
| 1 | `team_state_to_vulnerable` | retained `team_state_changed`, `to == "Vulnerable"`, `from != "Vulnerable"` | `{TEAM} moved into a Vulnerable bullpen state entering tonight.` |
| 2 | `team_state_change` | any other retained Team State change (`from != to`) | `{TEAM} moved from {FROM} to {TO} entering tonight.` |
| 3 | `heavy_back_to_back_pressure` | `rest.available` and `back_to_back_count >= 3` (stricter than TN-06's 2) | `{TEAM} has {N} bullpen arms coming off back-to-back usage tonight.` |
| 4 | `short_start_bullpen_transfer` | rotation `status == "complete"`, `short_start_count >= 1`, frozen `bullpen_innings >= 5.0` | `{TEAM}'s bullpen has absorbed {INN} innings after a recent short start.` (or `after {N} recent short starts`) |

Rule details:

- All rules: the team must be in tonight's frozen slate, in a game that was
  `scheduled` or `uncertain` at publication. If a team has two such games,
  the earliest (first pitch, game_number, game_pk) is used.
- Change evidence must be `complete`.
- `detail` is `{TEAM} is scheduled to face {OPPONENT}.` from the frozen game
  card.
- `bullpen_innings` is the frozen TeamSide rotation field. It is box-score
  thirds (`"5.1"` = 5⅓), so the threshold is 15 outs; a numeric value is
  compared directly. No other rotation metric is used, and INN is shown
  exactly as frozen.
- None of these leads: 3-in-4, high-pitch, membership, transactions, a current
  Vulnerable state with no retained change, featured status, one B2B arm,
  context, workload volume or performance.

Tie-break within a rule:

1. `occurred_on` (newest first; undated last);
2. first pitch (unknown last);
3. team abbreviation;
4. `team_id`;
5. `game_pk`.

## Copy

- `LEAD_BANNED_TERMS`, scanned with the shared editorial matcher: advantage,
  edge, favorite, favored, likely, will, should, should win, target, fade,
  bet, betting, fantasy, pick, prediction, must watch, best game, top game,
  gassed, exhausted, tired, danger, trouble.
- Every template also passes the default editorial list.
- Length limits: headline ≤ 120 characters, detail ≤ 140. A headline that
  fails the guard or the limit removes that candidate (fail-closed, no
  rewrite). A detail that fails is dropped to `null`.
- `evidence_state` is always `complete`. There is no partial lead.

## Serving (TN-03)

The lead is frozen and never reselected. When the lead's game is served in any
state other than scheduled or uncertain, `present_lead` appends
`pregame_context` to `reason_codes`; every other field is unchanged. That
marker is part of the overlay identity, so the composite ETag reflects it.
Serving is unchanged at 3 statements, with 0 GameLog, 0 FatigueScore and
0 writes. Build adds 0 queries.

## Compatibility

- No migration. The contract stays `tonight_v1`.
- Pre-TN-07 rows (for example production row 1) keep `lead: null` and are not
  regenerated or backfilled.
- TN-05 items gain the additive `state_change` field on new builds only.

## Verification

- `backend/tests/test_tonight_v1_read_model.py` covers:
  - Team State leads: Fresh→Vulnerable, Stretched→Vulnerable, Fresh→Stretched
    and Vulnerable→Stretched;
  - thresholds: back-to-back 3 leads and 2 does not; short start with 5.0 /
    "6.1" / 5.0 leads, while "4.2", 4.9 and 0 short starts do not;
  - incomplete rotation (partial, unavailable, missing) never leads;
  - 3-in-4, high-pitch, membership, transaction and a Vulnerable team with no
    change never lead;
  - an off-day team's change and live, final, postponed or suspended games
    never lead;
  - unavailable rest never gives a back-to-back lead;
  - tie-breaks: date, first pitch, then team;
  - copy and length guards, and an AST check for no score or weight;
  - the A→B→C→D→null priority ladder;
  - a capped-out Team State change never leads;
  - a production-shaped six-game fixture: lead is game 1
    `team_state_to_vulnerable`, and featured, league changes and cards are
    unchanged;
  - parity for each rule, presentation idempotence, and a real build over a
    TB-09 pair, including a quiet slate with a null lead.
- `backend/tests/test_tonight_v1_serving.py` covers the overlay: the lead is
  marked `pregame_context` when live or final, never reselected, gets a
  distinct ETag per presentation, and is untouched when another game moves.
- `backend/tests/test_trusted_publication_rehearsal.py`:
  - In the real publication, the lead is `team_state_change` on 7600001:
    "R01 moved from Fresh to Stretched entering tonight.", with the retained
    change as its ref.
  - A rebuild reuses the row.
  - Serving through scheduled, live and final keeps the lead frozen, adding
    the pregame marker once live or final.
  - The main Tonight rehearsal (no predecessor) asserts `lead is None`.
