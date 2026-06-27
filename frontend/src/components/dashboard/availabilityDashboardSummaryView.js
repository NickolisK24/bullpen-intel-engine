import {
  AVAILABILITY_FILTERS,
  formatConfidence,
  getAvailabilityBadgeView,
  getDataStateView,
} from '../bullpen/availabilityView'

export const DASHBOARD_CONFIDENCE_ORDER = ['high', 'medium', 'low']
export const DASHBOARD_DATA_STATE_ORDER = ['fresh', 'stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown']
export const SCORED_PITCHER_INVENTORY_MODE = 'scored_pitcher_inventory'

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
  failed: {
    color: '#fca5a5',
    borderColor: 'rgba(239,68,68,0.36)',
    backgroundColor: 'rgba(239,68,68,0.10)',
  },
  historical: {
    color: '#9aa8b8',
    borderColor: 'rgba(154,168,184,0.32)',
    backgroundColor: 'rgba(154,168,184,0.08)',
  },
  unknown: {
    color: '#9aa8b8',
    borderColor: 'rgba(154,168,184,0.32)',
    backgroundColor: 'rgba(154,168,184,0.08)',
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

function getPrimaryTrustNote(summary, limitedByData, isCurrentAvailability) {
  const notes = Array.isArray(summary?.notes) ? summary.notes : []
  if (limitedByData) {
    return isCurrentAvailability
      ? 'Some relievers have stale, missing, failed, or incomplete workload evidence, so the bullpen picture is less certain.'
      : 'Some pitchers have stale, missing, failed, or incomplete workload evidence, so the depth picture is less certain.'
  }
  return notes[0] || (isCurrentAvailability
    ? 'This summary translates the latest stored workload into bullpen availability.'
    : 'This inventory shows how much usable bullpen context BaseballOS has right now.')
}

function getDominantStatusRow(rows = []) {
  return rows.reduce((dominant, row) => {
    if (!dominant) return row
    return row.count > dominant.count ? row : dominant
  }, null)
}

function getOperationalSummary(rows = [], total = 0, isCurrentAvailability = true) {
  if (total <= 0) {
    return isCurrentAvailability
      ? 'No current bullpen availability records are available for this summary.'
      : 'No pitcher workload records are available for this summary.'
  }

  const dominant = getDominantStatusRow(rows)
  if (!dominant || dominant.count <= 0) {
    return isCurrentAvailability
      ? 'The current bullpen picture does not have a populated availability lane yet.'
      : 'The stored workload picture does not have a populated bullpen lane yet.'
  }

  const pct = Math.round((dominant.count / total) * 100)
  if (pct >= 50) {
    return isCurrentAvailability
      ? `Most current bullpen arms are in the ${dominant.label} lane.`
      : `Most stored pitcher workload reads are in the ${dominant.label} lane.`
  }

  return isCurrentAvailability
    ? 'Current bullpen availability is spread across multiple lanes.'
    : 'Stored workload reads are spread across multiple bullpen lanes.'
}

function getModeCopy(mode, isCurrentAvailability) {
  if (isCurrentAvailability) {
    return {
      modeLabel: 'Current availability',
      title: 'Availability Summary',
      distributionTitle: 'Bullpen Availability Mix',
      distributionAriaLabel: 'Bullpen availability mix',
      detailsOpenLabel: 'Hide Availability Detail',
      detailsClosedLabel: 'View Availability Detail',
      totalLabel: 'pitchers with a current read',
    }
  }

  if (mode === SCORED_PITCHER_INVENTORY_MODE) {
    return {
      modeLabel: 'Pitcher workload inventory',
      title: 'Pitcher Workload Inventory',
      distributionTitle: 'Workload Read Mix',
      distributionAriaLabel: 'Workload read mix',
      detailsOpenLabel: 'Hide Inventory Detail',
      detailsClosedLabel: 'View Inventory Detail',
      totalLabel: 'pitchers with workload reads',
    }
  }

  return {
    modeLabel: 'Non-current workload read',
    title: 'Workload Read',
    distributionTitle: 'Workload Read Mix',
    distributionAriaLabel: 'Workload read mix',
    detailsOpenLabel: 'Hide Workload Detail',
    detailsClosedLabel: 'View Workload Detail',
    totalLabel: 'pitchers with workload reads',
  }
}

export function getAvailabilityDashboardSummaryView(summary = null) {
  const mode = summary?.mode || 'unknown'
  const totalPitchers = Number(summary?.total_pitchers || 0)
  const dataState = summary?.data_state || {}
  const stale = Number(dataState.stale || 0)
  const missing = Number(dataState.missing || 0)
  const incomplete = Number(dataState.incomplete || 0)
  const failed = Number(dataState.failed || 0)
  const historical = Number(dataState.historical || 0)
  const unknown = Number(dataState.unknown || 0)
  const limitedDataCount = stale + missing + incomplete + failed + historical + unknown
  const limitedByData = totalPitchers > 0 && limitedDataCount > totalPitchers / 2
  const isCurrentAvailability = summary?.is_current_availability === true
  const modeCopy = getModeCopy(mode, isCurrentAvailability)
  const statusRows = buildRows(
    summary?.statuses,
    AVAILABILITY_FILTERS.filter(status => status !== 'ALL'),
    status => status,
    status => getAvailabilityBadgeView(status).style,
  )
  const statusTotal = statusRows.reduce((total, row) => total + row.count, 0)

  return {
    mode,
    ...modeCopy,
    isCurrentAvailability,
    totalPitchers,
    limitedByData,
    limitedDataCount,
    primaryTrustNote: getPrimaryTrustNote(summary, limitedByData, isCurrentAvailability),
    notes: Array.isArray(summary?.notes) ? summary.notes : [],
    statusRows,
    statusTotal,
    dominantStatus: getDominantStatusRow(statusRows),
    operationalSummary: getOperationalSummary(statusRows, statusTotal, isCurrentAvailability),
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
