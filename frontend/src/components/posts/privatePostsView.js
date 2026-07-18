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

const TEAM_MARKET_NAMES = {
  ARI: 'Arizona',
  AZ: 'Arizona',
  ATL: 'Atlanta',
  BAL: 'Baltimore',
  BOS: 'Boston',
  CHC: 'Chicago',
  CWS: 'Chicago',
  CIN: 'Cincinnati',
  CLE: 'Cleveland',
  COL: 'Colorado',
  DET: 'Detroit',
  HOU: 'Houston',
  KC: 'Kansas City',
  LAA: 'Los Angeles',
  LAD: 'Los Angeles',
  MIA: 'Miami',
  MIL: 'Milwaukee',
  MIN: 'Minnesota',
  NYM: 'New York',
  NYY: 'New York',
  OAK: 'Oakland',
  PHI: 'Philadelphia',
  PIT: 'Pittsburgh',
  SD: 'San Diego',
  SEA: 'Seattle',
  SF: 'San Francisco',
  STL: 'St. Louis',
  TB: 'Tampa Bay',
  TEX: 'Texas',
  TOR: 'Toronto',
  WSH: 'Washington',
}

// Canonical story_type -> kicker/rule label. Mirrors the Stories canonical feed
// adapter so Private Posts uses the same human-facing label per story type.
const CANONICAL_KICKER_BY_STORY_TYPE = {
  coverage_pressure: 'Carrying The Load',
  sustainability_question: 'Same Few Arms',
  depth_constraint: 'Thin Margin',
  route_change: 'Route Change',
  availability_depth: 'More Options',
  trust_lane: 'Trust Lane',
  bridge: 'Fragile Bridge',
}

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
      value: `${countLabel(highRiskArmCount, 'heavy-workload arm')}${names}`,
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
  const schedule = isObject(story?.schedule_postability)
    ? story.schedule_postability
    : {
        postable: false,
        state: 'uncertain',
        reason: 'schedule_authority_unavailable',
        games: [],
      }

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
    superlatives.push(`${highRiskArmCount} heavy-workload arms`)
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
    schedulePostable: schedule.postable === true,
    scheduleState: cleanText(schedule.state) || 'uncertain',
    scheduleReason: cleanText(schedule.reason) || 'schedule_authority_unavailable',
    scheduleGames: Array.isArray(schedule.games) ? schedule.games : [],
    doubleheader: schedule.doubleheader === true,
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

function verifiedNumber(take, path, fallback = null) {
  return finiteNumber(verifiedValue(take, path), fallback)
}

function marketName(take) {
  return TEAM_MARKET_NAMES[take.abbr] || teamLabel(take.story).replace(/^the\s+/i, '').split(/\s+/)[0] || take.abbr
}

function ordinal(value) {
  const number = finiteNumber(value)
  if (number === null) return ''
  const mod100 = number % 100
  if (mod100 >= 11 && mod100 <= 13) return `${number}th`
  const mod10 = number % 10
  if (mod10 === 1) return `${number}st`
  if (mod10 === 2) return `${number}nd`
  if (mod10 === 3) return `${number}rd`
  return `${number}th`
}

function trustedLatePhrase(count) {
  if (count === 0) return 'no obvious late-inning anchor'
  if (count === 1) return 'one trusted late option'
  if (count > 1) return `${count} trusted late options`
  return ''
}

function humanFacts(take) {
  const available = verifiedNumber(take, 'availability.available')
  const total = verifiedNumber(take, 'availability.total')
  const availableShare = verifiedNumber(take, 'availability.available_share')
  const cleanTrustCount = verifiedNumber(take, 'clean_trust.count')
  const cleanOptionCount = verifiedNumber(take, 'clean_options.count')
  const eraRank = verifiedNumber(take, 'season_era.rank')
  const eraRankTotal = verifiedNumber(take, 'season_era.rank_total')
  const era = verifiedNumber(take, 'season_era.era')
  const highRiskCount = verifiedNumber(take, 'high_risk.count', 0)
  const highRiskNames = Array.isArray(verifiedValue(take, 'high_risk.names', []))
    ? verifiedValue(take, 'high_risk.names', [])
    : []
  const topShare = verifiedNumber(take, 'workload.top_share')
  const perArmPitches = verifiedNumber(take, 'workload.per_arm_pitches')

  return {
    market: marketName(take),
    teamName: take.teamName,
    available,
    total,
    availableShare,
    cleanTrustCount,
    cleanOptionCount,
    eraRank,
    eraRankTotal,
    era,
    highRiskCount,
    highRiskNames,
    topShare,
    perArmPitches,
    trustedLate: trustedLatePhrase(cleanTrustCount),
  }
}

