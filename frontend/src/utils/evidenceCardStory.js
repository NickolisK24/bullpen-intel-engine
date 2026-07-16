import { normalizeCardText, wrapCardText } from './evidenceCardText'

export const TEAM_CARD_VERSION = 'team_story_v2'
export const COMPARISON_CARD_VERSION = 'comparison_story_v2'

export const TEAM_STORY_ANGLES = Object.freeze([
  'availability_constraint',
  'availability_watch',
  'availability_depth',
  'repeated_usage',
  'workload_concentration',
  'recent_work_volume',
  'starter_support',
  'roster_context',
])

export const COMPARISON_STORY_ANGLES = Object.freeze([
  'comparison_availability',
  'comparison_on_watch',
  'comparison_limited',
  'comparison_unavailable',
  'comparison_no_separation',
])

export const TEAM_STORY_EVIDENCE_SECTIONS = Object.freeze({
  availability_constraint: 'pitcher-lanes',
  availability_watch: 'pitcher-lanes',
  availability_depth: 'pitcher-lanes',
  repeated_usage: 'team-relief-work',
  workload_concentration: 'team-relief-work',
  recent_work_volume: 'team-relief-work',
  starter_support: 'team-relief-work',
  roster_context: 'pitcher-lanes',
})

export const TEAM_HEADLINE_LAYOUT = Object.freeze({ maxWidth: 548, maxLines: 4, fontSize: 34 })
export const TEAM_SUPPORTING_LAYOUT = Object.freeze({ maxWidth: 548, maxLines: 2, fontSize: 20 })
export const COMPARISON_HEADLINE_LAYOUT = Object.freeze({ maxWidth: 1088, maxLines: 2, fontSize: 30 })
export const COMPARISON_SUPPORTING_LAYOUT = Object.freeze({ maxWidth: 328, maxLines: 5, fontSize: 20 })

const CONSTRAINED_TEAM_STATES = /^(?:thin|stretched|stressed)$/i
const POSITIVE_TEAM_STATES = /^(?:stable|usable)$/i
const WATCH_TEAM_STATES = /^(?:worth watching|monitor)$/i
const ROSTER_STORY_STATES = /^(?:thin|stretched|stressed|recovering)$/i
const COUNT_LED_RELIEVER_RECEIPT = /^(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve) relievers?\b/i
const AVAILABILITY_COUNTS = /^(\d+) of (\d+) (?:active )?relievers? are classified Available\.$/i
const ON_WATCH_COUNTS = /^(\d+) of (\d+) relievers? are in (?:the )?On Watch (?:group|lane)\.$/i
const SHORT_START_COUNTS = /^(\d+) of (\d+) analyzed starts ended before five innings\.$/i
const ROSTER_INACTIVE_COUNTS = /^(?:Roster context: )?(\d+) bullpen arms? (?:is|are) inactive or unavailable\.$/i
const ROSTER_INJURED_COUNTS = /^(?:Roster context: )?(\d+) bullpen arms? (?:is|are) on the injured list\.$/i
const ROSTER_UNKNOWN_COUNTS = /^(?:Roster context: )?(\d+) bullpen arms? (?:has|have) unconfirmed roster status\.$/i
const CONCENTRATION_SUMMARY = /\bsmaller group\b/i
const TIE_STATEMENT = /^both bullpens currently (?:have the same number|show similar)/i

function firstCount(text, regex) {
  const match = text ? normalizeCardText(text).match(regex) : null
  return match ? Number(match[1]) : null
}

// Deterministic roster-context headline, choosing wording by the strongest
// verified public roster subtype. Never implies the arm would otherwise pitch.
function rosterSentence(subtype, count, teamName) {
  const arms = count === 1 ? 'arm' : 'arms'
  if (subtype === 'roster_injured_list') {
    return `${count} ${teamName} bullpen ${arms} ${count === 1 ? 'is' : 'are'} on the injured list.`
  }
  if (subtype === 'roster_unknown') {
    return `${count} ${teamName} bullpen ${arms} ${count === 1 ? 'has' : 'have'} unconfirmed roster status.`
  }
  return `${count} ${teamName} bullpen ${arms} ${count === 1 ? 'is' : 'are'} inactive or unavailable.`
}

// The strongest verified roster subtype, in the fixed order inactive →
// injured list → unknown. Returns null when no roster subtype has a count.
function strongestRosterCandidate({ rosterInactive, rosterInjured, rosterUnknown }) {
  const inactiveCount = rosterInactive ? firstCount(rosterInactive.text, ROSTER_INACTIVE_COUNTS) : null
  if (inactiveCount > 0) return { subtype: 'roster_inactive', count: inactiveCount, text: rosterInactive.text }
  const injuredCount = rosterInjured ? firstCount(rosterInjured.text, ROSTER_INJURED_COUNTS) : null
  if (injuredCount > 0) return { subtype: 'roster_injured_list', count: injuredCount, text: rosterInjured.text }
  const unknownCount = rosterUnknown ? firstCount(rosterUnknown.text, ROSTER_UNKNOWN_COUNTS) : null
  if (unknownCount > 0) return { subtype: 'roster_unknown', count: unknownCount, text: rosterUnknown.text }
  return null
}

