import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import {
  APPROVED_READ_LABELS,
  APPROVED_ROLE_LABELS,
} from '../src/utils/pitcherLabels.js'
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
const visibleText = (html) => html
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

function roleCard(name, status, role, overrides = {}) {
  return {
    pitcher_id: name.length + status.length,
    name,
    availability_status: status,
    fatigue_score: 25,
    confidence: 'high',
    data_state: 'fresh',
    role,
    ...overrides,
  }
}

const longRole = {
  role_key: 'long_multi_inning',
  role: 'Long Relief / Multi-Inning Pattern',
  confidence: 'high',
  short_reason: 'Recent outings show repeated multi-inning workload.',
  evidence: ['3 appearances in the recent window', 'Average recent IP: 1.9', '3 of 3 outings above 1.0 IP'],
  limitations: ['Role is inferred from recent workload patterns only.', 'Does not include manager intent.'],
}

const trustRole = {
  role_key: 'late_high_leverage',
  role: 'Late / High-Leverage Pattern',
  confidence: 'high',
  short_reason: 'Recent outings show late relief usage.',
  evidence: ['3 late relief appearances in the recent window'],
  limitations: ['Role is inferred from recent workload patterns only.'],
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

test('role and read label chips render product labels only on the pitcher card', () => {
  const board = makeBoard({ cardsByStatus: { Available: [roleCard('Lou Long', 'Available', longRole)] } })
  const html = render(board)
  const text = visibleText(html)
  assert.ok(text.includes('Coverage Arm'))
  assert.ok(text.includes('Clean Option'))
  assert.ok(!htmlIncludes(html, 'Role</span>Coverage Arm'))
  assert.ok(!htmlIncludes(html, 'Read</span>Clean Option'))
  assert.ok(htmlIncludes(html, 'Observed role:'))
  assert.ok(htmlIncludes(html, 'Long Relief / Multi-Inning Pattern'))
})

test('trust and clean option chips do not carry layer prefixes', () => {
  const board = makeBoard({ cardsByStatus: { Available: [roleCard('Terry Trust', 'Available', trustRole)] } })
  const html = render(board)
  const text = visibleText(html).toUpperCase()
  assert.ok(text.includes('TRUST ARM'))
  assert.ok(text.includes('CLEAN OPTION'))
  assert.equal(text.includes('ROLE TRUST ARM'), false)
  assert.equal(text.includes('READ CLEAN OPTION'), false)
})

test('pitcher card renders role chip before read chip and ahead of caveats', () => {
  const board = makeBoard({
    cardsByStatus: {
      Monitor: [
        roleCard('Terry Trust', 'Monitor', trustRole, {
          roster_status: {
            status: 'ACTIVE',
            label: 'Active MLB',
            confidence: 'high',
            is_authoritative: true,
          },
        }),
      ],
    },
  })
  const html = render(board)
  const cardStart = html.indexOf('Terry Trust')
  const roleKindIndex = html.indexOf('data-label-kind="role"', cardStart)
  const readKindIndex = html.indexOf('data-label-kind="read"', cardStart)
  const roleLabelIndex = html.indexOf('Trust Arm', cardStart)
  const readLabelIndex = html.indexOf('Watch Arm', cardStart)
  const caveatIndex = html.indexOf('Active MLB', cardStart)

  assert.ok(cardStart > -1)
  assert.ok(roleKindIndex > cardStart)
  assert.ok(readKindIndex > roleKindIndex)
  assert.ok(roleLabelIndex > cardStart)
  assert.ok(readLabelIndex > roleLabelIndex)
  assert.ok(caveatIndex > readLabelIndex)
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

test('low-confidence role remains a limited role read with a watch read', () => {
  const board = makeBoard({ cardsByStatus: { Monitor: [roleCard('Stu Short', 'Monitor', lowRole)] } })
  const html = render(board)
  const text = visibleText(html)
  assert.ok(text.includes('Limited Read'))
  assert.ok(text.includes('Watch Arm'))
  assert.ok(!htmlIncludes(html, 'Role</span>Limited Read'))
  assert.ok(!htmlIncludes(html, 'Read</span>Watch Arm'))
})

test('insufficient-data role displays without inventing a pattern', () => {
  const board = makeBoard({ cardsByStatus: { Unavailable: [roleCard('Newt Rookie', 'Unavailable', insufficientRole)] } })
  const html = render(board)
  const text = visibleText(html)
  assert.ok(text.includes('Limited Read'))
  assert.ok(text.includes('Unavailable'))
  assert.ok(htmlIncludes(html, 'Not enough recent usage data to classify a role.'))
})

test('cards without a role fall back to limited role read', () => {
  const board = makeBoard({ cardsByStatus: { Available: [{ pitcher_id: 1, name: 'No Role', availability_status: 'Available' }] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'No Role'))
  assert.ok(visibleText(html).includes('Limited Read'))
  assert.ok(!htmlIncludes(html, 'Observed role:'))
})

test('pitcher label key renders both label layers', () => {
  const board = makeBoard({ cardsByStatus: { Available: [roleCard('Lou Long', 'Available', longRole)] } })
  const html = render(board)
  assert.ok(htmlIncludes(html, 'Pitcher Label Key'))
  assert.ok(htmlIncludes(html, 'Role:'))
  assert.ok(htmlIncludes(html, 'Read:'))
  assert.ok(htmlIncludes(html, 'What type of bullpen arm is this?'))
  assert.ok(htmlIncludes(html, 'What do workload and availability say about this pitcher tonight?'))
  assert.ok(htmlIncludes(html, 'Trust Arm'))
  assert.ok(htmlIncludes(html, 'Rest-Restricted'))
  assert.ok(!htmlIncludes(html, 'Role</span>Trust Arm'))
  assert.ok(!htmlIncludes(html, 'Read</span>Clean Option'))
})

test('pitcher label key uses the approved public terminology only', () => {
  const board = makeBoard({ cardsByStatus: { Available: [roleCard('Lou Long', 'Available', longRole)] } })
  const html = render(board)
  const keyStart = html.indexOf('Pitcher Label Key')
  const keyEnd = html.indexOf('</details>', keyStart)
  const keyHtml = html.slice(keyStart, keyEnd)

  for (const label of APPROVED_ROLE_LABELS) {
    assert.ok(keyHtml.includes(label), `missing role label: ${label}`)
  }
  for (const label of APPROVED_READ_LABELS) {
    assert.ok(keyHtml.includes(label), `missing read label: ${label}`)
  }
  for (const rejected of [
    'Trusted Arm',
    'High Trust Arm',
    'Late-Inning Arm',
    'Clean Arm',
    'Fresh Option',
    'Fresh Arm',
  ]) {
    assert.equal(keyHtml.includes(rejected), false, `introduced label variant: ${rejected}`)
  }
})

test('pitcher label chip layout keeps mobile wrapping guards', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/BullpenBoardView.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('flex flex-wrap items-center gap-1.5'))
  assert.ok(source.includes('inline-flex max-w-full items-center gap-1.5'))
  assert.ok(source.includes('min-w-0 truncate sm:whitespace-nowrap'))
  assert.ok(source.includes('2xl:grid-cols-2'))
  assert.ok(source.includes('flex min-w-0 flex-wrap gap-1.5'))
})

test('visible board text does not leak prefixed label or raw label keys', () => {
  const board = makeBoard({
    cardsByStatus: {
      Available: [roleCard('Terry Trust', 'Available', trustRole)],
      Monitor: [roleCard('Stu Short', 'Monitor', lowRole)],
    },
  })
  const html = render(board)
  for (const term of [
    'Role</span>Trust Arm',
    'Read</span>Clean Option',
    'Role</span>Bridge Arm',
    'Read</span>Watch Arm',
  ]) {
    assert.equal(htmlIncludes(html, term), false, `leaked term: ${term}`)
  }
  const text = visibleText(html).toUpperCase()
  for (const term of [
    'ROLE TRUST ARM',
    'READ CLEAN OPTION',
    'ROLE BRIDGE ARM',
    'ROLE_',
    'READ_',
  ]) {
    assert.equal(text.includes(term), false, `leaked term: ${term}`)
  }
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
  assert.equal(v.shortLabel, 'Coverage Arm')
  assert.equal(v.confidenceLabel, 'Strong Read')
  assert.equal(v.evidence.length, 3)
  assert.equal(view.getRoleView(null), null)
  // Insufficient/low use the muted tone; defined roles use the neutral tone.
  assert.notEqual(view.getRoleView(longRole).tone.color, view.getRoleView(insufficientRole).tone.color)
})
