import { getPitcherLabels } from './pitcherLabels.js'

const READ_KEYS = Object.freeze([
  'trustAvailability',
  'cleanOptions',
  'bullpenPressure',
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

const STATUS_ORDER = ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable']

const ROLE_LABELS = {
  trust: 'Trust Arm',
  coverage: 'Coverage Arm',
  depth: 'Depth Arm',
  limited: 'Limited Read',
}

const READ_LABELS = {
  clean: 'Clean Option',
  watch: 'Watch Arm',
  restricted: 'Rest-Restricted',
  unavailable: 'Unavailable',
  limited: 'Limited Read',
}

function asNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function asPitchers(input) {
  if (Array.isArray(input)) return input
  if (Array.isArray(input?.pitchers)) return input.pitchers
  if (!Array.isArray(input?.groups)) return []
  return input.groups.flatMap(group => Array.isArray(group?.pitchers) ? group.pitchers : [])
}

function statusCountsFromBoard(board, pitchers) {
  const counts = Object.fromEntries(STATUS_ORDER.map(status => [status, 0]))
  for (const group of Array.isArray(board?.groups) ? board.groups : []) {
    if (typeof group?.status === 'string' && counts[group.status] != null) {
      counts[group.status] += asNumber(group.count)
    }
  }
  if (Object.values(counts).some(Boolean)) return counts

  for (const pitcher of pitchers) {
    const status = pitcher?.availability_status
    if (counts[status] != null) counts[status] += 1
  }
  return counts
}

function emptyLabelCounts(labels) {
  return Object.fromEntries(labels.map(label => [label, 0]))
}

function cardFatigue(card) {
  return asNumber(card?.fatigue_score ?? card?.raw_score ?? card?.availability?.fatigue_score)
}

function summarizePitchers(input) {
  const pitchers = asPitchers(input)
  const readCounts = emptyLabelCounts(Object.values(READ_LABELS))
  const roleCounts = emptyLabelCounts([
    'Trust Arm',
    'Bridge Arm',
    'Coverage Arm',
    'Depth Arm',
    'Limited Read',
  ])
  const roleReadCounts = {
    trust: emptyLabelCounts(Object.values(READ_LABELS)),
    coverage: emptyLabelCounts(Object.values(READ_LABELS)),
    depth: emptyLabelCounts(Object.values(READ_LABELS)),
  }
  let highFatigueArms = 0

  for (const card of pitchers) {
    const labels = getPitcherLabels(card)
    const roleLabel = labels.role.label
    const readLabel = labels.read.label
    if (roleCounts[roleLabel] != null) roleCounts[roleLabel] += 1
    if (readCounts[readLabel] != null) readCounts[readLabel] += 1
    if (roleLabel === ROLE_LABELS.trust) roleReadCounts.trust[readLabel] += 1
    if (roleLabel === ROLE_LABELS.coverage) roleReadCounts.coverage[readLabel] += 1
    if (roleLabel === ROLE_LABELS.depth) roleReadCounts.depth[readLabel] += 1
    if (cardFatigue(card) >= 70) highFatigueArms += 1
  }

  const totalBullpenArms = pitchers.length
  const statusCounts = statusCountsFromBoard(input, pitchers)
  const unavailableCount = readCounts[READ_LABELS.unavailable]
  const activeBullpenArms = Math.max(0, totalBullpenArms - unavailableCount)
  const roleKnownCount = totalBullpenArms - roleCounts[ROLE_LABELS.limited]
  const readKnownCount = totalBullpenArms - readCounts[READ_LABELS.limited]
  const tinyBullpen = totalBullpenArms > 0 && totalBullpenArms < 4

  return {
    totalBullpenArms,
    activeBullpenArms,
    statusCounts,
    roleCounts,
    readCounts,
    roleReadCounts,
    highFatigueArms,
    stressState: input?.stress?.state || input?.context?.health?.state || null,
    dataQuality: {
      roleKnownCount,
      readKnownCount,
      roleSparse: totalBullpenArms === 0 || tinyBullpen || roleKnownCount < Math.ceil(totalBullpenArms * 0.5),
      readSparse: totalBullpenArms === 0 || tinyBullpen || readKnownCount < Math.ceil(totalBullpenArms * 0.5),
    },
  }
}

function read(key, label, explanation, supportingCounts, reasons = []) {
  return {
    key,
    label,
    explanation,
    supportingCounts,
    reasons: reasons.length ? reasons : [explanation],
  }
}

function limitedRead(key, explanation, supportingCounts) {
  return read(key, 'Limited Read', explanation, supportingCounts)
}

function roleLimitedExplanation(roleKnownCount, totalBullpenArms, concept) {
  return `Only ${roleKnownCount} of ${totalBullpenArms} bullpen arms have clear role labels, so ${concept} is a Limited Read.`
}

function trustAvailability(summary) {
  const trustReads = summary.roleReadCounts.trust
  const trustArms = summary.roleCounts[ROLE_LABELS.trust]
  const cleanTrustArms = trustReads[READ_LABELS.clean]
  const watchTrustArms = trustReads[READ_LABELS.watch]
  const restRestrictedTrustArms = trustReads[READ_LABELS.restricted]
  const unavailableTrustArms = trustReads[READ_LABELS.unavailable]
  const limitedReadTrustArms = trustReads[READ_LABELS.limited]
  const availableTrustArms = cleanTrustArms + watchTrustArms
  const supportingCounts = {
    trustArms,
    availableTrustArms,
    cleanTrustArms,
    watchTrustArms,
    restRestrictedTrustArms,
    unavailableTrustArms,
    limitedReadTrustArms,
    roleKnownCount: summary.dataQuality.roleKnownCount,
    totalBullpenArms: summary.totalBullpenArms,
  }

  if (summary.dataQuality.roleSparse) {
    return limitedRead(
      'trustAvailability',
      roleLimitedExplanation(summary.dataQuality.roleKnownCount, summary.totalBullpenArms, 'Trust Arm Availability'),
      supportingCounts,
    )
  }

  const explanation = `${cleanTrustArms} of ${trustArms} Trust Arms are Clean Options; ${watchTrustArms} are Watch Arms, ${restRestrictedTrustArms} are Rest-Restricted, and ${unavailableTrustArms} are Unavailable.`
  if (trustArms === 0 || availableTrustArms === 0) {
    return read('trustAvailability', 'Limited Trust Arm Availability', explanation, supportingCounts)
  }
  if (trustArms >= 2 && cleanTrustArms >= 2 && restRestrictedTrustArms === 0 && unavailableTrustArms === 0) {
    return read('trustAvailability', 'Strong Trust Arm Availability', explanation, supportingCounts)
  }
  if (trustArms >= 2 && availableTrustArms >= 2 && unavailableTrustArms === 0) {
    return read('trustAvailability', 'Stable Trust Arm Availability', explanation, supportingCounts)
  }
  if (availableTrustArms >= 1) {
    return read('trustAvailability', 'Thin Trust Arm Availability', explanation, supportingCounts)
  }
  return read('trustAvailability', 'Limited Trust Arm Availability', explanation, supportingCounts)
}

function cleanOptions(summary) {
  const cleanOptionCount = summary.readCounts[READ_LABELS.clean]
  const restRestrictedCount = summary.readCounts[READ_LABELS.restricted]
  const unavailableCount = summary.readCounts[READ_LABELS.unavailable]
  const limitedReadCount = summary.readCounts[READ_LABELS.limited]
  const supportingCounts = {
    cleanOptionCount,
    activeBullpenArms: summary.activeBullpenArms,
    totalBullpenArms: summary.totalBullpenArms,
    restRestrictedCount,
    unavailableCount,
    limitedReadCount,
  }

  if (summary.dataQuality.readSparse) {
    return limitedRead(
      'cleanOptions',
      `Only ${summary.dataQuality.readKnownCount} of ${summary.totalBullpenArms} bullpen arms have clear today reads, so Clean Options is a Limited Read.`,
      supportingCounts,
    )
  }

  const explanation = `${cleanOptionCount} Clean Options out of ${summary.activeBullpenArms} active bullpen arms, with ${restRestrictedCount} Rest-Restricted and ${unavailableCount} Unavailable.`
  if (cleanOptionCount >= 6 || (summary.activeBullpenArms >= 7 && cleanOptionCount >= 5)) {
    return read('cleanOptions', 'Deep Clean Options', explanation, supportingCounts)
  }
  if (cleanOptionCount >= 4) {
    return read('cleanOptions', 'Healthy Clean Options', explanation, supportingCounts)
  }
  if (cleanOptionCount >= 2) {
    return read('cleanOptions', 'Thin Clean Options', explanation, supportingCounts)
  }
  return read('cleanOptions', 'Very Thin Clean Options', explanation, supportingCounts)
}

function bullpenPressure(summary) {
  const watchArmCount = summary.readCounts[READ_LABELS.watch]
  const restRestrictedCount = summary.readCounts[READ_LABELS.restricted]
  const unavailableCount = summary.readCounts[READ_LABELS.unavailable]
  const limitedReadCount = summary.readCounts[READ_LABELS.limited]
  const pressureLoad = watchArmCount + (restRestrictedCount * 2) + (unavailableCount * 2) + summary.highFatigueArms
  const supportingCounts = {
    watchArmCount,
    restRestrictedCount,
    unavailableCount,
    highFatigueArms: summary.highFatigueArms,
    limitedReadCount,
    totalBullpenArms: summary.totalBullpenArms,
  }

  if (summary.dataQuality.readSparse) {
    return limitedRead(
      'bullpenPressure',
      `Only ${summary.dataQuality.readKnownCount} of ${summary.totalBullpenArms} bullpen arms have clear today reads, so Bullpen Pressure is a Limited Read.`,
      supportingCounts,
    )
  }

  const explanation = `${watchArmCount} Watch Arms, ${restRestrictedCount} Rest-Restricted, ${unavailableCount} Unavailable, and ${summary.highFatigueArms} high-fatigue arms shape bullpen pressure today.`
  if (
    restRestrictedCount + unavailableCount >= 4 ||
    pressureLoad >= summary.totalBullpenArms ||
    summary.stressState === 'constrained'
  ) {
    return read('bullpenPressure', 'High Bullpen Pressure', explanation, supportingCounts)
  }
  if (
    restRestrictedCount + unavailableCount >= 2 ||
    watchArmCount >= 3 ||
    summary.highFatigueArms >= 2 ||
    summary.stressState === 'elevated' ||
    summary.stressState === 'monitoring'
  ) {
    return read('bullpenPressure', 'Elevated Bullpen Pressure', explanation, supportingCounts)
  }
  if (restRestrictedCount === 0 && unavailableCount === 0 && watchArmCount <= 1 && summary.highFatigueArms === 0) {
    return read('bullpenPressure', 'Low Bullpen Pressure', explanation, supportingCounts)
  }
  return read('bullpenPressure', 'Manageable Bullpen Pressure', explanation, supportingCounts)
}

function coverageSafety(summary) {
  const coverageReads = summary.roleReadCounts.coverage
  const coverageArms = summary.roleCounts[ROLE_LABELS.coverage]
  const cleanCoverageArms = coverageReads[READ_LABELS.clean]
  const watchCoverageArms = coverageReads[READ_LABELS.watch]
  const restRestrictedCoverageArms = coverageReads[READ_LABELS.restricted]
  const unavailableCoverageArms = coverageReads[READ_LABELS.unavailable]
  const limitedReadCoverageArms = coverageReads[READ_LABELS.limited]
  const availableCoverageArms = cleanCoverageArms + watchCoverageArms
  const supportingCounts = {
    coverageArms,
    availableCoverageArms,
    cleanCoverageArms,
    watchCoverageArms,
    restRestrictedCoverageArms,
    unavailableCoverageArms,
    limitedReadCoverageArms,
    roleKnownCount: summary.dataQuality.roleKnownCount,
    totalBullpenArms: summary.totalBullpenArms,
  }

  if (summary.dataQuality.roleSparse) {
    return limitedRead(
      'coverageSafety',
      roleLimitedExplanation(summary.dataQuality.roleKnownCount, summary.totalBullpenArms, 'Coverage Safety'),
      supportingCounts,
    )
  }

  const explanation = `${cleanCoverageArms} of ${coverageArms} Coverage Arms are Clean Options; ${watchCoverageArms} are Watch Arms, ${restRestrictedCoverageArms} are Rest-Restricted, and ${unavailableCoverageArms} are Unavailable.`
  if (coverageArms >= 2 && cleanCoverageArms >= 2 && restRestrictedCoverageArms === 0 && unavailableCoverageArms === 0) {
    return read('coverageSafety', 'Strong Coverage Safety', explanation, supportingCounts)
  }
  if (coverageArms >= 2 && availableCoverageArms >= 2 && unavailableCoverageArms === 0) {
    return read('coverageSafety', 'Stable Coverage Safety', explanation, supportingCounts)
  }
  if (coverageArms >= 1 && availableCoverageArms >= 1) {
    return read('coverageSafety', 'Thin Coverage Safety', explanation, supportingCounts)
  }
  return read('coverageSafety', 'Limited Coverage Safety', explanation, supportingCounts)
}

function depthSafety(summary) {
  const depthReads = summary.roleReadCounts.depth
  const depthArms = summary.roleCounts[ROLE_LABELS.depth]
  const cleanDepthArms = depthReads[READ_LABELS.clean]
  const watchDepthArms = depthReads[READ_LABELS.watch]
  const restRestrictedDepthArms = depthReads[READ_LABELS.restricted]
  const unavailableDepthArms = depthReads[READ_LABELS.unavailable]
  const limitedReadDepthArms = depthReads[READ_LABELS.limited]
  const availableDepthArms = cleanDepthArms + watchDepthArms
  const supportingCounts = {
    depthArms,
    availableDepthArms,
    cleanDepthArms,
    watchDepthArms,
    restRestrictedDepthArms,
    unavailableDepthArms,
    limitedReadDepthArms,
    activeBullpenArms: summary.activeBullpenArms,
    totalBullpenArms: summary.totalBullpenArms,
    roleKnownCount: summary.dataQuality.roleKnownCount,
  }

  if (summary.dataQuality.roleSparse) {
    return limitedRead(
      'depthSafety',
      roleLimitedExplanation(summary.dataQuality.roleKnownCount, summary.totalBullpenArms, 'Depth Safety'),
      supportingCounts,
    )
  }

  const explanation = `${depthArms} Depth Arms in a ${summary.totalBullpenArms}-arm bullpen; ${availableDepthArms} are Clean Options or Watch Arms, ${restRestrictedDepthArms} are Rest-Restricted, and ${unavailableDepthArms} are Unavailable.`
  if (summary.totalBullpenArms >= 8 && depthArms >= 3 && availableDepthArms >= 2) {
    return read('depthSafety', 'Strong Depth Safety', explanation, supportingCounts)
  }
  if (summary.totalBullpenArms >= 7 && depthArms >= 2 && availableDepthArms >= 1) {
    return read('depthSafety', 'Stable Depth Safety', explanation, supportingCounts)
  }
  if (depthArms >= 1 && availableDepthArms >= 1) {
    return read('depthSafety', 'Thin Depth Safety', explanation, supportingCounts)
  }
  return read('depthSafety', 'Limited Depth Safety', explanation, supportingCounts)
}

export function getTeamBullpenShape(input) {
  const summary = summarizePitchers(input)
  const reads = [
    trustAvailability(summary),
    cleanOptions(summary),
    bullpenPressure(summary),
    coverageSafety(summary),
    depthSafety(summary),
  ]
  const byKey = Object.fromEntries(reads.map(item => [item.key, item]))
  return {
    reads,
    byKey,
    trustAvailability: byKey.trustAvailability,
    cleanOptions: byKey.cleanOptions,
    bullpenPressure: byKey.bullpenPressure,
    coverageSafety: byKey.coverageSafety,
    depthSafety: byKey.depthSafety,
    supportingCounts: {
      totalBullpenArms: summary.totalBullpenArms,
      activeBullpenArms: summary.activeBullpenArms,
      roleKnownCount: summary.dataQuality.roleKnownCount,
      readKnownCount: summary.dataQuality.readKnownCount,
    },
  }
}

export function getTeamBullpenScoring(input) {
  return getTeamBullpenShape(input)
}

export function getTeamBullpenReadKeys() {
  return [...READ_KEYS]
}
