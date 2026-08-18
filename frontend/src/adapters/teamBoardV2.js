export const TEAM_BOARD_V2_CAPABILITY = 'team_board_v2'
export const TEAM_BOARD_V2_CONTRACT_VERSION = 'team-board-2.0.0'

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
    team: payload.team,
    representedDate: payload.represented_date,
    freshness: payload.freshness,
    teamState: payload.team_state,
    summary: payload.summary,
    activeBullpen: payload.active_bullpen,
    restStatus: payload.rest_status,
    rotationImpact: payload.rotation_impact,
    rosterContext: payload.roster_context,
    recentReliefWork: payload.recent_relief_work,
    gameContext: payload.game_context,
    sectionStatus: payload.section_status,
    limitations: payload.limitations,
  }
}
