// Fixtures mirroring GET /api/bullpen/teams/<id>/board, used to render the
// presentational BullpenBoardView without a backend.

const BOARD_GROUP_ORDER = ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable']

const GROUP_META = {
  Available: { label: 'Available Tonight', description: 'Workload signals are inside normal ranges.' },
  Monitor: { label: 'Monitor', description: 'Worth a look at recent workload before counting on these arms.' },
  Limited: { label: 'Limited', description: 'Recent workload suggests restricted use tonight.' },
  Avoid: { label: 'Avoid', description: 'Meaningful recent-use load on these arms.' },
  Unavailable: { label: 'Unavailable', description: "Should not be counted for tonight's planning." },
}

function card(pitcherId, name, status, overrides = {}) {
  return {
    pitcher_id: pitcherId,
    name,
    availability_status: status,
    fatigue_score: 25,
    confidence: 'high',
    short_reason: 'Fresh workload profile',
    data_state: 'fresh',
    reasons: [],
    limitations: ['No injury information available'],
    ...overrides,
  }
}

function buildGroups(cardsByStatus) {
  return BOARD_GROUP_ORDER.map(status => {
    const pitchers = cardsByStatus[status] || []
    return {
      status,
      label: GROUP_META[status].label,
      description: GROUP_META[status].description,
      count: pitchers.length,
      pitchers,
    }
  })
}

function contextFromGroups(groups, freshness) {
  // Lightweight stand-in mirroring the backend context shape for view tests.
  const get = status => groups.find(g => g.status === status)?.count || 0
  const available = get('Available')
  const monitor = get('Monitor')
  const limited = get('Limited')
  const avoid = get('Avoid')
  const unavailable = get('Unavailable')
  const total = available + monitor + limited + avoid + unavailable
  const restricted = avoid + unavailable
  const isCurrent = freshness ? freshness.is_current !== false : true

  let state = 'manageable'
  if (total === 0) state = 'no_data'
  else if (restricted / total >= 0.4 || available === 0) state = 'constrained'
  else if (monitor / total >= 0.4) state = 'monitoring'
  else if (restricted / total >= 0.2 || available / total < 0.4) state = 'elevated'

  const labels = {
    manageable: 'Bullpen workload appears manageable.',
    monitoring: 'Several relievers require monitoring.',
    elevated: 'Bullpen workload is elevated.',
    constrained: 'Availability is constrained tonight.',
    no_data: 'No bullpen availability to summarize tonight.',
  }
  const pct = (part) => (total ? Math.round((part / total) * 100) : 0)
  const reasons = total === 0
    ? ['No active relievers fall inside the current freshness window.']
    : [
      `${available} of ${total} relievers are Available Tonight.`,
      restricted === 0
        ? 'No relievers are marked Avoid or Unavailable.'
        : `${restricted} of ${total} relievers are Avoid or Unavailable.`,
      'Availability classifications are workload-based only.',
    ]
  const limitations = []
  let confidence = 'high'
  if (total === 0) confidence = 'none'
  else if (!isCurrent) {
    confidence = 'low'
    const note = 'Latest workload data is outside the active freshness window, so this snapshot may not reflect tonight.'
    reasons.push(note)
    limitations.push(note)
  }

  return {
    metrics: {
      total_relievers: total,
      available, monitor, limited, avoid, unavailable, restricted,
      pct_available: pct(available),
      pct_unavailable: pct(unavailable),
      pct_restricted: pct(restricted),
    },
    health: { state, label: labels[state], reasons },
    confidence,
    limitations,
  }
}

