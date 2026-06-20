import assert from 'node:assert/strict'
import test, { after } from 'node:test'
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
  default: OperationalReadinessSection,
} = await server.ssrLoadModule('/src/components/dashboard/OperationalReadinessSection.jsx')

const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const sanitizedGovernanceText = html => visibleText(html)
  .replace(/No ranking, selection, recommendation, or prediction applied\./g, '')
  .replace(/Context only - BaseballOS does not choose the next arm\./g, '')
  .replace(/ranking_applied/g, '')
  .replace(/selection_made/g, '')

const v2State = {
  contractState: 'available',
  isContractSafe: true,
  isFailClosed: false,
  governance: {
    rankingApplied: false,
    selectionMade: false,
    trustRankingApplied: false,
    trustSelectionMade: false,
  },
  freshness: {
    freshness_state: 'current',
    data_through: '2026-06-03',
    sync_timestamp: '2026-06-03T11:55:00Z',
  },
  trustMetadata: {
    scope: 'bullpen_state',
    confidence: 'medium',
    data_state: 'complete',
    ranking_applied: false,
    selection_made: false,
  },
  bullpenState: {
    status: 'available_context',
    stress_level: 'elevated',
    readiness_summary: 'Current availability inventory can be summarized.',
    inventory_summary: [],
    candidate_groups: [],
    team_context: {},
  },
  limitations: [],
  explanations: [
    {
      message: 'Bullpen inventory is summarized from current availability evidence.',
    },
  ],
  refusalReasons: [],
}

const readinessState = {
  contractState: 'available',
  sourceContractState: 'available',
  isContractSafe: true,
  isDegraded: false,
  isRefused: false,
  isFailClosed: false,
  isInternal: true,
  isInternalUncertified: true,
  governance: {
    rankingApplied: false,
    selectionMade: false,
    trustRankingApplied: false,
    trustSelectionMade: false,
  },
  routeStatus: {
    exposure: 'internal',
    productionStatus: 'non_production',
    certificationStatus: 'uncertified',
  },
  readinessStatus: 'operationally_stable',
  readinessSummary: 'Team-level bullpen readiness looks steady from current public workload evidence.',
  readiness: {
    status: 'Operationally Stable',
    summary: 'Team-level bullpen readiness looks steady from current public workload evidence.',
  },
  team: {
    team_abbreviation: 'SEA',
  },
  constraints: [
    {
      message: 'Coverage inventory is represented.',
    },
  ],
  workloadPressure: {
    pressure_level: 'elevated',
    summary: 'Workload pressure is elevated at the team level.',
  },
  availabilityDistribution: {
    available: 240,
    monitor: 210,
    limited: 100,
    avoid: 20,
    unavailable: 109,
    total: 679,
  },
  coverageInventory: {
    active_pitchers: 679,
    availability_present: 679,
  },
  handednessCoverage: {
    coverage_state: 'represented',
  },
  explanations: [
    {
      message: 'Readiness context is assembled from current bullpen evidence.',
    },
  ],
  limitations: [],
  trustMetadata: {
    confidence: 'medium',
    data_state: 'complete',
  },
  freshness: {
    freshness_state: 'current',
    data_through: '2026-06-03',
  },
  refusal: {
    refused: false,
  },
  failClosed: {
    failed_closed: false,
    state: 'not_failed_closed',
  },
}

function renderSection(props = {}) {
  return renderToStaticMarkup(
    React.createElement(OperationalReadinessSection, {
      v2State,
      readinessState,
      ...props,
    }),
  )
}

test('renders the Operational Readiness hero and snapshot for V2 and V3 state', () => {
  const html = renderSection()

  assert.ok(htmlIncludes(html, 'Operational Readiness'))
  assert.ok(htmlIncludes(html, 'Bullpen State + Team Readiness'))
  assert.ok(htmlIncludes(html, 'Bullpen State Available'))
  assert.ok(htmlIncludes(html, 'Team Readiness Available'))
  assert.ok(htmlIncludes(html, 'Operational Snapshot'))
  assert.ok(htmlIncludes(html, 'Observational context only'))
  assert.ok(htmlIncludes(html, 'Current State'))
  assert.ok(htmlIncludes(html, 'Bullpen State'))
  assert.ok(htmlIncludes(html, 'State source: available context'))
  assert.ok(htmlIncludes(html, 'Current Readiness'))
  assert.ok(htmlIncludes(html, 'Team Readiness'))
  assert.ok(htmlIncludes(html, 'Operationally Stable'))
  assert.ok(htmlIncludes(html, 'Workload Pressure'))
  assert.ok(htmlIncludes(html, 'elevated'))
  assert.ok(htmlIncludes(html, 'Inventory Concentration'))
  assert.ok(htmlIncludes(html, 'Available: 240 / 679 total'))
  assert.ok(htmlIncludes(html, 'Freshness Status'))
  assert.ok(htmlIncludes(html, 'current'))
  assert.ok(htmlIncludes(html, 'Bullpen Visibility'))
  assert.ok(htmlIncludes(html, 'Data state complete'))
  assert.ok(htmlIncludes(html, 'BaseballOS explains available choices without choosing the next arm.'))
})

test('keeps governance invariants visible while details are collapsed', () => {
  const html = renderSection()

  // Governance is stated in plain language on the primary surface; the raw
  // ranking_applied / selection_made booleans live in the API payload and the
  // Evidence & Metadata drawer.
  assert.ok(htmlIncludes(html, 'Context only - BaseballOS does not choose the next arm.'))
  assert.ok(htmlIncludes(html, 'View Readiness Details'))
  assert.ok(htmlIncludes(html, 'View Evidence &amp; Source Detail'))
  assert.equal(htmlIncludes(html, 'Coverage inventory is represented.'), false)
  assert.equal(htmlIncludes(html, 'Bullpen inventory is summarized from current availability evidence.'), false)
})

test('preserves readiness and evidence detail views on demand', () => {
  const html = renderSection({
    initialReadinessDetailsOpen: true,
    initialEvidenceOpen: true,
  })

  assert.ok(htmlIncludes(html, 'Hide Readiness Details'))
  assert.ok(htmlIncludes(html, 'Hide Evidence &amp; Source Detail'))
  assert.ok(htmlIncludes(html, 'Bullpen Operations Context'))
  assert.ok(htmlIncludes(html, 'Bullpen Intelligence'))
  assert.ok(htmlIncludes(html, 'View Context Details'))
  assert.ok(htmlIncludes(html, 'View Evidence And Source Detail'))
})

test('does not introduce prohibited dashboard guidance language', () => {
  const html = renderSection()
  const text = sanitizedGovernanceText(html)

  assert.equal(/\bbest\b|\bpreferred\b|\brecommended\b/i.test(text), false)
  assert.equal(/\bpitcher-level advice\b|\bmatchup advice\b/i.test(text), false)
  assert.equal(/\brank\b|\branking\b|\bselect\b|\bselection\b|\bpredict\b|\bprediction\b/i.test(text), false)
})
