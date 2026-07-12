import { recordProductEvent } from './api'

export const ANALYTICS_EVENTS = Object.freeze({
  APP_VIEWED: 'app_viewed',
  HOMEPAGE_VIEWED: 'homepage_viewed',
  BULLPEN_BOARD_VIEWED: 'bullpen_board_viewed',
  TEAM_SURFACE_VIEWED: 'team_surface_viewed',
  PITCHER_SURFACE_VIEWED: 'pitcher_surface_viewed',
  METHODOLOGY_VIEWED: 'methodology_viewed',
  TRUST_SURFACE_VIEWED: 'trust_surface_viewed',
  FRESHNESS_SURFACE_VIEWED: 'freshness_surface_viewed',
  SOCIAL_OUTBOUND_CLICKED: 'social_outbound_clicked',
  NEWSLETTER_INTEREST_CLICKED: 'newsletter_interest_clicked',
  TEAM_INTEREST_CLICKED: 'team_interest_clicked',
  SHARE_INTENT_CLICKED: 'share_intent_clicked',
  FEEDBACK_INTENT_CLICKED: 'feedback_intent_clicked',
  TEAM_FOLLOW_STARTED: 'team_follow_started',
  TEAM_FOLLOW_COMPLETED: 'team_follow_completed',
  DAILY_HOME_VIEWED: 'daily_home_viewed',
  WHAT_CHANGED_VIEWED: 'what_changed_viewed',
  WHAT_CHANGED_ITEM_OPENED: 'what_changed_item_opened',
  WHAT_CHANGED_TEAM_CLICKED: 'what_changed_team_clicked',
  TEAM_PAGE_VIEWED: 'team_page_viewed',
  SHARE_CARD_CLICKED: 'share_card_clicked',
  SHARE_CARD_DOWNLOADED: 'share_card_downloaded',
  DIGEST_SIGNUP_STARTED: 'digest_signup_started',
  DIGEST_SIGNUP_COMPLETED: 'digest_signup_completed',
  CORRECTION_SUBMITTED: 'correction_submitted',
  PRO_WAITLIST_STARTED: 'pro_waitlist_started',
  PRO_WAITLIST_COMPLETED: 'pro_waitlist_completed',
})

export const IMPLEMENTED_ANALYTICS_EVENT_NAMES = Object.freeze([
  ANALYTICS_EVENTS.APP_VIEWED,
  ANALYTICS_EVENTS.HOMEPAGE_VIEWED,
  ANALYTICS_EVENTS.BULLPEN_BOARD_VIEWED,
  ANALYTICS_EVENTS.TEAM_SURFACE_VIEWED,
  ANALYTICS_EVENTS.PITCHER_SURFACE_VIEWED,
  ANALYTICS_EVENTS.METHODOLOGY_VIEWED,
  ANALYTICS_EVENTS.TRUST_SURFACE_VIEWED,
  ANALYTICS_EVENTS.FRESHNESS_SURFACE_VIEWED,
  ANALYTICS_EVENTS.SOCIAL_OUTBOUND_CLICKED,
  ANALYTICS_EVENTS.NEWSLETTER_INTEREST_CLICKED,
  ANALYTICS_EVENTS.TEAM_INTEREST_CLICKED,
  ANALYTICS_EVENTS.SHARE_INTENT_CLICKED,
  ANALYTICS_EVENTS.WHAT_CHANGED_VIEWED,
  ANALYTICS_EVENTS.WHAT_CHANGED_ITEM_OPENED,
  ANALYTICS_EVENTS.WHAT_CHANGED_TEAM_CLICKED,
])

const implementedEvents = new Set(IMPLEMENTED_ANALYTICS_EVENT_NAMES)
const observedAnalyticsEvents = new Set()
const SAFE_SLUG_PATTERN = /^[a-z0-9][a-z0-9_.:-]*$/
const SAFE_FRESHNESS_PATTERN = /^[a-z0-9][a-z0-9_.:-]*$/
const TEAM_ABBREV_PATTERN = /^[A-Z0-9]{2,5}$/
const WHAT_CHANGED_STATES = new Set([
  'changes_detected',
  'no_meaningful_changes',
  'insufficient_context',
])

