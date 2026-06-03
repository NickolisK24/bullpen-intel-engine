const BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : '/api'

// Optional admin token for operational write endpoints (sync / recalculate).
// Left unset for local dev (the backend allows those routes when its own
// ADMIN_API_TOKEN is unset). Only set this for a build where you intend the
// operator UI to drive a token-protected backend.
const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_API_TOKEN
export const RECOMMENDATION_CANDIDATE_ROUTE = '/recommendations/candidate'
export const RECOMMENDATION_V2_BULLPEN_STATE_ROUTE = '/recommendations/v2/bullpen-state'
const inFlightGetRequests = new Map()

const RECOMMENDATION_V2_REQUIRED_TOP_LEVEL_FIELDS = [
  'scope',
  'ranking_applied',
  'selection_made',
  'confidence',
  'data_state',
  'generated_at',
  'freshness',
  'limitations',
  'explanations',
  'refusal_reasons',
  'fail_closed',
  'trust_metadata',
  'bullpen_state',
]

const RECOMMENDATION_V2_REQUIRED_TRUST_FIELDS = [
  'scope',
  'ranking_applied',
  'selection_made',
  'confidence',
  'data_state',
  'generated_at',
]

const RECOMMENDATION_V2_FORBIDDEN_FIELD_KEYS = new Set([
  'bestPitcher',
  'best_pitcher',
  'candidateRankings',
  'candidate_rankings',
  'gameOutcomeForecast',
  'game_outcome_forecast',
  'injuryForecast',
  'injury_forecast',
  'prediction',
  'predictions',
  'preferredOption',
  'preferredPitcher',
  'preferred_option',
  'preferred_pitcher',
  'priority',
  'priorityOrder',
  'priority_order',
  'rank',
  'rankedCandidates',
  'ranked_candidates',
  'ranking',
  'rankings',
  'recommendedPitcher',
  'recommended_pitcher',
  'saveForecast',
  'save_forecast',
  'score',
  'scores',
  'selectedPitcher',
  'selectedPitcherId',
  'selected_pitcher',
  'selected_pitcher_id',
  'winner',
])

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function hasOwn(value, key) {
  return isObject(value) && Object.prototype.hasOwnProperty.call(value, key)
}

function collectForbiddenFieldPaths(value, path = []) {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => collectForbiddenFieldPaths(item, [...path, index]))
  }
  if (!isObject(value)) return []

  return Object.entries(value).flatMap(([key, child]) => {
    const currentPath = [...path, key]
    const childPaths = collectForbiddenFieldPaths(child, currentPath)
    if (RECOMMENDATION_V2_FORBIDDEN_FIELD_KEYS.has(key)) {
      return [currentPath.join('.'), ...childPaths]
    }
    return childPaths
  })
}

function getMissingFields(value, fields, prefix = '') {
  if (!isObject(value)) {
    return fields.map(field => `${prefix}${field}`)
  }
  return fields
    .filter(field => !hasOwn(value, field))
    .map(field => `${prefix}${field}`)
}

function getMalformedFields(response = {}) {
  if (!isObject(response)) return ['response']

  const fields = []
  if (hasOwn(response, 'freshness') && !isObject(response.freshness)) {
    fields.push('freshness')
  }
  if (hasOwn(response, 'trust_metadata') && !isObject(response.trust_metadata)) {
    fields.push('trust_metadata')
  }
  if (hasOwn(response, 'limitations') && !Array.isArray(response.limitations)) {
    fields.push('limitations')
  }
  if (hasOwn(response, 'explanations') && !Array.isArray(response.explanations)) {
    fields.push('explanations')
  }
  if (hasOwn(response, 'refusal_reasons') && !Array.isArray(response.refusal_reasons)) {
    fields.push('refusal_reasons')
  }
  if (
    hasOwn(response, 'fail_closed')
    && typeof response.fail_closed !== 'boolean'
    && !isObject(response.fail_closed)
  ) {
    fields.push('fail_closed')
  }
  return fields
}

