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

const { PitcherDetailContent, matchesPitcherEdition } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherDetail.jsx',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Read one PIT-01 current-state fact without allowing a legitimate zero from a
// different fact to satisfy the missing-not-zero contract.
function currentStateFactValue(html, label) {
  const match = html.match(
    new RegExp(`<dt[^>]*>${escapeRegExp(label)}</dt><dd[^>]*>([^<>]*)</dd>`),
  )
  return match ? match[1].trim() : null
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
    arm_context: { mode: 'current', days_rest: 2 },
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
  const value = currentStateFactValue(renderDetail(null), 'Pitches / 7d')

  assert.equal(value, '—')
  assert.notEqual(value, '0')
})

test('undefined seven-day pitch workload renders as unavailable, not a fabricated zero', () => {
  const value = currentStateFactValue(renderDetail(undefined), 'Pitches / 7d')

  assert.equal(value, '—')
  assert.notEqual(value, '0')
})

test('a legitimate zero seven-day pitch workload still renders zero', () => {
  assert.equal(currentStateFactValue(renderDetail(0), 'Pitches / 7d'), '0')
})

test('a counted seven-day pitch workload renders unchanged', () => {
  assert.equal(currentStateFactValue(renderDetail(41), 'Pitches / 7d'), '41')
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
  assert.match(html, /<h1[^>]*>Test Pitcher<\/h1>/)
  assert.equal(html.includes('Close selected pitcher detail'), false)
})

test('Current Read stays primary while Availability explains its supporting relationship', () => {
  const data = detailData(41)
  data.availability = {
    availability_status: 'Monitor',
    confidence: 'high',
    data_state: 'fresh',
    reasons: ['Recent workload needs a check.'],
    limitations: [],
  }
  const html = renderData(data)
  const currentReadIndex = html.indexOf('Current Read')
  const relationshipIndex = html.indexOf(
    'Availability supports Current Read; evidence and roster limits can also shape the final read.',
  )

  assert.ok(currentReadIndex > -1)
  assert.ok(relationshipIndex > currentReadIndex)
  assert.ok(html.includes('Final availability: On Watch'))
  assert.ok(html.includes('Read Confidence'))
  assert.equal((html.match(/Final availability: On Watch/g) || []).length, 1)
})

test('missing Availability keeps the existing honest unavailable state', () => {
  const html = renderDetail(41)

  assert.ok(html.includes('Current availability is not available for this pitcher yet.'))
  assert.ok(html.indexOf('Current Read') < html.indexOf('Current availability is not available'))
})

test('missing workload counts and composed ledger pitch facts stay missing rather than becoming zero', () => {
  const data = detailData(null)
  data.current_fatigue.appearances_last_7 = null
  data.current_fatigue.appearances_last_14 = undefined
  data.recent_work = {
    capability: 'public_recent_work',
    recent_appearances: [{
      id: 1,
      game_date: '2026-08-15',
      opponent_abbreviation: 'BOS',
      innings_pitched: 1,
      innings_pitched_outs: 3,
      pitches_thrown: null,
    }],
    workload: { window_14: { appearances: null, pitches_total: null } },
  }
  const html = renderData(data)

  assert.equal(currentStateFactValue(html, 'Appearances / 7d'), '—')
  assert.ok(html.includes('Appearances / 14d'))
  assert.equal(html.includes('0 P'), false)
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

  assert.equal((source.match(/getPitcherFatigue\(pitcherId, options\)/g) || []).length, 1)
  assert.equal(source.includes('getPitcherRecentWork'), false)
  assert.ok(source.includes('payload={recentWork}'))
  assert.ok(source.includes("recentWorkStatus?.status === 'unavailable'"))
  assert.equal(source.includes('max-h-[calc(100vh-3rem)]'), false)
  assert.equal(source.includes('overflow-y-auto'), false)
  assert.equal(source.includes('sticky top-6'), false)
})

test('historical Murphy detail keeps recorded role and pitch count while withholding current claims', () => {
  const data = detailData(0)
  data.pitcher.full_name = 'Owen Murphy'
  data.pitcher_labels.read.label = 'Clean Option'
  data.availability = { availability_status: 'Available', data_state: 'stale' }
  data.last_workload_appearance = { game_date: '2026-09-22', pitches: 50 }
  for (const context of [{ mode: 'historical' }, undefined]) {
    const html = renderData({ ...data, arm_context: context })
    assert.match(html, /Recorded Bullpen Workload/)
    assert.match(html, /Setup Arm/)
    assert.match(html, /50 pitches/)
    assert.equal(currentStateFactValue(html, 'Days Rest'), '—')
    assert.doesNotMatch(html, /Clean Option|Final availability: Available/)
  }
})

test('routed detail shows measured series, incomplete readings and no unknown hand', () => {
  const data = detailData(41)
  data.pitcher.throws = null
  data.recent_work.workload_series = [{ date: '2026-08-10', pitches: 0, opponent: 'BOS' }]
  data.season_pitch_characteristics = { through: '2026-08-16', months: [
    { month: '2026-08', types: [{ type: 'FF', pitches: 22, mean_mph: 95.4, mix_percent: 55 }] },
  ] }
  const html = renderData(data)
  for (const value of ['30-day workload', '2026-08-10', 'Season velocity and pitch mix',
    '22 pitches (55%)', '95.4', 'Inning and leverage usage', 'Observed deployment movement',
    'Two comparable published seven-day windows are unavailable']) assert.ok(html.includes(value), value)
  assert.ok(!html.includes('Throws'))
  data.pitcher.throws = 'L'
  assert.ok(renderData(data).includes('Throws L'))
})

