// Team Bullpen Story Surface V1. Derives one compact team-level briefing from
// the board payload already fetched for this bullpen: workload buckets, role
// labels, read labels, shape reads, and the visible pitcher cards.

import { getBullpenReads } from '../../../utils/bullpenConcepts'
import { getPitcherLabels } from '../../../utils/pitcherLabels'
import { getTeamBullpenShape } from '../../../utils/teamBullpenScoring'

const STORY_TONES = {
  stress: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
  watch: { borderColor: '#eab30855', backgroundColor: '#eab30812', color: '#fde047', dot: '#eab308' },
  rest: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  balanced: { borderColor: 'rgba(148,163,184,0.32)', backgroundColor: 'rgba(148,163,184,0.09)', color: '#cbd5e1', dot: '#94a3b8' },
  data_limited: { borderColor: 'rgba(148,163,184,0.32)', backgroundColor: 'rgba(148,163,184,0.09)', color: '#cbd5e1', dot: '#94a3b8' },
}

export const TEAM_STORY_ARCHETYPES = Object.freeze({
  heavy_lifting: { key: 'heavy_lifting', label: 'Heavy Lifting', family: 'watch', tone: 'watch' },
  concentrated_workload: { key: 'concentrated_workload', label: 'Concentrated Workload', family: 'watch', tone: 'watch' },
  thin_margin: { key: 'thin_margin', label: 'Thin Margin', family: 'constrained', tone: 'stress' },
  recovery_window: { key: 'recovery_window', label: 'Recovery Window', family: 'rested', tone: 'rest' },
  depth_advantage: { key: 'depth_advantage', label: 'Depth Advantage', family: 'rested', tone: 'rest' },
  coverage_concern: { key: 'coverage_concern', label: 'Coverage Concern', family: 'constrained', tone: 'stress' },
  trust_dependency: { key: 'trust_dependency', label: 'Trust Dependency', family: 'constrained', tone: 'stress' },
  bridge_dependency: { key: 'bridge_dependency', label: 'Bridge Dependency', family: 'watch', tone: 'watch' },
  usage_shift: { key: 'usage_shift', label: 'Usage Shift', family: 'watch', tone: 'watch' },
  stable_bullpen: { key: 'stable_bullpen', label: 'Stable Bullpen', family: 'balanced', tone: 'balanced' },
  pressure_building: { key: 'pressure_building', label: 'Pressure Building', family: 'watch', tone: 'watch' },
  rested_flexibility: { key: 'rested_flexibility', label: 'Rested Flexibility', family: 'rested', tone: 'rest' },
  data_limited: { key: 'data_limited', label: 'Limited Read', family: 'data_limited', tone: 'data_limited' },
})

export const STORY_FRAMING_LINE =
  'Built from current workload, roster status, and usage-role reads already shown on this board.'

const SHAPE_READ_ORDER = [
  { key: 'trustAvailability', concept: 'Trust Arm Availability' },
  { key: 'cleanOptions', concept: 'Clean Options' },
  { key: 'bullpenPressure', concept: 'Bullpen Pressure' },
  { key: 'coverageSafety', concept: 'Coverage Safety' },
  { key: 'depthSafety', concept: 'Depth Safety' },
]

const READ_COUNT_PLURALS = {
  'Clean Option': 'Clean Options',
  'Watch Arm': 'Watch Arms',
  'Rest-Restricted': 'Rest-Restricted',
  Unavailable: 'Unavailable',
}

const ROLE_PRIORITY = {
  'Trust Arm': 0,
  'Bridge Arm': 1,
  'Coverage Arm': 2,
  'Depth Arm': 3,
  'Limited Read': 4,
}

const READ_PRIORITY = {
  'Rest-Restricted': 0,
  'Watch Arm': 1,
  'Unavailable': 2,
  'Clean Option': 3,
  'Limited Read': 4,
}

const STATUS_TO_READ = {
  Available: 'Clean Option',
  Monitor: 'Watch Arm',
  Limited: 'Rest-Restricted',
  Avoid: 'Rest-Restricted',
  Unavailable: 'Unavailable',
}

