import assert from 'node:assert/strict'
import test from 'node:test'

import {
  explanationLabel,
  humanizeLabel,
  summarizeDisplayValue,
} from '../src/utils/displayText.js'

// The frontend used to name structured explanation items itself. A small table
// renamed four engine keys, and every other key was title-cased into public copy
// by accident -- `deterministic_sample_state` reached readers as "Deterministic
// Sample State". The backend contract that already validates these types now
// authors their labels, and this file is the contract that the browser only
// renders them.

const GOVERNED_LABELS = [
  'Required explanation inputs are unavailable',
  'Required explanation inputs are stale',
  'Required explanation inputs have partial coverage',
  'Requested explanation scope is unavailable',
  'Explanation confidence is limited',
  'Explanation context is insufficient',
]

const INTERNAL_KEYS = [
  'deterministic_sample_state',
  'live_observation_source_unavailable',
  'forbidden_request_parameter',
  'unsupported_request_parameter',
  'invalid_supplied_state',
  'insufficient_context',
  'uncertified_source',
  'some_internal_reason',
  'trust_metadata',
  'trust_metadata_limited',
  'freshness_metadata',
  'fail_closed',
]

// ── governed labels pass through byte-for-byte ──────────────────────────────

for (const label of GOVERNED_LABELS) {
  test(`governed label passes through unchanged: ${label}`, () => {
    assert.equal(explanationLabel({ label }), label)
  })
}

test('a governed label is never re-cased on its way to the reader', () => {
  const label = 'Required explanation inputs are unavailable'
  assert.equal(explanationLabel({ label }), label)
  assert.notEqual(explanationLabel({ label }), humanizeLabel(label))
})

// ── unknown keys fail closed ────────────────────────────────────────────────

for (const key of INTERNAL_KEYS) {
  test(`an unlabelled item named by an internal key is withheld: ${key}`, () => {
    assert.equal(explanationLabel({ limitation_type: key }), null)
    assert.equal(explanationLabel({ code: key }), null)
    assert.equal(explanationLabel({ evidence_type: key }), null)
  })
}

test('a label that is itself an internal key is withheld', () => {
  assert.equal(explanationLabel({ label: 'data_limited_status_code' }), null)
  assert.equal(explanationLabel({ label: 'trust_metadata' }), null)
})

test('an absent, blank, or non-string label is withheld', () => {
  for (const item of [{}, null, undefined, 'string', 42, { label: '' },
    { label: '   ' }, { label: null }, { label: 7 }]) {
    assert.equal(explanationLabel(item), null)
  }
})

// ── the removed table is really gone ────────────────────────────────────────

test('the historical explanation-key mappings no longer fire', () => {
  // Each of these once produced reader-facing copy from an engine key.
  assert.notEqual(humanizeLabel('trust_metadata'), 'Visibility Detail')
  assert.notEqual(humanizeLabel('trust_metadata_limited'), 'Visibility Detail Limited')
  assert.notEqual(humanizeLabel('freshness_metadata'), 'Freshness Detail')
  assert.notEqual(humanizeLabel('fail_closed'), 'Source Boundary')
})

test('displayText source carries no explanation-label translation table', async () => {
  const { readFile } = await import('node:fs/promises')
  const source = await readFile(
    new URL('../src/utils/displayText.js', import.meta.url), 'utf8',
  )
  assert.equal(source.includes('DISPLAY_LABEL_REPLACEMENTS'), false)
  // Scan code only: the comments deliberately record what was removed and why.
  const code = source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter(line => !line.trim().startsWith('//') && !line.trim().startsWith('*'))
    .join('\n')
    .toLowerCase()
  for (const invented of ['visibility detail', 'source boundary', 'freshness detail',
    'team order', 'pitcher choice', 'decision boundary detail']) {
    assert.equal(code.includes(invented), false, invented)
  }
})

test('ExplanationDisclosure never names an item from an internal key', async () => {
  const { readFile } = await import('node:fs/promises')
  const source = await readFile(
    new URL('../src/components/explanations/ExplanationDisclosure.jsx', import.meta.url),
    'utf8',
  )
  for (const fallback of ['item.label || item.code',
    'item.label || item.evidence_type',
    'item.label || item.limitation_type',
    'humanizeLabel(labelSource)',
    'humanizeLabel(refusal.reason_code)']) {
    assert.equal(source.includes(fallback), false, fallback)
  }
})

// ── internal keys as VALUES are withheld too ────────────────────────────────

test('an internal key appearing as a value is withheld, not renamed', () => {
  const summary = summarizeDisplayValue({ affected_area: 'trust_metadata', count: 6 })
  assert.equal(summary.includes('Visibility Detail'), false)
  assert.equal(summary.includes('Trust Metadata'), false)
  assert.equal(summary.includes('trust_metadata'), false)
  assert.equal(summary, 'Count: 6')
})

test('withholding a technical value never blanks a row that has real content', () => {
  assert.equal(
    summarizeDisplayValue({ status: 'limited', affected_area: 'trust_metadata' }),
    'Status: limited',
  )
})

test('an object of only technical values falls back rather than leaking', () => {
  const summary = summarizeDisplayValue({ affected_area: 'trust_metadata' })
  assert.equal(summary.includes('trust_metadata'), false)
  assert.equal(summary, 'Not provided')
})

test('the withheld sentinel never escapes to a caller', () => {
  for (const value of ['trust_metadata', { affected_area: 'fail_closed' },
    ['trust_metadata']]) {
    const summary = summarizeDisplayValue(value)
    assert.equal(typeof summary, 'string')
    assert.equal(summary.includes('Symbol'), false)
  }
})

// ── real, non-semantic formatting still works ───────────────────────────────

test('humanizeLabel still formats bounded UI enum tokens', () => {
  assert.equal(humanizeLabel('availability_state'), 'Availability State')
  assert.equal(humanizeLabel('mlb_api'), 'MLB API')
  assert.equal(humanizeLabel(''), 'Not provided')
})

test('ordinary public values are untouched', () => {
  assert.equal(summarizeDisplayValue({ summary: 'Manager intent is not represented.' }),
    'Summary: Manager intent is not represented.')
  assert.equal(summarizeDisplayValue(6), '6')
  assert.equal(summarizeDisplayValue([]), 'None')
})

// ── determinism ─────────────────────────────────────────────────────────────

test('label resolution is deterministic', () => {
  const item = { label: 'Explanation context is insufficient' }
  const runs = [explanationLabel(item), explanationLabel(item), explanationLabel(item)]
  assert.equal(new Set(runs).size, 1)
})
