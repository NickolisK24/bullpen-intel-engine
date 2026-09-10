# Availability Unavailable Threshold Experiment

Generated at: 2026-06-02T00:33:33.772221+00:00
Reference date: 2026-06-01

This experiment compares current Availability Engine thresholds against
Unavailable-only candidate changes. It does not modify production
thresholds, fatigue scoring, API behavior, dashboard behavior, or frontend behavior.

## Current Unavailable Rules

| Rule | Condition |
|---|---|
| Pitches yesterday | `pitches_yesterday >= 50` |
| Three-day pitch volume | `pitches_last_3_days >= 90` |
| Five-day appearance/workload combination | `appearances_last_5_days >= 4 and pitches_last_5_days >= 75` |
| Critical fatigue plus heavy yesterday workload | `fatigue_score >= 85.0 and pitches_yesterday >= 35` |

## Baseline Snapshot Distribution

Latest-workload snapshot output is validation-only and not current bullpen availability.

### Baseline Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

### Baseline Confidence Distribution

| Value | Count |
|---|---:|
| high | 640 |
| low | 64 |

### Baseline Data State Distribution

| Value | Count |
|---|---:|
| fresh | 640 |
| missing | 64 |

### Baseline Reason Categories

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

## Candidate Overview

| Candidate | Changed rule | Unavailable | Delta | Moved from Unavailable |
|---|---|---:|---:|---:|
| Candidate A: raise Unavailable fatigue threshold | unavailable_fatigue_score: 85.0 -> 90.0 | 106 | 0 | 0 |
| Candidate B: raise Unavailable yesterday pitch threshold | unavailable_pitches_yesterday: 50 -> 55 | 106 | 0 | 0 |
| Candidate C: adopted Unavailable three-day pitch threshold | adopted production baseline: unavailable_pitches_last_3_days = 90 | 106 | 0 | 0 |
| Candidate D: raise Unavailable five-day combo pitch threshold | unavailable_multi_day_pitch_threshold: 75 -> 85 when appearances_last_5_days >= 4 | 106 | 0 | 0 |
| Candidate E: require two severe signals for Unavailable | Require at least two current Unavailable rule signals before preserving Unavailable | 0 | -106 | 106 |

## Candidate A: raise Unavailable fatigue threshold

Changed rule: unavailable_fatigue_score: 85.0 -> 90.0

### Candidate Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

### Status Delta From Baseline

| Status | Delta |
|---|---:|
| Available | 0 |
| Monitor | 0 |
| Limited | 0 |
| Avoid | 0 |
| Unavailable | 0 |

### Transitions

| Transition | Count |
|---|---:|
| Avoid -> Avoid | 156 |
| Limited -> Limited | 174 |
| Monitor -> Monitor | 268 |
| Unavailable -> Unavailable | 106 |

### Moved From Unavailable

| Candidate status | Count |
|---|---:|
| none | 0 |

### Reason Categories

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

### Changed Examples

| Pitcher | Team | Baseline | Candidate | Fatigue | Yday | 3-day | 5-day | App 5 | Severe signals | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| none |  |  |  |  |  |  |  |  |  |  |

### Boundary Examples

| Pitcher | Team | Status | Input value | Distance | Severe signals | Reasons |
|---|---|---|---:|---:|---|---|
| Grayson Rodriguez | LAA | Unavailable | 85.9 | 4.1 | 4 appearances and 105 pitches in 5 days | 31 pitches yesterday; 76 pitches in 3 days; 105 pitches in 5 days; 3 appearances in 3 days; 4 appearances in 5 days; Back-to-back appearances; 3 appearances in 4 days; No rest since last appearance; Fatigue score is 85.9 |
| Adam Mazur | MIA | Avoid | 85.5 | 4.5 | none | 63 pitches in 3 days; 63 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Andrew Alvarez | WSH | Avoid | 85.5 | 4.5 | none | 83 pitches in 3 days; 83 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Bowden Francis | TOR | Avoid | 85.5 | 4.5 | none | 74 pitches in 3 days; 74 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Bradley Blalock | MIA | Avoid | 85.5 | 4.5 | none | 73 pitches in 3 days; 73 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Brandon Walter | HOU | Avoid | 85.5 | 4.5 | none | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Braxton Garrett | MIA | Unavailable | 85.5 | 4.5 | 93 pitches in 3 days | 93 pitches in 3 days; 93 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Bryce Miller | SEA | Avoid | 85.5 | 4.5 | none | 70 pitches in 3 days; 70 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |

## Candidate B: raise Unavailable yesterday pitch threshold

Changed rule: unavailable_pitches_yesterday: 50 -> 55

### Candidate Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

### Status Delta From Baseline

| Status | Delta |
|---|---:|
| Available | 0 |
| Monitor | 0 |
| Limited | 0 |
| Avoid | 0 |
| Unavailable | 0 |

### Transitions

| Transition | Count |
|---|---:|
| Avoid -> Avoid | 156 |
| Limited -> Limited | 174 |
| Monitor -> Monitor | 268 |
| Unavailable -> Unavailable | 106 |

### Moved From Unavailable

| Candidate status | Count |
|---|---:|
| none | 0 |

### Reason Categories

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

### Changed Examples

| Pitcher | Team | Baseline | Candidate | Fatigue | Yday | 3-day | 5-day | App 5 | Severe signals | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| none |  |  |  |  |  |  |  |  |  |  |

### Boundary Examples

| Pitcher | Team | Status | Input value | Distance | Severe signals | Reasons |
|---|---|---|---:|---:|---|---|
| Michael Kelly | ATH | Unavailable | 35 | 20 | 4 appearances and 106 pitches in 5 days | 35 pitches yesterday; 78 pitches in 3 days; 106 pitches in 5 days; 3 appearances in 3 days; 4 appearances in 5 days; Back-to-back appearances; 3 appearances in 4 days; No rest since last appearance; Fatigue score is 69.6 |
| Cam Sanders | PIT | Avoid | 32 | 23 | none | 32 pitches yesterday; 37 pitches in 3 days; 2 appearances in 3 days; 2 appearances in 5 days; Back-to-back appearances; No rest since last appearance; Fatigue score is 45.5 |
| Grayson Rodriguez | LAA | Unavailable | 31 | 24 | 4 appearances and 105 pitches in 5 days | 31 pitches yesterday; 76 pitches in 3 days; 105 pitches in 5 days; 3 appearances in 3 days; 4 appearances in 5 days; Back-to-back appearances; 3 appearances in 4 days; No rest since last appearance; Fatigue score is 85.9 |
| Kyle Finnegan | DET | Avoid | 29 | 26 | none | 29 pitches yesterday; 46 pitches in 3 days; 62 pitches in 5 days; 2 appearances in 3 days; 3 appearances in 5 days; Back-to-back appearances; No rest since last appearance; Fatigue score is 50.3 |
| Blake Snell | LAD | Avoid | 26 | 29 | none | 26 pitches yesterday; 40 pitches in 3 days; 74 pitches in 5 days; 2 appearances in 3 days; 3 appearances in 5 days; Back-to-back appearances; 3 appearances in 4 days; No rest since last appearance; Fatigue score is 53.2 |
| Cade Winquest | NYY | Avoid | 26 | 29 | none | 26 pitches yesterday; 41 pitches in 3 days; 67 pitches in 5 days; 2 appearances in 3 days; 3 appearances in 5 days; Back-to-back appearances; 3 appearances in 4 days; No rest since last appearance; Fatigue score is 52.6 |
| Michael Petersen | MIA | Avoid | 26 | 29 | none | 26 pitches yesterday; 35 pitches in 3 days; 2 appearances in 3 days; 2 appearances in 5 days; Back-to-back appearances; No rest since last appearance; Fatigue score is 43.9 |
| Grant Anderson | MIL | Limited | 25 | 30 | none | 25 pitches yesterday; 33 pitches in 3 days; 2 appearances in 3 days; 2 appearances in 5 days; Back-to-back appearances; No rest since last appearance; Fatigue score is 42.2 |

## Candidate C: adopted Unavailable three-day pitch threshold

Changed rule: adopted production baseline: unavailable_pitches_last_3_days = 90

### Candidate Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

### Status Delta From Baseline

| Status | Delta |
|---|---:|
| Available | 0 |
| Monitor | 0 |
| Limited | 0 |
| Avoid | 0 |
| Unavailable | 0 |

### Transitions