const NON_PLAYER_NAME_PHRASES = new Set([
  'active mlb',
  'avoid',
  'available',
  'bridge arm',
  'bridge dependency',
  'bullpen pressure',
  'clean option',
  'clean options',
  'concentrated workload',
  'coverage arm',
  'coverage concern',
  'coverage safety',
  'data limited',
  'deep pen advantage',
  'depth advantage',
  'depth arm',
  'depth safety',
  'heavy lifting',
  'limited',
  'limited read',
  'monitor',
  'pressure building',
  'recovery window',
  'rest restricted',
  'rest-restricted',
  'rested flexibility',
  'stable bullpen',
  'strong read',
  'thin margin',
  'trust arm',
  'trust arm availability',
  'trust dependency',
  'unavailable',
  'usage shift',
  'watch arm',
  'watch list',
  'watch-list arm',
  'watch-list arms',
])

const NON_PLAYER_NAME_TOKENS = new Set([
  'active',
  'advantage',
  'arm',
  'arms',
  'avoid',
  'available',
  'bridge',
  'building',
  'bullpen',
  'clean',
  'concentrated',
  'concern',
  'coverage',
  'deep',
  'dependency',
  'depth',
  'flexibility',
  'heavy',
  'limited',
  'lifting',
  'list',
  'margin',
  'mlb',
  'monitor',
  'option',
  'options',
  'pressure',
  'read',
  'recovery',
  'rest',
  'restricted',
  'safety',
  'stable',
  'strong',
  'thin',
  'trust',
  'unavailable',
  'usage',
  'watch',
  'window',
  'workload',
])

const PITCHER_NAME_FIELDS = [
  card => card?.name,
  card => card?.player_name,
  card => card?.pitcher_name,
  card => card?.full_name,
  card => card?.pitcher?.full_name,
  card => card?.pitcher?.name,
  card => card?.player?.full_name,
  card => card?.player?.name,
]

const arms = (n) => `${n} arm${n === 1 ? '' : 's'}`
const relievers = (n) => `${n} reliever${n === 1 ? '' : 's'}`
const one = (n, singular, plural) => (n === 1 ? singular : plural)
const number = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : 0)
const readCount = (n, label) => `${n} ${n === 1 ? label : (READ_COUNT_PLURALS[label] || `${label}s`)}`
const cleanLabel = (value) => String(value || '').trim()
const compactLabel = (value) => cleanLabel(value).replace(/\s+/g, ' ')
const normalizedNameWords = (value) => compactLabel(value).toLowerCase().match(/[a-z0-9]+/g) || []