function isFailClosedMetadata(value) {
  if (value === true) return true
  if (!isObject(value)) return false

  return (
    value.failed_closed === true
    || value.critical_failure === true
    || value.governance_state === 'failed_closed'
    || value.state === 'degraded'
    || value.state === 'refused'
    || value.state === 'failed_closed'
  )
}

function buildQuery(params = {}) {
  const q = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      q.set(key, value)
    }
  })
  const query = q.toString()
  return query ? `?${query}` : ''
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (ADMIN_TOKEN) headers['X-Admin-Token'] = ADMIN_TOKEN
  const method = String(options.method || 'GET').toUpperCase()
  const dedupeKey = method === 'GET' && !options.body ? `${BASE}${path}` : null
  if (dedupeKey && inFlightGetRequests.has(dedupeKey)) {
    return inFlightGetRequests.get(dedupeKey)
  }

  const requestPromise = (async () => {
    try {
      const res = await fetch(`${BASE}${path}`, { ...options, headers })
      if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
      return await res.json()
    } catch (err) {
      console.error(`[API] ${path}`, err)
      throw err
    } finally {
      if (dedupeKey) {
        inFlightGetRequests.delete(dedupeKey)
      }
    }
  })()

  if (dedupeKey) {
    inFlightGetRequests.set(dedupeKey, requestPromise)
  }
  return requestPromise
}

// ── Health ─────────────────────────────────────────────────
export const checkHealth = () => request('/health')

// ── Bullpen / Fatigue ───────────────────────────────────────
export const getFatigueScores  = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/fatigue${q ? `?${q}` : ''}`)
}
export const getPitcherFatigue = (id) => request(`/bullpen/fatigue/${id}`)
export const recalculateFatigue = () => request('/bullpen/fatigue/recalculate', { method: 'POST' })

export const getPitchers       = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/pitchers${q ? `?${q}` : ''}`)
}
export const getPitcherLogs    = (id, days = 30) => request(`/bullpen/pitchers/${id}/logs?days=${days}`)

