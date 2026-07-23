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
        { tier: 'Available', n: 12345, next_day_appearances: 5333, next_day_rate_pct: 43.2 },
        { tier: 'Monitor', n: 9876, next_day_appearances: 3170, next_day_rate_pct: 32.1 },
        { tier: 'Limited', n: 4567, next_day_appearances: 959, next_day_rate_pct: 21.0 },
        { tier: 'Avoid', n: 321, next_day_appearances: 14, next_day_rate_pct: 4.4 },
        { tier: 'Unavailable', n: 54, next_day_appearances: 0, next_day_rate_pct: 0.0 },
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
        { tier: 'Available', n: 22222, next_day_appearances: 9311, next_day_rate_pct: 41.9 },
        { tier: 'Monitor', n: 11111, next_day_appearances: 3311, next_day_rate_pct: 29.8 },
        { tier: 'Limited', n: 7777, next_day_appearances: 1524, next_day_rate_pct: 19.6 },
        { tier: 'Avoid', n: 888, next_day_appearances: 28, next_day_rate_pct: 3.2 },
        { tier: 'Unavailable', n: 99, next_day_appearances: 0, next_day_rate_pct: 0.0 },
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
  // The card's own title is fixed, reader-first framing — never the backend title.
  assert.ok(text.includes('How the labels matched next-day usage'))
  assert.equal(text.includes('Backtest'), false)
  assert.ok(text.includes('Computed Jun 15, 2026, 3:00 AM ET'))
  assert.ok(text.includes('Data through June 14, 2026'))
  assert.ok(text.includes('43.2%'))
  assert.ok(text.includes('Sample: 12,345 pitcher-days'))
  // The Avoid and Unavailable tiers fold into one public Unavailable row: the
  // sample size sums (321 + 54 = 375) and the rate is recomputed from the
  // combined next-day appearances (14 / 375 → 3.7%).
  assert.ok(text.includes('Sample: 375 pitcher-days'))
  assert.ok(text.includes('3.7%'))
  assert.ok(text.includes('2025 secondary'))
  assert.ok(text.includes('observed association'))
  assert.ok(text.includes('not a physiological proof or causal workload claim'))
  assert.equal(text.includes('Avoid'), false)
})

// ── Defect 2: no duplicate "Unavailable" availability label ────────────────
// The backend returns five internal tiers; Avoid and Unavailable both carry the
// public label "Unavailable". Rendering raw tiers produced two rows labeled
// "Unavailable" (one near the Avoid rate, one near 0%). Each public label must
// appear once, with the sample sizes preserved and the rate recomputed.

test('Defect 2: each window shows one Unavailable row, not a duplicate Avoid+Unavailable pair', () => {
  // Frame text stripped so only tier-row labels contribute to the label counts.
  const singleWindow = {
    status: 'ok',
    computed_at: '2026-06-15T07:00:00Z',
    framing: {},
    windows: [payload.windows[0]],
  }
  const text = visibleText(renderCard(singleWindow))
  const occurrences = (needle) => text.split(needle).length - 1

  // Exactly one row per canonical public availability label.
  assert.equal(occurrences('Unavailable'), 1)
  assert.equal(occurrences('Available'), 1)
  assert.equal(occurrences('On Watch'), 1)
  assert.equal(occurrences('Limited'), 1)
  // Avoid is an internal tier only; it must never surface as a public label.
  assert.equal(text.includes('Avoid'), false)
  // Sample sizes remain attached: merged n is the sum of the two folded tiers.
  assert.ok(text.includes('Sample: 375 pitcher-days'))
  assert.ok(text.includes('3.7%'))
  // The distinct upstream tiers (Available/On Watch/Limited) keep their sizes.
  assert.ok(text.includes('Sample: 12,345 pitcher-days'))
})

test('Defect 2: an unknown non-availability tier is not folded into Unavailable', () => {
  // A hypothetical no-read tier the public label layer does not recognize keeps
  // its own row rather than being silently relabeled Unavailable.
  const withUnknownTier = {
    status: 'ok',
    computed_at: '2026-06-15T07:00:00Z',
    framing: {},
    windows: [{
      season: 2026,
      label: '2026 primary',
      is_primary: true,
      data_through: '2026-06-14',
      tiers: [
        { tier: 'Available', n: 100, next_day_appearances: 40, next_day_rate_pct: 40.0 },
        { tier: 'Avoid', n: 20, next_day_appearances: 1, next_day_rate_pct: 5.0 },
        { tier: 'Unavailable', n: 10, next_day_appearances: 0, next_day_rate_pct: 0.0 },
        { tier: 'No Read', n: 7, next_day_appearances: 0, next_day_rate_pct: 0.0 },
      ],
      stability: { no_appearance_days: 0, no_appearance_tier_flips: 0, no_appearance_tier_flip_rate_pct: 0.0 },
    }],
  }
  const text = visibleText(renderCard(withUnknownTier))
  const occurrences = (needle) => text.split(needle).length - 1
  // Avoid + Unavailable merge to one Unavailable row (n = 30); the unrecognized
  // tier stays separate and is not counted as Unavailable.
  assert.equal(occurrences('Unavailable'), 1)
  assert.ok(text.includes('Sample: 30 pitcher-days'))
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

  // Unsafe backend framing (claim/caveat) is withheld; the card's own fixed
  // title and summary are authored copy, so no unsafe framing can reach them.
  assert.equal(text.includes('accuracy'), false)
  assert.equal(text.includes('predicts'), false)
  assert.equal(text.includes('forecast'), false)
  assert.equal(text.includes('bet accordingly'), false)
  assert.equal(text.includes('V2'), false)
  assert.ok(text.includes('How the labels matched next-day usage'))
  assert.ok(text.includes('look back at completed games'))
  assert.ok(text.includes('Descriptive context only'))
  // The observed rates themselves still render — only framing copy is guarded.
  assert.ok(text.includes('43.2%'))
})

