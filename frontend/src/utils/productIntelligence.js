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