export const getTeams          = () => request('/bullpen/teams')
export const getTeamBullpen    = (teamId, params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/teams/${teamId}/bullpen${q ? `?${q}` : ''}`)
}
export const getBullpenOverview = () => request('/bullpen/stats/overview')
export const getSyncStatus     = () => request('/bullpen/sync/status')
export const getFatigueEraInsight = () => request('/bullpen/insights/fatigue-era')
// No public helper for /bullpen/fatigue/snapshot: latest-workload snapshot mode
// is admin/dev validation only and must not power current-availability UI.

// ── Recommendation Engine V1 ───────────────────────────────
export function buildRecommendationCandidateRequest(candidate, requestMetadata = {}) {
  if (Array.isArray(candidate)) {
    throw new TypeError('Recommendation candidate evaluation accepts exactly one candidate.')
  }
  if (!candidate || typeof candidate !== 'object') {
    throw new TypeError('Recommendation candidate evaluation requires a candidate object.')
  }
  if (
    requestMetadata
    && (Array.isArray(requestMetadata) || typeof requestMetadata !== 'object')
  ) {
    throw new TypeError('Recommendation request metadata must be an object.')
  }

  const payload = { candidate }
  if (requestMetadata && Object.keys(requestMetadata).length > 0) {
    payload.request = requestMetadata
  }
  return payload
}

export function getRecommendationCandidateTrustFields(response = {}) {
  const data = response.data || {}
  const meta = response.meta || {}

  return {
    explanations: data.explanations || [],
    limitations: data.limitations || [],
    confidence: data.confidence || {},
    freshness: data.freshness || {},
    availability: data.availability || {},
    assignedCategories: data.assigned_categories || [],
    blockedCategories: data.blocked_categories || [],
    refusal: data.refusal || null,
    rankingApplied: meta.ranking_applied,
    selectionMade: meta.selection_made,
    selectedPitcherId: meta.selected_pitcher_id,
  }
}

export const evaluateRecommendationCandidate = (candidate, requestMetadata = {}) => (
  request(RECOMMENDATION_CANDIDATE_ROUTE, {
    method: 'POST',
    body: JSON.stringify(
      buildRecommendationCandidateRequest(candidate, requestMetadata),
    ),
  })
)

// ── Recommendation Engine V2 ───────────────────────────────
export function normalizeRecommendationV2BullpenStateResponse(response = {}) {
  const topLevelMissingFields = getMissingFields(
    response,
    RECOMMENDATION_V2_REQUIRED_TOP_LEVEL_FIELDS,
  )
  const trustMissingFields = getMissingFields(
    response?.trust_metadata,
    RECOMMENDATION_V2_REQUIRED_TRUST_FIELDS,
    'trust_metadata.',
  )
  const missingFields = [...topLevelMissingFields, ...trustMissingFields]
  const malformedFields = getMalformedFields(response)
  const forbiddenFieldPaths = collectForbiddenFieldPaths(response)

  const rankingApplied = response?.ranking_applied
  const selectionMade = response?.selection_made
  const trustRankingApplied = response?.trust_metadata?.ranking_applied
  const trustSelectionMade = response?.trust_metadata?.selection_made

  const governanceSafe = (
    rankingApplied === false
    && selectionMade === false
    && trustRankingApplied === false
    && trustSelectionMade === false
  )
  const isContractSafe = (
    governanceSafe
    && missingFields.length === 0
    && malformedFields.length === 0
    && forbiddenFieldPaths.length === 0
  )
  const isFailClosed = isContractSafe && isFailClosedMetadata(response.fail_closed)
  const contractState = isContractSafe
    ? (isFailClosed ? 'fail_closed' : 'available')
    : 'unavailable'

  return {
    endpoint: RECOMMENDATION_V2_BULLPEN_STATE_ROUTE,
    contractState,
    isContractSafe,
    isFailClosed,
    governance: {
      rankingApplied,
      selectionMade,
      trustRankingApplied,
      trustSelectionMade,
      rankingAppliedIsFalse: rankingApplied === false,
      selectionMadeIsFalse: selectionMade === false,
    },
    missingFields,
    malformedFields,
    forbiddenFieldPaths,
    scope: response?.scope ?? null,
    confidence: hasOwn(response, 'confidence') ? response.confidence : null,
    dataState: hasOwn(response, 'data_state') ? response.data_state : null,
    generatedAt: hasOwn(response, 'generated_at') ? response.generated_at : null,
    failClosed: hasOwn(response, 'fail_closed') ? response.fail_closed : null,
    freshness: isObject(response?.freshness) ? response.freshness : null,
    statusMetadata: isObject(response?.status_metadata) ? response.status_metadata : null,
    limitations: Array.isArray(response?.limitations) ? response.limitations : null,
    explanations: Array.isArray(response?.explanations) ? response.explanations : null,
    refusalReasons: Array.isArray(response?.refusal_reasons) ? response.refusal_reasons : null,
    trustMetadata: isObject(response?.trust_metadata) ? response.trust_metadata : null,
    bullpenState: isContractSafe ? response.bullpen_state : null,
  }
}

export const getRecommendationV2BullpenState = async (params = {}) => {
  const response = await request(`${RECOMMENDATION_V2_BULLPEN_STATE_ROUTE}${buildQuery(params)}`)
  return normalizeRecommendationV2BullpenStateResponse(response)
}

// ── Prospects ───────────────────────────────────────────────
export const getProspects        = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/prospects/${q ? `?${q}` : ''}`)
}
export const getProspect         = (id) => request(`/prospects/${id}`)
export const getProspectsByTeam  = () => request('/prospects/by-team')
export const getProspectPipeline = () => request('/prospects/pipeline')
export const compareProspects    = (id1, id2) => request(`/prospects/compare?id1=${id1}&id2=${id2}`)
export const getPipelineOverview = () => request('/prospects/stats/overview')

// ── Methodology ───────────────────────────────────────────────
export const getMethodology = () => request('/methodology/')
