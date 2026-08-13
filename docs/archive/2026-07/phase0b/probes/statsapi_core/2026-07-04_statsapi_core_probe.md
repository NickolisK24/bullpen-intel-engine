# Stats API Core Probe Evidence - 2026-07-04

Status: `AUDIT-ONLY-0B`

This probe record supports `docs/phase0b/02_statsapi_core.md`. It is read-only
evidence only. No production code was imported, no production database was
opened, and no production behavior was changed.

## Probe Metadata

| field | value |
| --- | --- |
| probe_date | 2026-07-04 |
| requested_at_utc | 2026-07-04T16:46:14Z through 2026-07-04T16:47:14Z |
| source | `https://statsapi.mlb.com/api/v1` |
| method | Read-only HTTP GET requests from PowerShell |
| production imports | none |
| production writes | none |

## Requests

| purpose | endpoint and parameters |
| --- | --- |
| 2025 season schedule field scan | `/schedule?sportId=1&startDate=2025-03-01&endDate=2025-11-30&hydrate=team,venue,probablePitcher` |
| 2025 regular-season schedule field scan | `/schedule?sportId=1&startDate=2025-03-27&endDate=2025-11-30&hydrate=team,venue,probablePitcher` |
| regular-season final boxscore sample | `/game/778557/boxscore` |
| current-day non-final boxscore shape | `/schedule?sportId=1&date=2026-07-04&hydrate=team,venue,probablePitcher` and `/game/822716/boxscore` |
| postponed and doubleheader edge check | `/schedule?sportId=1&startDate=2025-04-05&endDate=2025-04-07&hydrate=team` |
| suspended/resumed field scan | season schedule scans for 2021 through 2026 with `sportId=1` |

## Observed Facts

### Schedule Identity And Date Fields

- The 2025 season scan returned 2878 schedule game rows.
- A regular-season final sample returned:
  - `gamePk=778557`
  - `officialDate=2025-03-27`
  - `gameDate=2025-03-27T19:05:00Z`
  - `gameType=R`
  - home team id `147` and away team id `158`
  - `venue.id=3313`, `venue.name=Yankee Stadium`
  - `doubleHeader=N`
  - `gameNumber=1`
  - `seriesGameNumber=1`
  - `gamesInSeries=3`
- The same sample included probable pitchers even though the game was final:
  - home probable pitcher id `607074`, name `Carlos Rodon`
  - away probable pitcher id `642547`, name `Freddy Peralta`

### Status And Finality Fields

- The regular-season final sample returned:
  - `abstractGameState=Final`
  - `codedGameState=F`
  - `detailedState=Final`
  - `statusCode=F`
  - `abstractGameCode=F`
- A postponed/rescheduled edge case returned a row with:
  - date bucket `2025-04-05`
  - `gamePk=778443`
  - `officialDate=2025-04-06`
  - `gameDate=2025-04-05T20:10:00Z`
  - `abstractGameState=Final`
  - `codedGameState=D`
  - `detailedState=Postponed`
  - `statusCode=DR`
  - `reason=Rain`
  - `rescheduleDate=2025-04-06T17:35:00Z`
- The same `gamePk=778443` also appeared on `2025-04-06` as the rescheduled
  final first game of a doubleheader:
  - `statusCode=F`
  - `detailedState=Final`
  - `doubleHeader=S`
  - `gameNumber=1`
- A second game in that doubleheader appeared as `gamePk=778432` with:
  - `doubleHeader=S`
  - `gameNumber=2`
  - `seriesGameNumber=3`

### Suspended And Resumed Fields

- The 2021 through 2026 season scans found historical final games with
  `resumedFrom` and `resumedFromDate`.
- Example observed row:
  - year `2025`
  - `gamePk=777861`
  - `officialDate=2025-05-19`
  - `gameDate=2025-05-21T17:10:00Z`
  - `statusCode=F`
  - `detailedState=Final`
  - `resumedFrom=2025-05-19T23:40:00Z`
  - `resumedFromDate=2025-05-19`
- `resumedFromGamePk` was not observed in the sampled rows.

### Boxscore Player Pitching Fields

The regular-season final boxscore sample for `gamePk=778557` included a pitcher
line for player id `607074` with these observed pitching fields:

- `gamesStarted`
- `inningsPitched`
- `outs`
- `numberOfPitches`
- `pitchesThrown`
- `balls`
- `strikes`
- `battersFaced`
- `hits`
- `runs`
- `earnedRuns`
- `baseOnBalls`
- `strikeOuts`
- `homeRuns`
- `holds`
- `saves`
- `blownSaves`
- `wins`
- `losses`
- `saveOpportunities`
- `inheritedRunners`
- `inheritedRunnersScored`
- `gamesFinished`
- `summary`

Sample values for player id `607074`:

- `inningsPitched=5.1`
- `outs=16`
- `numberOfPitches=89`
- `pitchesThrown=89`
- `balls=31`
- `strikes=58`
- `battersFaced=22`
- `gamesStarted=1`

### Boxscore Team Pitching Totals

The same boxscore included `teamStats.pitching` fields. Observed team totals
included:

- `inningsPitched`
- `outs`
- `numberOfPitches`
- `pitchesThrown`
- `balls`
- `strikes`
- `battersFaced`
- `runs`
- `earnedRuns`
- `baseOnBalls`
- `strikeOuts`
- `hits`
- `homeRuns`
- `inheritedRunners`
- `inheritedRunnersScored`
- `pitchesPerInning`
- `whip`
- `era`

Sample team totals for the home team:

- `inningsPitched=9.0`
- `outs=27`
- `numberOfPitches=175`
- `pitchesThrown=175`
- `strikes=113`
- `battersFaced=38`

### Non-Final Boxscore Shape

- On the 2026-07-04 current-day schedule probe, one non-final game returned:
  - `gamePk=822716`
  - `abstractGameState=Live`
  - `statusCode=I`
  - `detailedState=In Progress`
- A boxscore request for that in-progress game returned a partial boxscore shape
  with teams and pitching lists:
  - home pitcher count `2`
  - away pitcher count `1`

## Interpretation

- `gamePk` is the durable game identity, but postponed and rescheduled schedule
  rows can expose the same `gamePk` with different date buckets and status
  fields. A future denominator must evaluate status precedence and product date,
  not game id alone.
- `officialDate` is the safer product-day candidate than UTC `gameDate`, but
  rescheduled/postponed rows can move the official date forward from the date
  bucket being queried.
- `abstractGameState=Final` is not sufficient by itself. It appeared on a
  postponed row with `statusCode=DR` and `detailedState=Postponed`.
- `detailedState=Postponed`, `statusCode=DR`, suspended indicators, and
  resumed-from fields must be first-class slate denominator inputs.
- Probable pitchers are available from schedule hydration, but they remain
  forward-looking schedule context. They are not evidence of what happened.
- Final boxscore pitching lines expose more fields than BaseballOS currently
  stores, including `battersFaced`, `balls`, `outs`, `pitchesThrown`,
  `gamesFinished`, and team pitching totals.
- In-progress boxscores can contain partial pitching lines. They must not be
  used as completed-game evidence.
- Legal and terms posture was not resolved by this probe. All matrix rows that
  depend on this source remain `needs-legal-review`.
