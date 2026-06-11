// Today's Bullpen Story — the bridge between a homepage hook and the full
// board. Derives one team-level story from the board payload the page already
// fetched: the engine's own health state plus the five availability counts.
// Pure retelling in baseball language — descriptive only, no predictions,
// no recommendations, no new signals.

import { getBullpenReads } from '../../../utils/bullpenConcepts'
import { getTeamBullpenShape } from '../../../utils/teamBullpenScoring'

const STORY_TONES = {
  constrained: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
  watch: { borderColor: '#eab30855', backgroundColor: '#eab30812', color: '#fde047', dot: '#eab308' },
  rested: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  balanced: { borderColor: 'rgba(148,163,184,0.32)', backgroundColor: 'rgba(148,163,184,0.09)', color: '#cbd5e1', dot: '#94a3b8' },
  data_limited: { borderColor: 'rgba(148,163,184,0.32)', backgroundColor: 'rgba(148,163,184,0.09)', color: '#cbd5e1', dot: '#94a3b8' },
}

const STORY_LABELS = {
  constrained: 'Constrained Pen',
  watch: 'Watch-List Pen',
  rested: 'Rested Pen',
  balanced: 'Balanced Pen',
  data_limited: 'Limited Read',
}

export const STORY_FRAMING_LINE =
  'Context from current workload and availability signals — not a prediction.'

const SHAPE_READ_ORDER = [
  { key: 'trustAvailability', concept: 'Trust Arm Availability' },
  { key: 'cleanOptions', concept: 'Clean Options' },
  { key: 'bullpenPressure', concept: 'Bullpen Pressure' },
  { key: 'coverageSafety', concept: 'Coverage Safety' },
  { key: 'depthSafety', concept: 'Depth Safety' },
]

const arms = (n) => `${n} arm${n === 1 ? '' : 's'}`
// Verb agreement for count-driven sentences: one('is','are'), etc.
const one = (n, singular, plural) => (n === 1 ? singular : plural)
const hasCounts = (...values) => values.every(value => typeof value === 'number' && Number.isFinite(value))
const READ_COUNT_PLURALS = {
  'Clean Option': 'Clean Options',
  'Watch Arm': 'Watch Arms',
  'Rest-Restricted': 'Rest-Restricted',
  Unavailable: 'Unavailable',
}
const readCount = (n, label) => `${n} ${n === 1 ? label : (READ_COUNT_PLURALS[label] || `${label}s`)}`

function boardCounts(board) {
  const metrics = board?.context?.metrics || {}
  const count = (key) => (typeof metrics[key] === 'number' ? metrics[key] : 0)
  return {
    total: count('total_relievers'),
    ready: count('available'),
    watch: count('monitor'),
    // "Needing rest" is the workload-driven share (Limited + Avoid).
    // Unavailable arms are roster- or data-driven and called out separately.
    needRest: count('limited') + count('avoid'),
    out: count('unavailable'),
    pctAvailable: count('pct_available'),
  }
}

// One deterministic family per board. The engine's own health state leads;
// the count shapes settle anything the state leaves open.
export function deriveStoryFamily(board) {
  const { total, ready, watch, needRest, pctAvailable } = boardCounts(board)
  const healthState = board?.context?.health?.state || 'no_data'

  if (total === 0 || healthState === 'no_data') return 'data_limited'
  if (healthState === 'constrained' || needRest >= 3 || (needRest >= 2 && needRest > watch)) {
    return 'constrained'
  }
  if (
    healthState === 'monitoring'
    || healthState === 'elevated'
    || watch >= 3
    || (watch >= 2 && watch > needRest)
  ) {
    return 'watch'
  }
  if (needRest <= 1 && (ready >= 5 || pctAvailable >= 65)) return 'rested'
  return 'balanced'
}

