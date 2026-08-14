import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

// The explanation envelope carried five enum fields that the component
// title-cased straight into reader copy:
//
//   scope           readiness_state            -> "Readiness State"
//   state_explained operationally_stable       -> "Operationally Stable"
//   subject_type    bullpen                    -> "Bullpen"
//   route_status    internal_uncertified_route -> "Internal Uncertified Route"
//   severity        informational              -> "Informational"
//
// plus two more found while inventorying: evidence `source`, which read as
// "Team Operations Readiness", and the trust block's `certification_status`,
// which shipped the raw `certified_with_non_blocking_observations`.
//
// None answered a reader question. Scope and subject are established by the
// surface that opens the disclosure; state_explained is the internal readiness
// code whose public name is a Team State published by a different authority;
// route_status is which internal route served the request; severity is the
// engine's own priority word. They are removed rather than renamed -- a chip
// does not earn its place by being available.

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: ExplanationDisclosure } = await server.ssrLoadModule(
  '/src/components/explanations/ExplanationDisclosure.jsx',
)
const { normalizeV4ExplanationApiResponse } = await server.ssrLoadModule('/src/utils/api.js')

const governance = {
  ranking_applied: false,
  selection_made: false,
  recommendation_made: false,
  prediction_made: false,
  decision_scope: 'explanation_only',
  advice_scope: 'none',
}

function envelope(over = {}, explanationOver = {}) {
  return {
    status: 'ok',
    explanation_type: 'team_readiness_explanation',
    certification_status: 'certified_with_non_blocking_observations',
    route_status: 'internal_uncertified_route',
    explanation: {
      explanation_id: 'envelope_example',
      scope: 'readiness_state',
      subject_type: 'bullpen',
      subject_id: 'team:SEA',
      state_explained: 'operationally_stable',
      summary: 'This readiness state reflects workload, freshness, coverage, and trust evidence.',
      primary_reasons: [{
        code: 'READINESS_DEGRADED_BY_LIMITATIONS',
        scope: 'readiness_state',
        label: 'Readiness context reviewed',
        summary: 'Visible readiness context explains the current state.',
        display_safe: true,
        certification_required: true,
      }],
      supporting_evidence: [{
        evidence_id: 'availability_distribution_total',
        evidence_type: 'count',
        label: 'Availability distribution total',
        value: 6,
        unit: 'pitchers',
        source: 'team_operations_readiness',
        freshness: { status: 'current', data_through: '2026-06-03', last_sync_at: '2026-06-03T11:45:00Z' },
        trust_status: 'trusted',
        impact: 'Supports team-level readiness context.',
      }],
      limitations: [{
        limitation_type: 'insufficient_context',
        severity: 'informational',
        summary: 'Manager intent is not represented.',
        affected_scopes: ['readiness_state'],
        requires_refusal: false,
      }],
      freshness: { status: 'current', data_through: '2026-06-03', last_sync_at: '2026-06-03T11:45:00Z' },
      trust: {
        status: 'trusted',
        source: 'team_operations_readiness',
        certification_status: 'certified_with_non_blocking_observations',
      },
      confidence: { level: 'medium', summary: 'Explanation confidence reflects current source evidence.' },
      governance,
      generated_at: '2026-06-03T12:00:00Z',
      ...explanationOver,
    },
    governance,
    ...over,
  }
}

function render(payload = envelope()) {
  return renderToStaticMarkup(React.createElement(ExplanationDisclosure, {
    initialOpen: true,
    initialExplanation: normalizeV4ExplanationApiResponse(payload),
  }))
}

const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

// ── field disposition matrix ────────────────────────────────────────────────
//
// Every envelope field that reaches this surface has one explicit disposition.
// A newly added field does not become reader-visible by default: it will not
// appear here, and the sweep below fails if its raw value shows up.

const DISPOSITION = [
  { field: 'scope', raw: 'readiness_state', prettified: 'Readiness State', rendered: false },
  { field: 'stateExplained', raw: 'operationally_stable', prettified: 'Operationally Stable', rendered: false },
  { field: 'subjectType', raw: 'bullpen', prettified: 'Bullpen', rendered: false },
  { field: 'routeStatus', raw: 'internal_uncertified_route', prettified: 'Internal Uncertified Route', rendered: false },
  { field: 'severity', raw: 'informational', prettified: 'Informational', rendered: false },
  { field: 'evidence.source', raw: 'team_operations_readiness', prettified: 'Team Operations Readiness', rendered: false },
  { field: 'trust.certification_status', raw: 'certified_with_non_blocking_observations', prettified: 'Certified With Non Blocking Observations', rendered: false },
]

