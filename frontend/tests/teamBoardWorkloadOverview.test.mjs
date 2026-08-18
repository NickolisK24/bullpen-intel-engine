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
  assert.ok(html.includes('>6<'))
  assert.ok(html.includes('Some Workload Concentration'))
  assert.ok(html.includes(workloadOverview.concentration.summary))
})

test('Workload Overview omits unknown totals and preserves backend-supplied zero', () => {
  const html = renderWorkload({ read })
  const firstWindow = html.slice(html.indexOf('14 days'), html.indexOf('7 days'))
  const secondWindow = html.slice(html.indexOf('7 days'), html.indexOf('Concentration'))

  assert.equal(firstWindow.includes('>0<'), false)
  assert.ok(firstWindow.includes('Unavailable'))
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
  assert.ok(boardSource.includes('<TeamBoardWorkloadOverview'))
  assert.equal(boardSource.includes('<WorkloadOverview'), false)
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.equal(boardSource.includes('<TeamBoardRoles'), false)
  assert.ok(boardSource.indexOf('<TeamBoardRestStatus') < boardSource.indexOf('<TeamBoardWorkloadOverview'))
  for (const forbidden of ['.sort(', '.reduce(', 'Math.', 'trend', 'fatigue', 'workload_score', '3_in_4', '4_in_5', '4_in_6']) {
    assert.equal(componentSource.includes(forbidden), false, forbidden)
  }
})
