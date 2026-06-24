import assert from 'node:assert/strict'
import test, { after, afterEach } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
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

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const {
  SIGN_IN_ERROR,
  SIGN_IN_IDLE,
  SIGN_IN_SUCCESS,
  SignInView,
  submitSignInRequest,
} = await server.ssrLoadModule('/src/components/auth/SignIn.jsx')
const {
  VERIFY_FAILURE,
  VERIFY_LOADING,
  VERIFY_SUCCESS,
  VerifySignInView,
  safeVerifyRedirect,
  verifySignInToken,
} = await server.ssrLoadModule('/src/components/auth/VerifySignIn.jsx')
const { SidebarAccountBlock } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const {
  AUTH_TOKEN_STORAGE_KEY,
  isAuthTokenStorageEvent,
  readAuthToken,
  storeAuthToken,
} = await server.ssrLoadModule('/src/utils/api.js')
const {
  authStateForTokenCheck,
  initialAuthState,
  normalizeAuthResponse,
  signOutAuthState,
} = await server.ssrLoadModule('/src/hooks/useAuthState.js')

const htmlIncludes = (html, text) => html.includes(text)
const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)
const routeByPath = (path) => APP_ROUTES.find(route => route.path === path)

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
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) {
      this.type = type
      this.detail = init.detail
    }
  }
  globalThis.window = {
    localStorage: storage,
    dispatchEvent() {
      return true
    },
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

test('sign-in and verify routes are registered', () => {
  assert.equal(routeByPath('/signin')?.Component?.name, 'SignIn')
  assert.equal(routeByPath('/auth/verify')?.Component?.name, 'VerifySignIn')
})

test('sign-in form renders the minimal email link request', () => {
  const html = render(React.createElement(SignInView, {
    email: '',
    onEmailChange: () => {},
    onSubmit: () => {},
    status: SIGN_IN_IDLE,
  }))

  assert.ok(htmlIncludes(html, 'Enter your email and we&#x27;ll send a sign-in link.'))
  assert.ok(htmlIncludes(html, 'type="email"'))
  assert.ok(htmlIncludes(html, 'Send sign-in link'))
})

test('sign-in submit calls the request-link helper with trimmed email', async () => {
  const statuses = []
  let requestedEmail = null

  const submitted = await submitSignInRequest({
    email: ' fan@example.com ',
    requestLink: async (email) => {
      requestedEmail = email
      return { ok: true }
    },
    setStatus: status => statuses.push(status),
  })

  assert.equal(submitted, true)
  assert.equal(requestedEmail, 'fan@example.com')
  assert.deepEqual(statuses, ['loading', SIGN_IN_SUCCESS])
})

test('sign-in success and error messages render', () => {
  const successHtml = render(React.createElement(SignInView, {
    email: 'fan@example.com',
    onEmailChange: () => {},
    onSubmit: () => {},
    status: SIGN_IN_SUCCESS,
  }))
  const errorHtml = render(React.createElement(SignInView, {
    email: 'fan@example.com',
    onEmailChange: () => {},
    onSubmit: () => {},
    status: SIGN_IN_ERROR,
    error: new Error('network'),
  }))

  assert.ok(htmlIncludes(successHtml, 'Check your email for a sign-in link.'))
  assert.ok(htmlIncludes(errorHtml, 'We could not send a sign-in link. Please try again.'))
})

test('sign-in submit exposes a generic error state on request failure', async () => {
  const statuses = []
  let capturedError = null

  const submitted = await submitSignInRequest({
    email: 'fan@example.com',
    requestLink: async () => {
      throw new Error('failed')
    },
    setStatus: status => statuses.push(status),
    setError: error => {
      capturedError = error
    },
  })

  assert.equal(submitted, false)
  assert.equal(capturedError.message, 'failed')
  assert.deepEqual(statuses, ['loading', SIGN_IN_ERROR])
})

test('verify view renders loading, success, failure, and missing-token states', async () => {
  const loadingHtml = render(React.createElement(VerifySignInView, { status: VERIFY_LOADING }))
  const successHtml = render(React.createElement(VerifySignInView, { status: VERIFY_SUCCESS }))
  const failureHtml = render(React.createElement(VerifySignInView, { status: VERIFY_FAILURE }))
  const statuses = []
  let capturedError = null

  const verified = await verifySignInToken({
    token: '',
    verifyLink: async () => {
      throw new Error('should not verify')
    },
    setStatus: status => statuses.push(status),
    setError: error => {
      capturedError = error
    },
  })

  assert.ok(htmlIncludes(loadingHtml, 'Verifying sign-in link...'))
  assert.ok(htmlIncludes(successHtml, 'Signed in'))
  assert.ok(htmlIncludes(failureHtml, 'This sign-in link is invalid or expired.'))
  assert.equal(verified, false)
  assert.equal(capturedError.message, 'missing_token')
  assert.deepEqual(statuses, [VERIFY_FAILURE])
})

test('verify helper stores success state and failure state', async () => {
  const successStatuses = []
  const failureStatuses = []
  let verifiedToken = null

  assert.equal(await verifySignInToken({
    token: ' magic-token ',
    verifyLink: async (token) => {
      verifiedToken = token
      return { token: 'bearer-token' }
    },
    setStatus: status => successStatuses.push(status),
  }), true)
  assert.equal(verifiedToken, 'magic-token')
  assert.deepEqual(successStatuses, [VERIFY_LOADING, VERIFY_SUCCESS])

  assert.equal(await verifySignInToken({
    token: 'bad-token',
    verifyLink: async () => {
      throw new Error('expired')
    },
    setStatus: status => failureStatuses.push(status),
  }), false)
  assert.deepEqual(failureStatuses, [VERIFY_LOADING, VERIFY_FAILURE])
})

test('verify redirect accepts only app-relative next paths', () => {
  assert.equal(safeVerifyRedirect('/'), '/')
  assert.equal(safeVerifyRedirect('/stories?team=ACE'), '/stories?team=ACE')
  assert.equal(safeVerifyRedirect('https://example.com'), '/')
  assert.equal(safeVerifyRedirect('//example.com'), '/')
  assert.equal(safeVerifyRedirect('javascript:alert(1)'), '/')
  assert.equal(safeVerifyRedirect('/\\example.com'), '/')
})

test('auth-state helpers normalize anonymous, loading, and authenticated states', () => {
  const storage = createStorage()
  installWindow(storage)

  assert.equal(initialAuthState().loading, false)
  storeAuthToken('token', storage)
  assert.equal(initialAuthState().loading, true)
  assert.deepEqual(normalizeAuthResponse({ authenticated: false }), {
    loading: false,
    authenticated: false,
    user: null,
    error: null,
  })
  assert.deepEqual(normalizeAuthResponse({
    authenticated: true,
    user: { id: 1, email: 'fan@example.com' },
  }), {
    loading: false,
    authenticated: true,
    user: { id: 1, email: 'fan@example.com' },
    error: null,
  })
})

test('signed-in auth state stays visible during background token checks', () => {
  const authenticatedState = {
    loading: false,
    authenticated: true,
    user: { id: 1, email: 'fan@example.com' },
    error: new Error('stale'),
  }

  assert.deepEqual(authStateForTokenCheck(authenticatedState), {
    loading: false,
    authenticated: true,
    user: { id: 1, email: 'fan@example.com' },
    error: null,
  })
  assert.deepEqual(authStateForTokenCheck({
    loading: false,
    authenticated: false,
    user: null,
    error: null,
  }), {
    loading: true,
    authenticated: false,
    user: null,
    error: null,
  })
})

test('auth storage refresh is limited to bearer token changes', () => {
  const preferredTeamEvent = Object.create({ key: 'baseballos.preferredTeam' })

  assert.equal(isAuthTokenStorageEvent({ key: AUTH_TOKEN_STORAGE_KEY }), true)
  assert.equal(isAuthTokenStorageEvent({ key: null }), true)
  assert.equal(isAuthTokenStorageEvent({ key: 'baseballos.preferredTeam' }), false)
  assert.equal(isAuthTokenStorageEvent(preferredTeamEvent), false)
})

test('Sidebar anonymous state shows the sign-in entry', () => {
  const html = render(React.createElement(SidebarAccountBlock, {
    authState: {
      loading: false,
      authenticated: false,
      user: null,
    },
  }))

  assert.ok(htmlIncludes(html, 'Account'))
  assert.ok(htmlIncludes(html, 'href="/signin"'))
  assert.ok(htmlIncludes(html, 'Sign in'))
})

test('Sidebar authenticated state shows email and sign out', () => {
  const html = render(React.createElement(SidebarAccountBlock, {
    authState: {
      loading: false,
      authenticated: true,
      user: { email: 'fan@example.com' },
      signOut: () => {},
    },
  }))

  assert.ok(htmlIncludes(html, 'Signed in'))
  assert.ok(htmlIncludes(html, 'fan@example.com'))
  assert.ok(htmlIncludes(html, 'Sign out'))
})

test('Sidebar keeps signed-in account visible during background refresh', () => {
  const html = render(React.createElement(SidebarAccountBlock, {
    authState: {
      loading: true,
      authenticated: true,
      user: { email: 'fan@example.com' },
      signOut: () => {},
    },
  }))

  assert.ok(htmlIncludes(html, 'Signed in'))
  assert.ok(htmlIncludes(html, 'fan@example.com'))
  assert.ok(!htmlIncludes(html, 'Checking sign-in...'))
})

test('sign-out auth state clears the stored bearer token', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('bearer-token', storage)
  installFetch(async (url, options) => {
    assert.equal(url, '/api/auth/logout')
    assert.equal(options.method, 'POST')
    return { json: { ok: true } }
  })

  const state = await signOutAuthState()

  assert.equal(readAuthToken(storage), null)
  assert.equal(storage.has(AUTH_TOKEN_STORAGE_KEY), false)
  assert.equal(state.authenticated, false)
})

test('sign-out auth state clears local token even if logout request fails', async () => {
  const storage = createStorage()
  installWindow(storage)
  storeAuthToken('bearer-token', storage)
  console.error = () => {}
  installFetch(async () => ({
    ok: false,
    status: 500,
    statusText: 'Server Error',
    json: { error: 'failed' },
  }))

  const state = await signOutAuthState()

  assert.equal(readAuthToken(storage), null)
  assert.equal(state.authenticated, false)
})