for (const { field, prettified, rendered } of DISPOSITION) {
  test(`${field} is not published as reader copy`, () => {
    const text = visibleText(render())
    assert.equal(text.includes(prettified), rendered, `${field}: "${prettified}"`)
  })
}

test('no internal enum from the disposition matrix appears prettified', () => {
  const text = visibleText(render())
  const leaked = DISPOSITION.filter(d => !d.rendered && text.includes(d.prettified))
  assert.deepEqual(leaked.map(d => d.field), [])
})

test('the raw certification contract state never ships to a reader', () => {
  // This one was not title-cased; it was printed verbatim under a reader label.
  assert.equal(visibleText(render()).includes('certified_with_non_blocking_observations'), false)
})

// ── trust and transparency are preserved ────────────────────────────────────

test('reasons, evidence and limitations all still reach the reader', () => {
  const text = visibleText(render())
  for (const kept of [
    'This readiness state reflects workload, freshness, coverage, and trust evidence.',
    'Readiness context reviewed',
    'Visible readiness context explains the current state.',
    'Availability distribution total',
    'Manager intent is not represented.',
  ]) {
    assert.ok(text.includes(kept), kept)
  }
})

test('freshness, visibility and read confidence survive', () => {
  const text = visibleText(render())
  for (const kept of ['Freshness', 'Data Through', 'Last Sync', 'Visibility',
    'Read Confidence', 'Explanation confidence reflects current source evidence.']) {
    assert.ok(text.includes(kept), kept)
  }
})

test('the decision boundary strip is untouched', () => {
  const text = visibleText(render())
  assert.ok(text.includes('Decision boundary'))
  assert.ok(text.includes('No pitcher chosen'))
  assert.ok(text.includes('No outcome call made'))
})

test('a refused explanation still explains itself', () => {
  const html = render({
    status: 'unavailable',
    explanation: null,
    limitations: [{
      limitation_type: 'missing_data',
      label: 'Required explanation inputs are unavailable',
      summary: 'Source records are unavailable.',
    }],
    refusal: { refused: true, reason_code: 'missing_source_data', summary: 'Source records are unavailable.' },
  })
  const text = visibleText(html)
  assert.ok(text.includes('Required explanation inputs are unavailable'))
  assert.ok(text.includes('Source records are unavailable.'))
  // The refusal reason code is disclosed as a technical key, never as copy.
  assert.equal(text.includes('Missing Source Data'), false)
})

// ── unknown values fail closed ──────────────────────────────────────────────

test('an unrecognised enum value is not prettified into copy', () => {
  const text = visibleText(render(envelope({ route_status: 'some_future_route_state' }, {
    scope: 'some_future_scope',
    subject_type: 'some_future_subject',
    state_explained: 'some_future_state',
  })))
  for (const invented of ['Some Future Route State', 'Some Future Scope',
    'Some Future Subject', 'Some Future State']) {
    assert.equal(text.includes(invented), false, invented)
  }
})

test('an unrecognised enum value is not printed raw either', () => {
  const text = visibleText(render(envelope({ route_status: 'some_future_route_state' })))
  assert.equal(text.includes('some_future_route_state'), false)
})

// ── structural guard against the inference returning ────────────────────────

test('the explanation surface holds no raw-enum formatting helper', async () => {
  const source = await readFile(
    new URL('../src/components/explanations/ExplanationDisclosure.jsx', import.meta.url),
    'utf8',
  )
  const code = source
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .split('\n')
    .filter(line => !line.trim().startsWith('//'))
    .join('\n')

  assert.equal(/\btitleCase\s*\(/.test(code), false, 'titleCase call')
  assert.equal(/\bhumanizeLabel\s*\(/.test(code), false, 'humanizeLabel call')
  for (const banned of ['explanationView.scope', 'explanationView.stateExplained',
    'explanationView.subjectType', 'explanationView.routeStatus']) {
    assert.equal(code.includes(banned), false, banned)
  }
})

// ── determinism ─────────────────────────────────────────────────────────────

test('the rendered surface is byte-identical across repeats', () => {
  const runs = [render(), render(), render()]
  assert.equal(runs[0], runs[1])
  assert.equal(runs[1], runs[2])
})
