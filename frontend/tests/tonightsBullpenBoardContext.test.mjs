import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

import {
  makeBoard,
  staleBoard,
} from './fixtures/bullpenBoardFixtures.mjs'

// phase-0-clarity/03 removed the BullpenContextSummary component (its health
// statement and count snapshot restated the Team State card and the group
// headers). getBoardContextView remains the shared board-context view model --
// the Dashboard still derives its league confidence label from it -- so its
// contract stays covered here.

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const view = await server.ssrLoadModule(
  '/src/components/bullpen/board/tonightsBullpenBoardView.js',
)

test('getBoardContextView maps state, metrics, and degraded confidence', () => {
  const manageable = view.getBoardContextView(makeBoard({
    cardsByStatus: { Available: [{ pitcher_id: 1, name: 'A', availability_status: 'Available' }] },
  }))
  assert.equal(manageable.state, 'manageable')
  assert.equal(manageable.metrics.total, 1)
  assert.equal(manageable.isDegraded, false)
  assert.equal(manageable.snapshot.length, 4)

  const stale = view.getBoardContextView(staleBoard)
  assert.equal(stale.isDegraded, true)
  assert.equal(stale.state, 'constrained')

  assert.equal(view.getBoardContextView({}).hasContext, false)
})

test('board context view model exposes no scores, rankings, or governance jargon', () => {
  const serialized = JSON.stringify(view.getBoardContextView(makeBoard({
    cardsByStatus: {
      Available: Array.from({ length: 5 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
      Monitor: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: 20 + i, name: `M${i}`, availability_status: 'Monitor' })),
    },
  }))).toLowerCase()
  for (const term of [
    'ranking_applied', 'selection_made', 'readiness score', 'quality score',
    'composite', 'best option', 'top arm', 'recommend', 'priority score',
  ]) {
    assert.ok(!serialized.includes(term), `leaked term: ${term}`)
  }
})
