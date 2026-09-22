import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { frozenTeamWorkloadFixture } from './fixtures/teamBoardFrozenWorkload.mjs'
import { frozenPublicDeploymentFixture } from './fixtures/teamBoardFrozenDeployment.mjs'

import {
  TEAM_BOARD_V2_CAPABILITY,
  TEAM_BOARD_V2_CONTRACT_VERSION,
  TEAM_BOARD_CORE_CAPABILITY,
  TEAM_BOARD_CORE_CONTRACT_VERSION,
  TEAM_BOARD_DETAILS_CAPABILITY,
  TEAM_BOARD_DETAILS_CONTRACT_VERSION,
  getTeamBoardDetailsIdentity,
  isTeamBoardV2Payload,
  readTeamBoardDelivery,
  readTeamBoardRecentUsageRest,
  readTeamBoardFrozenWorkload,
  readTeamBoardFrozenDeployment,
  readTeamBoardFrozenPerformance,
  readTeamBoardFrozenRotationGames,
  readTeamBoardFrozenRosterTransactions,
  readTeamBoardV2,
  teamBoardIdentityKey,
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
    contract: 'team_board_roster_transactions_v1',
    team_board_package_contract: 'trusted_team_board_publication_v1',
    team_id: 1,
    data_through: '2026-08-16',
    population_basis: 'explanatory_eligible_pitcher_transactions_touching_selected_team_in_latest_source_sync_window',
    status: 'available',
    events: [{ event_id: 'tx-7', player_id: 7, player_name: 'Exact Source Name', date: '2026-08-16', type: 'recall', label: 'Recalled', description: 'Exact Source Name was recalled.', direction: 'addition', source: 'mlb_stats_api:transactions', evidence_status: 'complete', current_roster: { status: 'complete', membership: 'active', label: 'Active bullpen' } }],
    window_start_date: '2026-08-10',
    window_end_date: '2026-08-16',
    limitations: [],
    current_group: { population_basis: 'trusted_team_boards.default_pitcher_ids', active_count: 1, active_pitcher_ids: [7] },
    off_active_recent_contributors: { status: 'complete', window_days: 7, contributors: [] },
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

const recentUsageRest = {
  contract: 'team_board_recent_usage_rest_v1',
  status: 'complete',
  reason_code: null,
  data_through: identity.represented_date,
  reference_date: identity.availability_reference_date,
  window_policy: 'calendar_day_inclusive_through_date_v1',
  population_basis: 'official_appearance_team_relief_appearances_and_frozen_active_bullpen',
  thresholds: { high_pitch_outing_minimum_pitches: 25 },
  active_pitchers: [{
    pitcher_id: 7,
    pitcher_name: 'Exact Source Name',
    roster_state: 'active',
    windows: {
      yesterday: { window_days: 1, start_date: '2026-08-16', through_date: '2026-08-16', appearances: { value: 1, status: 'complete', reason_codes: [] }, pitches: { value: 25, status: 'complete', reason_codes: [] }, outs: { value: 3, status: 'complete', reason_codes: [] } },
      last_3_days: { window_days: 3, start_date: '2026-08-14', through_date: '2026-08-16', appearances: { value: 2, status: 'complete', reason_codes: [] }, pitches: { value: 40, status: 'complete', reason_codes: [] }, outs: { value: 6, status: 'complete', reason_codes: [] } },
      last_7_days: { window_days: 7, start_date: '2026-08-10', through_date: '2026-08-16', appearances: { value: 3, status: 'complete', reason_codes: [] }, pitches: { value: 58, status: 'complete', reason_codes: [] }, outs: { value: 10, status: 'complete', reason_codes: [] } },
    },
    days_since_last_appearance: { value: 1, status: 'complete', reason_codes: [] },
    pitched_yesterday: { value: true, status: 'complete', reason_codes: [] },
    back_to_back: { value: true, status: 'complete', reason_codes: [] },
    three_in_four: { value: false, status: 'complete', reason_codes: [] },
    four_in_six: { value: false, status: 'complete', reason_codes: [] },
    recent_multi_inning: { value: true, status: 'complete', reason_codes: [], threshold: 4 },
    high_pitch_outing: { value: true, status: 'complete', reason_codes: [], threshold: 25 },
  }],
  off_active_historical_contributors: [],
}

const detailsPayload = {
  capability: TEAM_BOARD_DETAILS_CAPABILITY,
  contract_version: TEAM_BOARD_DETAILS_CONTRACT_VERSION,
  publication_identity: identity,
  represented_date: payload.represented_date,
  recent_usage: payload.recent_usage,
  recent_usage_rest: recentUsageRest,
  recently_used_arms: payload.recently_used_arms,
  workload_overview: payload.workload_overview,
  roles_deployment: payload.roles_deployment,
  recent_transactions: payload.recent_transactions,
  recent_relief_work: payload.recent_relief_work,
  game_context: payload.game_context,
  performance: {
    capability: 'public_team_performance', contract_version: 'public_team_performance_v1', status: 'available',
    through: identity.represented_date,
    window: { policy: 'current_mlb_regular_season_through_represented_date', through: identity.represented_date },
    sample: { recorded_outs: 126, innings_pitched: '42.0' },
    population_basis: 'represented_default_visible_active_bullpen',
    metrics: [
      { key: 'active_bullpen_era', metric_id: 'M-001', value: '3.42', evidence_state: { status: 'complete' }, qualification: { status: 'qualified' } },
      { key: 'active_bullpen_whip', metric_id: 'M-002', value: '1.18', evidence_state: { status: 'complete' }, qualification: { status: 'qualified' } },
    ],
    capabilities: {
      k_bb_percent: { status: 'unavailable', value: null },
      home_runs_allowed: { status: 'unavailable', value: null },
      inherited_runner_context: { status: 'unavailable', value: null },
    },
  },
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
  assert.equal(view.recentTransactions, null)
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
  assert.equal(attached.recentUsageRest.activePitchers[0].windows[0].label, 'Yesterday')
  assert.equal(attached.recentUsageRest.activePitchers[0].highPitchOuting.value, true)

  const mismatched = readTeamBoardDelivery(corePayload, {
    ...detailsPayload,
    publication_identity: { ...identity, snapshot_id: 1901 },
  })
  assert.equal(mismatched.detailsAttached, false)
  assert.equal(mismatched.detailsRejected, true)
  assert.equal(mismatched.performance, null)
  assert.equal(mismatched.whatChanged, null)
  assert.equal(mismatched.recentUsageRest, null)
  assert.equal(mismatched.teamState, payload.team_state)
})

