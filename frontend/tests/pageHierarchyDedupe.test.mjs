import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
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

const { default: Home } = await server.ssrLoadModule('/src/components/home/Home.jsx')
const { MethodologyView } = await server.ssrLoadModule('/src/components/methodology/Methodology.jsx')
const { DataTrustView } = await server.ssrLoadModule('/src/components/trust/DataTrust.jsx')
const { default: Sidebar } = await server.ssrLoadModule('/src/components/Sidebar.jsx')
const { default: BullpenLandscape } = await server.ssrLoadModule('/src/components/dashboard/BullpenLandscape.jsx')

const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)
const fetchState = (data, overrides = {}) => ({
  data,
  loading: false,
  error: null,
  staleWithError: false,
  refetch: () => {},
  ...overrides,
})
const htmlIncludes = (html, text) => html.includes(text)
const visibleText = (html) => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const forbiddenVisibleTerms = /\b(Recommendation V2|V2|backend|endpoint|COIN|deterministic|snapshot|governance layer|recommendation engine|sample state)\b/i

const methodologyData = {
  fatigue_engine: {
    title: 'Availability Labels',
    summary: 'Availability labels describe the current bullpen read.',
    components: [],
    risk_tiers: [],
    excluded: {
      name: 'Leverage Index',
      reason: 'The gameLog endpoint is a backend snapshot and deterministic detail.',
    },
  },
  insights: {
    title: 'Exploratory ERA Study',
    summary: 'A research note about availability labels and next-game ERA.',
    finding: 'The study is exploratory and not used as a prediction.',
    samples: { LOW: 10, MODERATE: 12, HIGH: 8, CRITICAL: 4 },
    measured: ['Availability tier at the end of a completed game.'],
    not_measured: ['Pitcher matchup quality.'],
    caveat: 'This is descriptive research, not a causal claim.',
  },
  data_sources: [],
  stack: ['backend V2'],
}

const backtestPayload = {
  status: 'ok',
  computed_at: '2026-06-15T07:00:00Z',
  framing: {
    title: 'Operational Availability Backtest',
    summary: 'Stored reliability check from completed-game usage.',
    claim: 'Availability tiers have separated next-day usage rates.',
    caveat: 'This is an observed association, not a prediction.',
  },
  windows: [
    {
      season: 2026,
      label: '2026 primary',
      is_primary: true,
      data_through: '2026-06-14',
      tiers: [
        { tier: 'Available', n: 100, next_day_rate_pct: 40 },
        { tier: 'Monitor', n: 80, next_day_rate_pct: 30 },
      ],
      stability: {
        no_appearance_days: 50,
        no_appearance_tier_flips: 1,
        no_appearance_tier_flip_rate_pct: 2,
      },
    },
  ],
}

const dashboardPayload = {
  freshness: {
    data_through: '2026-06-14',
    last_successful_sync: '2026-06-15T07:00:00Z',
    is_current: true,
    sync_status: 'success',
  },
}

const syncPayload = {
  status: 'success',
  last_checked: '2026-06-15T07:05:00Z',
  last_sync: '2026-06-15T07:00:00Z',
  last_successful_sync: '2026-06-15T07:00:00Z',
  data: {
    latest_game_date: '2026-06-14',
  },
  freshness: {
    is_current: true,
    is_stale: false,
    freshness_state: 'current',
    label: 'Current baseball data through 2026-06-14.',
    limitations: [],
  },
}

function renderDataTrust() {
  return render(React.createElement(DataTrustView, {
    backtest: fetchState(backtestPayload),
    dashboard: fetchState(dashboardPayload),
    overview: fetchState(null),
    sync: fetchState(syncPayload),
  }))
}

test('sidebar renders the requested public page order', () => {
  const html = render(React.createElement(Sidebar))
  const routes = ['/', '/dashboard', '/bullpen', '/stories', '/methodology', '/trust']
  const indexes = routes.map(route => html.indexOf(`href="${route}"`))

  for (const index of indexes) {
    assert.notEqual(index, -1)
  }
  assert.deepEqual([...indexes].sort((a, b) => a - b), indexes)
  assert.equal(htmlIncludes(html, 'href="/prospects"'), false)
})

