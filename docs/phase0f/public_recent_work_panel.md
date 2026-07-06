# Phase 0F Branch 03 Public Recent Work Endpoint

## Gate Status

Phase 0B public evidence approval remains closed. This branch adds a narrow
public recent-work endpoint for a future Pitcher Detail panel, but it does not
publish evidence objects, citations, rule identifiers, read components,
recompute status, internal limitations, readiness notes, reconciliation content,
or any internal source-family vocabulary.

## Ratified Branch Constraints

- C1: public evidence surfacing remains closed until the Phase 0B legal/source
  gate approves it.
- C2: the endpoint mirrors the existing public game-log class exactly and does
  not add game-type filtering.
- C3: source separation is structural; public recent-work code cannot import,
  query, or serialize internal evidence/read/audit resources.
- C4: the bounded public windows are versioned constants in the service module.

## Public Contract

`GET /api/bullpen/pitchers/<pitcher_id>/recent-work`

The endpoint is public, read-only, and backend-only in this branch. The payload
contains only already-public data classes:

- pitcher identity
- MLB roster status already used by public surfaces
- public freshness/data-through block
- public game-log appearance lines
- server-authored neutral copy derived from those public lines

No frontend is connected in this branch.

## Payload Schema

```json
{
  "capability": "public_recent_work",
  "pitcher": {
    "id": 1,
    "mlb_id": 12345,
    "full_name": "Pitcher Name",
    "team_id": 110,
    "team_name": "Team Name",
    "team_abbreviation": "TST"
  },
  "data_through": "2026-07-05",
  "freshness": "existing public freshness block reused by reference",
  "roster_status": {
    "status": "Active",
    "source": "mlb_roster_data",
    "sentence": "On the active roster per MLB roster data."
  },
  "last_appearance": {
    "game_date": "2026-07-03",
    "opponent": "Boston Red Sox",
    "opponent_abbreviation": "BOS",
    "innings_pitched": 1.6666666666666667,
    "innings_pitched_outs": 5,
    "pitches_thrown": 24,
    "strikeouts": 2,
    "walks": 1,
    "hits_allowed": 2,
    "runs_allowed": 1,
    "save": true,
    "hold": false,
    "blown_save": false,
    "win": false,
    "loss": false,
    "save_situation": false,
    "sentence": "Last appearance: July 3 vs BOS — 1.2 IP, 24 pitches, 2 K, 1 BB, 2 H, 1 R.",
    "timing_sentence": "That appearance came 2 days before July 5.",
    "fact_sentences": []
  },
  "absence_sentence": "present only when last_appearance is null within the lookback",
  "recent_appearances": [
    {
      "game_date": "2026-07-03",
      "opponent": "Boston Red Sox",
      "opponent_abbreviation": "BOS",
      "innings_pitched": 1.6666666666666667,
      "innings_pitched_outs": 5,
      "pitches_thrown": 24,
      "strikeouts": 2,
      "walks": 1,
      "hits_allowed": 2,
      "runs_allowed": 1,
      "save": true,
      "hold": false,
      "blown_save": false,
      "win": false,
      "loss": false,
      "save_situation": false
    }
  ],
  "workload": {
    "window_7": {
      "through": "2026-07-05",
      "appearances": 3,
      "pitches_total": 61,
      "appearances_with_pitches": 3,
      "sentence": "3 appearances in the 7 days through July 5.",
      "pitches_sentence": "61 pitches across those 3 appearances."
    },
    "window_14": {
      "through": "2026-07-05",
      "appearances": 0,
      "pitches_total": 0,
      "appearances_with_pitches": 0,
      "sentence": "0 appearances in the 14 days through July 5."
    }
  }
}
```

When the public freshness gate has no data-through date, `data_through` is
`null`, `freshness` is still present, `last_appearance` is `null`,
`recent_appearances` is empty, and anchored fields such as `workload` and
`absence_sentence` are omitted.

## Constants

- `RECENT_LINES_MAX = 8`
- `LOOKBACK_DAYS = 30`
- `WINDOW_DAYS = (7, 14)`

The anchor date is the public published data-through date from the existing
board freshness helper. The endpoint never uses host-local today as the anchor.

## Copy Inventory

The server owns all prose for this endpoint. The future panel should render
these strings as received.

- `On the active roster per MLB roster data.`
- `Roster status: <status> per MLB roster data.`
- `Roster status unavailable.`
- `Last appearance: <date> vs <opponent> — <IP> IP, <pitches> pitches, <K> K, <BB> BB.`
- `Last appearance: <date> vs <opponent> — <IP> IP, <K> K, <BB> BB.`
- `That appearance came <N> days before <anchor>.`
- `That appearance came 1 day before <anchor>.`
- `That appearance came on <anchor>.`
- `Recorded a save (<date>).`
- `Recorded a hold (<date>).`
- `Charged with a blown save (<date>).`
- `Credited with the win (<date>).`
- `Charged with the loss (<date>).`
- `No appearances in the 30 days through <anchor>.`
- `<N> appearances in the <window> days through <anchor>.`
- `1 appearance in the <window> days through <anchor>.`
- `<N> pitches across those <M> appearances.`
- `1 pitch across those 1 appearance.`
- `Pitch count unavailable for <missing> of <total> appearances; <known_pitches> pitches across the other <known>.`
- `Pitch count unavailable for 1 of 1 appearance; 0 pitches across the other 0.`

The roster status fields are already public through the pitcher model and public
roster surfaces. Missing status remains explicitly unknown through the
`Roster status unavailable.` sentence instead of being inferred from workload.

## Source Separation

The service may import only the public game-log model, the public pitcher model,
the existing public freshness helper, date/stdlib utilities, and SQLAlchemy
query helpers. It does not import or query evidence, read, audit, reconciliation,
or internal pitcher-evidence services.

Import-guard tests enforce both directions: the public recent-work module cannot
depend on internal evidence/read/audit modules, and internal evidence/read/audit
modules cannot import this public endpoint or serializer.

## Frontend Sequencing

Frontend Pitcher Detail integration remains blocked for a later Phase 0F branch.
This branch does not modify `PitcherDetail.jsx`, public pages, freshness display
logic, sync behavior, or Data & Trust.
