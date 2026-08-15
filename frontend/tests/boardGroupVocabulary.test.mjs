// VOC-001 / #638 — the Team Board renders the BACKEND-AUTHORED group vocabulary.
//
// Production snapshot 398 proved the backend payload already publishes five
// distinct governed groups, including two zero-count restricted workload tiers:
// 'Unavailable — Heavy Workload' (engine key Avoid) and 'Unavailable — Severe
// Workload' (engine key Unavailable). The frontend previously merged those two
// into one frontend-authored 'Unavailable' heading with its own copy. These
// tests lock the repair: the browser owns layout, never group semantics.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import { snapshot398Board, snapshot398GroupShape } from './fixtures/bullpenBoardFixtures.mjs'

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
const { default: BullpenAvailabilityDistribution } = await server.ssrLoadModule(
  '/src/components/bullpen/board/BullpenAvailabilityDistribution.jsx',
)
const view = await server.ssrLoadModule('/src/components/bullpen/board/tonightsBullpenBoardView.js')
const availabilityView = await server.ssrLoadModule('/src/components/bullpen/availabilityView.js')
const pitcherLabels = await server.ssrLoadModule('/src/utils/pitcherLabels.js')

const boardViewSource = readFileSync('src/components/bullpen/board/tonightsBullpenBoardView.js', 'utf8')

const escapeRegExp = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const visibleText = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const render = board => renderToStaticMarkup(React.createElement(BullpenBoardView, { board }))
const renderDistribution = board =>
  renderToStaticMarkup(React.createElement(BullpenAvailabilityDistribution, { board }))

const HEAVY = {
  status: 'Avoid',
  label: 'Unavailable — Heavy Workload',
  description: 'Recent workload crosses the stronger restriction threshold and keeps these arms out of the available group.',
}
const SEVERE = {
  status: 'Unavailable',
  label: 'Unavailable — Severe Workload',
  description: 'Recent workload crosses the most restrictive workload threshold in the current availability read.',
}

// The exact copy the frontend used to author for its merged group. It must
// never come back as Team Board group vocabulary.
const RETIRED_MERGED_GROUP_COPY = "Recent workload or roster context keeps these arms out of tonight's available group."

// The fixture mirrors the shape production actually published.
test('the fixture matches the snapshot 398 group shape', () => {
  assert.deepEqual(
    snapshot398Board.groups.map(g => ({ status: g.status, label: g.label, count: g.count })),
    snapshot398GroupShape,
  )
})

test('a zero-count Avoid group keeps its backend heading, with no generic replacement', () => {
  const group = view.getBoardGroups(snapshot398Board).find(g => g.status === 'Avoid')
  assert.equal(group.count, 0)
  assert.equal(group.label, HEAVY.label)

  const html = render(snapshot398Board)
  assert.ok(htmlIncludes(html, HEAVY.label))
  assert.ok(htmlIncludes(html, `aria-label="${HEAVY.label} group"`))
  // No frontend-authored semantic substitute for this governed group.
  assert.equal(htmlIncludes(html, 'aria-label="Unavailable group"'), false)
  assert.equal(htmlIncludes(html, 'Unavailable Pitchers'), false)
  // The engine key is never reader vocabulary.
  assert.equal(htmlIncludes(html, 'Avoid'), false)
})

test('a zero-count Unavailable group keeps its backend heading, with no generic replacement', () => {
  const group = view.getBoardGroups(snapshot398Board).find(g => g.status === 'Unavailable')
  assert.equal(group.count, 0)
  assert.equal(group.label, SEVERE.label)

  const html = render(snapshot398Board)
  assert.ok(htmlIncludes(html, SEVERE.label))
  assert.ok(htmlIncludes(html, `aria-label="${SEVERE.label} group"`))
  assert.equal(htmlIncludes(html, 'aria-label="Unavailable group"'), false)
})

test('the backend description survives verbatim for both zero-count groups', () => {
  const groups = view.getBoardGroups(snapshot398Board)
  assert.equal(groups.find(g => g.status === 'Avoid').description, HEAVY.description)
  assert.equal(groups.find(g => g.status === 'Unavailable').description, SEVERE.description)

  const text = visibleText(render(snapshot398Board))
  assert.ok(htmlIncludes(text, HEAVY.description))
  assert.ok(htmlIncludes(text, SEVERE.description))
})

