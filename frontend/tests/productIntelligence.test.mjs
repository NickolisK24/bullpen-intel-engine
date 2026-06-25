import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after, afterEach } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
const originalCustomEvent = globalThis.CustomEvent
const originalConsoleError = console.error
const originalIntersectionObserver = globalThis.IntersectionObserver

afterEach(() => {
  resetProductObservationDedupeForTests()
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.CustomEvent = originalCustomEvent
  globalThis.IntersectionObserver = originalIntersectionObserver
  console.error = originalConsoleError
})

const {
  recordStoryImpression,
  recordStoryInteracted,
  recordStoryViewed,
  recordTodayLoaded,
  verifyMagicLink,
} = await server.ssrLoadModule('/src/utils/api.js')
const {
  PRODUCT_ANON_ID_STORAGE_KEY,
  getOrCreateProductAnonId,
  normalizeProductAnonId,
  readProductAnonId,
} = await server.ssrLoadModule('/src/utils/productIdentity.js')
const {
  STORY_IMPRESSION_THRESHOLD,
  buildStoryImpressionPayload,
  buildStoryInteractedPayload,
  buildStoryViewedPayload,
  buildTodayLoadedPayload,
  createStoryImpressionTracker,
  observeStoryImpressionOnce,
  observeStoryInteractedOnce,
  observeStoryViewedOnce,
  observeTodayLoadedOnce,
  resetProductObservationDedupeForTests,
  storyImpressionObservationKey,
  storyViewedObservationKey,
  uniqueStoryViewedPayloads,
} = await server.ssrLoadModule('/src/utils/productIntelligence.js')

function createStorage() {
  const values = new Map()
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null
    },
    setItem(key, value) {
      values.set(key, String(value))
    },
    removeItem(key) {
      values.delete(key)
    },
  }
}

function installWindow(storage) {
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) {
      this.type = type
      this.detail = init.detail
    }
  }
  globalThis.window = {
    localStorage: storage,
    dispatchEvent() { return true },
    addEventListener() {},
    removeEventListener() {},
  }
}

function installFetch(handler) {
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    const body = await handler(url, options, calls)
    return {
      ok: body?.ok !== false,
      status: body?.status || 200,
      statusText: body?.statusText || 'OK',
      json: async () => body?.json ?? {},
    }
  }
  return calls
}

test('product anonymous identity is stable, pseudonymous, and locally stored', () => {
  const storage = createStorage()
  const anonId = getOrCreateProductAnonId(storage)

  assert.match(anonId, /^anon:/)
  assert.equal(anonId.includes('@'), false)
  assert.equal(anonId.length <= 64, true)
  assert.equal(storage.getItem(PRODUCT_ANON_ID_STORAGE_KEY), anonId)
  assert.equal(readProductAnonId(storage), anonId)
  assert.equal(getOrCreateProductAnonId(storage), anonId)
  assert.equal(normalizeProductAnonId('fan@example.com'), null)
})

test('verifyMagicLink sends anon_id for the signed-in bridge without auth header', async () => {
  const storage = createStorage()
  installWindow(storage)
  const calls = installFetch(async (url, options) => {
    assert.equal(url, '/api/auth/verify')
    assert.equal(options.headers.Authorization, undefined)
    const payload = JSON.parse(options.body)
    assert.equal(payload.token, 'magic-token')
    assert.match(payload.anon_id, /^anon:/)
    return { json: { token: 'bearer-token', user: { id: 1 } } }
  })

  await verifyMagicLink('magic-token')

  assert.equal(calls.length, 1)
})

test('Product Intelligence helpers call the existing observation endpoints', async () => {
  const storage = createStorage()
  installWindow(storage)
  const calls = installFetch(async (url, options) => {
    assert.equal(options.method, 'POST')
    assert.equal(Object.hasOwn(options, 'silent'), false)
    return { json: { ok: true } }
  })

  await recordTodayLoaded({ team_id: 118, source: 'digest' })
  await recordStoryViewed({
    team_id: 118,
    story_id: '118:2026-06-22',
    story_type: 'coverage_pressure',
    surface: 'home',
  })

  assert.deepEqual(calls.map(call => call.url), [
    '/api/product/today-loaded',
    '/api/product/story-viewed',
  ])
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    anon_id: readProductAnonId(storage),
    team_id: 118,
    source: 'digest',
  })
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    anon_id: readProductAnonId(storage),
    team_id: 118,
    story_id: '118:2026-06-22',
    story_type: 'coverage_pressure',
    surface: 'home',
  })
})

