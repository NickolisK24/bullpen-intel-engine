import {
  BULLPEN_OBSERVATIONS_ROUTE,
  OBSERVATION_FORBIDDEN_FIELD_KEYS,
  OBSERVATION_FORBIDDEN_TEXT_TERMS,
  OBSERVATION_GOVERNANCE_FIELD_EXCEPTIONS,
  OBSERVATION_ITEM_REQUIRED_FIELDS,
  OBSERVATION_RESPONSE_REQUIRED_FIELDS,
} from '../types/observations'

const BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : '/api'

export const AUTH_TOKEN_STORAGE_KEY = 'baseballos.authToken'
export const AUTH_TOKEN_CHANGED_EVENT = 'baseballos:auth-token-changed'

// Privileged operational endpoints (sync / recalculate) are gated by the
// backend ADMIN_API_TOKEN via the X-Admin-Token header. The frontend never
// holds or sends that token: trigger those endpoints server-side or with curl
// so the admin secret can never be baked into the public browser bundle.
export const RECOMMENDATION_CANDIDATE_ROUTE = '/recommendations/candidate'
export const RECOMMENDATION_V2_BULLPEN_STATE_ROUTE = '/recommendations/v2/bullpen-state'
export const TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE =
  '/team-operations/bullpen-readiness'
export const EXPLANATION_AVAILABILITY_ROUTE_PREFIX = '/explanations/availability'
export const EXPLANATION_TEAM_READINESS_ROUTE = '/explanations/team-readiness'
export const BULLPEN_INTELLIGENCE_OBSERVATIONS_ROUTE = BULLPEN_OBSERVATIONS_ROUTE
const inFlightGetRequests = new Map()

function getBrowserStorage() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage || null
  } catch {
    return null
  }
}

function cleanAuthToken(value) {
  const token = value == null ? '' : String(value).trim()
  return token || null
}

function emitAuthTokenChange(token) {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return
  try {
    window.dispatchEvent(new CustomEvent(AUTH_TOKEN_CHANGED_EVENT, {
      detail: { token: token || null },
    }))
  } catch {
    // CustomEvent is not available in some test environments.
  }
}

export function readAuthToken(storage = getBrowserStorage()) {
  if (!storage) return null
  try {
    return cleanAuthToken(storage.getItem(AUTH_TOKEN_STORAGE_KEY))
  } catch {
    return null
  }
}

export function storeAuthToken(token, storage = getBrowserStorage()) {
  const cleaned = cleanAuthToken(token)
  if (!storage) return cleaned
  try {
    if (cleaned) {
      storage.setItem(AUTH_TOKEN_STORAGE_KEY, cleaned)
    } else {
      storage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    }
    emitAuthTokenChange(cleaned)
  } catch {
    // Storage can be disabled; callers can still keep the returned token.
  }
  return cleaned
}

export function clearAuthToken(storage = getBrowserStorage()) {
  if (!storage) {
    emitAuthTokenChange(null)
    return false
  }
  try {
    storage.removeItem(AUTH_TOKEN_STORAGE_KEY)
    emitAuthTokenChange(null)
    return true
  } catch {
    return false
  }
}

export function isAuthTokenStorageEvent(event) {
  if (!event || !('key' in event)) return true
  return event.key == null || event.key === AUTH_TOKEN_STORAGE_KEY
}

function hasAuthorizationHeader(headers = {}) {
  return Object.keys(headers).some(key => key.toLowerCase() === 'authorization')
}

function buildRequestHeaders(options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = options.authToken === undefined
    ? readAuthToken()
    : cleanAuthToken(options.authToken)

  if (token && !hasAuthorizationHeader(headers)) {
    headers.Authorization = `Bearer ${token}`
  }
  return { headers, token }
}

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

const TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_TOP_LEVEL_FIELDS = [
  'capability',
  'scope',
  'contract',
  'contract_version',
  'contract_state',
  'ranking_applied',
  'selection_made',
  'generated_at',
  'readiness',
  'constraints',
  'workload_pressure',
  'availability_distribution',
  'coverage_inventory',
  'handedness_coverage',
  'explanations',
  'limitations',
  'trust_metadata',
  'freshness',
  'refusal',
  'fail_closed',
  'route_metadata',
]

const TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_TRUST_FIELDS = [
  'confidence',
  'confidence_reasons',
  'data_state',
  'source_evidence_state',
  'governance_state',
  'generated_at',
  'limitations',
  'explanations',
  'refusal_reasons',
  'trust_validation_errors',
  'ranking_applied',
  'selection_made',
]

const TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_FRESHNESS_FIELDS = [
  'freshness_state',
  'data_through',
  'latest_workload_date',
  'last_successful_sync',
  'latest_sync_status',
  'latest_fatigue_calculated_at',
  'generated_at',
  'stale_warning',
  'missing_data_warning',
  'limitations',
]

const TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_ROUTE_FIELDS = [
  'route',
  'surface',
  'exposure',
  'production_status',
  'certification_status',
  'public_certified',
  'frontend_exposure',
]

const TEAM_OPERATIONS_BULLPEN_READINESS_ALLOWED_CONTRACT_STATES = new Set([
  'available',
  'degraded',
  'refused',
  'unavailable',
])

const TEAM_OPERATIONS_BULLPEN_READINESS_ALLOWED_STATUSES = new Set([
  'operationally_stable',
  'operationally_constrained',
  'operationally_stressed',
  'coverage_limited',
  'data_limited',
  'refused',
])