export function isValidPitcherEvidenceName(value) {
  const name = compactLabel(value)
  if (!name) return false

  const normalized = name
    .toLowerCase()
    .replace(/[_.]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (NON_PLAYER_NAME_PHRASES.has(normalized)) return false

  const words = normalizedNameWords(name)
  if (words.length < 2) return false
  if (words.some(word => NON_PLAYER_NAME_TOKENS.has(word))) return false

  return /[a-z]/i.test(name)
}

export function getPitcherEvidenceName(card) {
  for (const getter of PITCHER_NAME_FIELDS) {
    const candidate = compactLabel(getter(card))
    if (isValidPitcherEvidenceName(candidate)) return candidate
  }
  return ''
}

function boardCounts(board) {
  const metrics = board?.context?.metrics || {}
  const count = (key) => number(metrics[key])
  return {
    total: count('total_relievers'),
    ready: count('available'),
    watch: count('monitor'),
    needRest: count('limited') + count('avoid'),
    limited: count('limited'),
    avoid: count('avoid'),
    out: count('unavailable'),
    pctAvailable: count('pct_available'),
  }
}

function readCounts(shape, key) {
  return shape?.byKey?.[key]?.supportingCounts || {}
}

function readLabel(shape, key) {
  return cleanLabel(shape?.byKey?.[key]?.label)
}

function hasThinOrLimited(label) {
  return /^(Thin|Limited|Very Thin)\b/.test(label)
}

function hasStrongOrStable(label) {
  return /^(Strong|Stable|Deep|Healthy|Low)\b/.test(label)
}

function hasCoverageSpecificStress(coverage) {
  const coverageArms = number(coverage?.coverageArms)
  if (coverageArms <= 0) return false

  const stressedCoverageArms =
    number(coverage?.restRestrictedCoverageArms) + number(coverage?.unavailableCoverageArms)
  const availableCoverageArms = number(coverage?.availableCoverageArms)
  return stressedCoverageArms > 0 || availableCoverageArms / coverageArms <= 0.5
}

function flattenPitchers(board) {
  const groups = Array.isArray(board?.groups) ? board.groups : []
  return groups.flatMap((group, groupIndex) => {
    const status = cleanLabel(group?.status)
    return (Array.isArray(group?.pitchers) ? group.pitchers : []).map((card, index) => ({
      card,
      status: cleanLabel(card?.availability_status || status),
      groupIndex,
      index,
      labels: getPitcherLabels(card),
    }))
  })
}

function cardName(entry) {
  return getPitcherEvidenceName(entry?.card)
}

function cardFatigue(entry) {
  return number(entry?.card?.fatigue_score ?? entry?.card?.raw_score ?? entry?.card?.availability?.fatigue_score)
}

function roleLabel(entry) {
  return entry?.labels?.role?.label || 'Limited Read'
}

function readLabelForPitcher(entry) {
  return entry?.labels?.read?.label || STATUS_TO_READ[entry?.status] || 'Limited Read'
}

function roleRank(entry) {
  return ROLE_PRIORITY[roleLabel(entry)] ?? 9
}

function readRank(entry) {
  return READ_PRIORITY[readLabelForPitcher(entry)] ?? 9
}

function comparePitchers(a, b) {
  return (
    roleRank(a) - roleRank(b)
    || readRank(a) - readRank(b)
    || cardFatigue(b) - cardFatigue(a)
    || cardName(a).localeCompare(cardName(b))
    || number(a?.card?.pitcher_id) - number(b?.card?.pitcher_id)
    || a.groupIndex - b.groupIndex
    || a.index - b.index
  )
}

function uniqueEntries(entries) {
  const seen = new Set()
  const unique = []
  for (const entry of entries) {
    const key = entry?.card?.pitcher_id ?? cardName(entry)
    if (!key || seen.has(key)) continue
    seen.add(key)
    unique.push(entry)
  }
  return unique
}

function entriesBy(entries, predicate) {
  return uniqueEntries(entries.filter(entry => cardName(entry) && predicate(entry)).sort(comparePitchers))
}

function stressedEntries(entries) {
  return entriesBy(entries, entry => ['Watch Arm', 'Rest-Restricted', 'Unavailable'].includes(readLabelForPitcher(entry)))
}

function cleanEntries(entries) {
  return entriesBy(entries, entry => readLabelForPitcher(entry) === 'Clean Option')
}

function roleEntries(entries, roles, reads = null) {
  const allowedRoles = new Set(roles)
  const allowedReads = reads ? new Set(reads) : null
  return entriesBy(entries, entry => {
    if (!allowedRoles.has(roleLabel(entry))) return false
    return !allowedReads || allowedReads.has(readLabelForPitcher(entry))
  })
}

function evidencePitchers(archetypeKey, entries) {
  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      return [
        ...roleEntries(entries, ['Trust Arm', 'Bridge Arm', 'Coverage Arm'], ['Clean Option']),
        ...cleanEntries(entries),
      ].slice(0, 4)
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      return [
        ...roleEntries(entries, ['Coverage Arm'], ['Watch Arm', 'Rest-Restricted', 'Unavailable']),
        ...roleEntries(entries, ['Bridge Arm'], ['Watch Arm', 'Rest-Restricted', 'Unavailable']),
      ].slice(0, 4)
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      return roleEntries(entries, ['Trust Arm'], ['Watch Arm', 'Rest-Restricted', 'Unavailable']).slice(0, 4)
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      return roleEntries(entries, ['Bridge Arm'], ['Watch Arm', 'Rest-Restricted', 'Unavailable', 'Clean Option']).slice(0, 4)
    case TEAM_STORY_ARCHETYPES.stable_bullpen.key:
      return [
        ...roleEntries(entries, ['Trust Arm', 'Bridge Arm'], ['Clean Option', 'Watch Arm']),
        ...cleanEntries(entries),
      ].slice(0, 4)
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      return entriesBy(entries, entry => readLabelForPitcher(entry) === 'Limited Read').slice(0, 4)
    default:
      return stressedEntries(entries).slice(0, 4)
  }
}

function evidenceNames(entries) {
  const seen = new Set()
  const names = []
  for (const entry of entries) {
    const name = cardName(entry)
    const key = name.toLowerCase()
    if (!name || seen.has(key)) continue
    seen.add(key)
    names.push(name)
    if (names.length >= 4) break
  }
  return names
}

