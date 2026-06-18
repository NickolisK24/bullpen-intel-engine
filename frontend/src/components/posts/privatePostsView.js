import { getFourBeatStoryFeed } from '../stories/storiesFeedView'

export const PRIVATE_POSTS_PATH = '/posts-bpen-7f3d9c'
export const PRIVATE_POSTS_ROBOTS = 'noindex,nofollow,noarchive'
export const DEFAULT_POSTABLE_TAKE_LIMIT = 3
export const X_LEAD_CHARACTER_LIMIT = 280
export const DRAFT_SOURCE_GENERATED = 'generated'
export const DRAFT_SOURCE_TEMPLATE_FALLBACK = 'template_fallback'

export const DRAFT_SOURCE_LABELS = {
  [DRAFT_SOURCE_GENERATED]: 'Generated draft',
  [DRAFT_SOURCE_TEMPLATE_FALLBACK]: 'Template fallback',
}

export const POST_DRAFT_PLATFORMS = [
  'reddit_league',
  'reddit_team',
  'linkedin',
  'x',
]

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

function compactObject(value) {
  if (!isObject(value)) return {}
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => (
      entry !== null
      && entry !== undefined
      && entry !== ''
      && !(Array.isArray(entry) && entry.length === 0)
    )),
  )
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

function addNumberToken(tokens, value) {
  const clean = cleanText(value).toLowerCase().replace(/(st|nd|rd|th)$/i, '')
  if (!clean) return
  tokens.add(clean)
  if (clean.endsWith('%')) tokens.add(clean.slice(0, -1))
  if (clean.includes('/')) {
    clean.split('/').forEach(part => {
      if (part) tokens.add(part)
    })
  }
}

export function extractNumberTokens(value) {
  const text = cleanText(value)
  if (!text) return []
  const matches = text.match(/\b\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?%?(?:st|nd|rd|th)?\b/gi) || []
  const tokens = new Set()
  matches.forEach(match => addNumberToken(tokens, match))
  return Array.from(tokens)
}

function collectVerifiedNumberTokens(verifiedFacts) {
  const tokens = new Set()
  const addValue = value => {
    extractNumberTokens(value).forEach(token => tokens.add(token))
    if (Number.isFinite(value)) addNumberToken(tokens, String(value))
  }
  const visit = value => {
    if (Array.isArray(value)) {
      value.forEach(visit)
      return
    }
    if (isObject(value)) {
      Object.values(value).forEach(visit)
      return
    }
    addValue(value)
  }
  visit(verifiedFacts)
  return Array.from(tokens).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
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
    cleanTrustNames,
    cleanOptionCount,
    highRiskArmCount,
    highRiskArmNames,
    rosterUnavailableArms,
  }
}