function resultPhrase(facts) {
  if (facts.eraRank !== null && facts.eraRank <= 3) {
    return `the ${ordinal(facts.eraRank)}-best current bullpen ERA in baseball`
  }
  if (facts.eraRank !== null && facts.eraRank <= 10) {
    return `a top-${facts.eraRank} current bullpen ERA`
  }
  if (facts.era !== null && facts.eraRank !== null && facts.eraRankTotal !== null) {
    return `a ${facts.era.toFixed(2)} ERA sitting ${ordinal(facts.eraRank)} of ${facts.eraRankTotal}`
  }
  return ''
}

function availabilityPhrase(facts) {
  if (facts.available === null) return ''
  if (facts.availableShare !== null && facts.availableShare <= 0.35) {
    return `only ${facts.available} arms available`
  }
  if (facts.available !== null && facts.total !== null) {
    return `${facts.available}/${facts.total} arms available`
  }
  return `${facts.available} arms available`
}

function fatiguePhrase(facts) {
  if (!facts.highRiskCount) return ''
  const names = joinReadable(facts.highRiskNames)
  return names
    ? `${facts.highRiskCount} arms already running hot (${names})`
    : `${facts.highRiskCount} arms already running hot`
}

function workloadPhrase(facts) {
  if (facts.topShare !== null && facts.topShare >= 0.58) {
    return `a few arms have carried ${formatPercent(facts.topShare)} of the recent work`
  }
  if (facts.perArmPitches !== null && facts.perArmPitches >= 32) {
    return `the recent workload is already heavy`
  }
  return ''
}

function humanTensionClaim(take) {
  const facts = humanFacts(take)
  const result = resultPhrase(facts)
  const availability = availabilityPhrase(facts)
  const fatigue = fatiguePhrase(facts)
  const workload = workloadPhrase(facts)

  if (result && facts.cleanTrustCount === 0) {
    return {
      hook: `${facts.market} has ${result}. They also have ${facts.trustedLate} tonight.`,
      meaning: `That is not a bad-bullpen take. It is a weird leverage map: great results, no obvious late-game answer.`,
      team: `${facts.market} fans, this is the part that feels worth arguing about: the results look excellent, but the late lane is not clean.`,
      linkedin: `The shareable part is the contradiction: strong run prevention can still leave a team without an obvious late-inning answer on a given night.`,
    }
  }

  if (fatigue) {
    return {
      hook: `${facts.market}'s recent bullpen workload jumps out first: ${fatigue}.`,
      meaning: facts.available !== null
        ? `There may still be a late path, but ${availability} leaves very little cushion behind it.`
        : `There may still be a late path, but the cushion behind it looks thin.`,
      team: `${facts.market} fans, this does not read like panic. It reads like a margin problem behind the arms you trust most.`,
      linkedin: `The point is not that the bullpen is broken; heavy recent usage can turn a normal late-game plan into a thinner operating window.`,
    }
  }

  if (result && availability && facts.availableShare !== null && facts.availableShare <= 0.35) {
    return {
      hook: `${facts.market} has ${result} and ${availability}.`,
      meaning: `That is a tightrope: the results may be fine, but tonight's usable room is small.`,
      team: `${facts.market} fans, this is the uncomfortable version of a usable bullpen: the options are thin even if the surface read is not panic.`,
      linkedin: `The interesting baseball read is that run prevention and usable depth can tell very different stories on the same night.`,
    }
  }

  if (workload) {
    return {
      hook: `${facts.market}'s bullpen looks usable, but ${workload}.`,
      meaning: `That is the kind of shape that can feel fine until the game asks for extra outs.`,
      team: `${facts.market} fans, the question is not just who is up. It is how quickly the same names have to get involved again.`,
      linkedin: `The workload translation matters: availability means more when it also shows how concentrated the recent work has been.`,
    }
  }

  if (result) {
    return {
      hook: `${facts.market} has ${result}, and the board is not flashing a big warning tonight.`,
      meaning: `Sometimes the post is simply that the bullpen has room to breathe.`,
      team: `${facts.market} fans, this is the calmer kind of bullpen post: strong results and enough room to manage the game normally.`,
      linkedin: `The baseball read is that not every shareable note needs tension; sometimes a clean board is the point.`,
    }
  }

  return {
    hook: `${facts.market}'s bullpen has a specific read tonight.`,
    meaning: `It is worth discussing because the board frames a real question, not because it settles what happens next.`,
    team: `${facts.market} fans, this is a bullpen-management question more than a prediction.`,
    linkedin: `The baseball read is simple: turn the board into one honest question, then stop before inventing a bigger story.`,
  }
}