function formatNameList(names) {
  if (names.length === 0) return ''
  if (names.length === 1) return names[0]
  if (names.length === 2) return `${names[0]} and ${names[1]}`
  return `${names.slice(0, -1).join(', ')}, and ${names[names.length - 1]}`
}

function compactReadCounts(items, fallback) {
  const parts = items
    .filter(item => item.count > 0)
    .map(item => readCount(item.count, item.label))
  return parts.length ? `${parts.join('; ')}.` : fallback
}

function shortShapeExplanation(read) {
  const counts = read?.supportingCounts || {}
  switch (read?.key) {
    case 'trustAvailability':
      return `Trust Arms: ${compactReadCounts([
        { count: counts.cleanTrustArms, label: 'Clean Option' },
        { count: counts.watchTrustArms, label: 'Watch Arm' },
        { count: counts.restRestrictedTrustArms, label: 'Rest-Restricted' },
        { count: counts.unavailableTrustArms, label: 'Unavailable' },
      ], 'no Clean Options or Watch Arms.')}`
    case 'cleanOptions':
      if (counts.cleanOptionCount != null && counts.activeBullpenArms != null) {
        return `${counts.cleanOptionCount} Clean Options from ${counts.activeBullpenArms} active arms.`
      }
      break
    case 'bullpenPressure':
      return `Pressure: ${compactReadCounts([
        { count: counts.watchArmCount, label: 'Watch Arm' },
        { count: counts.restRestrictedCount, label: 'Rest-Restricted' },
        { count: counts.unavailableCount, label: 'Unavailable' },
      ], 'no Watch Arms, Rest-Restricted, or Unavailable arms.')}`
    case 'coverageSafety': {
      const base = `Coverage Arms: ${compactReadCounts([
        { count: counts.cleanCoverageArms, label: 'Clean Option' },
        { count: counts.watchCoverageArms, label: 'Watch Arm' },
        { count: counts.restRestrictedCoverageArms, label: 'Rest-Restricted' },
        { count: counts.unavailableCoverageArms, label: 'Unavailable' },
      ], 'no Clean Options or Watch Arms.')}`
      return counts.substituteCoverageApplied
        ? `${base} Bridge Arms cover emergency innings.`
        : base
    }
    case 'depthSafety':
      return `Depth Arms: ${compactReadCounts([
        { count: counts.cleanDepthArms, label: 'Clean Option' },
        { count: counts.watchDepthArms, label: 'Watch Arm' },
        { count: counts.restRestrictedDepthArms, label: 'Rest-Restricted' },
        { count: counts.unavailableDepthArms, label: 'Unavailable' },
      ], 'no Clean Options or Watch Arms.')}`
    default:
      break
  }
  return read?.explanation || 'Not enough current bullpen data for a confident read.'
}

function shapeTone(label) {
  if (!label || label === 'Limited Read') return 'neutral'
  if (/^(Strong|Stable|Deep|Healthy|Low)\b/.test(label)) return 'rest'
  if (/^(Thin|Elevated|Manageable)\b/.test(label)) return 'watch'
  if (/^(Very Thin|Limited|High)\b/.test(label)) return 'stress'
  return 'neutral'
}

function teamShapeReads(board) {
  const shape = getTeamBullpenShape(board)
  return SHAPE_READ_ORDER.map(item => {
    const read = shape.byKey[item.key]
    if (!read) return null
    return {
      key: item.key,
      concept: item.concept,
      label: read.label,
      explanation: shortShapeExplanation(read),
      tone: shapeTone(read.label),
    }
  }).filter(Boolean)
}

function hasUsageShiftSignal(board) {
  const context = board?.context || {}
  return Boolean(
    context.usage_shift
    || context.usageShift
    || context.workload_shift
    || context.workloadShift
    || context.change?.usage_shift
    || context.change?.workload_shift
  )
}

