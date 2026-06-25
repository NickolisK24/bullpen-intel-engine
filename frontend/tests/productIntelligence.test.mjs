import assert from 'node:assert/strict'
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

afterEach(() => {
  resetProductObservationDedupeForTests()
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.CustomEvent = originalCustomEvent
  console.error = originalConsoleError
})

const {
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
  buildStoryViewedPayload,
  buildTodayLoadedPayload,
  observeStoryViewedOnce,
  observeTodayLoadedOnce,
  resetProductObservationDedupeForTests,
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