test('today_loaded observation waits for loaded Today and dedupes per team/source', async () => {
  const calls = []
  const send = async (payload) => {
    calls.push(payload)
  }

  assert.equal(await observeTodayLoadedOnce({
    loaded: false,
    teamId: 118,
    source: 'digest',
    anonId: 'anon:test',
    send,
  }), false)
  assert.equal(await observeTodayLoadedOnce({
    loaded: true,
    teamId: 118,
    source: 'digest',
    anonId: 'anon:test',
    send,
  }), true)
  assert.equal(await observeTodayLoadedOnce({
    loaded: true,
    teamId: 118,
    source: 'digest',
    anonId: 'anon:test',
    send,
  }), false)
  assert.equal(await observeTodayLoadedOnce({
    loaded: true,
    teamId: 110,
    source: 'digest',
    anonId: 'anon:test',
    send,
  }), true)

  assert.deepEqual(calls, [
    {
      anon_id: 'anon:test',
      team_id: 118,
      source: 'digest',
    },
    {
      anon_id: 'anon:test',
      team_id: 110,
      source: 'digest',
    },
  ])
})

test('story_viewed observation records rendered canonical stories only and dedupes', async () => {
  const stories = [
    {
      storyId: '118:2026-06-22',
      storyType: 'coverage_pressure',
      teamId: 118,
    },
    {
      storyId: '118:2026-06-22',
      storyType: 'coverage_pressure',
      teamId: 118,
    },
    {
      storyId: null,
      storyType: 'coverage_pressure',
      teamId: 147,
    },
  ]
  const payload = buildStoryViewedPayload(stories[0], {
    surface: 'home',
    anonId: 'anon:test',
  })
  const unique = uniqueStoryViewedPayloads(stories, {
    surface: 'home',
    anonId: 'anon:test',
  })
  const calls = []
  const sent = await observeStoryViewedOnce({
    stories,
    surface: 'home',
    anonId: 'anon:test',
    send: async (nextPayload) => {
      calls.push(nextPayload)
    },
  })
  const sentAgain = await observeStoryViewedOnce({
    stories,
    surface: 'home',
    anonId: 'anon:test',
    send: async (nextPayload) => {
      calls.push(nextPayload)
    },
  })

  assert.deepEqual(payload, {
    anon_id: 'anon:test',
    team_id: 118,
    story_id: '118:2026-06-22',
    story_type: 'coverage_pressure',
    surface: 'home',
  })
  assert.equal(unique.length, 1)
  assert.equal(sent, 1)
  assert.equal(sentAgain, 0)
  assert.deepEqual(calls, [payload])
})

test('recordStoryInteracted posts to its endpoint with the product anon id', async () => {
  const storage = createStorage()
  installWindow(storage)
  const calls = installFetch(async () => ({ json: { ok: true } }))

  await recordStoryInteracted({
    team_id: 118,
    story_id: '118:2026-06-25',
    story_type: 'coverage_pressure',
    surface: 'stories',
    interaction_type: 'select',
  })

  assert.deepEqual(calls.map(call => call.url), ['/api/product/story-interacted'])
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    anon_id: readProductAnonId(storage),
    team_id: 118,
    story_id: '118:2026-06-25',
    story_type: 'coverage_pressure',
    surface: 'stories',
    interaction_type: 'select',
  })
})

test('story_interacted observation builds payload and dedupes per story/surface/kind', async () => {
  const story = { storyId: '118:2026-06-25', storyType: 'coverage_pressure', teamId: 118 }
  const payload = buildStoryInteractedPayload(story, {
    surface: 'stories',
    interactionType: 'select',
    anonId: 'anon:test',
  })
  assert.deepEqual(payload, {
    anon_id: 'anon:test',
    team_id: 118,
    story_id: '118:2026-06-25',
    story_type: 'coverage_pressure',
    surface: 'stories',
    interaction_type: 'select',
  })

  const calls = []
  const send = async (next) => { calls.push(next) }
  assert.equal(await observeStoryInteractedOnce({
    story, surface: 'stories', interactionType: 'select', anonId: 'anon:test', send,
  }), true)
  assert.equal(await observeStoryInteractedOnce({
    story, surface: 'stories', interactionType: 'select', anonId: 'anon:test', send,
  }), false)
  assert.deepEqual(calls, [payload])
})