export function deriveTeamStoryArchetype(board) {
  const counts = boardCounts(board)
  const shape = getTeamBullpenShape(board)
  const healthState = board?.context?.health?.state || 'no_data'
  const trust = readCounts(shape, 'trustAvailability')
  const pressure = readCounts(shape, 'bullpenPressure')
  const coverage = readCounts(shape, 'coverageSafety')
  const depth = readCounts(shape, 'depthSafety')

  if (counts.total === 0 || healthState === 'no_data') return TEAM_STORY_ARCHETYPES.data_limited.key
  if (hasUsageShiftSignal(board)) return TEAM_STORY_ARCHETYPES.usage_shift.key
  if ((trust.restrictedTrustArms || 0) + (trust.unavailableTrustArms || 0) >= 2 || trust.availableTrustArms === 0) {
    return TEAM_STORY_ARCHETYPES.trust_dependency.key
  }
  if (
    hasThinOrLimited(readLabel(shape, 'coverageSafety'))
    && (healthState === 'constrained' || counts.ready <= 3 || readLabel(shape, 'bullpenPressure') === 'High Bullpen Pressure')
    && hasCoverageSpecificStress(coverage)
  ) {
    return TEAM_STORY_ARCHETYPES.coverage_concern.key
  }
  if (
    number(coverage.coverageArms) === 0
    && coverage.substituteCoverageApplied
    && number(pressure.stressedBridgeArms) >= 2
  ) {
    return TEAM_STORY_ARCHETYPES.bridge_dependency.key
  }
  if (counts.watch >= 4 && counts.watch > counts.needRest) return TEAM_STORY_ARCHETYPES.heavy_lifting.key
  if (counts.needRest >= 3 || readLabel(shape, 'bullpenPressure') === 'High Bullpen Pressure') {
    return TEAM_STORY_ARCHETYPES.thin_margin.key
  }
  if ((pressure.stressedBridgeArms || 0) >= 2) return TEAM_STORY_ARCHETYPES.bridge_dependency.key
  if (counts.watch >= 4) return TEAM_STORY_ARCHETYPES.heavy_lifting.key
  if (counts.watch >= 3) return TEAM_STORY_ARCHETYPES.concentrated_workload.key
  if (counts.ready >= 6 || readLabel(shape, 'cleanOptions') === 'Deep Clean Options') {
    if (hasStrongOrStable(readLabel(shape, 'depthSafety')) && (depth.availableDepthArms || 0) >= 2) {
      return TEAM_STORY_ARCHETYPES.depth_advantage.key
    }
    return counts.watch <= 1 && counts.needRest <= 1
      ? TEAM_STORY_ARCHETYPES.rested_flexibility.key
      : TEAM_STORY_ARCHETYPES.recovery_window.key
  }
  if (healthState === 'monitoring' || healthState === 'elevated' || counts.watch + counts.needRest >= 3) {
    return TEAM_STORY_ARCHETYPES.pressure_building.key
  }
  return TEAM_STORY_ARCHETYPES.stable_bullpen.key
}

// Backward-compatible family signal used by existing tests and render tone.
export function deriveStoryFamily(board) {
  const archetype = TEAM_STORY_ARCHETYPES[deriveTeamStoryArchetype(board)] || TEAM_STORY_ARCHETYPES.stable_bullpen
  return archetype.family
}

function headlineFor(archetypeKey, teamName) {
  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.heavy_lifting.key:
      return `The ${teamName} keep asking the same relievers to carry the workload.`
    case TEAM_STORY_ARCHETYPES.concentrated_workload.key:
      return `The ${teamName} are carrying bullpen work through a small group.`
    case TEAM_STORY_ARCHETYPES.thin_margin.key:
      return `The ${teamName} enter today with a thin late-inning margin.`
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
      return `The ${teamName} have more room to maneuver than earlier in the window.`
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      return `The ${teamName} have multiple routes through the late innings.`
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      return `The ${teamName} have a tighter coverage picture than usual.`
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      return `The ${teamName} bullpen leans heavily on its trust group.`
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      return `The ${teamName} are leaning on the bridge layer again.`
    case TEAM_STORY_ARCHETYPES.usage_shift.key:
      return `The ${teamName} bullpen is entering a different workload phase.`
    case TEAM_STORY_ARCHETYPES.pressure_building.key:
      return `The ${teamName} have bullpen pressure building under the surface.`
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
      return `The ${teamName} have unusual bullpen flexibility today.`
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      return `BaseballOS has a limited bullpen read for the ${teamName} today.`
    default:
      return `The ${teamName} bullpen is holding a steady shape today.`
  }
}

