import assert from 'node:assert/strict'
import test, { after } from 'node:test'
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

const { createRequestGuard, getFetchStatus, isCanceledFetch } = await server.ssrLoadModule('/src/hooks/useFetch.js')

test('fetch status distinguishes fresh data, stale data with error, and no-data error', () => {
  assert.deepEqual(
    getFetchStatus({ data: { ok: true }, error: null, loading: false }),
    { hasData: true, noDataError: false, staleWithError: false },
  )

  assert.deepEqual(
    getFetchStatus({ data: { ok: true }, error: 'Network failed', loading: false }),
    { hasData: true, noDataError: false, staleWithError: true },
  )

  assert.deepEqual(
    getFetchStatus({ data: null, error: 'Network failed', loading: false }),
    { hasData: false, noDataError: true, staleWithError: false },
  )
})

test('request guard rejects late responses after a dependency change or newer retry', () => {
  const guard = createRequestGuard()
  const firstTeam = guard.begin()
  const secondTeam = guard.begin()

  assert.equal(guard.isCurrent(firstTeam), false)
  assert.equal(guard.isCurrent(secondTeam), true)

  guard.invalidate()
  assert.equal(guard.isCurrent(secondTeam), false)
})

test('request cancellation is not classified as a user-facing failure', () => {
  const canceled = new Error('canceled')
  canceled.name = 'AbortError'
  assert.equal(isCanceledFetch(canceled), true)
  assert.equal(isCanceledFetch({ status: 'canceled' }), true)
  assert.equal(isCanceledFetch(new Error('network failed')), false)
})
