import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
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

after(async () => server.close())

const { default: TeamBoardWorkloadOverview, getWorkloadWindowRows } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardWorkloadOverview.jsx',
)
const { chartKeyIndex, chartPointerIndex } = await server.ssrLoadModule('/src/components/bullpen/board/WorkloadTrend.jsx')

const workloadOverview = {
  population_basis: 'official_team_relief_appearances_and_current_bullpen_eligible_pitchers',
  window_population_basis: 'official_appearance_team_relief_appearances',
  represented_date: '2026-08-16',
  windows: [
    {
      window_days: 14,
      through: '2026-08-16',
      relief_appearances: 9,
      pitchers_in_relief: 6,
      pitches_total: null,
    },
    {
      window_days: 7,
      through: '2026-08-16',
      relief_appearances: 0,
      pitchers_in_relief: 0,
      pitches_total: 0,
    },
  ],
  concentration: {
    population_basis: 'current_bullpen_eligible_pitchers_recent_relief_pitch_workload',
    label: 'Some Workload Concentration',
    summary: 'Two arms have carried 62% of the recent relief work across five bullpen arms.',
  },
  limitations: [],
}

const read = {
  workloadOverview,
  recentReliefWork: {
    read: {
      data_through: '2026-08-16',
      relief_by_date: [
        { game_date: '2026-08-16', outs_total: 0 },
        { game_date: '2026-08-14', outs_total: 8 },
      ],
    },
  },
  sectionStatus: {
    workload_overview: { status: 'available', limitations: [] },
  },
}

const renderWorkload = props => renderToStaticMarkup(React.createElement(TeamBoardWorkloadOverview, props))

test('Workload Overview preserves backend window order and renders governed facts verbatim', () => {
  const rows = getWorkloadWindowRows(workloadOverview)
  const html = renderWorkload({ read })

  assert.deepEqual(rows.map(row => row.label), ['14 days', '7 days'])
  assert.ok(html.indexOf('14 days') < html.indexOf('7 days'))
  assert.ok(html.includes('>9<'))
  assert.ok(html.includes('Some Workload Concentration'))
  assert.ok(html.includes(workloadOverview.concentration.summary))
})

test('Workload Overview omits unknown totals and preserves backend-supplied zero', () => {
  const html = renderWorkload({ read })
  const firstWindow = html.slice(html.indexOf('14 days'), html.indexOf('7 days'))
  const secondWindow = html.slice(html.indexOf('7 days'), html.indexOf('Concentration'))

  assert.equal(firstWindow.includes('>0<'), false)
  assert.ok(firstWindow.includes('>—<'))
  assert.equal(firstWindow.includes('null'), false)
  assert.ok(secondWindow.includes('>0<'))
})

test('Workload Overview renders only backend-provided windows without synthetic trend copy', () => {
  const html = renderWorkload({ read: {
    ...read,
    workloadOverview: {
      ...workloadOverview,
      windows: [workloadOverview.windows[1]],
    },
  } })

  assert.ok(html.includes('7 days'))
  assert.equal(html.includes('14 days'), false)
  for (const forbidden of ['rising', 'falling', 'easing', 'worsening', 'improving', '3-in-4', '4-in-6']) {
    assert.equal(html.toLowerCase().includes(forbidden), false, forbidden)
  }
})

test('Workload Overview renders one governed daily-outs chart and distinguishes zero from unavailable', () => {
  const html = renderWorkload({ read })

  assert.equal((html.match(/data-testid="workload-trend"/g) || []).length, 1)
  assert.ok(html.includes('Published outs across 30 calendar days'))
  assert.ok(html.includes('Swipe or use the arrow keys to inspect each day.'))
  assert.ok(html.includes('data-outs="0"'))
  assert.ok(html.includes('height:2px'))
  assert.ok(html.includes('data-published="false"'))
  assert.ok(html.includes('unavailable'))
})