function observationFor(archetypeKey, counts, shape) {
  const trust = readCounts(shape, 'trustAvailability')
  const pressure = readCounts(shape, 'bullpenPressure')
  const coverage = readCounts(shape, 'coverageSafety')
  const depth = readCounts(shape, 'depthSafety')
  const active = readCounts(shape, 'cleanOptions').activeBullpenArms || counts.total

  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.heavy_lifting.key:
      return `${relievers(counts.watch)} of ${counts.total} sit on the watch list, so recent bullpen work is flowing through a narrow group.`
    case TEAM_STORY_ARCHETYPES.concentrated_workload.key:
      return `${relievers(counts.watch)} are carrying enough recent work to change how clean the bullpen looks beneath the overall count.`
    case TEAM_STORY_ARCHETYPES.thin_margin.key:
      return `${relievers(counts.needRest)} of ${counts.total} ${one(counts.needRest, 'needs', 'need')} rest after recent work, leaving fewer clean paths through the late innings.`
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
      return `${relievers(counts.ready)} of ${counts.total} come in rested, giving this bullpen more room than it had during heavier stretches.`
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      return `The clean group runs beyond one or two primary arms, with ${depth.availableDepthArms || 0} depth arms still usable behind the main late-inning layer.`
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      return number(coverage.coverageArms) > 0
        ? `The coverage layer is tighter than usual: ${coverage.availableCoverageArms || 0} of ${coverage.coverageArms || 0} Coverage Arms are clean or on watch.`
        : 'The coverage layer is tighter than usual because the board has no designated Coverage Arm support today.'
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      return `The trust group is carrying the shape of this bullpen, with ${trust.cleanTrustArms || 0} clean Trust Arms and ${((trust.watchTrustArms || 0) + (trust.restRestrictedTrustArms || 0) + (trust.unavailableTrustArms || 0))} trust reads under pressure.`
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      return `${number(pressure.stressedBridgeArms)} ${one(number(pressure.stressedBridgeArms), 'Bridge Arm is', 'Bridge Arms are')} carrying stress in the current read, tightening the handoff before the late innings.`
    case TEAM_STORY_ARCHETYPES.usage_shift.key:
      return `The current window is reading differently from the prior bullpen shape, so the workload is landing in new places.`
    case TEAM_STORY_ARCHETYPES.pressure_building.key:
      return `${relievers(counts.watch + counts.needRest)} are either on watch or need rest, which is enough to change how much margin this pen has.`
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
      return `${relievers(counts.ready)} of ${counts.total} are clean options, giving the bullpen more usable routes than a busier group would have.`
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      return `The board has too little current workload signal to make a strong team-level read, so BaseballOS keeps the story narrow.`
    default:
      return `The bullpen has ${counts.ready} clean ${one(counts.ready, 'option', 'options')}, ${counts.watch} watch-list ${one(counts.watch, 'arm', 'arms')}, and ${counts.needRest} needing rest out of ${active} active arms.`
  }
}

function whyItMattersFor(archetypeKey, counts) {
  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.heavy_lifting.key:
    case TEAM_STORY_ARCHETYPES.concentrated_workload.key:
      return 'When the same part of the bullpen keeps absorbing work, late-game flexibility can become less balanced.'
    case TEAM_STORY_ARCHETYPES.thin_margin.key:
      return 'Additional workload could quickly narrow the clean late-game options available to this bullpen.'
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
      return 'Recovery has created more paths through the late innings than this bullpen had during the heavier part of the window.'
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      return 'Depth gives the club more ways to cover the middle and late innings without forcing one narrow sequence.'
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      return 'Coverage matters when a game asks for length before the preferred late-inning sequence is available.'
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      return 'A narrow trust layer can make the whole bullpen feel tighter even when the total arm count looks usable.'
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      return 'Bridge pressure can shape the game before the highest-trust arms ever get the ball.'
    case TEAM_STORY_ARCHETYPES.usage_shift.key:
      return 'A changing usage pattern helps explain why this bullpen may not read the same way it did earlier in the window.'
    case TEAM_STORY_ARCHETYPES.pressure_building.key:
      return 'The bullpen remains usable, but the margin is becoming more concentrated around the clean options.'
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      return 'A limited read keeps the board honest by separating visible bullpen facts from unsupported conclusions.'
    default:
      return counts.ready >= counts.watch + counts.needRest
        ? 'A stable bullpen gives the manager multiple ordinary paths through the game.'
        : 'The balance is still manageable, but the next workload swing can change the board quickly.'
  }
}

