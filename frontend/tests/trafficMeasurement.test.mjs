import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after, beforeEach } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const traffic = await server.ssrLoadModule('/src/utils/trafficMeasurement.js')
const api = await server.ssrLoadModule('/src/utils/api.js')
const {
  TRAFFIC_SESSION_STORAGE_KEY,
  TRAFFIC_VISITOR_STORAGE_KEY,
  acquisitionFields,
  buildPageView,
  canonicalPage,
  getOrCreateSession,
  getOrCreateVisitorId,
  observeTrafficRoute,
  resetObservedTrafficEntriesForTests,
  sendPageView,
  trafficPageViewUrl,
} = traffic

beforeEach(() => resetObservedTrafficEntriesForTests())

test('route observer includes hash state in payload derivation and dependencies', () => {
  const source = readFileSync('src/components/TrafficRouteObserver.jsx', 'utf8')
  assert.ok(source.includes('hash: location.hash'))
  assert.ok(source.includes('[location.key, location.pathname, location.search, location.hash]'))
})

function storage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
}

function cryptoSequence() {
  let number = 0
  return {
    randomUUID() {
      number += 1
      return `00000000-0000-4000-8000-${String(number).padStart(12, '0')}`
    },
  }
}

test('visitor and active session persist independently', () => {
  const local = storage()
  const cryptoObject = cryptoSequence()
  const visitor = getOrCreateVisitorId(local, cryptoObject)
  assert.equal(getOrCreateVisitorId(local, cryptoObject), visitor)
  assert.equal(local.getItem(TRAFFIC_VISITOR_STORAGE_KEY), visitor)

  const first = getOrCreateSession(local, 1_000, cryptoObject)
  const second = getOrCreateSession(local, 2_000, cryptoObject)
  assert.equal(second.session_id, first.session_id)
  assert.equal(JSON.parse(local.getItem(TRAFFIC_SESSION_STORAGE_KEY)).last_activity_at, 2_000)
})

test('session rotates at thirty minutes of inactivity', () => {
  const local = storage()
  const cryptoObject = cryptoSequence()
  const first = getOrCreateSession(local, 0, cryptoObject)
  const second = getOrCreateSession(local, 30 * 60 * 1000, cryptoObject)
  assert.notEqual(second.session_id, first.session_id)
})

test('tracking is enabled only on the exact canonical production host', () => {
  for (const hostname of ['localhost', 'baseballos.vercel.app', 'preview-1.vercel.app', 'www.baseballos.app']) {
    assert.equal(buildPageView({
      hostname, pathname: '/', search: '', storage: storage(), now: 1, cryptoObject: cryptoSequence(),
    }), null)
  }
  assert.ok(buildPageView({
    hostname: 'baseballos.app', pathname: '/', search: '', storage: storage(), now: 1,
    cryptoObject: cryptoSequence(),
  }))
})

test('canonical route mapping excludes private, admin, and wildcard routes', () => {
  assert.deepEqual(canonicalPage('/'), { route: '/', surface: 'today' })
  assert.deepEqual(canonicalPage('/dashboard'), { route: '/dashboard', surface: 'dashboard' })
  assert.deepEqual(canonicalPage('/trust'), { route: '/trust', surface: 'data_trust' })
  assert.equal(canonicalPage('/posts/private'), null)
  assert.equal(canonicalPage('/admin'), null)
  assert.equal(canonicalPage('/anything'), null)
})

test('bullpen mapping retains only route-compatible allowlisted context and never raw query', () => {
  const page = canonicalPage('/bullpen', '?view=compare&team_a=nyy&team_b=bos&team=sea&pitcher=42&secret=token')
  assert.deepEqual(page, {
    route: '/bullpen', surface: 'compare_bullpens', view_mode: 'compare',
    team_a_ref: 'NYY', team_b_ref: 'BOS', evidence_target: 'comparison_read',
  })
  const payload = buildPageView({
    hostname: 'baseballos.app', pathname: '/bullpen',
    search: '?view=pitchers&team=la&unknown=value', storage: storage(), now: 1,
    cryptoObject: cryptoSequence(),
  })
  assert.equal(payload.surface, 'all_pitchers')
  assert.equal('search' in payload, false)
  assert.equal(JSON.stringify(payload).includes('unknown'), false)
})

