const ACRONYM_TOKENS = new Set([
  'api',
  'id',
  'json',
  'mlb',
  'ui',
  'url',
])

// The explanation-key label table is gone. It renamed engine KEYS into
// reader-facing text, which made this file a second author of public
// vocabulary, and it only ever covered the handful of keys somebody happened to
// notice — every other key was title-cased into public copy by accident
// (`deterministic_sample_state` -> "Deterministic Sample State").
//
// Structured explanation items now carry a governed `label` from the backend
// contract that already validates their type. Read it with `explanationLabel`
// below; it returns null rather than inventing a heading, so an unlabelled item
// is withheld instead of leaking an internal key.
//
// `humanizeLabel` remains for bounded UI enum chips the frontend legitimately
// formats (scope, subject type, severity). It must not be used to name a
// structured explanation item.
function normalizeDisplayString(value) {
  return String(value || '')
    .replace(/^explains[_-]+/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * The backend-authored public label for a structured explanation item.
 *
 * Returns null when the item carries no governed label. Callers withhold the
 * heading in that case; they never fall back to `limitation_type`, `code`,
 * `evidence_type`, or any other internal key.
 */
export function explanationLabel(item) {
  const label = item && typeof item === 'object' ? item.label : null
  if (typeof label !== 'string' || !label.trim()) return null
  // A governed label that is itself shaped like an internal key is a backend
  // defect, not a heading. Withhold rather than publish it.
  return isTechnicalKey(label) ? null : label
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

// An internal key appearing as a VALUE is not reader copy either. It used to be
// title-cased into public text through the same table that named explanation
// items, which is how `trust_metadata` reached readers as "Visibility Detail".
// Nothing in the frontend is entitled to name it, so it is withheld.
const WITHHELD = Symbol('withheld-technical-value')

function displayScalar(value) {
  if (value === false) return 'false'
  if (value === true) return 'true'
  if (value === 0) return '0'
  if (typeof value === 'number') return value.toLocaleString()
  if (typeof value !== 'string') return String(value)
  return isTechnicalKey(value) ? WITHHELD : value
}

// Internal-key values are dropped from the summary entirely: a row reading
// "Affected Area: <withheld>" would be noise, and naming the key would be the
// leak this package exists to close. The raw object stays available under the
// component's explicit "Technical details" disclosure.
function summarizeEntry(key, item, fallback) {
  // Scalars go through displayScalar directly so the withheld sentinel is still
  // visible here; summarizeDisplayValue converts it to the fallback for callers
  // outside this module.
  const summarized = isPlainObject(item) || Array.isArray(item)
    ? summarizeDisplayValue(item, fallback)
    : displayScalar(item)
  if (summarized === WITHHELD) return null
  return `${humanizeLabel(key)}: ${summarized}`
}

export function summarizeDisplayValue(value, fallback = 'Not provided') {
  if (value === null || value === undefined || value === '') return fallback
  if (Array.isArray(value)) {
    if (!value.length) return 'None'
    const items = value
      .map(item => (isPlainObject(item) || Array.isArray(item)
        ? summarizeDisplayValue(item, fallback)
        : displayScalar(item)))
      .filter(item => item !== WITHHELD)
    return items.length ? items.join(', ') : 'None'
  }
  if (!isPlainObject(value)) {
    const scalar = displayScalar(value)
    // Callers outside this module get the fallback, never the sentinel.
    return scalar === WITHHELD ? fallback : scalar
  }

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
    .map(key => summarizeEntry(key, value[key], fallback))
    .filter(Boolean)

  if (entries.length) return entries.join('; ')

  return Object.entries(value)
    .filter(([, item]) => !isPlainObject(item) && !Array.isArray(item))
    .slice(0, 4)
    .map(([key, item]) => summarizeEntry(key, item, fallback))
    .filter(Boolean)
    .join('; ') || fallback
}

export function technicalJson(value) {
  if (!isPlainObject(value) && !Array.isArray(value)) return String(value)
  return JSON.stringify(value, null, 2)
}
