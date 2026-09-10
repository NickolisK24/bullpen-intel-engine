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

const { default: WorkloadPatterns, getWorkloadPatternsView } = await server.ssrLoadModule(
  '/src/components/bullpen/WorkloadPatterns.jsx',
)
const { PitcherDetailContent } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherDetail.jsx',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function factValue(html, label) {
  const match = html.match(
    new RegExp(`<dt[^>]*>${escapeRegExp(label)}</dt><dd[^>]*>([^<>]*)</dd>`),
  )
  return match ? match[1].trim() : null
}

function workloadSignal(inputs = {}, dataState = 'fresh') {
  return {
    availability_status: 'Limited',
    confidence: 'high',
    data_state: dataState,
    reasons: [],
    limitations: [],
    inputs: {
      reference_date: '2026-08-25',
      back_to_back: true,
      three_in_four: true,
      four_in_five: false,
      appearances_last_3_days: 2,
      pitches_last_3_days: 41,
      appearances_last_5_days: 3,
      pitches_last_5_days: 58,
      ...inputs,
    },
  }
}

function renderPatterns(signal = workloadSignal()) {
  return renderToStaticMarkup(React.createElement(WorkloadPatterns, { workloadSignal: signal }))
}

test('renders canonical multi-day patterns and short-window facts unchanged', () => {
  const html = renderPatterns()

  assert.equal(factValue(html, 'Back-to-back appearances'), 'Yes')
  assert.equal(factValue(html, '3 appearances in 4 days'), 'Yes')
  assert.equal(factValue(html, '4 appearances in 5 days'), 'No')
  assert.equal(factValue(html, 'Appearances / 3d'), '2')
  assert.equal(factValue(html, 'Pitches / 3d'), '41')
  assert.equal(factValue(html, 'Appearances / 5d'), '3')
  assert.equal(factValue(html, 'Pitches / 5d'), '58')
})

test('explicit false renders No while missing pattern facts stay absent', () => {
  const signal = workloadSignal({
    back_to_back: false,
    three_in_four: null,
    four_in_five: undefined,
  })
  const html = renderPatterns(signal)

  assert.equal(factValue(html, 'Back-to-back appearances'), 'No')
  assert.equal(factValue(html, '3 appearances in 4 days'), null)
  assert.equal(factValue(html, '4 appearances in 5 days'), null)
})

test('missing counts remain missing while legitimate zero remains zero', () => {
  const signal = workloadSignal({
    appearances_last_3_days: 0,
    pitches_last_3_days: null,
    appearances_last_5_days: undefined,
    pitches_last_5_days: -1,
  })
  const html = renderPatterns(signal)

  assert.equal(factValue(html, 'Appearances / 3d'), '0')
  assert.equal(factValue(html, 'Pitches / 3d'), null)
  assert.equal(factValue(html, 'Appearances / 5d'), null)
  assert.equal(factValue(html, 'Pitches / 5d'), null)
})

test('non-current workload carriers fail closed locally', () => {
  for (const dataState of ['missing', 'incomplete', 'stale']) {
    const signal = workloadSignal({}, dataState)
    const html = renderPatterns(signal)

    assert.ok(html.includes('Workload patterns are unavailable.'))
    assert.equal(html.includes('Back-to-back appearances'), false)
  }
  const missingState = workloadSignal()
  delete missingState.data_state
  assert.ok(renderPatterns(missingState).includes('Workload patterns are unavailable.'))
  assert.deepEqual(getWorkloadPatternsView(null), {
    available: false,
    facts: [],
  })
})

test('Pitcher detail keeps PIT-01 PIT-02 and PIT-03 healthy around workload patterns', () => {
  const data = {
    pitcher: {
      id: 42,
      full_name: 'Test Reliever',
      team_name: 'Test Club',
      team_abbreviation: 'TST',
      position: 'P',
      throws: 'R',
    },
    current_fatigue: {
      days_since_last_appearance: 1,
      appearances_last_7: 3,
      appearances_last_14: 5,
      pitches_last_7_days: 61,
      innings_last_7_days: 2,
    },
    availability: {
      availability_status: 'Limited',
      confidence: 'high',
      data_state: 'fresh',
      reasons: ['Back-to-back appearances'],
      limitations: [],
    },
    workload_signal: workloadSignal(),
    roster_status: { status: 'ACTIVE', label: 'Active MLB' },
    pitcher_labels: {
      role: { key: 'setup_arm', label: 'Setup Arm' },
      read: { key: 'watch_arm', label: 'Watch Arm' },
    },
    freshness: { data_through: '2026-08-24', product_current_date: '2026-08-25' },
    last_workload_appearance: { game_date: '2026-08-24', pitches: 28 },
    recent_work: {
      capability: 'public_recent_work',
      workload: { window_14: { appearances: 5, pitches_total: 82 } },
      recent_appearances: [{
        game_date: '2026-08-24',
        opponent_abbreviation: 'BOS',
        innings_pitched_outs: 3,
        pitches_thrown: 28,
      }],
    },
    recent_work_status: { status: 'available' },
  }
  const html = renderToStaticMarkup(
    React.createElement(PitcherDetailContent, { data, pitcherId: 42, onClose: () => {} }),
  )

  for (const expected of [
    'Current Bullpen Situation',
    'Final availability: Limited',
    'View availability details',
    'Recent Work',
    'Recent Appearances',
    'Workload Patterns',
  ]) {
    assert.ok(html.includes(expected), expected)
  }
  assert.equal((html.match(/dateTime="2026-08-24"/g) || []).length, 1)
})

test('Pitcher detail retains one eager owner request and no pattern fan-out', async () => {
  const detailSource = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )
  const patternSource = await readFile(
    new URL('../src/components/bullpen/WorkloadPatterns.jsx', import.meta.url),
    'utf8',
  )

  assert.equal((detailSource.match(/getPitcherFatigue\(pitcherId, options\)/g) || []).length, 1)
  assert.ok(detailSource.includes('<WorkloadPatterns workloadSignal={workloadSignal} />'))
  assert.equal(patternSource.includes('useFetch'), false)
  assert.equal(patternSource.includes('/api/'), false)
  assert.equal(patternSource.includes('fetch('), false)
})

test('presentation stays responsive descriptive and bounded to governed facts', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/WorkloadPatterns.jsx', import.meta.url),
    'utf8',
  )

  for (const className of ['min-w-0', 'grid-cols-2', 'xl:grid-cols-4', 'break-words']) {
    assert.ok(source.includes(className), className)
  }
  assert.equal(source.includes('overflow-x'), false)
  assert.equal(source.includes('appearances_last_7'), false)
  assert.equal(source.includes('appearances_last_14'), false)
  assert.equal(source.includes('pitches_last_7_days'), false)
  for (const forbidden of [
    '4_in_6',
    'multi_inning',
    'pitch_spike',
    'injury',
    'risk',
    'overworked',
    'likely',
    'should',
    'will pitch',
  ]) {
    assert.equal(source.toLowerCase().includes(forbidden), false, forbidden)
  }
})
