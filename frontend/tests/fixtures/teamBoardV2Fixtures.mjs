export function teamBoardV2Fixture(board, overrides = {}) {
  const representedDate = board?.team_state?.data_through
    || board?.freshness?.data_through
    || null
  const teamStateStatus = board?.team_state?.available === true ? 'available' : 'unavailable'
  const activeStatus = (
    board?.freshness?.fail_closed === true
    || board?.freshness?.is_current === false
    || board?.total_pitchers == null
    || (Array.isArray(board?.limitations) && board.limitations.length > 0)
  )
    ? 'partial'
    : 'available'

  return {
    capability: 'team_board_v2',
    contract_version: 'team-board-2.0.0',
    team: board?.team || {},
    represented_date: representedDate,
    generated_at: board?.generated_at || null,
    freshness: board?.freshness || {},
    team_state: board?.team_state || {},
    summary: board?.team_state?.summary ?? null,
    active_bullpen: {
      population_basis: 'current_scored_bullpen_eligible_pitchers',
      arm_count: board?.total_pitchers ?? null,
      arms: [],
    },
    rest_status: board?.rest_status || {},
    rotation_impact: { population_basis: 'stored_team_game_pitching_splits', read: board?.rotation_support_pressure || {} },
    roster_context: board?.roster_authority || {},
    recent_relief_work: { population_basis: 'official_appearance_team_relief_appearances', read: null },
    game_context: null,
    section_status: {
      team_state: {
        status: teamStateStatus,
        reason_code: board?.team_state?.reason_code || null,
        limitations: board?.team_state?.unavailable_message ? [board.team_state.unavailable_message] : [],
        represented_date: representedDate,
      },
      active_bullpen: {
        status: activeStatus,
        reason_code: activeStatus === 'partial' ? 'current_population_counts_withheld' : null,
        limitations: board?.limitations || [],
        represented_date: representedDate,
      },
    },
    limitations: board?.limitations || [],
    ...overrides,
  }
}