| Transition | Count |
|---|---:|
| Avoid -> Avoid | 156 |
| Limited -> Limited | 174 |
| Monitor -> Monitor | 268 |
| Unavailable -> Unavailable | 106 |

### Moved From Unavailable

| Candidate status | Count |
|---|---:|
| none | 0 |

### Reason Categories

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

### Changed Examples

| Pitcher | Team | Baseline | Candidate | Fatigue | Yday | 3-day | 5-day | App 5 | Severe signals | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| none |  |  |  |  |  |  |  |  |  |  |

### Boundary Examples

| Pitcher | Team | Status | Input value | Distance | Severe signals | Reasons |
|---|---|---|---:|---:|---|---|
| Anthony Kay | CWS | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 58 |
| Bryce Elder | ATL | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Cody Bradford | TEX | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Freddy Peralta | NYM | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 65 |
| Garrett Crochet | BOS | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 65.5 |
| Jack Kochanowicz | LAA | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 65.5 |
| Mick Abel | MIN | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Shane Bieber | TOR | Unavailable | 90 | 0 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |

## Candidate D: raise Unavailable five-day combo pitch threshold

Changed rule: unavailable_multi_day_pitch_threshold: 75 -> 85 when appearances_last_5_days >= 4

### Candidate Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 156 |
| Unavailable | 106 |

### Status Delta From Baseline

| Status | Delta |
|---|---:|
| Available | 0 |
| Monitor | 0 |
| Limited | 0 |
| Avoid | 0 |
| Unavailable | 0 |

### Transitions

| Transition | Count |
|---|---:|
| Avoid -> Avoid | 156 |
| Limited -> Limited | 174 |
| Monitor -> Monitor | 268 |
| Unavailable -> Unavailable | 106 |

### Moved From Unavailable

| Candidate status | Count |
|---|---:|
| none | 0 |

### Reason Categories

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

### Changed Examples

| Pitcher | Team | Baseline | Candidate | Fatigue | Yday | 3-day | 5-day | App 5 | Severe signals | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| none |  |  |  |  |  |  |  |  |  |  |

### Boundary Examples

| Pitcher | Team | Status | Input value | Distance | Severe signals | Reasons |
|---|---|---|---:|---:|---|---|
| Bubba Chandler | PIT | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |
| Cristopher Sánchez | PHI | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 64 |
| Jacob Misiorowski | MIL | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Jake Bennett | BOS | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |
| Jared Jones | PIT | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Joe Musgrove | SD | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Jose Quintana | COL | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Michael Lorenzen | COL | Avoid | 85 | 0 | none | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.6 |

## Candidate E: require two severe signals for Unavailable

Changed rule: Require at least two current Unavailable rule signals before preserving Unavailable

### Candidate Status Distribution

| Value | Count |
|---|---:|
| Monitor | 268 |
| Limited | 174 |
| Avoid | 262 |

### Status Delta From Baseline

| Status | Delta |
|---|---:|
| Available | 0 |
| Monitor | 0 |
| Limited | 0 |
| Avoid | +106 |
| Unavailable | -106 |

### Transitions

| Transition | Count |
|---|---:|
| Avoid -> Avoid | 156 |
| Limited -> Limited | 174 |
| Monitor -> Monitor | 268 |
| Unavailable -> Avoid | 106 |

### Moved From Unavailable

| Candidate status | Count |
|---|---:|
| Avoid | 106 |

### Reason Categories

| Category | Count |
|---|---:|
| pitch_count | 671 |
| appearance_frequency | 1170 |
| fatigue | 569 |
| data_state | 64 |

### Changed Examples

