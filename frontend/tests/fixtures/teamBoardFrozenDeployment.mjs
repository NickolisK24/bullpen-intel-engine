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

function movementWindow({ start, through, appearances, phase = 'regular_season' }) {
  return {
    start_date: start,
    through_date: through,
    window_days: 7,
    appearances,
    season_phase: appearances ? phase : null,
    eighth_or_later_appearances: 0,
    known_entry_appearances: appearances,
    high_leverage_appearances: 0,
    known_leverage_appearances: appearances,
  }
}

// A governed observed_role_movement_v1 carrier as authored by the backend.
export function governedRoleMovementFixture({
  dataThrough = '2026-09-02',
  pitcherId = 101,
  status = 'complete',
  movement = 'later_or_higher_leverage',
  publicLabel = 'Recent deployment shifted toward later-inning, higher-leverage work.',
  reasonCode = null,
  recentAppearances = 3,
  priorAppearances = 3,
} = {}) {
  return {
    contract: 'observed_role_movement_v1',
    method_version: 'observed_role_movement_v1',
    status,
    reason_code: status === 'complete' ? null : 'insufficient_comparable_pitcher_evidence',
    population_basis: 'official_appearance_team_relief_appearances',
    game_types: ['D', 'F', 'L', 'R', 'W'],
    data_through: dataThrough,
    profiles: [{
      pitcher_id: pitcherId,
      contract: 'observed_role_movement_v1',
      method_version: 'observed_role_movement_v1',
      status,
      reason_code: reasonCode,
      movement,
      public_label: publicLabel,
      season_phase: status === 'complete' ? 'regular_season' : null,
      signals: [],
      recent_window: movementWindow({ start: '2026-08-27', through: dataThrough, appearances: recentAppearances }),
      prior_window: movementWindow({ start: '2026-08-20', through: '2026-08-26', appearances: priorAppearances }),
    }],
  }
}