function contextLine(take, facts) {
  const fatigue = fatiguePhrase(facts)
  const pieces = fatigue
    ? [
      fatigue,
      availabilityPhrase(facts),
      resultPhrase(facts),
      workloadPhrase(facts),
    ].filter(Boolean)
    : [
      resultPhrase(facts),
      availabilityPhrase(facts),
      workloadPhrase(facts),
    ].filter(Boolean)
  const limited = pieces.slice(0, 2)
  if (limited.length > 0) return `The shape: ${joinReadable(limited)}.`
  return trimSentence(take.evidence || take.signal)
}

function discussionQuestion(facts) {
  if (facts.cleanTrustCount === 0 && facts.cleanOptionCount !== null) {
    return `How much do ${facts.cleanOptionCount} clean options matter when none of them read like the obvious late arm?`
  }
  if (facts.highRiskCount > 0) {
    return `How much room is there behind the trusted names before recent workload starts steering the choices?`
  }
  if (facts.availableShare !== null && facts.availableShare <= 0.35) {
    return `Would you spend the cleaner lane early, or save it and accept the thinner middle?`
  }
  return `What would make you change the plan before the late innings?`
}

function xHumanLead(take) {
  const facts = humanFacts(take)
  const claim = humanTensionClaim(take)
  const result = resultPhrase(facts)
  const availability = availabilityPhrase(facts)
  const fatigue = fatiguePhrase(facts)

  return underLimit([
    `${claim.hook} ${claim.meaning}`,
    result && facts.cleanTrustCount === 0
      ? `${facts.market} has ${result}. No obvious late-inning anchor tonight. Great results, weird leverage map.`
      : '',
    result && availability
      ? `${facts.market} has ${result} and ${availability}. Strong pen, tight room to maneuver.`
      : '',
    fatigue && availability
      ? `${facts.market} has ${fatigue} and ${availability}. There is a path, but not much cushion.`
      : '',
    `${facts.market} bullpen tonight: ${trimSentence(take.signal)}`,
  ], X_LEAD_CHARACTER_LIMIT)
}