test('team board canonical context maps default and exact evidence destinations', () => {
  assert.deepEqual(canonicalPage('/bullpen', '?view=board&team=bos'), {
    route: '/bullpen', surface: 'bullpen_board', view_mode: 'board',
    team_ref: 'BOS', evidence_target: 'team_read',
  })
  assert.equal(
    canonicalPage('/bullpen', '?view=board&team=BOS', '#team-relief-work').evidence_target,
    'team_relief_work',
  )
  assert.equal(
    canonicalPage('/bullpen', '?view=board&team=BOS', '#pitcher-lanes').evidence_target,
    'pitcher_lanes',
  )
})

test('pitcher detail yields to a supported exact evidence hash', () => {
  const detail = canonicalPage('/bullpen', '?view=board&team=BOS&pitcher=123456')
  assert.equal(detail.pitcher_id, 123456)
  assert.equal(detail.evidence_target, 'pitcher_detail')
  assert.equal(
    canonicalPage('/bullpen', '?view=board&team=BOS&pitcher=123456', '#pitcher-lanes').evidence_target,
    'pitcher_lanes',
  )
})

test('comparison context preserves visible order and maps exact evidence', () => {
  assert.deepEqual(canonicalPage(
    '/bullpen', '?view=compare&team_a=BOS&team_b=NYY&source=comparison', '#comparison-evidence',
  ), {
    route: '/bullpen', surface: 'compare_bullpens', view_mode: 'compare', entry_source: 'comparison',
    team_a_ref: 'BOS', team_b_ref: 'NYY', evidence_target: 'comparison_evidence',
  })
})

test('invalid and same-team comparisons remain generic compare views', () => {
  for (const search of [
    '?view=compare&team_a=BOS&team_b=BOS',
    '?view=compare&team_a=BOS&team_b=Boston',
    '?view=compare&team_a=BOS',
  ]) {
    assert.deepEqual(canonicalPage('/bullpen', search, '#comparison-evidence'), {
      route: '/bullpen', surface: 'compare_bullpens', view_mode: 'compare',
    })
  }
})

test('all pitchers keeps an optional team filter without evidence context', () => {
  assert.deepEqual(canonicalPage('/bullpen', '?view=pitchers&team=BOS&pitcher=123', '#pitcher-lanes'), {
    route: '/bullpen', surface: 'all_pitchers', view_mode: 'pitchers', team_ref: 'BOS',
  })
})

test('bounded entry sources are accepted and unknown source or hash values are omitted', () => {
  for (const source of ['today', 'dashboard', 'landscape', 'stories', 'comparison', 'all_pitchers', 'pitcher_search', 'share', 'share_link', 'share_card', 'since_yesterday']) {
    assert.equal(canonicalPage('/bullpen', `?view=board&team=BOS&source=${source}`).entry_source, source)
  }
  const page = canonicalPage('/bullpen', '?view=board&team=BOS&source=private', '#private-section')
  assert.equal('entry_source' in page, false)
  assert.equal(page.evidence_target, 'team_read')
  assert.equal(JSON.stringify(page).includes('private'), false)
})

test('direct exact-link payload includes hash-derived evidence context', () => {
  const payload = buildPageView({
    hostname: 'baseballos.app', pathname: '/bullpen',
    search: '?view=board&team=BOS&source=share_link', hash: '#team-relief-work',
    storage: storage(), now: 1, cryptoObject: cryptoSequence(),
  })
  assert.equal(payload.team_ref, 'BOS')
  assert.equal(payload.entry_source, 'share_link')
  assert.equal(payload.evidence_target, 'team_relief_work')
  assert.equal('hash' in payload, false)
})

test('UTM and referrer acquisition are normalized and bounded', () => {
  const fields = acquisitionFields(
    '?utm_source=News%20Letter&utm_medium=E-mail&utm_campaign=' + 'A'.repeat(200),
    'https://EXAMPLE.com/path?private=yes',
  )
  assert.equal(fields.referrer_domain, 'example.com')
  assert.equal(fields.utm_source, 'news_letter')
  assert.equal(fields.utm_medium, 'e-mail')
  assert.equal(fields.utm_campaign.length, 128)
  assert.equal(JSON.stringify(fields).includes('/path'), false)
})

