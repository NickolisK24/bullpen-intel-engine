// Production-shaped tonight_v1 fixtures, mirroring
// backend/services/tonight_read_model.py and tonight_v1_serving.py.

const CLUBS = [
  [147, 'NYY', 'New York Yankees'], [111, 'BOS', 'Boston Red Sox'],
  [119, 'LAD', 'Los Angeles Dodgers'], [137, 'SF', 'San Francisco Giants'],
  [136, 'SEA', 'Seattle Mariners'], [117, 'HOU', 'Houston Astros'],
  [121, 'NYM', 'New York Mets'], [143, 'PHI', 'Philadelphia Phillies'],
  [144, 'ATL', 'Atlanta Braves'], [146, 'MIA', 'Miami Marlins'],
  [112, 'CHC', 'Chicago Cubs'], [158, 'MIL', 'Milwaukee Brewers'],
  [138, 'STL', 'St. Louis Cardinals'], [113, 'CIN', 'Cincinnati Reds'],
  [134, 'PIT', 'Pittsburgh Pirates'], [114, 'CLE', 'Cleveland Guardians'],
  [116, 'DET', 'Detroit Tigers'], [142, 'MIN', 'Minnesota Twins'],
  [145, 'CWS', 'Chicago White Sox'], [118, 'KC', 'Kansas City Royals'],
  [140, 'TEX', 'Texas Rangers'], [108, 'LAA', 'Los Angeles Angels'],
  [133, 'ATH', 'Athletics'], [135, 'SD', 'San Diego Padres'],
  [109, 'AZ', 'Arizona Diamondbacks'], [115, 'COL', 'Colorado Rockies'],
  [110, 'BAL', 'Baltimore Orioles'], [141, 'TOR', 'Toronto Blue Jays'],
  [139, 'TB', 'Tampa Bay Rays'], [120, 'WSH', 'Washington Nationals'],
]

const LABELS = { fresh: 'Fresh', stretched: 'Stretched', vulnerable: 'Vulnerable' }

export function teamSide(index, overrides = {}) {
  const [teamId, abbreviation, name] = CLUBS[index % CLUBS.length]
  const state = ['fresh', 'stretched', 'vulnerable'][index % 3]
  return {
    team_id: teamId,
    abbreviation,
    name,
    available: true,
    reason_code: null,
    team_state: {
      public_state: state,
      public_label: LABELS[state],
      available: true,
      reason_code: null,
    },
    rest: {
      active_arm_count: 8,
      rested_arm_count: 3 + (index % 4),
      worked_yesterday_count: index % 3,
      back_to_back_count: index % 4 === 1 ? 2 : 0,
      available: true,
      reason_code: null,
    },
    multi_day_usage: { three_in_four_count: index % 5 === 2 ? 1 : 0 },
    workload_7d: {
      appearances: 18, pitches: 410, outs: 66, status: 'complete', reason_codes: [],
    },
    key_arms: [
      {
        pitcher_id: 600000 + index * 10 + 1,
        name: `${abbreviation} Trust Arm`,
        role_key: 'trust_arm',
        role_label: 'Trust arm',
        days_since_last_appearance: 1,
        pattern: index % 4 === 1 ? 'B2B' : null,
      },
      {
        pitcher_id: 600000 + index * 10 + 2,
        name: `${abbreviation} Bridge Arm`,
        role_key: 'bridge_arm',
        role_label: 'Bridge arm',
        days_since_last_appearance: 2,
        pattern: index % 5 === 2 ? '3-in-4' : null,
      },
    ],
    rotation: index % 6 === 3
      ? { short_start_count: 1, bullpen_innings: '6.0', games_analyzed: 5, status: 'complete' }
      : null,
    change_refs: [],
    ...overrides,
  }
}

export function withheldSide(index, reasonCode = 'team_package_unavailable') {
  const [teamId, abbreviation, name] = CLUBS[index % CLUBS.length]
  return {
    team_id: teamId,
    abbreviation,
    name,
    available: false,
    reason_code: reasonCode,
    team_state: { public_state: null, public_label: null, available: false, reason_code: reasonCode },
    rest: {
      active_arm_count: null, rested_arm_count: null, worked_yesterday_count: null,
      back_to_back_count: null, available: false, reason_code: 'rest_unavailable',
    },
    multi_day_usage: { three_in_four_count: null },
    workload_7d: {
      appearances: null, pitches: null, outs: null, status: 'unavailable',
      reason_codes: ['workload_unavailable'],
    },
    key_arms: [],
    rotation: null,
    change_refs: [],
  }
}