function textValue(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function looksLikeSensitiveText(value) {
  return value.includes('@') || value.includes('\n') || value.includes('\r')
}

function cleanEventName(value) {
  const eventName = textValue(value)?.toLowerCase()
  return implementedEvents.has(eventName) ? eventName : null
}

function cleanSlug(value, maxLength = 64) {
  const slug = textValue(value)?.toLowerCase().slice(0, maxLength)
  if (!slug || looksLikeSensitiveText(slug)) return null
  return SAFE_SLUG_PATTERN.test(slug) ? slug : null
}

function cleanRoute(value) {
  const route = textValue(value)?.split('?')[0].split('#')[0].slice(0, 128)
  if (!route || !route.startsWith('/') || looksLikeSensitiveText(route)) return null
  if (/\s/.test(route)) return null
  return route
}

function cleanTeamAbbrev(value) {
  const abbr = textValue(value)?.toUpperCase().slice(0, 5)
  return abbr && TEAM_ABBREV_PATTERN.test(abbr) ? abbr : null
}

function cleanPlayerId(value) {
  if (value == null || value === '' || value === true || value === false) return null
  const playerId = Number(value)
  return Number.isInteger(playerId) && playerId > 0 && playerId < 10 ** 12 ? playerId : null
}

function cleanTeamId(value) {
  if (value == null || value === '' || value === true || value === false) return null
  const teamId = Number(value)
  return Number.isInteger(teamId) ? teamId : null
}

function cleanFreshnessState(value) {
  const state = textValue(value)?.toLowerCase().slice(0, 64)
  if (!state || looksLikeSensitiveText(state)) return null
  return SAFE_FRESHNESS_PATTERN.test(state) ? state : null
}

function cleanWhatChangedState(value) {
  const state = textValue(value)?.toLowerCase()
  return WHAT_CHANGED_STATES.has(state) ? state : null
}

export function currentAnalyticsRoute(env = globalThis) {
  const pathname = env?.window?.location?.pathname
  return cleanRoute(pathname) || null
}

export function buildAnalyticsEventPayload(eventName, props = {}) {
  const safeEventName = cleanEventName(eventName)
  if (!safeEventName) return null

  const payload = { event_name: safeEventName }
  const surface = cleanSlug(props.surface)
  const route = cleanRoute(props.route)
  const source = cleanSlug(props.source, 32)
  const teamAbbrev = cleanTeamAbbrev(props.team_abbrev ?? props.teamAbbrev)
  const playerId = cleanPlayerId(props.player_id ?? props.playerId)
  const freshnessState = cleanFreshnessState(props.freshness_state ?? props.freshnessState)
  const teamId = cleanTeamId(props.team_id ?? props.teamId)
  const state = cleanWhatChangedState(props.state)

  if (surface) payload.surface = surface
  if (route) payload.route = route
  if (source) payload.source = source
  if (teamAbbrev) payload.team_abbrev = teamAbbrev
  if (playerId != null) payload.player_id = playerId
  if (freshnessState) payload.freshness_state = freshnessState
  if (teamId != null) payload.team_id = teamId
  if (state) payload.state = state

  return payload
}

export function analyticsObservationKey(payload) {
  if (!payload?.event_name) return null
  return [
    payload.event_name,
    payload.route || 'none',
    payload.surface || 'none',
    payload.source || 'none',
    payload.team_abbrev || payload.team_id || 'none',
    payload.player_id || 'none',
    payload.freshness_state || 'none',
    payload.state || 'none',
  ].join('|')
}

export async function trackAnalyticsEvent(eventName, props = {}, { send = recordProductEvent } = {}) {
  const payload = buildAnalyticsEventPayload(eventName, props)
  if (!payload || typeof send !== 'function') return false
  try {
    await send(payload)
    return true
  } catch {
    return false
  }
}

export function trackAnalyticsEventOnce(eventName, props = {}, options = {}) {
  const payload = buildAnalyticsEventPayload(eventName, props)
  const key = analyticsObservationKey(payload)
  if (!payload || !key || observedAnalyticsEvents.has(key)) return Promise.resolve(false)
  observedAnalyticsEvents.add(key)
  return trackAnalyticsEvent(payload.event_name, payload, options)
}

export function resetAnalyticsDedupeForTests() {
  observedAnalyticsEvents.clear()
}
