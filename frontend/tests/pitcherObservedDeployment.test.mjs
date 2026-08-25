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

const { default: ObservedDeployment, getObservedDeploymentView } = await server.ssrLoadModule(
  '/src/components/bullpen/ObservedDeployment.jsx',
)
const { PitcherDetailContent } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherDetail.jsx',
)

const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function factValue(html, label) {
  const match = html.match(
    new RegExp(`<dt[^>]*>${escapeRegExp(label)}</dt><dd[^>]*>(.*?)</dd>`),
  )
  return match ? match[1].replace(/<[^>]+>/g, '').trim() : null
}

function deploymentContext(profile = {}) {
  return {
    contract: 'pitcher_observed_deployment_context_v1',
    status: 'complete',
    reason_code: null,
    data_through: '2026-08-24',
    window_days: 14,
    source_contract: 'team_board_deployment_profile_carrier_v1',
    profile: {
      pitcher_id: 42,
      appearances_analyzed: 7,
      saves: 2,
      holds: 3,
      games_finished: 5,
      appearances_with_games_finished: 6,
      multi_inning_appearances: 1,
      appearances_with_outs: 7,
      most_recent_multi_inning_date: '2026-08-19',
      limitations: [],
      ...profile,
    },
    limitations: profile.limitations || [],
  }
}

function renderDeployment(context = deploymentContext()) {
  return renderToStaticMarkup(React.createElement(ObservedDeployment, { context }))
}

test('renders exact observed deployment facts with canonical denominators', () => {
  const html = renderDeployment()

  assert.ok(html.includes('Observed Deployment'))
  assert.ok(html.includes('14-day window'))
  assert.ok(html.includes('Through'))
  assert.equal(factValue(html, 'Saves'), '2')
  assert.equal(factValue(html, 'Holds'), '3')
  assert.equal(factValue(html, 'Games finished'), '5 of 6 recorded appearances')
  assert.equal(factValue(html, 'Multi-inning'), '1 of 7 appearances with recorded outs')
  assert.equal(factValue(html, 'Last multi-inning'), 'Aug 19, 2026')
  assert.ok(html.includes('dateTime="2026-08-19"'))
})

test('canonical zero remains zero when its evidence denominator is present', () => {
  const html = renderDeployment(deploymentContext({
    saves: 0,
    holds: 0,
    games_finished: 0,
    appearances_with_games_finished: 2,
    multi_inning_appearances: 0,
    appearances_with_outs: 3,
    most_recent_multi_inning_date: null,
  }))

  assert.equal(factValue(html, 'Saves'), '0')
  assert.equal(factValue(html, 'Holds'), '0')
  assert.equal(factValue(html, 'Games finished'), '0 of 2 recorded appearances')
  assert.equal(factValue(html, 'Multi-inning'), '0 of 3 appearances with recorded outs')
  assert.equal(factValue(html, 'Last multi-inning'), null)
})

test('missing coverage never becomes a zero-denominator deployment claim', () => {
  const context = deploymentContext({
    games_finished: 0,
    appearances_with_games_finished: 0,
    multi_inning_appearances: 0,
    appearances_with_outs: null,
    limitations: [
      'Games-finished counts include only appearances with recorded finish authority.',
      'Multi-inning counts include only appearances with recorded outs.',
    ],
  })
  const html = renderDeployment(context)

  assert.equal(factValue(html, 'Games finished'), null)
  assert.equal(factValue(html, 'Multi-inning'), null)
  assert.equal(html.includes('0 of 0 recorded appearances'), false)
  for (const limitation of context.limitations) assert.ok(html.includes(limitation))
})

test('quiet and unavailable carriers remain local explicit states', () => {
  const quiet = deploymentContext()
  quiet.profile = null
  assert.ok(renderDeployment(quiet).includes('No relief deployment is represented in this window.'))

  for (const context of [
    null,
    { status: 'withheld', reason_code: 'data_through_missing' },
    { status: 'unavailable', reason_code: 'deployment_context_unavailable' },
  ]) {
    assert.ok(renderDeployment(context).includes('Observed deployment is unavailable.'))
  }
  assert.deepEqual(getObservedDeploymentView(null), {
    state: 'unavailable',
    facts: [],
    limitations: [],
  })
})

test('deployment failure leaves PIT-01 through PIT-04 healthy', () => {
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
    workload_signal: {
      availability_status: 'Limited',
      confidence: 'high',
      data_state: 'fresh',
      reasons: [],
      limitations: [],
      inputs: { back_to_back: true, appearances_last_3_days: 2 },
    },
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
    deployment_context: {
      status: 'unavailable',
      reason_code: 'deployment_context_unavailable',
    },
  }
  const html = renderToStaticMarkup(
    React.createElement(PitcherDetailContent, { data, pitcherId: 42, onClose: () => {} }),
  )

  for (const expected of [
    'Current Bullpen Situation',
    'Final availability: Limited',
    'Recent Work',
    'Recent Appearances',
    'Workload Patterns',
    'Observed deployment is unavailable.',
  ]) {
    assert.ok(html.includes(expected), expected)
  }
})

test('Observed Deployment adds no request or frontend baseball authority', async () => {
  const detailSource = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )
  const source = await readFile(
    new URL('../src/components/bullpen/ObservedDeployment.jsx', import.meta.url),
    'utf8',
  )

  assert.equal((detailSource.match(/getPitcherFatigue\(pitcherId\)/g) || []).length, 1)
  assert.ok(detailSource.includes('<ObservedDeployment context={deploymentContext} />'))
  for (const requestToken of ['useFetch', '/api/', 'fetch(', 'getTeamBoard']) {
    assert.equal(source.includes(requestToken), false, requestToken)
  }
  for (const forbidden of [
    'leverage',
    'entry band',
    'role movement',
    'likely to pitch',
    'likely closer',
    'next up',
    'manager will use',
    'probable ninth-inning',
  ]) {
    assert.equal(source.toLowerCase().includes(forbidden), false, forbidden)
  }
})

test('responsive source remains compact at mobile and desktop widths', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/ObservedDeployment.jsx', import.meta.url),
    'utf8',
  )

  for (const className of [
    'min-w-0',
    'grid-cols-2',
    'sm:grid-cols-3',
    'lg:grid-cols-5',
    'break-words',
  ]) {
    assert.ok(source.includes(className), className)
  }
  assert.equal(source.includes('overflow-x'), false)
})
