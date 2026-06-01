// Canonical fatigue-model definitions for the frontend.
//
// The authoritative source of truth is the backend scoring engine
// (backend/services/fatigue.py), surfaced to users via the /api/methodology
// endpoint. These constants mirror that model so component-level UI — such as
// the pitcher detail score breakdown — stays consistent with it instead of
// hardcoding its own (and drifting out of sync).
//
// Leverage Index is intentionally absent: the model does not use it. MLB Stats
// API game logs do not expose reliable leverage data, so it was removed from
// the composite rather than faked. Do not reintroduce it here.

export const FATIGUE_FACTORS = [
  { key: 'pitch_count', label: 'Pitch Count Load',     short: 'Pitches', scoreField: 'pitch_count_score', weight: 35 },
  { key: 'rest_days',   label: 'Rest Days',            short: 'Rest',    scoreField: 'rest_days_score',   weight: 30 },
  { key: 'appearances', label: 'Appearance Frequency', short: 'Apps',    scoreField: 'appearances_score', weight: 20 },
  { key: 'innings',     label: 'Innings Load',         short: 'Innings', scoreField: 'innings_score',     weight: 15 },
]

// Risk tiers mirror get_risk_level() / RISK_LEVELS in services/fatigue.py.
// Descriptions are framed as workload/fatigue risk — this is a transparent
// workload heuristic, not an injury or performance prediction.
export const RISK_TIERS = [
  { level: 'LOW',      range: '0–24',   blurb: 'Fresh and available.' },
  { level: 'MODERATE', range: '25–49',  blurb: 'Some recent use — monitor workload.' },
  { level: 'HIGH',     range: '50–80',  blurb: 'Elevated workload — use with caution.' },
  { level: 'CRITICAL', range: '81–100', blurb: 'Heavy recent workload — rest recommended.' },
]

export const RISK_BLURB = RISK_TIERS.reduce((acc, t) => {
  acc[t.level] = t.blurb
  return acc
}, {})
