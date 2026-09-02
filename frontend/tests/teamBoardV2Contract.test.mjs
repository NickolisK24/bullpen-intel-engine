import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  TEAM_BOARD_V2_CAPABILITY,
  TEAM_BOARD_V2_CONTRACT_VERSION,
  TEAM_BOARD_CORE_CAPABILITY,
  TEAM_BOARD_CORE_CONTRACT_VERSION,
  TEAM_BOARD_DETAILS_CAPABILITY,
  TEAM_BOARD_DETAILS_CONTRACT_VERSION,
  isTeamBoardV2Payload,
  readTeamBoardDelivery,
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
  recent_usage: { appearances: [{ pitcher_name: 'Exact Source Name', pitches_thrown: null }] },
  recently_used_arms: {
    contract: 'team_board_recently_used_arms_v1',
    status: 'available',
    value: 1,
    window_days: 3,
    window_label: 'Last 3 days',
  },
  off_active_count: {
    contract: 'team_board_off_active_count_v1',
    status: 'available',
    value: 2,
    through: '2026-08-16',
    context_label: 'Current roster context',
  },
  workload_overview: {
    windows: [{ window_days: 7, relief_appearances: 3, pitches_total: null }],
    concentration: { label: 'Exact Concentration', summary: 'Backend workload sentence.' },
  },
  roles_deployment: {
    population_basis: 'current_visible_active_bullpen_public_role_reads',
    arm_count: 1,
    role_arm_count: 1,
    missing_role_count: 0,
    roles: [{ role_key: 'bridge_arm', label: 'Setup Arm', arm_count: 1 }],
  },
  rotation_impact: {
    population_basis: 'stored_team_game_pitching_splits',
    read: { starter_avg_innings: 5.2, summary: 'Backend sentence.' },
  },
  recent_transactions: {
    population_basis: 'explanatory_eligible_pitcher_transactions_touching_selected_team_in_latest_source_sync_window',
    status: 'available',
    events: [{ player_id: 7, player_name: 'Exact Source Name', date: '2026-08-16', label: 'Recalled' }],
  },
  roster_context: {},
  recent_relief_work: { read: { relief_by_date: [] } },
  game_context: null,
  section_status: {
    active_bullpen: { status: 'available' },
    recent_usage: { status: 'available' },
    rest_status: { status: 'unavailable' },
    workload_overview: { status: 'partial' },
    roles_deployment: { status: 'available' },
    rotation_impact: { status: 'available' },
    recent_transactions: { status: 'available' },
    recent_relief_work: { status: 'unavailable', reason_code: 'source_unavailable' },
  },
  limitations: [],
}

const identity = {
  contract: 'team_board_publication_identity_v1',
  team_id: 1,
  team_abbreviation: 'EX',
  snapshot_id: 1900,
  sync_run_id: 2900,
  represented_date: '2026-08-16',
  availability_reference_date: '2026-08-17',
  published_at: '2026-08-17T12:01:00',
  snapshot_generated_at: '2026-08-17T12:00:00',
  dashboard_payload_version: 1,
  publication_authority_contract: 'trusted_dashboard_publication_v1',
  team_board_package_contract: 'trusted_team_board_publication_v1',
  team_board_contract_version: TEAM_BOARD_V2_CONTRACT_VERSION,
  team_state_contract: 'team_state_public_v1',
  bullpen_membership_method_version: 'team_board_default_bullpen_membership_v1',
  rest_status_method_version: 'rest_status_v1',
  workload_windows_method_version: 'workload_windows_v1',
  deployment_profile_method_version: 'deployment_profile_v1',
  rotation_impact_method_version: 'rotation_support_pressure_v1',
}

const corePayload = {
  ...payload,
  capability: TEAM_BOARD_CORE_CAPABILITY,
  contract_version: TEAM_BOARD_CORE_CONTRACT_VERSION,
  publication_identity: identity,
}

