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

afterEach(() => {
  resetAnalyticsDedupeForTests()
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.CustomEvent = originalCustomEvent
})

const { recordProductEvent } = await server.ssrLoadModule('/src/utils/api.js')
const {
  ANALYTICS_EVENTS,
  IMPLEMENTED_ANALYTICS_EVENT_NAMES,
  analyticsObservationKey,
  buildAnalyticsEventPayload,
  currentAnalyticsRoute,
  resetAnalyticsDedupeForTests,
  trackAnalyticsEvent,
  trackAnalyticsEventOnce,
} = await server.ssrLoadModule('/src/utils/analytics.js')
const { readProductAnonId } = await server.ssrLoadModule('/src/utils/productIdentity.js')

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

function installWindow(storage, pathname = '/bullpen') {
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) {
      this.type = type
      this.detail = init.detail
    }
  }
  globalThis.window = {
    location: { pathname },
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

test('V4 analytics constants keep implemented and reserved names stable', () => {
  assert.equal(ANALYTICS_EVENTS.APP_VIEWED, 'app_viewed')
  assert.equal(ANALYTICS_EVENTS.HOMEPAGE_VIEWED, 'homepage_viewed')
  assert.equal(ANALYTICS_EVENTS.SHARE_INTENT_CLICKED, 'share_intent_clicked')
  assert.equal(ANALYTICS_EVENTS.TEAM_FOLLOW_STARTED, 'team_follow_started')
  assert.ok(IMPLEMENTED_ANALYTICS_EVENT_NAMES.includes('social_outbound_clicked'))
  assert.equal(IMPLEMENTED_ANALYTICS_EVENT_NAMES.includes('team_follow_started'), false)
})

test('analytics payload builder keeps only safe, useful fields', () => {
  assert.deepEqual(buildAnalyticsEventPayload(ANALYTICS_EVENTS.TEAM_SURFACE_VIEWED, {
    surface: 'Bullpen',
    route: '/bullpen?view=board&email=fan@example.com',
    source: 'team_selector',
    team_abbrev: ' sf ',
    team_id: '137',
    player_id: '657277',
    freshness_state: 'current',
    ignored: 'not stored',
  }), {
    event_name: 'team_surface_viewed',
    surface: 'bullpen',
    route: '/bullpen',
    source: 'team_selector',
    team_abbrev: 'SF',
    player_id: 657277,
    freshness_state: 'current',
    team_id: 137,
  })

  assert.deepEqual(buildAnalyticsEventPayload(ANALYTICS_EVENTS.SOCIAL_OUTBOUND_CLICKED, {
    surface: 'footer',
    source: 'fan@example.com',
    route: 'mailto:baseballoshq@gmail.com',
    team_abbrev: 'too-long',
    player_id: 'player-name',
    freshness_state: 'current state',
  }), {
    event_name: 'social_outbound_clicked',
    surface: 'footer',
  })
})

test('future events remain no-op until the corresponding surface exists', () => {
  assert.equal(buildAnalyticsEventPayload(ANALYTICS_EVENTS.TEAM_FOLLOW_STARTED, {
    surface: 'dashboard',
  }), null)
  assert.equal(buildAnalyticsEventPayload('unknown_event', { surface: 'app' }), null)
})

test('analytics tracker no-ops when unavailable and swallows send failures', async () => {
  assert.equal(await trackAnalyticsEvent(ANALYTICS_EVENTS.APP_VIEWED, { route: '/' }, { send: null }), false)
  assert.equal(await trackAnalyticsEvent(ANALYTICS_EVENTS.APP_VIEWED, { route: '/' }, {
    send: async () => {
      throw new Error('analytics unavailable')
    },
  }), false)
})

test('analytics tracker sends sanitized payload and once helper dedupes by payload', async () => {
  const calls = []
  const send = async payload => calls.push(payload)

  assert.equal(await trackAnalyticsEvent(ANALYTICS_EVENTS.METHODOLOGY_VIEWED, {
    surface: 'methodology',
    route: '/methodology',
    source: 'page',
  }, { send }), true)
  assert.equal(await trackAnalyticsEventOnce(ANALYTICS_EVENTS.METHODOLOGY_VIEWED, {
    surface: 'methodology',
    route: '/methodology',
    source: 'page',
  }, { send }), true)
  assert.equal(await trackAnalyticsEventOnce(ANALYTICS_EVENTS.METHODOLOGY_VIEWED, {
    surface: 'methodology',
    route: '/methodology',
    source: 'page',
  }, { send }), false)

  assert.deepEqual(calls, [
    { event_name: 'methodology_viewed', surface: 'methodology', route: '/methodology', source: 'page' },
    { event_name: 'methodology_viewed', surface: 'methodology', route: '/methodology', source: 'page' },
  ])
  assert.equal(
    analyticsObservationKey(calls[0]),
    'methodology_viewed|/methodology|methodology|page|none|none|none',
  )
})

test('currentAnalyticsRoute reads only the safe pathname', () => {
  const storage = createStorage()
  installWindow(storage, '/trust')
  assert.equal(currentAnalyticsRoute(), '/trust')
})

test('recordProductEvent posts through the owned product-event endpoint with anon id', async () => {
  const storage = createStorage()
  installWindow(storage)
  const calls = installFetch(async () => ({ json: { ok: true } }))

  await recordProductEvent({
    event_name: 'app_viewed',
    surface: 'app',
    route: '/bullpen',
    source: 'app',
  })

  assert.deepEqual(calls.map(call => call.url), ['/api/product/event'])
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    anon_id: readProductAnonId(storage),
    event_name: 'app_viewed',
    surface: 'app',
    route: '/bullpen',
    source: 'app',
  })
})
