import assert from 'node:assert/strict'
import test, { after, afterEach } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
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

const {
  AppErrorFallback,
  default: AppErrorBoundary,
} = await server.ssrLoadModule('/src/components/AppErrorBoundary.jsx')
const {
  buildSentryEnvelope,
  captureFrontendError,
  createErrorMonitoring,
  getErrorMonitoringConfig,
  initializeErrorMonitoring,
  resetErrorMonitoringForTests,
  sanitizeMonitoringContext,
  sentryEnvelopeUrlFromDsn,
} = await server.ssrLoadModule('/src/utils/errorMonitoring.js')

afterEach(() => {
  resetErrorMonitoringForTests()
})

function createRuntime() {
  const handlers = new Map()
  return {
    location: { pathname: '/trust', search: '?email=fan@example.com' },
    Date: { now: () => 1770000000000 },
    crypto: {
      getRandomValues(bytes) {
        bytes.fill(1)
        return bytes
      },
    },
    console: { info() {} },
    addEventListener(type, handler) {
      handlers.set(type, handler)
    },
    removeEventListener(type) {
      handlers.delete(type)
    },
    handlers,
  }
}

test('monitoring config safely no-ops when provider env is missing', () => {
  const config = getErrorMonitoringConfig({ MODE: 'production' })
  const monitor = createErrorMonitoring(config, createRuntime())

  assert.equal(config.provider, 'none')
  assert.equal(config.enabled, false)
  assert.equal(monitor.enabled, false)
  assert.equal(monitor.capture(new Error('boom')), false)
})

test('capture function does not throw when monitoring has not been initialized', () => {
  assert.doesNotThrow(() => captureFrontendError(new Error('not initialized')))
  assert.equal(captureFrontendError(new Error('not initialized')), false)
})

test('configured monitoring queues sanitized Sentry envelopes without sensitive fields', async () => {
  const runtime = createRuntime()
  const calls = []
  const send = async (url, options) => calls.push({ url, options })
  const monitor = initializeErrorMonitoring({
    env: {
      MODE: 'production',
      VITE_APP_ENV: 'production',
      VITE_RELEASE_SHA: 'abc123',
      VITE_SENTRY_DSN: 'https://public@example.sentry.io/12345',
    },
    runtime,
    send,
  })

  const captured = monitor.capture(new Error('Failed for fan@example.com'), {
    source: 'react_error_boundary',
    route: '/trust?token=secret-token&email=fan@example.com',
    email: 'fan@example.com',
    token: 'secret-token',
    payload: { password: 'pw', nested: 'keep this' },
  })
  await new Promise(resolve => setTimeout(resolve, 0))

  assert.equal(captured, true)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, 'https://example.sentry.io/api/12345/envelope/')
  assert.equal(calls[0].options.headers['Content-Type'], 'application/x-sentry-envelope')
  assert.equal(calls[0].options.keepalive, true)

  const body = calls[0].options.body
  assert.equal(body.includes('fan@example.com'), false)
  assert.equal(body.includes('secret-token'), false)
  assert.equal(body.includes('"email":"[redacted]"'), true)
  assert.equal(body.includes('"token":"[redacted]"'), true)
  assert.equal(body.includes('"payload":"[redacted]"'), true)
  assert.equal(body.includes('"release":"abc123"'), true)
  assert.equal(body.includes('"environment":"production"'), true)
})

test('monitoring capture de-duplicates repeated boundary reports', async () => {
  const runtime = createRuntime()
  const calls = []
  const send = async (url, options) => calls.push({ url, options })
  const monitor = initializeErrorMonitoring({
    env: {
      MODE: 'production',
      VITE_APP_ENV: 'production',
      VITE_SENTRY_DSN: 'https://public@example.sentry.io/12345',
    },
    runtime,
    send,
  })
  const error = new Error('same error')

  assert.equal(monitor.capture(error, { source: 'react_error_boundary' }), true)
  assert.equal(monitor.capture(error, { source: 'react_error_boundary' }), false)
  await new Promise(resolve => setTimeout(resolve, 0))

  assert.equal(calls.length, 1)
})

