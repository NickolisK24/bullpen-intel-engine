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

const { default: RecommendationPanel } = await server.ssrLoadModule('/src/components/recommendations/RecommendationPanel.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

test('RecommendationPanel renders required shell sections and policy-safe labels', () => {
  const html = renderToStaticMarkup(React.createElement(RecommendationPanel))

  const requiredCopy = [
    'Recommendation Engine V1',
    'Candidate Evaluation',
    'Recommendation Status',
    'Recommendation Status Area',
    'Eligible Categories',
    'Use With Caution',
    'Avoid Tonight',
    'Explanation',
    'Limitation',
    'Trust And Freshness',
    'Data Freshness',
    'Confidence',
    'Refusal Output',
    'Metadata',
    'No Final Pitcher Selection Made',
    'No Bullpen Ranking Applied',
    'ranking_applied',
    'selection_made',
    'false',
  ]

  for (const label of requiredCopy) {
    assert.ok(htmlIncludes(html, label), `expected shell copy: ${label}`)
  }
})

test('RecommendationPanel keeps prohibited selection and ranking claims out of the shell', () => {
  const html = renderToStaticMarkup(React.createElement(RecommendationPanel))
  const blockedCopy = [
    'Best Pitcher',
    'Recommended Starter',
    'Guaranteed Option',
    ['A', 'I Pick'].join(''),
    'Manager Should Use',
  ]

  for (const label of blockedCopy) {
    assert.ok(!htmlIncludes(html, label), `unexpected shell copy: ${label}`)
  }
})

test('RecommendationPanel accepts a future display model without calling the recommendation API', () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => {
    throw new Error('RecommendationPanel shell must not call the API')
  }

  try {
    const html = renderToStaticMarkup(
      React.createElement(RecommendationPanel, {
        model: {
          candidateName: 'Example Pitcher',
          statusLabel: 'Candidate Evaluation Ready',
          statusDetail: 'Eligible category output is displayed without final selection.',
          categories: ['Use With Caution'],
          explanations: ['Explanation from a future candidate response.'],
          limitations: ['Limitation from a future candidate response.'],
          trust: {
            confidence: 'Medium',
            freshness: 'Fresh',
            availability: 'Monitor',
          },
          refusal: {
            reason: 'No refusal for this placeholder model.',
          },
          metadata: {
            rankingApplied: false,
            selectionMade: false,
          },
        },
      }),
    )

    assert.ok(htmlIncludes(html, 'Example Pitcher'))
    assert.ok(htmlIncludes(html, 'Medium'))
    assert.ok(htmlIncludes(html, 'Fresh'))
    assert.ok(htmlIncludes(html, 'Monitor'))
    assert.ok(htmlIncludes(html, 'Use With Caution'))
    assert.ok(htmlIncludes(html, 'false'))
  } finally {
    globalThis.fetch = originalFetch
  }
})