export function makeBoard({ team, cardsByStatus = {}, freshness, limitations = [], context, rosterStatus } = {}) {
  const groups = buildGroups(cardsByStatus)
  const totalPitchers = groups.reduce((sum, g) => sum + g.count, 0)
  const resolvedFreshness = freshness || {
    data_through: '2026-06-04',
    latest_workload_date: '2026-06-04',
    last_successful_sync: '2026-06-04T12:00:00+00:00',
    sync_status: 'success',
    is_current: true,
    label: 'Current baseball data through 2026-06-04.',
    limitations: [],
  }
  return {
    capability: 'tonights_bullpen_board',
    team: team || { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' },
    generated_at: '2026-06-05T00:00:00+00:00',
    ranking_applied: false,
    selection_made: false,
    group_order: BOARD_GROUP_ORDER,
    context: context || contextFromGroups(groups, resolvedFreshness),
    groups,
    total_pitchers: totalPitchers,
    ungrouped_pitchers: 0,
    freshness: freshness || {
      data_through: '2026-06-04',
      latest_workload_date: '2026-06-04',
      last_successful_sync: '2026-06-04T12:00:00+00:00',
      sync_status: 'success',
      is_current: true,
      label: 'Current baseball data through 2026-06-04.',
      limitations: [],
    },
    roster_status: rosterStatus || {
      authority: 'available',
      total_candidates: totalPitchers,
      known_count: totalPitchers,
      unknown_count: 0,
      included_unknown_count: 0,
      active_mlb_count: totalPitchers,
      inactive_context_count: 0,
      excluded_inactive_count: 0,
      limitations: [],
    },
    limitations,
  }
}

export const populatedBoard = makeBoard({
  cardsByStatus: {
    Available: [
      card(1, 'Zane Available', 'Available', { short_reason: 'Minimal recent usage' }),
      card(2, 'Alan Available', 'Available', { short_reason: 'Low recent workload' }),
    ],
    Monitor: [
      card(3, 'Marty Monitor', 'Monitor', {
        confidence: 'medium',
        fatigue_score: 45,
        short_reason: '18 pitches yesterday',
        reasons: ['18 pitches yesterday', 'Only 1 day of rest'],
      }),
    ],
    Limited: [
      card(4, 'Larry Limited', 'Limited', {
        confidence: 'medium',
        fatigue_score: 63,
        short_reason: '29 pitches yesterday',
        reasons: ['29 pitches yesterday', '3 appearances in 5 days'],
      }),
    ],
    Avoid: [
      card(5, 'Avery Avoid', 'Avoid', { fatigue_score: 80, short_reason: '42 pitches yesterday' }),
    ],
    Unavailable: [
      card(6, 'Uri Unavailable', 'Unavailable', { fatigue_score: 92, short_reason: '54 pitches yesterday' }),
    ],
  },
})

export const emptyBoard = makeBoard({ cardsByStatus: {} })

export const staleBoard = makeBoard({
  cardsByStatus: {
    Monitor: [
      card(7, 'Stale Sam', 'Monitor', {
        confidence: 'low',
        data_state: 'stale',
        short_reason: 'Data freshness limits confidence',
        reasons: ['Latest workload data is outside the 14-day freshness window'],
        limitations: ['Stale workload data must not be treated as current availability'],
        eligibility: {
          eligible: true,
          status: 'inactive_bullpen_relevant',
          confidence: 'low',
          reason: 'No game logs inside the active freshness window.',
          evidence: [],
          limitations: ['No game logs inside the active freshness window; shown only when stale/context pitchers are included.'],
        },
        roster_status: {
          status: 'UNKNOWN',
          label: 'Roster Unknown',
          source: 'unavailable',
          is_authoritative: false,
          is_active_mlb: null,
          is_inactive_context: false,
          confidence: 'low',
          evidence: [],
          limitations: ['Roster status unavailable; bullpen eligibility is based on stored usage and position data.'],
        },
      }),
    ],
  },
  freshness: {
    data_through: '2026-04-01',
    latest_workload_date: '2026-04-01',
    last_successful_sync: null,
    sync_status: 'metadata_unavailable',
    is_current: false,
    label: 'Historical baseball data through 2026-04-01.',
    limitations: ['Latest game date is outside the 14-day freshness window.'],
  },
  rosterStatus: {
    authority: 'unavailable',
    total_candidates: 1,
    known_count: 0,
    unknown_count: 1,
    included_unknown_count: 1,
    active_mlb_count: 0,
    inactive_context_count: 0,
    excluded_inactive_count: 0,
    limitations: ['Roster status unavailable; bullpen eligibility is based on stored usage and position data.'],
  },
})

export const rosterContextBoard = makeBoard({
  cardsByStatus: {
    Unavailable: [
      card(8, 'Graham Ashcraft', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: IL-60.',
        reasons: ['Roster status: IL-60.'],
        limitations: ['Inactive roster-status context is not active planning availability.'],
        roster_status: {
          status: 'IL_60',
          label: 'IL-60',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: IL-60.'],
          limitations: [],
        },
      }),
      card(9, 'Jose Franco', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: Minors.',
        reasons: ['Roster status: Minors.'],
        limitations: ['Inactive roster-status context is not active planning availability.'],
        roster_status: {
          status: 'MINORS',
          label: 'Minors',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: Minors.'],
          limitations: [],
        },
      }),
    ],
  },
  rosterStatus: {
    authority: 'available',
    total_candidates: 2,
    known_count: 2,
    unknown_count: 0,
    included_unknown_count: 0,
    active_mlb_count: 0,
    inactive_context_count: 2,
    excluded_inactive_count: 0,
    limitations: ['Inactive roster-status cards are context only and are not active planning availability.'],
  },
})
