// Fixtures mirroring GET /api/bullpen/teams/<id>/board, used to render the
// presentational BullpenBoardView without a backend.

const BOARD_GROUP_ORDER = ['Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable']

const GROUP_META = {
  Available: { label: 'Available', description: 'Workload signals are inside normal ranges in the latest completed data.' },
  Monitor: { label: 'Monitor', description: 'Worth a look at recent workload before counting on these arms.' },
  Limited: { label: 'Limited', description: 'Recent workload suggests limited use in the current availability read.' },
  Avoid: { label: 'Avoid', description: 'Meaningful recent-use load on these arms.' },
  Unavailable: { label: 'Unavailable Pitchers', description: 'Not available in the current bullpen planning read.' },
}

const ROLE_LABELS_BY_KEY = {
  late_high_leverage: { kind: 'role', key: 'trust_arm', label: 'Trust Arm', source: 'backend:test_fixture' },
  high_leverage: { kind: 'role', key: 'trust_arm', label: 'Trust Arm', source: 'backend:test_fixture' },
  setup_bridge: { kind: 'role', key: 'bridge_arm', label: 'Bridge Arm', source: 'backend:test_fixture' },
  middle_relief: { kind: 'role', key: 'bridge_arm', label: 'Bridge Arm', source: 'backend:test_fixture' },
  long_multi_inning: { kind: 'role', key: 'coverage_arm', label: 'Coverage Arm', source: 'backend:test_fixture' },
  depth: { kind: 'role', key: 'depth_arm', label: 'Depth Arm', source: 'backend:test_fixture' },
}

const LIMITED_ROLE_LABEL = { kind: 'role', key: 'limited_read', label: 'Limited Read', source: 'backend:test_fixture' }

const READ_LABELS_BY_STATUS = {
  Available: { kind: 'read', key: 'clean_option', label: 'Clean Option', source: 'backend:test_fixture' },
  Monitor: { kind: 'read', key: 'watch_arm', label: 'Watch Arm', source: 'backend:test_fixture' },
  Limited: { kind: 'read', key: 'rest_restricted', label: 'Rest-Restricted', source: 'backend:test_fixture' },
  Avoid: { kind: 'read', key: 'rest_restricted', label: 'Rest-Restricted', source: 'backend:test_fixture' },
  Unavailable: { kind: 'read', key: 'unavailable', label: 'Unavailable', source: 'backend:test_fixture' },
}

const LIMITED_READ_LABEL = { kind: 'read', key: 'limited_read', label: 'Limited Read', source: 'backend:test_fixture' }
const UNAVAILABLE_READ_LABEL = { kind: 'read', key: 'unavailable', label: 'Unavailable', source: 'backend:test_fixture' }

const INACTIVE_ROSTER_STATUSES = new Set([
  'IL_10',
  'IL_15',
  'IL_60',
  'MINORS',
  'OPTIONED',
  'DFA',
  'NON_ROSTER',
  '40_MAN_ONLY',
])

function authoredPitcherLabels(card) {
  if (card.pitcher_labels || card.pitcherLabels) return card.pitcher_labels || card.pitcherLabels

  const roleKey = card.role?.role_key
  const role = card.role?.confidence === 'none' || card.role?.confidence === 'low'
    ? LIMITED_ROLE_LABEL
    : ROLE_LABELS_BY_KEY[roleKey] || LIMITED_ROLE_LABEL
  const rosterStatus = card.roster_status || {}
  const rosterUnavailable = (
    rosterStatus.is_active_mlb === false ||
    rosterStatus.is_inactive_context === true ||
    INACTIVE_ROSTER_STATUSES.has(rosterStatus.status)
  )
  const staleOrMissing = ['stale', 'missing', 'incomplete', 'failed'].includes(String(card.data_state || '').toLowerCase())
  const read = rosterUnavailable
    ? UNAVAILABLE_READ_LABEL
    : staleOrMissing
      ? LIMITED_READ_LABEL
      : READ_LABELS_BY_STATUS[card.availability_status] || LIMITED_READ_LABEL

  return { role, read }
}

function normalizeCardForBackendPayload(card) {
  return {
    ...card,
    pitcher_labels: authoredPitcherLabels(card),
  }
}

