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
  default: AvailabilityBacktestCard,
} = await server.ssrLoadModule('/src/components/trust/AvailabilityBacktestCard.jsx')

const componentSource = await readFile(
  new URL('../src/components/trust/AvailabilityBacktestCard.jsx', import.meta.url),
  'utf8',
)
const dataTrustSource = await readFile(
  new URL('../src/components/trust/DataTrust.jsx', import.meta.url),
  'utf8',
)

const payload = {
  status: 'ok',
  computed_at: '2026-06-15T07:00:00Z',
  framing: {
    title: 'Operational Availability Backtest',
    summary: 'Stored backtest summary from the API.',
    claim: 'Avoid and Unavailable were used less often than Available.',
    caveat: 'This is an observed association with bullpen management behavior, not a physiological proof or causal workload claim.',
  },
  windows: [
    {
      season: 2026,
      label: '2026 primary',
      is_primary: true,
      data_through: '2026-06-14',
      tiers: [
        { tier: 'Available', n: 12345, next_day_rate_pct: 43.2 },
        { tier: 'Monitor', n: 9876, next_day_rate_pct: 32.1 },
        { tier: 'Limited', n: 4567, next_day_rate_pct: 21.0 },
        { tier: 'Avoid', n: 321, next_day_rate_pct: 4.3 },
        { tier: 'Unavailable', n: 54, next_day_rate_pct: 0.0 },
      ],
      stability: {
        no_appearance_days: 6789,
        no_appearance_tier_flips: 123,
        no_appearance_tier_flip_rate_pct: 1.8,
      },
    },
    {
      season: 2025,
      label: '2025 secondary',
      is_primary: false,
      data_through: '2025-09-30',
      tiers: [
        { tier: 'Available', n: 22222, next_day_rate_pct: 41.9 },
        { tier: 'Monitor', n: 11111, next_day_rate_pct: 29.8 },
        { tier: 'Limited', n: 7777, next_day_rate_pct: 19.6 },
        { tier: 'Avoid', n: 888, next_day_rate_pct: 3.2 },
        { tier: 'Unavailable', n: 99, next_day_rate_pct: 0.0 },
      ],
      stability: {
        no_appearance_days: 20000,
        no_appearance_tier_flips: 300,
        no_appearance_tier_flip_rate_pct: 1.5,
      },
    },
  ],
}

function renderCard(data = payload, props = {}) {
  return renderToStaticMarkup(
    React.createElement(AvailabilityBacktestCard, { data, ...props }),
  )
}

function visibleText(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

test('renders stored usage-check values and honest framing', () => {
  const text = visibleText(renderCard())

  assert.ok(text.includes('Usage Check'))
  assert.equal(text.includes('Operational Backtest'), false)
  assert.ok(text.includes('Computed Jun 15, 2026, 3:00 AM ET'))
  assert.ok(text.includes('Data through June 14, 2026'))
  // Backend framing still says "Backtest"; the public layer rewrites it.
  assert.ok(text.includes('Operational Availability usage check'))
  assert.equal(text.includes('Backtest'), false)
  assert.ok(text.includes('43.2%'))
  assert.ok(text.includes('n=12,345'))
  assert.ok(text.includes('4.3%'))
  assert.ok(text.includes('2025 secondary'))
  assert.ok(text.includes('No-appearance tier flips: 1.8%'))
  assert.ok(text.includes('observed association'))
  assert.ok(text.includes('not a physiological proof or causal workload claim'))
  assert.equal(text.includes('Avoid'), false)
})

test('renders an honest empty state when no stored computation exists', () => {
  const text = visibleText(renderCard({ status: 'not_computed', framing: {}, windows: [] }))

  assert.ok(text.includes('Usage check not computed yet'))
  assert.ok(text.includes('Stored next-day usage results will appear after the next scheduled data refresh.'))
})

test('backend framing that reads as prediction, betting, or internal tooling is withheld', () => {
  const text = visibleText(renderCard({
    ...payload,
    framing: {
      title: 'Availability model accuracy',
      summary: 'Our model predicts next-day usage.',
      claim: 'Tiers forecast appearances with 90% accuracy — bet accordingly.',
      caveat: 'Backtested against the V2 endpoint.',
    },
  }))

  // Every unsafe framing string falls back to the card's fixed copy.
  assert.equal(text.includes('accuracy'), false)
  assert.equal(text.includes('predicts'), false)
  assert.equal(text.includes('forecast'), false)
  assert.equal(text.includes('bet accordingly'), false)
  assert.equal(text.includes('V2'), false)
  assert.ok(text.includes('Availability Tier Usage Check'))
  assert.ok(text.includes('Stored next-day usage results are not available yet.'))
  assert.ok(text.includes('Descriptive context only'))
  // The observed rates themselves still render — only framing copy is guarded.
  assert.ok(text.includes('43.2%'))
})

test('safe backend framing passes the guard unchanged', () => {
  const text = visibleText(renderCard())
  assert.ok(text.includes('Unavailable was used less often than Available.'))
  assert.ok(text.includes('observed association'))
})

test('backtest display contains no audited-result literals', () => {
  assert.equal(componentSource.includes('34%'), false)
  assert.equal(componentSource.includes('27%'), false)
  assert.equal(componentSource.includes('17%'), false)
  assert.equal(componentSource.includes('1.1%'), false)
  assert.equal(componentSource.includes('58k'), false)
})

test('Data & Trust renders the backtest and does not duplicate the secondary ERA study', () => {
  assert.ok(dataTrustSource.includes('AvailabilityBacktestCard'))
  assert.equal(dataTrustSource.includes('Secondary Exploratory ERA Study'), false)
  assert.equal(dataTrustSource.includes('FatigueInsightCard'), false)
})
