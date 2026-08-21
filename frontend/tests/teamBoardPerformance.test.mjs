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

const { default: TeamBoardPerformance, PERFORMANCE_UNAVAILABLE_MESSAGE } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardPerformance.jsx',
)
const { default: TeamBoardRolesDeployment } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRolesDeployment.jsx',
)
const { default: SectionPair } = await server.ssrLoadModule('/src/components/UI/SectionPair.jsx')

const availableRead = {
  performance: {
    status: 'partial',
    metrics: [{ key: 'active_bullpen_era', label: 'Active Bullpen ERA', value: '3.42' }],
    summary: 'Active Bullpen ERA describes recorded results for the current active bullpen and remains supporting context.',
    sample_summary: 'Current regular season · 8 active arms · 7 with a sample · 31 relief appearances · 42.0 innings · Through Aug 20, 2026',
    limitations: ['WHIP, K-BB%, home-run rate, and inherited-runner outcomes are not included because they do not yet have approved public metric and sample contracts.'],
  },
  sectionStatus: { performance: { status: 'partial' } },
}

test('Performance renders the backend-owned active bullpen ERA and sample context', () => {
  const html = renderToStaticMarkup(React.createElement(TeamBoardPerformance, { read: availableRead }))

  assert.ok(html.includes('team-board-performance'))
  assert.ok(html.includes('Supporting context for the current active bullpen.'))
  assert.ok(html.includes('Active Bullpen ERA'))
  assert.ok(html.includes('3.42'))
  assert.ok(html.includes('31 relief appearances'))
  assert.ok(html.includes('Through Aug 20, 2026'))
  assert.ok(html.includes('WHIP, K-BB%'))
  assert.ok(html.includes('data-state="partial"'))
  assert.equal(html.includes('<button'), false)
})

test('Performance preserves below-sample and unavailable states without a number', () => {
  const partial = renderToStaticMarkup(React.createElement(TeamBoardPerformance, {
    read: {
      performance: {
        status: 'partial',
        metrics: [{ key: 'active_bullpen_era', label: 'Active Bullpen ERA', value: null }],
        summary: 'Not Enough Innings Yet',
        sample_summary: 'Current regular season · 8 active arms · 3 with a sample · 7 relief appearances · 9.0 innings · Through Aug 20, 2026',
        limitations: [],
      },
      sectionStatus: { performance: { status: 'partial' } },
    },
  }))
  const unavailable = renderToStaticMarkup(React.createElement(TeamBoardPerformance, {
    read: {
      performance: { status: 'unavailable' },
      sectionStatus: { performance: { status: 'unavailable' } },
    },
  }))

  assert.ok(partial.includes('Not Enough Innings Yet'))
  assert.ok(partial.includes('9.0 innings'))
  assert.equal(partial.includes('3.42'), false)
  assert.ok(unavailable.includes(PERFORMANCE_UNAVAILABLE_MESSAGE))
  assert.ok(unavailable.includes('data-state="unavailable"'))
})

test('Team Board has no internal Performance fetch or browser-authored metric calculation', async () => {
  const performanceSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardPerformance.jsx', import.meta.url), 'utf8')
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const adapterSource = await readFile(new URL('../src/adapters/teamBoardV2.js', import.meta.url), 'utf8')
  const apiSource = await readFile(new URL('../src/utils/api.js', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(boardSource.includes('<TeamBoardPerformance'))
  assert.ok(boardSource.includes('ratio="7:5"'))
  assert.ok(adapterSource.includes('performance: payload.performance'))
  for (const source of [performanceSource, boardSource, apiSource]) {
    assert.equal(source.includes('/api/internal/performance'), false)
    assert.equal(source.includes('active-bullpen-era'), false)
  }
  for (const forbiddenCalculation of ['earned_runs', 'innings_pitched', 'strikeouts', 'walks', 'home_runs', '.reduce(']) {
    assert.equal(performanceSource.includes(forbiddenCalculation), false, forbiddenCalculation)
  }
})

test('the 7:5 pair keeps role and Performance presentation compact', () => {
  const html = renderToStaticMarkup(React.createElement(
    SectionPair,
    { label: 'Roles and performance', ratio: '7:5' },
    React.createElement(TeamBoardRolesDeployment, { read: null }),
    React.createElement(TeamBoardPerformance, { read: availableRead }),
  ))

  assert.ok(html.includes('data-ratio="7:5"'))
  assert.ok(html.includes('A current backend-authored role composition is not available.'))
  assert.ok(html.includes('Active Bullpen ERA'))
  assert.ok(html.indexOf('Roles &amp; Deployment') < html.indexOf('Performance'))
})

test('Team Board retains exactly one chart and Performance adds none', async () => {
  const workloadSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardWorkloadOverview.jsx', import.meta.url), 'utf8')
  const performanceSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardPerformance.jsx', import.meta.url), 'utf8')

  assert.equal((workloadSource.match(/<WorkloadTrend/g) || []).length, 1)
  assert.equal(performanceSource.includes('chart'), false)
  assert.equal(performanceSource.includes('svg'), false)
  assert.equal(performanceSource.includes('canvas'), false)
})