test('story_interacted skips stories without ids and never fabricates surface or kind', () => {
  assert.equal(buildStoryInteractedPayload(
    { storyId: '', storyType: 'coverage_pressure', teamId: 1 },
    { surface: 'stories', interactionType: 'select', anonId: 'anon:test' },
  ), null)

  const payload = buildStoryInteractedPayload(
    { storyId: 's1', storyType: 'coverage_pressure', teamId: 1 },
    { surface: 'popup_banner', interactionType: 'hover', anonId: 'anon:test' },
  )
  assert.equal(payload.surface, null)
  assert.equal(payload.interaction_type, null)
})

test('today and story payload builders normalize unsafe optional fields', () => {
  assert.deepEqual(buildTodayLoadedPayload({
    teamId: 'not-a-team',
    source: 'facebook_ad',
    anonId: 'fan@example.com',
  }), {
    anon_id: null,
    team_id: null,
    source: 'direct',
  })
  assert.equal(buildStoryViewedPayload({
    storyId: '',
    storyType: 'coverage_pressure',
    teamId: 118,
  }, { surface: 'stories', anonId: 'anon:test' }), null)
})

// ── V3-1: viewport-based story impressions ────────────────────────────────────

function installIntersectionObserver() {
  const instances = []
  class FakeIntersectionObserver {
    constructor(callback, options = {}) {
      this.callback = callback
      this.options = options
      this.elements = new Set()
      this.disconnected = false
      instances.push(this)
    }
    observe(element) { this.elements.add(element) }
    unobserve(element) { this.elements.delete(element) }
    disconnect() { this.elements.clear(); this.disconnected = true }
    fire(entries) { this.callback(entries, this) }
  }
  globalThis.IntersectionObserver = FakeIntersectionObserver
  return instances
}

test('story_impression payload mirrors story_viewed but uses a distinct dedupe key', () => {
  const story = { storyId: '118:2026-06-22', storyType: 'coverage_pressure', teamId: 118 }
  assert.deepEqual(
    buildStoryImpressionPayload(story, { surface: 'home', anonId: 'anon:test' }),
    buildStoryViewedPayload(story, { surface: 'home', anonId: 'anon:test' }),
  )
  const identity = { storyId: '118:2026-06-22', storyType: 'coverage_pressure', teamId: 118, surface: 'home' }
  assert.notEqual(storyImpressionObservationKey(identity), storyViewedObservationKey(identity))
  assert.equal(STORY_IMPRESSION_THRESHOLD, 0.5)
})

test('observeStoryImpressionOnce fires once per story/surface/session', async () => {
  const story = { storyId: '118:2026-06-22', storyType: 'coverage_pressure', teamId: 118 }
  const calls = []
  const send = async (payload) => { calls.push(payload) }
  assert.equal(await observeStoryImpressionOnce({ story, surface: 'stories', anonId: 'anon:test', send }), true)
  assert.equal(await observeStoryImpressionOnce({ story, surface: 'stories', anonId: 'anon:test', send }), false)
  assert.deepEqual(calls, [{
    anon_id: 'anon:test', team_id: 118, story_id: '118:2026-06-22',
    story_type: 'coverage_pressure', surface: 'stories',
  }])
})

test('recordStoryImpression posts to the owned story-event endpoint with a fixed event_name', async () => {
  const storage = createStorage()
  installWindow(storage)
  const calls = installFetch(async () => ({ json: { ok: true } }))

  await recordStoryImpression({
    team_id: 118, story_id: '118:2026-06-22', story_type: 'coverage_pressure', surface: 'home',
  })

  assert.deepEqual(calls.map(call => call.url), ['/api/product/story-event'])
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    anon_id: readProductAnonId(storage),
    team_id: 118,
    story_id: '118:2026-06-22',
    story_type: 'coverage_pressure',
    surface: 'home',
    event_name: 'story_impression',
  })
})

