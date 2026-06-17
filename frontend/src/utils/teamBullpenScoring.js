const READ_KEYS = Object.freeze([
  'trustAvailability',
  'cleanOptions',
  'bullpenPressure',
  'workloadConcentration',
  'coverageSafety',
  'depthSafety',
])

export const TEAM_BULLPEN_PUBLIC_LABELS = Object.freeze({
  trustAvailability: Object.freeze([
    'Strong Trust Arm Availability',
    'Stable Trust Arm Availability',
    'Thin Trust Arm Availability',
    'Limited Trust Arm Availability',
    'Limited Read',
  ]),
  cleanOptions: Object.freeze([
    'Deep Clean Options',
    'Healthy Clean Options',
    'Thin Clean Options',
    'Very Thin Clean Options',
    'Limited Read',
  ]),
  bullpenPressure: Object.freeze([
    'High Bullpen Pressure',
    'Elevated Bullpen Pressure',
    'Manageable Bullpen Pressure',
    'Low Bullpen Pressure',
    'Limited Read',
  ]),
  workloadConcentration: Object.freeze([
    'Heavily Concentrated Workload',
    'Concentrated Workload',
    'Some Workload Concentration',
    'No Workload Concentration',
    'Limited Read',
  ]),
  coverageSafety: Object.freeze([
    'Strong Coverage Safety',
    'Stable Coverage Safety',
    'Thin Coverage Safety',
    'Limited Coverage Safety',
    'Limited Read',
  ]),
  depthSafety: Object.freeze([
    'Strong Depth Safety',
    'Stable Depth Safety',
    'Thin Depth Safety',
    'Limited Depth Safety',
    'Limited Read',
  ]),
})

function sourceShape(input) {
  if (input?.team_shape && typeof input.team_shape === 'object') return input.team_shape
  if (input?.teamShape && typeof input.teamShape === 'object') return input.teamShape
  if (Array.isArray(input?.reads) || input?.byKey || input?.by_key) return input
  return null
}

function isApprovedLabel(key, label) {
  return TEAM_BULLPEN_PUBLIC_LABELS[key]?.includes(label) === true
}

function limitedRead(key, source = 'missing_backend_team_shape') {
  const explanation = 'Backend team bullpen shape was not returned.'
  return {
    key,
    label: 'Limited Read',
    explanation,
    supportingCounts: {},
    reasons: [explanation],
    source,
  }
}

function normalizeRead(key, payload) {
  if (!payload || typeof payload !== 'object') return limitedRead(key)
  const label = typeof payload.label === 'string' && isApprovedLabel(key, payload.label)
    ? payload.label
    : 'Limited Read'
  const explanation = payload.explanation || 'Backend team bullpen shape did not include an explanation.'
  const supportingCounts = payload.supportingCounts || payload.supporting_counts || {}
  const reasons = Array.isArray(payload.reasons) && payload.reasons.length
    ? payload.reasons
    : [explanation]
  return {
    key,
    label,
    explanation,
    supportingCounts,
    reasons,
    source: payload.source || 'backend',
  }
}

function readsByKey(shape) {
  const byKey = shape?.byKey || shape?.by_key || {}
  const reads = Array.isArray(shape?.reads) ? shape.reads : []
  return {
    ...Object.fromEntries(reads.map(read => [read?.key, read]).filter(([key]) => READ_KEYS.includes(key))),
    ...byKey,
  }
}

export function getTeamBullpenShape(input) {
  const shape = sourceShape(input)
  const rawByKey = readsByKey(shape)
  const reads = READ_KEYS.map(key => normalizeRead(key, rawByKey[key]))
  const byKey = Object.fromEntries(reads.map(item => [item.key, item]))
  const supportingCounts = shape?.supportingCounts || shape?.supporting_counts || {}

  return {
    reads,
    byKey,
    trustAvailability: byKey.trustAvailability,
    cleanOptions: byKey.cleanOptions,
    bullpenPressure: byKey.bullpenPressure,
    workloadConcentration: byKey.workloadConcentration,
    coverageSafety: byKey.coverageSafety,
    depthSafety: byKey.depthSafety,
    supportingCounts,
    source: shape?.source || 'missing_backend_team_shape',
  }
}

export function getTeamBullpenScoring(input) {
  return getTeamBullpenShape(input)
}

export function getTeamBullpenReadKeys() {
  return [...READ_KEYS]
}
