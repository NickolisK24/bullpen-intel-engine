import {
  BULLPEN_OBSERVATIONS_ROUTE,
  OBSERVATION_FORBIDDEN_FIELD_KEYS,
  OBSERVATION_FORBIDDEN_TEXT_TERMS,
  OBSERVATION_GOVERNANCE_FIELD_EXCEPTIONS,
  OBSERVATION_ITEM_REQUIRED_FIELDS,
  OBSERVATION_RESPONSE_REQUIRED_FIELDS,
} from '../types/observations'
import { getOrCreateProductAnonId } from './productIdentity'

const BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : '/api'
const TONIGHT_INTELLIGENCE_TIMEOUT_MS = 12000

export const AUTH_TOKEN_STORAGE_KEY = 'baseballos.authToken'
export const AUTH_TOKEN_CHANGED_EVENT = 'baseballos:auth-token-changed'

// Privileged operational endpoints (sync / recalculate) are gated by the
// backend ADMIN_API_TOKEN via the X-Admin-Token header. The frontend never
// holds or sends that token: trigger those endpoints server-side or with curl
// so the admin secret can never be baked into the public browser bundle.
export const RECOMMENDATION_CANDIDATE_ROUTE = '/recommendations/candidate'
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
  forbiddenFieldKeys,
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
  forbiddenTextTerms,
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
  const {
    silent = false,
    authToken: _authToken,
    timeoutMs = 0,
    ...fetchOptions
  } = options
  const { headers, token } = buildRequestHeaders(options)
  const method = String(options.method || 'GET').toUpperCase()
  const dedupeKey = method === 'GET' && !options.body
    ? `${BASE}${path}|auth:${token || ''}`
    : null
  if (dedupeKey && inFlightGetRequests.has(dedupeKey)) {
    return inFlightGetRequests.get(dedupeKey)
  }

  const requestPromise = (async () => {
    const timeoutDuration = Number(timeoutMs)
    const shouldTimeout = Number.isFinite(timeoutDuration)
      && timeoutDuration > 0
      && typeof AbortController !== 'undefined'
      && !fetchOptions.signal
    const controller = shouldTimeout ? new AbortController() : null
    const requestOptions = controller
      ? { ...fetchOptions, signal: controller.signal }
      : fetchOptions
    let timeoutId = null
    try {
      if (controller) {
        timeoutId = setTimeout(() => controller.abort(), timeoutDuration)
      }
      const res = await fetch(`${BASE}${path}`, { ...requestOptions, headers })
      if (!res.ok) {
        if (res.status === 401) clearAuthToken()
        const error = new Error(`API ${res.status}: ${res.statusText}`)
        error.status = res.status
        throw error
      }
      return await res.json()
    } catch (err) {
      const requestError = controller && err?.name === 'AbortError'
        ? Object.assign(
          new Error(`API request timed out after ${timeoutDuration}ms`),
          { status: 'timeout' },
        )
        : err
      if (!silent) console.error(`[API] ${path}`, requestError)
      throw requestError
    } finally {
      if (timeoutId) clearTimeout(timeoutId)
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

function payloadWithProductAnonId(payload = {}) {
  const anonId = payload.anon_id === undefined
    ? getOrCreateProductAnonId()
    : payload.anon_id
  return {
    ...payload,
    ...(anonId ? { anon_id: anonId } : {}),
  }
}

export const verifyMagicLink = async (token, options = {}) => {
  const response = await request('/auth/verify', {
    method: 'POST',
    body: JSON.stringify(payloadWithProductAnonId({
      token,
      ...(options.anonId === undefined ? {} : { anon_id: options.anonId }),
    })),
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

// ── Product Intelligence ───────────────────────────────────
export const recordTodayLoaded = (payload = {}) => request('/product/today-loaded', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId(payload)),
  silent: true,
})

export const recordStoryViewed = (payload = {}) => request('/product/story-viewed', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId(payload)),
  silent: true,
})

export const recordStoryInteracted = (payload = {}) => request('/product/story-interacted', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId(payload)),
  silent: true,
})

// V3-1: story_impression posts through the owned generic story-event endpoint.
// event_name is fixed here so the client can only ever emit the allowlisted name.
export const recordStoryImpression = (payload = {}) => request('/product/story-event', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId({ ...payload, event_name: 'story_impression' })),
  silent: true,
})

// V3-2: story_team_board_opened posts through the same owned story-event endpoint.
// Fires once per physical click (not deduped) — each Team Board open is a signal.
export const recordStoryTeamBoardOpened = (payload = {}) => request('/product/story-event', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId({ ...payload, event_name: 'story_team_board_opened' })),
  silent: true,
})

// V3-3: story_share_clicked posts through the same owned story-event endpoint.
// Fired on Share click intent (not native-share / copy success); per-click, not deduped.
export const recordStoryShareClicked = (payload = {}) => request('/product/story-event', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId({ ...payload, event_name: 'story_share_clicked' })),
  silent: true,
})

// V4.0: generic owned product-loop observations. Event names are centralized in
// utils/analytics.js; this seam only posts the already-normalized payload.
export const recordProductEvent = (payload = {}) => request('/product/event', {
  method: 'POST',
  body: JSON.stringify(payloadWithProductAnonId(payload)),
  silent: true,
})

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
export const getPitcherRecentWork = (id) => request(`/bullpen/pitchers/${encodeURIComponent(id)}/recent-work`)

export const getTeams          = () => request('/bullpen/teams')
export const getTeamReliefWork = (teamId) => request(`/bullpen/teams/${encodeURIComponent(teamId)}/relief-work`)
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
export const getPrivatePostsDashboard = () => request('/private-posts/dashboard')
// Tonight's Bullpen Landscape — league-wide bullpen context (descriptive only).
export const getBullpenLandscape = () => request('/bullpen/landscape')
// Intelligence Surface — the single league lead story for the homepage.
export const getTodayIntelligence = (params = {}) => (
  request(`/bullpen/intelligence/today${buildQuery(params)}`)
)
// Intelligence Surface — pregame bullpen cards for the homepage Tonight rail.
export const getTonightIntelligence = (params = {}, options = {}) => (
  request(`/bullpen/intelligence/tonight${buildQuery(params)}`, {
    timeoutMs: TONIGHT_INTELLIGENCE_TIMEOUT_MS,
    ...options,
  })
)
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

// ── Methodology ───────────────────────────────────────────────
export const getMethodology = () => request('/methodology/')
export const getAvailabilityBacktest = () => request('/methodology/availability-backtest')
