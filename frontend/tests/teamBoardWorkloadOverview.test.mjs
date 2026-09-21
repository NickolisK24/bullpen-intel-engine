import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { frozenTeamWorkloadFixture } from './fixtures/teamBoardFrozenWorkload.mjs'
import { readTeamBoardFrozenWorkload } from '../src/adapters/teamBoardV2.js'

const server = await createServer({ root: process.cwd(), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
after(async () => server.close())
const { default: TeamBoardWorkloadOverview } = await server.ssrLoadModule('/src/components/bullpen/board/TeamBoardWorkloadOverview.jsx')
const identity = { represented_date: '2026-09-02', publication_authority_contract: 'trusted_dashboard_publication_v1' }
const render = carrier => renderToStaticMarkup(React.createElement(TeamBoardWorkloadOverview, {
  read: { frozenTeamWorkload: readTeamBoardFrozenWorkload(carrier, identity) },
}))

test('four backend-authored windows render in direct comparison with pitches, appearances, and outs', () => {
  const html = render(frozenTeamWorkloadFixture())
  const labels = ['3 Days', '7 Days', '14 Days', '30 Days']
  for (const label of labels) assert.ok(html.includes(label), label)
  for (let index = 1; index < labels.length; index++) assert.ok(html.indexOf(labels[index - 1]) < html.indexOf(labels[index]))
  assert.match(html, /data-window-days="3"[\s\S]*?>0<[\s\S]*?>0<[\s\S]*?>0</)
  assert.match(html, /data-window-days="7"[\s\S]*?>88<[\s\S]*?>8<[\s\S]*?>22</)
  assert.match(html, /data-window-days="14"[\s\S]*?>220<[\s\S]*?>17<[\s\S]*?>49</)
  assert.match(html, /data-window-days="30"[\s\S]*?>430<[\s\S]*?>34<[\s\S]*?>102</)
  assert.ok(html.includes('<table'))
  assert.ok(html.includes('scope="row"'))
  assert.ok(html.includes('scope="col"'))
})

test('metric evidence remains independent; null never becomes zero', () => {
  const carrier = frozenTeamWorkloadFixture()
  carrier.windows.window_7.outs = { value: null, status: 'partial', reason_codes: ['slate_coverage_incomplete'] }
  carrier.windows.window_14.pitches = { value: null, status: 'unknown', reason_codes: ['appearance_pitch_count_unknown'] }
  carrier.windows.window_30.appearances = { value: null, status: 'unavailable', reason_codes: ['slate_coverage_unavailable'] }
  const html = render(carrier)
  assert.ok(html.includes('7 Days Outs: partial'))
  assert.ok(html.includes('14 Days Pitches: unknown'))
  assert.ok(html.includes('30 Days Appearances: unavailable'))
  assert.ok(html.includes('Not published'))
  assert.ok(html.includes('7 Days Pitches: 88'))
  assert.ok(html.includes('3 Days Pitches: 0'))
  assert.equal(html.includes('null'), false)
})

test('concentration and leading contributors use backend order, share, and active state', () => {
  const html = render(frozenTeamWorkloadFixture())
  assert.ok(html.includes('Top 3 arms account for 80% of 7-day pitches.'))
  assert.ok(html.indexOf('Fixture Reliever') < html.indexOf('Former Reliever'))
  assert.ok(html.indexOf('Former Reliever') < html.indexOf('Third Reliever'))
  assert.ok(html.includes('5 pitchers contributed'))
  assert.ok(html.includes('Current active bullpen:'))
  assert.ok(html.includes('Recent off-active contributors:'))
  assert.ok(html.includes('70 pitches'))
  assert.ok(html.includes('18 pitches'))
})

test('an unavailable concentration does not invent a share, contributors, or trend', () => {
  const carrier = frozenTeamWorkloadFixture()
  carrier.concentration_7_day = {
    status: 'unavailable', reason_codes: ['slate_coverage_unavailable'], total_pitches: null,
    top_3_share: null, pitcher_count: null, contributors: [], top_contributor: null,
    top_3_contributors: [], active_current_contribution: null, off_active_contribution: null,
  }
  const html = render(carrier)
  assert.ok(html.includes('Seven-day concentration is not published'))
  for (const forbidden of ['account for', 'workload-trend', 'rising', 'falling', 'overworked', 'fatigue', 'dangerously']) {
    assert.equal(html.toLowerCase().includes(forbidden), false, forbidden)
  }
})

test('loading, missing carrier, and errors are section-local', () => {
  assert.ok(renderToStaticMarkup(React.createElement(TeamBoardWorkloadOverview, { loading: true })).includes('workload-overview-skeleton'))
  assert.ok(renderToStaticMarkup(React.createElement(TeamBoardWorkloadOverview, { read: {} })).includes('Frozen team workload is not published'))
  const html = renderToStaticMarkup(React.createElement(TeamBoardWorkloadOverview, { error: 'private exception' }))
  assert.ok(html.includes('Workload overview could not be loaded'))
  assert.equal(html.includes('private exception'), false)
})

test('the frontend does not aggregate team or contributor baseball facts', async () => {
  const component = await readFile(new URL('../src/components/bullpen/board/TeamBoardWorkloadOverview.jsx', import.meta.url), 'utf8')
  const adapter = await readFile(new URL('../src/adapters/teamBoardV2.js', import.meta.url), 'utf8')
  for (const forbidden of ['.reduce(', '.sort(', 'top_3_share =', 'total_pitches =', 'workload_score', 'fatigue']) {
    assert.equal(component.includes(forbidden), false, forbidden)
  }
  assert.equal(adapter.includes('workloadMetricKeys.map(key => [key, readWorkloadMetric(window[key])])'), true)
  assert.equal(component.includes('recentReliefWork'), false)
})
