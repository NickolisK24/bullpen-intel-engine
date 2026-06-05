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

export function makeBoard({ team, cardsByStatus = {}, freshness, limitations = [] } = {}) {
  const groups = buildGroups(cardsByStatus)
  return {
    capability: 'tonights_bullpen_board',
    team: team || { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' },
    generated_at: '2026-06-05T00:00:00+00:00',
    ranking_applied: false,
    selection_made: false,
    group_order: BOARD_GROUP_ORDER,
    groups,
    total_pitchers: groups.reduce((sum, g) => sum + g.count, 0),
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
})
