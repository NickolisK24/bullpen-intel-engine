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
  const activeArms = (board?.groups || []).flatMap(group => (group?.pitchers || []))
    .filter(card => card?.visibility?.is_visible_by_default !== false)
    .map(card => ({
      pitcher_id: card?.pitcher_id ?? null,
      name: card?.name ?? null,
      public_role_read: card?.public_role_read ?? null,
      public_labels: card?.pitcher_labels ?? null,
      availability: {
        status: card?.availability_status ?? null,
        label: card?.availability_public_label ?? null,
        confidence: card?.confidence ?? null,
        data_state: card?.data_state ?? null,
        short_reason: card?.short_reason ?? null,
        reasons: card?.reasons || [],
        limitations: card?.limitations || [],
      },
      last_appearance: card?.last_appearance ?? null,
      workload: card?.workload_facts ?? {},
      roster_status: card?.roster_status ?? null,
      visibility: card?.visibility ?? null,
    }))

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
      arms: activeArms,
    },
    rest_status: board?.rest_status || {},
    recent_usage: {
      population_basis: 'official_recent_team_relief_appearance_rows',
      appearances: [],
      represented_date: representedDate,
      limitations: [],
    },
    workload_overview: {
      population_basis: 'official_team_relief_appearances_and_current_bullpen_eligible_pitchers',
      window_population_basis: 'official_appearance_team_relief_appearances',
      windows: [],
      concentration: board?.team_shape?.workloadConcentration
          ? {
            population_basis: 'current_bullpen_eligible_pitchers_recent_relief_pitch_workload',
            label: board.team_shape.workloadConcentration.label ?? null,
            summary: board.team_shape.workloadConcentration.summary ?? null,
          }
        : null,
      represented_date: representedDate,
      limitations: [],
    },
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
      recent_usage: {
        status: 'available',
        reason_code: null,
        limitations: [],
        represented_date: representedDate,
      },
      rest_status: {
        status: board?.rest_status?.available === true ? 'available' : 'unavailable',
        reason_code: board?.rest_status?.reason_code || null,
        limitations: [],
        represented_date: representedDate,
      },
      workload_overview: {
        status: board?.team_shape?.workloadConcentration ? 'available' : 'unavailable',
        reason_code: board?.team_shape?.workloadConcentration ? null : 'workload_overview_unavailable',
        limitations: [],
        represented_date: representedDate,
      },
    },
    limitations: board?.limitations || [],
    ...overrides,
  }
}
