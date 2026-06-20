const ACRONYM_TOKENS = new Set([
  'api',
  'id',
  'json',
  'mlb',
  'ui',
  'url',
])

const DISPLAY_LABEL_REPLACEMENTS = new Map([
  ['trust metadata', 'visibility detail'],
  ['trust metadata limited', 'visibility detail limited'],
  ['governance metadata', 'decision boundary detail'],
  ['freshness metadata', 'freshness detail'],
  ['fail closed', 'source boundary'],
  ['ranking applied', 'team order'],
  ['selection made', 'pitcher choice'],
])

function normalizeDisplayString(value) {
  const normalized = String(value || '')
    .replace(/^explains[_-]+/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return DISPLAY_LABEL_REPLACEMENTS.get(normalized.toLowerCase()) || normalized
}

function formatToken(token) {
  const lower = token.toLowerCase()
  if (/^v\d+$/.test(lower)) return lower.toUpperCase()
  if (ACRONYM_TOKENS.has(lower)) return lower.toUpperCase()
  return `${lower.slice(0, 1).toUpperCase()}${lower.slice(1)}`
}

export function humanizeLabel(value, fallback = 'Not provided') {
  const normalized = normalizeDisplayString(value)
  if (!normalized) return fallback
  return normalized.split(' ').map(formatToken).join(' ')
}

export function isPlainObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
}

export function isTechnicalKey(value) {
  if (typeof value !== 'string') return false
  const text = value.trim()
  if (!text || /\s/.test(text)) return false
  return /_/.test(text) || /^[a-z]+(?:-[a-z]+)+$/.test(text)
}

export function shouldShowTechnicalKey(value) {
  return isTechnicalKey(value) && humanizeLabel(value) !== value
}

function displayScalar(value) {
  if (value === false) return 'false'
  if (value === true) return 'true'
  if (value === 0) return '0'
  if (typeof value === 'number') return value.toLocaleString()
  if (typeof value !== 'string') return String(value)
  return isTechnicalKey(value) ? humanizeLabel(value) : value
}

export function summarizeDisplayValue(value, fallback = 'Not provided') {
  if (value === null || value === undefined || value === '') return fallback
  if (Array.isArray(value)) {
    return value.length ? value.map(item => summarizeDisplayValue(item, fallback)).join(', ') : 'None'
  }
  if (!isPlainObject(value)) return displayScalar(value)

  const priorityKeys = [
    'label',
    'summary',
    'message',
    'reason',
    'status',
    'state',
    'status_code',
    'value',
    'count',
    'category',
    'affected_area',
    'source',
    'source_type',
  ]
  const entries = priorityKeys
    .filter(key => Object.prototype.hasOwnProperty.call(value, key))
    .filter(key => !isPlainObject(value[key]) && !Array.isArray(value[key]))
    .map(key => `${humanizeLabel(key)}: ${summarizeDisplayValue(value[key], fallback)}`)

  if (entries.length) return entries.join('; ')

  return Object.entries(value)
    .filter(([, item]) => !isPlainObject(item) && !Array.isArray(item))
    .slice(0, 4)
    .map(([key, item]) => `${humanizeLabel(key)}: ${summarizeDisplayValue(item, fallback)}`)
    .join('; ') || fallback
}

export function technicalJson(value) {
  if (!isPlainObject(value) && !Array.isArray(value)) return String(value)
  return JSON.stringify(value, null, 2)
}
