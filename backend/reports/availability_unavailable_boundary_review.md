# Availability Unavailable Boundary Review

Generated at: 2026-06-02T00:19:57.537692+00:00
Reference date: 2026-06-01

This report reviews pitchers moved by Candidate C from the unavailable-threshold experiment.
Candidate C raises the Unavailable three-day pitch threshold from 80 to 90.
This report does not change thresholds, classifier logic, API behavior, dashboard behavior, or frontend behavior.

## Summary

Total moved pitchers: 57
Baseline Unavailable bucket: 163
Percentage of Unavailable bucket affected: 35.0%
Recommendation category: Supports further review

### Status Transitions

| Transition | Count |
|---|---:|
| Avoid -> Avoid | 99 |
| Limited -> Limited | 174 |
| Monitor -> Monitor | 268 |
| Unavailable -> Avoid | 57 |
| Unavailable -> Unavailable | 106 |

## Why Did These Pitchers Move?

All moved pitchers had 80 to 89 pitches in 3 days.
They crossed the baseline Unavailable 3-day pitch threshold of 80 but did not
cross Candidate C threshold of 90. No moved pitcher retained another Candidate C
Unavailable severe signal.

Moved pitchers with fatigue score >= 85: 18
Moved pitchers who pitched yesterday: 0
Moved pitchers with 4+ appearances in 5 days: 0

### Moved Cases By 3-Day Pitch Count

| 3-day pitches | Count |
|---|---:|
| 80 | 6 |
| 81 | 3 |
| 82 | 8 |
| 83 | 3 |
| 84 | 5 |
| 85 | 10 |
| 86 | 7 |
| 87 | 6 |
| 88 | 7 |
| 89 | 2 |

### Baseline Severe Signal Count Distribution

| Signal count | Count |
|---|---:|
| 1 | 57 |

### Candidate Severe Signal Count Distribution

| Signal count | Count |
|---|---:|
| 0 | 57 |

## Closest Boundary Examples

### Threshold Sensitivity By 3-Day Pitch Count

| 3-day pitches | Total | Baseline Unavailable | Candidate Avoid | Candidate Unavailable | Moved Unavailable -> Avoid | Example moved pitchers |
|---:|---:|---:|---:|---:|---:|---|
| 80 | 6 | 6 | 6 | 0 | 6 | Dean Kremer; Chris Murphy; Hayden Wesneski |
| 81 | 3 | 3 | 3 | 0 | 3 | David Festa; Carmen Mlodzinski; DJ Herz |
| 82 | 8 | 8 | 8 | 0 | 8 | Brandon Young; Ryan Feltner; Brandon Walter |
| 83 | 3 | 3 | 3 | 0 | 3 | Luis Gil; Matt Waldron; Andrew Alvarez |
| 84 | 5 | 5 | 5 | 0 | 5 | Connor Prielipp; Hunter Barco; Bryan Woo |
| 85 | 10 | 10 | 10 | 0 | 10 | Spencer Strider; Jake Bennett; Jose Quintana |
| 86 | 7 | 7 | 7 | 0 | 7 | Joey Wentz; Kutter Crawford; Andrew Abbott |
| 87 | 6 | 6 | 6 | 0 | 6 | Aaron Civale; Grant Holmes; Eduardo Rodriguez |
| 88 | 7 | 7 | 7 | 0 | 7 | J.T. Ginn; Kyle Bradish; Logan Allen |
| 89 | 2 | 2 | 2 | 0 | 2 | Max Fried; Trevor McDonald |
| 90 | 11 | 11 | 0 | 11 | 0 | none |
| 91 | 8 | 8 | 0 | 8 | 0 | none |

### Closest Boundary Examples

### 80 pitches in 3 days

| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Andrew Painter | PHI | Unavailable | Avoid | 59.1 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 59.1 |
| Chris Murphy | CWS | Unavailable | Avoid | 57.5 | 0 | 80 | 80 | 2 | 2 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; 2 appearances in 3 days; 2 appearances in 5 days; No rest since last appearance; Fatigue score is 57.5 |
| David Peterson | NYM | Unavailable | Avoid | 53.9 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 53.9 |

