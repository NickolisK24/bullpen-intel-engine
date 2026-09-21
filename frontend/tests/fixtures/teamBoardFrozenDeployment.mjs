export function frozenPublicDeploymentFixture({ teamId = 111, dataThrough = '2026-09-02', pitcherId = 101, pitcherName = 'Fixture Reliever' } = {}) {
  return {
    contract: 'team_board_public_deployment_context_v1',
    method_version: 'team_board_public_deployment_context_v1',
    team_id: teamId,
    data_through: dataThrough,
    window_days: 14,
    population_basis: 'official_appearance_team_relief_appearances',
    profiles: [{
      pitcher_id: pitcherId,
      pitcher_name: pitcherName,
      team_id: teamId,
      public_role_read: { key: 'trust_arm', label: 'Trusted Arm', confidence: 'high' },
      observed_profile: {
        pitcher_id: pitcherId,
        appearances_analyzed: 4,
        saves: 2,
        holds: 1,
        games_finished: 2,
        appearances_with_games_finished: 4,
        multi_inning_appearances: 1,
        appearances_with_outs: 4,
        limitations: [],
      },
      context: {
        pitcher_id: pitcherId,
        entry_inning: { status: 'complete', appearances: 4, known_appearances: 4, reason_codes: [], by_inning: [{ inning: 7, appearances: 1 }, { inning: 8, appearances: 1 }, { inning: 9, appearances: 2 }], eighth_or_later_appearances: 3, extra_inning_appearances: 0 },
        score_context: { status: 'complete', appearances: 4, known_appearances: 4, reason_codes: [], leading: 2, tied: 1, trailing: 1 },
        leverage: { status: 'complete', appearances: 4, known_appearances: 4, reason_codes: [], basis: 'recorded_game_log_leverage_index_only', high: 2, middle: 1, low: 1 },
      },
    }],
    role_movement: { status: 'unavailable', reason_code: 'not_published' },
  }
}
