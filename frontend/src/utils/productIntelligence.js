import { getOrCreateProductAnonId, normalizeProductAnonId } from './productIdentity'

const observedProductEvents = new Set()

function cleanText(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function cleanTeamId(value) {
  if (value == null || value === '' || value === false || value === true) return null
  const id = Number(value)
  return Number.isInteger(id) ? id : null
}

function cleanSource(value, fallback = 'direct') {
  const source = cleanText(value)?.toLowerCase()
  if (source === 'digest' || source === 'direct' || source === 'organic') return source
  return fallback
}

function cleanSurface(value) {
  const surface = cleanText(value)?.toLowerCase()
  if (surface === 'home' || surface === 'stories' || surface === 'digest_web') return surface
  return null
}

function cleanInteraction(value) {
  const interaction = cleanText(value)?.toLowerCase()
  if (interaction === 'expand' || interaction === 'open' || interaction === 'select') return interaction
  return null
}

function storyValue(story, ...keys) {
  for (const key of keys) {
    const value = story?.[key]
    if (value != null && value !== '') return value
  }
  return null
}

export function productObservationKey(parts = []) {
  return parts.map(part => (part == null || part === '' ? 'none' : String(part))).join('|')
}

export function todayLoadedObservationKey({ teamId = null, team_id = teamId, source = 'direct' } = {}) {
  return productObservationKey(['today_loaded', cleanSource(source), cleanTeamId(team_id)])
}

export function storyViewedObservationKey({
  storyId = null,
  storyType = null,
  teamId = null,
  surface = null,
} = {}) {
  return productObservationKey([
    'story_viewed',
    cleanSurface(surface),
    cleanTeamId(teamId),
    cleanText(storyId),
    cleanText(storyType),
  ])
}

export function buildTodayLoadedPayload({
  teamId = null,
  source = 'direct',
  anonId = getOrCreateProductAnonId(),
} = {}) {
  return {
    anon_id: normalizeProductAnonId(anonId),
    team_id: cleanTeamId(teamId),
    source: cleanSource(source),
  }
}

export function buildStoryViewedPayload(
  story,
  {
    surface = null,
    anonId = getOrCreateProductAnonId(),
  } = {},
) {
  const storyId = cleanText(storyValue(story, 'storyId', 'story_id', 'id'))
  const storyType = cleanText(storyValue(story, 'storyType', 'story_type'))
  if (!storyId || !storyType) return null

  return {
    anon_id: normalizeProductAnonId(anonId),
    team_id: cleanTeamId(storyValue(story, 'teamId', 'team_id')),
    story_id: storyId,
    story_type: storyType,
    surface: cleanSurface(surface),
  }
}

export function storyInteractedObservationKey({
  storyId = null,
  storyType = null,
  teamId = null,
  surface = null,
  interactionType = null,
} = {}) {
  return productObservationKey([
    'story_interacted',
    cleanSurface(surface),
    cleanInteraction(interactionType),
    cleanTeamId(teamId),
    cleanText(storyId),
    cleanText(storyType),
  ])
}

export function buildStoryInteractedPayload(
  story,
  {
    surface = null,
    interactionType = 'select',
    anonId = getOrCreateProductAnonId(),
  } = {},
) {
  const storyId = cleanText(storyValue(story, 'storyId', 'story_id', 'id'))
  const storyType = cleanText(storyValue(story, 'storyType', 'story_type'))
  if (!storyId || !storyType) return null

  return {
    anon_id: normalizeProductAnonId(anonId),
    team_id: cleanTeamId(storyValue(story, 'teamId', 'team_id')),
    story_id: storyId,
    story_type: storyType,
    surface: cleanSurface(surface),
    interaction_type: cleanInteraction(interactionType),
  }
}

export function uniqueStoryViewedPayloads(
  stories = [],
  {
    surface = null,
    anonId = getOrCreateProductAnonId(),
  } = {},
) {
  const seen = new Set()
  const payloads = []
  for (const story of (Array.isArray(stories) ? stories : [])) {
    const payload = buildStoryViewedPayload(story, { surface, anonId })
    if (!payload) continue
    const key = storyViewedObservationKey({
      storyId: payload.story_id,
      storyType: payload.story_type,
      teamId: payload.team_id,
      surface: payload.surface,
    })
    if (seen.has(key)) continue
    seen.add(key)
    payloads.push(payload)
  }
  return payloads
}

export function resetProductObservationDedupeForTests() {
  observedProductEvents.clear()
}

async function sendOnce(key, send, payload) {
  if (!key || typeof send !== 'function' || observedProductEvents.has(key)) return false
  observedProductEvents.add(key)
  try {
    await send(payload)
    return true
  } catch {
    return false
  }
}

export function observeTodayLoadedOnce({
  loaded = false,
  teamId = null,
  source = 'direct',
  anonId = getOrCreateProductAnonId(),
  send,
} = {}) {
  if (!loaded) return Promise.resolve(false)
  const payload = buildTodayLoadedPayload({ teamId, source, anonId })
  return sendOnce(todayLoadedObservationKey(payload), send, payload)
}

export async function observeStoryViewedOnce({
  stories = [],
  surface = null,
  anonId = getOrCreateProductAnonId(),
  send,
} = {}) {
  const payloads = uniqueStoryViewedPayloads(stories, { surface, anonId })
  let sent = 0
  for (const payload of payloads) {
    const didSend = await sendOnce(storyViewedObservationKey({
      storyId: payload.story_id,
      storyType: payload.story_type,
      teamId: payload.team_id,
      surface: payload.surface,
    }), send, payload)
    if (didSend) sent += 1
  }
  return sent
}

export function observeStoryInteractedOnce({
  story,
  surface = null,
  interactionType = 'select',
  anonId = getOrCreateProductAnonId(),
  send,
} = {}) {
  const payload = buildStoryInteractedPayload(story, { surface, interactionType, anonId })
  if (!payload) return Promise.resolve(false)
  return sendOnce(storyInteractedObservationKey({
    storyId: payload.story_id,
    storyType: payload.story_type,
    teamId: payload.team_id,
    surface: payload.surface,
    interactionType: payload.interaction_type,
  }), send, payload)
}

// ── Story impression observation (V3-1) ───────────────────────────────────────
// A story card appeared on screen, as opposed to merely rendering into the DOM.
// The honest successor to the old render-fired story_viewed: it shares the exact
// canonical identity (story_id + story_type + team_id + surface + anon_id) and the
// in-session dedupe, but fires from viewport observation rather than on render.

// Approximate viewport visibility at which a card counts as "appeared".
export const STORY_IMPRESSION_THRESHOLD = 0.5

// Same payload shape as story_viewed (the on-screen presentation fact).
export function buildStoryImpressionPayload(story, options = {}) {
  return buildStoryViewedPayload(story, options)
}

export function storyImpressionObservationKey({
  storyId = null,
  storyType = null,
  teamId = null,
  surface = null,
} = {}) {
  return productObservationKey([
    'story_impression',
    cleanSurface(surface),
    cleanTeamId(teamId),
    cleanText(storyId),
    cleanText(storyType),
  ])
}

// A stable per-card key for wiring viewport refs. Null for any card that lacks a
// canonical story identity (e.g. the league context card), so such cards are
// never observed and never emit an impression.
export function storyImpressionRefKey(story) {
  const storyId = cleanText(storyValue(story, 'storyId', 'story_id', 'id'))
  const storyType = cleanText(storyValue(story, 'storyType', 'story_type'))
  if (!storyId || !storyType) return null
  const teamId = cleanTeamId(storyValue(story, 'teamId', 'team_id'))
  return [storyId, storyType, teamId == null ? 'none' : teamId].join('|')
}

export function observeStoryImpressionOnce({
  story,
  surface = null,
  anonId = getOrCreateProductAnonId(),
  send,
} = {}) {
  const payload = buildStoryImpressionPayload(story, { surface, anonId })
  if (!payload) return Promise.resolve(false)
  return sendOnce(storyImpressionObservationKey({
    storyId: payload.story_id,
    storyType: payload.story_type,
    teamId: payload.team_id,
    surface: payload.surface,
  }), send, payload)
}

// Pure viewport-impression orchestrator, decoupled from React for testability.
// observe(element, story) starts watching a card; when it reaches the threshold
// the impression fires once (deduped via observeStoryImpressionOnce) and the
// element is unobserved. IntersectionObserver is feature-detected — when it is
// unavailable the tracker is an inert no-op (it never fires a false impression).
// disconnect() tears everything down.
export function createStoryImpressionTracker({
  surface = null,
  anonId = getOrCreateProductAnonId(),
  send,
  threshold = STORY_IMPRESSION_THRESHOLD,
} = {}) {
  if (typeof IntersectionObserver === 'undefined') {
    return { supported: false, observe() {}, unobserve() {}, disconnect() {} }
  }

  const storyByElement = new Map()
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting || entry.intersectionRatio < threshold) continue
      const element = entry.target
      const story = storyByElement.get(element)
      if (!story) continue
      observer.unobserve(element)
      storyByElement.delete(element)
      observeStoryImpressionOnce({ story, surface, anonId, send })
    }
  }, { threshold })

  return {
    supported: true,
    observe(element, story) {
      if (!element || !story) return
      storyByElement.set(element, story)
      observer.observe(element)
    },
    unobserve(element) {
      if (!element) return
      storyByElement.delete(element)
      observer.unobserve(element)
    },
    disconnect() {
      storyByElement.clear()
      observer.disconnect()
    },
  }
}

// ── Story team-board open (V3-2) ──────────────────────────────────────────────
// The reader followed a story's primary CTA into the Team Board — the high-intent
// story → team-board conversion. Unlike impressions/views (deduped once per
// session), this fires once per physical click: each open is a distinct intent
// signal, so it is intentionally NOT routed through the session dedupe.

export function buildStoryTeamBoardOpenedPayload(story, options = {}) {
  return buildStoryViewedPayload(story, options)
}

export function observeStoryTeamBoardOpened({
  story,
  surface = null,
  anonId = getOrCreateProductAnonId(),
  send,
} = {}) {
  const payload = buildStoryTeamBoardOpenedPayload(story, { surface, anonId })
  if (!payload || typeof send !== 'function') return Promise.resolve(false)
  try {
    return Promise.resolve(send(payload)).then(() => true).catch(() => false)
  } catch {
    return Promise.resolve(false)
  }
}