function pitcherEvidenceSentence(archetypeKey, selected) {
  const names = evidenceNames(selected)
  if (names.length < 2) return null
  const nameList = formatNameList(names)
  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      return `${nameList} are part of the clean rested layer supporting today's flexibility.`
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      return `${nameList} are the Coverage or Bridge Arms most directly shaping the coverage read.`
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      return `${nameList} are the Trust Arms most directly shaping the trust-layer read.`
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      return `${nameList} are the Bridge Arms most directly shaping the handoff read.`
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      return `${nameList} are visible in the board, but their current reads are limited.`
    default:
      return `${nameList} are the arms most directly shaping the recent workload read.`
  }
}

function evidenceFor(archetypeKey, counts, shape, entries) {
  const evidence = []
  const selected = evidencePitchers(archetypeKey, entries)
  const nameSentence = pitcherEvidenceSentence(archetypeKey, selected)
  const trust = readCounts(shape, 'trustAvailability')
  const clean = readCounts(shape, 'cleanOptions')
  const pressure = readCounts(shape, 'bullpenPressure')
  const coverage = readCounts(shape, 'coverageSafety')
  const depth = readCounts(shape, 'depthSafety')

  if (nameSentence) evidence.push(nameSentence)

  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      evidence.push(`${trust.cleanTrustArms || 0} clean Trust Arms; ${(trust.watchTrustArms || 0) + (trust.restRestrictedTrustArms || 0) + (trust.unavailableTrustArms || 0)} trust reads under pressure.`)
      evidence.push(`${clean.cleanOptionCount || counts.ready} Clean Options across ${clean.activeBullpenArms || counts.total} active bullpen arms.`)
      break
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      if (number(coverage.coverageArms) > 0) {
        evidence.push(`${coverage.availableCoverageArms || 0} of ${coverage.coverageArms || 0} Coverage Arms are clean or on watch.`)
      }
      if (coverage.substituteCoverageApplied) evidence.push('Bridge Arms are helping cover emergency innings behind the coverage layer.')
      break
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      evidence.push(`${depth.availableDepthArms || 0} Depth Arms are clean options or watch arms behind the primary layer.`)
      evidence.push(`${clean.cleanOptionCount || counts.ready} Clean Options are available from ${clean.activeBullpenArms || counts.total} active bullpen arms.`)
      break
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
      evidence.push(`${counts.ready} of ${counts.total} relievers are clean options.`)
      evidence.push(`${counts.watch + counts.needRest} relievers are on watch or need rest.`)
      break
    case TEAM_STORY_ARCHETYPES.thin_margin.key:
      evidence.push(`${counts.needRest} of ${counts.total} ${one(counts.total, 'reliever', 'relievers')} ${one(counts.needRest, 'needs', 'need')} rest after recent work.`)
      evidence.push(`${readCount(pressure.watchArmCount || counts.watch, 'Watch Arm')} and ${pressure.restRestrictedCount || counts.needRest} ${one(pressure.restRestrictedCount || counts.needRest, 'Rest-Restricted arm', 'Rest-Restricted arms')} are in the pressure read.`)
      break
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      evidence.push(`${number(pressure.stressedBridgeArms)} ${one(number(pressure.stressedBridgeArms), 'Bridge Arm is', 'Bridge Arms are')} stressed in the bullpen pressure read.`)
      evidence.push(`${counts.watch + counts.needRest} relievers are on watch or need rest.`)
      break
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      evidence.push(`${counts.total} current bullpen arms are available for the team-level story read.`)
      evidence.push('The current workload picture is thinner than the board needs for a stronger briefing.')
      break
    case TEAM_STORY_ARCHETYPES.stable_bullpen.key:
      evidence.push(`${counts.ready} clean options, ${counts.watch} watch-list arms, and ${counts.needRest} needing rest.`)
      evidence.push(`${clean.cleanOptionCount || counts.ready} Clean Options from ${clean.activeBullpenArms || counts.total} active bullpen arms.`)
      break
    default:
      evidence.push(`${counts.watch} of ${counts.total} relievers are on the watch list.`)
      evidence.push(`${counts.ready} clean options remain available.`)
      break
  }

  return uniqueText(evidence).slice(0, 4)
}

