// Story Engine V1 foundation.
//
// This module does not create new signals or fetch new data. It takes the
// story candidates the existing homepage and Stories view-models already
// derive, then adds deterministic tiering, significance scoring, evidence
// checks, and suppression.

export const STORY_ENGINE_V1_VERSION = 'story_engine_v1_foundation'

export const STORY_TIERS = Object.freeze({
  league: Object.freeze({
    key: 'tier_1',
    level: 1,
    label: 'League-wide story',
    description: 'A bullpen pattern that matters beyond one club.',
  }),
  team: Object.freeze({
    key: 'tier_2',
    level: 2,
    label: 'Team story',
    description: 'A club-level bullpen story with enough evidence to surface.',
  }),
  pitcher: Object.freeze({
    key: 'tier_3',
    level: 3,
    label: 'Pitcher story',
    description: 'A pitcher-level story that needs broader context to surface.',
  }),
  data: Object.freeze({
    key: 'tier_4',
    level: 4,
    label: 'Data observation / suppressible',
    description: 'A data or trust note that only surfaces when the evidence is useful.',
  }),
})

export const SIGNIFICANCE_LEVELS = Object.freeze({
  lead: Object.freeze({ key: 'lead', label: 'Lead story', min: 78 }),
  high: Object.freeze({ key: 'high', label: 'High significance', min: 62 }),
  solid: Object.freeze({ key: 'solid', label: 'Solid significance', min: 48 }),
  supporting: Object.freeze({ key: 'supporting', label: 'Supporting significance', min: 36 }),
  low: Object.freeze({ key: 'low', label: 'Low significance', min: 0 }),
})

const DEFAULT_MIN_SIGNIFICANCE = 42
const DATA_MIN_SIGNIFICANCE = 36

const MECHANICAL_LANGUAGE_PATTERNS = [
  /\bavailability inventory\b/i,
  /\breadiness limitations\b/i,
  /\blimitations are present\b/i,
  /\btrusted snapshot\b/i,
  /\bfatigue score\b/i,
  /\bconfidence score\b/i,
  /\bontology\b/i,
  /\bdata_state\b/i,
  /\bfail_closed\b/i,
  /\bregister as\b/i,
  /\bworkload-restricted\b/i,
  /\blimited recovery window\b/i,
  /\bcarrying workload concentration\b/i,
]

function asNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function text(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function candidateText(candidate) {
  return [
    candidate?.kicker,
    candidate?.title,
    candidate?.body,
    candidate?.observation,
    candidate?.whyItMatters,
  ].map(text).filter(Boolean).join(' ')
}

function storyKind(candidate) {
  return text(candidate?.storyKind || candidate?.family || candidate?.kicker).toLowerCase()
}

function teamFromCandidate(candidate) {
  if (candidate?.team) return candidate.team
  if (candidate?.teamId == null && candidate?.teamName == null) return null
  return {
    teamId: candidate.teamId ?? null,
    teamName: candidate.teamName ?? null,
    abbr: candidate.abbr ?? null,
    available: asNumber(candidate.available),
    monitor: asNumber(candidate.monitor),
    restricted: asNumber(candidate.restricted),
    total: asNumber(candidate.total),
    pctAvailable: asNumber(candidate.pctAvailable),
    pctRestricted: asNumber(candidate.pctRestricted),
  }
}

function teamKey(candidate) {
  const team = teamFromCandidate(candidate)
  return team?.teamId ?? team?.abbr ?? team?.teamName ?? null
}

function sourceObservation(candidate) {
  return candidate?.sourceObservation || candidate?.observationSource || null
}

function usesLeagueMetricContext(candidate) {
  if (teamFromCandidate(candidate)) return true
  return classifyStoryTier(candidate).key === STORY_TIERS.league.key
}

function contextMetrics(context = {}) {
  return context.leagueMetrics || {}
}

function contextFreshness(context = {}) {
  return context.freshness || {}
}

function normalizeEvidenceItem(item, fallbackSource = 'story_candidate') {
  if (!item || typeof item !== 'object') return null
  const label = text(item.label || item.evidence_label || item.name)
  if (!label) return null
  return {
    label,
    value: item.value ?? item.evidence_value ?? null,
    source: text(item.source) || fallbackSource,
    sourceType: text(item.source_type || item.sourceType) || 'derived_story_evidence',
    detail: text(item.detail || item.summary) || null,
    dataThrough: text(item.data_through || item.dataThrough) || null,
    freshnessStatus: text(item.freshness_status || item.freshnessStatus) || null,
  }
}

function evidenceFromTeam(team) {
  if (!team) return []
  const total = asNumber(team.total)
  if (total <= 0) return []
  return [
    {
      label: 'Relievers needing rest',
      value: `${asNumber(team.restricted)} of ${total}`,
      source: 'bullpen_dashboard_landscape',
      sourceType: 'team_bullpen_counts',
      detail: 'Recent workload has left this many tracked relievers needing a day.',
    },
    {
      label: 'Watch-list arms',
      value: `${asNumber(team.monitor)} of ${total}`,
      source: 'bullpen_dashboard_landscape',
      sourceType: 'team_bullpen_counts',
      detail: 'Tracked relievers carrying enough recent work to watch.',
    },
    {
      label: 'Fresh arms',
      value: `${asNumber(team.available)} of ${total}`,
      source: 'bullpen_dashboard_landscape',
      sourceType: 'team_bullpen_counts',
      detail: 'Tracked relievers coming in rested.',
    },
  ]
}

function evidenceFromObservation(observation) {
  if (!observation || !Array.isArray(observation.evidence)) return []
  return observation.evidence
    .map(item => normalizeEvidenceItem(item, 'governed_observation_feed'))
    .filter(Boolean)
}

function evidenceFromLeague(candidate, context = {}) {
  const metrics = contextMetrics(context)
  const total = asNumber(metrics.total)
  if (total <= 0) return []
  const kind = storyKind(candidate)
  const includeStress = kind.includes('pressure') || kind.includes('workload') || candidate?.tone === 'stress'
  const includeWorkload = kind.includes('workload') || kind.includes('watch') || candidate?.tone === 'watch'
  const includeRest = kind.includes('recovery') || kind.includes('rest') || candidate?.tone === 'rest'

  const evidence = []
  if (includeStress) {
    evidence.push({
      label: 'League arms needing rest',
      value: `${asNumber(metrics.restricted)} of ${total}`,
      source: 'bullpen_dashboard_context',
      sourceType: 'league_bullpen_counts',
      detail: 'Tracked relievers league-wide needing a day after recent work.',
    })
  }
  if (includeWorkload) {
    evidence.push({
      label: 'League watch-list arms',
      value: `${asNumber(metrics.monitor)} of ${total}`,
      source: 'bullpen_dashboard_context',
      sourceType: 'league_bullpen_counts',
      detail: 'Tracked relievers league-wide carrying enough recent work to watch.',
    })
  }
  if (includeRest) {
    evidence.push({
      label: 'League fresh arms',
      value: `${asNumber(metrics.available)} of ${total}`,
      source: 'bullpen_dashboard_context',
      sourceType: 'league_bullpen_counts',
      detail: 'Tracked relievers league-wide coming in rested.',
    })
  }
  return evidence
}

export function buildStoryEvidence(candidate = {}, context = {}) {
  const provided = Array.isArray(candidate.evidence)
    ? candidate.evidence.map(item => normalizeEvidenceItem(item)).filter(Boolean)
    : []
  const observationEvidence = evidenceFromObservation(sourceObservation(candidate))
  const teamEvidence = evidenceFromTeam(teamFromCandidate(candidate))
  const leagueEvidence = teamEvidence.length || !usesLeagueMetricContext(candidate)
    ? []
    : evidenceFromLeague(candidate, context)

  const seen = new Set()
  return [...provided, ...observationEvidence, ...teamEvidence, ...leagueEvidence]
    .filter(item => {
      const key = `${item.label}:${item.value}:${item.source}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function classifyStoryTier(candidate = {}) {
  if (candidate.tier?.key) {
    const known = Object.values(STORY_TIERS).find(tier => tier.key === candidate.tier.key)
    if (known) return known
  }
  const kind = storyKind(candidate)
  if (candidate.pitcherId != null || kind.includes('pitcher')) return STORY_TIERS.pitcher
  if (candidate.teamId != null || candidate.teamName || candidate.team) return STORY_TIERS.team
  if (
    kind.includes('data')
    || kind.includes('trust')
    || kind.includes('freshness')
    || candidate.kicker === 'Data Note'
  ) {
    return STORY_TIERS.data
  }
  return STORY_TIERS.league
}

function factor(key, label, points, reason) {
  return {
    key,
    label,
    points: Math.round(clamp(points, 0, 30)),
    reason,
  }
}

function workloadConcentrationFactor(candidate, context) {
  const team = teamFromCandidate(candidate)
  const metrics = contextMetrics(context)
  const source = team || (usesLeagueMetricContext(candidate) ? metrics : {})
  const monitor = asNumber(source.monitor)
  const total = asNumber(source.total)
  const kind = storyKind(candidate)
  const observation = sourceObservation(candidate)
  let points = 0

  if (total > 0) {
    const share = monitor / total
    points = Math.max(points, share >= 0.5 ? 24 : share >= 0.35 ? 20 : share >= 0.25 ? 14 : monitor > 0 ? 8 : 0)
  }
  if (monitor >= 4) points = Math.max(points, 22)
  if (monitor >= 3) points = Math.max(points, 18)
  if (kind.includes('workload') || kind.includes('watch') || observation?.family === 'workload_pressure') {
    points = Math.max(points, observation?.family === 'workload_pressure' ? 12 : 10)
  }

  return factor(
    'workload_concentration',
    'Workload concentration',
    points,
    points > 0
      ? `${monitor} tracked ${monitor === 1 ? 'arm is' : 'arms are'} on the watch list.`
      : 'No meaningful watch-list concentration is present.',
  )
}

function bullpenStressFactor(candidate, context) {
  const team = teamFromCandidate(candidate)
  const metrics = contextMetrics(context)
  const source = team || (usesLeagueMetricContext(candidate) ? metrics : {})
  const restricted = asNumber(source.restricted)
  const total = asNumber(source.total)
  const kind = storyKind(candidate)
  let points = 0

  if (total > 0) {
    const share = restricted / total
    points = Math.max(points, share >= 0.45 ? 28 : share >= 0.35 ? 24 : share >= 0.25 ? 18 : restricted > 0 ? 9 : 0)
  }
  if (restricted >= 4) points = Math.max(points, 26)
  if (restricted >= 3) points = Math.max(points, 23)
  if (candidate?.tone === 'stress' || kind.includes('pressure')) points = Math.max(points, 12)

  return factor(
    'bullpen_stress',
    'Bullpen stress',
    points,
    points > 0
      ? `${restricted} tracked ${restricted === 1 ? 'arm needs' : 'arms need'} rest after recent work.`
      : 'No meaningful rest shortage is present.',
  )
}

function recencyFactor(candidate, context) {
  const observation = sourceObservation(candidate)
  const freshness = observation?.freshness || contextFreshness(context)
  const games = context.games || {}
  const evidence = buildStoryEvidence(candidate, context)
  let points = 4
  let reason = 'The story has limited current-date context.'

  if (freshness?.status === 'current' || freshness?.is_current === true || freshness?.sync_status === 'success') {
    points = 14
    reason = 'The source data is marked current.'
  } else if (freshness?.data_through || games.as_of_date || games.data_state === 'historical') {
    points = 11
    reason = 'The story is tied to the latest completed-game window.'
  }

  if (evidence.some(item => item.freshnessStatus === 'current' || item.dataThrough)) {
    points = Math.max(points, 12)
    reason = 'Evidence carries current or dated source context.'
  }

  return factor('recency', 'Recency', points, reason)
}

function teamImpactFactor(candidate, context) {
  const tier = classifyStoryTier(candidate)
  const team = teamFromCandidate(candidate)
  const metrics = contextMetrics(context)
  let points = 0
  let reason = 'The story has limited team or league impact.'

  if (tier.key === STORY_TIERS.team.key && team) {
    const total = asNumber(team.total)
    const restricted = asNumber(team.restricted)
    const monitor = asNumber(team.monitor)
    const available = asNumber(team.available)
    points = total >= 7 ? 12 : total >= 5 ? 9 : 6
    if (restricted >= 3 || monitor >= 4 || available >= 6) points += 3
    reason = `${team.teamName || 'This club'} has a complete enough bullpen shape to carry a team story.`
  } else if (tier.key === STORY_TIERS.league.key) {
    const total = asNumber(metrics.total)
    const affected = asNumber(metrics.monitor) + asNumber(metrics.restricted)
    points = total > 0 ? 10 : 0
    if (affected >= 20) points += 4
    if (affected >= 10) points += 2
    reason = affected > 0
      ? `${affected} tracked league arms sit in watch or rest-shortage buckets.`
      : 'No broad league impact is present.'
  } else if (tier.key === STORY_TIERS.pitcher.key) {
    points = 5
    reason = 'Pitcher-level notes need broader team context before they lead.'
  } else if (tier.key === STORY_TIERS.data.key) {
    points = sourceObservation(candidate)?.severity === 'significant' ? 6 : 3
    reason = 'Data notes explain whether BaseballOS should speak or stay quiet.'
  }

  return factor('team_level_impact', 'Team-level impact', points, reason)
}

function continuityFactor(candidate) {
  const value = candidateText(candidate).toLowerCase()
  const kind = storyKind(candidate)
  const observation = sourceObservation(candidate)
  let points = 0
  let reason = 'No repeated pattern is visible in the supplied story data.'

  if (kind.includes('continuity') || kind.includes('hidden')) {
    points = 12
    reason = 'The candidate is built around a repeated workload pattern.'
  } else if (/(same arms|keep|keeps|lately|night after night|again|still|recent work|heavy work)/.test(value)) {
    points = 8
    reason = 'The story copy is tied to repeated recent usage.'
  }

  const evidence = Array.isArray(observation?.evidence) ? observation.evidence : []
  if (evidence.some(item => item?.metadata?.repeated_pattern || item?.metadata?.continuity)) {
    points = Math.max(points, 12)
    reason = 'Governed evidence marks a repeated pattern.'
  }

  return factor('narrative_continuity', 'Repeated pattern / narrative continuity', points, reason)
}

function evidenceStrengthFactor(candidate, context) {
  const evidence = buildStoryEvidence(candidate, context)
  const observation = sourceObservation(candidate)
  const directEvidenceCount = (
    (Array.isArray(candidate.evidence) ? candidate.evidence.length : 0)
    + (Array.isArray(observation?.evidence) ? observation.evidence.length : 0)
  )
  let points = 0
  let reason = 'No usable evidence is attached.'

  if (evidence.length >= 3) {
    points = 15
    reason = 'The story is backed by multiple count-based evidence items.'
  } else if (evidence.length === 2) {
    points = 12
    reason = 'The story is backed by more than one evidence item.'
  } else if (evidence.length === 1) {
    points = 9
    reason = 'The story has one usable evidence item.'
  }

  const confidenceStatus = observation?.confidence?.status
  if (directEvidenceCount >= 2) points += 4
  else if (directEvidenceCount === 1) points += 2
  if (confidenceStatus === 'high' || confidenceStatus === 'medium') points += 2
  if (observation?.severity === 'significant') points += 4
  if (observation?.severity === 'elevated') points += 2

  return factor('evidence_strength', 'Evidence strength', points, reason)
}

function fanRelevanceFactor(candidate) {
  const tier = classifyStoryTier(candidate)
  const value = candidateText(candidate)
  const hasReadableCopy = text(candidate.title).length >= 12
    && text(candidate.body || candidate.observation).length >= 24
  let points = hasReadableCopy ? 8 : 3
  let reason = hasReadableCopy
    ? 'The candidate has a clear baseball headline and supporting copy.'
    : 'The candidate needs stronger human-readable story copy.'

  if (candidate.href) points += 2
  if (candidate.teamName || candidate.team?.teamName) points += 2
  if (tier.key === STORY_TIERS.data.key) points = Math.min(points, 6)
  if (MECHANICAL_LANGUAGE_PATTERNS.some(pattern => pattern.test(value))) {
    points = 0
    reason = 'The candidate uses mechanical language and should not surface.'
  }

  return factor('fan_relevance_readability', 'Fan relevance / readability', points, reason)
}

function significanceLevel(total) {
  if (total >= SIGNIFICANCE_LEVELS.lead.min) return SIGNIFICANCE_LEVELS.lead
  if (total >= SIGNIFICANCE_LEVELS.high.min) return SIGNIFICANCE_LEVELS.high
  if (total >= SIGNIFICANCE_LEVELS.solid.min) return SIGNIFICANCE_LEVELS.solid
  if (total >= SIGNIFICANCE_LEVELS.supporting.min) return SIGNIFICANCE_LEVELS.supporting
  return SIGNIFICANCE_LEVELS.low
}

export function scoreStorySignificance(candidate = {}, context = {}) {
  const factors = [
    workloadConcentrationFactor(candidate, context),
    bullpenStressFactor(candidate, context),
    recencyFactor(candidate, context),
    teamImpactFactor(candidate, context),
    continuityFactor(candidate),
    evidenceStrengthFactor(candidate, context),
    fanRelevanceFactor(candidate),
  ]
  const total = factors.reduce((sum, item) => sum + item.points, 0)
  const level = significanceLevel(total)
  return {
    total,
    level: level.key,
    levelLabel: level.label,
    factors,
    summary: `${level.label}: ${factors.filter(item => item.points > 0).map(item => item.label).join(', ') || 'limited supporting signal'}.`,
  }
}

function storyThreshold(candidate, options = {}) {
  if (Number.isFinite(options.minSignificance)) return options.minSignificance
  return classifyStoryTier(candidate).key === STORY_TIERS.data.key
    ? DATA_MIN_SIGNIFICANCE
    : DEFAULT_MIN_SIGNIFICANCE
}

export function getStorySuppressionReasons(candidate = {}, context = {}, options = {}) {
  const tier = classifyStoryTier(candidate)
  const significance = scoreStorySignificance(candidate, context)
  const evidence = buildStoryEvidence(candidate, context)
  const reasons = []
  const value = candidateText(candidate)
  const kind = storyKind(candidate)

  if (!text(candidate.title || candidate.headline) || !text(candidate.body || candidate.observation)) {
    reasons.push('story_missing_human_readable_copy')
  }
  if (evidence.length === 0) {
    reasons.push('story_missing_evidence')
  }
  if (MECHANICAL_LANGUAGE_PATTERNS.some(pattern => pattern.test(value))) {
    reasons.push('mechanical_story_language')
  }
  if (
    kind.includes('minor')
    || (
      kind.includes('availability_movement')
      && !significance.factors.find(item => item.key === 'narrative_continuity' && item.points >= 8)
    )
  ) {
    reasons.push('minor_availability_movement')
  }
  if (
    tier.key === STORY_TIERS.pitcher.key
    && !(
      (candidate.teamId != null || candidate.teamName || candidate.team)
      && evidence.length >= 2
      && significance.factors.find(item => item.key === 'narrative_continuity' && item.points >= 8)
    )
  ) {
    reasons.push('one_off_pitcher_observation')
  }
  if (significance.total < storyThreshold(candidate, options)) {
    reasons.push(tier.key === STORY_TIERS.data.key
      ? 'data_observation_below_surface_threshold'
      : 'story_below_significance_threshold')
  }

  return [...new Set(reasons)]
}

function defaultWhyItMatters(candidate, tier) {
  const kind = storyKind(candidate)
  if (candidate.whyItMatters) return candidate.whyItMatters
  if (kind.includes('pressure') || candidate.tone === 'stress') {
    return 'A short bullpen changes how much room the club has in close games.'
  }
  if (kind.includes('workload') || candidate.tone === 'watch') {
    return 'Heavy work on the same few arms can turn a quiet day into tomorrow\'s story.'
  }
  if (kind.includes('recovery') || candidate.tone === 'rest') {
    return 'Fresh arms give a club more room to handle the late innings.'
  }
  if (tier.key === STORY_TIERS.data.key) {
    return 'Thin or limited data changes how much BaseballOS should say out loud.'
  }
  return 'The wider league picture helps explain whether one club is an outlier or part of the day\'s broader bullpen shape.'
}

function noticed(candidate) {
  return candidate.noticed
    || candidate.observation
    || candidate.body
    || candidate.title
    || candidate.headline
    || 'A bullpen story changed enough to review.'
}

function selectionReason(tier, significance) {
  const strongest = [...significance.factors]
    .sort((a, b) => b.points - a.points)
    .slice(0, 2)
    .map(item => item.label.toLowerCase())
    .join(' and ')
  return `${tier.label} surfaced for ${strongest || 'supporting evidence'}.`
}

function decorateCandidate(candidate, evaluation) {
  const { tier, significance, evidence } = evaluation
  return {
    ...candidate,
    tier,
    significance,
    evidence,
    noticed: noticed(candidate),
    whyItMatters: defaultWhyItMatters(candidate, tier),
    selectionReason: selectionReason(tier, significance),
    storySelection: {
      noticed: noticed(candidate),
      whyItMatters: defaultWhyItMatters(candidate, tier),
      evidence,
      tier: tier.label,
      significance: significance.levelLabel,
    },
  }
}

export function evaluateStoryCandidate(candidate = {}, context = {}, index = 0, options = {}) {
  const tier = classifyStoryTier(candidate)
  const significance = scoreStorySignificance(candidate, context)
  const evidence = buildStoryEvidence(candidate, context)
  const suppressionReasons = getStorySuppressionReasons(candidate, context, options)
  return {
    candidate,
    index,
    tier,
    significance,
    evidence,
    suppressed: suppressionReasons.length > 0,
    suppressionReasons,
    story: decorateCandidate(candidate, { tier, significance, evidence }),
  }
}

function compareEvaluations(a, b) {
  if (b.significance.total !== a.significance.total) {
    return b.significance.total - a.significance.total
  }
  if (a.tier.level !== b.tier.level) return a.tier.level - b.tier.level
  return a.index - b.index
}

function normalizedKey(value) {
  return value == null ? null : String(value).toLowerCase()
}

function narrativeKey(story) {
  if (teamKey(story) != null) return `team:${normalizedKey(teamKey(story))}`
  const theme = storyTheme(story)
  if (theme) return `theme:${theme}`
  return `title:${text(story.title).toLowerCase()}`
}

function storyTheme(story) {
  const kind = storyKind(story)
  const family = text(story.family || sourceObservation(story)?.family).toLowerCase()

  if (family === 'workload_pressure' || kind.includes('workload') || kind.includes('watch')) {
    return 'workload'
  }
  if (family === 'freshness' || kind.includes('freshness')) return 'data:freshness'
  if (family === 'trust' || kind.includes('trust')) return 'data:trust'
  if (family === 'inventory' || kind.includes('depth')) return 'depth'
  if (family === 'readiness' || kind.includes('pressure') || kind.includes('stress')) return 'pressure'
  if (kind.includes('recovery') || kind.includes('rest')) return 'recovery'
  if (kind.includes('data')) return `data:${family || 'general'}`
  return kind
}

function suppressedEvaluation(evaluation, reason) {
  return {
    ...evaluation,
    suppressed: true,
    suppressionReasons: [...new Set([...evaluation.suppressionReasons, reason])],
  }
}

export function selectStoryCandidates(candidates = [], context = {}, options = {}) {
  const limit = Number.isFinite(options.limit) ? options.limit : 8
  const excludedTeams = new Set((options.excludedTeamIds || []).map(normalizedKey))
  const usedTeams = new Set()
  const usedNarratives = new Set()
  const surfaced = []
  const suppressed = []

  const evaluated = (Array.isArray(candidates) ? candidates : [])
    .map((candidate, index) => evaluateStoryCandidate(candidate, context, index, options))
    .sort(compareEvaluations)

  for (const evaluation of evaluated) {
    const key = normalizedKey(teamKey(evaluation.story))
    const storyNarrative = narrativeKey(evaluation.story)

    if (evaluation.suppressed) {
      suppressed.push(evaluation)
      continue
    }
    if (key && excludedTeams.has(key)) {
      suppressed.push(suppressedEvaluation(evaluation, 'duplicate_flagship_team_story'))
      continue
    }
    if (key && usedTeams.has(key)) {
      suppressed.push(suppressedEvaluation(evaluation, 'duplicate_team_narrative'))
      continue
    }
    if (storyNarrative && usedNarratives.has(storyNarrative)) {
      suppressed.push(suppressedEvaluation(evaluation, 'duplicate_story_narrative'))
      continue
    }

    surfaced.push(evaluation.story)
    if (key) usedTeams.add(key)
    if (storyNarrative) usedNarratives.add(storyNarrative)
    if (surfaced.length >= limit) break
  }

  return {
    items: surfaced,
    suppressed,
    suppressedCount: suppressed.length,
    suppressionReasons: [...new Set(suppressed.flatMap(item => item.suppressionReasons))],
  }
}

export function selectLeadStory(candidates = [], context = {}, options = {}) {
  return selectStoryCandidates(candidates, context, { ...options, limit: 1 }).items[0] || null
}
