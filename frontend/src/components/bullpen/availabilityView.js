export const AVAILABILITY_FILTERS = [
  'ALL',
  'Available',
  'Monitor',
  'Limited',
  'Unavailable',
]

export const RAW_AVAILABILITY_STATUSES = [
  'Available',
  'Monitor',
  'Limited',
  'Avoid',
  'Unavailable',
]

const PUBLIC_STATUS_BY_RAW_STATUS = {
  Avoid: 'Unavailable',
}

const STATUS_CONFIG = {
  Available: {
    label: 'Available',
    tone: 'Recent usage leaves this arm in a clean spot for normal bullpen coverage.',
    style: {
      color: '#86efac',
      borderColor: 'rgba(34,197,94,0.38)',
      backgroundColor: 'rgba(34,197,94,0.10)',
    },
    dotStyle: { backgroundColor: '#22c55e' },
  },
  Monitor: {
    label: 'On Watch',
    tone: 'Recent work should be checked before counting on a full late-game lane.',
    style: {
      color: '#fde047',
      borderColor: 'rgba(234,179,8,0.40)',
      backgroundColor: 'rgba(234,179,8,0.11)',
    },
    dotStyle: { backgroundColor: '#eab308' },
  },
  Limited: {
    label: 'Limited',
    tone: 'Recent usage narrows how comfortably this arm can be used.',
    style: {
      color: '#fdba74',
      borderColor: 'rgba(249,115,22,0.42)',
      backgroundColor: 'rgba(249,115,22,0.12)',
    },
    dotStyle: { backgroundColor: '#f97316' },
  },
  Avoid: {
    label: 'Unavailable',
    tone: "Recent workload keeps this arm out of today's available group.",
    style: {
      color: '#fca5a5',
      borderColor: 'rgba(239,68,68,0.42)',
      backgroundColor: 'rgba(239,68,68,0.12)',
    },
    dotStyle: { backgroundColor: '#ef4444' },
  },
  Unavailable: {
    label: 'Unavailable',
    tone: "Roster or workload context keeps this pitcher out of tonight's available group.",
    style: {
      color: '#fecaca',
      borderColor: 'rgba(185,28,28,0.54)',
      backgroundColor: 'rgba(185,28,28,0.18)',
    },
    dotStyle: { backgroundColor: '#dc2626' },
  },
  Unknown: {
    label: 'Unknown',
    tone: 'BaseballOS does not have enough current context for a bullpen read.',
    style: {
      color: '#cbd5e1',
      borderColor: 'rgba(148,163,184,0.32)',
      backgroundColor: 'rgba(148,163,184,0.09)',
    },
    dotStyle: { backgroundColor: '#94a3b8' },
  },
}

// Workload Data — the state of ONE pitcher's stored workload record.
//
// H-11: this family used to render under the field label "Data Status", which
// is the platform-wide public family (Current / Partial Data / Stale / Data
// Unavailable) describing whether the published READ is current. This one
// answers a different question — how complete and how recent the workload
// record behind a single arm is — and its values carry that detail (a missing
// record and a failed fetch are different things a reader can act on, and
// collapsing both into "Data Unavailable" would delete that).
//
// It is therefore its own named public family rather than a second dictionary
// for Data Status. The baseball word 'Fresh' is gone: it is a canonical Team
// State label, and a reader met it here meaning "the data is recent" while it
// means "this bullpen is rested" one surface away.
export const WORKLOAD_DATA_FIELD_LABEL = 'Workload Data'

const DATA_STATE_COPY = {
  fresh: {
    label: 'Current',
    message: 'Latest workload information is inside the active freshness window.',
  },
  stale: {
    label: 'Outside Freshness Window',
    message: 'Workload history exists, but the latest appearance is older than the active freshness window.',
  },
  missing: {
    label: 'No Workload Record',
    message: 'No recent workload history is available for this pitcher.',
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
    message: 'This status is based on an older workload read.',
  },
  unknown: {
    label: 'Unavailable',
    message: 'BaseballOS does not have a workload data state for this pitcher.',
  },
}

// The complete public value set for this family. A value outside it is not
// rendered at all (see getDataStateView) rather than title-cased into a new
// public label, so the family cannot grow by accident.
export const WORKLOAD_DATA_LABELS = Object.freeze(
  Array.from(new Set(Object.values(DATA_STATE_COPY).map(entry => entry.label))),
)

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
  RESTRICTED: 'Roster Unavailable',
  UNKNOWN: 'Roster Unknown',
}

const STATUS_DISPLAY_LABELS = Object.fromEntries(
  Object.entries(STATUS_CONFIG).map(([status, config]) => [status.toLowerCase(), config.label]),
)
STATUS_DISPLAY_LABELS.all = 'All'

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
  return RAW_AVAILABILITY_STATUSES.find(s => s.toLowerCase() === String(status).toLowerCase()) || null
}

export function getPublicAvailabilityStatus(status) {
  const normalized = normalizeAvailabilityStatus(status)
  if (!normalized) return null
  return PUBLIC_STATUS_BY_RAW_STATUS[normalized] || normalized
}