### 81 pitches in 3 days

| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Carmen Mlodzinski | PIT | Unavailable | Avoid | 54.5 | 0 | 81 | 81 | 1 | 1 | 0 | 81 pitches in 3 days; 81 pitches in 5 days; No rest since last appearance; Fatigue score is 54.5 |
| DJ Herz | WSH | Unavailable | Avoid | 85.5 | 0 | 81 | 81 | 1 | 1 | 0 | 81 pitches in 3 days; 81 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| David Festa | MIN | Unavailable | Avoid | 60.2 | 0 | 81 | 81 | 1 | 1 | 0 | 81 pitches in 3 days; 81 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |

### 89 pitches in 3 days

| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Max Fried | NYY | Unavailable | Avoid | 65.3 | 0 | 89 | 89 | 1 | 1 | 0 | 89 pitches in 3 days; 89 pitches in 5 days; No rest since last appearance; Fatigue score is 65.3 |
| Trevor McDonald | SF | Unavailable | Avoid | 85.5 | 0 | 89 | 89 | 1 | 1 | 0 | 89 pitches in 3 days; 89 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |

### 90 pitches in 3 days

| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Anthony Kay | CWS | Unavailable | Unavailable | 58 | 0 | 90 | 90 | 1 | 1 | 0 | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 58 |
| Bryce Elder | ATL | Unavailable | Unavailable | 85.1 | 0 | 90 | 90 | 1 | 1 | 0 | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Cody Bradford | TEX | Unavailable | Unavailable | 85.5 | 0 | 90 | 90 | 1 | 1 | 0 | 90 pitches in 3 days; 90 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |

### 91 pitches in 3 days

| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Andre Pallante | STL | Unavailable | Unavailable | 65.6 | 0 | 91 | 91 | 1 | 1 | 0 | 91 pitches in 3 days; 91 pitches in 5 days; No rest since last appearance; Fatigue score is 65.6 |
| Drew Rasmussen | TB | Unavailable | Unavailable | 61.9 | 0 | 91 | 91 | 1 | 1 | 0 | 91 pitches in 3 days; 91 pitches in 5 days; No rest since last appearance; Fatigue score is 61.9 |
| Jack Flaherty | DET | Unavailable | Unavailable | 82.1 | 0 | 91 | 91 | 1 | 1 | 0 | 91 pitches in 3 days; 91 pitches in 5 days; No rest since last appearance; Fatigue score is 82.1 |

## Detailed Boundary Cases

### All Moved Pitchers

