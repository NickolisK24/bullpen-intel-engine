const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : '/api'

export const PRODUCT_INTELLIGENCE_ADMIN_ROUTE = '/system/product-events'
export const PRODUCT_INTELLIGENCE_HEARTBEAT_ROUTE = '/system/product-event-heartbeat'
export const ADMIN_PRODUCT_EVENTS_PATH = '/admin/product-intelligence'
export const ADMIN_TOKEN_HEADER = 'X-Admin-Token'

export const PRODUCT_INTELLIGENCE_EVENT_NAMES = [
  'today_loaded',
  'story_viewed',
  'signed_in',
  'followed_team_changed',
  'digest_generated',
  'digest_suppressed',
  'digest_sent',
  'digest_opened',
  'digest_clicked',
  'digest_returned',
  'digest_unsubscribed',
  'digest_reenabled',
]

function cleanText(value) {
  return value == null ? '' : String(value).trim()
}

export function normalizeProductEventsLimit(value, fallback = 25) {
  const numeric = Number.parseInt(value, 10)
  if (!Number.isFinite(numeric)) return fallback
  return Math.max(1, Math.min(100, numeric))
}

export function buildProductEventsQuery({ eventName = '', limit = 25 } = {}) {
  const params = new URLSearchParams()
  const cleanEventName = cleanText(eventName)
  if (cleanEventName) params.set('event_name', cleanEventName)
  params.set('limit', String(normalizeProductEventsLimit(limit)))
  return params.toString()
}

export async function fetchProductIntelligenceEvents({
  adminToken = '',
  eventName = '',
  limit = 25,
  fetchImpl = fetch,
} = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = cleanText(adminToken)
  if (token) headers[ADMIN_TOKEN_HEADER] = token

  const query = buildProductEventsQuery({ eventName, limit })
  const response = await fetchImpl(`${API_BASE}${PRODUCT_INTELLIGENCE_ADMIN_ROUTE}?${query}`, {
    method: 'GET',
    headers,
  })
  if (!response.ok) {
    const message = response.status === 401
      ? 'Admin token required.'
      : `Product Intelligence events request failed with ${response.status}.`
    throw new Error(message)
  }
  return response.json()
}

export async function fetchProductIntelligenceHeartbeat({
  adminToken = '',
  fetchImpl = fetch,
} = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = cleanText(adminToken)
  if (token) headers[ADMIN_TOKEN_HEADER] = token

  const response = await fetchImpl(`${API_BASE}${PRODUCT_INTELLIGENCE_HEARTBEAT_ROUTE}`, {
    method: 'GET',
    headers,
  })
  if (!response.ok) {
    const message = response.status === 401
      ? 'Admin token required.'
      : `Product Intelligence heartbeat request failed with ${response.status}.`
    throw new Error(message)
  }
  return response.json()
}
