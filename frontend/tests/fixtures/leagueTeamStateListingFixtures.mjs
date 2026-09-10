const CLUB_NAMES = [
  ['ARI', 'Arizona Diamondbacks'], ['ATH', 'Athletics'], ['ATL', 'Atlanta Braves'],
  ['BAL', 'Baltimore Orioles'], ['BOS', 'Boston Red Sox'], ['CHC', 'Chicago Cubs'],
  ['CWS', 'Chicago White Sox'], ['CIN', 'Cincinnati Reds'], ['CLE', 'Cleveland Guardians'],
  ['COL', 'Colorado Rockies'], ['DET', 'Detroit Tigers'], ['HOU', 'Houston Astros'],
  ['KC', 'Kansas City Royals'], ['LAA', 'Los Angeles Angels'], ['LAD', 'Los Angeles Dodgers'],
  ['MIA', 'Miami Marlins'], ['MIL', 'Milwaukee Brewers'], ['MIN', 'Minnesota Twins'],
  ['NYM', 'New York Mets'], ['NYY', 'New York Yankees'], ['PHI', 'Philadelphia Phillies'],
  ['PIT', 'Pittsburgh Pirates'], ['SD', 'San Diego Padres'], ['SF', 'San Francisco Giants'],
  ['SEA', 'Seattle Mariners'], ['STL', 'St. Louis Cardinals'], ['TB', 'Tampa Bay Rays'],
  ['TEX', 'Texas Rangers'], ['TOR', 'Toronto Blue Jays'], ['WSH', 'Washington Nationals'],
]

const STATE_ROWS = [
  ['fresh', 'Fresh'],
  ['stretched', 'Stretched'],
  ['vulnerable', 'Vulnerable'],
]

export function makeLeagueTeamStateListing({ withheld = 0, status = 'ok', freshness = null } = {}) {
  const represented = status === 'snapshot_unavailable' ? 0 : 30 - withheld
  const teams = CLUB_NAMES.map(([team_abbreviation, team_name], index) => {
    const available = index < represented
    const [public_state, public_label] = STATE_ROWS[index % STATE_ROWS.length]
    return {
      team_id: 100 + index,
      team_abbreviation,
      team_name,
      team_state: available
        ? {
            available: true,
            public_state,
            public_label,
            data_through: '2026-08-14',
          }
        : {
            available: false,
            public_state: null,
            public_label: null,
            unavailable_message: 'A current published read is unavailable for this club.',
            data_through: status === 'snapshot_unavailable' ? null : '2026-08-14',
          },
    }
  })
  return {
    capability: 'league_team_state_listing_v1',
    version: '1.0.0',
    source: 'backend',
    generated_at: '2026-08-15T12:00:00Z',
    status,
    ranking_applied: false,
    selection_made: false,
    prediction_applied: false,
    ordering_basis: 'team_name_then_team_id',
    expected_team_count: 30,
    team_count: 30,
    represented_team_count: represented,
    withheld_team_count: 30 - represented,
    publication_authority: status === 'snapshot_unavailable' ? null : { snapshot_id: 7 },
    freshness: freshness || (status === 'snapshot_unavailable'
      ? { data_through: null, freshness_state: 'metadata_unavailable' }
      : { data_through: '2026-08-14', freshness_state: 'current', is_current: true }),
    teams,
  }
}
