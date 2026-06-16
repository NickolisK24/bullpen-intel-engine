const role = (key, label, definition, tone) => Object.freeze({
  kind: 'role',
  key,
  label,
  definition,
  tone,
})

const read = (key, label, definition, tone) => Object.freeze({
  kind: 'read',
  key,
  label,
  definition,
  tone,
})

export const PITCHER_ROLE_LABELS = Object.freeze({
  TRUST_ARM: role(
    'trust_arm',
    'Trust Arm',
    'Existing usage read points to late or high-leverage relief work.',
    { borderColor: 'rgba(125,211,252,0.36)', backgroundColor: 'rgba(125,211,252,0.09)', color: '#bae6fd' },
  ),
  BRIDGE_ARM: role(
    'bridge_arm',
    'Bridge Arm',
    'Existing usage read points to setup, bridge, or middle relief work.',
    { borderColor: 'rgba(196,181,253,0.34)', backgroundColor: 'rgba(196,181,253,0.08)', color: '#ddd6fe' },
  ),
  COVERAGE_ARM: role(
    'coverage_arm',
    'Coverage Arm',
    'Existing usage read points to longer or multi-inning relief coverage.',
    { borderColor: 'rgba(45,212,191,0.32)', backgroundColor: 'rgba(45,212,191,0.08)', color: '#99f6e4' },
  ),
  DEPTH_ARM: role(
    'depth_arm',
    'Depth Arm',
    'Existing usage read points to lighter or depth bullpen usage; a usage label, not a talent judgment.',
    { borderColor: 'rgba(203,213,225,0.30)', backgroundColor: 'rgba(203,213,225,0.07)', color: '#cbd5e1' },
  ),
  LIMITED_READ: role(
    'limited_read',
    'Limited Read',
    'The current payload does not support a clear role label.',
    { borderColor: 'rgba(148,163,184,0.28)', backgroundColor: 'rgba(148,163,184,0.07)', color: '#cbd5e1' },
  ),
})

export const PITCHER_READ_LABELS = Object.freeze({
  CLEAN_OPTION: read(
    'clean_option',
    'Clean Option',
    'Current workload status is Available with enough data to show the read.',
    { borderColor: 'rgba(34,197,94,0.32)', backgroundColor: 'rgba(34,197,94,0.08)', color: '#bbf7d0' },
  ),
  WATCH_ARM: read(
    'watch_arm',
    'Watch Arm',
    'Current workload status is Monitor or the data read is not fully clear.',
    { borderColor: 'rgba(234,179,8,0.34)', backgroundColor: 'rgba(234,179,8,0.09)', color: '#fef08a' },
  ),
  REST_RESTRICTED: read(
    'rest_restricted',
    'Rest-Restricted',
    'Current workload status is Limited or Avoid because of recent workload only.',
    { borderColor: 'rgba(249,115,22,0.34)', backgroundColor: 'rgba(249,115,22,0.09)', color: '#fed7aa' },
  ),
  UNAVAILABLE: read(
    'unavailable',
    'Unavailable',
    'Current status or roster context says this pitcher is not counted in the current availability read.',
    { borderColor: 'rgba(239,68,68,0.36)', backgroundColor: 'rgba(239,68,68,0.10)', color: '#fecaca' },
  ),
  LIMITED_READ: read(
    'limited_read',
    'Limited Read',
    'The current payload does not support a clear availability read.',
    { borderColor: 'rgba(148,163,184,0.28)', backgroundColor: 'rgba(148,163,184,0.07)', color: '#cbd5e1' },
  ),
})

export const APPROVED_ROLE_LABELS = Object.freeze(
  Object.values(PITCHER_ROLE_LABELS).map(label => label.label),
)

export const APPROVED_READ_LABELS = Object.freeze(
  Object.values(PITCHER_READ_LABELS).map(label => label.label),
)

export const PITCHER_LABEL_KEY_COPY = Object.freeze({
  title: 'Pitcher Label Key',
  roleLayer: 'Role:',
  readLayer: 'Read:',
  roleSummary: 'Role labels describe bullpen usage shape.',
  readSummary: 'Read labels describe the current workload and availability shape.',
  roleQuestion: 'What type of bullpen arm is this?',
  readQuestion: 'What does the current read say about this pitcher?',
})