test('safe backend framing passes the guard unchanged', () => {
  const text = visibleText(renderCard())
  assert.ok(text.includes('Unavailable was used less often than Available.'))
  assert.ok(text.includes('observed association'))
})

// ── Unknown-versus-zero honesty in the usage check ─────────────────────────

function renderWindow(tiers) {
  return visibleText(renderCard({
    status: 'ok',
    computed_at: '2026-06-15T07:00:00Z',
    framing: {},
    windows: [{ label: 'primary', is_primary: true, data_through: '2026-06-14', tiers }],
  }))
}
const availableRow = (text) => {
  const start = text.indexOf('Available')
  return start > -1 ? text.slice(start, start + 90) : ''
}

test('a missing sample size renders as unknown, never as zero', () => {
  const text = renderWindow([{ tier: 'Available', next_day_rate_pct: 40.0 }])
  const row = availableRow(text)
  assert.ok(row.includes('Sample: — pitcher-days'), row)
  assert.equal(row.includes('Sample: 0 pitcher-days'), false)
})

test('an explicit zero sample size remains zero', () => {
  const text = renderWindow([{ tier: 'Available', n: 0, next_day_appearances: 0, next_day_rate_pct: 0.0 }])
  assert.ok(availableRow(text).includes('Sample: 0 pitcher-days'))
})

test('a missing next-day count with no rate renders the rate as unknown, not 0.0%', () => {
  const text = renderWindow([{ tier: 'Available', n: 100 }])
  const row = availableRow(text)
  assert.ok(row.includes('—'), row)
  assert.equal(row.includes('0.0%'), false)
  assert.ok(row.includes('Sample: 100 pitcher-days'))
})

test('an explicit zero next-day rate remains 0.0%', () => {
  const text = renderWindow([{ tier: 'Available', n: 54, next_day_appearances: 0, next_day_rate_pct: 0.0 }])
  const row = availableRow(text)
  assert.ok(row.includes('0.0%'))
  assert.ok(row.includes('Sample: 54 pitcher-days'))
})

test('empty-string and null numeric fields are unknown, not zero', () => {
  const text = renderWindow([{ tier: 'Available', n: '', next_day_appearances: null, next_day_rate_pct: '' }])
  const row = availableRow(text)
  assert.ok(row.includes('Sample: — pitcher-days'), row)
  assert.equal(row.includes('Sample: 0 pitcher-days'), false)
  assert.equal(row.includes('0.0%'), false)
})

test('an impossible rate (appearances above sample) fails closed instead of exceeding 100%', () => {
  const text = renderWindow([{ tier: 'Available', n: 10, next_day_appearances: 20 }])
  const row = availableRow(text)
  assert.equal(/\b\d{3,}\.\d%/.test(row), false)
  assert.ok(row.includes('—'), row)
})

test('incomplete merged Unavailable data is withheld, not shown as complete', () => {
  // Avoid carries a full row, but the strict Unavailable tier is missing its
  // sample size — the merged public Unavailable must not look complete.
  const text = renderWindow([
    { tier: 'Available', n: 100, next_day_appearances: 40, next_day_rate_pct: 40.0 },
    { tier: 'Avoid', n: 20, next_day_appearances: 1, next_day_rate_pct: 5.0 },
    { tier: 'Unavailable', next_day_rate_pct: 0.0 },
  ])
  const start = text.indexOf('Unavailable')
  const row = text.slice(start, start + 90)
  assert.ok(row.includes('Sample: — pitcher-days'), row)
  assert.equal(/Sample: \d/.test(row), false)
})

test('complete merged Unavailable data reconciles to the summed sample and recomputed rate', () => {
  const text = renderWindow([
    { tier: 'Avoid', n: 300, next_day_appearances: 12, next_day_rate_pct: 4.0 },
    { tier: 'Unavailable', n: 100, next_day_appearances: 8, next_day_rate_pct: 8.0 },
  ])
  const start = text.indexOf('Unavailable')
  const row = text.slice(start, start + 90)
  // n = 400, appearances = 20, rate = 20/400 = 5.0%.
  assert.ok(row.includes('Sample: 400 pitcher-days'))
  assert.ok(row.includes('5.0%'))
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