| Pitcher | Team | Original | Candidate | Fatigue | Yday | 3-day | 5-day | App 3 | App 5 | Rest | Reasons |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Andrew Painter | PHI | Unavailable | Avoid | 59.1 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 59.1 |
| Chris Murphy | CWS | Unavailable | Avoid | 57.5 | 0 | 80 | 80 | 2 | 2 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; 2 appearances in 3 days; 2 appearances in 5 days; No rest since last appearance; Fatigue score is 57.5 |
| David Peterson | NYM | Unavailable | Avoid | 53.9 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 53.9 |
| Dean Kremer | BAL | Unavailable | Avoid | 59.1 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 59.1 |
| Elmer Rodríguez | NYY | Unavailable | Avoid | 55.4 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 55.4 |
| Hayden Wesneski | HOU | Unavailable | Avoid | 55.8 | 0 | 80 | 80 | 1 | 1 | 0 | 80 pitches in 3 days; 80 pitches in 5 days; No rest since last appearance; Fatigue score is 55.8 |
| Carmen Mlodzinski | PIT | Unavailable | Avoid | 54.5 | 0 | 81 | 81 | 1 | 1 | 0 | 81 pitches in 3 days; 81 pitches in 5 days; No rest since last appearance; Fatigue score is 54.5 |
| DJ Herz | WSH | Unavailable | Avoid | 85.5 | 0 | 81 | 81 | 1 | 1 | 0 | 81 pitches in 3 days; 81 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| David Festa | MIN | Unavailable | Avoid | 60.2 | 0 | 81 | 81 | 1 | 1 | 0 | 81 pitches in 3 days; 81 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |
| Brandon Sproat | MIL | Unavailable | Avoid | 56.6 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 56.6 |
| Brandon Walter | HOU | Unavailable | Avoid | 85.5 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Brandon Young | BAL | Unavailable | Avoid | 55.8 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 55.8 |
| Carson Whisenhunt | SF | Unavailable | Avoid | 85.1 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Kyle Leahy | STL | Unavailable | Avoid | 59.9 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 59.9 |
| Ryan Feltner | COL | Unavailable | Avoid | 55.8 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 55.8 |
| Tyler Mahle | SF | Unavailable | Avoid | 60 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 60 |
| Tylor Megill | NYM | Unavailable | Avoid | 85.5 | 0 | 82 | 82 | 1 | 1 | 0 | 82 pitches in 3 days; 82 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Andrew Alvarez | WSH | Unavailable | Avoid | 85.5 | 0 | 83 | 83 | 1 | 1 | 0 | 83 pitches in 3 days; 83 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Luis Gil | NYY | Unavailable | Avoid | 56.5 | 0 | 83 | 83 | 1 | 1 | 0 | 83 pitches in 3 days; 83 pitches in 5 days; No rest since last appearance; Fatigue score is 56.5 |
| Matt Waldron | SD | Unavailable | Avoid | 59.8 | 0 | 83 | 83 | 1 | 1 | 0 | 83 pitches in 3 days; 83 pitches in 5 days; No rest since last appearance; Fatigue score is 59.8 |
| Bryan Woo | SEA | Unavailable | Avoid | 85.1 | 0 | 84 | 84 | 1 | 1 | 0 | 84 pitches in 3 days; 84 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Connor Prielipp | MIN | Unavailable | Avoid | 60 | 0 | 84 | 84 | 1 | 1 | 0 | 84 pitches in 3 days; 84 pitches in 5 days; No rest since last appearance; Fatigue score is 60 |
| Hunter Barco | PIT | Unavailable | Avoid | 57 | 0 | 84 | 84 | 1 | 1 | 0 | 84 pitches in 3 days; 84 pitches in 5 days; No rest since last appearance; Fatigue score is 57 |
| Kumar Rocker | TEX | Unavailable | Avoid | 64.2 | 0 | 84 | 84 | 1 | 1 | 0 | 84 pitches in 3 days; 84 pitches in 5 days; No rest since last appearance; Fatigue score is 64.2 |
| Zack Littell | WSH | Unavailable | Avoid | 54.7 | 0 | 84 | 84 | 1 | 1 | 0 | 84 pitches in 3 days; 84 pitches in 5 days; No rest since last appearance; Fatigue score is 54.7 |
| Bubba Chandler | PIT | Unavailable | Avoid | 60.2 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |
| Cristopher Sánchez | PHI | Unavailable | Avoid | 64 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 64 |
| Jacob Misiorowski | MIL | Unavailable | Avoid | 85.1 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Jake Bennett | BOS | Unavailable | Avoid | 60.2 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |
| Jared Jones | PIT | Unavailable | Avoid | 85.5 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Joe Musgrove | SD | Unavailable | Avoid | 85.5 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Jose Quintana | COL | Unavailable | Avoid | 85.1 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Michael Lorenzen | COL | Unavailable | Avoid | 60.6 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.6 |
| Spencer Strider | ATL | Unavailable | Avoid | 85.5 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Taijuan Walker | PHI | Unavailable | Avoid | 60.2 | 0 | 85 | 85 | 1 | 1 | 0 | 85 pitches in 3 days; 85 pitches in 5 days; No rest since last appearance; Fatigue score is 60.2 |
| Andrew Abbott | CIN | Unavailable | Avoid | 64.2 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 64.2 |
| Hunter Brown | HOU | Unavailable | Avoid | 85.5 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Joey Wentz | ATL | Unavailable | Avoid | 85.5 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Keider Montero | DET | Unavailable | Avoid | 60.9 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 60.9 |
| Kutter Crawford | BOS | Unavailable | Avoid | 85.5 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |
| Ryan Weathers | NYY | Unavailable | Avoid | 61.2 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 61.2 |
| Trevor Williams | WSH | Unavailable | Avoid | 55.7 | 0 | 86 | 86 | 1 | 1 | 0 | 86 pitches in 3 days; 86 pitches in 5 days; No rest since last appearance; Fatigue score is 55.7 |
| Aaron Civale | ATH | Unavailable | Avoid | 60.6 | 0 | 87 | 87 | 1 | 1 | 0 | 87 pitches in 3 days; 87 pitches in 5 days; No rest since last appearance; Fatigue score is 60.6 |
| Braxton Ashcraft | PIT | Unavailable | Avoid | 57.7 | 0 | 87 | 87 | 1 | 1 | 0 | 87 pitches in 3 days; 87 pitches in 5 days; No rest since last appearance; Fatigue score is 57.7 |
| Eduardo Rodriguez | AZ | Unavailable | Avoid | 58.1 | 0 | 87 | 87 | 1 | 1 | 0 | 87 pitches in 3 days; 87 pitches in 5 days; No rest since last appearance; Fatigue score is 58.1 |
| Grant Holmes | ATL | Unavailable | Avoid | 60.6 | 0 | 87 | 87 | 1 | 1 | 0 | 87 pitches in 3 days; 87 pitches in 5 days; No rest since last appearance; Fatigue score is 60.6 |
| Quinn Priester | MIL | Unavailable | Avoid | 61.5 | 0 | 87 | 87 | 1 | 1 | 0 | 87 pitches in 3 days; 87 pitches in 5 days; No rest since last appearance; Fatigue score is 61.5 |
| Yoshinobu Yamamoto | LAD | Unavailable | Avoid | 61.1 | 0 | 87 | 87 | 1 | 1 | 0 | 87 pitches in 3 days; 87 pitches in 5 days; No rest since last appearance; Fatigue score is 61.1 |
| Bailey Ober | MIN | Unavailable | Avoid | 85.1 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| J.T. Ginn | ATH | Unavailable | Avoid | 85.1 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Jesús Luzardo | PHI | Unavailable | Avoid | 65.1 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 65.1 |
| Joe Ryan | MIN | Unavailable | Avoid | 64.6 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 64.6 |
| Kyle Bradish | BAL | Unavailable | Avoid | 61.3 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 61.3 |
| Logan Allen | CLE | Unavailable | Avoid | 57.9 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 57.9 |
| Simeon Woods Richardson | MIN | Unavailable | Avoid | 85.1 | 0 | 88 | 88 | 1 | 1 | 0 | 88 pitches in 3 days; 88 pitches in 5 days; No rest since last appearance; Fatigue score is 85.1 |
| Max Fried | NYY | Unavailable | Avoid | 65.3 | 0 | 89 | 89 | 1 | 1 | 0 | 89 pitches in 3 days; 89 pitches in 5 days; No rest since last appearance; Fatigue score is 65.3 |
| Trevor McDonald | SF | Unavailable | Avoid | 85.5 | 0 | 89 | 89 | 1 | 1 | 0 | 89 pitches in 3 days; 89 pitches in 5 days; No rest since last appearance; Fatigue score is 85.5 |

## Review Guidance

- Supports further review means the transition set is coherent enough to justify human review.
- Neutral means the evidence is inconclusive.
- Evidence against change means the boundary review found a trust or workload-severity concern.

This report is descriptive. It does not recommend threshold adoption.
