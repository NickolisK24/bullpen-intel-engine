import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
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
  default: ExplanationDisclosure,
} = await server.ssrLoadModule('/src/components/explanations/ExplanationDisclosure.jsx')
const {
  normalizeV4ExplanationApiResponse,
} = await server.ssrLoadModule('/src/utils/api.js')
const pitcherDetailSource = await readFile(
  new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
  'utf8',
)

const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const withoutGovernanceSentence = html => visibleText(html)
  .replace(/No ranking, selection, recommendation, or prediction applied\./g, '')
  .replace(/BaseballOS explains the current bullpen read without choosing an arm or calling an outcome\./g, '')
  .replace(/Team order No bullpen order made Pitcher choice No pitcher chosen Arm choice No arm chosen Outcome call No outcome call made Decision scope Explanation only Advice scope No bullpen advice/g, '')

const governance = {
  ranking_applied: false,
  selection_made: false,
  recommendation_made: false,
  prediction_made: false,
  decision_scope: 'explanation_only',
  advice_scope: 'none',
}

const explanationEnvelope = {
  status: 'ok',
  explanation_type: 'team_readiness_explanation',
  certification_status: 'certified_with_non_blocking_observations',
  route_status: 'internal_uncertified_route',
  explanation: {
    explanation_id: 'readiness_state_example',
    scope: 'readiness_state',
    subject_type: 'bullpen',
    subject_id: 'team:SEA',
    state_explained: 'operationally_stable',
    summary: 'This readiness state reflects workload, freshness, coverage, and trust evidence.',
    primary_reasons: [
      {
        code: 'READINESS_DEGRADED_BY_LIMITATIONS',
        scope: 'readiness_state',
        label: 'Readiness context reviewed',
        summary: 'Visible readiness context explains the current state.',
        display_safe: true,
        certification_required: true,
      },
    ],
    supporting_evidence: [
      {
        evidence_id: 'availability_distribution_total',
        evidence_type: 'count',
        label: 'Availability distribution total',
        value: 6,
        unit: 'pitchers',
        source: 'team_operations_readiness',
        freshness: {
          status: 'current',
          data_through: '2026-06-03',
          last_sync_at: '2026-06-03T11:45:00Z',
        },
        trust_status: 'trusted',
        impact: 'Supports team-level readiness context.',
      },
      {
        evidence_id: 'data_limited_status_code',
        evidence_type: 'data_limited_status_code',
        label: 'data_limited_status_code',
        value: {
          affected_area: 'trust_metadata',
          category: 'trust',
          status_code: 'trust_metadata_limited',
        },
        source: 'explains_workload_state',
        trust_status: 'trusted',
        impact: 'Explains a workload-state limitation without changing the decision boundary.',
      },
    ],
    limitations: [
      {
        limitation_type: 'insufficient_context',
        severity: 'informational',
        summary: 'Manager intent is not represented.',
        affected_scopes: ['readiness_state'],
        requires_refusal: false,
      },
    ],
    freshness: {
      status: 'current',
      data_through: '2026-06-03',
      last_sync_at: '2026-06-03T11:45:00Z',
    },
    trust: {
      status: 'trusted',
      source: 'team_operations_readiness',
      certification_status: 'certified_with_non_blocking_observations',
    },
    confidence: {
      level: 'medium',
      summary: 'Explanation confidence reflects current source evidence.',
    },
    governance,
    generated_at: '2026-06-03T12:00:00Z',
  },
  governance,
}

const failClosedEnvelope = {
  status: 'unavailable',
  explanation_type: 'team_readiness_explanation',
  certification_status: 'certified_with_non_blocking_observations',
  route_status: 'internal_uncertified_route',
  explanation: null,
  limitations: [
    {
      limitation_type: 'missing_data',
      label: 'Required explanation inputs are unavailable',
      summary: 'Team Operations readiness explanation cannot be generated because source records are unavailable.',
    },
  ],
  refusal: {
    refused: true,
    reason_code: 'missing_source_data',
    summary: 'Team Operations readiness explanation cannot be generated because source records are unavailable.',
  },
  governance,
}

function renderDisclosure(props = {}) {
  return renderToStaticMarkup(
    React.createElement(ExplanationDisclosure, {
      fetchExplanation: async () => normalizeV4ExplanationApiResponse(explanationEnvelope),
      ...props,
    }),
  )
}

