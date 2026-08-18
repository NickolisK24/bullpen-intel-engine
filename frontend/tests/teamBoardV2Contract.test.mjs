import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  TEAM_BOARD_V2_CAPABILITY,
  TEAM_BOARD_V2_CONTRACT_VERSION,
  isTeamBoardV2Payload,
  readTeamBoardV2,
} from '../src/adapters/teamBoardV2.js'


const payload = {
  capability: TEAM_BOARD_V2_CAPABILITY,
  contract_version: TEAM_BOARD_V2_CONTRACT_VERSION,
  team: { team_id: 1, team_name: 'Example Club', team_abbreviation: 'EX' },
  represented_date: '2026-08-16',
  freshness: { data_through: '2026-08-16' },
  team_state: {
    available: true,
    public_state: 'fresh',
    public_label: 'Fresh',
    summary: 'Backend-authored canonical summary.',
  },
  summary: 'Backend-authored canonical summary.',
  active_bullpen: {
    population_basis: 'current_scored_bullpen_eligible_pitchers',
    arm_count: 1,
    arms: [{
      pitcher_id: 7,
      workload: { pitches_last_7_days: null, appearances_last_7: 2 },
    }],
  },
  rest_status: { available: false, active_arm_count: null },
  rotation_impact: { read: { starter_avg_innings: 5.2, summary: 'Backend sentence.' } },
  roster_context: {},
  recent_relief_work: { read: { relief_by_date: [] } },
  game_context: null,
  section_status: {
    active_bullpen: { status: 'available' },
    recent_relief_work: { status: 'unavailable', reason_code: 'source_unavailable' },
  },
  limitations: [],
}


test('v2 guard pins the capability and contract version', () => {
  assert.equal(isTeamBoardV2Payload(payload), true)
  assert.equal(isTeamBoardV2Payload({ ...payload, capability: 'tonights_bullpen_board' }), false)
  assert.equal(isTeamBoardV2Payload({ ...payload, contract_version: 'team-board-1.0.0' }), false)
})


test('adapter passes backend semantics and nulls through unchanged', () => {
  const view = readTeamBoardV2(payload)

  assert.equal(view.teamState, payload.team_state)
  assert.equal(view.summary, payload.summary)
  assert.equal(view.activeBullpen, payload.active_bullpen)
  assert.equal(view.activeBullpen.arms[0].workload.pitches_last_7_days, null)
  assert.equal(view.restStatus.active_arm_count, null)
  assert.equal(view.sectionStatus, payload.section_status)
  assert.equal(view.rotationImpact.read.summary, 'Backend sentence.')
})


test('TB-02 reuses the v2 read for Answer Block and Active Bullpen without frontend derivation', async () => {
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  const adapterSource = await readFile(
    new URL('../src/adapters/teamBoardV2.js', import.meta.url),
    'utf8',
  )
  const apiSource = await readFile(new URL('../src/utils/api.js', import.meta.url), 'utf8')

  assert.equal(boardSource.includes('getTeamBoardV2(selectedTeam)'), true)
  assert.equal(boardSource.includes('<TeamBoardAnswerBlock'), true)
  assert.equal(boardSource.includes('<TeamBoardActiveBullpen'), true)
  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.match(
    apiSource,
    /getTeamBoardV2 = \(teamId\) => request\(`\/bullpen\/teams\/\$\{encodeURIComponent\(teamId\)\}\/board-v2`\)/,
  )
  for (const forbidden of ['reduce(', '/ 3', 'Math.round', 'public_state =', 'summary =']) {
    assert.equal(adapterSource.includes(forbidden), false, forbidden)
  }
})
