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
  default: RecommendationV2BullpenStatePanel,
} = await server.ssrLoadModule('/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx')
const {
  default: TeamOperationsBullpenReadinessPanel,
} = await server.ssrLoadModule('/src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx')
const {
  default: BullpenIntelligencePanel,
} = await server.ssrLoadModule('/src/components/observations/BullpenIntelligencePanel.jsx')

const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const forbiddenChrome = /\bCertified\b|\bProtected\b|\bV2\b|\bV3\b|\bV4\b/i

function render(element) {
  return visibleText(renderToStaticMarkup(element))
}

test('trust surfaces do not render certification, protection, or version chrome', () => {
  const recommendationText = render(
    React.createElement(RecommendationV2BullpenStatePanel, {
      state: {
        contractState: 'fail_closed',
        isContractSafe: true,
        isFailClosed: true,
        governance: { rankingApplied: false, selectionMade: false },
        freshness: {
          source_freshness_status: 'stale',
          aggregate_v2_freshness_status: 'stale',
          sync_timestamp: '2026-06-03T07:44:27Z',
        },
        statusMetadata: {
          reason_summary: 'Source freshness is stale. V2 is preserving fail-closed protection while displaying degraded context only.',
          display_label: 'Data freshness protection active',
          fail_closed_reason_code: 'data_state_stale',
          freshness_failed: true,
          trust_failed: false,
        },
        failClosed: {
          failed_closed: true,
          state: 'degraded',
          display_label: 'Data freshness protection active',
          reason_summary: 'Source freshness is stale. V2 is preserving fail-closed protection while displaying degraded context only.',
          reason_codes: ['data_state_stale'],
        },
        refusalReasons: [
          {
            message: 'V2 context is degraded or refused because source data state is stale.',
          },
        ],
        bullpenState: null,
      },
    }),
  )

  const teamOperationsText = render(
    React.createElement(TeamOperationsBullpenReadinessPanel, {
      state: {
        contractState: 'available',
        sourceContractState: 'available',
        isContractSafe: true,
        isInternal: true,
        isInternalUncertified: true,
        governance: { rankingApplied: false, selectionMade: false },
        routeStatus: {
          exposure: 'internal',
          productionStatus: 'non_production',
          certificationStatus: 'uncertified',
        },
        readinessStatus: 'operationally_stable',
        readinessSummary: 'Team-level bullpen readiness is operationally stable.',
        readiness: {
          status: 'Operationally Stable',
          summary: 'Team-level bullpen readiness is operationally stable.',
        },
        workloadPressure: {},
        availabilityDistribution: {},
        coverageInventory: {},
        handednessCoverage: {},
        trustMetadata: {
          governance_state: 'internal_uncertified',
          confidence: 'medium',
          data_state: 'complete',
        },
        freshness: {},
      },
      initialExpandedSections: ['metadata'],
    }),
  )

  const observationText = render(
    React.createElement(BullpenIntelligencePanel, {
      state: {
        status: 'fail_closed',
        trustStatus: 'protected',
        observations: [],
        limitations: [],
        confidence: {},
        freshness: {},
      },
    }),
  )

  const combinedText = `${recommendationText} ${teamOperationsText} ${observationText}`

  assert.equal(forbiddenChrome.test(combinedText), false, combinedText)
  assert.match(combinedText, /Unavailable - freshness failed/)
  assert.match(combinedText, /Internal \/ Limited Exposure/)
  assert.match(combinedText, /withheld/i)
})

test('component sources do not contain old visible trust-chrome phrases', async () => {
  const files = [
    '../src/components/explanations/ExplanationDisclosure.jsx',
    '../src/components/recommendations/RecommendationV2BullpenStatePanel.jsx',
    '../src/components/dashboard/OperationalReadinessSection.jsx',
    '../src/components/observations/BullpenIntelligencePanel.jsx',
    '../src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx',
  ]
  const oldVisiblePhrases = [
    'Certified V4 Explanation',
    'Freshness Protected',
    'Trust Protected',
    'V2 Bullpen Intelligence',
    'V5 Bullpen Intelligence',
    'Internal / Non-production / Uncertified',
    'Data freshness protection active',
    'Trust protection active',
  ]

  for (const file of files) {
    const source = await readFile(new URL(file, import.meta.url), 'utf8')
    for (const phrase of oldVisiblePhrases) {
      assert.equal(
        source.includes(phrase),
        false,
        `${file} still contains visible trust-chrome phrase: ${phrase}`,
      )
    }
  }
})