export function buildVerifiedFactSet(story, storyFacts = extractStoryFacts(story)) {
  const factItems = storyFacts.items.map(item => ({
    key: item.key,
    label: item.label,
    value: item.value,
    source: item.source,
  }))
  const getValue = key => factItems.find(item => item.key === key)?.value || ''
  const verified = {
    team: compactObject({
      id: story?.teamId ?? story?.team_id ?? null,
      abbr: teamAbbr(story),
      name: teamLabel(story),
    }),
    story: compactObject({
      id: story?.story_id || null,
      rule_key: cleanText(story?.rule_key),
      rule_label: cleanText(story?.rule_label || story?.kicker),
      lead_dimension: cleanText(story?.lead_dimension),
      lead_score: finiteNumber(story?.lead_dimension_detail?.score),
    }),
    signal: getStorySignal(story),
    evidence: getStoryEvidence(story),
    availability: compactObject({
      available: storyFacts.availability.available,
      total: storyFacts.availability.total,
      available_share: storyFacts.availability.availableShare,
      text: getValue('availability'),
    }),
    clean_trust: compactObject({
      count: storyFacts.cleanTrustCount,
      names: Array.isArray(storyFacts.cleanTrustNames) ? storyFacts.cleanTrustNames : [],
      text: getValue('clean_trust'),
      names_text: getValue('clean_trust_names'),
    }),
    clean_options: compactObject({
      count: storyFacts.cleanOptionCount,
      text: getValue('clean_options'),
    }),
    workload: compactObject({
      top_arm_count: storyFacts.workload.topArmCount,
      top_share: storyFacts.workload.topShare,
      top_share_text: storyFacts.workload.topShare !== null ? formatPercent(storyFacts.workload.topShare) : null,
      participant_count: storyFacts.workload.participantCount,
      per_arm_pitches: storyFacts.workload.perArmPitches,
      total_pitches: storyFacts.workload.totalPitches,
      concentration_level: storyFacts.workload.concentrationLevel,
      concentration_descriptor: storyFacts.workload.concentrationDescriptor,
      top_share_story_text: getValue('top_share'),
      participation_story_text: getValue('participation'),
      total_workload_story_text: getValue('total_workload'),
    }),
    season_era: compactObject({
      available: storyFacts.seasonEra.available,
      era: storyFacts.seasonEra.era,
      rank: storyFacts.seasonEra.rank,
      rank_total: storyFacts.seasonEra.rankTotal,
      strong_results: storyFacts.seasonEra.strongResults,
      solid_results: storyFacts.seasonEra.solidResults,
      text: getValue('season_era'),
    }),
    high_risk: compactObject({
      count: storyFacts.highRiskArmCount,
      names: storyFacts.highRiskArmNames,
      text: getValue('high_risk'),
    }),
    roster_unavailable: compactObject({
      count: storyFacts.rosterUnavailableArms,
      text: getValue('roster_unavailable'),
    }),
    fact_items: factItems,
  }

  return {
    ...verified,
    numeric_tokens: collectVerifiedNumberTokens(verified),
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

function verifiedValue(take, path, fallback = '') {
  const facts = take.verifiedFacts || {}
  return path.split('.').reduce((value, key) => value?.[key], facts) ?? fallback
}

function availableFactLines(take) {
  const facts = take.verifiedFacts || buildVerifiedFactSet(take.story, take.facts)
  return [
    facts.availability?.text,
    facts.clean_trust?.text,
    facts.clean_options?.text,
    facts.season_era?.text,
    facts.high_risk?.text,
    facts.workload?.top_share_story_text,
    facts.workload?.participation_story_text,
    facts.roster_unavailable?.text,
  ].map(cleanText).filter(Boolean)
}

function compactFactLine(take, limit = 5) {
  return joinReadable(availableFactLines(take).slice(0, limit), trimSentence(take.signal))
}

function articleForStat(value) {
  const text = cleanText(value)
  if (!text) return ''
  return /^\d/.test(text) ? `a ${text}` : text
}

function generatedOpening(take) {
  const teamName = take.teamName
  const era = cleanText(verifiedValue(take, 'season_era.text'))
  const availability = cleanText(verifiedValue(take, 'availability.text'))
  if (era && availability) {
    return `The ${teamName} bullpen owns ${articleForStat(era)} with ${availability} tonight`
  }
  if (availability) {
    return `The ${teamName} bullpen has ${availability} tonight`
  }
  return trimSentence(take.signal)
}

function generatedAngleSentence(take) {
  const angle = angleLine(take)
  if (take.postability.hasTension) {
    return `The useful angle is the contrast: ${angle}.`
  }
  if (take.postability.hasSuperlative) {
    return `The useful angle is the clean strength: ${angle}.`
  }
  return `The useful angle is a specific bullpen read without forcing extra drama.`
}

function xFactSentence(take) {
  const abbr = take.abbr
  const era = cleanText(verifiedValue(take, 'season_era.text'))
  const availability = cleanText(verifiedValue(take, 'availability.text'))
  const cleanTrust = cleanText(verifiedValue(take, 'clean_trust.text'))
  const highRisk = cleanText(verifiedValue(take, 'high_risk.text'))
  const cleanOptions = cleanText(verifiedValue(take, 'clean_options.text'))
  const tension = take.postability.hasTension ? angleLine(take) : ''
  const strength = take.postability.hasSuperlative ? angleLine(take) : ''
  const eraPhrase = articleForStat(era)

  return underLimit([
    eraPhrase
      ? `${abbr} has ${eraPhrase}${availability ? `, with ${availability}` : ''} tonight. ${cleanTrust ? `${cleanTrust}. ` : ''}${highRisk ? `${highRisk}. ` : ''}${tension ? `The catch: ${tension}.` : strength ? `The shape: ${strength}.` : trimSentence(take.signal)}`
      : `${abbr} bullpen tonight: ${availability || compactFactLine(take, 3)}. ${cleanTrust ? `${cleanTrust}. ` : ''}${highRisk ? `${highRisk}. ` : ''}${tension || strength || trimSentence(take.signal)}.`,
    `${abbr} bullpen tonight: ${compactFactLine(take, 4)}. ${tension || strength || trimSentence(take.signal)}.`,
    `${abbr} bullpen tonight: ${compactFactLine(take, 3)}.`,
  ], X_LEAD_CHARACTER_LIMIT)
}

function cleanLaneQuestion(cleanTrust, cleanOptions) {
  if (cleanTrust.startsWith('0 ')) {
    return cleanOptions
      ? `If the starter exits early, the thread question is whether ${cleanOptions} can cover leverage without a clean Trust Arm lane.`
      : `If the starter exits early, the thread question is how much room the current board really leaves without a clean Trust Arm lane.`
  }
  if (cleanTrust || cleanOptions) {
    return `If the starter exits early, the thread question is where the clean lane comes from: ${joinReadable([cleanTrust, cleanOptions].filter(Boolean))}.`
  }
  return `If the starter exits early, the thread question is how much room the current board really leaves.`
}

export function buildGeneratedPlatformDrafts(take) {
  const teamName = take.teamName
  const teamPhrase = definiteTeamName(teamName)
  const abbr = take.abbr
  const signal = trimSentence(take.signal)
  const opening = generatedOpening(take)
  const angleSentence = generatedAngleSentence(take)
  const factLine = compactFactLine(take, 6)
  const teamFactLine = compactFactLine(take, 5)
  const cleanTrust = cleanText(verifiedValue(take, 'clean_trust.text'))
  const cleanOptions = cleanText(verifiedValue(take, 'clean_options.text'))
  const highRisk = cleanText(verifiedValue(take, 'high_risk.text'))
  const xLead = xFactSentence(take)

  return {
    reddit: {
      platform: 'Reddit',
      league: {
        label: 'Reddit - league-wide',
        audience: 'r/baseball or r/Sabermetrics',
        text: [
          `${opening}.`,
          `${angleSentence} This is more useful as a bullpen-management question than a prediction.`,
          `Verified facts in the story: ${factLine}.`,
          cleanLaneQuestion(cleanTrust, cleanOptions),
        ].join('\n\n'),
      },
      team: {
        label: 'Reddit - team subreddit',
        audience: `${abbr} team subreddit`,
        text: [
          `${abbr} fans, tonight's bullpen board has a specific shape: ${teamFactLine}.`,
          `${signal}.`,
          take.postability.hasTension
            ? `That makes the game-thread angle less about raw availability and more about ${angleLine(take)}.`
            : `That makes the game-thread angle a clean board read, not a forced warning.`,
          highRisk
            ? `The watch-list piece is hard to ignore: ${highRisk}.`
            : `How would you sequence the trust lane if this turns into a close game?`,
        ].join('\n\n'),
      },
    },
    linkedin: {
      platform: 'LinkedIn',
      label: 'LinkedIn',
      audience: 'Baseball ops, builders, and professional network',
      text: [
        `${opening}.`,
        `That was the most useful private BaseballOS post draft for ${teamPhrase} today because the copy stays anchored to the story's verified facts: ${factLine}.`,
        `${angleSentence} The product lesson is that shareable baseball copy gets sharper when the claim stays inside the evidence, not when it adds a louder opinion.`,
      ].join('\n\n'),
    },
    x: {
      platform: 'X',
      label: 'X lead tweet',
      audience: 'Baseball fans scrolling X',
      lead: xLead,
      characterCount: xLead.length,
      support: underLimit([
        `Verified facts: ${factLine}. ${signal}.`,
        `Verified facts: ${factLine}.`,
      ], X_LEAD_CHARACTER_LIMIT),
      text: `${xLead}\n\nVerified facts: ${underLimit([factLine], X_LEAD_CHARACTER_LIMIT - 18)}`,
    },
  }
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

export function findUnverifiedNumbers(text, verifiedFacts) {
  const allowed = new Set(verifiedFacts?.numeric_tokens || collectVerifiedNumberTokens(verifiedFacts || {}))
  return extractNumberTokens(text).filter(token => !allowed.has(token))
}

function decorateDraft(draft, verifiedFacts, options = {}) {
  if (!draft) return draft
  const textToCheck = [draft.lead, draft.support, draft.text].map(cleanText).filter(Boolean).join('\n')
  const unverifiedNumbers = findUnverifiedNumbers(textToCheck, verifiedFacts)
  return {
    ...draft,
    source: options.source,
    sourceLabel: DRAFT_SOURCE_LABELS[options.source] || options.source,
    fallbackReason: options.fallbackReason || null,
    factCheck: {
      checked: true,
      unverifiedNumbers,
    },
    reviewFlags: unverifiedNumbers.map(value => `Unverified number: ${value}`),
  }
}

function decorateDraftTree(drafts = {}, verifiedFacts, options = {}) {
  return {
    reddit: {
      ...drafts.reddit,
      league: decorateDraft(drafts.reddit?.league, verifiedFacts, options),
      team: decorateDraft(drafts.reddit?.team, verifiedFacts, options),
    },
    linkedin: decorateDraft(drafts.linkedin, verifiedFacts, options),
    x: decorateDraft(drafts.x, verifiedFacts, options),
  }
}

function draftHasCopy(draft) {
  return Boolean(cleanText(draft?.text) || cleanText(draft?.lead))
}

function hasCompleteDraftSet(drafts) {
  return Boolean(
    draftHasCopy(drafts?.reddit?.league)
    && draftHasCopy(drafts?.reddit?.team)
    && draftHasCopy(drafts?.linkedin)
    && draftHasCopy(drafts?.x)
  )
}

export function buildDraftGenerationPayload(take) {
  const verifiedFacts = take.verifiedFacts || buildVerifiedFactSet(take.story, take.facts)
  return {
    platforms: POST_DRAFT_PLATFORMS,
    team: verifiedFacts.team,
    story: verifiedFacts.story,
    signal: verifiedFacts.signal,
    evidence: verifiedFacts.evidence,
    postability: {
      has_tension: take.postability.hasTension,
      has_superlative: take.postability.hasSuperlative,
      angle: angleLine(take),
    },
    verified_facts: verifiedFacts,
    constraints: {
      use_only_verified_facts: true,
      x_lead_character_limit: X_LEAD_CHARACTER_LIMIT,
      no_public_product_centering_for: ['reddit_league', 'reddit_team', 'x'],
    },
  }
}

export function resolveDraftPackage(take, candidateDrafts, options = {}) {
  const verifiedFacts = take.verifiedFacts || buildVerifiedFactSet(take.story, take.facts)
  const hasGeneratedDrafts = hasCompleteDraftSet(candidateDrafts)
  const source = hasGeneratedDrafts ? DRAFT_SOURCE_GENERATED : DRAFT_SOURCE_TEMPLATE_FALLBACK
  const drafts = hasGeneratedDrafts
    ? candidateDrafts
    : (take.templateDrafts || buildPlatformDrafts(take))
  return {
    source,
    sourceLabel: DRAFT_SOURCE_LABELS[source],
    fallbackReason: hasGeneratedDrafts ? null : (options.fallbackReason || 'Generated draft request returned no usable copy.'),
    drafts: decorateDraftTree(drafts, verifiedFacts, {
      source,
      fallbackReason: hasGeneratedDrafts ? null : (options.fallbackReason || 'Generated draft request returned no usable copy.'),
    }),
  }
}

export async function resolveGeneratedDraftPackage(take, options = {}) {
  if (typeof options.requestDrafts === 'function') {
    try {
      const response = await options.requestDrafts(buildDraftGenerationPayload(take))
      return resolveDraftPackage(take, response?.drafts || response, options)
    } catch (error) {
      return resolveDraftPackage(take, null, {
        ...options,
        fallbackReason: options.fallbackReason || 'Generated draft request failed.',
      })
    }
  }
  return resolveDraftPackage(take, buildGeneratedPlatformDrafts(take), options)
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
  const verifiedFacts = buildVerifiedFactSet(story, facts)
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
    verifiedFacts,
    postability,
    suggestedAudience: postability.hasTension
      ? `${teamAbbr(story)} team subreddit first, then r/baseball if the angle holds up outside the fan base`
      : `r/baseball or ${teamAbbr(story)} team subreddit as a lighter discussion prompt`,
  }
  const templateDrafts = decorateDraftTree(buildPlatformDrafts(take), verifiedFacts, {
    source: DRAFT_SOURCE_TEMPLATE_FALLBACK,
    fallbackReason: 'Template fallback copy.',
  })
  const draftPackage = resolveDraftPackage(
    { ...take, templateDrafts },
    buildGeneratedPlatformDrafts(take),
  )
  return {
    ...take,
    templateDrafts,
    draftPackage,
    drafts: draftPackage.drafts,
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
