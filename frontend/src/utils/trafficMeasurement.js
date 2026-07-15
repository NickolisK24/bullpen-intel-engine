import { readAuthToken } from './api'
import {
  BULLPEN_VIEWS,
  EVIDENCE_SECTIONS,
  normalizeBullpenSource,
  normalizeTeamReference,
} from './evidenceLinks'

export const TRAFFIC_VISITOR_STORAGE_KEY = 'baseballos.traffic.visitor.v1'
export const TRAFFIC_SESSION_STORAGE_KEY = 'baseballos.traffic.session.v1'
export const TRAFFIC_SESSION_TIMEOUT_MS = 30 * 60 * 1000
export const TRAFFIC_CANONICAL_HOST = 'baseballos.app'

const STATIC_ROUTES = Object.freeze({
  '/': 'today',
  '/dashboard': 'dashboard',
  '/stories': 'stories',
  '/about': 'about',
  '/how-to-read': 'how_to_read',
  '/methodology': 'methodology',
  '/trust': 'data_trust',
  '/signin': 'sign_in',
  '/auth/verify': 'auth_verify',
})
const BULLPEN_SURFACES = Object.freeze({
  board: 'bullpen_board',
  compare: 'compare_bullpens',
  pitchers: 'all_pitchers',
})
const UTM_LIMITS = Object.freeze({
  utm_source: 64,
  utm_medium: 64,
  utm_campaign: 128,
  utm_content: 128,
})
const SENSITIVE_UTM_PATTERNS = Object.freeze([
  /[^\s@]+@[^\s@]+\.[^\s@]+/i,
  /[\r\n]/,
  /(?:^|[^a-z0-9])(?:bearer|basic|authorization|token|secret|password|passwd|api[\s_.-]*key|access[\s_.-]*token|refresh[\s_.-]*token|id[\s_.-]*token|client[\s_.-]*secret)(?![a-z0-9])/i,
  /(?:^|[^A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])/,
  /(?:^|[^a-z0-9])(?:sk|rk|pk)[-_][a-z0-9_-]{12,}(?![a-z0-9])/i,
  /(?:^|[^A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])/,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/i,
])
let lastObservedEntry = null

function uuid(cryptoObject = globalThis.crypto) {
  if (!cryptoObject || typeof cryptoObject.randomUUID !== 'function') return null
  return cryptoObject.randomUUID()
}

function safeGet(storage, key) {
  try {
    return storage?.getItem(key) || null
  } catch {
    return null
  }
}

function safeSet(storage, key, value) {
  try {
    storage?.setItem(key, value)
  } catch {
    // Measurement remains best-effort when browser storage is unavailable.
  }
}

export function getOrCreateVisitorId(storage, cryptoObject = globalThis.crypto) {
  const existing = safeGet(storage, TRAFFIC_VISITOR_STORAGE_KEY)
  if (existing) return existing
  const visitorId = uuid(cryptoObject)
  if (visitorId) safeSet(storage, TRAFFIC_VISITOR_STORAGE_KEY, visitorId)
  return visitorId
}

export function getOrCreateSession(storage, now, cryptoObject = globalThis.crypto) {
  const raw = safeGet(storage, TRAFFIC_SESSION_STORAGE_KEY)
  try {
    const existing = JSON.parse(raw)
    if (
      existing?.session_id
      && Number.isFinite(existing.last_activity_at)
      && now - existing.last_activity_at < TRAFFIC_SESSION_TIMEOUT_MS
      && now >= existing.last_activity_at
    ) {
      const session = { session_id: existing.session_id, last_activity_at: now }
      safeSet(storage, TRAFFIC_SESSION_STORAGE_KEY, JSON.stringify(session))
      return session
    }
  } catch {
    // Invalid state rotates into a new session.
  }
  const sessionId = uuid(cryptoObject)
  if (!sessionId) return null
  const session = { session_id: sessionId, last_activity_at: now }
  safeSet(storage, TRAFFIC_SESSION_STORAGE_KEY, JSON.stringify(session))
  return session
}

function normalizePitcher(value) {
  const text = String(value || '').trim()
  return /^[1-9]\d*$/.test(text) ? Number(text) : null
}