export function gameCard(gamePk, away, home, overrides = {}) {
  return {
    game_pk: gamePk,
    game_number: 1,
    first_pitch_utc: '2026-09-26T23:05:00Z',
    state: 'scheduled',
    state_as_of: '2026-09-26T14:00:00Z',
    away,
    home,
    context: {
      sentence: `${away.abbreviation} has ${away.rest.rested_arm_count ?? 0} rested bullpen arms; ${home.abbreviation} has ${home.rest.rested_arm_count ?? 0}.`,
      reason_codes: ['rested_arm_snapshot'],
      evidence_state: 'complete',
    },
    featured: false,
    featured_reason_codes: [],
    links: {
      away_team_board: `/bullpen?view=board&team=${away.abbreviation}`,
      home_team_board: `/bullpen?view=board&team=${home.abbreviation}`,
      matchup: `/matchup/${gamePk}`,
    },
    ...overrides,
  }
}

function summaryFor(games, changes) {
  const byState = { scheduled: 0, live: 0, final: 0, postponed: 0, suspended: 0, uncertain: 0 }
  const teamStates = { fresh: 0, stretched: 0, vulnerable: 0, withheld: 0 }
  let b2b = 0
  for (const game of games) {
    byState[game.state] += 1
    for (const side of [game.away, game.home]) {
      const state = side.team_state.available ? side.team_state.public_state : 'withheld'
      teamStates[state] += 1
      if (side.rest.available && side.rest.back_to_back_count > 0) b2b += 1
    }
  }
  return {
    game_count: games.length,
    games_by_state: byState,
    team_state_counts: teamStates,
    clubs_with_back_to_back_arms: b2b,
    change_count: changes.length,
  }
}

export const leagueChanges = [
  {
    change_id: 'a1b2c3d4e5f6a7b8c9d0e1f2',
    team_id: 136,
    team_abbreviation: 'SEA',
    change_class: 'team_state_changed',
    headline: 'SEA moved from Stretched to Vulnerable.',
    detail: null,
    occurred_on: '2026-09-25',
    evidence_state: 'complete',
    source_ref: 'team_board_what_changed_v1:3601:3590:136',
    game_pks: [],
    state_change: { from: 'Stretched', to: 'Vulnerable' },
  },
  {
    change_id: 'f0e1d2c3b4a5968778695a4b',
    team_id: 147,
    team_abbreviation: 'NYY',
    change_class: 'active_bullpen_joined',
    headline: 'NYY Call-Up joined the active bullpen.',
    detail: 'Verified transaction: Recalled.',
    occurred_on: null,
    evidence_state: 'complete',
    source_ref: 'team_board_what_changed_v1:3601:3590:147#transaction:998877',
    game_pks: [],
    state_change: null,
  },
]

// Fifteen games in backend order (first pitch, game number, game_pk). Game 3
// is live and game 4 final so served state labels are exercised; featured
// order intentionally differs from slate order.
export function productionPayload() {
  const times = [
    '2026-09-26T17:05:00Z', '2026-09-26T17:10:00Z', '2026-09-26T20:05:00Z',
    '2026-09-26T20:10:00Z', '2026-09-26T22:40:00Z', '2026-09-26T23:05:00Z',
    '2026-09-26T23:05:00Z', '2026-09-26T23:10:00Z', '2026-09-26T23:15:00Z',
    '2026-09-26T23:40:00Z', '2026-09-27T00:10:00Z', '2026-09-27T00:40:00Z',
    '2026-09-27T01:38:00Z', '2026-09-27T02:05:00Z', '2026-09-27T02:10:00Z',
  ]
  const games = times.map((time, i) => {
    const away = teamSide(i * 2)
    const home = teamSide(i * 2 + 1)
    return gameCard(776000 + (i + 1) * 7 % 100, away, home, { first_pitch_utc: time })
  })
  games[2] = {
    ...games[2],
    state: 'live',
    context: { ...games[2].context, reason_codes: ['rested_arm_snapshot', 'pregame_context'] },
  }
  games[3] = {
    ...games[3],
    state: 'final',
    context: { sentence: null, reason_codes: ['pregame_context_hidden'], evidence_state: 'complete' },
  }
  const featuredPks = [games[6].game_pk, games[1].game_pk, games[10].game_pk]
  for (const game of games) {
    if (featuredPks.includes(game.game_pk)) {
      game.featured = true
      game.featured_reason_codes = ['vulnerable_team']
    }
  }
  return {
    contract: 'tonight_v1',
    edition: {
      baseball_date: '2026-09-26',
      data_through: '2026-09-25',
      availability_reference_date: '2026-09-26',
      generated_at: '2026-09-26T13:02:11Z',
      publication: {
        dashboard_snapshot_id: 3601,
        sync_run_id: 9120,
        team_board_package_contract: 'trusted_team_boards_v1',
      },
      schedule_as_of: '2026-09-26T13:00:00Z',
    },
    summary: summaryFor(games, leagueChanges),
    lead: {
      lead_type: 'team_state_to_vulnerable',
      headline: 'SEA moved into a Vulnerable bullpen state entering tonight.',
      detail: 'SEA is scheduled to face HOU.',
      team_ids: [136],
      game_pk: games[2].game_pk,
      change_refs: ['a1b2c3d4e5f6a7b8c9d0e1f2'],
      reason_codes: ['team_state_to_vulnerable'],
      evidence_state: 'complete',
    },
    featured_game_pks: featuredPks,
    games,
    league_changes: leagueChanges,
    quiet_day: false,
    limitations: [],
  }
}

