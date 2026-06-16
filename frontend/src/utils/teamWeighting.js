import { getPitcherLabels } from './pitcherLabels.js'

// Internal weighting foundation for team bullpen interpretation.
//
// This module answers "how many meaningful options are available?" rather than
// "how many arms are available?". It is an internal logic layer only: nothing
// here is a public score, ranking, leaderboard, or grade, and no UI surface or
// public label consumes it yet. Outputs use internal band vocabulary that is
// deliberately distinct from the approved public label sets in
// teamBullpenScoring.js so the two cannot be confused.

// Role influence hierarchy. Trust Arms carry the highest influence because a
// bullpen's usable shape tonight depends first on whether its late/high-leverage
// arms can pitch. Bridge Arms sit between Trust and Depth. Coverage Arms carry
// medium, context-specific influence: they matter most for length/coverage
// questions, less for late-inning availability. Depth Arms carry the lowest
// influence. Limited Read arms contribute nothing — an arm we cannot read is
// not a meaningful option.
export const ROLE_INFLUENCE = Object.freeze({
  trust_arm: Object.freeze({ weight: 3, tier: 'highest' }),
  bridge_arm: Object.freeze({ weight: 2, tier: 'medium' }),
  coverage_arm: Object.freeze({ weight: 2, tier: 'medium', contextual: 'coverage' }),
  depth_arm: Object.freeze({ weight: 1, tier: 'lowest' }),
  limited_read: Object.freeze({ weight: 0, tier: 'none' }),
})

// Read multipliers translate the current workload read into how much of an arm's
// role influence is actually usable tonight. A Watch Arm is half-usable: the
// arm can pitch but the read says check the recent workload first.
export const READ_USABILITY = Object.freeze({
  clean_option: 1,
  watch_arm: 0.5,
  rest_restricted: 0,
  unavailable: 0,
  limited_read: 0,
})

export const MEANINGFUL_OPTION_BANDS = Object.freeze([
  'broad',
  'workable',
  'narrow',
  'minimal',
  'limited_read',
])

const ROLE_KEY_ORDER = Object.freeze([
  'trust_arm',
  'bridge_arm',
  'coverage_arm',
  'depth_arm',
  'limited_read',
])

function asPitchers(input) {
  if (Array.isArray(input)) return input
  if (Array.isArray(input?.pitchers)) return input.pitchers
  if (!Array.isArray(input?.groups)) return []
  return input.groups.flatMap(group => (Array.isArray(group?.pitchers) ? group.pitchers : []))
}

function roleWeight(roleKey) {
  return ROLE_INFLUENCE[roleKey]?.weight ?? 0
}

function readUsability(readKey) {
  return READ_USABILITY[readKey] ?? 0
}

// Pressure on an arm is the inverse of its usability (a Rest-Restricted or
// Unavailable arm is fully lost tonight, a Watch Arm half-lost), scaled by the
// arm's role influence. Losing a Trust Arm therefore raises weighted pressure
// three times as much as losing a Depth Arm.
function pressureUnits(readKey) {
  return 1 - readUsability(readKey)
}

export function summarizeWeightedBullpen(input) {
  const pitchers = asPitchers(input)
  const roles = Object.fromEntries(ROLE_KEY_ORDER.map(key => [key, {
    arms: 0,
    cleanArms: 0,
    watchArms: 0,
    usableInfluence: 0,
    fullInfluence: 0,
    weightedPressure: 0,
  }]))

  let usableInfluence = 0
  let fullInfluence = 0
  let weightedPressure = 0
  let roleKnownCount = 0
  let readKnownCount = 0

  for (const card of pitchers) {
    const labels = getPitcherLabels(card)
    const roleKey = labels.role.key
    const readKey = labels.read.key
    const bucket = roles[roleKey] || roles.limited_read

    bucket.arms += 1
    if (roleKey !== 'limited_read') roleKnownCount += 1
    if (readKey !== 'limited_read') readKnownCount += 1
    if (readKey === 'clean_option') bucket.cleanArms += 1
    if (readKey === 'watch_arm') bucket.watchArms += 1

    const weight = roleWeight(roleKey)
    const usable = weight * readUsability(readKey)
    const pressure = weight * pressureUnits(readKey)
    bucket.usableInfluence += usable
    bucket.fullInfluence += weight
    bucket.weightedPressure += pressure
    usableInfluence += usable
    fullInfluence += weight
    weightedPressure += pressure
  }

  const totalBullpenArms = pitchers.length
  const tinyBullpen = totalBullpenArms > 0 && totalBullpenArms < 4
  const limitedRead =
    totalBullpenArms === 0 ||
    tinyBullpen ||
    roleKnownCount < Math.ceil(totalBullpenArms * 0.5) ||
    readKnownCount < Math.ceil(totalBullpenArms * 0.5)

  return {
    totalBullpenArms,
    roleKnownCount,
    readKnownCount,
    limitedRead,
    roles,
    usableInfluence,
    fullInfluence,
    weightedPressure,
    trustPressure: roles.trust_arm.weightedPressure,
    usableShare: fullInfluence > 0 ? usableInfluence / fullInfluence : 0,
  }
}

// Internal band describing how many meaningful options the bullpen carries
// tonight. Bands are gated on Trust Arm usability first: a bullpen with no
// usable trust influence cannot read better than "narrow" no matter how many
// clean depth arms it carries, and a bullpen whose trust arms are fully clean
// is protected from reading worse than "workable" on volume alone.
export function meaningfulOptionsBand(input) {
  const summary = typeof input?.usableShare === 'number' && input?.roles
    ? input
    : summarizeWeightedBullpen(input)

  if (summary.limitedRead) {
    return { band: 'limited_read', summary }
  }

  const trust = summary.roles.trust_arm
  const trustUsable = trust.usableInfluence > 0
  const trustFullyClean = trust.arms > 0 && trust.cleanArms === trust.arms
  const share = summary.usableShare

  let band
  if (share >= 0.7) band = 'broad'
  else if (share >= 0.45) band = 'workable'
  else if (share >= 0.2) band = 'narrow'
  else band = 'minimal'

  if (!trustUsable && (band === 'broad' || band === 'workable')) {
    band = 'narrow'
  }
  if (trustFullyClean && (band === 'narrow' || band === 'minimal')) {
    band = 'workable'
  }

  return { band, summary }
}

// Context-specific coverage view: Coverage Arms dominate the coverage question,
// with Depth Arms as partial fallback length. Trust Arms intentionally do not
// raise coverage usability — a clean closer adds no multi-inning coverage.
export function coverageUsability(input) {
  const summary = typeof input?.usableShare === 'number' && input?.roles
    ? input
    : summarizeWeightedBullpen(input)

  if (summary.limitedRead) {
    return { band: 'limited_read', usableCoverageInfluence: 0, summary }
  }

  const coverage = summary.roles.coverage_arm
  const depth = summary.roles.depth_arm
  const usableCoverageInfluence = coverage.usableInfluence + depth.usableInfluence * 0.5

  let band
  if (coverage.cleanArms >= 2) band = 'broad'
  else if (usableCoverageInfluence >= 2) band = 'workable'
  else if (usableCoverageInfluence >= 1) band = 'narrow'
  else band = 'minimal'

  return { band, usableCoverageInfluence, summary }
}

export function getTeamWeightingFoundation(input) {
  const summary = summarizeWeightedBullpen(input)
  return {
    summary,
    meaningfulOptions: meaningfulOptionsBand(summary),
    coverage: coverageUsability(summary),
  }
}