function uniqueText(items) {
  const seen = new Set()
  const result = []
  for (const item of items.map(cleanLabel).filter(Boolean)) {
    const key = item.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(item)
  }
  return result
}

function watchItemsFor(archetypeKey, counts) {
  switch (archetypeKey) {
    case TEAM_STORY_ARCHETYPES.heavy_lifting.key:
    case TEAM_STORY_ARCHETYPES.concentrated_workload.key:
      return [
        'Whether workload keeps flowing through the same relievers.',
        'Whether rested options move into higher-trust innings.',
        'Whether the watch-list group gets a recovery day.',
      ]
    case TEAM_STORY_ARCHETYPES.thin_margin.key:
      return [
        'Whether the bullpen gets a lower-workload night.',
        'Whether clean options remain available behind the trusted group.',
        'Whether another busy game narrows the late-inning paths.',
      ]
    case TEAM_STORY_ARCHETYPES.recovery_window.key:
    case TEAM_STORY_ARCHETYPES.rested_flexibility.key:
      return [
        'Whether the rested layer is used broadly or held in reserve.',
        'Whether recent workload stays spread across the group.',
        'Whether the clean options remain stable after the next completed game.',
      ]
    case TEAM_STORY_ARCHETYPES.depth_advantage.key:
      return [
        'Whether depth arms cover bridge innings cleanly.',
        'Whether the trusted group avoids carrying every leverage spot.',
        'Whether the fallback layer remains usable.',
      ]
    case TEAM_STORY_ARCHETYPES.coverage_concern.key:
      return [
        'Whether coverage depth remains stable.',
        'Whether bridge arms need to cover extra length.',
        'Whether clean options survive an early starter exit.',
      ]
    case TEAM_STORY_ARCHETYPES.trust_dependency.key:
      return [
        'Whether trusted options receive recovery days.',
        'Whether work spreads beyond the same late-inning group.',
        'Whether clean bridge options protect the trust layer.',
      ]
    case TEAM_STORY_ARCHETYPES.bridge_dependency.key:
      return [
        'Whether bridge arms keep absorbing the middle-inning handoff.',
        'Whether trusted options enter with a clean setup path.',
        'Whether coverage depth protects the bridge layer.',
      ]
    case TEAM_STORY_ARCHETYPES.usage_shift.key:
      return [
        'Whether the changed workload pattern holds.',
        'Whether the same roles keep absorbing the new work.',
        'Whether clean options remain spread across the group.',
      ]
    case TEAM_STORY_ARCHETYPES.data_limited.key:
      return [
        'Which arms gain current workload reads after the next sync.',
        'Whether the board fills in enough for a stronger bullpen story.',
      ]
    default:
      return [
        'Which arms sit closest to the watch line.',
        `Whether the ${arms(counts.ready)} currently clean remain clean after the next workload window.`,
        'Whether the bullpen stays balanced across roles.',
      ]
  }
}

export function getTeamBullpenStoryView(board) {
  if (!board) return { hasStory: false }

  const teamName = board?.team?.team_name || board?.team?.team_abbreviation || 'selected club'
  const counts = boardCounts(board)
  const archetypeKey = deriveTeamStoryArchetype(board)
  const archetype = TEAM_STORY_ARCHETYPES[archetypeKey] || TEAM_STORY_ARCHETYPES.stable_bullpen
  const shape = getTeamBullpenShape(board)
  const entries = flattenPitchers(board)
  const { reads } = getBullpenReads({ ...counts, limitedRead: archetypeKey === TEAM_STORY_ARCHETYPES.data_limited.key })

  return {
    hasStory: true,
    family: archetype.family,
    archetypeKey: archetype.key,
    archetypeLabel: archetype.label,
    label: archetype.label,
    tone: STORY_TONES[archetype.tone] || STORY_TONES.balanced,
    teamName,
    headline: headlineFor(archetype.key, teamName),
    observation: observationFor(archetype.key, counts, shape),
    evidence: evidenceFor(archetype.key, counts, shape, entries),
    whyItMatters: whyItMattersFor(archetype.key, counts),
    watchItems: watchItemsFor(archetype.key, counts).slice(0, 4),
    reads,
    shapeReads: teamShapeReads(board),
    framing: STORY_FRAMING_LINE,
  }
}
