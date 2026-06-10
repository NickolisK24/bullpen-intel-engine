import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { default: BullpenBoardView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenBoardView.jsx',
)
const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/tonightsBullpenBoardView.js',
)

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

function roleCard(name, status, role) {
  return { pitcher_id: name.length + status.length, name, availability_status: status, role }
}

const longRole = {
  role_key: 'long_multi_inning',
  role: 'Long Relief / Multi-Inning Pattern',
  confidence: 'high',
  short_reason: 'Recent outings show repeated multi-inning workload.',
  evidence: ['3 appearances in the recent window', 'Average recent IP: 1.9', '3 of 3 outings above 1.0 IP'],
  limitations: ['Role is inferred from recent workload patterns only.', 'Does not include manager intent.'],
}

const lowRole = {
  role_key: 'low_unclear',
  role: 'Low Recent Usage / Unclear Pattern',
  confidence: 'low',
  short_reason: 'Too few recent appearances to establish a usage pattern.',
  evidence: ['1 appearance in the recent window'],
  limitations: ['Based on too few recent appearances to establish a pattern.'],
}

const insufficientRole = {
  role_key: 'insufficient_data',
  role: 'Insufficient Data',
  confidence: 'none',
  short_reason: 'Not enough recent usage data to classify a role.',
  evidence: [],
  limitations: ['No usable recent appearances with innings data.'],
}

const render = (board) => renderToStaticMarkup(React.createElement(BullpenBoardView, { board }))

test('role chip renders on the pitcher card with role and confidence', () => {
  const board = makeBoard({ cardsByStatus: { Available: [roleCard('Lou Long', 'Available', longRole)] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'Long / Multi-Inning'))
  assert.ok(htmlIncludes(html, 'Observed usage role: Long Relief / Multi-Inning Pattern'))
})

test('role explanation expands with reason, evidence, and limitations', () => {
  const board = makeBoard({ cardsByStatus: { Available: [roleCard('Lou Long', 'Available', longRole)] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'Usage role'))
  assert.ok(htmlIncludes(html, 'Observed role:'))
  assert.ok(htmlIncludes(html, 'Recent outings show repeated multi-inning workload.'))
  assert.ok(htmlIncludes(html, 'Average recent IP: 1.9'))            // evidence
  assert.ok(htmlIncludes(html, 'Does not include manager intent.'))  // limitation
})

test('low-confidence role displays its confidence', () => {
  const board = makeBoard({ cardsByStatus: { Monitor: [roleCard('Stu Short', 'Monitor', lowRole)] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'Low / Unclear Usage'))
  assert.ok(htmlIncludes(html, '· Unclear Read'))
})

test('insufficient-data role displays without inventing a pattern', () => {
  const board = makeBoard({ cardsByStatus: { Unavailable: [roleCard('Newt Rookie', 'Unavailable', insufficientRole)] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'Insufficient Data'))
  assert.ok(htmlIncludes(html, 'Not enough recent usage data to classify a role.'))
})

test('cards without a role simply omit the chip', () => {
  const board = makeBoard({ cardsByStatus: { Available: [{ pitcher_id: 1, name: 'No Role', availability_status: 'Available' }] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'No Role'))
  assert.ok(!htmlIncludes(html, 'Observed usage role:'))
})

test('role surface contains no advisory or recommendation language', () => {
  const board = makeBoard({
    cardsByStatus: {
      Available: [roleCard('Lou Long', 'Available', longRole)],
      Monitor: [roleCard('Stu Short', 'Monitor', lowRole)],
    },
  })
  const html = render(board).toLowerCase()
  for (const term of [
    'use this pitcher', 'best option', 'recommended role', 'should pitch',
    'deploy here', 'closer of the night', 'best arm', 'high-leverage recommendation',
  ]) {
    assert.ok(!html.includes(term), `leaked term: ${term}`)
  }
})

test('getRoleView maps key, labels, confidence, and neutral tone', () => {
  const v = view.getRoleView(longRole)
  assert.equal(v.key, 'long_multi_inning')
  assert.equal(v.shortLabel, 'Long / Multi-Inning')
  assert.equal(v.confidenceLabel, 'Strong Read')
  assert.equal(v.evidence.length, 3)
  assert.equal(view.getRoleView(null), null)
  // Insufficient/low use the muted tone; defined roles use the neutral tone.
  assert.notEqual(view.getRoleView(longRole).tone.color, view.getRoleView(insufficientRole).tone.color)
})
