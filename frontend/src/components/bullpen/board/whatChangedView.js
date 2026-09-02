import { formatDateOnly } from '../../../utils/dateDisplay'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
const numberValue = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null

function changeKey(change, index) {
  return `${change?.type || 'change'}-${change?.pitcher_id ?? 'unknown'}-${change?.game_date || index}-${index}`
}

function teamStateRows(change) {
  if (change?.type !== 'team_state_change') return []
  const fromLabel = textValue(change.from_label)
  const toLabel = textValue(change.to_label)
  if (!fromLabel || !toLabel) return []
  return [{
    key: 'team-state-change',
    transition: `${fromLabel} → ${toLabel}`,
    summary: textValue(change.summary),
    fromDate: textValue(change.from_date),
    fromDateLabel: formatDateOnly(change.from_date, { month: 'short' }),
    toDate: textValue(change.to_date),
    toDateLabel: formatDateOnly(change.to_date, { month: 'short' }),
  }]
}

function restStatusRows(change) {
  if (change?.type !== 'rest_status_change') return []
  const transition = textValue(change.transition)
  if (!transition) return []
  return [{
    key: 'rest-status-change',
    transition,
    summary: textValue(change.summary),
    fromDate: textValue(change.from_date),
    fromDateLabel: formatDateOnly(change.from_date, { month: 'short' }),
    toDate: textValue(change.to_date),
    toDateLabel: formatDateOnly(change.to_date, { month: 'short' }),
  }]
}

function teamStateComparisonView(comparison) {
  const source = comparison && typeof comparison === 'object' ? comparison : {}
  return {
    status: textValue(source.status),
    limitation: textValue(source.limitation),
  }
}

function armReadRows(changes) {
  return changes.flatMap((change, index) => {
    if (change?.type !== 'arm_read_change' || change?.semantic_family !== 'public_arm_read') return []
    const fromRead = change.from_read && typeof change.from_read === 'object' ? change.from_read : {}
    const toRead = change.to_read && typeof change.to_read === 'object' ? change.to_read : {}
    const fromLabel = textValue(fromRead.label)
    const toLabel = textValue(toRead.label)
    if (!fromLabel || !toLabel) return []
    return [{
      key: changeKey(change, index),
      pitcherId: change.pitcher_id ?? null,
      subject: textValue(change.pitcher_name) || 'Arm unavailable',
      transition: `${fromLabel} → ${toLabel}`,
      summary: textValue(change.summary),
      fromDate: textValue(change.from_date),
      fromDateLabel: formatDateOnly(change.from_date, { month: 'short' }),
      toDate: textValue(change.to_date),
      toDateLabel: formatDateOnly(change.to_date, { month: 'short' }),
    }]
  })
}

function appearanceRows(changes) {
  return changes.flatMap((change, index) => {
    if (change?.type !== 'appearance') return []
    const pitches = numberValue(change.pitches)
    return [{
      key: changeKey(change, index),
      pitcherId: change.pitcher_id ?? null,
      subject: textValue(change.pitcher_name) || 'Arm unavailable',
      gameDate: textValue(change.game_date),
      dateLabel: formatDateOnly(change.game_date, { month: 'short' }),
      pitches,
      summary: textValue(change.summary),
    }]
  })
}

export function getWhatChangedView(payload) {
  const source = payload && typeof payload === 'object' ? payload : {}
  const comparison = source.comparison && typeof source.comparison === 'object'
    ? source.comparison
    : {}
  const changes = Array.isArray(source.pitcher_changes) ? source.pitcher_changes : []
  const groups = [
    { key: 'team-state', label: 'Team State', rows: teamStateRows(source.team_state_change) },
    { key: 'rest-status', label: 'Rested Options', rows: restStatusRows(source.rest_status_change) },
    { key: 'arm-read', label: 'Arm Read movement', rows: armReadRows(changes) },
    { key: 'appearance', label: 'New appearance / workload', rows: appearanceRows(changes) },
  ].filter(group => group.rows.length > 0)

  return {
    capabilityValid: source.capability === 'what_changed_since_last_game',
    state: textValue(source.state) || 'unavailable',
    comparison: {
      fromDate: textValue(comparison.anchor_game_date),
      fromLabel: formatDateOnly(comparison.anchor_game_date, { month: 'short' }),
      toDate: textValue(comparison.current_game_date),
      toLabel: formatDateOnly(comparison.current_game_date, { month: 'short' }),
    },
    teamStateComparison: teamStateComparisonView(source.team_state_comparison),
    restStatusComparison: teamStateComparisonView(source.rest_status_comparison),
    armReadComparison: teamStateComparisonView(source.arm_read_comparison),
    groups,
    limitations: Array.isArray(source.limitations)
      ? source.limitations.map(textValue).filter(Boolean)
      : [],
  }
}
