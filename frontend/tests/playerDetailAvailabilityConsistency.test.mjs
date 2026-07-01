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
    React.createElement(AvailabilitySummary, payload),
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
    },
    lastAppearance: { game_date: '2026-06-20', pitches: 15 },
  })

  assert.ok(htmlIncludes(html, '15 pitches today'))
  assert.equal(htmlIncludes(html, '15 pitches yesterday'), false)
})

test('PitcherDetail passes final availability workload signal and roster status to the summary', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('workload_signal: workloadSignal'))
  assert.ok(source.includes('roster_status: rosterStatus'))
  assert.ok(source.includes('freshness'))
  assert.ok(source.includes('last_appearance: lastAppearance'))
  assert.ok(source.includes('last_workload_appearance: lastWorkloadAppearance'))
  assert.ok(source.includes('latestWorkloadAppearanceFromLogs(recent_logs)'))
  assert.ok(source.includes('Most Recent Workload Appearance'))
  assert.ok(source.includes('recent_logs.slice(0, 8).map(log =>'))
  assert.ok(source.includes('workloadSignal={workloadSignal}'))
  assert.ok(source.includes('rosterStatus={rosterStatus}'))
  assert.ok(source.includes('freshness={freshness}'))
  assert.ok(source.includes('lastAppearance={mostRecentAppearance}'))
})
