export const PRODUCT_ANON_ID_STORAGE_KEY = 'baseballos.productAnonId'

let volatileAnonId = null

function getBrowserStorage() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage || null
  } catch {
    return null
  }
}

export function normalizeProductAnonId(value) {
  const text = value == null ? '' : String(value).trim()
  if (!text || text.includes('@')) return null
  const safe = text.replace(/[^a-zA-Z0-9._:-]/g, '').slice(0, 64)
  return safe || null
}

function randomSegment() {
  try {
    const cryptoApi = globalThis.crypto
    if (cryptoApi?.randomUUID) return cryptoApi.randomUUID()
    if (cryptoApi?.getRandomValues) {
      const bytes = new Uint8Array(16)
      cryptoApi.getRandomValues(bytes)
      return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
    }
  } catch {
    // Fall back below when browser crypto is unavailable.
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 18)}`
}

export function createProductAnonId() {
  return normalizeProductAnonId(`anon:${randomSegment()}`)
}

export function readProductAnonId(storage = getBrowserStorage()) {
  if (!storage) return volatileAnonId
  try {
    return normalizeProductAnonId(storage.getItem(PRODUCT_ANON_ID_STORAGE_KEY))
  } catch {
    return volatileAnonId
  }
}

export function getOrCreateProductAnonId(storage = getBrowserStorage()) {
  const existing = readProductAnonId(storage)
  if (existing) return existing

  const next = createProductAnonId()
  volatileAnonId = next
  if (!storage) return next

  try {
    storage.setItem(PRODUCT_ANON_ID_STORAGE_KEY, next)
  } catch {
    // Storage can be disabled; the in-memory id still connects this page load.
  }
  return next
}