// Every governed PUBLIC availability label, keyed by its lowercase form. Some
// callers pass an already-public label ("On Watch") rather than a raw engine
// status ("Monitor"); recognising it is not a translation, it is the identity.
const PUBLIC_LABELS_BY_LOWERCASE = Object.fromEntries(
  Object.values(STATUS_CONFIG).map(config => [config.label.toLowerCase(), config.label]),
)

// Fails closed: a value that is neither a governed raw status nor a governed
// public label yields '' rather than echoing an internal token to a reader.
// Callers already treat an empty label as "nothing to show" for that row.
export function getAvailabilityStatusLabel(status) {
  const text = String(status || '').trim()
  if (!text) return ''
  const lower = text.toLowerCase()
  if (lower === 'all') return 'All'
  const normalized = normalizeAvailabilityStatus(text)
  if (normalized) return STATUS_CONFIG[normalized]?.label || ''
  return PUBLIC_LABELS_BY_LOWERCASE[lower] || STATUS_DISPLAY_LABELS[lower] || ''
}

export function getRowAvailability(row) {
  return row?.availability || null
}

export function getRowAvailabilityStatus(row) {
  return normalizeAvailabilityStatus(getRowAvailability(row)?.availability_status)
}

/**
 * Badge view for an availability status.
 *
 * `publicLabel` is the backend-published public form of the status
 * (`availability_public_label`, decided by
 * backend/services/public_bullpen_copy.py). When it is supplied it is rendered
 * as published — the frontend does not re-derive or re-translate it. The local
 * STATUS_CONFIG label remains only for surfaces whose payloads do not yet carry
 * a public label, and only ever supplies styling and tone for the board path.
 */
export function getAvailabilityBadgeView(availabilityOrStatus, publicLabel = null) {
  const status = typeof availabilityOrStatus === 'string'
    ? availabilityOrStatus
    : availabilityOrStatus?.availability_status
  const normalized = normalizeAvailabilityStatus(status) || 'Unknown'
  const config = STATUS_CONFIG[normalized] || STATUS_CONFIG.Unknown
  const backendLabel = typeof publicLabel === 'string' ? publicLabel.trim() : ''
  return {
    status: normalized,
    label: backendLabel || config.label,
    tone: config.tone,
    style: config.style,
    dotStyle: config.dotStyle,
  }
}

// Baseball-facing labels for classification confidence: the user sees how
// clear the workload read is, not an internal confidence grade. Raw API
// values ('high'/'medium'/'low') are preserved everywhere outside display.
// 'Limited Read' is reserved for the pitcher label that means "not enough
// data for a clear role/availability label" — confidence uses 'Partial Read'
// so the two concepts never share a public name.
// VOC-001: read confidence is a presentation-only quality scale, not a second
// baseball read. The retired wording (Strong Read / Partial Read / Unclear
// Read / No Read / Unknown Read) looked like a competing arm-read
// classification sitting next to the governed pitcher read, so a reader had
// two "read" vocabularies and no way to tell which one was the baseball
// conclusion. This family is explicitly a confidence scale and must always be
// rendered under READ_CONFIDENCE_FIELD_LABEL so a bare "High" can never be
// mistaken for Team State or for arm availability.
//
// The raw API confidence values (high / medium / low / none / unknown) are
// unchanged; only the display strings moved.
const CONFIDENCE_READ_LABELS = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  none: 'Unavailable',
  unknown: 'Unavailable',
}

// The one field-label owner for this family. Every surface renders this exact
// string, so a bare value can never be mistaken for a Team State or an arm
// availability label. It is re-exported through utils/bullpenConcepts for the
// glossary, which must name the family the same way the product does.
export const READ_CONFIDENCE_FIELD_LABEL = 'Read Confidence'

// Fails closed: an unrecognised confidence token resolves to the governed
// 'Unavailable' value instead of being title-cased into a new public label.
export function formatConfidence(confidence) {
  const value = String(confidence || '').trim().toLowerCase()
  if (!value) return CONFIDENCE_READ_LABELS.unknown
  return CONFIDENCE_READ_LABELS[value] || CONFIDENCE_READ_LABELS.unknown
}

// Fails closed: an unrecognised backend state resolves to the governed
// unavailable entry rather than being title-cased into a brand-new public
// label. `isKnown` lets a caller style or omit the row without comparing
// reader-facing text, so renaming a label can never change behaviour.
export function getDataStateView(dataState) {
  const key = String(dataState || 'unknown').toLowerCase()
  const entry = DATA_STATE_COPY[key]
  if (!entry) {
    return { ...DATA_STATE_COPY.unknown, key: 'unknown', isKnown: false, isCurrent: false }
  }
  return { ...entry, key, isKnown: true, isCurrent: key === 'fresh' }
}

export function filterRowsByAvailability(rows, availabilityFilter = 'ALL') {
  if (availabilityFilter === 'ALL') return rows
  const publicFilter = getPublicAvailabilityStatus(availabilityFilter)
  return rows.filter(row => getPublicAvailabilityStatus(getRowAvailabilityStatus(row)) === publicFilter)
}

export function getAvailabilityFilterCounts(rows = []) {
  const counts = Object.fromEntries(AVAILABILITY_FILTERS.map(filter => [filter, 0]))
  counts.ALL = rows.length
  rows.forEach(row => {
    const status = getPublicAvailabilityStatus(getRowAvailabilityStatus(row))
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
