import { getPitcherLabels } from './pitcherLabels.js'
import { READ_USABILITY, ROLE_INFLUENCE } from './teamWeighting.js'

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
  bridge: 'Bridge Arm',
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
    bridge: emptyLabelCounts(Object.values(READ_LABELS)),
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
    if (roleLabel === ROLE_LABELS.bridge) roleReadCounts.bridge[readLabel] += 1
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

// Clean Options interpretation tiers, ordered weakest to strongest. The public
// labels are unchanged; weighting only affects which tier the raw count earns.
const CLEAN_OPTIONS_TIERS = ['Very Thin Clean Options', 'Thin Clean Options', 'Healthy Clean Options', 'Deep Clean Options']
const CLEAN_TIER_VERY_THIN = 0
const CLEAN_TIER_THIN = 1
const CLEAN_TIER_HEALTHY = 2
const CLEAN_TIER_DEEP = 3

function cleanOptions(summary) {
  const cleanOptionCount = summary.readCounts[READ_LABELS.clean]
  const restRestrictedCount = summary.readCounts[READ_LABELS.restricted]
  const unavailableCount = summary.readCounts[READ_LABELS.unavailable]
  const limitedReadCount = summary.readCounts[READ_LABELS.limited]

  // Clean composition by role. The raw count stays the honest headline; these
  // tell us how many of those clean options are actually meaningful.
  const cleanTrustArms = summary.roleReadCounts.trust[READ_LABELS.clean]
  const cleanBridgeArms = summary.roleReadCounts.bridge[READ_LABELS.clean]
  const cleanCoverageArms = summary.roleReadCounts.coverage[READ_LABELS.clean]
  const cleanDepthArms = summary.roleReadCounts.depth[READ_LABELS.clean]
  // Bridge and Coverage Arms are meaningful clean backing; Depth Arms alone are
  // not. A bullpen whose only clean arms are Depth Arms has bodies, not options.
  const meaningfulCleanBacking = cleanTrustArms >= 1 || cleanBridgeArms >= 1 || cleanCoverageArms >= 1

  const supportingCounts = {
    cleanOptionCount,
    activeBullpenArms: summary.activeBullpenArms,
    totalBullpenArms: summary.totalBullpenArms,
    restRestrictedCount,
    unavailableCount,
    limitedReadCount,
    cleanTrustArms,
    cleanBridgeArms,
    cleanCoverageArms,
    cleanDepthArms,
    meaningfulCleanBacking,
  }

  if (summary.dataQuality.readSparse) {
    return limitedRead(
      'cleanOptions',
      `Only ${summary.dataQuality.readKnownCount} of ${summary.totalBullpenArms} bullpen arms have clear current reads, so Clean Options is a Limited Read.`,
      supportingCounts,
    )
  }

  // Raw count sets the honest base tier — you can never read deeper than your
  // body count supports.
  let tier
  if (cleanOptionCount >= 6 || (summary.activeBullpenArms >= 7 && cleanOptionCount >= 5)) {
    tier = CLEAN_TIER_DEEP
  } else if (cleanOptionCount >= 4) {
    tier = CLEAN_TIER_HEALTHY
  } else if (cleanOptionCount >= 2) {
    tier = CLEAN_TIER_THIN
  } else {
    tier = CLEAN_TIER_VERY_THIN
  }

  // Trust-backed upgrade: a genuine clean Trust Arm pair lifts a low body count
  // into Healthy — two trusted options matter more than the count suggests.
  if (cleanTrustArms >= 2 && tier < CLEAN_TIER_HEALTHY) {
    tier = CLEAN_TIER_HEALTHY
  }
  // Deep is reserved for a real clean Trust Arm core; depth volume alone cannot
  // reach the strongest interpretation.
  if (tier === CLEAN_TIER_DEEP && cleanTrustArms < 2) {
    tier = CLEAN_TIER_HEALTHY
  }
  // With no meaningful clean backing at all (only clean Depth Arms), the read
  // cannot exceed Thin no matter how many bodies are available.
  if (!meaningfulCleanBacking && tier > CLEAN_TIER_THIN) {
    tier = CLEAN_TIER_THIN
  }

  const explanation = `${cleanOptionCount} Clean Options out of ${summary.activeBullpenArms} active bullpen arms — ${cleanTrustArms} Trust, ${cleanBridgeArms} Bridge, ${cleanCoverageArms} Coverage, ${cleanDepthArms} Depth, with ${restRestrictedCount} Rest-Restricted and ${unavailableCount} Unavailable. Interpretation weighs clean Trust Arms above clean Depth Arms.`
  return read('cleanOptions', CLEAN_OPTIONS_TIERS[tier], explanation, supportingCounts)
}