test('Methodology links to Data & Trust and preserves its inbound anchors instead of rendering the backtest', () => {
  const html = render(React.createElement(MethodologyView, { data: methodologyData }))
  const text = visibleText(html)

  assert.ok(htmlIncludes(html, 'href="/trust"'))
  assert.ok(htmlIncludes(html, 'id="methodology"'))
  assert.ok(htmlIncludes(html, 'id="data-sources"'))
  assert.ok(htmlIncludes(html, 'id="known-limitations"'))
  assert.ok(text.includes('Limitations and refusals'))
  assert.ok(text.includes('public MLB data'))
  assert.ok(text.includes('not a health claim'))
  // The live reliability report stays on Data & Trust; Methodology only links there.
  assert.ok(text.includes('current system status, coverage, and validation'))
  assert.equal(text.includes('Operational Backtest'), false)
  assert.equal(text.includes('Operational Availability Backtest'), false)
  assert.equal(text.includes('Exploratory ERA Study'), false)
  assert.equal(text.includes('LOW n='), false)
  assert.equal(text.includes('MODERATE n='), false)
  assert.equal(text.includes('HIGH n='), false)
  assert.equal(text.includes('CRITICAL n='), false)
})

test('Data & Trust leads with the current answer and owns the usage check without duplicate sections', () => {
  const html = renderDataTrust()
  const text = visibleText(html)

  // The current-data answer precedes the usage check.
  const currentAnswer = text.indexOf('Is the public bullpen picture current?')
  const usageCheck = text.indexOf('How the labels matched next-day usage')
  assert.ok(currentAnswer > -1)
  assert.ok(usageCheck > currentAnswer)

  assert.ok(text.includes('Usage Check'))
  // The card title is fixed reader-first framing, never the backend "Backtest".
  assert.equal(text.includes('Operational Backtest'), false)
  assert.equal(text.includes('Backtest'), false)
  assert.ok(text.includes('Freshness and coverage detail'))
  assert.ok(text.includes('BaseballOS updates after completed MLB games'))
  // Methodology and How to Read are linked rather than duplicated.
  assert.ok(htmlIncludes(html, 'href="/methodology"'))
  assert.ok(htmlIncludes(html, 'href="/how-to-read"'))
  // The inbound freshness anchor is preserved.
  assert.ok(htmlIncludes(html, 'id="freshness-update-schedule"'))
  // The workload inventory and its internal term are gone from the public page.
  assert.equal(text.includes('Pitcher Workload Inventory'), false)
  assert.equal(text.includes('scored_pitcher_inventory'), false)
  assert.equal(htmlIncludes(html, 'id="contact"'), false)
  assert.equal(text.includes('Secondary Exploratory ERA Study'), false)
  assert.equal(text.includes('Digest Preferences'), false)
})

test('off-lane and dead frontend surfaces are not present for remounting', () => {
  for (const rel of [
    '../src/components/prospects/Prospects.jsx',
    '../src/components/prospects/ProspectCard.jsx',
    '../src/components/trust/DigestPreferencesCard.jsx',
    '../src/components/home/LegacyMorningBullpenReport.jsx',
    '../src/components/home/homeCanonicalStoriesView.js',
    '../src/components/home/DigestReturnNotice.jsx',
    '../src/utils/todayDigestReturn.js',
  ]) {
    assert.equal(existsSync(new URL(rel, import.meta.url)), false, rel)
  }
})

test('Methodology and Data & Trust rendered text does not leak internal labels', () => {
  const methodologyText = visibleText(render(React.createElement(MethodologyView, { data: methodologyData })))
  const trustText = visibleText(renderDataTrust())

  assert.equal(forbiddenVisibleTerms.test(methodologyText), false)
  assert.equal(forbiddenVisibleTerms.test(trustText), false)
  assert.ok(methodologyText.includes('public MLB data'))
  assert.ok(methodologyText.includes('On Watch'))
})

test('dashboard landscape notes soften internal sorting language', () => {
  const html = render(React.createElement(BullpenLandscape, {
    landscape: {
      reference_date: '2026-06-14',
      teams_evaluated: 1,
      games: { available: true, data_state: 'historical', as_of_date: '2026-06-14', as_of_count: 1 },
      constrained_bullpens: [],
      available_bullpens: [],
      monitoring_concentration: [],
      notes: ['Sorted deterministically by count, then percentage, then team name.'],
    },
  }))
  const text = visibleText(html)

  assert.ok(text.includes('Groups reflect the current bullpen counts for each team.'))
  assert.equal(text.includes('Sorted by count'), false)
  assert.equal(forbiddenVisibleTerms.test(text), false)
})

test('Today route stays pointed at the Intelligence Surface', () => {
  const source = readFileSync(new URL('../src/components/home/Home.jsx', import.meta.url), 'utf8')
  const html = render(React.createElement(Home))

  assert.ok(source.includes("import IntelligenceSurfacePage from './IntelligenceSurface'"))
  assert.ok(source.includes('return <IntelligenceSurfacePage />'))
  assert.equal(source.includes('LegacyMorningBullpenReport'), false)
  assert.equal(source.includes('getBullpenDashboard'), false)
  assert.equal(html.includes('Upcoming Games'), false)
  assert.equal(html.includes("Today&#x27;s Story"), false)
  assert.equal(html.includes('Loading today&#x27;s lead story...'), false)
})
