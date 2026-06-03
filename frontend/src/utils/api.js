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
export const TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE =
  '/team-operations/bullpen-readiness'
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