test('Workload window columns can shrink under text zoom without creating horizontal scroll', () => {
  const html = renderWorkload({ read })

  assert.match(html, /grid-template-columns:minmax\(0, 1fr\) repeat\(2, minmax\(0, 0.65fr\)\)/)
  assert.doesNotMatch(html, /minmax\(7rem|minmax\(4\.5rem/)
})

test('Workload chart uses one continuous touch and keyboard control without a 30-tab-stop explosion', () => {
  const html = renderWorkload({ read })

  assert.equal((html.match(/type="range"/g) || []).length, 1)
  assert.equal((html.match(/data-testid="workload-trend-control"/g) || []).length, 1)
  assert.equal((html.match(/<button/g) || []).length, 0)
  assert.match(html, /min="0"/)
  assert.match(html, /max="29"/)
  assert.match(html, /step="1"/)
  assert.match(html, /aria-label="Inspect daily bullpen relief workload"/)
  assert.match(html, /aria-valuetext="Aug 16, 2026: 0 outs"/)
  assert.match(html, /focus-within:ring-2/)
  assert.match(html, /hidden sm:inline/)
  assert.doesNotMatch(html, /transition|animate-|motion-/)
})

test('Workload chart Arrow, Home, and End keys traverse all calendar positions with bounded indexes', () => {
  assert.equal(chartKeyIndex('ArrowLeft', 5, 29), 4)
  assert.equal(chartKeyIndex('ArrowDown', 0, 29), 0)
  assert.equal(chartKeyIndex('ArrowRight', 28, 29), 29)
  assert.equal(chartKeyIndex('ArrowUp', 29, 29), 29)
  assert.equal(chartKeyIndex('Home', 17, 29), 0)
  assert.equal(chartKeyIndex('End', 17, 29), 29)
  assert.equal(chartKeyIndex('Enter', 17, 29), null)
})

test('Workload chart pointer positions select the nearest governed calendar slot', () => {
  assert.equal(chartPointerIndex(100, 100, 300, 29), 0)
  assert.equal(chartPointerIndex(250, 100, 300, 29), 15)
  assert.equal(chartPointerIndex(400, 100, 300, 29), 29)
  assert.equal(chartPointerIndex(50, 100, 300, 29), 0)
  assert.equal(chartPointerIndex(450, 100, 300, 29), 29)
  assert.equal(chartPointerIndex(100, 100, 0, 29), null)
})

test('Workload Overview omits the chart when no governed date groups are published', () => {
  const html = renderWorkload({ read: {
    ...read,
    recentReliefWork: { read: { data_through: '2026-08-16', relief_by_date: [] } },
  } })

  assert.equal(html.includes('data-testid="workload-trend"'), false)
  assert.ok(html.includes('14 days'))
  assert.ok(html.includes(workloadOverview.concentration.summary))
})

test('Workload Overview distinguishes loading, partial, unavailable, error, and empty states', () => {
  assert.ok(renderWorkload({ loading: true }).includes('workload-overview-skeleton'))
  assert.ok(renderWorkload({ read: {
    ...read,
    sectionStatus: { workload_overview: { status: 'partial', limitations: ['One governed window is incomplete.'] } },
  } }).includes('One governed window is incomplete.'))
  assert.ok(renderWorkload({ read: {
    ...read,
    workloadOverview: { ...workloadOverview, concentration: null },
    sectionStatus: { workload_overview: { status: 'partial', limitations: [] } },
  } }).includes('Concentration unavailable'))
  assert.ok(renderWorkload({ read: {
    ...read,
    sectionStatus: { workload_overview: { status: 'unavailable', limitations: [] } },
  } }).includes('Recent team workload evidence is unavailable.'))
  assert.ok(renderWorkload({ read: {
    ...read,
    workloadOverview: { ...workloadOverview, windows: [], concentration: null },
  } }).includes('No recent team workload'))
  const errorHtml = renderWorkload({ read, error: 'private exception' })
  assert.ok(errorHtml.includes('Workload overview could not be loaded.'))
  assert.equal(errorHtml.includes('private exception'), false)
})

test('production reuses one v2 request, retires the legacy mount, and leaves later sections alone', async () => {
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const componentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardWorkloadOverview.jsx', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(boardSource.includes('aria-label="Current workload picture"'))
  assert.ok(boardSource.includes('<TeamBoardWorkloadOverview'))
  assert.ok(boardSource.includes('<SectionPair label="Rest and workload"'))
  assert.equal(boardSource.includes('<WorkloadOverview'), false)
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.ok(boardSource.includes('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.indexOf('<TeamBoardWorkloadOverview') < boardSource.indexOf('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.indexOf('<TeamBoardRestStatus') < boardSource.indexOf('<TeamBoardWorkloadOverview'))
  for (const forbidden of ['.sort(', '.reduce(', 'Math.', 'fatigue', 'workload_score', '3_in_4', '4_in_5', '4_in_6']) {
    assert.equal(componentSource.includes(forbidden), false, forbidden)
  }
})
