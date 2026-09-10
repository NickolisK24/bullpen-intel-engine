export const TEAM_BOARD_V2_CAPABILITY = 'team_board_v2'
export const TEAM_BOARD_V2_CONTRACT_VERSION = 'team-board-2.0.0'
export const TEAM_BOARD_CORE_CAPABILITY = 'team_board_answer_core'
export const TEAM_BOARD_CORE_CONTRACT_VERSION = 'team_board_answer_core_v1'
export const TEAM_BOARD_DETAILS_CAPABILITY = 'team_board_deferred_details'
export const TEAM_BOARD_DETAILS_CONTRACT_VERSION = 'team_board_deferred_details_v1'

const identityFields = [
  'contract', 'team_id', 'team_abbreviation', 'snapshot_id', 'sync_run_id',
  'represented_date', 'availability_reference_date', 'published_at',
  'snapshot_generated_at', 'dashboard_payload_version',
  'publication_authority_contract', 'team_board_package_contract',
  'team_board_contract_version', 'team_state_contract',
  'bullpen_membership_method_version', 'rest_status_method_version',
  'workload_windows_method_version', 'deployment_profile_method_version',
  'rotation_impact_method_version',
]

export function teamBoardIdentitiesMatch(left, right) {
  if (!left || !right) return false
  return identityFields.every(field => left[field] === right[field])
}

export function isTeamBoardV2Payload(payload) {
  return Boolean(
    payload
    && typeof payload === 'object'
    && !Array.isArray(payload)
    && payload.capability === TEAM_BOARD_V2_CAPABILITY
    && payload.contract_version === TEAM_BOARD_V2_CONTRACT_VERSION
    && payload.team_state
    && typeof payload.team_state === 'object'
    && payload.active_bullpen
    && Array.isArray(payload.active_bullpen.arms)
    && payload.section_status
    && typeof payload.section_status === 'object'
  )
}

export function readTeamBoardV2(payload) {
  if (!isTeamBoardV2Payload(payload)) return null

  return {
    capability: payload.capability,
    contractVersion: payload.contract_version,
    publicationIdentity: payload.publication_identity,
    team: payload.team,
    representedDate: payload.represented_date,
    freshness: payload.freshness,
    teamState: payload.team_state,
    summary: payload.summary,
    activeBullpen: payload.active_bullpen,
    recentUsage: payload.recent_usage,
    recentlyUsedArms: payload.recently_used_arms,
    offActiveCount: payload.off_active_count,
    restStatus: payload.rest_status,
    workloadOverview: payload.workload_overview,
    rolesDeployment: payload.roles_deployment,
    rotationImpact: payload.rotation_impact,
    recentTransactions: payload.recent_transactions,
    rosterContext: payload.roster_context,
    recentReliefWork: payload.recent_relief_work,
    gameContext: payload.game_context,
    performance: payload.performance,
    whatChanged: payload.what_changed,
    operatingState: payload.operating_state,
    sectionStatus: payload.section_status,
    limitations: payload.limitations,
  }
}

export function isTeamBoardCorePayload(payload) {
  return Boolean(
    payload
    && payload.capability === TEAM_BOARD_CORE_CAPABILITY
    && payload.contract_version === TEAM_BOARD_CORE_CONTRACT_VERSION
    && payload.publication_identity
    && payload.team_state
    && Array.isArray(payload.active_bullpen?.arms)
  )
}

export function isTeamBoardDetailsPayload(payload) {
  return Boolean(
    payload
    && payload.capability === TEAM_BOARD_DETAILS_CAPABILITY
    && payload.contract_version === TEAM_BOARD_DETAILS_CONTRACT_VERSION
    && payload.publication_identity
    && payload.section_status
  )
}

export function readTeamBoardDelivery(corePayload, detailsPayload = null) {
  if (!isTeamBoardCorePayload(corePayload)) return null
  const detailsValid = isTeamBoardDetailsPayload(detailsPayload)
    && teamBoardIdentitiesMatch(
      corePayload.publication_identity,
      detailsPayload.publication_identity,
    )
  const details = detailsValid ? detailsPayload : {}
  return {
    capability: corePayload.capability,
    contractVersion: corePayload.contract_version,
    publicationIdentity: corePayload.publication_identity,
    team: corePayload.team,
    representedDate: corePayload.represented_date,
    freshness: corePayload.freshness,
    teamState: corePayload.team_state,
    summary: corePayload.summary,
    activeBullpen: corePayload.active_bullpen,
    recentUsage: details.recent_usage || null,
    recentlyUsedArms: details.recently_used_arms || null,
    offActiveCount: corePayload.off_active_count,
    restStatus: corePayload.rest_status,
    workloadOverview: details.workload_overview || corePayload.workload_overview,
    rolesDeployment: details.roles_deployment || corePayload.roles_deployment,
    rotationImpact: corePayload.rotation_impact,
    recentTransactions: details.recent_transactions || null,
    rosterContext: corePayload.roster_context,
    recentReliefWork: details.recent_relief_work || null,
    gameContext: details.game_context || null,
    performance: details.performance || null,
    whatChanged: details.what_changed || null,
    operatingState: corePayload.operating_state,
    sectionStatus: {
      ...(corePayload.section_status || {}),
      ...(detailsValid ? detailsPayload.section_status : {}),
    },
    detailsAttached: detailsValid,
    detailsRejected: Boolean(detailsPayload) && !detailsValid,
    limitations: corePayload.limitations,
  }
}
