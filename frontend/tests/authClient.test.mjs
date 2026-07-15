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
  globalThis.fetch = originalFetch
  globalThis.window = originalWindow
  globalThis.CustomEvent = originalCustomEvent
  console.error = originalConsoleError
})

const api = await server.ssrLoadModule('/src/utils/api.js')
const {
  AUTH_TOKEN_STORAGE_KEY,
  checkHealth,
  clearAuthToken,
  deleteFollowedTeam,
  followTeam,
  getCurrentUser,
  getFollowedTeams,
  logoutAuth,
  readAuthToken,
  requestMagicLink,
  setPrimaryTeam,
  storeAuthToken,
  verifyMagicLink,
} = api

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
    has(key) {
      return values.has(key)
    },
  }
}

function installWindow(storage) {
  const events = []
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) {
      this.type = type
      this.detail = init.detail
    }
  }
  globalThis.window = {
    localStorage: storage,
    dispatchEvent(event) {
      events.push(event)
      return true
    },
    addEventListener() {},
    removeEventListener() {},
  }
  return events
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

test('auth token helpers store, read, and clear the local bearer token', () => {
  const storage = createStorage()
  const events = installWindow(storage)

  assert.equal(storeAuthToken(' token-123 ', storage), 'token-123')
  assert.equal(readAuthToken(storage), 'token-123')
  assert.equal(storage.getItem(AUTH_TOKEN_STORAGE_KEY), 'token-123')
  assert.equal(clearAuthToken(storage), true)
  assert.equal(readAuthToken(storage), null)
  assert.equal(events.at(-1).detail.token, null)
})

test('bearer token is attached to API requests', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('bearer-token', storage)
  const calls = installFetch(async () => ({ json: { ok: true } }))

  await checkHealth()

  assert.equal(calls[0].url, '/api/health')
  assert.equal(calls[0].options.headers.Authorization, 'Bearer bearer-token')
})

test('/api/auth/me helper returns authenticated identity responses', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('identity-token', storage)
  installFetch(async (url) => {
    assert.equal(url, '/api/auth/me')
    return {
      json: {
        authenticated: true,
        user: { id: 7, email: 'fan@example.com' },
      },
    }
  })

  const identity = await getCurrentUser()

  assert.equal(identity.authenticated, true)
  assert.equal(identity.user.email, 'fan@example.com')
})

test('magic-link helpers request and verify auth without sign-in UI', async () => {
  const storage = createStorage()
  installWindow(storage)
  const calls = installFetch(async (url, options) => {
    if (url === '/api/auth/request-link') {
      assert.equal(options.method, 'POST')
      assert.deepEqual(JSON.parse(options.body), { email: 'fan@example.com' })
      return { json: { ok: true } }
    }
    assert.equal(url, '/api/auth/verify')
    assert.equal(options.headers.Authorization, undefined)
    const verifyPayload = JSON.parse(options.body)
    assert.deepEqual(verifyPayload, { token: 'magic-token' })
    return { json: { token: 'bearer-token', user: { id: 1 } } }
  })

  await requestMagicLink('fan@example.com')
  const verified = await verifyMagicLink('magic-token')

  assert.equal(calls.length, 2)
  assert.equal(verified.token, 'bearer-token')
  assert.equal(readAuthToken(storage), 'bearer-token')
})

test('server follow helpers call the expected /api/me endpoints', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('team-token', storage)
  const calls = installFetch(async (url, options) => {
    if (url === '/api/me/teams' && (!options.method || options.method === 'GET')) {
      return { json: { teams: [], primary_team_id: null } }
    }
    if (url === '/api/me/teams' && options.method === 'POST') {
      assert.deepEqual(JSON.parse(options.body), { team_id: 118, is_primary: true })
      return { json: { teams: [{ team_id: 118, is_primary: true }], primary_team_id: 118 } }
    }
    if (url === '/api/me/teams/118') {
      assert.equal(options.method, 'DELETE')
      return { json: { teams: [], primary_team_id: null } }
    }
    assert.equal(url, '/api/me/primary-team')
    assert.equal(options.method, 'PUT')
    assert.deepEqual(JSON.parse(options.body), { team_id: 147 })
    return { json: { teams: [{ team_id: 147, is_primary: true }], primary_team_id: 147 } }
  })

  await getFollowedTeams()
  await followTeam(118, { isPrimary: true })
  await deleteFollowedTeam(118)
  await setPrimaryTeam(147)

  assert.deepEqual(calls.map(call => call.url), [
    '/api/me/teams',
    '/api/me/teams',
    '/api/me/teams/118',
    '/api/me/primary-team',
  ])
})

test('401 API responses clear the stored token for safe fallback', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('expired-token', storage)
  console.error = () => {}
  installFetch(async () => ({
    ok: false,
    status: 401,
    statusText: 'Unauthorized',
    json: { error: 'authentication_required' },
  }))

  await assert.rejects(() => getFollowedTeams(), /API 401/)
  assert.equal(readAuthToken(storage), null)
})

test('logout helper clears the token even though server logout is stateless', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('logout-token', storage)
  installFetch(async (url, options) => {
    assert.equal(url, '/api/auth/logout')
    assert.equal(options.method, 'POST')
    return { json: { ok: true } }
  })

  await logoutAuth()

  assert.equal(readAuthToken(storage), null)
})