export function quietPayload() {
  return {
    ...productionPayload(),
    summary: {
      game_count: 0,
      games_by_state: { scheduled: 0, live: 0, final: 0, postponed: 0, suspended: 0, uncertain: 0 },
      team_state_counts: { fresh: 0, stretched: 0, vulnerable: 0, withheld: 0 },
      clubs_with_back_to_back_arms: 0,
      change_count: 0,
    },
    lead: null,
    featured_game_pks: [],
    games: [],
    league_changes: [],
    quiet_day: true,
  }
}

export function unavailablePayload({ withPublication = true } = {}) {
  return {
    contract: 'tonight_v1',
    status: 'unavailable',
    reason: 'tonight_v1_unavailable',
    empty_reason: 'tonight_v1_unavailable',
    reason_codes: ['tonight_publication_row_missing'],
    edition: null,
    current_publication: withPublication
      ? {
        dashboard_snapshot_id: 3601,
        sync_run_id: 9120,
        data_through: '2026-09-25',
        availability_reference_date: '2026-09-26',
      }
      : null,
    summary: { game_count: 0 },
    lead: null,
    featured_game_pks: [],
    games: [],
    game_count: 0,
    league_changes: [],
    quiet_day: false,
    limitations: ['Tonight v1 publication row is missing.'],
  }
}

// TN-09 stress edition: 17 games, 4 featured, 12 changes, every game state,
// maximum-length lead/context/change copy, long names, withheld and
// rest-limited sides, double-digit counts and three key arms.
export const LONG_TEAM_NAME = 'Commonwealth Riverfront Metropolitans'
export const LONG_PLAYER_NAME = 'Maximiliano Bartholomew Santiago-Villanueva'
export const LONG_ROLE_LABEL = 'Late-inning trust arm in leverage'
export const MAX_LEAD_HEADLINE = 'CRM moved into a Vulnerable bullpen state entering tonight after a heavy week of relief work across two series.'.padEnd(120, '.')
export const MAX_LEAD_DETAIL = 'CRM is scheduled to face SEA in the second game of a split doubleheader at the home ballpark this evening tonight ok.'.padEnd(140, '.')
export const LONG_CONTEXT = 'CRM enters tonight with a Vulnerable bullpen state, while SEA is Stretched after absorbing a long relief night in the series opener yesterday.'
export const LONG_CHANGE_HEADLINE = `${LONG_PLAYER_NAME} joined the active bullpen after a verified transaction.`
export const LONG_CHANGE_DETAIL = 'Verified transaction: Recalled from Triple-A affiliate following a roster move to cover depleted relief innings.'

