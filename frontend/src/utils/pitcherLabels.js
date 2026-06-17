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
    'Existing usage read points to the primary late-inning trust lane.',
    { borderColor: 'rgba(125,211,252,0.36)', backgroundColor: 'rgba(125,211,252,0.09)', color: '#bae6fd' },
  ),
  BRIDGE_ARM: role(
    'bridge_arm',
    'Bridge Arm',
    'Existing usage read points to the bridge or handoff layer.',
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

const ROLE_BY_KEY = Object.freeze(Object.fromEntries(
  Object.values(PITCHER_ROLE_LABELS).map(label => [label.key, label]),
))

const READ_BY_KEY = Object.freeze(Object.fromEntries(
  Object.values(PITCHER_READ_LABELS).map(label => [label.key, label]),
))

function normalizeKey(value) {
  return String(value || '').trim().toLowerCase()
}

function authoredLabels(card) {
  return card?.pitcher_labels || card?.pitcherLabels || {}
}

function mergeAuthoredLabel(payload, catalogByKey, fallback) {
  if (!payload || typeof payload !== 'object') {
    return {
      ...fallback,
      source: 'missing_backend_label',
    }
  }

  const key = normalizeKey(payload.key)
  const catalog = catalogByKey[key]
  if (!catalog) {
    return {
      ...fallback,
      source: payload.source || 'unknown_backend_label',
    }
  }

  return {
    ...catalog,
    label: payload.label || catalog.label,
    source: payload.source || 'backend',
  }
}

export function derivePitcherRoleLabel(card) {
  return mergeAuthoredLabel(
    authoredLabels(card).role,
    ROLE_BY_KEY,
    PITCHER_ROLE_LABELS.LIMITED_READ,
  )
}

export function derivePitcherReadLabel(card) {
  return mergeAuthoredLabel(
    authoredLabels(card).read,
    READ_BY_KEY,
    PITCHER_READ_LABELS.LIMITED_READ,
  )
}

export function getPitcherLabels(card) {
  return {
    role: derivePitcherRoleLabel(card),
    read: derivePitcherReadLabel(card),
  }
}
