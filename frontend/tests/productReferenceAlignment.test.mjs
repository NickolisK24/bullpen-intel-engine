import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('public routes use the Daily Edition, Slate, and complete League Board surfaces', () => {
  const app = read('../src/App.jsx')
  assert.match(app, /path: '\/', Component: DailyEdition/)
  assert.match(app, /path: '\/slate', Component: Slate/)
  assert.match(app, /path: '\/dashboard', Component: LeagueBoard/)
})

test('league board consumes backend-owned Team State and never derives it from counts', () => {
  const board = read('../src/components/product/LeagueBoard.jsx')
  const api = read('../src/utils/api.js')
  assert.ok(board.includes('getLeagueTeamStateBoard'))
  assert.ok(api.includes("request('/bullpen/league-board')"))
  assert.equal(/clean_option_count\s*[<>=]/.test(board), false)
  assert.equal(/active_read_count\s*[<>=]/.test(board), false)
})

test('daily edition follows the supplied lead, league rail, change, and slate hierarchy', () => {
  const source = read('../src/components/product/DailyEdition.jsx')
  for (const label of ["Today's Lead", 'Across MLB', 'What changed', 'Tonight']) {
    assert.ok(source.includes(label), label)
  }
})
