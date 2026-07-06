# Phase 0G Branch 02 Public Team Relief Work Endpoint

## Gate Status

Phase 0B remains closed. This branch adds a public, backend-only endpoint for a
future team relief-work panel, but it does not publish evidence objects,
citations, read components, rule identifiers, source-readiness notes,
reconciliation content, or internal review payloads.

## Ratified Branch Constraints

- The endpoint uses only the already-public game-log class and the existing
  public freshness block.
- Relief classification is mechanical: `games_started == 0` is counted,
  `games_started == 1` is excluded, and `games_started IS NULL` is excluded and
  disclosed in window copy.
- Game logs do not carry historical team assignment, so team grouping is based
  on pitchers currently assigned to the requested team in MLB roster data.
- The public service is structurally separate from internal evidence, read,
  audit, and reconciliation code.
- The public window constants are versioned in the service:
  `RECENT_GAME_DATES_MAX = 5`, `LOOKBACK_DAYS = 30`, and
  `WINDOW_DAYS = (7, 14)`.

## Endpoint Contract

`GET /api/bullpen/teams/<team_id>/relief-work`

The endpoint is public and read-only. It accepts no query parameters in this
version and returns `{"error": "team_not_found"}` with status `404` when no
stored pitcher rows exist for the team id.

## Payload Schema

```json
{
  "capability": "public_team_relief_work",
  "team": {
    "team_id": 110,
    "team_name": "Team Name",
    "team_abbreviation": "TST"
  },
  "data_through": "2026-07-05",
  "freshness": "existing public freshness block reused by reference",
  "scope_sentence": "Covers pitchers currently on the TST roster per MLB roster data.",
  "relief_by_date": [
    {
      "game_date": "2026-07-03",
      "relief_appearances": 4,
      "outs_total": 11,
      "pitches_total": 61,
      "appearances_with_pitches": 4,
      "sentence": "July 3 - 4 relief appearances, 3.2 IP, 61 pitches.",
      "appearances": [
        {
          "pitcher_id": 1,
          "pitcher_mlb_id": 12345,
          "pitcher_full_name": "Pitcher Name",
          "roster_status_sentence": "On the active roster per MLB roster data.",
          "game_date": "2026-07-03",
          "opponent": "Boston Red Sox",
          "opponent_abbreviation": "BOS",
          "innings_pitched": 1.0,
          "innings_pitched_outs": 3,
          "pitches_thrown": 14,
          "strikeouts": 1,
          "walks": 0,
          "hits_allowed": 1,
          "runs_allowed": 0,
          "save": false,
          "hold": true,
          "blown_save": false,
          "win": false,
          "loss": false,
          "save_situation": false,
          "sentence": "Pitcher Name - 1.0 IP, 14 pitches, 1 K, 0 BB, 1 H, 0 R."
        }
      ]
    }
  ],
  "windows": {
    "window_7": {
      "through": "2026-07-05",
      "relief_appearances": 14,
      "pitchers_in_relief": 6,
      "pitches_total": 112,
      "appearances_with_pitches": 14,
      "start_relief_unknown": 0,
      "sentence": "14 relief appearances in the 7 days through July 5.",
      "pitchers_sentence": "6 pitchers appeared in relief in the 7 days through July 5.",
      "pitches_sentence": "112 pitches across those 14 relief appearances."
    }
  },
  "absence_sentence": "present only when no relief appearances exist in the lookback"
}
```

When the public freshness block does not provide a usable `data_through` date,
the payload keeps `capability`, `team`, `data_through: null`, `freshness`,
`scope_sentence`, and `relief_by_date: []`. Anchored sections such as
`windows` and `absence_sentence` are omitted.

## Copy Inventory

The server owns every sentence. A later frontend panel should render the
strings verbatim.

- `Covers pitchers currently on the <ABBR> roster per MLB roster data.`
- `<date> - <N> relief appearances, <IP> IP, <pitches> pitches.`
- `<date> - <N> relief appearances, <IP> IP.`
- `<Pitcher Name> - <IP> IP, <pitches> pitches, <K> K, <BB> BB.`
- `<Pitcher Name> - <IP> IP, <K> K, <BB> BB.`
- `<N> relief appearances in the <window> days through <anchor>.`
- `<N> pitchers appeared in relief in the <window> days through <anchor>.`
- `<N> pitches across those <M> relief appearances.`
- `Pitch count unavailable for <missing> of <total> relief appearances; <known> pitches across the other <K>.`
- `Start/relief status unavailable for <N> of <M> appearances in the <window> days through <anchor>; relief totals cover the other <K>.`
- `No relief appearances in the <LOOKBACK_DAYS> days through <anchor>.`

Every windowed sentence is anchored with `through <anchor>`, and every dated
group or appearance carries the game date.

## Source Separation

The route and service do not import, wrap, redact, or reuse the internal team
review endpoint or service. Import guards enforce the public service's source
list and the reverse direction from internal evidence/read/audit modules.

## Frontend Sequencing

The team relief-work panel is deferred to a later branch. This branch does not
wire any frontend component and does not change Data & Trust, sync, methodology,
static team previews, existing public routes, or legacy fatigue/availability
surfaces.