export function buildGeneratedPlatformDrafts(take) {
  const teamName = take.teamName
  const teamPhrase = definiteTeamName(teamName)
  const abbr = take.abbr
  const facts = humanFacts(take)
  const claim = humanTensionClaim(take)
  const context = contextLine(take, facts)
  const question = discussionQuestion(facts)
  const xLead = xHumanLead(take)

  return {
    reddit: {
      platform: 'Reddit',
      league: {
        label: 'Reddit - league-wide',
        audience: 'r/baseball or r/Sabermetrics',
        text: [
          claim.hook,
          `${claim.meaning} ${context}`,
          question,
          'I do not read it as a prediction. I read it as the kind of bullpen shape that makes the middle innings more interesting.',
        ].join('\n\n'),
      },
      team: {
        label: 'Reddit - team subreddit',
        audience: `${abbr} team subreddit`,
        text: [
          claim.team,
          context,
          `${question} I am not sure there is a perfect answer; that is what makes it a postable read.`,
        ].join('\n\n'),
      },
    },
    linkedin: {
      platform: 'LinkedIn',
      label: 'LinkedIn',
      audience: 'Baseball ops, builders, and professional network',
      text: [
        `${claim.hook}`,
        `${claim.linkedin} ${context}`,
        `That is the voice I want BaseballOS to get better at: not louder than the evidence, but willing to say what the evidence feels like in baseball language for ${teamPhrase}.`,
      ].join('\n\n'),
    },
    x: {
      platform: 'X',
      label: 'X lead tweet',
      audience: 'Baseball fans scrolling X',
      lead: xLead,
      characterCount: xLead.length,
      support: underLimit([
        `${context} ${question}`,
        context,
      ], X_LEAD_CHARACTER_LIMIT),
      text: xLead,
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
          `The ${teamName} bullpen is one I would bring up in a pregame conversation tonight.`,
          take.postability.hasTension
            ? `${signal}. The tension is not "bad bullpen"; it is ${angle}.`
            : `${signal}. The interesting part is ${angle}.`,
          `The numbers behind it: ${evidence}.`,
          'The question I would put to the room: if the starter exits early, does that change how you handle the late innings?',
        ].join('\n\n'),
      },
      team: {
        label: 'Reddit - team subreddit',
        audience: `${abbr} team subreddit`,
        text: [
          `${abbr} fans, tonight's bullpen question is more specific than just "who is available."`,
          `${signal}.`,
          `The board underneath it: ${evidence}.`,
          take.postability.hasTension
            ? `That is the argument for the game thread: the pen has a usable path, but ${angle}.`
            : `That is the game-thread angle: ${angle}, without turning it into a prediction.`,
          'Would you try to steal outs earlier, or hold the cleaner arms for leverage?',
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

function verifiedFactValuesByKind(verifiedFacts) {
  const values = new Map()
  const add = (kind, entry) => {
    if (!values.has(kind)) values.set(kind, new Set())
    values.get(kind).add(String(entry).trim().toLowerCase())
  }
  const visit = (entry, path = []) => {
    if (Array.isArray(entry)) {
      entry.forEach(item => visit(item, path))
      return
    }
    if (isObject(entry)) {
      Object.entries(entry).forEach(([key, item]) => visit(item, [...path, key]))
      return
    }
    if (entry === null || entry === undefined || entry === '') return
    const key = String(path.at(-1) || '').toLowerCase()
    const ancestors = path.map(part => String(part).toLowerCase())
    if (/name$/.test(key) && ancestors.some(part => /arm|reliever|pitcher|named/.test(part))) add('names', entry)
    if (/date$/.test(key)) add('dates', entry)
    if (/pitch.*count|pitch_counts|trailing_pitches/.test(key)) add('pitch_counts', entry)
    if (/percent|percentage|_pct$|share_pct/.test(key)) add('percentages', entry)
    if (/team/.test(key) || ancestors.some(part => part === 'team' || part === 'teams')) add('teams', entry)
    if (/matchup/.test(key) || ancestors.some(part => /matchup/.test(part))) add('matchup_facts', entry)
  }
  visit(verifiedFacts || {})
  return values
}

export function auditGeneratedFactClaims(factClaims, verifiedFacts) {
  if (!isObject(factClaims)) {
    return { checked: false, valid: false, violations: ['Missing structured fact claims'] }
  }
  const allowedByKind = verifiedFactValuesByKind(verifiedFacts)
  const violations = []
  const requiredKinds = ['names', 'dates', 'pitch_counts', 'percentages', 'teams', 'matchup_facts']
  for (const kind of requiredKinds) {
    if (!Array.isArray(factClaims[kind])) {
      violations.push(`Missing ${kind.replaceAll('_', ' ')} claims`)
    }
  }
  for (const [kind, claims] of Object.entries(factClaims)) {
    const values = Array.isArray(claims) ? claims : [claims]
    for (const value of values.filter(item => item !== null && item !== undefined && item !== '')) {
      const allowed = allowedByKind.get(kind) || new Set()
      if (!allowed.has(String(value).trim().toLowerCase())) {
        violations.push(`Unverified ${kind.replaceAll('_', ' ')}: ${value}`)
      }
    }
  }
  return { checked: true, valid: violations.length === 0, violations }
}

function decorateDraft(draft, verifiedFacts, options = {}) {
  if (!draft) return draft
  const textToCheck = [draft.lead, draft.support, draft.text].map(cleanText).filter(Boolean).join('\n')
  const unverifiedNumbers = findUnverifiedNumbers(textToCheck, verifiedFacts)
  const claimAudit = options.requireFactClaims || draft.factClaims
    ? auditGeneratedFactClaims(draft.factClaims, verifiedFacts)
    : { checked: false, valid: true, violations: [] }
  const reviewFlags = [
    ...unverifiedNumbers.map(value => `Unverified number: ${value}`),
    ...claimAudit.violations,
  ]
  return {
    ...draft,
    source: options.source,
    sourceLabel: DRAFT_SOURCE_LABELS[options.source] || options.source,
    fallbackReason: options.fallbackReason || null,
    factCheck: {
      checked: true,
      unverifiedNumbers,
      claims: claimAudit,
    },
    reviewFlags,
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

function generatedDraftFactsAreValid(drafts, verifiedFacts, requireFactClaims) {
  return flattenTakeDrafts({ drafts }).every(draft => {
    const text = [draft?.lead, draft?.support, draft?.text].map(cleanText).filter(Boolean).join('\n')
    if (findUnverifiedNumbers(text, verifiedFacts).length > 0) return false
    if (!requireFactClaims) return true
    return auditGeneratedFactClaims(draft?.factClaims, verifiedFacts).valid
  })
}

export function buildDraftGenerationPayload(take) {
  const verifiedFacts = take.verifiedFacts || buildVerifiedFactSet(take.story, take.facts)
  return {
    platforms: POST_DRAFT_PLATFORMS,
    verified_facts: verifiedFacts,
    writing_instructions: {
      interpretive_license: 'medium',
      lead: 'Open with the most surprising or arguable tension as a human claim, not a stat list.',
      interpretation: [
        'Explain what the verified facts mean in plain baseball language.',
        'Use light point of view when it follows from the facts.',
        'Do not predict outcomes as certain, assign causes, or add facts outside verified_facts.',
      ],
      style: [
        'Use fan language instead of internal labels.',
        'Use only the one or two numbers that make the take.',
        'Vary sentence length and avoid fixed skeleton phrases.',
      ],
    },
    constraints: {
      use_only_verified_facts: true,
      return_structured_fact_claims: {
        required: true,
        fields: ['names', 'dates', 'pitch_counts', 'percentages', 'teams', 'matchup_facts'],
      },
      x_lead_character_limit: X_LEAD_CHARACTER_LIMIT,
      no_public_product_centering_for: ['reddit_league', 'reddit_team', 'x'],
      forbidden_residue: [
        'The catch:',
        'the argument is',
        'The useful angle',
        'The useful framing',
        'The useful read',
        'Verified facts:',
      ],
      honest_register: [
        'Interpret, do not invent.',
        'Avoid future-tense certainty.',
        'Avoid causal claims the facts do not prove.',
      ],
    },
  }
}

export function resolveDraftPackage(take, candidateDrafts, options = {}) {
  const verifiedFacts = take.verifiedFacts || buildVerifiedFactSet(take.story, take.facts)
  const generatedFactClaimsComplete = !options.requireFactClaims || flattenTakeDrafts({ drafts: candidateDrafts })
    .every(draft => isObject(draft.factClaims))
  const generatedFactsValid = generatedFactClaimsComplete
    && generatedDraftFactsAreValid(candidateDrafts, verifiedFacts, options.requireFactClaims)
  const hasGeneratedDrafts = hasCompleteDraftSet(candidateDrafts) && generatedFactsValid
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
      requireFactClaims: source === DRAFT_SOURCE_GENERATED && options.requireFactClaims,
      fallbackReason: hasGeneratedDrafts ? null : (options.fallbackReason || 'Generated draft request returned no usable copy.'),
    }),
  }
}

export async function resolveGeneratedDraftPackage(take, options = {}) {
  if (typeof options.requestDrafts === 'function') {
    try {
      const response = await options.requestDrafts(buildDraftGenerationPayload(take))
      return resolveDraftPackage(take, response?.drafts || response, {
        ...options,
        requireFactClaims: true,
      })
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

// Adapt the canonical story feed (dashboard.stories) into the shape
// buildPostableTake consumes. Each PUBLISHABLE canonical story (story_available
// === true with a non-null team_id) becomes one postable-source story; the
// league_context card (no team_id) is excluded, and a missing/malformed feed
// returns [].
//
// GAP: the canonical story feed does not carry the legacy four-beat `computed`
// structured facts (availability/workload/season-ERA/clean-trust/high-risk
// counts), so those structured facts are not available here. Takes are built
// from canonical story content instead: the headline as the signal, the joined
// canonical evidence beats as the evidence, story_type as the rule key, plus
// continuity. extractStoryFacts already tolerates a missing `computed` (it
// returns its empty-but-valid shape), so nothing downstream crashes — the
// resulting takes simply carry no structured numeric facts.
export function canonicalPostableStories(dashboard) {
  const feed = dashboard?.stories
  const items = isObject(feed) && Array.isArray(feed.items) ? feed.items : []
  return items
    .filter(item => isObject(item) && item.story_available === true && item.team_id != null)
    .map(item => {
      const kicker = CANONICAL_KICKER_BY_STORY_TYPE[item.story_type] || 'Bullpen Story'
      const evidence = Array.isArray(item.evidence)
        ? item.evidence.map(part => cleanText(part?.text)).filter(Boolean).join(' ')
        : ''
      return {
        teamId: item.team_id,
        team_id: item.team_id,
        teamName: item.team_name,
        team_name: item.team_name,
        abbr: item.team_abbreviation,
        team_abbreviation: item.team_abbreviation,
        story_id: item.story_id,
        rule_key: item.story_type,
        rule_label: kicker,
        kicker,
        title: item.headline,
        body: item.narrative,
        narrative: item.narrative,
        tone: item.tone,
        category: item.category,
        continuity: item.continuity || null,
        schedule_postability: schedulePostabilityForTeam(dashboard, item.team_id),
        beats: [
          { key: 'signal', text: item.headline },
          { key: 'evidence', text: evidence || cleanText(item.narrative) },
        ],
        source: 'canonical',
      }
    })
}

export function getPrivatePostTakes(dashboard, options = {}) {
  const limit = Math.max(1, finiteNumber(options.limit, DEFAULT_POSTABLE_TAKE_LIMIT))
  return canonicalPostableStories(dashboard)
    .map(buildPostableTake)
    .filter(take => take?.postability?.schedulePostable === true)
    .sort((a, b) => (
      b.postability.score - a.postability.score
      || b.postability.storyStrength - a.postability.storyStrength
      || a.teamName.localeCompare(b.teamName)
      || a.abbr.localeCompare(b.abbr)
    ))
    .slice(0, limit)
}

function schedulePostabilityForTeam(dashboard, teamId) {
  const authority = isObject(dashboard?.schedule_authority)
    ? dashboard.schedule_authority
    : {}
  const freshness = isObject(authority.freshness) ? authority.freshness : {}
  if (freshness.is_fresh !== true) {
    return {
      postable: false,
      state: 'uncertain',
      reason: `schedule_${cleanText(freshness.state) || 'unavailable'}`,
      games: [],
    }
  }
  const team = isObject(authority.teams?.[String(teamId)])
    ? authority.teams[String(teamId)]
    : null
  return team || {
    postable: false,
    state: 'cancelled',
    reason: 'team_not_on_slate',
    games: [],
  }
}
