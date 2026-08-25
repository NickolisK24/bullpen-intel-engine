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

after(async () => {
  await server.close()
})

const { PitcherDetailContent } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherDetail.jsx',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Read the value rendered inside one Recent Workload Snapshot tile. Each tile
// emits its value div immediately before its label div, so scoping the match by
// label keeps the assertion off every other tile — a legitimate zero elsewhere
// can never satisfy or mask a Pitches/7d assertion.
function workloadTileValue(html, label) {
  const match = html.match(
    new RegExp(`>([^<>]*)</div><div[^>]*>${escapeRegExp(label)}</div>`),
  )
  return match ? match[1] : null
}

function detailData(pitchesLastSevenDays) {
  return {
    pitcher: {
      id: 42,
      full_name: 'Test Pitcher',
      team_name: 'Test Team',
      team_abbreviation: 'TST',
      position: 'P',
      throws: 'R',
    },
    current_fatigue: {
      calculated_at: '2026-08-16T11:00:00',
      days_since_last_appearance: 2,
      appearances_last_7: 2,
      appearances_last_14: 4,
      pitches_last_7_days: pitchesLastSevenDays,
      innings_last_7_days: 1.0,
    },
    roster_status: { status: 'ACTIVE', label: 'Active MLB' },
    pitcher_labels: {
      role: { key: 'setup_arm', label: 'Setup Arm', source: 'backend' },
      read: { key: 'watch_arm', label: 'Watch Arm', source: 'backend' },
    },
    freshness: { data_through: '2026-08-16' },
    last_workload_appearance: { game_date: '2026-08-15', pitches: 18 },
    recent_work: { capability: 'public_recent_work' },
    recent_work_status: { status: 'available' },
  }
}

function renderData(data) {
  return renderToStaticMarkup(
    React.createElement(PitcherDetailContent, {
      data,
      pitcherId: 42,
      onClose: () => {},
    }),
  )
}

const renderDetail = (pitchesLastSevenDays) => renderData(detailData(pitchesLastSevenDays))

test('unknown seven-day pitch workload renders as unavailable, not a fabricated zero', () => {
  const value = workloadTileValue(renderDetail(null), 'Pitches/7d')

  assert.equal(value, '—')
  assert.notEqual(value, '0')
})

test('undefined seven-day pitch workload renders as unavailable, not a fabricated zero', () => {
  const value = workloadTileValue(renderDetail(undefined), 'Pitches/7d')

  assert.equal(value, '—')
  assert.notEqual(value, '0')
})

test('a legitimate zero seven-day pitch workload still renders zero', () => {
  assert.equal(workloadTileValue(renderDetail(0), 'Pitches/7d'), '0')
})

test('a counted seven-day pitch workload renders unchanged', () => {
  assert.equal(workloadTileValue(renderDetail(41), 'Pitches/7d'), '41')
})

test('current-state answer passes through canonical role read roster workload and team handoff', () => {
  const html = renderDetail(41)

  for (const expected of [
    'Current Bullpen Situation',
    'Test Pitcher',
    'Active MLB',
    'Setup Arm',
    'Watch Arm',
    'Appearances / 7d',
    'Pitches / 7d',
    '2026-08-16',
    'Open Test Team Team Board',
    'href="/bullpen?view=board&amp;team=TST"',
  ]) {
    assert.ok(html.includes(expected), expected)
  }

  assert.equal(html.includes('fatigue_score'), false)
  assert.equal(html.includes('likely tonight'), false)
})

test('missing workload counts and raw pitch facts stay missing rather than becoming zero', () => {
  const data = detailData(null)
  data.current_fatigue.appearances_last_7 = null
  data.current_fatigue.appearances_last_14 = undefined
  data.recent_logs = [{
    id: 1,
    game_date: '2026-08-15',
    opponent_abbreviation: 'BOS',
    innings_pitched: 1,
    innings_pitched_outs: 3,
    pitches_thrown: null,
  }]
  const html = renderData(data)

  assert.equal(workloadTileValue(html, 'Apps/7d'), '—')
  assert.equal(workloadTileValue(html, 'Apps/14d'), '—')
  assert.ok(html.includes('<td class="text-right font-mono text-xs text-chalk200">—</td>'))
})

test('recent-work failure is local to its panel and keeps the current-state answer', () => {
  const data = detailData(41)
  data.recent_work = null
  data.recent_work_status = { status: 'unavailable' }
  const html = renderData(data)

  assert.ok(html.includes('Recent work is unavailable.'))
  assert.ok(html.includes('Setup Arm'))
  assert.ok(html.includes('Watch Arm'))
  assert.ok(html.includes('Active MLB'))
})

test('Pitcher detail uses one eager owner request and the composed recent-work payload', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )

  assert.equal((source.match(/getPitcherFatigue\(pitcherId\)/g) || []).length, 1)
  assert.equal(source.includes('getPitcherRecentWork'), false)
  assert.ok(source.includes('payload={recentWork}'))
  assert.ok(source.includes("recentWorkStatus?.status === 'unavailable'"))
})
