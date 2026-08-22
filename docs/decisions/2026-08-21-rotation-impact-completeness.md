# Rotation Impact Completeness

Date: 2026-08-21
Status: Accepted

## Decision

The existing seven-day Rotation Impact read is fully available when every
qualifying completed team game has a complete, governed team-game pitching
split and at least three rotation starts are analyzed. Descriptive source notes
about team-at-game ownership and opener/bulk handling are methodology context;
they are not runtime limitations by themselves.

Runtime status remains partial when a declared core input is missing,
unresolved, materially excluded, or below the minimum sample. An unverified
opener/bulk or bullpen-game shape remains a real scoped limitation. Unavailable
continues to mean that the core rotation-transfer read cannot be established.

## Authority

The public window is the inclusive seven-calendar-day interval `[D-6, D]`,
where `D` is the represented Team Board date. Only final regular-season games
from `scheduled_games` qualify. Doubleheaders remain distinct by MLB game PK;
future and non-final games do not enter the window.

`team_game_pitching_splits` is the canonical team-and-game owner. Its writer now
groups GameLogs only through resolved `GameLog.appearance_team_id` authority.
Mutable `Pitcher.team_id` has no role in historical attribution. Unresolved or
conflicting appearance-team authority fails closed instead of falling back to
the pitcher's current club.

The stored official starter flag (`games_started == 1`) governs starter
identity. Ambiguous or missing starter identity is not converted to zero.
Rotation starts shorter than 15 recorded outs are short starts. Starter and
bullpen work aggregate integer outs before one display conversion; bullpen
transfer is the stored `bullpen_outs_recorded` for qualifying rotation starts.
Complete team-game shapes require at least 24 recorded team outs, preserving
shortened and extra-inning game facts without display-rounded arithmetic.

## Public status boundary

The existing public method and contract do not change. This correction enforces
their already-declared team-at-game population and separates durable source
notes from actual availability limitations:

- complete governed coverage and the minimum sample: `available`;
- useful core facts with a real typed limitation: `partial`;
- no safe core read: `unavailable`.

Source notes remain present in `source_limitations` for contract compatibility
and methodology transparency. They no longer force a partial section when the
declared public metrics are complete.

## Deferred optional context

Starter pitch totals remain stored evidence but are not promoted as a new
public metric in this slice. Verified opener/bulk and bullpen-game shapes remain
separate descriptive context; uncertain shapes fail closed. A literal recent-
series burden remains definition/authority blocked because no durable canonical
series identity safely spans postponements, resumptions, and makeup games.

No Team State, Rest Status, workload, Performance, roster, Recent Relief Work,
What Changed, frontend layout, historical package, or delta-carrier semantics
change under this decision.
