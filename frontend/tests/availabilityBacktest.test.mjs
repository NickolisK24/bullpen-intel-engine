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
    caveat: 'This is an observed association with bullpen management behavior, not a physiological proof or causal fatigue claim.',
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

test('renders stored backtest values and honest framing', () => {
  const text = visibleText(renderCard())

  assert.ok(text.includes('Operational Backtest'))
  assert.ok(text.includes('Operational Availability Backtest'))
  assert.ok(text.includes('43.2%'))
  assert.ok(text.includes('n=12,345'))
  assert.ok(text.includes('4.3%'))
  assert.ok(text.includes('2025 secondary'))
  assert.ok(text.includes('No-appearance tier flips: 1.8%'))
  assert.ok(text.includes('observed association'))
  assert.ok(text.includes('not a physiological proof or causal fatigue claim'))
})

test('renders an honest empty state when no stored computation exists', () => {
  const text = visibleText(renderCard({ status: 'not_computed', framing: {}, windows: [] }))

  assert.ok(text.includes('Operational backtest not computed'))
  assert.ok(text.includes('Stored backtest results will appear after the backtest refresh runs.'))
})

test('backtest display contains no audited-result literals', () => {
  assert.equal(componentSource.includes('34%'), false)
  assert.equal(componentSource.includes('27%'), false)
  assert.equal(componentSource.includes('17%'), false)
  assert.equal(componentSource.includes('1.1%'), false)
  assert.equal(componentSource.includes('58k'), false)
})

test('Data & Trust renders the backtest before the secondary ERA study', () => {
  assert.ok(dataTrustSource.includes('AvailabilityBacktestCard'))
  assert.ok(dataTrustSource.includes('Secondary Exploratory ERA Study'))
  assert.ok(
    dataTrustSource.indexOf('AvailabilityBacktestCard')
      < dataTrustSource.indexOf('Secondary Exploratory ERA Study'),
  )
})