const detailsPayload = {
  capability: TEAM_BOARD_DETAILS_CAPABILITY,
  contract_version: TEAM_BOARD_DETAILS_CONTRACT_VERSION,
  publication_identity: identity,
  represented_date: payload.represented_date,
  recent_usage: payload.recent_usage,
  recently_used_arms: payload.recently_used_arms,
  workload_overview: payload.workload_overview,
  roles_deployment: payload.roles_deployment,
  recent_transactions: payload.recent_transactions,
  recent_relief_work: payload.recent_relief_work,
  game_context: payload.game_context,
  performance: { status: 'available' },
  what_changed: { state: 'changes' },
  section_status: payload.section_status,
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
  assert.equal(view.recentUsage, payload.recent_usage)
  assert.equal(view.recentlyUsedArms, payload.recently_used_arms)
  assert.equal(view.offActiveCount, payload.off_active_count)
  assert.equal(view.recentUsage.appearances[0].pitches_thrown, null)
  assert.equal(view.workloadOverview, payload.workload_overview)
  assert.equal(view.workloadOverview.windows[0].pitches_total, null)
  assert.equal(view.rolesDeployment, payload.roles_deployment)
  assert.equal(view.rolesDeployment.roles[0].label, 'Setup Arm')
  assert.equal(view.sectionStatus, payload.section_status)
  assert.equal(view.rotationImpact.read.summary, 'Backend sentence.')
  assert.equal(view.recentTransactions, payload.recent_transactions)
  assert.equal(view.recentTransactions.events[0].label, 'Recalled')
})


test('answer core is useful before deferred sections resolve', () => {
  const view = readTeamBoardDelivery(corePayload)
  assert.equal(view.teamState, payload.team_state)
  assert.equal(view.activeBullpen, payload.active_bullpen)
  assert.equal(view.restStatus, payload.rest_status)
  assert.equal(view.performance, null)
  assert.equal(view.whatChanged, null)
  assert.equal(view.detailsAttached, false)
})


test('deferred sections attach only when every publication identity field matches', () => {
  const attached = readTeamBoardDelivery(corePayload, detailsPayload)
  assert.equal(attached.detailsAttached, true)
  assert.equal(attached.performance, detailsPayload.performance)
  assert.equal(attached.whatChanged, detailsPayload.what_changed)

  const mismatched = readTeamBoardDelivery(corePayload, {
    ...detailsPayload,
    publication_identity: { ...identity, snapshot_id: 1901 },
  })
  assert.equal(mismatched.detailsAttached, false)
  assert.equal(mismatched.detailsRejected, true)
  assert.equal(mismatched.performance, null)
  assert.equal(mismatched.whatChanged, null)
  assert.equal(mismatched.teamState, payload.team_state)
})


test('Team Board loads the answer core first and defers identified depth', async () => {
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  const adapterSource = await readFile(
    new URL('../src/adapters/teamBoardV2.js', import.meta.url),
    'utf8',
  )
  const apiSource = await readFile(new URL('../src/utils/api.js', import.meta.url), 'utf8')

  assert.equal(boardSource.includes('getTeamBoardCore(selectedTeam)'), true)
  assert.equal(boardSource.includes('getTeamBoardDetails(selectedTeam, coreIdentity)'), true)
  assert.equal(boardSource.includes('<TeamBoardAnswerBlock'), true)
  assert.equal(boardSource.includes('<TeamBoardActiveBullpen'), true)
  assert.equal(boardSource.includes('<TeamBoardRecentUsage'), true)
  assert.equal(boardSource.includes('<TeamBoardRestStatus'), true)
  assert.equal(boardSource.includes('<TeamBoardWorkloadOverview'), true)
  assert.equal(boardSource.includes('<TeamBoardRolesDeployment'), true)
  assert.equal(boardSource.includes('<TeamBoardRotationImpact'), true)
  assert.equal(boardSource.includes('<TeamBoardRecentTransactions'), true)
  assert.equal((boardSource.match(/getTeamBoardCore\(/g) || []).length, 1)
  assert.equal((boardSource.match(/getTeamBoardDetails\(/g) || []).length, 1)
  assert.match(
    apiSource,
    /getTeamBoardCore = \(teamId\) => request\(`\/bullpen\/teams\/\$\{encodeURIComponent\(teamId\)\}\/board-v2\/core`\)/,
  )
  for (const forbidden of ['reduce(', '/ 3', 'Math.round', 'public_state =', 'summary =']) {
    assert.equal(adapterSource.includes(forbidden), false, forbidden)
  }
})