const TEAM_OPERATIONS_BULLPEN_READINESS_FORBIDDEN_FIELD_KEYS = new Set([
  'best',
  'best_pitcher',
  'bestPitcher',
  'best_pitcher_id',
  'preferred',
  'preferred_pitcher',
  'preferredPitcher',
  'preferred_pitcher_id',
  'recommended',
  'recommendation',
  'recommendations',
  'recommended_pitcher',
  'recommendedPitcher',
  'recommended_pitcher_id',
  'rank',
  'ranking',
  'rankings',
  'rankedCandidates',
  'ranked_candidates',
  'selected',
  'selection',
  'selected_pitcher',
  'selectedPitcher',
  'selected_pitcher_id',
  'priority',
  'priorityOrder',
  'priority_order',
  'hiddenPriority',
  'hidden_priority',
  'matchup',
  'matchupAdvice',
  'matchup_advice',
  'prediction',
  'predictions',
  'gameOutcomeForecast',
  'game_outcome_forecast',
  'injuryForecast',
  'injury_forecast',
  'saveForecast',
  'save_forecast',
  'performancePrediction',
  'performance_prediction',
])

const TEAM_OPERATIONS_BULLPEN_READINESS_GOVERNANCE_FIELD_EXCEPTIONS = new Set([
  'ranking_applied',
  'selection_made',
])

const TEAM_OPERATIONS_BULLPEN_READINESS_FORBIDDEN_TEXT_TERMS = [
  /\bbest\b/i,
  /\bpreferred\b/i,
  /\brecommended\b/i,
]

const CERTIFIED_EXPLANATION_TYPES = new Set([
  'availability_explanation',
  'team_readiness_explanation',
])

const CERTIFIED_TEAM_READINESS_EXPLANATION_SCOPES = new Set([
  'readiness_state',
  'workload_state',
  'coverage_state',
  'freshness_state',
  'trust_state',
])

const V4_EXPLANATION_REQUIRED_GOVERNANCE_FIELDS = [
  'ranking_applied',
  'selection_made',
  'recommendation_made',
  'prediction_made',
  'decision_scope',
  'advice_scope',
]

const V4_EXPLANATION_REQUIRED_SUCCESS_ENVELOPE_FIELDS = [
  'status',
  'explanation_type',
  'certification_status',
  'route_status',
  'explanation',
  'governance',
]

const V4_EXPLANATION_REQUIRED_UNAVAILABLE_ENVELOPE_FIELDS = [
  'status',
  'explanation_type',
  'certification_status',
  'route_status',
  'explanation',
  'limitations',
  'refusal',
  'governance',
]

const V4_EXPLANATION_REQUIRED_EXPLANATION_FIELDS = [
  'explanation_id',
  'scope',
  'subject_type',
  'subject_id',
  'state_explained',
  'summary',
  'primary_reasons',
  'supporting_evidence',
  'limitations',
  'freshness',
  'trust',
  'confidence',
  'governance',
]

const V4_EXPLANATION_FORBIDDEN_FIELD_KEYS = new Set([
  'best_arm',
  'best_candidate',
  'best_pitcher',
  'game_outcome_prediction',
  'game_prediction',
  'hidden_priority_ordering',
  'injury_prediction',
  'matchup',
  'matchup_advice',
  'outcome_prediction',
  'performance_forecast',
  'performance_prediction',
  'pitcher_choice',
  'predicted_injury',
  'predicted_performance',
  'predicted_saves',
  'prediction',
  'preferred_option',
  'preferred_pitcher',
  'priority',
  'priority_score',
  'projected_outcome',
  'projected_performance',
  'rank',
  'ranking',
  'recommended_option',
  'recommended_pitcher',
  'save_prediction',
  'score',
  'score_ordering',
  'selected_candidate',
  'selected_candidate_id',
  'selected_pitcher',
  'selected_pitcher_id',
  'top_candidate',
  'winner',
])

const V4_EXPLANATION_GOVERNANCE_FIELD_EXCEPTIONS = new Set([
  ...V4_EXPLANATION_REQUIRED_GOVERNANCE_FIELDS,
])

const V4_EXPLANATION_FORBIDDEN_TEXT_TERMS = [
  /\buse this pitcher\b/i,
  /\bavoid this pitcher\b/i,
  /\bbest option\b/i,
  /\bpreferred arm\b/i,
  /\brecommended arm\b/i,
  /\bchoose this option\b/i,
  /\bmatchup advice\b/i,
]

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function hasOwn(value, key) {
  return isObject(value) && Object.prototype.hasOwnProperty.call(value, key)
}

function collectForbiddenFieldPaths(
  value,
  path = [],
  forbiddenFieldKeys = RECOMMENDATION_V2_FORBIDDEN_FIELD_KEYS,
  allowedFieldKeys = new Set(),
) {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => collectForbiddenFieldPaths(
      item,
      [...path, index],
      forbiddenFieldKeys,
      allowedFieldKeys,
    ))
  }
  if (!isObject(value)) return []

  return Object.entries(value).flatMap(([key, child]) => {
    const currentPath = [...path, key]
    const childPaths = collectForbiddenFieldPaths(
      child,
      currentPath,
      forbiddenFieldKeys,
      allowedFieldKeys,
    )
    if (forbiddenFieldKeys.has(key) && !allowedFieldKeys.has(key)) {
      return [currentPath.join('.'), ...childPaths]
    }
    return childPaths
  })
}

