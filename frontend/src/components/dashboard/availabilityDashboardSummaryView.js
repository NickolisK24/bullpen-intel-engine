import {
  AVAILABILITY_FILTERS,
  formatConfidence,
  getAvailabilityBadgeView,
  getDataStateView,
} from '../bullpen/availabilityView'

export const DASHBOARD_CONFIDENCE_ORDER = ['high', 'medium', 'low']
export const DASHBOARD_DATA_STATE_ORDER = ['fresh', 'stale', 'missing', 'incomplete']

const CONFIDENCE_STYLE = {
  high: {
    color: '#86efac',
    borderColor: 'rgba(34,197,94,0.34)',
    backgroundColor: 'rgba(34,197,94,0.10)',
  },
  medium: {
    color: '#fdba74',
    borderColor: 'rgba(249,115,22,0.35)',
    backgroundColor: 'rgba(249,115,22,0.10)',
  },
  low: {
    color: '#fca5a5',
    borderColor: 'rgba(239,68,68,0.36)',
    backgroundColor: 'rgba(239,68,68,0.10)',
  },
}

const DATA_STATE_STYLE = {
  fresh: {
    color: '#86efac',
    borderColor: 'rgba(34,197,94,0.34)',
    backgroundColor: 'rgba(34,197,94,0.10)',
  },
  stale: {
    color: '#fde047',
    borderColor: 'rgba(234,179,8,0.36)',
    backgroundColor: 'rgba(234,179,8,0.10)',
  },
  missing: {
    color: '#fca5a5',
    borderColor: 'rgba(239,68,68,0.36)',
    backgroundColor: 'rgba(239,68,68,0.10)',
  },
  incomplete: {
    color: '#fdba74',
    borderColor: 'rgba(249,115,22,0.35)',
    backgroundColor: 'rgba(249,115,22,0.10)',
  },
}

function buildRows(counts = {}, order = [], labelFor = value => value, styleFor = () => ({})) {
  return order.map((key) => ({
    key,
    label: labelFor(key),
    count: Number(counts?.[key] || 0),
    style: styleFor(key),
  }))
}

function getPrimaryTrustNote(summary, limitedByData) {
  const notes = Array.isArray(summary?.notes) ? summary.notes : []
  if (limitedByData) {
    return 'Availability is limited by stale workload data.'
  }
  return notes[0] || 'Availability summary is based on current-mode classifier output.'
}

export function getAvailabilityDashboardSummaryView(summary = null) {
  const totalPitchers = Number(summary?.total_pitchers || 0)
  const dataState = summary?.data_state || {}
  const stale = Number(dataState.stale || 0)
  const missing = Number(dataState.missing || 0)
  const incomplete = Number(dataState.incomplete || 0)
  const limitedDataCount = stale + missing + incomplete
  const limitedByData = totalPitchers > 0 && limitedDataCount > totalPitchers / 2
  const isCurrentAvailability = summary?.is_current_availability === true

  return {
    mode: summary?.mode || 'unknown',
    modeLabel: isCurrentAvailability ? 'Current availability' : 'Non-current availability',
    isCurrentAvailability,
    totalPitchers,
    limitedByData,
    limitedDataCount,
    primaryTrustNote: getPrimaryTrustNote(summary, limitedByData),
    notes: Array.isArray(summary?.notes) ? summary.notes : [],
    statusRows: buildRows(
      summary?.statuses,
      AVAILABILITY_FILTERS.filter(status => status !== 'ALL'),
      status => status,
      status => getAvailabilityBadgeView(status).style,
    ),
    confidenceRows: buildRows(
      summary?.confidence,
      DASHBOARD_CONFIDENCE_ORDER,
      formatConfidence,
      confidence => CONFIDENCE_STYLE[confidence] || {},
    ),
    dataStateRows: buildRows(
      dataState,
      DASHBOARD_DATA_STATE_ORDER,
      state => getDataStateView(state).label,
      state => DATA_STATE_STYLE[state] || {},
    ),
  }
}
