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

const { default: AvailabilitySummary } = await server.ssrLoadModule(
  '/src/components/bullpen/AvailabilitySummary.jsx',
)
const { PitcherDetailContent } = await server.ssrLoadModule(
  '/src/components/bullpen/PitcherDetail.jsx',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

function finalAvailability(rosterLabel, rosterStatus, workloadStatus) {
  return {
    availability: {
      availability_status: 'Unavailable',
      confidence: 'high',
      data_state: 'fresh',
      reasons: [`Roster status: ${rosterLabel}.`],
      limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
      roster_status: {
        status: rosterStatus,
        label: rosterLabel,
        confidence: 'high',
        is_authoritative: true,
        is_inactive_context: true,
      },
    },
    workloadSignal: {
      availability_status: workloadStatus,
      confidence: workloadStatus === 'Available' ? 'high' : 'medium',
      data_state: 'fresh',
      reasons: [`Workload-only signal: ${workloadStatus}.`],
      limitations: ['No injury information available'],
    },
  }
}

function renderSummary(payload) {
  return renderToStaticMarkup(
    React.createElement(AvailabilitySummary, { ...payload, initialDetailsOpen: true }),
  )
}

function renderDetail(data) {
  return renderToStaticMarkup(
    React.createElement(PitcherDetailContent, {
      data,
      pitcherId: 42,
      onClose: () => {},
    }),
  )
}

test('player detail summary keeps Graham Ashcraft 60-day IL final availability unavailable', () => {
  const html = renderSummary(finalAvailability('60-Day IL', 'IL_60', 'Available'))

  assert.ok(htmlIncludes(html, 'Final availability: Unavailable'))
  assert.ok(htmlIncludes(html, 'Roster Status'))
  assert.ok(htmlIncludes(html, '60-Day IL'))
  assert.ok(htmlIncludes(html, 'Workload Signal'))
  assert.ok(htmlIncludes(html, 'Workload signal: Available'))
  assert.ok(htmlIncludes(html, 'Roster status: 60-Day IL.'))
  assert.equal(htmlIncludes(html, 'Final availability: Available'), false)
})

test('player detail summary keeps 15-day IL final availability unavailable when workload is monitor', () => {
  for (const name of ['Emilio Pagan', 'Pierce Johnson']) {
    const html = renderSummary(finalAvailability('15-Day IL', 'IL_15', 'Monitor'))

    assert.ok(htmlIncludes(html, 'Final availability: Unavailable'), name)
    assert.ok(htmlIncludes(html, 'Roster Status'), name)
    assert.ok(htmlIncludes(html, '15-Day IL'), name)
    assert.ok(htmlIncludes(html, 'Workload Signal'), name)
    assert.ok(htmlIncludes(html, 'Workload signal: On Watch'), name)
    assert.equal(htmlIncludes(html, 'Final availability: On Watch'), false, name)
  }
})

test('player detail summary leaves active pitcher final availability aligned with workload signal', () => {
  const payload = {
    availability: {
      availability_status: 'Available',
      confidence: 'high',
      data_state: 'fresh',
      reasons: ['Workload signals are inside normal ranges.'],
      limitations: ['No injury information available'],
      roster_status: {
        status: 'ACTIVE',
        label: 'Active MLB',
        confidence: 'high',
        is_authoritative: true,
        is_inactive_context: false,
      },
    },
    workloadSignal: {
      availability_status: 'Available',
      confidence: 'high',
      data_state: 'fresh',
      reasons: ['Workload signals are inside normal ranges.'],
      limitations: ['No injury information available'],
    },
  }

  const html = renderSummary(payload)

  assert.ok(htmlIncludes(html, 'Final availability: Available'))
  assert.ok(htmlIncludes(html, 'Workload signal: Available'))
  assert.ok(htmlIncludes(html, 'Active MLB'))
})

test('final availability reasons use day-aware appearance wording', () => {
  const html = renderSummary({
    availability: {
      availability_status: 'Monitor',
      confidence: 'medium',
      data_state: 'fresh',
      reasons: ['15 pitches yesterday'],
      limitations: ['No injury information available'],
      roster_status: {
        status: 'ACTIVE',
        label: 'Active MLB',
        confidence: 'high',
        is_authoritative: true,
        is_inactive_context: false,
      },
    },
    workloadSignal: {
      availability_status: 'Monitor',
      confidence: 'medium',
      data_state: 'fresh',
      reasons: ['15 pitches yesterday'],
      limitations: ['No injury information available'],
    },
    freshness: {
      data_through: '2026-06-20',
      availability_reference_date: '2026-06-21',
      product_current_date: '2026-06-21',
    },
    lastAppearance: { game_date: '2026-06-20', pitches: 15 },
  })

  assert.ok(htmlIncludes(html, '15 pitches yesterday'))
  assert.equal(htmlIncludes(html, '15 pitches today'), false)
})

test('PitcherDetail passes final availability workload signal and roster status to the summary', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('workload_signal: workloadSignal'))
  assert.ok(source.includes('roster_status: rosterStatus'))
  assert.ok(source.includes('freshness'))
  assert.ok(source.includes('last_workload_appearance: lastWorkloadAppearance'))
  assert.equal(source.includes('last_appearance: lastAppearance'), false)
  assert.equal(source.includes('latestWorkloadAppearanceFromLogs'), false)
  assert.equal(source.includes('Most Recent Workload Appearance'), false)
  assert.equal(source.includes('recent_logs.slice(0, 8).map(log =>'), false)
  assert.ok(source.includes('workloadSignal={workloadSignal}'))
  assert.ok(source.includes('rosterStatus={rosterStatus}'))
  assert.ok(source.includes('freshness={freshness}'))
  assert.ok(source.includes('lastAppearance={mostRecentAppearance}'))
  assert.ok(source.includes('fetchExplanation={pitcherId ? () => getAvailabilityExplanation(pitcherId) : null}'))
  assert.equal(source.includes('<ExplanationDisclosure'), false)
})