test('TB-08 attaches only frozen roster movement for the exact core, team and active group', () => {
  const attached = readTeamBoardDelivery(corePayload, detailsPayload)
  assert.equal(attached.recentTransactions.events[0].label, 'Recalled')
  assert.equal(attached.recentTransactions.currentGroup.activeCount, 1)
  assert.equal(attached.frozenRosterTransactionsRejected, false)
  assert.equal(attached.teamState, corePayload.team_state)

  for (const altered of [
    { team_id: 2 }, { data_through: '2026-08-15' },
    { current_group: { ...payload.recent_transactions.current_group, active_pitcher_ids: [8] } },
    { events: [{ ...payload.recent_transactions.events[0], date: '2026-08-17' }] },
  ]) {
    const wrong = readTeamBoardDelivery(corePayload, {
      ...detailsPayload,
      recent_transactions: { ...payload.recent_transactions, ...altered },
    })
    assert.equal(wrong.recentTransactions, null)
    assert.equal(wrong.frozenRosterTransactionsRejected, true)
    assert.equal(wrong.frozenPerformance, attached.frozenPerformance)
    assert.equal(wrong.teamState, corePayload.team_state)
  }
  const priorSnapshot = readTeamBoardDelivery(corePayload, {
    ...detailsPayload, publication_identity: { ...identity, snapshot_id: 1901 },
  })
  assert.equal(priorSnapshot.recentTransactions, null)
  assert.equal(priorSnapshot.detailsRejected, true)
  const switchedTeam = readTeamBoardDelivery({
    ...corePayload, publication_identity: { ...identity, team_id: 2 },
  }, detailsPayload)
  assert.equal(switchedTeam.recentTransactions, null)
  assert.equal(switchedTeam.detailsRejected, true)
  assert.equal(readTeamBoardFrozenRosterTransactions(payload.recent_transactions, null), null)
})

test('TB-06 attaches only the frozen represented-date performance read', () => {
  const attached = readTeamBoardDelivery(corePayload, detailsPayload)
  assert.equal(attached.frozenPerformance, detailsPayload.performance)
  assert.equal(attached.frozenPerformanceRejected, false)
  assert.equal(attached.teamState, corePayload.team_state)

  const stale = readTeamBoardDelivery(corePayload, {
    ...detailsPayload,
    performance: { ...detailsPayload.performance, through: '2026-08-15' },
  })
  assert.equal(stale.frozenPerformance, null)
  assert.equal(stale.frozenPerformanceRejected, true)
  assert.equal(stale.frozenPublicDeployment, attached.frozenPublicDeployment)
  assert.equal(stale.teamState, corePayload.team_state)

  const priorTeam = readTeamBoardDelivery({
    ...corePayload,
    publication_identity: { ...identity, team_id: 2 },
  }, detailsPayload)
  assert.equal(priorTeam.frozenPerformance, null)
  assert.equal(priorTeam.detailsRejected, true)
  assert.equal(priorTeam.teamState, corePayload.team_state)
})