// Weighted-pressure thresholds. Trust-arm stress is read on its own scale so a
// single restricted Trust Arm (weight 3) clears the elevated bar on its own and
// a Trust Arm pair lost clears the high bar, while the same loss among Depth
// Arms (weight 1) does not. ``pressureShare`` is the fraction of the bullpen's
// total role influence currently under stress, which keeps the read stable
// across bullpen sizes.
const TRUST_PRESSURE_HIGH = 4.5
const TRUST_PRESSURE_ELEVATED = 2.5
const ROLE_STRESS_ELEVATED = 2
const PRESSURE_SHARE_HIGH = 0.45
const PRESSURE_SHARE_ELEVATED = 0.25

// Pressure contributed by a role's current reads, scaled by role influence. Only
// Watch / Rest-Restricted / Unavailable reads carry pressure (Clean Options and
// Limited Reads add none), matching the prior model's inputs but weighting them
// by role. Read pressure is the inverse of read usability, so a Watch Arm is
// half the load of a fully lost arm.
function rolePressure(reads, weight) {
  if (!reads) return 0
  const load =
    (reads[READ_LABELS.watch] || 0) * (1 - READ_USABILITY.watch_arm) +
    (reads[READ_LABELS.restricted] || 0) * (1 - READ_USABILITY.rest_restricted) +
    (reads[READ_LABELS.unavailable] || 0) * (1 - READ_USABILITY.unavailable)
  return weight * load
}