test('the two restricted groups remain distinct sections without duplicated header counts', () => {
  const groups = view.getBoardGroups(snapshot398Board)
  const restricted = groups.filter(g => g.status === 'Avoid' || g.status === 'Unavailable')
  assert.equal(restricted.length, 2)
  assert.notEqual(restricted[0].label, restricted[1].label)
  assert.notEqual(restricted[0].description, restricted[1].description)
  assert.notEqual(restricted[0].emptyCopy, restricted[1].emptyCopy)

  // Empty-group policy is unchanged, while counts are owned by the compact
  // four-status summary above the board.
  const html = render(snapshot398Board)
  assert.equal(
    html.indexOf(`aria-label="${HEAVY.label} group"`) < html.indexOf(`aria-label="${SEVERE.label} group"`),
    true,
  )
  const text = visibleText(html)
  assert.ok(htmlIncludes(text, HEAVY.label))
  assert.ok(htmlIncludes(text, SEVERE.label))
  assert.equal(htmlIncludes(text, `${HEAVY.label} 0`), false)
})

test('governed board groups stay distinct while the summary uses four public counts', () => {
  const groups = view.getBoardGroups(snapshot398Board)
  assert.deepEqual(groups.map(g => g.status), ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable'])
  assert.equal(new Set(groups.map(g => g.label)).size, groups.length)
  assert.deepEqual(groups.map(g => g.count), [4, 3, 2, 0, 0])
  // The merge helper the board used to run is gone from the governed path.
  assert.equal(/mergePublicUnavailableGroups/.test(boardViewSource), false)

  // The compact summary is explicitly the four-reader-status presentation.
  const distribution = visibleText(renderDistribution(snapshot398Board))
  assert.ok(htmlIncludes(distribution, 'Unavailable 0'))
  assert.equal(htmlIncludes(distribution, HEAVY.label), false)
  assert.equal(htmlIncludes(distribution, SEVERE.label), false)
})

test('populated groups are unchanged: backend labels, counts, and cards', () => {
  const groups = view.getBoardGroups(snapshot398Board)
  assert.deepEqual(
    groups.filter(g => g.count > 0).map(g => [g.label, g.count, g.pitchers.length]),
    [['Available Arms', 4, 4], ['On-Watch Arms', 3, 3], ['Limited Arms', 2, 2]],
  )
  assert.equal(view.getBoardTotals(snapshot398Board).total, 9)

  const text = visibleText(render(snapshot398Board))
  assert.ok(htmlIncludes(text, 'Available Arms'))
  assert.ok(htmlIncludes(text, 'On-Watch Arms'))
  assert.ok(htmlIncludes(text, 'Limited Arms'))
  assert.ok(htmlIncludes(text, 'Available Arm 1'))
  assert.ok(htmlIncludes(text, 'Limited Arm 2'))
})

test('the retired merged-group copy is not recreated as Team Board group vocabulary', () => {
  assert.equal(boardViewSource.includes(RETIRED_MERGED_GROUP_COPY), false)
  assert.equal(htmlIncludes(visibleText(render(snapshot398Board)), RETIRED_MERGED_GROUP_COPY), false)
})

// The fix narrows ONE thing: the board group heading. 'Unavailable' stays a
// legitimate pitcher-level word — it is a real availability status, a real
// public status label, and a real pitcher read chip. Nothing here bans it.
test('pitcher-level Unavailable vocabulary is untouched', () => {
  assert.equal(availabilityView.getAvailabilityStatusLabel('Unavailable'), 'Unavailable')
  assert.equal(availabilityView.getAvailabilityStatusLabel('Avoid'), 'Unavailable')
  assert.equal(availabilityView.getAvailabilityBadgeView('Unavailable').label, 'Unavailable')
  assert.equal(availabilityView.getAvailabilityBadgeView('Unavailable').status, 'Unavailable')
  assert.equal(availabilityView.getAvailabilityBadgeView('Avoid').status, 'Avoid')
  assert.equal(pitcherLabels.PITCHER_READ_LABELS.UNAVAILABLE.label, 'Unavailable')

  // A pitcher card still renders the plain Unavailable chip...
  const card = { pitcher_id: 9, name: 'Uri Unavailable', availability_status: 'Unavailable' }
  assert.equal(view.getBoardCardView(card).badge.label, 'Unavailable')

  // ...while the group that pitcher lands in is headed by the backend's
  // severity-named group label, not the bare status word.
  const board = {
    ...snapshot398Board,
    groups: snapshot398Board.groups.map(group =>
      group.status === 'Unavailable' ? { ...group, count: 1, pitchers: [card] } : group,
    ),
    total_pitchers: 10,
  }
  const html = render(board)
  assert.ok(htmlIncludes(html, `aria-label="${SEVERE.label} group"`))
  assert.equal(htmlIncludes(html, 'aria-label="Unavailable group"'), false)
  assert.ok(htmlIncludes(html, 'Uri Unavailable'))
})