test('TB-07 recent starts attach only to exact trusted team and snapshot', () => {
  const carrier = {
    contract: 'team_board_recent_rotation_games_v1',
    team_id: identity.team_id,
    data_through: identity.represented_date,
    window_start: '2026-08-10', window_days: 7,
    status: 'partial', reason_codes: ['split_row_missing'],
    games_in_window: 2, games_excluded: 1,
    games_analyzed: 1, starter_innings: '4.2', bullpen_innings: '4.1',
    short_start_count: 1,
    summary: 'Backend-authored represented-date rotation summary.',
    starts: [{
      mlb_game_pk: 55, game_date: '2026-08-15',
      starter_pitcher_id: 18, starter_name: 'Source Starter',
      starter_outs: 14, starter_innings: '4.2',
      starter_evidence: { status: 'complete', reason_codes: [] },
      bullpen_outs: 13, bullpen_innings: '4.1',
      bullpen_evidence: { status: 'complete', reason_codes: [] },
      short_start: true, short_start_evidence: { status: 'complete', reason_codes: [] },
      status: 'complete', reason_codes: [],
    }],
  }
  const details = { ...detailsPayload, rotation_impact: { frozen_recent_games: carrier } }
  const attached = readTeamBoardDelivery(corePayload, details)
  assert.equal(attached.frozenRotationGames.starts[0].starterName, 'Source Starter')
  assert.equal(attached.frozenRotationGames.starts[0].shortStart, true)
  assert.equal(attached.frozenRotationGames.gamesExcluded, 1)
  assert.equal(attached.frozenRotationGamesRejected, false)

  const wrongDate = readTeamBoardDelivery(corePayload, {
    ...details, rotation_impact: { frozen_recent_games: { ...carrier, data_through: '2026-08-15' } },
  })
  assert.equal(wrongDate.frozenRotationGames, null)
  assert.equal(wrongDate.frozenRotationGamesRejected, true)
  assert.equal(wrongDate.frozenPerformance, attached.frozenPerformance)

  const wrongSnapshot = readTeamBoardDelivery(corePayload, {
    ...details, publication_identity: { ...identity, snapshot_id: 1901 },
  })
  assert.equal(wrongSnapshot.detailsRejected, true)
  assert.equal(wrongSnapshot.frozenRotationGames, null)
  assert.equal(wrongSnapshot.teamState, corePayload.team_state)

  const switched = readTeamBoardDelivery({
    ...corePayload, publication_identity: { ...identity, team_id: 2 },
  }, details)
  assert.equal(switched.frozenRotationGames, null)
  assert.equal(switched.detailsRejected, true)
  assert.equal(readTeamBoardFrozenRotationGames({ ...carrier, starts: [{ ...carrier.starts[0], short_start: null }] }, identity), null)
  assert.equal(readTeamBoardFrozenRotationGames({ ...carrier, starts: [{ ...carrier.starts[0], starter_innings: '4.7' }] }, identity), null)
  const partialStart = readTeamBoardFrozenRotationGames({
    ...carrier,
    starts: [{
      ...carrier.starts[0], status: 'partial',
      starter_outs: null, starter_innings: null,
      starter_evidence: { status: 'partial', reason_codes: ['starter_outs_missing'] },
      short_start: null,
      short_start_evidence: { status: 'unknown', reason_codes: ['starter_outs_missing'] },
    }],
  }, identity)
  assert.equal(partialStart.starts[0].starterInnings, null)
  assert.equal(partialStart.starts[0].bullpenInnings, '4.1')
  assert.equal(partialStart.starts[0].shortStart, null)
})

test('TB-06 rejects fabricated deferred metrics and never changes certified zero', () => {
  assert.equal(readTeamBoardFrozenPerformance({
    ...detailsPayload.performance,
    capabilities: { ...detailsPayload.performance.capabilities, home_runs_allowed: { status: 'unavailable', value: 0 } },
  }, identity), null)
  assert.equal(readTeamBoardFrozenPerformance({
    ...detailsPayload.performance,
    metrics: detailsPayload.performance.metrics.map((metric, index) => index === 0
      ? { ...metric, value: '0.00' } : metric),
  }, identity).metrics[0].value, '0.00')
})