test('sensitive UTM values are omitted from request payload fields', () => {
  const sensitiveValues = [
    'fan@example.com',
    'campaign\nAuthorization: Bearer abc',
    'Bearer abcdefghijklmnop',
    'access_token=abcdefgh',
    'client-secret-value',
    'password=hunter2',
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue',
    'sk-live_abcdefghijklmnopqrstuvwxyz',
    'AKIAABCDEFGHIJKLMNOP',
  ]
  for (const sensitiveValue of sensitiveValues) {
    const search = `?utm_source=newsletter&utm_medium=${encodeURIComponent(sensitiveValue)}`
    const fields = acquisitionFields(
      search,
    )
    assert.deepEqual(fields, { utm_source: 'newsletter' })
    assert.equal(JSON.stringify(fields).includes(sensitiveValue), false)
    const payload = buildPageView({
      hostname: 'baseballos.app', pathname: '/dashboard', search,
      storage: storage(), now: 1, cryptoObject: cryptoSequence(),
    })
    assert.equal(payload.utm_source, 'newsletter')
    assert.equal('utm_medium' in payload, false)
  }
})

test('traffic requests follow configured and same-origin API resolution', () => {
  assert.equal(trafficPageViewUrl('https://api.baseballos.app'), 'https://api.baseballos.app/api/traffic/page-view')
  assert.equal(trafficPageViewUrl(''), '/api/traffic/page-view')
  assert.equal(trafficPageViewUrl(undefined), '/api/traffic/page-view')
  const urls = []
  const fetchImpl = (url) => {
    urls.push(url)
    return Promise.resolve({ ok: true })
  }
  sendPageView({ view_id: 'configured' }, {
    fetchImpl,
    storage: storage(),
    configuredBackendOrigin: 'https://api.baseballos.app',
  })
  sendPageView({ view_id: 'same-origin' }, {
    fetchImpl,
    storage: storage(),
    configuredBackendOrigin: '',
  })
  assert.deepEqual(urls, [
    'https://api.baseballos.app/api/traffic/page-view',
    '/api/traffic/page-view',
  ])
})

test('immediate StrictMode duplicates are suppressed while later history revisits record', () => {
  const calls = []
  const input = {
    locationKey: 'entry-1', hostname: 'baseballos.app', pathname: '/dashboard', search: '',
    storage: storage(), now: 1, cryptoObject: cryptoSequence(),
    fetchImpl: (...args) => { calls.push(args); return Promise.resolve({ ok: true }) },
  }
  assert.equal(observeTrafficRoute(input), true)
  assert.equal(observeTrafficRoute(input), false)
  assert.equal(observeTrafficRoute({ ...input, locationKey: 'entry-2' }), true)
  assert.equal(observeTrafficRoute(input), true)
  assert.equal(observeTrafficRoute(input), false)
  assert.equal(calls.length, 3)
})

test('meaningful hash and canonical context changes record without rerender duplicates', () => {
  const calls = []
  const input = {
    locationKey: 'bullpen-entry', hostname: 'baseballos.app', pathname: '/bullpen',
    search: '?view=board&team=BOS&source=dashboard', hash: '', storage: storage(), now: 1,
    cryptoObject: cryptoSequence(),
    fetchImpl: (...args) => { calls.push(args); return Promise.resolve({ ok: true }) },
  }
  assert.equal(observeTrafficRoute(input), true)
  assert.equal(observeTrafficRoute(input), false)
  assert.equal(observeTrafficRoute({ ...input, hash: '#team-relief-work' }), true)
  assert.equal(observeTrafficRoute({ ...input, hash: '#team-relief-work' }), false)
  assert.equal(observeTrafficRoute({ ...input, search: '?view=board&team=NYY&source=dashboard' }), true)
  assert.equal(observeTrafficRoute({ ...input, search: '?view=compare&team_a=BOS&team_b=NYY' }), true)
  assert.equal(calls.length, 4)
})

test('request failure is isolated and request excludes token and raw query from body', () => {
  const local = storage()
  local.setItem(api.AUTH_TOKEN_STORAGE_KEY, 'secret-bearer')
  const payload = buildPageView({
    hostname: 'baseballos.app', pathname: '/dashboard',
    search: '?utm_source=source&private=do-not-send', storage: local, now: 1,
    cryptoObject: cryptoSequence(),
  })
  let request
  assert.doesNotThrow(() => sendPageView(payload, {
    storage: local,
    fetchImpl: (url, options) => {
      request = { url, options }
      throw new Error('offline')
    },
  }))
  assert.equal(request.url, '/api/traffic/page-view')
  assert.equal(request.options.keepalive, true)
  assert.equal(request.options.headers.Authorization, 'Bearer secret-bearer')
  assert.equal(request.options.body.includes('secret-bearer'), false)
  assert.equal(request.options.body.includes('do-not-send'), false)
  assert.equal(JSON.parse(request.options.body).utm_source, 'source')
})