export function canonicalPage(pathname, search = '', hash = '') {
  const path = pathname === '/' ? '/' : String(pathname || '').replace(/\/+$/, '')
  if (STATIC_ROUTES[path]) {
    return { route: path, surface: STATIC_ROUTES[path] }
  }
  if (path !== '/bullpen') return null

  const params = new URLSearchParams(search)
  const viewMode = params.get('view') || 'board'
  const surface = BULLPEN_SURFACES[viewMode]
  if (!surface) return null
  const page = { route: '/bullpen', surface, view_mode: viewMode }
  const entrySource = normalizeBullpenSource(params.get('source'))
  if (entrySource) page.entry_source = entrySource

  if (viewMode === BULLPEN_VIEWS.COMPARE) {
    const teamARef = normalizeTeamReference(params.get('team_a'))
    const teamBRef = normalizeTeamReference(params.get('team_b'))
    const completedPair = teamARef && teamBRef && teamARef !== teamBRef
    if (completedPair) {
      page.team_a_ref = teamARef
      page.team_b_ref = teamBRef
      page.evidence_target = String(hash || '').replace(/^#/, '') === EVIDENCE_SECTIONS.COMPARISON_EVIDENCE
        ? 'comparison_evidence'
        : 'comparison_read'
    }
    return page
  }

  const teamRef = normalizeTeamReference(params.get('team'))
  if (teamRef) page.team_ref = teamRef
  if (viewMode === BULLPEN_VIEWS.PITCHERS) return page

  const pitcherId = normalizePitcher(params.get('pitcher'))
  if (pitcherId) page.pitcher_id = pitcherId
  const section = String(hash || '').replace(/^#/, '')
  if (section === EVIDENCE_SECTIONS.TEAM_RELIEF_WORK && teamRef) {
    page.evidence_target = 'team_relief_work'
  } else if (section === EVIDENCE_SECTIONS.PITCHER_LANES && teamRef) {
    page.evidence_target = 'pitcher_lanes'
  } else if (pitcherId) {
    page.evidence_target = 'pitcher_detail'
  } else if (teamRef) {
    page.evidence_target = 'team_read'
  }
  return page
}

function normalizeUtm(value, limit) {
  const raw = String(value || '')
  if (SENSITIVE_UTM_PATTERNS.some((pattern) => pattern.test(raw))) return null
  const text = raw.trim().toLowerCase()
    .replace(/[^a-z0-9._~-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^[_.~-]+|[_.~-]+$/g, '')
  return text.slice(0, limit) || null
}

function referrerHostname(referrer) {
  if (!referrer) return null
  try {
    const hostname = new URL(referrer).hostname.toLowerCase().replace(/\.$/, '')
    return hostname && !hostname.includes(':') ? hostname.slice(0, 253) : null
  } catch {
    return null
  }
}

export function acquisitionFields(search = '', referrer = '') {
  const params = new URLSearchParams(search)
  const acquisition = {}
  const domain = referrerHostname(referrer)
  if (domain) acquisition.referrer_domain = domain
  for (const [key, limit] of Object.entries(UTM_LIMITS)) {
    const value = normalizeUtm(params.get(key), limit)
    if (value) acquisition[key] = value
  }
  return acquisition
}

export function buildPageView({ hostname, pathname, search, hash, referrer, storage, now, cryptoObject }) {
  if (hostname !== TRAFFIC_CANONICAL_HOST) return null
  const page = canonicalPage(pathname, search, hash)
  if (!page) return null
  const visitorId = getOrCreateVisitorId(storage, cryptoObject)
  const session = getOrCreateSession(storage, now, cryptoObject)
  const viewId = uuid(cryptoObject)
  if (!visitorId || !session || !viewId) return null
  return {
    view_id: viewId,
    visitor_id: visitorId,
    session_id: session.session_id,
    ...page,
    ...acquisitionFields(search, referrer),
    site_host: TRAFFIC_CANONICAL_HOST,
  }
}

export function sendPageView(payload, {
  fetchImpl = globalThis.fetch,
  storage,
  configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL,
} = {}) {
  if (!payload || typeof fetchImpl !== 'function') return
  const headers = { 'Content-Type': 'application/json' }
  const token = readAuthToken(storage)
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    Promise.resolve(fetchImpl(trafficPageViewUrl(configuredBackendOrigin), {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      keepalive: true,
    })).catch(() => {})
  } catch {
    // Measurement failures never affect rendering or navigation.
  }
}

export function trafficPageViewUrl(configuredBackendOrigin = import.meta.env.VITE_API_BASE_URL) {
  const apiBase = configuredBackendOrigin ? `${configuredBackendOrigin}/api` : '/api'
  return `${apiBase}/traffic/page-view`
}

export function observeTrafficRoute({
  locationKey,
  hostname,
  pathname,
  search = '',
  hash = '',
  referrer = '',
  storage,
  now = Date.now(),
  cryptoObject = globalThis.crypto,
  fetchImpl = globalThis.fetch,
}) {
  if (hostname !== TRAFFIC_CANONICAL_HOST) return false
  const page = canonicalPage(pathname, search, hash)
  if (!page) return false
  const identity = [
    page.route,
    page.surface,
    page.view_mode || '',
    page.team_ref || '',
    page.team_a_ref || '',
    page.team_b_ref || '',
    page.pitcher_id || '',
    page.evidence_target || '',
    page.entry_source || '',
  ].join('|')
  const dedupeKey = `${locationKey || 'unknown'}|${identity}`
  if (lastObservedEntry === dedupeKey) return false
  const payload = buildPageView({ hostname, pathname, search, hash, referrer, storage, now, cryptoObject })
  if (!payload) return false
  lastObservedEntry = dedupeKey
  sendPageView(payload, { fetchImpl, storage })
  return true
}

export function resetObservedTrafficEntriesForTests() {
  lastObservedEntry = null
}
