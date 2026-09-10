import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

// Set a build-time admin token BEFORE loading the module. This proves that even
// if an operator defines VITE_ADMIN_API_TOKEN, the frontend never reads it or
// attaches an X-Admin-Token header, so the admin secret cannot reach the
// browser bundle. Privileged endpoints stay backend/curl/server-only.
process.env.VITE_ADMIN_API_TOKEN = 'this-admin-token-must-never-leak'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const apiModule = await server.ssrLoadModule('/src/utils/api.js')
const { checkHealth, evaluateRecommendationCandidate } = apiModule

function withFetchSpy(t) {
  const originalFetch = globalThis.fetch
  const calls = []
  t.after(() => {
    globalThis.fetch = originalFetch
  })
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return { ok: true, json: async () => ({}) }
  }
  return calls
}

function headerKeys(headers = {}) {
  return Object.keys(headers).map(key => key.toLowerCase())
}

test('GET requests never attach an X-Admin-Token header', async (t) => {
  const calls = withFetchSpy(t)
  await checkHealth()

  assert.equal(calls.length, 1)
  assert.ok(
    !headerKeys(calls[0].options.headers).includes('x-admin-token'),
    'health request must not send X-Admin-Token',
  )
})

test('POST requests never attach an X-Admin-Token header', async (t) => {
  const calls = withFetchSpy(t)
  await evaluateRecommendationCandidate({
    pitcher_id: 1,
    pitcher_name: 'Example Pitcher',
    availability: { availability_status: 'Available' },
  })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].options.method, 'POST')
  assert.ok(
    !headerKeys(calls[0].options.headers).includes('x-admin-token'),
    'POST request must not send X-Admin-Token',
  )
})

test('no privileged recalculate helper is exported from the api module', () => {
  assert.equal(
    apiModule.recalculateFatigue,
    undefined,
    'recalculateFatigue must not exist: recalculation is admin-token-gated and backend-only',
  )
})

test('the api module source never references the admin token env var or header', async () => {
  const moduleUrl = new URL('../src/utils/api.js', import.meta.url)
  const { readFile } = await import('node:fs/promises')
  const source = await readFile(moduleUrl, 'utf8')

  assert.ok(
    !source.includes('VITE_ADMIN_API_TOKEN'),
    'api.js must not read VITE_ADMIN_API_TOKEN',
  )
  assert.ok(
    !/headers\[['"]X-Admin-Token['"]\]/.test(source),
    'api.js must not inject an X-Admin-Token header',
  )
})
