import assert from 'node:assert/strict'
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

function renderDetail(pitchesLastSevenDays) {
  return renderToStaticMarkup(
    React.createElement(PitcherDetailContent, {
      data: {
        pitcher: {
          id: 42,
          full_name: 'Test Pitcher',
          team_name: 'Test Team',
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
      },
      pitcherId: 42,
      onClose: () => {},
    }),
  )
}

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