export function stressPayload() {
  const states = ['scheduled', 'scheduled', 'live', 'final', 'postponed', 'suspended', 'uncertain']
  const games = Array.from({ length: 17 }, (_, i) => {
    let away = teamSide(i * 2)
    let home = teamSide(i * 2 + 1)
    if (i === 0) {
      away = teamSide(0, {
        abbreviation: 'CRM',
        name: LONG_TEAM_NAME,
        team_state: { public_state: 'vulnerable', public_label: 'Vulnerable', available: true, reason_code: null },
        rest: { active_arm_count: 14, rested_arm_count: 12, worked_yesterday_count: 6, back_to_back_count: 11, available: true, reason_code: null },
        multi_day_usage: { three_in_four_count: 10 },
        key_arms: [
          { pitcher_id: 1, name: LONG_PLAYER_NAME, role_key: 'trust_arm', role_label: LONG_ROLE_LABEL, days_since_last_appearance: 0, pattern: 'B2B' },
          { pitcher_id: 2, name: 'Christopher Alexander Montgomery-Whitfield', role_key: 'trust_arm', role_label: 'Trust arm', days_since_last_appearance: 1, pattern: '3-in-4' },
          { pitcher_id: 3, name: 'Jonathan Fitzgerald Oyelaran', role_key: 'bridge_arm', role_label: 'Bridge arm', days_since_last_appearance: 2, pattern: null },
        ],
        rotation: { short_start_count: 12, bullpen_innings: '41.2', games_analyzed: 15, status: 'partial' },
      })
    }
    if (i === 1) home = withheldSide(3)
    if (i === 2) {
      home = teamSide(5)
      home.rest = { ...home.rest, rested_arm_count: 0 }
    }
    if (i === 5) {
      away = teamSide(10)
      away.rest = { ...away.rest, available: false, rested_arm_count: null, back_to_back_count: null, reason_code: 'rest_unavailable' }
      away.multi_day_usage = { three_in_four_count: null }
    }
    const pk = 777000 + i * 3
    const game = gameCard(pk, away, home, {
      first_pitch_utc: i === 7 ? null : `2026-09-26T${String(16 + Math.floor(i / 2)).padStart(2, '0')}:${i % 2 ? '40' : '05'}:00Z`,
      state: states[i % states.length],
    })
    if (i === 0) {
      game.context = { sentence: LONG_CONTEXT, reason_codes: ['team_state_vulnerable'], evidence_state: 'complete' }
    }
    if (game.state === 'live') {
      game.context = { ...game.context, reason_codes: [...game.context.reason_codes, 'pregame_context'] }
    }
    if (['final', 'postponed', 'suspended'].includes(game.state)) {
      game.context = { sentence: null, reason_codes: ['pregame_context_hidden'], evidence_state: 'complete' }
    }
    return game
  })
  const featuredPks = [games[0].game_pk, games[8].game_pk, games[1].game_pk, games[14].game_pk]
  for (const game of games) {
    if (featuredPks.includes(game.game_pk)) {
      game.featured = true
      game.featured_reason_codes = ['vulnerable_team']
    }
  }
  const changes = Array.from({ length: 12 }, (_, i) => {
    const side = i === 0 ? games[0].away : games[i].home
    return {
      change_id: `c${String(i).padStart(23, '0')}`,
      team_id: side.team_id,
      team_abbreviation: side.abbreviation,
      change_class: i === 0 ? 'active_bullpen_joined' : 'back_to_back_started',
      headline: i === 0 ? LONG_CHANGE_HEADLINE : `${side.abbreviation} Reliever ${i} started a back-to-back.`,
      detail: i === 0 ? LONG_CHANGE_DETAIL : null,
      occurred_on: i % 3 === 2 ? null : '2026-09-25',
      evidence_state: 'complete',
      source_ref: `team_board_what_changed_v1:3601:3590:${side.team_id}`,
      game_pks: [],
      state_change: null,
    }
  })
  const base = productionPayload()
  return {
    ...base,
    summary: { ...summaryFor(games, changes) },
    lead: {
      ...base.lead,
      headline: MAX_LEAD_HEADLINE,
      detail: MAX_LEAD_DETAIL,
      game_pk: games[0].game_pk,
      reason_codes: ['team_state_to_vulnerable'],
    },
    featured_game_pks: featuredPks,
    games,
    league_changes: changes,
  }
}

// TN-11.5 lifecycle fixtures. States are interleaved so bucket order can be
// checked against backend order. Context markers follow TN-03/TN-04 serving:
// live keeps its sentence with pregame_context; final/postponed/suspended hide
// it with pregame_context_hidden.
export const MIXED_LIFECYCLE_STATES = Object.freeze([
  'final', 'scheduled', 'live', 'final', 'uncertain', 'scheduled', 'suspended',
  'final', 'postponed', 'scheduled', 'final', 'live', 'scheduled', 'final',
  'scheduled', 'final', 'final',
])

function withServedState(game, state) {
  const hidden = ['final', 'postponed', 'suspended'].includes(state)
  const baseCodes = (game.context.reason_codes || []).filter(code => !code.startsWith('pregame_context'))
  const sentence = hidden ? null : (game.context.sentence || `${game.away.abbreviation} has rested bullpen arms; ${game.home.abbreviation} too.`)
  return {
    ...game,
    state,
    context: {
      ...game.context,
      sentence,
      reason_codes: hidden
        ? [...baseCodes, 'pregame_context_hidden']
        : state === 'live' ? [...baseCodes, 'pregame_context'] : baseCodes,
    },
  }
}

function lifecyclePayload(states) {
  const base = stressPayload()
  const games = base.games.map((game, index) => withServedState(game, states[index]))
  const byState = { scheduled: 0, live: 0, final: 0, postponed: 0, suspended: 0, uncertain: 0 }
  for (const game of games) byState[game.state] += 1
  const leadGame = games.find(game => game.game_pk === base.lead.game_pk)
  const leadServedPregame = leadGame && !['scheduled', 'uncertain'].includes(leadGame.state)
  return {
    ...base,
    summary: { ...base.summary, games_by_state: byState },
    lead: {
      ...base.lead,
      reason_codes: leadServedPregame ? [...base.lead.reason_codes, 'pregame_context'] : base.lead.reason_codes,
    },
    games,
  }
}

export function mixedLifecyclePayload() {
  return lifecyclePayload(MIXED_LIFECYCLE_STATES)
}

export function allFinalPayload() {
  return lifecyclePayload(Array(17).fill('final'))
}