function workloadBullets(family, counts, confidence) {
  const { total, ready, watch, needRest, out } = counts
  const bullets = []

  bullets.push(ready > 0
    ? `${arms(ready)} of ${total} ${one(ready, 'comes', 'come')} in rested and ready.`
    : 'No arm in this pen comes in fully rested.')
  if (needRest > 0) {
    bullets.push(`${arms(needRest)} ${one(needRest, 'is', 'are')} workload-restricted after ${one(needRest, 'its', 'their')} recent use.`)
  }
  if (watch > 0) {
    bullets.push(`${arms(watch)} ${one(watch, 'carries', 'carry')} enough recent work to sit on the watch list.`)
  }
  if (out > 0) {
    bullets.push(`${arms(out)} ${one(out, 'is', 'are')} unavailable for roster or data reasons rather than tonight's workload.`)
  }
  if (confidence === 'low') {
    bullets.push('The workload read is thinner than usual today — take the counts with some caution.')
  }
  if (bullets.length < 2) {
    bullets.push(`${arms(total)} tracked in this pen today.`)
  }
  return bullets.slice(0, 2)
}

function watchBullets(family, counts) {
  const rosterBullet = 'Whether unavailable pitchers are roster moves rather than workload.'
  switch (family) {
    case 'constrained':
      return [
        'How many fully rested arms actually sit in the Available group.',
        'Whether the same small group has been carrying the heaviest recent work.',
        counts.out > 0
          ? rosterBullet
          : 'How much clean depth exists beyond the highest-trust arms.',
      ]
    case 'watch':
      return [
        'Whether the watch-list arms are the same names night after night.',
        'How the Monitor group’s fatigue reads compare with the rested arms.',
        'Whether rest is starting to show up for the busiest arms.',
      ]
    case 'rested':
      return [
        'How deep the Available group runs beyond the first few names.',
        'Which rested arms have carried the lightest work this week.',
        ...(counts.out > 0 ? [rosterBullet] : []),
      ]
    case 'data_limited':
      return [
        'Which arms have current workload reads and which are missing them.',
        'Whether the picture fills in after the next completed games sync.',
      ]
    default:
      return [
        'Which arms sit closest to the watch line.',
        'How the workload spreads across the middle of the pen.',
        'Whether tonight’s work tips this pen toward stress or rest.',
      ]
  }
}

function storyHeadline(family, teamName, counts) {
  const { total, ready, watch, needRest } = counts
  switch (family) {
    case 'constrained':
      return {
        headline: `The ${teamName} enter today with a thin late-inning margin`,
        summary: needRest > 0
          ? `${arms(needRest)} of ${total} ${one(needRest, 'comes', 'come')} in needing rest after recent work, and the clean options are thinner than they look. This bullpen has less margin than most today.`
          : `Only ${arms(ready)} of ${total} ${one(ready, 'comes', 'come')} in fully rested, and the clean options are thinner than they look. This bullpen has less margin than most today.`,
      }
    case 'watch':
      return {
        headline: `The ${teamName} look calm on the surface — the workload underneath is worth watching`,
        summary: `${arms(watch)} of ${total} ${one(watch, 'carries', 'carry')} enough recent work to land on the watch list${needRest === 0 ? ', even though nobody is workload-restricted yet' : ''}. The work is concentrated in a small group, and that concentration is the story.`,
      }
    case 'rested':
      return {
        headline: `The ${teamName} bring one of the cleanest availability pictures into today`,
        summary: `${arms(ready)} of ${total} ${one(ready, 'comes', 'come')} in rested and ready. Rest is doing a lot of the work in this bullpen's story today.`,
      }
    case 'data_limited':
      return {
        headline: `Not enough fresh data for a strong read on the ${teamName} today`,
        summary: 'The current workload picture is too thin to carry a confident story. The board below shows what the data does support.',
      }
    default:
      return {
        headline: `The ${teamName} come in steady — no extreme bullpen signal today`,
        summary: `A bit of everything: ${ready} ready, ${watch} on watch, ${needRest} needing rest. Nothing here pushes the late innings into a corner today.`,
      }
  }
}

