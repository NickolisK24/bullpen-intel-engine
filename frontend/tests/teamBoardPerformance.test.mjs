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

test('Performance ships the valid flat unavailable destination without metrics or retry', () => {
  const html = renderToStaticMarkup(React.createElement(TeamBoardPerformance))

  assert.ok(html.includes('team-board-performance'))
  assert.ok(html.includes('<h2'))
  assert.ok(html.includes('Performance'))
  assert.ok(html.includes(PERFORMANCE_UNAVAILABLE_MESSAGE))
  assert.ok(html.includes('data-state="unavailable"'))
  assert.equal(html.includes('<button'), false)
  for (const metric of ['ERA', 'WHIP', 'K-BB%', 'Inherited runners', 'Home runs']) {
    assert.equal(html.includes(metric), false, metric)
  }
})

test('Team Board has no internal Performance fetch or browser-authored metric calculation', async () => {
  const performanceSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardPerformance.jsx', import.meta.url), 'utf8')
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const adapterSource = await readFile(new URL('../src/adapters/teamBoardV2.js', import.meta.url), 'utf8')
  const apiSource = await readFile(new URL('../src/utils/api.js', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(boardSource.includes('<TeamBoardPerformance'))
  assert.ok(boardSource.includes('ratio="7:5"'))
  assert.equal(adapterSource.includes('performance'), false)
  for (const source of [performanceSource, boardSource, apiSource]) {
    assert.equal(source.includes('/api/internal/performance'), false)
    assert.equal(source.includes('active-bullpen-era'), false)
  }
  for (const forbiddenCalculation of ['earned_runs', 'innings_pitched', 'strikeouts', 'walks', 'home_runs', '.reduce(']) {
    assert.equal(performanceSource.includes(forbiddenCalculation), false, forbiddenCalculation)
  }
})

test('the 7:5 pair holds both governed unavailable destinations', () => {
  const html = renderToStaticMarkup(React.createElement(
    SectionPair,
    { label: 'Roles and performance', ratio: '7:5' },
    React.createElement(TeamBoardRolesDeployment, { read: null }),
    React.createElement(TeamBoardPerformance),
  ))

  assert.ok(html.includes('data-ratio="7:5"'))
  assert.ok(html.includes('A current backend-authored role composition is not available.'))
  assert.ok(html.includes(PERFORMANCE_UNAVAILABLE_MESSAGE))
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