| Pitcher | Team | Baseline | Candidate | Fatigue | Yday | 3-day | 5-day | App 5 | Severe signals | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| Luis Severino | ATH | Unavailable | Avoid | 72.6 | 0 | 103 | 103 | 1 | 103 pitches in 3 days | 103 pitches in 3 days; 103 pitches in 5 days; No rest since last appearance; Fatigue score is 72.6 |
| Mason Barnett | ATH | Unavailable | Avoid | 66.6 | 0 | 97 | 97 | 1 | 97 pitches in 3 days | 97 pitches in 3 days; 97 pitches in 5 days; No rest since last appearance; Fatigue score is 66.6 |
| Michael Kelly | ATH | Unavailable | Avoid | 69.6 | 35 | 78 | 106 | 4 | 4 appearances and 106 pitches in 5 days | 35 pitches yesterday; 78 pitches in 3 days; 106 pitches in 5 days; 3 appearances in 3 days; 4 appearances in 5 days; Back-to-back appearances; 3 appearances in 4 days; No rest since last appearance; Fatigue score is 69.6 |
| Bryce Elder | ATL | Unavailable | Avoid | 85.1 | 0 | 90 | 90 | 1 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Chris Sale | ATL | Unavailable | Avoid | 71.3 | 0 | 100 | 100 | 1 | 100 pitches in 3 days | 100 pitches in 3 days; 100 pitches in 5 days; No rest since last appearance; Fatigue score is 71.3 |
| Hurston Waldrep | ATL | Unavailable | Avoid | 85.5 | 0 | 92 | 92 | 1 | 92 pitches in 3 days | 92 pitches in 3 days; 92 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Spencer Schwellenbach | ATL | Unavailable | Avoid | 85.5 | 0 | 90 | 90 | 1 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Merrill Kelly | AZ | Unavailable | Avoid | 69.9 | 0 | 104 | 104 | 1 | 104 pitches in 3 days | 104 pitches in 3 days; 104 pitches in 5 days; No rest since last appearance; Fatigue score is 69.9 |
| Ryne Nelson | AZ | Unavailable | Avoid | 63.5 | 0 | 93 | 93 | 1 | 93 pitches in 3 days | 93 pitches in 3 days; 93 pitches in 5 days; No rest since last appearance; Fatigue score is 63.5 |
| Zac Gallen | AZ | Unavailable | Avoid | 85.1 | 0 | 95 | 95 | 1 | 95 pitches in 3 days | 95 pitches in 3 days; 95 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Chris Bassitt | BAL | Unavailable | Avoid | 67.4 | 0 | 94 | 94 | 1 | 94 pitches in 3 days | 94 pitches in 3 days; 94 pitches in 5 days; No rest since last appearance; Fatigue score is 67.4 |
| Shane Baz | BAL | Unavailable | Avoid | 67.2 | 0 | 98 | 98 | 1 | 98 pitches in 3 days | 98 pitches in 3 days; 98 pitches in 5 days; No rest since last appearance; Fatigue score is 67.2 |

### Boundary Examples

| Pitcher | Team | Status | Input value | Distance | Severe signals | Reasons |
|---|---|---|---:|---:|---|---|
| Aaron Nola | PHI | Unavailable | 1 | 1 | 101 pitches in 3 days | 101 pitches in 3 days; 101 pitches in 5 days; No rest since last appearance; Fatigue score is 65.2 |
| Andre Pallante | STL | Unavailable | 1 | 1 | 91 pitches in 3 days | 91 pitches in 3 days; 91 pitches in 5 days; No rest since last appearance; Fatigue score is 65.6 |
| Anthony Kay | CWS | Unavailable | 1 | 1 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 58 |
| Braxton Garrett | MIA | Unavailable | 1 | 1 | 93 pitches in 3 days | 93 pitches in 3 days; 93 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Bryce Elder | ATL | Unavailable | 1 | 1 | 90 pitches in 3 days | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Cade Cavalli | WSH | Unavailable | 1 | 1 | 97 pitches in 3 days | 97 pitches in 3 days; 97 pitches in 5 days; No rest since last appearance; Fatigue score is 69.1 |
| Cam Schlittler | NYY | Unavailable | 1 | 1 | 92 pitches in 3 days | 92 pitches in 3 days; 92 pitches in 5 days; No rest since last appearance; Fatigue score is 66.2 |
| Chad Patrick | MIL | Unavailable | 1 | 1 | 98 pitches in 3 days | 98 pitches in 3 days; 98 pitches in 5 days; No rest since last appearance; Fatigue score is 66.4 |

## Recommendation

Recommendation: Needs more data

- Current-mode output is stale/missing dominated, so production tuning should not rely on current-mode distribution alone.
- Largest one-variable candidate moved 0 pitchers out of Unavailable.
- The multi-signal gate moved 106 pitchers, but it changes rule semantics rather than one threshold.
- Review near-boundary pitcher examples before adopting any future production threshold change.

Any candidate threshold still requires human review and approval before
production adoption.