function bullpenPressure(summary) {
  const watchArmCount = summary.readCounts[READ_LABELS.watch]
  const restRestrictedCount = summary.readCounts[READ_LABELS.restricted]
  const unavailableCount = summary.readCounts[READ_LABELS.unavailable]
  const limitedReadCount = summary.readCounts[READ_LABELS.limited]

  const trustReads = summary.roleReadCounts.trust
  const bridgeReads = summary.roleReadCounts.bridge
  const coverageReads = summary.roleReadCounts.coverage
  const depthReads = summary.roleReadCounts.depth

  const trustPressure = rolePressure(trustReads, ROLE_INFLUENCE.trust_arm.weight)
  const bridgePressure = rolePressure(bridgeReads, ROLE_INFLUENCE.bridge_arm.weight)
  const coveragePressure = rolePressure(coverageReads, ROLE_INFLUENCE.coverage_arm.weight)
  const depthPressure = rolePressure(depthReads, ROLE_INFLUENCE.depth_arm.weight)
  const weightedPressure = trustPressure + bridgePressure + coveragePressure + depthPressure

  const fullInfluence =
    summary.roleCounts[ROLE_LABELS.trust] * ROLE_INFLUENCE.trust_arm.weight +
    summary.roleCounts[ROLE_LABELS.bridge] * ROLE_INFLUENCE.bridge_arm.weight +
    summary.roleCounts[ROLE_LABELS.coverage] * ROLE_INFLUENCE.coverage_arm.weight +
    summary.roleCounts[ROLE_LABELS.depth] * ROLE_INFLUENCE.depth_arm.weight
  const pressureShare = fullInfluence > 0 ? weightedPressure / fullInfluence : 0

  const cleanTrustArms = trustReads[READ_LABELS.clean]
  const watchTrustArms = trustReads[READ_LABELS.watch]
  const restrictedTrustArms = trustReads[READ_LABELS.restricted]
  const unavailableTrustArms = trustReads[READ_LABELS.unavailable]
  const usableTrustArms = cleanTrustArms + watchTrustArms
  const stressedBridgeArms = bridgeReads[READ_LABELS.restricted] + bridgeReads[READ_LABELS.unavailable]
  const stressedCoverageArms = coverageReads[READ_LABELS.restricted] + coverageReads[READ_LABELS.unavailable]
  // No usable Trust Arm means no trusted option to lean on in the current read, regardless
  // of how many rested Depth Arms remain. This is the "meaningful options"
  // floor: such a bullpen can never read Low and lands at least Elevated.
  const noUsableTrust = usableTrustArms === 0

  const supportingCounts = {
    watchArmCount,
    restRestrictedCount,
    unavailableCount,
    highFatigueArms: summary.highFatigueArms,
    limitedReadCount,
    totalBullpenArms: summary.totalBullpenArms,
    cleanTrustArms,
    restrictedTrustArms,
    unavailableTrustArms,
    usableTrustArms,
    stressedBridgeArms,
    stressedCoverageArms,
    noUsableTrust,
  }

  if (summary.dataQuality.readSparse) {
    return limitedRead(
      'bullpenPressure',
      `Only ${summary.dataQuality.readKnownCount} of ${summary.totalBullpenArms} bullpen arms have clear current reads, so Bullpen Pressure is a Limited Read.`,
      supportingCounts,
    )
  }

  const explanation = `Trust Arms show ${cleanTrustArms} clean, ${restrictedTrustArms} Rest-Restricted, and ${unavailableTrustArms} Unavailable; ${stressedBridgeArms} Bridge Arms and ${stressedCoverageArms} Coverage Arms are stressed, alongside ${summary.highFatigueArms} high-fatigue arms. Pressure weighs Trust and Bridge Arm stress above Depth Arm stress.`

  if (
    trustPressure >= TRUST_PRESSURE_HIGH ||
    pressureShare >= PRESSURE_SHARE_HIGH ||
    summary.stressState === 'constrained'
  ) {
    return read('bullpenPressure', 'High Bullpen Pressure', explanation, supportingCounts)
  }
  if (
    trustPressure >= TRUST_PRESSURE_ELEVATED ||
    bridgePressure >= ROLE_STRESS_ELEVATED ||
    coveragePressure >= ROLE_STRESS_ELEVATED ||
    pressureShare >= PRESSURE_SHARE_ELEVATED ||
    noUsableTrust ||
    watchArmCount >= 3 ||
    summary.highFatigueArms >= 2 ||
    summary.stressState === 'elevated' ||
    summary.stressState === 'monitoring'
  ) {
    return read('bullpenPressure', 'Elevated Bullpen Pressure', explanation, supportingCounts)
  }
  if (
    restRestrictedCount === 0 &&
    unavailableCount === 0 &&
    watchArmCount <= 1 &&
    summary.highFatigueArms === 0 &&
    usableTrustArms > 0
  ) {
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

  // Substitute-coverage guardrail. Coverage Safety stays coverage-led: only
  // designated Coverage Arms can earn Strong/Stable/Thin through the gates
  // below. But a bullpen whose designated length is degraded or absent is not
  // automatically in an innings emergency when usable Bridge Arms can chain
  // emergency innings behind it. Meaningful substitute capacity is at least
  // one clean Bridge Arm, or two on watch (a watched arm is half-usable, per
  // the read-usability semantics). It lifts the floor only — Limited becomes
  // Thin — and never raises any other tier, so designated Coverage Arms remain
  // the only path to Strong or Stable and depth volume still earns nothing.
  const cleanBridgeArms = summary.roleReadCounts.bridge[READ_LABELS.clean]
  const watchBridgeArms = summary.roleReadCounts.bridge[READ_LABELS.watch]
  const hasSubstituteCoverage = cleanBridgeArms >= 1 || watchBridgeArms >= 2

  const supportingCounts = {
    coverageArms,
    availableCoverageArms,
    cleanCoverageArms,
    watchCoverageArms,
    restRestrictedCoverageArms,
    unavailableCoverageArms,
    limitedReadCoverageArms,
    cleanBridgeArms,
    watchBridgeArms,
    substituteCoverageApplied: false,
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
  if (hasSubstituteCoverage) {
    const bridgeFallback = [
      cleanBridgeArms > 0 ? `${cleanBridgeArms} clean Bridge Arm${cleanBridgeArms === 1 ? '' : 's'}` : null,
      watchBridgeArms > 0 ? `${watchBridgeArms} Bridge Arm${watchBridgeArms === 1 ? '' : 's'} on watch` : null,
    ].filter(Boolean).join(' and ')
    const liftedExplanation = `${explanation} No designated Coverage Arm is available, but ${bridgeFallback} can chain emergency innings, so coverage reads Thin rather than Limited — substitute capacity, not designated length.`
    return read(
      'coverageSafety',
      'Thin Coverage Safety',
      liftedExplanation,
      { ...supportingCounts, substituteCoverageApplied: true },
    )
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

  // Depth Safety answers "if the primary arms become unavailable, how much
  // fallback exists?" — which only means something when there is a usable
  // primary corps to fall back from. A bullpen with no usable Trust Arm has no
  // anchored late-inning option, so its Depth Arms are the front line, not
  // fallback. This trust-anchor read is a guardrail only: Depth Safety still
  // describes depth, and Trust Arm influence never inflates the depth count.
  const usableTrustArms = summary.roleReadCounts.trust[READ_LABELS.clean] + summary.roleReadCounts.trust[READ_LABELS.watch]
  const anchoredByTrust = usableTrustArms > 0
  const supportingCounts = {
    depthArms,
    availableDepthArms,
    cleanDepthArms,
    watchDepthArms,
    restRestrictedDepthArms,
    unavailableDepthArms,
    limitedReadDepthArms,
    usableTrustArms,
    anchoredByTrust,
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

  const baseExplanation = `${depthArms} Depth Arms in a ${summary.totalBullpenArms}-arm bullpen; ${availableDepthArms} are Clean Options or Watch Arms, ${restRestrictedDepthArms} are Rest-Restricted, and ${unavailableDepthArms} are Unavailable.`
  const strongByVolume = summary.totalBullpenArms >= 8 && depthArms >= 3 && availableDepthArms >= 2

  // Guardrail: deep volume only reads Strong when a usable Trust Arm anchors the
  // bullpen behind that depth. Without one, the same volume reads Stable —
  // fallback arms with no primary corps in front of them.
  if (strongByVolume && anchoredByTrust) {
    return read('depthSafety', 'Strong Depth Safety', baseExplanation, supportingCounts)
  }
  if (strongByVolume && !anchoredByTrust) {
    const explanation = `${baseExplanation} No usable Trust Arm anchors the bullpen, so this depth reads Stable rather than Strong — fallback volume without a primary corps in front of it.`
    return read('depthSafety', 'Stable Depth Safety', explanation, supportingCounts)
  }
  if (summary.totalBullpenArms >= 7 && depthArms >= 2 && availableDepthArms >= 1) {
    return read('depthSafety', 'Stable Depth Safety', baseExplanation, supportingCounts)
  }
  if (depthArms >= 1 && availableDepthArms >= 1) {
    return read('depthSafety', 'Thin Depth Safety', baseExplanation, supportingCounts)
  }
  return read('depthSafety', 'Limited Depth Safety', baseExplanation, supportingCounts)
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
