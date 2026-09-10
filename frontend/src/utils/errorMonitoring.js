const SENSITIVE_KEY_PATTERN = /(email|token|secret|password|authorization|cookie|payload|body|request)/i
const SENSITIVE_QUERY_PATTERN = /([?&](?:email|token|auth|authorization|secret|password)=)[^&#\s]+/gi
const EMAIL_PATTERN = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi
const DEDUPE_WINDOW_MS = 5000
const MAX_EXTRA_DEPTH = 4
const MAX_EXTRA_ITEMS = 25
const recentErrorKeys = new Map()

let activeMonitoring = null
let removeGlobalHandlers = null

function now(runtime = globalThis) {
  return runtime?.Date?.now ? runtime.Date.now() : Date.now()
}

function cleanString(value) {
  return String(value || '')
    .replace(SENSITIVE_QUERY_PATTERN, '$1[redacted]')
    .replace(EMAIL_PATTERN, '[redacted-email]')
    .slice(0, 1000)
}

function cleanRoute(value) {
  const route = cleanString(value)
  return route.split('?')[0].split('#')[0] || '/'
}

function cleanErrorMessage(error) {
  if (error instanceof Error) return cleanString(error.message || error.name)
  if (typeof error === 'string') return cleanString(error)
  if (error && typeof error.message === 'string') return cleanString(error.message)
  return 'Unknown frontend error'
}

function cleanErrorName(error) {
  if (error instanceof Error && error.name) return cleanString(error.name)
  if (error && typeof error.name === 'string') return cleanString(error.name)
  return 'Error'
}

function cleanStack(error) {
  if (error instanceof Error && error.stack) return cleanString(error.stack).slice(0, 5000)
  if (error && typeof error.stack === 'string') return cleanString(error.stack).slice(0, 5000)
  return undefined
}

export function sanitizeMonitoringContext(value, depth = 0) {
  if (value == null) return value
  if (depth >= MAX_EXTRA_DEPTH) return '[truncated]'
  if (typeof value === 'string') return cleanString(value)
  if (typeof value === 'number' || typeof value === 'boolean') return value
  if (value instanceof Error) {
    return {
      name: cleanErrorName(value),
      message: cleanErrorMessage(value),
    }
  }
  if (Array.isArray(value)) {
    return value.slice(0, MAX_EXTRA_ITEMS).map(item => sanitizeMonitoringContext(item, depth + 1))
  }
  if (typeof value === 'object') {
    return Object.entries(value).slice(0, MAX_EXTRA_ITEMS).reduce((safe, [key, child]) => {
      if (SENSITIVE_KEY_PATTERN.test(key)) {
        safe[key] = '[redacted]'
        return safe
      }
      safe[key] = sanitizeMonitoringContext(child, depth + 1)
      return safe
    }, {})
  }
  return cleanString(value)
}

function normalizeEnvironment(env = {}) {
  const explicit = env.VITE_APP_ENV || env.APP_ENV || env.MODE
  return cleanString(explicit || 'development').toLowerCase()
}

function shouldEnableMonitoring(config) {
  if (!config?.dsn) return false
  return ['production', 'staging', 'preview'].includes(config.environment)
}

export function getErrorMonitoringConfig(env = import.meta.env || {}) {
  const environment = normalizeEnvironment(env)
  const dsn = String(env.VITE_SENTRY_DSN || '').trim()
  const release = cleanString(env.VITE_RELEASE_SHA || '').trim()
  return {
    dsn,
    environment,
    release,
    enabled: shouldEnableMonitoring({ dsn, environment }),
    provider: dsn ? 'sentry' : 'none',
  }
}

export function sentryEnvelopeUrlFromDsn(dsn) {
  try {
    const parsed = new URL(dsn)
    const parts = parsed.pathname.split('/').filter(Boolean)
    const projectId = parts.pop()
    if (!projectId) return null
    const basePath = parts.length ? `/${parts.join('/')}` : ''
    return `${parsed.origin}${basePath}/api/${projectId}/envelope/`
  } catch {
    return null
  }
}

function randomHex(length = 32, runtime = globalThis) {
  const crypto = runtime?.crypto
  if (crypto?.getRandomValues) {
    const bytes = new Uint8Array(length / 2)
    crypto.getRandomValues(bytes)
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  }
  return Array.from({ length }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}

function errorDedupeKey(error, context = {}) {
  const source = context.source || 'frontend'
  return [
    source,
    cleanErrorName(error),
    cleanErrorMessage(error),
    cleanStack(error) || '',
  ].join('|')
}

function shouldSendError(error, context, runtime) {
  const timestamp = now(runtime)
  const key = errorDedupeKey(error, context)
  const previous = recentErrorKeys.get(key)
  if (previous && timestamp - previous < DEDUPE_WINDOW_MS) return false
  recentErrorKeys.set(key, timestamp)

  for (const [storedKey, storedAt] of recentErrorKeys.entries()) {
    if (timestamp - storedAt > DEDUPE_WINDOW_MS) recentErrorKeys.delete(storedKey)
  }
  return true
}

export function buildSentryEnvelope({ config, error, context = {}, runtime = globalThis }) {
  const event = {
    event_id: randomHex(32, runtime),
    timestamp: new Date(now(runtime)).toISOString(),
    platform: 'javascript',
    level: 'error',
    environment: config.environment,
    release: config.release || undefined,
    tags: {
      app: 'baseballos',
      source: cleanString(context.source || 'frontend'),
    },
    exception: {
      values: [{
        type: cleanErrorName(error),
        value: cleanErrorMessage(error),
        stacktrace: cleanStack(error) ? { frames: [] } : undefined,
      }],
    },
    extra: sanitizeMonitoringContext({
      ...context,
      route: cleanRoute(context.route || runtime?.location?.pathname || '/'),
      stack: cleanStack(error),
    }),
  }

  const envelopeHeader = JSON.stringify({
    sent_at: event.timestamp,
    dsn: config.dsn,
  })
  const itemHeader = JSON.stringify({ type: 'event' })
  return `${envelopeHeader}\n${itemHeader}\n${JSON.stringify(event)}`
}

async function sendSentryEnvelope({ config, error, context, runtime, send }) {
  const endpoint = sentryEnvelopeUrlFromDsn(config.dsn)
  if (!endpoint) return false
  const body = buildSentryEnvelope({ config, error, context, runtime })
  const sender = send || runtime?.fetch
  if (typeof sender !== 'function') return false
  await sender(endpoint, {
    method: 'POST',
    body,
    keepalive: true,
    headers: {
      'Content-Type': 'application/x-sentry-envelope',
    },
  })
  return true
}

export function createErrorMonitoring(config = {}, runtime = globalThis, send = null) {
  const enabled = shouldEnableMonitoring(config)

  return {
    enabled,
    config: { ...config, enabled },
    capture(error, context = {}) {
      if (!enabled) return false
      try {
        if (!shouldSendError(error, context, runtime)) return false
        void sendSentryEnvelope({ config, error, context, runtime, send }).catch(() => {})
        return true
      } catch {
        return false
      }
    },
  }
}

export function captureFrontendError(error, context = {}) {
  try {
    if (!activeMonitoring) return false
    return activeMonitoring.capture(error, context)
  } catch {
    return false
  }
}

function addGlobalHandlers(runtime, monitor) {
  if (!monitor?.enabled || typeof runtime?.addEventListener !== 'function') return null

  const handleError = (event) => {
    const error = event?.error || new Error(event?.message || 'Unhandled frontend error')
    monitor.capture(error, {
      source: 'window_error',
      route: runtime?.location?.pathname || '/',
      filename: event?.filename,
      lineno: event?.lineno,
      colno: event?.colno,
    })
  }

  const handleRejection = (event) => {
    const reason = event?.reason instanceof Error
      ? event.reason
      : new Error(cleanErrorMessage(event?.reason || 'Unhandled promise rejection'))
    monitor.capture(reason, {
      source: 'unhandled_rejection',
      route: runtime?.location?.pathname || '/',
    })
  }

  runtime.addEventListener('error', handleError)
  runtime.addEventListener('unhandledrejection', handleRejection)

  return () => {
    if (typeof runtime.removeEventListener !== 'function') return
    runtime.removeEventListener('error', handleError)
    runtime.removeEventListener('unhandledrejection', handleRejection)
  }
}

export function initializeErrorMonitoring({
  env = import.meta.env || {},
  runtime = globalThis,
  send = null,
} = {}) {
  if (removeGlobalHandlers) {
    removeGlobalHandlers()
    removeGlobalHandlers = null
  }

  const config = getErrorMonitoringConfig(env)
  activeMonitoring = createErrorMonitoring(config, runtime, send)
  removeGlobalHandlers = addGlobalHandlers(runtime, activeMonitoring)

  if (!activeMonitoring.enabled && env.DEV && !config.dsn && runtime?.console?.info) {
    runtime.console.info('BaseballOS frontend error monitoring is disabled: VITE_SENTRY_DSN is not set.')
  }

  return activeMonitoring
}

export function resetErrorMonitoringForTests() {
  if (removeGlobalHandlers) removeGlobalHandlers()
  removeGlobalHandlers = null
  activeMonitoring = null
  recentErrorKeys.clear()
}