function shapeTone(label) {
  if (!label || label === 'Limited Read') return 'neutral'
  if (/^(Strong|Stable|Deep|Healthy|Low)\b/.test(label)) return 'rest'
  if (/^(Thin|Elevated|Manageable)\b/.test(label)) return 'watch'
  if (/^(Very Thin|Limited|High)\b/.test(label)) return 'stress'
  return 'neutral'
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
      if (hasCounts(counts.availableTrustArms, counts.trustArms)) {
        return `Trust Arms: ${compactReadCounts([
          { count: counts.cleanTrustArms, label: 'Clean Option' },
          { count: counts.watchTrustArms, label: 'Watch Arm' },
          { count: counts.restRestrictedTrustArms, label: 'Rest-Restricted' },
          { count: counts.unavailableTrustArms, label: 'Unavailable' },
        ], 'no Clean Options or Watch Arms.')}`
      }
      break
    case 'cleanOptions':
      if (hasCounts(counts.cleanOptionCount, counts.activeBullpenArms)) {
        return `${counts.cleanOptionCount} Clean Options from ${counts.activeBullpenArms} active arms.`
      }
      break
    case 'bullpenPressure':
      if (hasCounts(counts.watchArmCount, counts.restRestrictedCount, counts.unavailableCount)) {
        return `Pressure: ${compactReadCounts([
          { count: counts.watchArmCount, label: 'Watch Arm' },
          { count: counts.restRestrictedCount, label: 'Rest-Restricted' },
          { count: counts.unavailableCount, label: 'Unavailable' },
        ], 'no Watch Arms, Rest-Restricted, or Unavailable arms.')}`
      }
      break
    case 'coverageSafety':
      if (hasCounts(counts.availableCoverageArms, counts.coverageArms)) {
        return `Coverage Arms: ${compactReadCounts([
          { count: counts.cleanCoverageArms, label: 'Clean Option' },
          { count: counts.watchCoverageArms, label: 'Watch Arm' },
          { count: counts.restRestrictedCoverageArms, label: 'Rest-Restricted' },
          { count: counts.unavailableCoverageArms, label: 'Unavailable' },
        ], 'no Clean Options or Watch Arms.')}`
      }
      break
    case 'depthSafety':
      if (hasCounts(counts.availableDepthArms, counts.depthArms)) {
        return `Depth Arms: ${compactReadCounts([
          { count: counts.cleanDepthArms, label: 'Clean Option' },
          { count: counts.watchDepthArms, label: 'Watch Arm' },
          { count: counts.restRestrictedDepthArms, label: 'Rest-Restricted' },
          { count: counts.unavailableDepthArms, label: 'Unavailable' },
        ], 'no Clean Options or Watch Arms.')}`
      }
      break
    default:
      break
  }
  return read?.explanation || 'Not enough current bullpen data for a confident read.'
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

export function getTeamBullpenStoryView(board) {
  if (!board) return { hasStory: false }

  const teamName = board?.team?.team_name || board?.team?.team_abbreviation || 'selected club'
  const counts = boardCounts(board)
  const confidence = board?.context?.confidence || 'high'
  const family = deriveStoryFamily(board)
  const { headline, summary } = storyHeadline(family, teamName, counts)
  // The BaseballOS Reads strip — the named vocabulary derived from the same
  // counts the story itself uses. A thin dataset reads as Limited across.
  const { reads } = getBullpenReads({ ...counts, limitedRead: family === 'data_limited' })

  return {
    hasStory: true,
    family,
    label: STORY_LABELS[family],
    tone: STORY_TONES[family],
    teamName,
    headline,
    summary,
    reads,
    shapeReads: teamShapeReads(board),
    workloadBullets: workloadBullets(family, counts, confidence),
    watchBullets: watchBullets(family, counts).slice(0, 2),
    framing: STORY_FRAMING_LINE,
  }
}
