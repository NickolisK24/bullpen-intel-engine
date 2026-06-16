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

const { getFetchStatus } = await server.ssrLoadModule('/src/hooks/useFetch.js')

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