function collectForbiddenTextPaths(
  value,
  path = [],
  forbiddenTextTerms = TEAM_OPERATIONS_BULLPEN_READINESS_FORBIDDEN_TEXT_TERMS,
) {
  if (typeof value === 'string') {
    return forbiddenTextTerms.some(term => term.test(value)) ? [path.join('.')] : []
  }

  if (Array.isArray(value)) {
    return value.flatMap((item, index) => collectForbiddenTextPaths(
      item,
      [...path, index],
      forbiddenTextTerms,
    ))
  }

  if (!isObject(value)) return []

  return Object.entries(value).flatMap(([key, child]) => collectForbiddenTextPaths(
    child,
    [...path, key],
    forbiddenTextTerms,
  ))
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

function getTeamOperationsBullpenReadinessMalformedFields(response = {}) {
  if (!isObject(response)) return ['response']

  const fields = []
  const stringFields = [
    'capability',
    'scope',
    'contract',
    'contract_version',
    'contract_state',
    'readiness_status',
    'status_summary',
    'generated_at',
  ]
  const booleanFields = ['ranking_applied', 'selection_made']
  const arrayFields = ['constraints', 'explanations', 'limitations']
  const objectFields = [
    'readiness',
    'workload_pressure',
    'availability_distribution',
    'coverage_inventory',
    'handedness_coverage',
    'trust_metadata',
    'freshness',
    'refusal',
    'fail_closed',
    'route_metadata',
  ]

  for (const field of stringFields) {
    if (hasOwn(response, field) && typeof response[field] !== 'string') {
      fields.push(field)
    }
  }

  for (const field of booleanFields) {
    if (hasOwn(response, field) && typeof response[field] !== 'boolean') {
      fields.push(field)
    }
  }

  for (const field of arrayFields) {
    if (hasOwn(response, field) && !Array.isArray(response[field])) {
      fields.push(field)
    }
  }

  for (const field of objectFields) {
    if (hasOwn(response, field) && !isObject(response[field])) {
      fields.push(field)
    }
  }

  if (isObject(response.trust_metadata)) {
    for (const field of ['ranking_applied', 'selection_made']) {
      if (
        hasOwn(response.trust_metadata, field)
        && typeof response.trust_metadata[field] !== 'boolean'
      ) {
        fields.push(`trust_metadata.${field}`)
      }
    }
  }

  if (isObject(response.fail_closed)) {
    for (const field of [
      'failed_closed',
      'critical_failure',
      'safe_partial_output_allowed',
      'partial_context_safe',
      'ranking_applied',
      'selection_made',
    ]) {
      if (
        hasOwn(response.fail_closed, field)
        && typeof response.fail_closed[field] !== 'boolean'
      ) {
        fields.push(`fail_closed.${field}`)
      }
    }
  }

  if (isObject(response.route_metadata)) {
    for (const field of ['public_certified', 'frontend_exposure']) {
      if (
        hasOwn(response.route_metadata, field)
        && typeof response.route_metadata[field] !== 'boolean'
      ) {
        fields.push(`route_metadata.${field}`)
      }
    }
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
  const { headers, token } = buildRequestHeaders(options)
  const method = String(options.method || 'GET').toUpperCase()
  const dedupeKey = method === 'GET' && !options.body
    ? `${BASE}${path}|auth:${token || ''}`
    : null
  if (dedupeKey && inFlightGetRequests.has(dedupeKey)) {
    return inFlightGetRequests.get(dedupeKey)
  }

  const requestPromise = (async () => {
    try {
      const res = await fetch(`${BASE}${path}`, { ...options, headers })
      if (!res.ok) {
        if (res.status === 401) clearAuthToken()
        const error = new Error(`API ${res.status}: ${res.statusText}`)
        error.status = res.status
        throw error
      }
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

// ── Auth / Identity ────────────────────────────────────────
export const getCurrentUser = () => request('/auth/me')

export const requestMagicLink = (email) => request('/auth/request-link', {
  method: 'POST',
  body: JSON.stringify({ email }),
})

export const verifyMagicLink = async (token) => {
  const response = await request('/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ token }),
    authToken: null,
  })
  storeAuthToken(response?.token)
  return response
}

export const logoutAuth = async () => {
  try {
    return await request('/auth/logout', { method: 'POST' })
  } finally {
    clearAuthToken()
  }
}

// ── User Team Following ────────────────────────────────────
export const getFollowedTeams = () => request('/me/teams')

export const followTeam = (teamId, options = {}) => request('/me/teams', {
  method: 'POST',
  body: JSON.stringify({
    team_id: teamId,
    ...(options.isPrimary === true ? { is_primary: true } : {}),
  }),
})

export const deleteFollowedTeam = (teamId) => request(`/me/teams/${teamId}`, {
  method: 'DELETE',
})

export const setPrimaryTeam = (teamId) => request('/me/primary-team', {
  method: 'PUT',
  body: JSON.stringify({ team_id: teamId }),
})

// ── Health ─────────────────────────────────────────────────
export const checkHealth = () => request('/health')

// ── Bullpen / Fatigue ───────────────────────────────────────
export const getFatigueScores  = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/fatigue${q ? `?${q}` : ''}`)
}
export const getPitcherFatigue = (id) => request(`/bullpen/fatigue/${id}`)
// No frontend helper for POST /bullpen/fatigue/recalculate: fatigue
// recalculation is an admin-token-gated operation, triggered server-side or
// via curl (see docs/current/SETUP.md), never from the browser.

export const getPitchers       = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/pitchers${q ? `?${q}` : ''}`)
}
export const searchPitchers    = (params = {}) => {
  const queryParams = typeof params === 'string' ? { q: params } : params
  return request(`/pitchers/search${buildQuery(queryParams)}`)
}
export const getPitcherLogs    = (id, days = 30) => request(`/bullpen/pitchers/${id}/logs?days=${days}`)

export const getTeams          = () => request('/bullpen/teams')
export const getTeamBullpen    = (teamId, params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/teams/${teamId}/bullpen${q ? `?${q}` : ''}`)
}
// Tonight's Bullpen Board — existing availability classifications grouped for a
// coach-facing read. Presentation only (no ranking/selection).
export const getTeamBullpenBoard = (teamId, params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/teams/${teamId}/board${q ? `?${q}` : ''}`)
}
// Story Intelligence API V1 - one deterministic team bullpen story.
export const getTeamStory = (teamId, params = {}) => {
  return request(`/bullpen/teams/${teamId}/story${buildQuery(params)}`)
}
// What Changed Since Last Game — followed-team change summary.
// Descriptive only (no ranking/selection/recommendation).
export const getTeamChanges = (teamId) => request(`/bullpen/teams/${teamId}/changes`)
// Team Bullpen Comparison — descriptive side-by-side of two team boards.
// Aggregates existing board outputs (no ranking/selection/grading).
export const getTeamBullpenComparison = (teamA, teamB, params = {}) => {
  const q = new URLSearchParams({ team_a: teamA, team_b: teamB, ...params }).toString()
  return request(`/bullpen/teams/compare?${q}`)
}
export const getBullpenOverview = () => request('/bullpen/stats/overview')
// League-wide bullpen landing summary: availability snapshot, Team Context
// health, and usage-role composition. Context only (no ranking/selection).
export const getBullpenDashboard = () => request('/bullpen/dashboard')
// Tonight's Bullpen Landscape — league-wide bullpen context (descriptive only).
export const getBullpenLandscape = () => request('/bullpen/landscape')
// Game context for one team, derived from stored game logs only.
export const getTeamGameContext = (teamId) => request(`/bullpen/teams/${teamId}/game-context`)
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

// ── Team Operations Bullpen Readiness ──────────────────────
export function normalizeTeamOperationsBullpenReadinessResponse(response = {}) {
  const trustMetadata = isObject(response?.trust_metadata) ? response.trust_metadata : null
  const freshness = isObject(response?.freshness) ? response.freshness : null
  const refusal = isObject(response?.refusal) ? response.refusal : null
  const failClosed = isObject(response?.fail_closed) ? response.fail_closed : null
  const routeMetadata = isObject(response?.route_metadata) ? response.route_metadata : null
  const readiness = isObject(response?.readiness) ? response.readiness : null

  const topLevelMissingFields = getMissingFields(
    response,
    TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_TOP_LEVEL_FIELDS,
  )
  const trustMissingFields = trustMetadata
    ? getMissingFields(
      trustMetadata,
      TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_TRUST_FIELDS,
      'trust_metadata.',
    )
    : TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_TRUST_FIELDS
      .map(field => `trust_metadata.${field}`)
  const freshnessMissingFields = freshness
    ? getMissingFields(
      freshness,
      TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_FRESHNESS_FIELDS,
      'freshness.',
    )
    : TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_FRESHNESS_FIELDS
      .map(field => `freshness.${field}`)
  const routeMissingFields = routeMetadata
    ? getMissingFields(
      routeMetadata,
      TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_ROUTE_FIELDS,
      'route_metadata.',
    )
    : TEAM_OPERATIONS_BULLPEN_READINESS_REQUIRED_ROUTE_FIELDS
      .map(field => `route_metadata.${field}`)
  const missingFields = [
    ...topLevelMissingFields,
    ...trustMissingFields,
    ...freshnessMissingFields,
    ...routeMissingFields,
  ]
  const malformedFields = getTeamOperationsBullpenReadinessMalformedFields(response)
  const forbiddenFieldPaths = collectForbiddenFieldPaths(
    response,
    [],
    TEAM_OPERATIONS_BULLPEN_READINESS_FORBIDDEN_FIELD_KEYS,
    TEAM_OPERATIONS_BULLPEN_READINESS_GOVERNANCE_FIELD_EXCEPTIONS,
  )
  const forbiddenTextPaths = collectForbiddenTextPaths(response)

  const sourceContractState = typeof response?.contract_state === 'string'
    ? response.contract_state
    : null
  const readinessStatus = typeof response?.readiness_status === 'string'
    ? response.readiness_status
    : (typeof readiness?.status_code === 'string' ? readiness.status_code : null)
  const unknownContractState = (
    sourceContractState
    && !TEAM_OPERATIONS_BULLPEN_READINESS_ALLOWED_CONTRACT_STATES.has(sourceContractState)
  ) ? sourceContractState : null
  const unknownReadinessStatus = (
    readinessStatus
    && !TEAM_OPERATIONS_BULLPEN_READINESS_ALLOWED_STATUSES.has(readinessStatus)
  ) ? readinessStatus : null

  const routeStatus = {
    route: routeMetadata?.route ?? null,
    surface: routeMetadata?.surface ?? null,
    exposure: routeMetadata?.exposure ?? null,
    productionStatus: routeMetadata?.production_status ?? null,
    certificationStatus: routeMetadata?.certification_status ?? null,
    publicCertified: routeMetadata?.public_certified ?? null,
    frontendExposure: routeMetadata?.frontend_exposure ?? null,
  }
  const isInternalUncertified = (
    routeStatus.exposure === 'internal'
    && routeStatus.productionStatus === 'non_production'
    && routeStatus.certificationStatus === 'uncertified'
    && routeStatus.publicCertified === false
    && routeStatus.frontendExposure === false
  )

  const governance = {
    rankingApplied: response?.ranking_applied,
    selectionMade: response?.selection_made,
    trustRankingApplied: trustMetadata?.ranking_applied,
    trustSelectionMade: trustMetadata?.selection_made,
    failClosedRankingApplied: failClosed?.ranking_applied,
    failClosedSelectionMade: failClosed?.selection_made,
    rankingAppliedIsFalse: response?.ranking_applied === false,
    selectionMadeIsFalse: response?.selection_made === false,
  }
  const governanceSafe = (
    governance.rankingApplied === false
    && governance.selectionMade === false
    && governance.trustRankingApplied === false
    && governance.trustSelectionMade === false
    && (
      !hasOwn(failClosed, 'ranking_applied')
      || governance.failClosedRankingApplied === false
    )
    && (
      !hasOwn(failClosed, 'selection_made')
      || governance.failClosedSelectionMade === false
    )
  )
  const isFailClosed = Boolean(
    failClosed
    && (
      failClosed.failed_closed === true
      || failClosed.critical_failure === true
      || failClosed.governance_state === 'failed_closed'
      || failClosed.state === 'refused'
      || failClosed.state === 'failed_closed'
    ),
  )
  const sourceRefused = sourceContractState === 'refused' || refusal?.refused === true
  const sourceDegraded = sourceContractState === 'degraded'
  const isContractSafe = (
    governanceSafe
    && isInternalUncertified
    && missingFields.length === 0
    && malformedFields.length === 0
    && forbiddenFieldPaths.length === 0
    && forbiddenTextPaths.length === 0
    && !unknownContractState
    && !unknownReadinessStatus
  )
  const contractState = isContractSafe
    ? (sourceRefused || isFailClosed ? 'refused' : (sourceDegraded ? 'degraded' : 'available'))
    : 'unavailable'

  return {
    endpoint: TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE,
    contractState,
    sourceContractState,
    isContractSafe,
    isDegraded: contractState === 'degraded',
    isRefused: contractState === 'refused',
    isFailClosed,
    isInternal: routeStatus.exposure === 'internal',
    isInternalUncertified,
    governance,
    governanceSafe,
    routeStatus,
    missingFields,
    malformedFields,
    forbiddenFieldPaths,
    forbiddenTextPaths,
    unknownContractState,
    unknownReadinessStatus,
    capability: typeof response?.capability === 'string' ? response.capability : null,
    scope: typeof response?.scope === 'string' ? response.scope : null,
    contract: typeof response?.contract === 'string' ? response.contract : null,
    contractVersion: typeof response?.contract_version === 'string'
      ? response.contract_version
      : null,
    readinessStatus,
    readinessSummary: typeof response?.status_summary === 'string'
      ? response.status_summary
      : (typeof readiness?.summary === 'string' ? readiness.summary : null),
    readiness,
    team: isObject(response?.team) ? response.team : null,
    generatedAt: typeof response?.generated_at === 'string' ? response.generated_at : null,
    constraints: Array.isArray(response?.constraints) ? response.constraints : [],
    workloadPressure: isObject(response?.workload_pressure)
      ? response.workload_pressure
      : null,
    availabilityDistribution: isObject(response?.availability_distribution)
      ? response.availability_distribution
      : null,
    coverageInventory: isObject(response?.coverage_inventory)
      ? response.coverage_inventory
      : null,
    handednessCoverage: isObject(response?.handedness_coverage)
      ? response.handedness_coverage
      : null,
    explanations: Array.isArray(response?.explanations) ? response.explanations : [],
    limitations: Array.isArray(response?.limitations) ? response.limitations : [],
    trustMetadata,
    freshness,
    refusal,
    failClosed,
    routeMetadata,
  }
}

export const getTeamOperationsBullpenReadiness = async (params = {}) => {
  const response = await request(`${TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE}${buildQuery(params)}`)
  return normalizeTeamOperationsBullpenReadinessResponse(response)
}

// ── V5 Bullpen Intelligence Observations ───────────────────
function getBullpenObservationMalformedFields(response = {}) {
  if (!isObject(response)) return ['response']

  const fields = []
  const stringFields = [
    'status',
    'collection_id',
    'generated_at',
    'trust_status',
  ]
  const booleanFields = ['ranking_applied', 'selection_made']
  const arrayFields = [
    'observations',
    'limitations',
    'suppression_reasons',
  ]
  const objectFields = [
    'freshness',
    'confidence',
    'route_metadata',
  ]

  for (const field of stringFields) {
    if (hasOwn(response, field) && typeof response[field] !== 'string') {
      fields.push(field)
    }
  }
  for (const field of booleanFields) {
    if (hasOwn(response, field) && typeof response[field] !== 'boolean') {
      fields.push(field)
    }
  }
  for (const field of arrayFields) {
    if (hasOwn(response, field) && !Array.isArray(response[field])) {
      fields.push(field)
    }
  }
  for (const field of objectFields) {
    if (hasOwn(response, field) && !isObject(response[field])) {
      fields.push(field)
    }
  }
  if (
    hasOwn(response, 'observation_count')
    && typeof response.observation_count !== 'number'
  ) {
    fields.push('observation_count')
  }
  if (
    hasOwn(response, 'suppressed_count')
    && typeof response.suppressed_count !== 'number'
  ) {
    fields.push('suppressed_count')
  }

  const observations = Array.isArray(response?.observations)
    ? response.observations
    : []
  observations.forEach((observation, index) => {
    if (!isObject(observation)) {
      fields.push(`observations.${index}`)
      return
    }

    for (const field of [
      'observation_id',
      'observation_type',
      'family',
      'severity',
      'title',
      'summary',
      'trust_status',
    ]) {
      if (hasOwn(observation, field) && typeof observation[field] !== 'string') {
        fields.push(`observations.${index}.${field}`)
      }
    }
    for (const field of ['ranking_applied', 'selection_made']) {
      if (hasOwn(observation, field) && typeof observation[field] !== 'boolean') {
        fields.push(`observations.${index}.${field}`)
      }
    }
    for (const field of ['evidence', 'limitations']) {
      if (hasOwn(observation, field) && !Array.isArray(observation[field])) {
        fields.push(`observations.${index}.${field}`)
      }
    }
    for (const field of ['confidence', 'freshness']) {
      if (hasOwn(observation, field) && !isObject(observation[field])) {
        fields.push(`observations.${index}.${field}`)
      }
    }
    if (
      hasOwn(observation, 'explanation_reference')
      && observation.explanation_reference !== null
      && typeof observation.explanation_reference !== 'string'
    ) {
      fields.push(`observations.${index}.explanation_reference`)
    }
  })

  return fields
}

function collectGovernanceFlagValues(value) {
  if (Array.isArray(value)) {
    return value.flatMap(item => collectGovernanceFlagValues(item))
  }
  if (!isObject(value)) return []

  return Object.entries(value).flatMap(([key, child]) => {
    const childValues = collectGovernanceFlagValues(child)
    if (key === 'ranking_applied' || key === 'selection_made') {
      return [child, ...childValues]
    }
    return childValues
  })
}

export function normalizeBullpenObservationsResponse(response = {}) {
  const observations = Array.isArray(response?.observations)
    ? response.observations
    : []
  const topLevelMissingFields = getMissingFields(
    response,
    OBSERVATION_RESPONSE_REQUIRED_FIELDS,
  )
  const observationMissingFields = observations.flatMap((observation, index) => (
    getMissingFields(
      observation,
      OBSERVATION_ITEM_REQUIRED_FIELDS,
      `observations.${index}.`,
    )
  ))
  const missingFields = [...topLevelMissingFields, ...observationMissingFields]
  const malformedFields = getBullpenObservationMalformedFields(response)
  const forbiddenFieldPaths = collectForbiddenFieldPaths(
    response,
    [],
    OBSERVATION_FORBIDDEN_FIELD_KEYS,
    OBSERVATION_GOVERNANCE_FIELD_EXCEPTIONS,
  )
  const forbiddenTextPaths = collectForbiddenTextPaths(
    response,
    [],
    OBSERVATION_FORBIDDEN_TEXT_TERMS,
  )
  const governanceFlagValues = collectGovernanceFlagValues(response)
  const governanceSafe = (
    response?.ranking_applied === false
    && response?.selection_made === false
    && governanceFlagValues.every(value => value === false)
  )
  const isContractSafe = (
    governanceSafe
    && missingFields.length === 0
    && malformedFields.length === 0
    && forbiddenFieldPaths.length === 0
    && forbiddenTextPaths.length === 0
  )
  const isFailClosed = Boolean(
    response?.status === 'fail_closed'
    || response?.trust_status === 'fail_closed'
    || (
      response?.suppressed_count > 0
      && observations.length === 0
    ),
  )
  const isEmpty = observations.length === 0
  const contractState = isContractSafe
    ? (isFailClosed ? 'fail_closed' : (isEmpty ? 'empty' : 'available'))
    : 'unavailable'

  return {
    endpoint: BULLPEN_INTELLIGENCE_OBSERVATIONS_ROUTE,
    contractState,
    isContractSafe,
    isFailClosed,
    isEmpty,
    governanceSafe,
    governance: {
      rankingApplied: response?.ranking_applied,
      selectionMade: response?.selection_made,
      rankingAppliedIsFalse: response?.ranking_applied === false,
      selectionMadeIsFalse: response?.selection_made === false,
    },
    missingFields,
    malformedFields,
    forbiddenFieldPaths,
    forbiddenTextPaths,
    status: typeof response?.status === 'string' ? response.status : null,
    collectionId: typeof response?.collection_id === 'string'
      ? response.collection_id
      : null,
    observationCount: typeof response?.observation_count === 'number'
      ? response.observation_count
      : observations.length,
    observations: isContractSafe ? observations : [],
    freshness: isObject(response?.freshness) ? response.freshness : null,
    confidence: isObject(response?.confidence) ? response.confidence : null,
    limitations: Array.isArray(response?.limitations) && isContractSafe
      ? response.limitations
      : [],
    trustStatus: typeof response?.trust_status === 'string'
      ? response.trust_status
      : null,
    generatedAt: typeof response?.generated_at === 'string'
      ? response.generated_at
      : null,
    suppressedCount: typeof response?.suppressed_count === 'number'
      ? response.suppressed_count
      : 0,
    suppressionReasons: Array.isArray(response?.suppression_reasons)
      ? response.suppression_reasons
      : [],
    routeMetadata: isObject(response?.route_metadata) ? response.route_metadata : null,
  }
}

export const getBullpenObservations = async () => {
  const response = await request(BULLPEN_INTELLIGENCE_OBSERVATIONS_ROUTE)
  return normalizeBullpenObservationsResponse(response)
}

// ── Governed Explanations ──────────────────────────────────
function v4GovernanceDefaults() {
  return {
    ranking_applied: false,
    selection_made: false,
    recommendation_made: false,
    prediction_made: false,
    decision_scope: 'explanation_only',
    advice_scope: 'none',
  }
}

function isV4GovernanceSafe(governance = null) {
  return (
    isObject(governance)
    && governance.ranking_applied === false
    && governance.selection_made === false
    && governance.recommendation_made === false
    && governance.prediction_made === false
    && governance.decision_scope === 'explanation_only'
    && governance.advice_scope === 'none'
  )
}

function getV4ExplanationMalformedFields(response = {}) {
  if (!isObject(response)) return ['response']

  const fields = []
  const status = response.status
  const explanation = isObject(response.explanation) ? response.explanation : null

  for (const field of ['status', 'explanation_type', 'certification_status', 'route_status']) {
    if (hasOwn(response, field) && typeof response[field] !== 'string') {
      fields.push(field)
    }
  }

  if (hasOwn(response, 'governance') && !isObject(response.governance)) {
    fields.push('governance')
  }
  if (hasOwn(response, 'limitations') && !Array.isArray(response.limitations)) {
    fields.push('limitations')
  }
  if (hasOwn(response, 'refusal') && !isObject(response.refusal)) {
    fields.push('refusal')
  }
  if (status === 'ok' && !isObject(response.explanation)) {
    fields.push('explanation')
  }
  if (status === 'unavailable' && response.explanation !== null) {
    fields.push('explanation')
  }

  if (explanation) {
    for (const field of [
      'explanation_id',
      'scope',
      'subject_type',
      'subject_id',
      'state_explained',
      'summary',
    ]) {
      if (hasOwn(explanation, field) && typeof explanation[field] !== 'string') {
        fields.push(`explanation.${field}`)
      }
    }

    for (const field of ['primary_reasons', 'supporting_evidence', 'limitations']) {
      if (hasOwn(explanation, field) && !Array.isArray(explanation[field])) {
        fields.push(`explanation.${field}`)
      }
    }

    for (const field of ['freshness', 'trust', 'confidence', 'governance']) {
      if (hasOwn(explanation, field) && !isObject(explanation[field])) {
        fields.push(`explanation.${field}`)
      }
    }
  }

  for (const [path, governance] of [
    ['governance', response.governance],
    ['explanation.governance', explanation?.governance],
  ]) {
    if (!isObject(governance)) continue
    for (const field of V4_EXPLANATION_REQUIRED_GOVERNANCE_FIELDS) {
      if (!hasOwn(governance, field)) continue
      const value = governance[field]
      if (
        ['ranking_applied', 'selection_made', 'recommendation_made', 'prediction_made']
          .includes(field)
        && typeof value !== 'boolean'
      ) {
        fields.push(`${path}.${field}`)
      }
      if (
        ['decision_scope', 'advice_scope'].includes(field)
        && typeof value !== 'string'
      ) {
        fields.push(`${path}.${field}`)
      }
    }
  }

  return fields
}

function buildClientFailClosedExplanationEnvelope({
  explanationType,
  reasonCode,
  summary,
  limitationType = 'uncertified_source',
  certificationStatus = 'certified_with_non_blocking_observations',
}) {
  return {
    status: 'unavailable',
    explanation_type: explanationType,
    certification_status: certificationStatus,
    route_status: 'client_guarded_unavailable',
    explanation: null,
    limitations: [
      {
        limitation_type: limitationType,
        label: 'Explanation unavailable',
        summary,
      },
    ],
    refusal: {
      refused: true,
      reason_code: reasonCode,
      summary,
    },
    governance: v4GovernanceDefaults(),
  }
}

export function normalizeV4ExplanationApiResponse(response = {}) {
  const status = typeof response?.status === 'string' ? response.status : null
  const explanationType = typeof response?.explanation_type === 'string'
    ? response.explanation_type
    : null
  const explanation = isObject(response?.explanation) ? response.explanation : null
  const envelopeGovernance = isObject(response?.governance) ? response.governance : null
  const explanationGovernance = isObject(explanation?.governance)
    ? explanation.governance
    : null
  const successMissingFields = status === 'ok'
    ? [
      ...getMissingFields(response, V4_EXPLANATION_REQUIRED_SUCCESS_ENVELOPE_FIELDS),
      ...getMissingFields(explanation, V4_EXPLANATION_REQUIRED_EXPLANATION_FIELDS, 'explanation.'),
      ...getMissingFields(envelopeGovernance, V4_EXPLANATION_REQUIRED_GOVERNANCE_FIELDS, 'governance.'),
      ...getMissingFields(explanationGovernance, V4_EXPLANATION_REQUIRED_GOVERNANCE_FIELDS, 'explanation.governance.'),
    ]
    : []
  const unavailableMissingFields = status === 'unavailable'
    ? [
      ...getMissingFields(response, V4_EXPLANATION_REQUIRED_UNAVAILABLE_ENVELOPE_FIELDS),
      ...getMissingFields(envelopeGovernance, V4_EXPLANATION_REQUIRED_GOVERNANCE_FIELDS, 'governance.'),
    ]
    : []
  const missingFields = status === 'ok'
    ? successMissingFields
    : (status === 'unavailable' ? unavailableMissingFields : ['status'])
  const malformedFields = getV4ExplanationMalformedFields(response)
  const forbiddenFieldPaths = collectForbiddenFieldPaths(
    response,
    [],
    V4_EXPLANATION_FORBIDDEN_FIELD_KEYS,
    V4_EXPLANATION_GOVERNANCE_FIELD_EXCEPTIONS,
  )
  const forbiddenTextPaths = collectForbiddenTextPaths(
    response,
    [],
    V4_EXPLANATION_FORBIDDEN_TEXT_TERMS,
  )

  const isCertifiedType = CERTIFIED_EXPLANATION_TYPES.has(explanationType)
  const isUnsupportedScope = Boolean(
    explanationType === 'team_readiness_explanation'
    && explanation
    && !CERTIFIED_TEAM_READINESS_EXPLANATION_SCOPES.has(explanation.scope),
  )
  const governanceSafe = (
    isV4GovernanceSafe(envelopeGovernance)
    && (
      !explanation
      || isV4GovernanceSafe(explanationGovernance)
    )
  )
  const hasStableStatus = status === 'ok' || status === 'unavailable'
  const isContractSafe = (
    hasStableStatus
    && governanceSafe
    && isCertifiedType
    && !isUnsupportedScope
    && missingFields.length === 0
    && malformedFields.length === 0
    && forbiddenFieldPaths.length === 0
    && forbiddenTextPaths.length === 0
  )
  const isFailClosed = status === 'unavailable'
  const contractState = isContractSafe
    ? (isFailClosed ? 'unavailable' : 'available')
    : 'unavailable'
  const limitations = explanation
    ? (Array.isArray(explanation.limitations) ? explanation.limitations : [])
    : (Array.isArray(response?.limitations) ? response.limitations : [])

  return {
    endpoint: explanationType,
    contractState,
    status,
    explanationType,
    certificationStatus: typeof response?.certification_status === 'string'
      ? response.certification_status
      : null,
    routeStatus: typeof response?.route_status === 'string'
      ? response.route_status
      : null,
    isContractSafe,
    isFailClosed,
    isCertifiedType,
    isInternalUncertified: response?.route_status === 'internal_uncertified_route',
    governanceSafe,
    governance: {
      rankingApplied: envelopeGovernance?.ranking_applied,
      selectionMade: envelopeGovernance?.selection_made,
      recommendationMade: envelopeGovernance?.recommendation_made,
      predictionMade: envelopeGovernance?.prediction_made,
      decisionScope: envelopeGovernance?.decision_scope,
      adviceScope: envelopeGovernance?.advice_scope,
      rankingAppliedIsFalse: envelopeGovernance?.ranking_applied === false,
      selectionMadeIsFalse: envelopeGovernance?.selection_made === false,
      recommendationMadeIsFalse: envelopeGovernance?.recommendation_made === false,
      predictionMadeIsFalse: envelopeGovernance?.prediction_made === false,
    },
    missingFields,
    malformedFields,
    forbiddenFieldPaths,
    forbiddenTextPaths,
    isUnsupportedScope,
    explanation: isContractSafe && explanation ? explanation : null,
    summary: isContractSafe && explanation ? explanation.summary : null,
    stateExplained: isContractSafe && explanation ? explanation.state_explained : null,
    scope: isContractSafe && explanation ? explanation.scope : null,
    subjectType: isContractSafe && explanation ? explanation.subject_type : null,
    subjectId: isContractSafe && explanation ? explanation.subject_id : null,
    primaryReasons: isContractSafe && explanation && Array.isArray(explanation.primary_reasons)
      ? explanation.primary_reasons
      : [],
    supportingEvidence: isContractSafe && explanation && Array.isArray(explanation.supporting_evidence)
      ? explanation.supporting_evidence
      : [],
    limitations,
    freshness: isContractSafe && isObject(explanation?.freshness) ? explanation.freshness : null,
    trust: isContractSafe && isObject(explanation?.trust) ? explanation.trust : null,
    confidence: isContractSafe && isObject(explanation?.confidence) ? explanation.confidence : null,
    refusal: isObject(response?.refusal) ? response.refusal : null,
    generatedAt: isContractSafe && typeof explanation?.generated_at === 'string'
      ? explanation.generated_at
      : null,
  }
}

export const getAvailabilityExplanation = async (pitcherId) => {
  if (pitcherId === undefined || pitcherId === null || pitcherId === '') {
    return normalizeV4ExplanationApiResponse(buildClientFailClosedExplanationEnvelope({
      explanationType: 'availability_explanation',
      reasonCode: 'missing_subject',
      summary: 'Availability explanation cannot be requested without a pitcher identifier.',
      limitationType: 'missing_data',
    }))
  }

  const response = await request(`${EXPLANATION_AVAILABILITY_ROUTE_PREFIX}/${encodeURIComponent(pitcherId)}`)
  return normalizeV4ExplanationApiResponse(response)
}

export const getTeamReadinessExplanation = async (params = {}) => {
  const { scope = 'readiness_state', ...queryParams } = params || {}
  const normalizedScope = scope || 'readiness_state'
  if (!CERTIFIED_TEAM_READINESS_EXPLANATION_SCOPES.has(normalizedScope)) {
    return normalizeV4ExplanationApiResponse(buildClientFailClosedExplanationEnvelope({
      explanationType: 'team_readiness_explanation',
      reasonCode: 'unsupported_scope',
      summary: 'The requested readiness explanation scope is not available for frontend exposure.',
      limitationType: 'uncertified_source',
    }))
  }

  const route = normalizedScope === 'readiness_state'
    ? EXPLANATION_TEAM_READINESS_ROUTE
    : `${EXPLANATION_TEAM_READINESS_ROUTE}/${encodeURIComponent(normalizedScope)}`
  const response = await request(`${route}${buildQuery({
    team_id: queryParams.team_id,
    team_abbreviation: queryParams.team_abbreviation,
  })}`)
  return normalizeV4ExplanationApiResponse(response)
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
export const getAvailabilityBacktest = () => request('/methodology/availability-backtest')
