import assert from 'node:assert/strict'
import test, { after, beforeEach } from 'node:test'
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

const cacheModule = await server.ssrLoadModule('/src/utils/publicResponseCache.js')
const api = await server.ssrLoadModule('/src/utils/api.js')
const originalFetch = globalThis.fetch

beforeEach(() => {
  api.clearPublicDeliveryStateForTests()
  globalThis.fetch = originalFetch
})

function payload(snapshotId) {
  return {
    status: 'ok',
    version: '1.0.0',
    snapshot: {
      snapshot_id: snapshotId,
      sync_run_id: snapshotId + 100,
      represented_date: `2026-09-${String(snapshotId).padStart(2, '0')}`,
      payload_version: 1,
    },
    data: { snapshotId },
  }
}

function jsonResponse(body) {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => body,
  }
}

test('current alias reuses one publication then discovers a forced publication turnover', async () => {
  const responses = [payload(1), payload(2)]
  let calls = 0
  globalThis.fetch = async () => jsonResponse(responses[calls++])

  const first = await api.getHomeProjection()
  const revisit = await api.getHomeProjection()
  const afterTurnover = await api.getHomeProjection({ forceRefresh: true })

  assert.equal(calls, 2)
  assert.strictEqual(revisit, first)
  assert.equal(first.snapshot.snapshot_id, 1)
  assert.equal(afterTurnover.snapshot.snapshot_id, 2)
})

test('simultaneous consumers dedupe while one canceled consumer does not cancel the other', async () => {
  let calls = 0
  let resolveFetch
  globalThis.fetch = () => {
    calls += 1
    return new Promise(resolve => { resolveFetch = resolve })
  }
  const firstController = new AbortController()
  const secondController = new AbortController()
  const first = api.getLeagueProjection({ signal: firstController.signal, forceRefresh: true })
  const second = api.getLeagueProjection({ signal: secondController.signal, forceRefresh: true })

  firstController.abort()
  resolveFetch(jsonResponse(payload(3)))

  await assert.rejects(first, error => error?.name === 'AbortError')
  assert.equal((await second).snapshot.snapshot_id, 3)
  assert.equal(calls, 1)
})

test('timeout aborts the underlying read and reports a scoped timeout', async () => {
  globalThis.fetch = (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => {
      const error = new Error('aborted')
      error.name = 'AbortError'
      reject(error)
    }, { once: true })
  })

  await assert.rejects(
    api.getHomeProjection({ timeoutMs: 5, forceRefresh: true, silent: true }),
    error => error?.status === 'timeout',
  )
})

test('query cache key includes values but normalizes parameter order', async () => {
  let calls = 0
  globalThis.fetch = async () => {
    calls += 1
    return jsonResponse({ status: 'available', data: [], meta: { page: 1 } })
  }

  await api.getRelieverFinder({ q: 'smith', page: 1 })
  await api.getRelieverFinder({ page: 1, q: 'smith' })

  assert.equal(calls, 1)
})

test('cache refuses unavailable payloads and evicts least-recently-used entries', () => {
  let clock = 100
  const cache = cacheModule.createPublicResponseCache({ maxEntries: 2, clock: () => clock })
  cache.set('home', payload(1), { ttlMs: 50 })
  cache.set('league', payload(2), { ttlMs: 50 })
  assert.equal(cache.get('home').snapshot.snapshot_id, 1)
  cache.set('stories', payload(3), { ttlMs: 50 })

  assert.equal(cache.size(), 2)
  assert.equal(cache.get('league'), null)
  assert.equal(cache.get('home').snapshot.snapshot_id, 1)

  cache.set('trust', { status: 'snapshot_unavailable' }, { ttlMs: 50 })
  assert.equal(cache.get('trust'), null)
  clock = 151
  assert.equal(cache.get('home'), null)
})
