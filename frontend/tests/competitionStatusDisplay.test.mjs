// DEC-02 competition status display (WP-0.1).
//
// A club the backend withholds because its season is complete, or because its
// competition status is unconfirmed, shows the backend-owned status label in
// place of a Team State. The frontend only accepts the backend's exact
// outcome/label pair; it never derives a club's season status.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
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

const { readPublicTeamState } = await server.ssrLoadModule('/src/adapters/publicTeamState.js')

const seasonComplete = {
  contract: 'team_state_public_v1',
  available: false,
  public_state: null,
  public_label: null,
  summary: null,
  outcome: 'season_complete',
  unavailable_message: "This club's season is complete, so there is no current Team State read.",
  reason_code: 'postseason_series_lost',
  data_through: '2026-10-14',
  status_label: 'Season Complete',
  final_recorded_date: '2026-10-12',
}

test('a season-complete withholding carries its label and final recorded date', () => {
  const read = readPublicTeamState(seasonComplete)
  assert.equal(read.available, false)
  assert.equal(read.publicLabel, null)
  assert.equal(read.statusLabel, 'Season Complete')
  assert.equal(read.finalRecordedDate, '2026-10-12')
  assert.equal(read.unavailableMessage, seasonComplete.unavailable_message)
})

test('an unconfirmed status shows its label and makes no dated season claim', () => {
  const read = readPublicTeamState({
    ...seasonComplete,
    outcome: 'competition_status_unconfirmed',
    status_label: 'Status Unconfirmed',
    final_recorded_date: '2026-10-12',
  })
  assert.equal(read.available, false)
  assert.equal(read.statusLabel, 'Status Unconfirmed')
  assert.equal(read.finalRecordedDate, null)
})

test('a label that does not match its outcome fails closed to no status label', () => {
  assert.equal(readPublicTeamState({ ...seasonComplete, status_label: 'Eliminated' }).statusLabel, null)
  assert.equal(
    readPublicTeamState({ ...seasonComplete, outcome: 'data_limited' }).statusLabel,
    null,
  )
  const available = readPublicTeamState({
    ...seasonComplete,
    available: true,
    public_state: 'fresh',
    public_label: 'Fresh',
    outcome: 'available',
  })
  assert.equal(available.available, true)
  assert.equal(available.statusLabel, null)
  assert.equal(available.finalRecordedDate, null)
})

test('the board and league listing render the backend status label', () => {
  const board = readFileSync('src/components/bullpen/board/TeamBoardAnswerBlock.jsx', 'utf8')
  assert.match(board, /view\.teamState\.statusLabel/)
  assert.match(board, /view\.teamState\.finalRecordedDate/)
  const listing = readFileSync('src/components/dashboard/LeagueTeamStateLandscape.jsx', 'utf8')
  assert.match(listing, /team\.teamState\.statusLabel \|\| 'Read unavailable'/)
})