function card(pitcherId, name, status, overrides = {}) {
  return normalizeCardForBackendPayload({
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
  })
}

function buildGroups(cardsByStatus) {
  return BOARD_GROUP_ORDER.map(status => {
    const pitchers = (cardsByStatus[status] || []).map(normalizeCardForBackendPayload)
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
    constrained: 'Availability is constrained in the current read.',
    no_data: 'No bullpen availability to summarize from the latest completed data.',
  }
  const pct = (part) => (total ? Math.round((part / total) * 100) : 0)
  const reasons = total === 0
    ? ['No active relievers fall inside the current freshness window.']
    : [
      `${available} of ${total} relievers are classified Available.`,
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
    const note = 'Latest workload data is outside the active freshness window, so this snapshot may not reflect current bullpen planning.'
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

function stressFromContext(context) {
  const state = context?.health?.state || 'no_data'
  const confidence = context?.confidence || 'none'
  const isStale = confidence === 'low'
  const meta = {
    manageable: {
      label: 'Manageable',
      summary: 'Overall bullpen availability is manageable.',
      tone: 'manageable',
    },
    monitoring: {
      label: 'Monitoring',
      summary: 'Overall bullpen availability needs monitoring.',
      tone: 'monitoring',
    },
    elevated: {
      label: 'Elevated',
      summary: 'Overall bullpen availability is tighter than usual.',
      tone: 'elevated',
    },
    constrained: {
      label: 'Constrained',
      summary: 'Overall bullpen availability is constrained.',
      tone: 'constrained',
    },
    no_data: {
      label: 'No Read',
      summary: 'Not enough current bullpen data to assess overall availability.',
      tone: 'muted',
    },
  }
  const base = meta[state] || meta.no_data
  return {
    state,
    label: isStale && state !== 'no_data' ? 'No Read' : base.label,
    summary: isStale && state !== 'no_data'
      ? 'Overall availability read is limited by data freshness.'
      : base.summary,
    reasons: context?.health?.reasons || [],
    reason_codes: [state === 'no_data' ? 'no_current_bullpen_data' : `fixture_${state}`],
    confidence,
    is_stale: isStale,
    limitations: context?.limitations || [],
    tone: isStale ? 'muted' : base.tone,
    source: 'team_context.health',
  }
}

export function makeBoard({ team, cardsByStatus = {}, freshness, limitations = [], context, stress, rosterStatus } = {}) {
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
  const resolvedContext = context || contextFromGroups(groups, resolvedFreshness)
  return {
    capability: 'tonights_bullpen_board',
    team: team || { team_id: 1, team_name: 'Test Club', team_abbreviation: 'TST' },
    generated_at: '2026-06-05T00:00:00+00:00',
    ranking_applied: false,
    selection_made: false,
    group_order: BOARD_GROUP_ORDER,
    context: resolvedContext,
    stress: stress || stressFromContext(resolvedContext),
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
        short_reason: 'Outside active freshness window',
        reasons: ['Latest workload data is outside the 14-day freshness window'],
        limitations: ['Stale workload data must not be treated as current availability'],
        eligibility: {
          eligible: true,
          status: 'inactive_bullpen_relevant',
          confidence: 'low',
          reason: 'No game logs inside the active freshness window.',
          evidence: [],
          limitations: ['No game logs inside the active freshness window; shown only when unavailable or stale workload pitchers are included.'],
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
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
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
        short_reason: 'Roster status: 40-Man Only.',
        reasons: ['Roster status: 40-Man Only.'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
        roster_status: {
          status: '40_MAN_ONLY',
          label: '40-Man Only',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: 40-Man Only.'],
          limitations: [],
        },
      }),
      card(10, 'Connor Phillips', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: Minors.',
        reasons: ['Roster status: Minors.'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
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
    total_candidates: 3,
    known_count: 3,
    unknown_count: 0,
    included_unknown_count: 0,
    active_mlb_count: 0,
    inactive_context_count: 3,
    excluded_inactive_count: 0,
    limitations: ['Unavailable pitchers are shown for roster awareness and are not counted as active bullpen options.'],
  },
})