const ROLE_KEY_TO_LABEL = Object.freeze({
  late_high_leverage: PITCHER_ROLE_LABELS.TRUST_ARM,
  high_leverage: PITCHER_ROLE_LABELS.TRUST_ARM,
  closer: PITCHER_ROLE_LABELS.TRUST_ARM,
  leverage: PITCHER_ROLE_LABELS.TRUST_ARM,

  setup_bridge: PITCHER_ROLE_LABELS.BRIDGE_ARM,
  setup: PITCHER_ROLE_LABELS.BRIDGE_ARM,
  bridge: PITCHER_ROLE_LABELS.BRIDGE_ARM,
  middle_relief: PITCHER_ROLE_LABELS.BRIDGE_ARM,
  middle: PITCHER_ROLE_LABELS.BRIDGE_ARM,

  long_multi_inning: PITCHER_ROLE_LABELS.COVERAGE_ARM,
  long_relief: PITCHER_ROLE_LABELS.COVERAGE_ARM,
  multi_inning: PITCHER_ROLE_LABELS.COVERAGE_ARM,
  bulk: PITCHER_ROLE_LABELS.COVERAGE_ARM,
  coverage: PITCHER_ROLE_LABELS.COVERAGE_ARM,

  depth: PITCHER_ROLE_LABELS.DEPTH_ARM,
  depth_arm: PITCHER_ROLE_LABELS.DEPTH_ARM,
  lower_leverage: PITCHER_ROLE_LABELS.DEPTH_ARM,
  low_leverage: PITCHER_ROLE_LABELS.DEPTH_ARM,
  mop_up: PITCHER_ROLE_LABELS.DEPTH_ARM,

  low_unclear: PITCHER_ROLE_LABELS.LIMITED_READ,
  insufficient_data: PITCHER_ROLE_LABELS.LIMITED_READ,
})

const COVERAGE_ROLE_KEYS = new Set([
  'long_multi_inning',
  'long_relief',
  'multi_inning',
  'bulk',
  'coverage',
])

const INACTIVE_ROSTER_STATUSES = new Set([
  'IL_10',
  'IL_15',
  'IL_60',
  'MINORS',
  'OPTIONED',
  'DFA',
  'NON_ROSTER',
  '40_MAN_ONLY',
])

const FRESH_DATA_STATES = new Set(['fresh', 'current', 'ok'])
const LIMITED_DATA_STATES = new Set(['stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown'])

function cloneLabel(label, source) {
  return {
    ...label,
    source,
  }
}

function normalizeToken(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function normalizeText(...values) {
  return values
    .map(value => String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, ' '))
    .filter(Boolean)
    .join(' ')
}

function rolePayload(card) {
  return card?.role || card?.usage_role || null
}

