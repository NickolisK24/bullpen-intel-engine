# Official-starter alignment incident — Team Board relief work, July 28 2026

Status: read-path corrected; no production data repair proposed.
Surface: `GET /api/bullpen/teams/<team_id>/relief-work` → "Relief Work by Date".

## What was published

The Reds Team Board showed, under one July 28 header:

- a date summary of `8 relief appearances, 11.1 IP, 165 pitches`;
- an "Extended bullpen coverage" narrative naming Caleb Ferguson as the game's
  starter (`5 outs (1.2 IP) on 27 pitches`, `four relievers … 22 outs (7.1 IP)
  on 108 pitches`);
- an eight-row appearance list.

The official box score for the Reds' July 28 game shows Chase Burns starting
(5.0 IP) with Brock Burke, Pierce Johnson, Sam Moll, and Chase Petty in relief
(1.0 IP each).

## Root cause

Two coupled defects in `services/public_team_relief_work.py`, both in how the
board decided *which rows belong to this team's game*. The official start
signal itself (`GameLog.games_started`) was never wrong.

1. **Cohort selected by current roster, not by official game side.** The row
   query filtered on `Pitcher.team_id == team_id` — the pitcher's mutable
   current club. `GameLog.appearance_team_id` (Foundation 1), the canonical
   team-at-appearance authority, was never consulted. Two consequences:
   - appearances a pitcher made **for another club** were pulled onto this
     board, bringing that club's game and its starter narrative with them;
   - the board's **own** official starter was dropped when he was no longer on
     the current roster, leaving the real game with no credited starter, which
     silently suppressed its block and left the foreign game's narrative as the
     only one under the date header.

2. **A date-level cohort feeding a game-level narrative, with nothing
   reconciling them.** `_relief_by_date` grouped by `game_date` and emitted one
   summary plus one flat appearance list; `_game_context_blocks` then emitted
   `game_pk`-scoped narratives *inside* that container. No check required the
   narrative's pitcher set to be the rows shown beneath it, and no check
   disclosed that a date total spanned more than one game.

The published summary (8 / 34 outs / 165 pitches) did reconcile to its own
eight rows. The narrative under it described a different five-pitcher game.
That is the rule 8 / rule 9 violation.

## Correction

- Appearances are scoped by `appearance_team_status = 'resolved'` **and**
  `appearance_team_id = <team>`. Current roster is used only for the team's
  display name and for an out-of-band disclosure of appearances whose official
  game side is unresolved.
- A game narrative additionally requires official final-game authority for that
  exact team side (`ScheduledGame.status_state = 'final'`), exactly one
  credited starter, and no unclassified line.
- Two reconciliation gates run before publication: a date summary must equal
  its own rows, and a game narrative's relief pitcher set and totals must equal
  that game's shown rows. A failing narrative is dropped; a failing summary
  publishes an honest unavailable state with no counts at all.
- Date summaries spanning more than one game say so ("across 2 games").
- Blocks carry `starter_authority` and `reconciled`; the panel renders a
  narrative only when both are affirmatively set by the server.

## Blast radius

The relief-work payload has exactly one consumer chain — the API route and
`TeamReliefWorkPanel` — and is computed per request. It is not snapshotted,
not written to a story or observation object, and not frozen into a share
artifact, so no published immutable artifact carries the incorrect narrative
and none needs rewriting.

The current-roster join over game logs remains present in other services; that
is the pre-existing Foundation 1 condition (`appearance_team_id` was added and
indexed for exactly this migration). Those surfaces are out of scope for this
change and are bounded by the audit command below.

## Read-only audit command

    python backend/scripts/run_official_starter_alignment_audit.py \
      --through 2026-07-28 --days 30 [--team-id 113] [--output audit.json]

Never writes, commits, or backfills. Exit 0 CLEAN / 1 AFFECTED / 2 ERROR.
Reports, per window: published-vs-official starter differences, published-vs-
official relief set differences, date summaries combining multiple games,
appearances whose owner differs from the pitcher's current club, final team
sides without exactly one official starter, and appearances with an unresolved
game side.

## Data changes

None proposed. The canonical rows were correct; the read path was not.

One deployment precondition: appearances whose `appearance_team_status` is not
`resolved` now fail closed out of the board (and are disclosed) instead of
being pulled in by the roster join. Run the audit above for the live window
before deploy and confirm
`findings.appearances_with_unresolved_game_side.count` is acceptable. If it is
not, the existing reviewed `run_unresolved_appearance_team_repair_2026.py`
path — not this change — is the remedy, and requires its own authorization.