const COMPARISON_ROW_ANGLES = new Map([
  ['Available', 'comparison_availability'],
  ['On Watch', 'comparison_on_watch'],
  ['Limited', 'comparison_limited'],
  ['Unavailable', 'comparison_unavailable'],
])

const COMPARISON_DIMENSION_PRIORITY = new Map([
  ['Available', 0],
  ['Limited', 1],
  ['Unavailable', 2],
  ['On Watch', 3],
])

function headlineFromSentence(sentence) {
  return normalizeCardText(sentence).replace(/\.$/, '').toUpperCase()
}

// Inserts the team name in front of the first "relievers" so a public receipt
// like "Two relievers have appeared on consecutive days." names the team while
// keeping the receipt's meaning intact.
function teamSentenceFromReceipt(receipt, teamName) {
  const text = normalizeCardText(receipt)
  if (!COUNT_LED_RELIEVER_RECEIPT.test(text)) return null
  return text.replace(/\brelievers?\b/i, match => `${teamName} ${match.toLowerCase()}`)
}

function comparisonCountPhrase(label, count) {
  const singular = count === 1
  if (label === 'On Watch') return `${count} ${singular ? 'arm' : 'arms'} On Watch`
  return `${count} ${label.toLowerCase()} ${singular ? 'arm' : 'arms'}`
}

export function comparisonDimensionSentence(row, labelA, labelB) {
  const aLeads = row.valueA > row.valueB
  const leaderLabel = aLeads ? labelA : labelB
  const otherLabel = aLeads ? labelB : labelA
  const leaderValue = aLeads ? row.valueA : row.valueB
  const otherValue = aLeads ? row.valueB : row.valueA
  return `The ${leaderLabel} have ${comparisonCountPhrase(row.label, leaderValue)}; the ${otherLabel} have ${otherValue}.`
}

function comparisonLeadSentence(row, labelA, labelB) {
  const aLeads = row.valueA > row.valueB
  const leaderLabel = aLeads ? labelA : labelB
  const otherLabel = aLeads ? labelB : labelA
  const difference = row.difference
  const singular = difference === 1
  const phrase = row.label === 'On Watch'
    ? `${difference} more ${singular ? 'arm' : 'arms'} On Watch`
    : `${difference} more ${row.label.toLowerCase()} ${singular ? 'arm' : 'arms'}`
  return `The ${leaderLabel} have ${phrase} than the ${otherLabel}.`
}

export function rankComparisonRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .filter(row => COMPARISON_DIMENSION_PRIORITY.has(row?.label))
    .map(row => ({
      ...row,
      valueA: Number(row.valueA),
      valueB: Number(row.valueB),
      difference: Math.abs(Number(row.valueA) - Number(row.valueB)),
    }))
    .filter(row => Number.isFinite(row.valueA) && Number.isFinite(row.valueB))
    .sort((left, right) => (
      Number(left.difference === 0) - Number(right.difference === 0)
      || right.difference - left.difference
      || COMPARISON_DIMENSION_PRIORITY.get(left.label) - COMPARISON_DIMENSION_PRIORITY.get(right.label)
    ))
}

function teamStoryAttempt(storyAngle, sentence, supportReceipt, supportingCandidates) {
  if (!sentence || !supportReceipt) return null
  return {
    storyAngle,
    sentence,
    headline: headlineFromSentence(sentence),
    supportReceipt,
    supportingCandidates: supportingCandidates.filter(Boolean),
  }
}

