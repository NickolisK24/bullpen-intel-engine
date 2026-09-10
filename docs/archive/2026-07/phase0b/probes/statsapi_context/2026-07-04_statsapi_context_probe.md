# Stats API Context Probe - 2026-07-04

Status: `READ-ONLY-PROBE`

This probe records point-in-time observations for Phase 0B-04. It did not
import BaseballOS production code, write to the production database, schedule a
job, or change production behavior. Observations are source facts from the
queried responses; interpretations are audit conclusions only.

## Probe Method

| item | value |
| --- | --- |
| probe date | 2026-07-04 |
| probe time | 13:02 America/Indianapolis |
| source host | `https://statsapi.mlb.com` |
| production code imported | no |
| production database touched | no |
| raw response persisted | no |

## Requests

| area | endpoint | observed result |
| --- | --- | --- |
| Final play-by-play | `https://statsapi.mlb.com/api/v1/game/778557/playByPlay` | HTTP success; top-level keys included `copyright`, `allPlays`, `currentPlay`, `scoringPlays`, and `playsByInning`; `allPlays` count was 73. |
| Final live feed | `https://statsapi.mlb.com/api/v1.1/game/778557/feed/live` | HTTP success; top-level keys included `gameData` and `liveData`; `liveData` included `plays`, `linescore`, `boxscore`, `decisions`, and `leaders`; `liveData.plays.allPlays` count was 73. |
| Current-day schedule | `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-07-04&hydrate=team,probablePitcher` | HTTP success; first row observed as `gamePk=822716`, `abstractGameState=Live`, `detailedState=In Progress`, `statusCode=I`; other rows included pregame probable pitchers. |
| In-progress live feed | `https://statsapi.mlb.com/api/v1.1/game/822716/feed/live` | HTTP success; status was `Live` / `In Progress`; linescore showed current inning, inning half, balls, strikes, outs, offense, and defense. |
| In-progress play-by-play | `https://statsapi.mlb.com/api/v1/game/822716/playByPlay` | HTTP success; `allPlays` count matched the live feed count at probe time. |
| In-progress boxscore | `https://statsapi.mlb.com/api/v1/game/822716/boxscore` | HTTP success; home and away pitcher lists each had 2 pitchers at probe time, showing a partial in-progress shape. |
| Active roster | `https://statsapi.mlb.com/api/v1/teams/147/roster?rosterType=active&date=2026-07-04&hydrate=person` | HTTP success; roster count was 26; entries included `person`, `jerseyNumber`, `position`, `status`, and `parentTeamId`. |
| 40-man roster | `https://statsapi.mlb.com/api/v1/teams/147/roster?rosterType=40Man&date=2026-07-04&hydrate=person` | HTTP success; roster count was 41; entries included `person`, `jerseyNumber`, `position`, `note`, `status`, and `parentTeamId`. |
| Full roster | `https://statsapi.mlb.com/api/v1/teams/147/roster?rosterType=fullRoster&date=2026-07-04&hydrate=person` | HTTP success; roster count was 284; entries included the same broad roster fields as the 40-man response. |
| Transactions | `https://statsapi.mlb.com/api/v1/transactions?sportId=1&startDate=2026-06-01&endDate=2026-07-04` | HTTP success; returned 1,556 transaction rows; sample row keys included `id`, `person`, `toTeam`, `date`, `effectiveDate`, `resolutionDate`, `typeCode`, `typeDesc`, and `description`. |
| Injuries endpoint candidate | `https://statsapi.mlb.com/api/v1/injuries?sportId=1&startDate=2026-06-01&endDate=2026-07-04` | HTTP 404. No direct injury endpoint shape was confirmed by this probe. |

## Observed Play-By-Play Shape

The final `playByPlay` response returned `allPlays`. A complete play contained:

- `result`
- `about`
- `count`
- `matchup`
- `pitchIndex`
- `actionIndex`
- `runnerIndex`
- `runners`
- `playEvents`
- `playEndTime`
- `atBatIndex`

The observed `about` block included:

- `atBatIndex`
- `halfInning`
- `isTopInning`
- `inning`
- `startTime`
- `endTime`
- `isComplete`
- `isScoringPlay`
- `hasReview`
- `hasOut`
- `captivatingIndex`

The observed `result` block included:

- `type`
- `event`
- `eventType`
- `description`
- `rbi`
- `awayScore`
- `homeScore`
- `isOut`

The observed `matchup` block included batter and pitcher identity plus handedness
context. The first pitch event included `details`, `count`, `pitchData`, `index`,
`playId`, `pitchNumber`, `startTime`, `endTime`, `isPitch`, and `type`.

Interpretation: final play-by-play appears to expose enough structured fields to
support later derived bullpen context such as pitcher changes, score at entry,
inning/half, and some runner or pitch-event context. This probe does not prove
correction latency, legal posture, all-game-type coverage, or public-display
safety.

## Observed Live Feed Shape

The final `feed/live` response returned broader game context than `playByPlay`.
`gameData` included keys such as `game`, `datetime`, `status`, `teams`, `players`,
`venue`, `weather`, `gameInfo`, `review`, `flags`, `alerts`,
`probablePitchers`, `officialScorer`, `primaryDatacaster`, and `moundVisits`.
`liveData` included `plays`, `linescore`, `boxscore`, `decisions`, and
`leaders`.

The in-progress `feed/live` response for `gamePk=822716` had status `Live` /
`In Progress` and exposed current inning, inning state, inning half, balls,
strikes, outs, offense, and defense. At probe time, both `playByPlay` and
`feed/live` showed 52 plays; the boxscore had only partial pitcher lists.

Interpretation: live feed is useful for research, but it is non-final by
definition. It must not support public evidence unless a later phase proves
finality, correction, and stale-feed behavior. Current Phase 0B-04 posture is
`NEVER` for public display of live/in-progress evidence.

## Observed Roster Shape

The active roster query returned 26 rows for team 147 on 2026-07-04. Active
roster entries included person identity, jersey number, position, status, and
parent team id. The 40-man query returned 41 rows, including a `note` field on
the sampled entry. The full roster query returned 284 rows.

Interpretation: roster endpoints can support current-state categories such as
active roster, 40-man depth, full-roster depth, and unknown. They do not prove a
player is healthy or injury-free.

## Observed Transaction Shape

The transaction query returned rows with `date`, `effectiveDate`,
`resolutionDate`, `typeCode`, `typeDesc`, `description`, person, and team fields.
The sampled row was a status-change transaction involving an injured-list
transfer and public injury text.

Interpretation: transaction rows can support later audit of roster churn,
IL placements, activations, recalls, options, DFA, trades, releases, and public
injury descriptions. Transaction text parsing is risky and should remain
explanatory, not current-state authority, unless aligned with roster snapshot
evidence and effective dates.

## Unknowns

- Exact correction latency for final play-by-play and transactions.
- Whether every play-by-play field is stable across postponed, suspended,
  resumed, extra-inning, and doubleheader cases.
- Whether ghost runner state is represented consistently enough for public use.
- Whether mound visits and substitutions are complete enough for bullpen
  evidence.
- Whether direct injury endpoints exist under a different documented path.
- Legal terms, attribution requirements, storage rights, redistribution rights,
  and SLA for all queried context families.