test('PitcherDetail does not reconstruct a withheld workload appearance from recent logs', () => {
  const html = renderDetail({
    pitcher: { full_name: 'Withheld Arm', team_name: 'Test Club', position: 'P', throws: 'R' },
    freshness: {
      data_through: '2026-08-30',
      availability_reference_date: '2026-08-31',
      product_current_date: '2026-08-31',
    },
    last_workload_appearance: null,
    recent_logs: [{
      game_date: '2026-08-30',
      pitches_thrown: 31,
      innings_pitched_outs: 3,
    }],
  })

  assert.equal(htmlIncludes(html, 'Last Used'), false)
  assert.equal(htmlIncludes(html, 'Aug 30'), false)
  assert.equal(htmlIncludes(html, '31 pitches'), false)
})

test('PitcherDetail leads with availability and workload facts instead of a black-box score', () => {
  const html = renderDetail({
    pitcher: {
      full_name: 'Test Reliever',
      team_name: 'Test Club',
      position: 'P',
      throws: 'R',
    },
    current_fatigue: {
      raw_score: 88,
      risk_level: 'CRITICAL',
      days_since_last_appearance: 1,
      pitches_last_7_days: 61,
      appearances_last_7: 3,
      innings_last_7_days: 2,
      appearances_last_14: 5,
    },
    availability: {
      availability_status: 'Limited',
      confidence: 'medium',
      data_state: 'fresh',
      reasons: ['61 pitches across three appearances in the last seven days.'],
      limitations: ['No injury information available.'],
      roster_status: {
        status: 'ACTIVE',
        label: 'Active MLB',
        confidence: 'high',
        is_authoritative: true,
        is_inactive_context: false,
      },
    },
    workload_signal: {
      availability_status: 'Limited',
      confidence: 'medium',
      data_state: 'fresh',
      reasons: ['61 pitches across three appearances in the last seven days.'],
      limitations: ['No injury information available.'],
    },
    freshness: {
      data_through: '2026-07-05',
      availability_reference_date: '2026-07-06',
      product_current_date: '2026-07-06',
    },
    last_workload_appearance: {
      game_date: '2026-07-05',
      pitches: 28,
    },
    recent_logs: [
      {
        id: 1,
        game_date: '2026-07-05',
        opponent_abbreviation: 'BOS',
        innings_pitched: 1,
        innings_pitched_outs: 3,
        pitches_thrown: 28,
      },
    ],
  })

  assert.ok(htmlIncludes(html, 'Final availability: Limited'))
  assert.ok(htmlIncludes(html, 'Data through'))
  assert.ok(htmlIncludes(html, '2026-07-05'))
  assert.ok(htmlIncludes(html, 'Jul 5 (Yesterday) • 28 pitches'))
  assert.ok(htmlIncludes(html, 'View availability details'))
  assert.equal(htmlIncludes(html, 'Final Availability Reasons'), false)
  assert.equal(htmlIncludes(html, '61 pitches across three appearances in the last seven days.'), false)
  assert.equal(htmlIncludes(html, 'Limitations'), false)
  assert.equal(htmlIncludes(html, 'No injury information available.'), false)
  assert.ok(htmlIncludes(html, 'Pitches / 7d'))
  assert.equal(htmlIncludes(html, 'Recent Workload Snapshot'), false)
  assert.ok(htmlIncludes(html, '61'))
  assert.ok(htmlIncludes(html, 'Days Rest'))

  for (const forbidden of [
    'Workload Index',
    '0-100',
    'Workload Profile',
    'Workload Trend',
    'CRITICAL',
    '>88<',
  ]) {
    assert.equal(htmlIncludes(html, forbidden), false, forbidden)
  }
})