// Deterministic team-card story selection. Works only from the public read
// model and the already-classified receipt candidates; the strongest supported
// observation wins in a fixed priority order. Returns null when no specific,
// receipt-supported headline exists.
export function selectTeamStory({ readModel, candidates } = {}) {
  const teamName = normalizeCardText(readModel?.teamName || readModel?.teamLabel)
  const stateLabel = normalizeCardText(readModel?.stateLabel)
  const list = Array.isArray(candidates) ? candidates : []
  if (!teamName || !stateLabel) return null

  const bySubtype = subtype => list.find(candidate => candidate.subtype === subtype)
  const byFamily = family => list.find(candidate => candidate.family === family)

  const available = bySubtype('availability_available')
  const availableCount = available ? firstCount(available.text, AVAILABILITY_COUNTS) : null
  const availableTotal = available ? Number((available.text.match(AVAILABILITY_COUNTS) || [])[2]) : null
  const onWatch = bySubtype('availability_on_watch')
  const onWatchMatch = onWatch ? onWatch.text.match(ON_WATCH_COUNTS) : null
  const onWatchCount = onWatchMatch ? Number(onWatchMatch[1]) : null
  const onWatchTotal = onWatchMatch ? Number(onWatchMatch[2]) : null

  const repeated = byFamily('repeated_appearances')
  const workCandidate = list.find(candidate => (
    ['workload_concentration', 'recent_work_volume'].includes(candidate.family)
    && COUNT_LED_RELIEVER_RECEIPT.test(candidate.text)
  ))
  const workloadSupport = list.find(candidate => (
    ['workload_concentration', 'recent_work_volume', 'repeated_appearances'].includes(candidate.family)
  ))

  const starterSummary = bySubtype('starter_summary')
  const shortStarts = bySubtype('starter_short_starts')
  const shortStartMatch = shortStarts ? shortStarts.text.match(SHORT_START_COUNTS) : null

  const roster = strongestRosterCandidate({
    rosterInactive: bySubtype('roster_inactive'),
    rosterInjured: bySubtype('roster_injured_list'),
    rosterUnknown: bySubtype('roster_unknown'),
  })

  const concentration = normalizeCardText(readModel?.workloadConcentration?.summary)
  const hasConcentration = CONCENTRATION_SUMMARY.test(concentration)
  const concernBody = normalizeCardText(readModel?.primaryConcern?.body)

  const attempts = [
    availableCount != null && CONSTRAINED_TEAM_STATES.test(stateLabel) && availableCount < availableTotal
      ? teamStoryAttempt(
        'availability_constraint',
        `Only ${availableCount} of ${availableTotal} ${teamName} relievers are available.`,
        available.text,
        [concentration],
      )
      : null,
    repeated
      ? teamStoryAttempt(
        'repeated_usage',
        teamSentenceFromReceipt(repeated.text, teamName),
        repeated.text,
        [hasConcentration ? concentration : null],
      )
      : null,
    onWatchMatch && WATCH_TEAM_STATES.test(stateLabel) && onWatchCount > 0 && onWatchTotal > 0
      ? teamStoryAttempt(
        'availability_watch',
        `${onWatchCount} of ${onWatchTotal} ${teamName} relievers are On Watch.`,
        onWatch.text,
        [concentration],
      )
      : null,
    hasConcentration && workloadSupport
      ? teamStoryAttempt(
        'workload_concentration',
        `Recent ${teamName} relief work has run through a smaller group of arms.`,
        workloadSupport.text,
        [repeated && repeated.text !== workloadSupport.text ? repeated.text : null, concernBody],
      )
      : null,
    workCandidate
      ? teamStoryAttempt(
        'recent_work_volume',
        teamSentenceFromReceipt(workCandidate.text, teamName),
        workCandidate.text,
        [hasConcentration ? concentration : null, concernBody],
      )
      : null,
    shortStartMatch && Number(shortStartMatch[1]) > 0
      ? teamStoryAttempt(
        'starter_support',
        `${Number(shortStartMatch[1])} of ${Number(shortStartMatch[2])} recent ${teamName} starts ended before five innings.`,
        shortStarts.text,
        [starterSummary ? starterSummary.text : null, hasConcentration ? concentration : null, concernBody],
      )
      : null,
    availableCount != null && POSITIVE_TEAM_STATES.test(stateLabel) && availableCount > 0
      ? teamStoryAttempt(
        'availability_depth',
        `${availableCount} of ${availableTotal} ${teamName} relievers are available.`,
        available.text,
        [concentration],
      )
      : null,
    roster && ROSTER_STORY_STATES.test(stateLabel)
      ? teamStoryAttempt(
        'roster_context',
        rosterSentence(roster.subtype, roster.count, teamName),
        roster.text,
        [],
      )
      : null,
  ]

  return attempts.find(attempt => (
    attempt
    && TEAM_STORY_ANGLES.includes(attempt.storyAngle)
    && Boolean(wrapCardText(attempt.headline, TEAM_HEADLINE_LAYOUT))
  )) || null
}

// Deterministic comparison-card story selection. Leads with the largest
// meaningful visible difference; identical distributions only produce a card
// when another specific, safe observation already exists.
export function selectComparisonStory({ rows, labelA, labelB, statements = [] } = {}) {
  const ranked = Array.isArray(rows) ? rows : []
  const fits = headline => Boolean(wrapCardText(headline, COMPARISON_HEADLINE_LAYOUT))
  const differences = ranked.filter(row => row.difference > 0)

  for (let index = 0; index < differences.length; index += 1) {
    const row = differences[index]
    const sentence = comparisonLeadSentence(row, labelA, labelB)
    const headline = headlineFromSentence(sentence)
    if (!fits(headline)) continue
    const supportingCandidates = differences
      .filter(other => other !== row)
      .map(other => comparisonDimensionSentence(other, labelA, labelB))
    return {
      storyAngle: COMPARISON_ROW_ANGLES.get(row.label),
      sentence,
      headline,
      supportingCandidates,
    }
  }

  if (ranked.length > 0 && differences.length === 0) {
    const specific = statements.find(text => /\d/.test(text) && !TIE_STATEMENT.test(text))
    if (!specific) return null
    const sentence = `The ${labelA} and ${labelB} bullpens match across every availability group.`
    const headline = headlineFromSentence(sentence)
    if (!fits(headline)) return null
    return {
      storyAngle: 'comparison_no_separation',
      sentence,
      headline,
      supportingCandidates: [specific],
    }
  }

  return null
}