test('impression tracker fires once only when a card crosses the viewport threshold', async () => {
  const instances = installIntersectionObserver()
  const calls = []
  const tracker = createStoryImpressionTracker({
    surface: 'stories', anonId: 'anon:test', send: async (payload) => { calls.push(payload) },
  })
  assert.equal(tracker.supported, true)

  const element = { id: 'card-1' }
  const story = { storyId: '118:2026-06-22', storyType: 'coverage_pressure', teamId: 118 }
  tracker.observe(element, story)
  // Observing (render/attach) alone must NOT fire an impression.
  assert.equal(calls.length, 0)

  const observer = instances[0]
  // Below the threshold -> still nothing.
  observer.fire([{ target: element, isIntersecting: true, intersectionRatio: 0.2 }])
  await Promise.resolve()
  assert.equal(calls.length, 0)

  // Crossing the threshold -> exactly one impression.
  observer.fire([{ target: element, isIntersecting: true, intersectionRatio: 0.75 }])
  await Promise.resolve()
  assert.deepEqual(calls, [{
    anon_id: 'anon:test', team_id: 118, story_id: '118:2026-06-22',
    story_type: 'coverage_pressure', surface: 'stories',
  }])

  // A repeat intersection does not double-count (already fired + unobserved).
  observer.fire([{ target: element, isIntersecting: true, intersectionRatio: 0.95 }])
  await Promise.resolve()
  assert.equal(calls.length, 1)
})

test('impression tracker handles Home and Stories surfaces independently', async () => {
  const instances = installIntersectionObserver()
  const calls = []
  const send = async (payload) => { calls.push(payload) }
  const story = { storyId: '118:2026-06-22', storyType: 'coverage_pressure', teamId: 118 }

  const homeTracker = createStoryImpressionTracker({ surface: 'home', anonId: 'anon:test', send })
  const homeEl = { id: 'home-card' }
  homeTracker.observe(homeEl, story)
  instances[0].fire([{ target: homeEl, isIntersecting: true, intersectionRatio: 0.6 }])

  const storiesTracker = createStoryImpressionTracker({ surface: 'stories', anonId: 'anon:test', send })
  const storiesEl = { id: 'stories-card' }
  storiesTracker.observe(storiesEl, story)
  instances[1].fire([{ target: storiesEl, isIntersecting: true, intersectionRatio: 0.6 }])

  await Promise.resolve()
  assert.deepEqual(calls.map(call => call.surface), ['home', 'stories'])
})

test('impression tracker no-ops where IntersectionObserver is unavailable', async () => {
  delete globalThis.IntersectionObserver
  const calls = []
  const tracker = createStoryImpressionTracker({
    surface: 'home', anonId: 'anon:test', send: async (payload) => { calls.push(payload) },
  })
  assert.equal(tracker.supported, false)
  tracker.observe({ id: 'x' }, { storyId: 's', storyType: 'coverage_pressure', teamId: 1 })
  tracker.disconnect()
  await Promise.resolve()
  assert.equal(calls.length, 0)
})

test('impression tracker disconnects its observer on teardown', () => {
  const instances = installIntersectionObserver()
  const tracker = createStoryImpressionTracker({ surface: 'stories', anonId: 'anon:test', send: async () => {} })
  tracker.observe({ id: 'a' }, { storyId: 's', storyType: 'coverage_pressure', teamId: 1 })
  tracker.disconnect()
  assert.equal(instances[0].disconnected, true)
  assert.equal(instances[0].elements.size, 0)
})

test('Home and Stories track impressions on screen, not story_viewed on render', () => {
  const homeSrc = readFileSync(new URL('../src/components/home/Home.jsx', import.meta.url), 'utf8')
  const storiesSrc = readFileSync(new URL('../src/components/stories/Stories.jsx', import.meta.url), 'utf8')
  for (const src of [homeSrc, storiesSrc]) {
    assert.equal(src.includes('useStoryViewedObservations'), false)
    assert.ok(src.includes('useStoryImpressionObservations'))
  }
})
