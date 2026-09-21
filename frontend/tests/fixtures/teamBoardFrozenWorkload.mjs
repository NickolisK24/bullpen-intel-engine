const fact = (value, status = 'complete', reason_codes = []) => ({ value, status, reason_codes })

export function frozenTeamWorkloadFixture(dataThrough = '2026-09-02', pitcherName = 'Fixture Reliever') {
  const window = (start, pitches, appearances, outs) => ({
    start, through: dataThrough,
    pitches: fact(pitches), appearances: fact(appearances), outs: fact(outs),
  })
  const active = { pitcher_id: 101, name: pitcherName, pitches: 40, appearances: 3, outs: 7, current_active: true }
  const offActive = { pitcher_id: 102, name: 'Former Reliever', pitches: 18, appearances: 2, outs: 4, current_active: false }
  const third = { pitcher_id: 103, name: 'Third Reliever', pitches: 12, appearances: 1, outs: 3, current_active: true }
  return {
    contract: 'team_board_workload_overview_v1',
    data_through: dataThrough,
    window_policy: 'calendar_day_inclusive_through_date_v1',
    population_basis: 'official_appearance_team_relief_appearances',
    windows: {
      window_3: window('2026-08-31', 0, 0, 0),
      window_7: window('2026-08-27', 88, 8, 22),
      window_14: window('2026-08-20', 220, 17, 49),
      window_30: window('2026-08-04', 430, 34, 102),
    },
    concentration_7_day: {
      status: 'complete', reason_codes: [], total_pitches: 88,
      top_3_share: 70 / 88, pitcher_count: 5,
      contributors: [active, offActive, third,
        { pitcher_id: 104, name: 'Fourth Reliever', pitches: 10, appearances: 1, outs: 4, current_active: true },
        { pitcher_id: 105, name: 'Fifth Reliever', pitches: 8, appearances: 1, outs: 4, current_active: true }],
      top_contributor: active, top_3_contributors: [active, offActive, third],
      active_current_contribution: { pitches: 70, appearances: 6, outs: 18 },
      off_active_contribution: { pitches: 18, appearances: 2, outs: 4 },
    },
    trend_status: 'unavailable',
  }
}