test('recent usage carrier dates must match the exact core identity', () => {
  const valid = readTeamBoardRecentUsageRest(recentUsageRest, identity)
  assert.equal(valid.dataThrough, identity.represented_date)
  assert.equal(valid.referenceDate, identity.availability_reference_date)
  assert.equal(valid.activePitchers[0].windows[1].appearances.value, 2)

  const staleCarrier = readTeamBoardDelivery(corePayload, {
    ...detailsPayload,
    recent_usage_rest: { ...recentUsageRest, data_through: '2026-08-15' },
  })
  assert.equal(staleCarrier.detailsAttached, true)
  assert.equal(staleCarrier.recentUsageRest, null)
  assert.equal(staleCarrier.recentUsageRestRejected, true)
  assert.equal(staleCarrier.teamState, payload.team_state)
  assert.equal(staleCarrier.activeBullpen, payload.active_bullpen)
})

test('frozen TB-04 carrier attaches only to matching trusted details identity', () => {
  const carrier = frozenTeamWorkloadFixture(identity.represented_date)
  const details = { ...detailsPayload, workload_overview: { ...detailsPayload.workload_overview, frozen_team_workload: carrier } }
  const attached = readTeamBoardDelivery(corePayload, details)
  assert.equal(attached.frozenTeamWorkload.windows.length, 4)
  assert.equal(attached.frozenTeamWorkload.windows[0].pitches.value, 0)
  assert.equal(attached.frozenTeamWorkload.concentration.topThreeShare, carrier.concentration_7_day.top_3_share)
  assert.deepEqual(attached.frozenTeamWorkload.concentration.topThree.map(item => item.pitcherId), [101, 102, 103])
  assert.equal(attached.frozenTeamWorkload.concentration.offActiveContribution.pitches, 18)
  assert.equal(attached.frozenTeamWorkloadRejected, false)

  const staleDetails = readTeamBoardDelivery(corePayload, { ...details, publication_identity: { ...identity, snapshot_id: identity.snapshot_id + 1 } })
  assert.equal(staleDetails.frozenTeamWorkload, null)
  assert.equal(staleDetails.detailsRejected, true)
  assert.equal(staleDetails.teamState, payload.team_state)
  assert.equal(staleDetails.activeBullpen, payload.active_bullpen)

  const staleCarrier = readTeamBoardDelivery(corePayload, { ...details, workload_overview: { frozen_team_workload: { ...carrier, data_through: '2026-09-01' } } })
  assert.equal(staleCarrier.detailsAttached, true)
  assert.equal(staleCarrier.frozenTeamWorkload, null)
  assert.equal(staleCarrier.frozenTeamWorkloadRejected, true)
  assert.ok(staleCarrier.recentUsageRest)
  assert.equal(readTeamBoardFrozenWorkload(carrier, { ...identity, publication_authority_contract: 'other' }), null)
})

test('team switching cannot carry prior team workload into the new core', () => {
  const carrier = frozenTeamWorkloadFixture(identity.represented_date)
  const oldDetails = { ...detailsPayload, workload_overview: { frozen_team_workload: carrier } }
  const newCore = { ...corePayload, publication_identity: { ...identity, team_id: 2, team_abbreviation: 'NX' } }
  const switched = readTeamBoardDelivery(newCore, oldDetails)
  assert.equal(switched.frozenTeamWorkload, null)
  assert.equal(switched.detailsRejected, true)
  assert.equal(switched.teamState, payload.team_state)
})

