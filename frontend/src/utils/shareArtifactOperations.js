import { readAuthToken } from './api'

// Internal operator route (kept out of public navigation and sitemap; see the
// page's robots noindex meta). Not a public path.
export const SHARE_ARTIFACT_OPERATIONS_PATH = '/internal/share-artifacts/operations'

// Browser-safe authenticated read boundary (SC-03B-03B). This never sends the
// privileged admin secret — it carries only the signed-in user's Bearer session,
// exactly like the existing internal Traffic surface.
const OPERATIONS_RESOURCE = 'internal-browser/share-artifacts/operations'

export const OPERATIONS_LIST_LIMIT = 25

function operationsUrl(resource, params, configuredBackendOrigin) {
  const apiBase = configuredBackendOrigin ? `${configuredBackendOrigin}/api` : '/api'
  const query = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      query.set(key, String(value))
    }
  })
  const suffix = query.toString()
  return `${apiBase}/${OPERATIONS_RESOURCE}/${resource}${suffix ? `?${suffix}` : ''}`
}

async function getOperations(resource, params, {
  fetchImpl = globalThis.fetch,
  authToken = readAuthToken(),
  configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL,
} = {}) {
  const headers = { 'Content-Type': 'application/json' }
  // Only the user's own Bearer session is attached — never an admin token.
  if (authToken) headers.Authorization = `Bearer ${authToken}`

  const response = await fetchImpl(
    operationsUrl(resource, params, configuredBackendOrigin),
    { method: 'GET', headers },
  )
  if (!response.ok) {
    const error = new Error(`Share artifact operations request failed with ${response.status}`)
    error.status = response.status
    throw error
  }
  return response.json()
}

export function fetchOperationsOverview(options = {}) {
  return getOperations('overview', {}, options)
}

export function fetchOperationsArtifacts(params = {}, options = {}) {
  return getOperations('artifacts', params, options)
}

export function fetchOperationsAudits(params = {}, options = {}) {
  return getOperations('audits', params, options)
}

// --- Presentation vocabulary (backend-authoritative; text, never color alone) ---

export const OPERATIONAL_STATUS_LABELS = Object.freeze({
  complete: 'Complete',
  complete_with_refusals: 'Complete — with refusals',
  degraded: 'Degraded',
  incomplete: 'Incomplete',
  disabled: 'Automatic generation disabled',
  unavailable: 'Unavailable',
})

export function operationalStatusLabel(status) {
  return OPERATIONAL_STATUS_LABELS[status] || 'Unknown'
}

export const COVERAGE_STATE_LABELS = Object.freeze({
  generated: 'Generated',
  reused: 'Reused',
  refused: 'Refused',
  failed: 'Failed',
  missing: 'Missing',
})

export function coverageStateLabel(state) {
  return COVERAGE_STATE_LABELS[state] || state || 'Unknown'
}

export const INTEGRITY_STATE_LABELS = Object.freeze({
  verified: 'Verified',
  mismatch: 'Integrity mismatch',
  error: 'Verification error',
  not_applicable: '—',
})

export function integrityStateLabel(state) {
  return INTEGRITY_STATE_LABELS[state] || state || '—'
}