test('individual performance discloses both outing samples and preserves zero and withheld rates', () => {
  const metrics = Object.fromEntries(['era', 'whip', 'k_bb_percent', 'hr9', 'inherited'].map(key =>
    [key, { value: null, covered: 0 }]))
  const window = { start: '2026-01-01', through: '2026-09-28', outings: 2, metrics }
  const html = renderData({ ...detailData(0), performance: {
    season: window, recent: { ...window, start: '2026-08-30', outings: 1,
      metrics: { ...metrics, era: { value: '0.00', covered: 1 } } },
  } })
  for (const text of ['Individual relief performance', 'Season to date', 'Last 30 days', '0.00',
    '1/1 with inputs', '0/2 with inputs', 'Withheld', 'Published role and arm reads']) assert.ok(html.includes(text), text)
})

test('history cites both ends of a published change and identifies a missing edition', async () => {
  const { PublicationDays } = await server.ssrLoadModule('/src/components/bullpen/PitcherPerformanceHistory.jsx')
  const html = renderToStaticMarkup(React.createElement(PublicationDays, { days: [
    { date: '2026-09-28', edition: { team: 'BOS', role: 'Trusted Arm', read: 'Watch Arm',
      snapshot_id: 9, citation: '/share/second', reference_date: '2026-09-29' },
      changes: { role: { from: 'Setup Arm', citation: '/share/first' } } },
    { date: '2026-09-26', edition: null, changes: {} },
  ] }))
  for (const text of ['/share/first', '/share/second', 'Setup Arm', 'Trusted Arm', 'Watch Arm',
    'No citable pitcher label']) assert.ok(html.includes(text), text)
})

test('archived editions remain searchable when the current publication date is missing', () => {
  const html = renderData({ ...detailData(0), freshness: {} })
  assert.ok(html.includes('Select a week to view archived editions.'))
})

test('isolated pitcher editions identify the player and keep research within the selected edition', () => {
  const data = detailData(0)
  delete data.freshness
  const html = renderData({
    ...data, scope: 'isolated_historical_core', current_serving_eligible: false,
    arm_context: { mode: 'historical', days_rest: null },
    data_through: '2026-08-15',
  })
  for (const text of ['Test Pitcher', 'Test Team', 'Historical edition · 2026-08-15',
    '30-day workload', 'Season velocity and pitch mix', 'Inning and leverage usage',
    'Observed deployment movement']) assert.ok(html.includes(text), text)
  assert.equal(currentStateFactValue(html, 'Current Read'), 'Withheld')
  assert.ok(!html.includes('Open Test Team Team Board'))
  assert.ok(!html.includes('Published role and arm reads'))
})


test('a historical pitcher handoff must agree on edition, public ID and MLB identity', () => {
  const generation = 'a'.repeat(64)
  const page = { scope: 'isolated_historical_core', current_serving_eligible: false, generation,
    selection_revision: 3, public_pitcher_id: 8997, pitcher: { id: 8997, mlb_id: 11100 },
    identity: { public_id: 8997, mlb_id: 11100 } }
  assert.ok(matchesPitcherEdition(page, 8997, 3, generation))
  for (const bad of [{ generation: 'b'.repeat(64) }, { selection_revision: 2 }, { public_pitcher_id: 11100 },
    { current_serving_eligible: true }, { identity: { public_id: 8997, mlb_id: 11101 } }]) {
    assert.ok(!matchesPitcherEdition({ ...page, ...bad }, 8997, 3, generation))
  }
})

test('historical seven-day counts use the dated regular-season bullpen window', () => {
  const data = { ...detailData(99), scope: 'isolated_historical_core', data_through: '2017-08-28' }
  const window = { through: data.data_through, first: '2017-08-22', player_observed: true, gaps: {},
    facts: { appearances: 2, pitches_thrown: 37 } }
  data.sections = { workload: { value: { windows: { '7': window } } } }
  const count = label => currentStateFactValue(renderData(data), label)
  assert.match(renderData(data), /Seven-day totals cover regular-season bullpen work, including qualifying openers/)
  assert.equal(count('Appearances / 7d'), '2')
  assert.equal(count('Pitches / 7d'), '37')
  window.facts = { appearances: 1, pitches_thrown: null }
  assert.equal(count('Appearances / 7d'), '1')
  assert.equal(count('Pitches / 7d'), '—')
  window.facts = { appearances: 0, pitches_thrown: 0 }
  assert.equal(count('Pitches / 7d'), '0')
  for (const replacement of [{ ...window, gaps: { '2017-08-24': 'missing_compatible_final' } },
    { ...window, through: '2017-08-27' }, { ...window, player_observed: false }, null]) {
    data.sections.workload.value.windows['7'] = replacement
    assert.equal(count('Appearances / 7d'), '—')
    assert.equal(count('Pitches / 7d'), '—')
  }
})


test('historical pitcher returns to the same club and edition', () => {
  const generation = 'b'.repeat(64)
  const data = { ...detailData(0), scope: 'isolated_historical_core', selection_revision: 2, generation,
    identity: { team_id: 137 }, pitcher: { team_id: 137, full_name: 'Albert Suárez', team_name: 'San Francisco Giants' } }
  const href = 'href="/bullpen?view=board&amp;team=137&amp;rehearsalRevision=2&amp;rehearsalGeneration=' + generation + '"'
  assert.ok(renderData(data).includes(href))
  for (const delta of [{ identity: { team_id: 111 } }, { identity: { team_id: null } }, { generation: null }]) {
    assert.ok(!renderData({ ...data, ...delta }).includes('Open San Francisco Giants Team Board'))
  }
})