test('TB-05 frozen deployment attaches only to exact trusted details identity', () => {
  const carrier = frozenPublicDeploymentFixture({ teamId: identity.team_id, dataThrough: identity.represented_date })
  const details = { ...detailsPayload, roles_deployment: { ...detailsPayload.roles_deployment, frozen_public_deployment: carrier } }
  const attached = readTeamBoardDelivery(corePayload, details)
  assert.equal(attached.frozenPublicDeployment.profiles[0].role.label, 'Trusted Arm')
  assert.equal(attached.frozenPublicDeployment.profiles[0].leverage.high, 2)
  assert.equal(attached.frozenPublicDeployment.profiles[0].entry.byInning[2].inning, 9)
  assert.equal(attached.frozenPublicDeploymentRejected, false)

  const mismatched = readTeamBoardDelivery(corePayload, { ...details, publication_identity: { ...identity, snapshot_id: identity.snapshot_id + 1 } })
  assert.equal(mismatched.frozenPublicDeployment, null)
  assert.equal(mismatched.detailsRejected, true)
  assert.equal(mismatched.teamState, payload.team_state)
  assert.equal(mismatched.activeBullpen, payload.active_bullpen)
  const switched = readTeamBoardDelivery({ ...corePayload, publication_identity: { ...identity, team_id: identity.team_id + 1 } }, details)
  assert.equal(switched.frozenPublicDeployment, null)
  assert.equal(switched.detailsRejected, true)
  const staleCarrier = readTeamBoardDelivery(corePayload, { ...details, roles_deployment: { frozen_public_deployment: { ...carrier, data_through: '2026-09-01' } } })
  assert.equal(staleCarrier.frozenPublicDeployment, null)
  assert.equal(staleCarrier.frozenPublicDeploymentRejected, true)
  assert.equal(readTeamBoardFrozenDeployment(carrier, { ...identity, publication_authority_contract: 'other' }), null)
})

test('TB-05 adapter preserves unknown leverage and backend role without inference', () => {
  const carrier = frozenPublicDeploymentFixture({ teamId: identity.team_id, dataThrough: identity.represented_date })
  const profile = carrier.profiles[0]
  profile.public_role_read = { key: 'limited_read', label: 'Role Unclear', confidence: 'low' }
  profile.context.leverage = { ...profile.context.leverage, status: 'unknown', known_appearances: 0, high: 0, middle: 0, low: 0 }
  profile.context.entry_inning = { ...profile.context.entry_inning, status: 'partial', known_appearances: 3 }
  const adapted = readTeamBoardFrozenDeployment(carrier, identity)
  assert.equal(adapted.profiles[0].role.label, 'Role Unclear')
  assert.equal(adapted.profiles[0].leverage.status, 'unknown')
  assert.equal(adapted.profiles[0].observed.saves, 2)
  assert.equal(adapted.profiles[0].entry.status, 'partial')
  assert.equal(Object.hasOwn(adapted.profiles[0], 'roleMovement'), false)
})


test('details retained from a prior team cannot attach after team switching', () => {
  const nextIdentity = { ...identity, team_id: 2, team_abbreviation: 'NX' }
  const nextCore = {
    ...corePayload,
    team: { team_id: 2, team_name: 'Next Club', team_abbreviation: 'NX' },
    publication_identity: nextIdentity,
  }
  const switched = readTeamBoardDelivery(nextCore, detailsPayload)

  assert.equal(getTeamBoardDetailsIdentity(nextCore, 2), nextIdentity)
  assert.equal(switched.detailsAttached, false)
  assert.equal(switched.detailsRejected, true)
  assert.equal(switched.recentUsageRest, null)
  assert.equal(switched.team.team_id, 2)
})


test('deferred requests require a core identity for the currently selected team', () => {
  assert.equal(getTeamBoardDetailsIdentity(corePayload, 1), identity)
  assert.equal(getTeamBoardDetailsIdentity(corePayload, 2), null)
  assert.equal(getTeamBoardDetailsIdentity({ ...corePayload, publication_identity: null }, 1), null)
  assert.equal(getTeamBoardDetailsIdentity(corePayload, null), null)
})


test('the deferred request key covers every exact publication identity field', () => {
  const baseline = teamBoardIdentityKey(identity)
  assert.ok(baseline)
  for (const field of Object.keys(identity)) {
    assert.notEqual(
      teamBoardIdentityKey({ ...identity, [field]: `${identity[field]}-changed` }),
      baseline,
      field,
    )
  }
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

  assert.equal(boardSource.includes('getTeamBoardCore(selectedTeam, options)'), true)
  assert.equal(boardSource.includes('getTeamBoardDetails(selectedTeam, coreIdentity, options)'), true)
  assert.equal(boardSource.includes('getTeamBoardDetailsIdentity(teamBoardV2State.data, selectedTeam)'), true)
  assert.equal(boardSource.includes('teamBoardIdentityKey(coreIdentity)'), true)
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
    /getTeamBoardCore = \(teamId, options = \{\}\) => request\(`\/bullpen\/teams\/\$\{encodeURIComponent\(teamId\)\}\/board-v2\/core`/,
  )
  for (const forbidden of ['reduce(', '/ 3', 'Math.round', 'public_state =', 'summary =']) {
    assert.equal(adapterSource.includes(forbidden), false, forbidden)
  }
})
