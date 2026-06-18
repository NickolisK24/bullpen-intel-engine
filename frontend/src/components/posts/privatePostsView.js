import { getFourBeatStoryFeed } from '../stories/storiesFeedView'

export const PRIVATE_POSTS_PATH = '/posts-bpen-7f3d9c'
export const PRIVATE_POSTS_ROBOTS = 'noindex,nofollow,noarchive'
export const DEFAULT_POSTABLE_TAKE_LIMIT = 3
export const X_LEAD_CHARACTER_LIMIT = 280

const TENSION_RULE_KEYS = new Set([
  'stress_transfer',
  'sustainability_question',
  'hidden_capacity_loss',
])

const TENSION_LEAD_DIMENSIONS = new Set([
  'fatigue_load',
  'trust_lane_absence',
  'trust_lane_shallow',
  'workload_high',
  'availability_thin',
  'concentration_shape',
  'participation_narrow',
  'era_ordinary',
])

const SUPERLATIVE_LEAD_DIMENSIONS = new Set([
  'workload_light',
  'availability_deep',
  'deep_intact',
  'participation_broad',
  'era_elite',
  'trust_lane_depth',
])

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function finiteNumber(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function formatDecimal(value, digits = 1) {
  const number = finiteNumber(value)
  if (number === null) return null
  return Number.isInteger(number) ? String(number) : number.toFixed(digits)
}

function formatPercent(value) {
  const number = finiteNumber(value)
  if (number === null) return null
  return `${Math.round(number * 100)}%`
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function trimSentence(value) {
  return cleanText(value).replace(/[.?!]\s*$/, '')
}

function getBeatText(story, key) {
  const beats = Array.isArray(story?.beats) ? story.beats : []
  const beat = beats.find(item => item?.key === key)
  return cleanText(beat?.text)
}

function joinReadable(values, fallback = '') {
  const items = values.map(cleanText).filter(Boolean)
  if (items.length === 0) return fallback
  if (items.length === 1) return items[0]
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`
}

function countLabel(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`
}

function teamLabel(story) {
  return cleanText(story?.teamName)
    || cleanText(story?.team_name)
    || cleanText(story?.team_abbreviation)
    || cleanText(story?.abbr)
    || 'This team'
}

function teamAbbr(story) {
  return (cleanText(story?.abbr) || cleanText(story?.team_abbreviation) || 'TEAM').toUpperCase()
}

function definiteTeamName(teamName) {
  const clean = cleanText(teamName)
  if (!clean) return 'this club'
  return clean.toLowerCase().startsWith('the ') ? clean : `the ${clean}`
}

export function getStorySignal(story) {
  return getBeatText(story, 'signal') || cleanText(story?.title)
}

function getStoryEvidence(story) {
  return getBeatText(story, 'evidence')
}

export function extractStoryFacts(story) {
  const computed = isObject(story?.computed) ? story.computed : {}
  const workload = isObject(computed.workload) ? computed.workload : {}
  const availability = isObject(computed.availability) ? computed.availability : {}
  const seasonEra = isObject(computed.season_era) ? computed.season_era : {}
  const available = finiteNumber(availability.available)
  const total = finiteNumber(availability.total)
  const availableShare = finiteNumber(
    availability.available_share,
    total ? available / total : null,
  )
  const cleanTrustCount = finiteNumber(computed.clean_trust_count)
  const cleanOptionCount = finiteNumber(computed.clean_option_count)
  const highRiskArmCount = finiteNumber(
    computed.high_risk_arm_count ?? computed.high_risk_arms,
    0,
  )
  const rosterUnavailableArms = finiteNumber(computed.roster_unavailable_arms, 0)
  const topArmCount = finiteNumber(workload.top_arm_count)
  const topShare = finiteNumber(workload.top_share)
  const participantCount = finiteNumber(workload.participant_count)
  const perArmPitches = finiteNumber(workload.per_arm_pitches)
  const totalPitches = finiteNumber(workload.total_pitches)
  const seasonEraValue = finiteNumber(seasonEra.era)
  const seasonEraRank = finiteNumber(seasonEra.rank)
  const seasonEraRankTotal = finiteNumber(seasonEra.rank_total)
  const cleanTrustNames = Array.isArray(computed.clean_trust_names)
    ? computed.clean_trust_names.map(cleanText).filter(Boolean)
    : []
  const highRiskArmNames = Array.isArray(computed.high_risk_arm_names)
    ? computed.high_risk_arm_names.map(cleanText).filter(Boolean)
    : []

  const facts = []
  if (available !== null && total !== null) {
    facts.push({
      key: 'availability',
      label: 'Availability',
      value: `${available}/${total} arms available`,
      source: 'computed.availability',
    })
  }
  if (cleanTrustCount !== null) {
    facts.push({
      key: 'clean_trust',
      label: 'Clean Trust Arms',
      value: `${cleanTrustCount} clean Trust ${cleanTrustCount === 1 ? 'Arm' : 'Arms'}`,
      source: 'computed.clean_trust_count',
    })
  }
  if (cleanOptionCount !== null) {
    facts.push({
      key: 'clean_options',
      label: 'Clean Options',
      value: `${cleanOptionCount} clean options`,
      source: 'computed.clean_option_count',
    })
  }
  if (topShare !== null && topArmCount !== null) {
    facts.push({
      key: 'top_share',
      label: 'Top Workload Share',
      value: `top ${topArmCount} carried ${formatPercent(topShare)} of recent relief pitches`,
      source: 'computed.workload.top_share',
    })
  }
  if (participantCount !== null && perArmPitches !== null) {
    facts.push({
      key: 'participation',
      label: 'Recent Participation',
      value: `${participantCount} participating arms at ${formatDecimal(perArmPitches)} pitches per arm`,
      source: 'computed.workload.participant_count',
    })
  }
  if (totalPitches !== null) {
    facts.push({
      key: 'total_workload',
      label: 'Recent Workload',
      value: `${totalPitches} recent relief pitches`,
      source: 'computed.workload.total_pitches',
    })
  }
  if (seasonEra.available && seasonEraValue !== null) {
    const rank = seasonEraRank !== null && seasonEraRankTotal !== null
      ? `, No. ${seasonEraRank} of ${seasonEraRankTotal}`
      : ''
    facts.push({
      key: 'season_era',
      label: 'Current-Pen ERA',
      value: `${seasonEraValue.toFixed(2)} current-pen ERA${rank}`,
      source: 'computed.season_era',
    })
  }
  if (highRiskArmCount > 0) {
    const names = highRiskArmNames.length > 0 ? ` (${joinReadable(highRiskArmNames)})` : ''
    facts.push({
      key: 'high_risk',
      label: 'Watch List',
      value: `${countLabel(highRiskArmCount, 'HIGH/CRITICAL arm')}${names}`,
      source: 'computed.high_risk_arm_count',
    })
  }
  if (rosterUnavailableArms > 0) {
    facts.push({
      key: 'roster_unavailable',
      label: 'Roster Unavailable',
      value: `${countLabel(rosterUnavailableArms, 'arm')} off the active lane`,
      source: 'computed.roster_unavailable_arms',
    })
  }
  if (cleanTrustNames.length > 0) {
    facts.push({
      key: 'clean_trust_names',
      label: 'Clean Trust Lane',
      value: joinReadable(cleanTrustNames),
      source: 'computed.clean_trust_names',
    })
  }

  return {
    items: facts,
    availability: { available, total, availableShare },
    workload: {
      topArmCount,
      topShare,
      participantCount,
      perArmPitches,
      totalPitches,
      concentrationLevel: cleanText(workload.concentration_level),
      concentrationDescriptor: cleanText(workload.concentration_descriptor),
    },
    seasonEra: {
      available: Boolean(seasonEra.available),
      era: seasonEraValue,
      rank: seasonEraRank,
      rankTotal: seasonEraRankTotal,
      strongResults: Boolean(seasonEra.strong_results),
      solidResults: Boolean(seasonEra.solid_results),
    },
    cleanTrustCount,
    cleanOptionCount,
    highRiskArmCount,
    highRiskArmNames,
    rosterUnavailableArms,
  }
}

function factValue(facts, key) {
  return facts.items.find(item => item.key === key)?.value || ''
}

function classifyPostability(story, facts) {
  const computed = isObject(story?.computed) ? story.computed : {}
  const conditions = isObject(computed.conditions) ? computed.conditions : {}
  const ruleKey = cleanText(story?.rule_key)
  const leadDimension = cleanText(story?.lead_dimension)
  const leadScore = finiteNumber(story?.lead_dimension_detail?.score, 0)
  const strength = finiteNumber(story?.strength, 0)
  const availableShare = finiteNumber(facts.availability.availableShare, 0)
  const cleanTrustCount = finiteNumber(facts.cleanTrustCount, 0)
  const cleanOptionCount = finiteNumber(facts.cleanOptionCount, 0)
  const highRiskArmCount = finiteNumber(facts.highRiskArmCount, 0)
  const rosterUnavailableArms = finiteNumber(facts.rosterUnavailableArms, 0)
  const topShare = finiteNumber(facts.workload.topShare, 0)
  const perArmPitches = finiteNumber(facts.workload.perArmPitches, 0)
  const seasonRank = finiteNumber(facts.seasonEra.rank)
  const storyText = [
    getStorySignal(story),
    getStoryEvidence(story),
    cleanText(story?.body),
  ].join(' ').toLowerCase()
  const saysBut = /\bbut\b/.test(storyText)

  const tension = []
  if (
    availableShare >= 0.45
    && (conditions.workload_concentrated || topShare >= 0.62 || leadDimension === 'concentration_shape')
  ) {
    tension.push('available board with concentrated recent usage')
  }
  if (
    (facts.seasonEra.strongResults || (seasonRank !== null && seasonRank <= 10))
    && (conditions.heavy_recent_workload || perArmPitches >= 30 || highRiskArmCount > 0)
  ) {
    tension.push('good current results paired with expensive recent usage')
  }
  if (
    (facts.seasonEra.solidResults || facts.seasonEra.strongResults)
    && (conditions.depleted_depth || availableShare <= 0.4 || rosterUnavailableArms > 0)
  ) {
    tension.push('solid results with thinner usable depth')
  }
  if (cleanOptionCount > 1 && cleanTrustCount <= 1) {
    tension.push('clean options outside a thin Trust Arm lane')
  }
  if (TENSION_RULE_KEYS.has(ruleKey) && (saysBut || TENSION_LEAD_DIMENSIONS.has(leadDimension))) {
    tension.push(`${story.rule_label || ruleKey} story carries an explicit contrast`)
  }

  const superlatives = []
  if (seasonRank !== null && seasonRank <= 3) {
    superlatives.push(`top-${seasonRank} current-pen ERA rank`)
  }
  if (topShare >= 0.75) {
    superlatives.push(`${formatPercent(topShare)} recent workload share at the top of the pen`)
  }
  if (highRiskArmCount >= 3) {
    superlatives.push(`${highRiskArmCount} HIGH/CRITICAL fatigue arms`)
  }
  if (availableShare >= 0.75 && cleanOptionCount >= 5) {
    superlatives.push('deep available board with at least five clean options')
  }
  if (SUPERLATIVE_LEAD_DIMENSIONS.has(leadDimension)) {
    superlatives.push(`distinct ${leadDimension.replaceAll('_', ' ')} lead`)
  }

  const distinctiveness = Math.min(30, Math.max(0, leadScore / 35))
  const strengthScore = Math.min(18, Math.max(0, strength / 8))
  const hasTension = tension.length > 0
  const hasSuperlative = superlatives.length > 0
  const score = Math.round(
    20
    + (hasTension ? 42 : 0)
    + (hasSuperlative ? 30 : 0)
    + Math.min(24, tension.length * 8)
    + Math.min(18, superlatives.length * 6)
    + distinctiveness
    + strengthScore
    - (!hasTension && !hasSuperlative ? 18 : 0),
  )

  return {
    score,
    hasTension,
    hasSuperlative,
    tension,
    superlatives,
    distinctiveness,
    leadDimension,
    leadScore,
    storyStrength: strength,
    rationale: [
      ...tension.map(value => `Tension: ${value}.`),
      ...superlatives.map(value => `Superlative: ${value}.`),
      leadDimension ? `Lead dimension: ${leadDimension}.` : '',
    ].filter(Boolean),
  }
}

function evidenceLine(take) {
  const preferred = [
    factValue(take.facts, 'availability'),
    factValue(take.facts, 'top_share'),
    factValue(take.facts, 'clean_trust'),
    factValue(take.facts, 'season_era'),
    factValue(take.facts, 'high_risk'),
    factValue(take.facts, 'clean_options'),
  ].filter(Boolean)
  return joinReadable(preferred.slice(0, 5), getStoryEvidence(take.story))
}

function shortHookFact(take) {
  const facts = [
    factValue(take.facts, 'availability'),
    factValue(take.facts, 'top_share'),
    factValue(take.facts, 'clean_trust'),
    factValue(take.facts, 'season_era'),
  ].filter(Boolean)
  return facts[0] || trimSentence(take.signal)
}

function angleLine(take) {
  if (take.postability.hasTension) {
    return take.postability.tension[0]
  }
  if (take.postability.hasSuperlative) {
    return take.postability.superlatives[0]
  }
  return 'a mild but specific bullpen read'
}

function underLimit(candidates, limit) {
  for (const candidate of candidates.map(cleanText).filter(Boolean)) {
    if (candidate.length <= limit) return candidate
  }
  const first = cleanText(candidates.find(Boolean))
  if (first.length <= limit) return first
  return `${first.slice(0, Math.max(0, limit - 3)).trimEnd()}...`
}

export function buildPlatformDrafts(take) {
  const teamName = take.teamName
  const teamPhrase = definiteTeamName(teamName)
  const abbr = take.abbr
  const signal = trimSentence(take.signal)
  const evidence = evidenceLine(take)
  const angle = angleLine(take)
  const firstFact = shortHookFact(take)
  const storyEvidence = trimSentence(getStoryEvidence(take.story))
  const xLead = underLimit([
    `${abbr} bullpen tonight: ${firstFact}. The argument is ${angle}.`,
    `${abbr} bullpen tonight: ${signal}. ${firstFact}.`,
    `${abbr} bullpen tonight: ${firstFact}.`,
  ], X_LEAD_CHARACTER_LIMIT)

  return {
    reddit: {
      platform: 'Reddit',
      league: {
        label: 'Reddit - league-wide',
        audience: 'r/baseball or r/Sabermetrics',
        text: [
          `The ${teamName} bullpen is one of the more interesting watches tonight.`,
          take.postability.hasTension
            ? `${signal}. The tension is not "bad bullpen"; it is ${angle}.`
            : `${signal}. The interesting part is ${angle}.`,
          `The numbers behind it: ${evidence}.`,
          'The question I would put to the room: if the starter exits early, does that shape change how you would manage the late innings?',
        ].join('\n\n'),
      },
      team: {
        label: 'Reddit - team subreddit',
        audience: `${abbr} team subreddit`,
        text: [
          `${abbr} fans, tonight's bullpen read feels more specific than just "who is available."`,
          `${signal}.`,
          `The board underneath it: ${evidence}.`,
          take.postability.hasTension
            ? `That is the argument for the game thread: the pen has a usable path, but ${angle}.`
            : `That is the game-thread angle: ${angle}, without turning it into a prediction.`,
          'Would you try to steal outs earlier, or hold the cleaner lane for leverage?',
        ].join('\n\n'),
      },
    },
    linkedin: {
      platform: 'LinkedIn',
      label: 'LinkedIn',
      audience: 'Baseball ops, builders, and professional network',
      text: [
        `${signal}.`,
        `That was the most postable bullpen story BaseballOS surfaced for ${teamPhrase} today because it turns raw availability into a baseball-ops question: ${angle}.`,
        `The underlying read is grounded in the same story payload: ${evidence}.`,
        'The useful product lesson for me is that the sharpest framing is usually not "I built a tracker." It is the specific baseball tension the data makes visible.',
      ].join('\n\n'),
    },
    x: {
      platform: 'X',
      label: 'X lead tweet',
      audience: 'Baseball fans scrolling X',
      lead: xLead,
      characterCount: xLead.length,
      support: underLimit([
        `Thread detail: ${evidence}. ${storyEvidence || signal}.`,
        `Thread detail: ${evidence}.`,
      ], X_LEAD_CHARACTER_LIMIT),
      text: `${xLead}\n\nThread detail: ${underLimit([
        `${evidence}. ${storyEvidence || signal}.`,
        evidence,
      ], X_LEAD_CHARACTER_LIMIT - 15)}`,
    },
  }
}

export function flattenTakeDrafts(take) {
  if (!take?.drafts) return []
  return [
    take.drafts.reddit?.league,
    take.drafts.reddit?.team,
    take.drafts.linkedin,
    take.drafts.x,
  ].filter(Boolean)
}

export function buildPostableTake(story) {
  if (!story || story.teamId == null) return null
  const signal = getStorySignal(story)
  if (!signal) return null
  const facts = extractStoryFacts(story)
  const postability = classifyPostability(story, facts)
  const take = {
    story,
    storyId: story.story_id,
    ruleKey: story.rule_key,
    ruleLabel: story.rule_label || story.kicker,
    teamId: story.teamId,
    teamName: teamLabel(story),
    abbr: teamAbbr(story),
    signal,
    evidence: getStoryEvidence(story),
    facts,
    postability,
    suggestedAudience: postability.hasTension
      ? `${teamAbbr(story)} team subreddit first, then r/baseball if the angle holds up outside the fan base`
      : `r/baseball or ${teamAbbr(story)} team subreddit as a lighter discussion prompt`,
  }
  return {
    ...take,
    drafts: buildPlatformDrafts(take),
  }
}

export function getPrivatePostTakes(dashboard, options = {}) {
  const limit = Math.max(1, finiteNumber(options.limit, DEFAULT_POSTABLE_TAKE_LIMIT))
  return getFourBeatStoryFeed(dashboard).items
    .map(buildPostableTake)
    .filter(Boolean)
    .sort((a, b) => (
      b.postability.score - a.postability.score
      || b.postability.storyStrength - a.postability.storyStrength
      || a.teamName.localeCompare(b.teamName)
      || a.abbr.localeCompare(b.abbr)
    ))
    .slice(0, limit)
}
