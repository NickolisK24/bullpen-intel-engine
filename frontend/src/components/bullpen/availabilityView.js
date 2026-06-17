export const AVAILABILITY_FILTERS = [
  'ALL',
  'Available',
  'Monitor',
  'Limited',
  'Avoid',
  'Unavailable',
]

const STATUS_CONFIG = {
  Available: {
    label: 'Available',
    tone: 'Workload signals are inside normal public-data use ranges.',
    style: {
      color: '#86efac',
      borderColor: 'rgba(34,197,94,0.38)',
      backgroundColor: 'rgba(34,197,94,0.10)',
    },
    dotStyle: { backgroundColor: '#22c55e' },
  },
  Monitor: {
    label: 'Monitor',
    tone: 'Review the workload context before treating this pitcher as fully available.',
    style: {
      color: '#fde047',
      borderColor: 'rgba(234,179,8,0.40)',
      backgroundColor: 'rgba(234,179,8,0.11)',
    },
    dotStyle: { backgroundColor: '#eab308' },
  },
  Limited: {
    label: 'Limited',
    tone: 'Recent workload suggests a restricted-use decision should be considered.',
    style: {
      color: '#fdba74',
      borderColor: 'rgba(249,115,22,0.42)',
      backgroundColor: 'rgba(249,115,22,0.12)',
    },
    dotStyle: { backgroundColor: '#f97316' },
  },
  Avoid: {
    label: 'Avoid',
    tone: 'Public workload signals show meaningful recent-use risk.',
    style: {
      color: '#fca5a5',
      borderColor: 'rgba(239,68,68,0.42)',
      backgroundColor: 'rgba(239,68,68,0.12)',
    },
    dotStyle: { backgroundColor: '#ef4444' },
  },
  Unavailable: {
    label: 'Unavailable',
    tone: 'Deterministic workload rules indicate this pitcher should not be counted for normal planning.',
    style: {
      color: '#fecaca',
      borderColor: 'rgba(185,28,28,0.54)',
      backgroundColor: 'rgba(185,28,28,0.18)',
    },
    dotStyle: { backgroundColor: '#dc2626' },
  },
  Unknown: {
    label: 'Unknown',
    tone: 'Availability status was not returned by the backend.',
    style: {
      color: '#cbd5e1',
      borderColor: 'rgba(148,163,184,0.32)',
      backgroundColor: 'rgba(148,163,184,0.09)',
    },
    dotStyle: { backgroundColor: '#94a3b8' },
  },
}

const DATA_STATE_COPY = {
  fresh: {
    label: 'Fresh',
    message: 'Latest workload information is inside the active freshness window.',
  },
  stale: {
    label: 'Outside Freshness Window',
    message: 'Workload history exists, but the latest appearance is older than the active freshness window.',
  },
  missing: {
    label: 'No Workload Record',
    message: 'No workload history or fatigue score is available for this pitcher.',
  },
  incomplete: {
    label: 'Incomplete Workload Inputs',
    message: 'Some workload inputs are incomplete, so the status should be treated cautiously.',
  },
  failed: {
    label: 'Fetch Failed',
    message: 'The latest workload fetch failed, so the read is unresolved until data refresh succeeds.',
  },
  historical: {
    label: 'Historical',
    message: 'This status is based on an older workload snapshot.',
  },
  unknown: {
    label: 'Unknown',
    message: 'The backend did not report a workload data state.',
  },
}

const ROSTER_STATUS_LABELS = {
  ACTIVE: 'Active MLB',
  IL_10: '10-Day IL',
  IL_15: '15-Day IL',
  IL_60: '60-Day IL',
  MINORS: 'Optioned / Minors',
  OPTIONED: 'Optioned',
  DFA: 'DFA',
  NON_ROSTER: 'Non-Roster',
  '40_MAN_ONLY': '40-Man (not active)',
  BEREAVEMENT: 'Bereavement List',
  PATERNITY: 'Paternity List',
  SUSPENDED: 'Suspended List',
  RESTRICTED: 'Restricted List',
  UNKNOWN: 'Roster Unknown',
}

export function getRosterStatusSummary(rosterStatus = null) {
  if (!rosterStatus || typeof rosterStatus !== 'object') {
    return null
  }
  const status = rosterStatus.status || 'UNKNOWN'
  return {
    status,
    label: rosterStatus.label || ROSTER_STATUS_LABELS[status] || 'Roster status',
    confidenceLabel: formatConfidence(rosterStatus.confidence),
    source: rosterStatus.source || null,
    isInactive: rosterStatus.is_inactive_context === true,
    isAuthoritative: rosterStatus.is_authoritative === true,
  }
}

export function normalizeAvailabilityStatus(status) {
  if (!status) return null
  return AVAILABILITY_FILTERS.find(s => s !== 'ALL' && s.toLowerCase() === String(status).toLowerCase()) || null
}

export function getRowAvailability(row) {
  return row?.availability || null
}

export function getRowAvailabilityStatus(row) {
  return normalizeAvailabilityStatus(getRowAvailability(row)?.availability_status)
}

export function getAvailabilityBadgeView(availabilityOrStatus) {
  const status = typeof availabilityOrStatus === 'string'
    ? availabilityOrStatus
    : availabilityOrStatus?.availability_status
  const normalized = normalizeAvailabilityStatus(status) || 'Unknown'
  const config = STATUS_CONFIG[normalized] || STATUS_CONFIG.Unknown
  return {
    status: normalized,
    label: config.label,
    tone: config.tone,
    style: config.style,
    dotStyle: config.dotStyle,
  }
}

// Baseball-facing labels for classification confidence: the user sees how
// clear the workload read is, not an internal confidence grade. Raw API
// values ('high'/'medium'/'low') are preserved everywhere outside display.
const CONFIDENCE_READ_LABELS = {
  high: 'Strong Read',
  medium: 'Limited Read',
  low: 'Unclear Read',
  none: 'No Read',
  unknown: 'Unknown Read',
}

function capitalizeToken(value) {
  return `${value.charAt(0).toUpperCase()}${value.slice(1).toLowerCase()}`
}

export function formatConfidence(confidence) {
  const value = String(confidence || '').trim().toLowerCase()
  if (!value) return 'Unknown Read'
  return CONFIDENCE_READ_LABELS[value] || capitalizeToken(value)
}

export function getDataStateView(dataState) {
  const key = String(dataState || 'unknown').toLowerCase()
  return DATA_STATE_COPY[key] || {
    label: capitalizeToken(key),
    message: 'The backend returned a non-standard workload data state.',
  }
}

export function filterRowsByAvailability(rows, availabilityFilter = 'ALL') {
  if (availabilityFilter === 'ALL') return rows
  return rows.filter(row => getRowAvailabilityStatus(row) === availabilityFilter)
}

export function getAvailabilityFilterCounts(rows = []) {
  const counts = Object.fromEntries(AVAILABILITY_FILTERS.map(filter => [filter, 0]))
  counts.ALL = rows.length
  rows.forEach(row => {
    const status = getRowAvailabilityStatus(row)
    if (status && counts[status] != null) counts[status] += 1
  })
  return counts
}

export function getAvailabilitySummary(availability = null) {
  const badge = getAvailabilityBadgeView(availability)
  return {
    ...badge,
    rosterStatus: getRosterStatusSummary(availability?.roster_status),
    confidenceLabel: formatConfidence(availability?.confidence),
    dataStateView: getDataStateView(availability?.data_state),
    reasons: Array.isArray(availability?.reasons) ? availability.reasons : [],
    limitations: Array.isArray(availability?.limitations) ? availability.limitations : [],
    inputs: availability?.inputs || {},
  }
}