function normalizedRoleKey(payload) {
  return normalizeToken(payload?.role_key || payload?.key || payload?.role_type)
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function roleEvidenceText(payload) {
  return normalizeText(
    payload?.role,
    payload?.short_reason,
    payload?.reason,
    ...asArray(payload?.evidence),
    ...asArray(payload?.reasons),
  )
}

function numberValue(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function getUsageSampleSize(payload) {
  for (const value of [
    payload?.sample_size,
    payload?.usage_sample_size,
    payload?.appearance_count,
    payload?.appearances,
    payload?.recent_appearances,
    payload?.recent_outings,
    payload?.relief_appearances,
  ]) {
    const parsed = numberValue(value)
    if (parsed != null) return parsed
    if (Array.isArray(value)) return value.length
  }

  const evidenceText = roleEvidenceText(payload)
  const match = evidenceText.match(/\b(\d+)\s+(?:appearance|appearances|outing|outings)\b/)
  return match ? Number(match[1]) : null
}

function hasLowUsageSample(payload) {
  const sampleSize = getUsageSampleSize(payload)
  return sampleSize != null && sampleSize < 2
}

function hasWeakRoleConfidence(payload) {
  const confidence = normalizeToken(payload?.confidence || payload?.role_confidence || payload?.usage_confidence)
  return ['low', 'none', 'unknown'].includes(confidence)
}

function hasCoverageUsageSignal(payload) {
  const text = roleEvidenceText(payload)
  return text.includes('long relief') ||
    text.includes('multi inning') ||
    text.includes('multi innings') ||
    text.includes('bulk') ||
    text.includes('coverage')
}

function isMixedStarterReliever(card, payload) {
  if (!card && !payload) return false
  if (payload?.is_starter === true && payload?.is_reliever === true) return true
  if (payload?.starter_reliever_mixed === true || payload?.mixed_starter_reliever === true) return true
  if (card?.eligibility?.status === 'role_ambiguous') return true

  const text = normalizeText(
    payload?.role_key,
    payload?.role,
    payload?.short_reason,
    payload?.reason,
    card?.eligibility?.status,
    card?.eligibility?.reason,
  )
  const hasStarter = text.includes('starter') || text.includes('starting')
  const hasRelief = text.includes('relief') || text.includes('reliever') || text.includes('bullpen')
  const ambiguous = text.includes('ambiguous') || text.includes('mixed') || text.includes('swing')
  return hasStarter && hasRelief && ambiguous
}

function inferRoleFromText(payload) {
  const text = roleEvidenceText(payload)
  if (!text) return null
  if (text.includes('high leverage') || text.includes('late leverage') || text.includes('closer')) {
    return PITCHER_ROLE_LABELS.TRUST_ARM
  }
  if (text.includes('setup') || text.includes('bridge') || text.includes('middle relief')) {
    return PITCHER_ROLE_LABELS.BRIDGE_ARM
  }
  if (text.includes('long relief') || text.includes('multi inning') || text.includes('bulk') || text.includes('coverage')) {
    return PITCHER_ROLE_LABELS.COVERAGE_ARM
  }
  if (text.includes('depth') || text.includes('low leverage') || text.includes('lighter usage')) {
    return PITCHER_ROLE_LABELS.DEPTH_ARM
  }
  return null
}

export function derivePitcherRoleLabel(card) {
  const payload = rolePayload(card)
  if (!payload || typeof payload !== 'object') {
    return cloneLabel(PITCHER_ROLE_LABELS.LIMITED_READ, 'missing_role')
  }

  const key = normalizedRoleKey(payload)
  if (hasLowUsageSample(payload) || hasWeakRoleConfidence(payload)) {
    return cloneLabel(PITCHER_ROLE_LABELS.LIMITED_READ, 'low_usage_sample')
  }

  if (isMixedStarterReliever(card, payload)) {
    if (COVERAGE_ROLE_KEYS.has(key) && hasCoverageUsageSignal(payload)) {
      return cloneLabel(PITCHER_ROLE_LABELS.COVERAGE_ARM, `mixed_coverage:${key}`)
    }
    return cloneLabel(PITCHER_ROLE_LABELS.LIMITED_READ, 'mixed_starter_reliever')
  }

  const mapped = ROLE_KEY_TO_LABEL[key]
  if (mapped) {
    return cloneLabel(mapped, `role_key:${key}`)
  }

  const inferred = inferRoleFromText(payload)
  if (inferred) {
    return cloneLabel(inferred, 'role_text')
  }

  return cloneLabel(PITCHER_ROLE_LABELS.LIMITED_READ, 'unknown_role')
}

function rosterUnavailable(rosterStatus) {
  if (!rosterStatus || typeof rosterStatus !== 'object') return false
  const status = rosterStatus.status || rosterStatus.roster_status
  if (INACTIVE_ROSTER_STATUSES.has(status)) return true
  return rosterStatus.is_active_mlb === false || rosterStatus.is_inactive_context === true
}

function hasEnoughReadData(card, status) {
  if (!card || !status) return false
  const dataState = normalizeToken(card.data_state)
  if (LIMITED_DATA_STATES.has(dataState)) return false
  if (dataState && !FRESH_DATA_STATES.has(dataState)) return false
  if (!dataState) return false
  if (card.confidence && ['none', 'unknown'].includes(normalizeToken(card.confidence))) return false
  return true
}

export function derivePitcherReadLabel(card) {
  if (!card || typeof card !== 'object') {
    return cloneLabel(PITCHER_READ_LABELS.LIMITED_READ, 'missing_card')
  }

  const status = normalizeToken(card.availability_status || card.availability?.availability_status)
  if (status === 'unavailable' || rosterUnavailable(card.roster_status || card.availability?.roster_status)) {
    return cloneLabel(PITCHER_READ_LABELS.UNAVAILABLE, 'unavailable_status')
  }

  if (!hasEnoughReadData(card, status)) {
    return cloneLabel(PITCHER_READ_LABELS.LIMITED_READ, 'limited_data')
  }

  if (status === 'available') {
    return cloneLabel(PITCHER_READ_LABELS.CLEAN_OPTION, 'availability_status')
  }
  if (status === 'monitor') {
    return cloneLabel(PITCHER_READ_LABELS.WATCH_ARM, 'availability_status')
  }
  if (status === 'limited' || status === 'avoid') {
    return cloneLabel(PITCHER_READ_LABELS.REST_RESTRICTED, 'availability_status')
  }

  return cloneLabel(PITCHER_READ_LABELS.LIMITED_READ, 'unknown_availability')
}

export function getPitcherLabels(card) {
  return {
    role: derivePitcherRoleLabel(card),
    read: derivePitcherReadLabel(card),
  }
}