test('renders compact Why this state action while explanation details stay closed', () => {
  const html = renderDisclosure({
    initialExplanation: normalizeV4ExplanationApiResponse(explanationEnvelope),
  })

  assert.ok(htmlIncludes(html, 'Why this state?'))
  assert.ok(htmlIncludes(html, 'aria-expanded="false"'))
  assert.ok(htmlIncludes(html, 'Explanation'))
  assert.equal(htmlIncludes(html, explanationEnvelope.explanation.summary), false)
  assert.equal(htmlIncludes(html, 'Availability Distribution Total'), false)
})

test('opens explanation detail surface with summary and reasons when disclosure is active', () => {
  const html = renderDisclosure({
    initialOpen: true,
    initialExplanation: normalizeV4ExplanationApiResponse(explanationEnvelope),
  })

  assert.ok(htmlIncludes(html, 'Hide Explanation'))
  assert.ok(htmlIncludes(html, 'aria-expanded="true"'))
  assert.ok(htmlIncludes(html, explanationEnvelope.explanation.summary))
  assert.ok(htmlIncludes(html, 'Readiness Context Reviewed'))
  assert.ok(htmlIncludes(html, 'Visible readiness context explains the current state.'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'Freshness / Visibility / Workload Read'))
})

test('renders evidence and limitations inside the opened explanation detail surface', () => {
  const html = renderDisclosure({
    initialOpen: true,
    initialExplanation: normalizeV4ExplanationApiResponse(explanationEnvelope),
  })

  assert.ok(htmlIncludes(html, 'Availability Distribution Total'))
  assert.ok(htmlIncludes(html, '6 pitchers'))
  assert.ok(htmlIncludes(html, 'Data Limited Status Code'))
  assert.ok(htmlIncludes(html, 'Technical key: data_limited_status_code'))
  assert.ok(htmlIncludes(html, 'Source key: explains_workload_state'))
  assert.ok(htmlIncludes(html, 'Affected Area: Visibility Detail'))
  assert.ok(htmlIncludes(html, 'Technical details'))
  assert.ok(htmlIncludes(html, 'Manager intent is not represented.'))
  assert.ok(htmlIncludes(html, 'medium'))
  assert.ok(htmlIncludes(html, 'current'))
})

test('renders fail-closed explanation responses safely', () => {
  const html = renderDisclosure({
    initialOpen: true,
    initialExplanation: normalizeV4ExplanationApiResponse(failClosedEnvelope),
  })

  assert.ok(htmlIncludes(html, 'Explanation unavailable for this state.'))
  assert.ok(htmlIncludes(html, 'Required explanation inputs were unavailable for this request.'))
  assert.ok(htmlIncludes(html, 'missing_source_data'))
  assert.ok(htmlIncludes(html, 'Required Explanation Inputs Are Unavailable'))
  assert.ok(htmlIncludes(html, 'BaseballOS explains the current bullpen read without choosing an arm or calling an outcome.'))
})

test('keeps governance-safe messaging visible in explanation details', () => {
  const html = renderDisclosure({
    initialOpen: true,
    initialExplanation: normalizeV4ExplanationApiResponse(explanationEnvelope),
  })

  assert.ok(htmlIncludes(html, 'Decision Boundary'))
  assert.ok(htmlIncludes(html, 'BaseballOS explains the current bullpen read without choosing an arm or calling an outcome.'))
  assert.ok(htmlIncludes(html, 'Team order'))
  assert.ok(htmlIncludes(html, 'Pitcher choice'))
  assert.ok(htmlIncludes(html, 'Arm choice'))
  assert.ok(htmlIncludes(html, 'Outcome call'))
  assert.ok(htmlIncludes(html, 'Explanation only'))
  assert.ok(htmlIncludes(html, 'No bullpen advice'))
})

test('does not render prohibited explanation surface language', () => {
  const html = renderDisclosure({
    initialOpen: true,
    initialExplanation: normalizeV4ExplanationApiResponse(explanationEnvelope),
  })
  const text = withoutGovernanceSentence(html)

  assert.equal(/\buse this pitcher\b|\bbest option\b|\bpreferred arm\b|\brecommended arm\b|\bchoose this option\b|\bmatchup advice\b/i.test(text), false)
})

test('Pitcher detail uses the certified availability explanation client without dashboard card stacks', () => {
  assert.ok(pitcherDetailSource.includes('getAvailabilityExplanation'))
  assert.ok(pitcherDetailSource.includes('Why this availability?'))
  assert.equal(/per-pitcher explanation card stacks|comparison/i.test(pitcherDetailSource), false)
})