test('global runtime hooks register only when monitoring is enabled', () => {
  const disabledRuntime = createRuntime()
  initializeErrorMonitoring({
    env: { MODE: 'production' },
    runtime: disabledRuntime,
  })
  assert.equal(disabledRuntime.handlers.size, 0)

  const enabledRuntime = createRuntime()
  initializeErrorMonitoring({
    env: {
      MODE: 'production',
      VITE_APP_ENV: 'production',
      VITE_SENTRY_DSN: 'https://public@example.sentry.io/12345',
    },
    runtime: enabledRuntime,
    send: async () => {},
  })

  assert.ok(enabledRuntime.handlers.has('error'))
  assert.ok(enabledRuntime.handlers.has('unhandledrejection'))
})

test('global runtime hooks capture unhandled errors and promise rejections', async () => {
  const runtime = createRuntime()
  const calls = []
  initializeErrorMonitoring({
    env: {
      MODE: 'production',
      VITE_APP_ENV: 'production',
      VITE_SENTRY_DSN: 'https://public@example.sentry.io/12345',
    },
    runtime,
    send: async (url, options) => calls.push({ url, options }),
  })

  runtime.handlers.get('error')({
    error: new Error('window failed'),
    filename: 'https://baseballos.app/assets/app.js?token=secret',
    lineno: 12,
    colno: 4,
  })
  runtime.handlers.get('unhandledrejection')({
    reason: new Error('promise failed'),
  })
  await new Promise(resolve => setTimeout(resolve, 0))

  assert.equal(calls.length, 2)
  assert.ok(calls[0].options.body.includes('"source":"window_error"'))
  assert.ok(calls[1].options.body.includes('"source":"unhandled_rejection"'))
})

test('error boundary renders normal children when no error occurs', () => {
  const html = renderToStaticMarkup(
    React.createElement(AppErrorBoundary, null, React.createElement('div', null, 'Normal BaseballOS view')),
  )

  assert.equal(html.includes('Normal BaseballOS view'), true)
  assert.equal(html.includes('Something went wrong while loading this BaseballOS view.'), false)
})

test('error boundary renders stable fallback and reports caught render errors', () => {
  const calls = []
  const boundary = new AppErrorBoundary({
    captureError: (error, context) => calls.push({ error, context }),
    onReload: () => {},
    children: React.createElement('div', null, 'Broken child'),
  })
  boundary.state = AppErrorBoundary.getDerivedStateFromError(new Error('render failed'))
  boundary.componentDidCatch(new Error('render failed'), { componentStack: 'Component stack' })

  const html = renderToStaticMarkup(boundary.render())

  assert.equal(html.includes('Something went wrong while loading this BaseballOS view.'), true)
  assert.equal(html.includes('Try refreshing the page.'), true)
  assert.equal(html.includes('Reload'), true)
  assert.equal(html.includes('current'), false)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].context.source, 'react_error_boundary')
  assert.equal(calls[0].context.component_stack, 'Component stack')
})

test('fallback view can render directly for static checks', () => {
  const html = renderToStaticMarkup(React.createElement(AppErrorFallback, { onReload: () => {} }))

  assert.equal(html.includes('BaseballOS'), true)
  assert.equal(html.includes('Something went wrong while loading this BaseballOS view.'), true)
  assert.equal(html.includes('Try refreshing the page.'), true)
})

test('sensitive monitoring context fields are redacted', () => {
  assert.deepEqual(sanitizeMonitoringContext({
    email: 'fan@example.com',
    route: '/trust?email=fan@example.com',
    nested: {
      Authorization: 'Bearer secret',
      safe: 'contact fan@example.com later',
    },
  }), {
    email: '[redacted]',
    route: '/trust?email=[redacted]',
    nested: {
      Authorization: '[redacted]',
      safe: 'contact [redacted-email] later',
    },
  })
})

test('Sentry envelope helpers tolerate malformed provider config', () => {
  assert.equal(sentryEnvelopeUrlFromDsn('not a dsn'), null)
  assert.equal(sentryEnvelopeUrlFromDsn('https://public@example.sentry.io/123'), 'https://example.sentry.io/api/123/envelope/')
  assert.doesNotThrow(() => buildSentryEnvelope({
    config: {
      dsn: 'https://public@example.sentry.io/123',
      environment: 'production',
      release: '',
    },
    error: new Error('safe'),
    context: {},
    runtime: createRuntime(),
  }))
})
