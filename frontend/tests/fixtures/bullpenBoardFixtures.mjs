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
  'BEREAVEMENT',
  'PATERNITY',
  'SUSPENDED',
  'RESTRICTED',
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
    constrained: 'The bullpen is short on clean options right now.',
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
      summary: 'This pen has ordinary usable room right now.',
      tone: 'manageable',
    },
    monitoring: {
      label: 'Monitoring',
      summary: 'This pen is usable, but a few arms are already in the yellow.',
      tone: 'monitoring',
    },
    elevated: {
      label: 'Elevated',
      summary: 'This pen has less room than usual.',
      tone: 'elevated',
    },
    constrained: {
      label: 'Constrained',
      summary: 'This pen is short on clean options.',
      tone: 'constrained',
    },
    no_data: {
      label: 'No Read',
      summary: 'Not enough bullpen data to give a clean availability note.',
      tone: 'muted',
    },
  }
  const base = meta[state] || meta.no_data
  return {
    state,
    label: isStale && state !== 'no_data' ? 'No Read' : base.label,
    summary: isStale && state !== 'no_data'
      ? 'Availability note is limited by data freshness.'
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

// Mirror services/roster_authority.build_roster_authority over the fixture cards so the
// board payload carries a realistic, invariant roster_authority. Each card partitions
// into exactly one roster bucket; the availability breakdown applies to active arms only.
const USABLE_AVAILABILITY = ['Available', 'Monitor', 'Limited', 'Avoid']

function rosterBucketOf(card) {
  const rs = card.roster_status || {}
  if (rs.is_inactive_context === true || rs.is_active_mlb === false || INACTIVE_ROSTER_STATUSES.has(rs.status)) {
    return 'inactive'
  }
  if (rs.is_authoritative === false || rs.status === 'UNKNOWN') return 'unknown'
  return 'active'
}

function authorityReason(card, bucket) {
  const rs = card.roster_status || {}
  if (bucket === 'inactive') return `Off the active roster (${rs.label || rs.status || 'inactive'}).`
  if (bucket === 'unknown') return 'Roster status not yet confirmed.'
  return card.availability_status === 'Unavailable'
    ? 'On the active roster; read Unavailable for tonight.'
    : 'On the active roster.'
}

function authorityEvidence(cards, bucket) {
  return cards
    .map(card => ({
      pitcher_id: card.pitcher_id,
      name: card.name,
      roster_status: (card.roster_status || {}).status || 'UNKNOWN',
      roster_status_label: (card.roster_status || {}).label || 'Roster Unknown',
      availability: card.availability_status || null,
      reason: authorityReason(card, bucket),
    }))
    .sort((a, b) => (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
      || (a.pitcher_id || 0) - (b.pitcher_id || 0))
}

export function deriveRosterAuthority(cards, { referenceDate = null } = {}) {
  const active = [], inactive = [], unknown = []
  for (const card of cards) {
    const bucket = rosterBucketOf(card)
    if (bucket === 'inactive') inactive.push(card)
    else if (bucket === 'unknown') unknown.push(card)
    else active.push(card)
  }
  const byAvailability = { Available: [], Monitor: [], Limited: [], Avoid: [], Unavailable: [] }
  const availabilityUnknown = []
  for (const card of active) {
    const status = card.availability_status
    if (byAvailability[status]) byAvailability[status].push(card)
    else availabilityUnknown.push(card)
  }
  const usable = USABLE_AVAILABILITY.flatMap(status => byAvailability[status])
  const total = cards.length
  const known = active.length + inactive.length
  const evidence = {
    bullpen_arms: authorityEvidence(active, 'active'),
    active_bullpen_arms: authorityEvidence(usable, 'active'),
    inactive_roster_context_count: authorityEvidence(inactive, 'inactive'),
    roster_unknown_count: authorityEvidence(unknown, 'unknown'),
    available_count: authorityEvidence(byAvailability.Available, 'active'),
    monitor_count: authorityEvidence(byAvailability.Monitor, 'active'),
    limited_count: authorityEvidence(byAvailability.Limited, 'active'),
    avoid_count: authorityEvidence(byAvailability.Avoid, 'active'),
    unavailable_count: authorityEvidence(byAvailability.Unavailable, 'active'),
    availability_unknown_count: authorityEvidence(availabilityUnknown, 'active'),
  }
  const counts = Object.fromEntries(Object.entries(evidence).map(([key, list]) => [key, list.length]))
  return {
    capability: 'roster_authority_v1',
    version: 'fixture',
    source: 'backend',
    invariant: true,
    reference_date: referenceDate,
    team: null,
    population: {
      total_candidates: total,
      known_count: known,
      unknown_count: unknown.length,
      roster_status_coverage: total ? Math.round((known / total) * 10000) / 10000 : 0.0,
    },
    counts,
    evidence,
    field_invariance: Object.fromEntries(Object.keys(counts).map(key => [key, true])),
    limitations: [],
  }
}

export function makeBoard({ team, cardsByStatus = {}, freshness, limitations = [], context, stress, rosterAuthority } = {}) {
  const groups = buildGroups(cardsByStatus)
  const totalPitchers = groups.reduce((sum, g) => sum + g.count, 0)
  const allCards = groups.flatMap(group => group.pitchers)
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
    // Roster Authority is the single roster-context payload (the legacy roster_status board
    // summary was retired in CRC-10). Defaults to the authority derived from the board's cards;
    // explicit fixtures may override it to model an authority population larger than the cards.
    roster_authority: rosterAuthority || deriveRosterAuthority(allCards, { referenceDate: resolvedFreshness.data_through }),
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
        last_appearance: { game_date: '2026-06-04', pitches: 18 },
        reasons: ['18 pitches yesterday', 'Only 1 day of rest'],
      }),
    ],
    Limited: [
      card(4, 'Larry Limited', 'Limited', {
        confidence: 'medium',
        fatigue_score: 63,
        short_reason: '29 pitches yesterday',
        last_appearance: { game_date: '2026-06-03', pitches: 29 },
        reasons: ['29 pitches yesterday', '3 appearances in 5 days'],
      }),
    ],
    Avoid: [
      card(5, 'Avery Avoid', 'Avoid', {
        fatigue_score: 80,
        short_reason: '42 pitches yesterday',
        last_appearance: { game_date: '2026-05-30', pitches: 42 },
      }),
    ],
    Unavailable: [
      card(6, 'Uri Unavailable', 'Unavailable', {
        fatigue_score: 92,
        short_reason: '54 pitches yesterday',
        last_appearance: { game_date: '2026-06-01', pitches: 54 },
      }),
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
})

export const rosterContextBoard = makeBoard({
  cardsByStatus: {
    Unavailable: [
      card(8, 'Graham Ashcraft', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: 60-Day IL.',
        reasons: ['Roster status: 60-Day IL.'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
        roster_status: {
          status: 'IL_60',
          label: '60-Day IL',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: 60-Day IL.'],
          limitations: [],
        },
      }),
      card(9, 'Jose Franco', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: 40-Man (not active).',
        reasons: ['Roster status: 40-Man (not active).'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
        roster_status: {
          status: '40_MAN_ONLY',
          label: '40-Man (not active)',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: 40-Man (not active).'],
          limitations: [],
        },
      }),
      card(10, 'Connor Phillips', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: Optioned / Minors.',
        reasons: ['Roster status: Optioned / Minors.'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
        roster_status: {
          status: 'MINORS',
          label: 'Optioned / Minors',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: Optioned / Minors.'],
          limitations: [],
        },
      }),
    ],
  },
})

// STL-like case: the roster summary knows about more roster-inactive arms than
// the board lists as cards. One inactive pitcher is shown (a card the reader can
// open); the other six are off the active roster and not listed. The visible
// "Unavailable Pitchers" count must stay at the one shown card, with the rest
// reported separately — never folded into a single "7" that has no cards behind it.
// STL-like canonical case: the authority knows about 7 off-roster arms, but only one of
// them (Ike Injured) is rendered as a card. The banner must show the invariant count of 7
// with evidence for all seven, plus a view-only "showing 1 of 7 here" — never a roster
// number that shifts with the filter.
function offRosterEvidenceEntry(pitcherId, name, status, label) {
  return {
    pitcher_id: pitcherId,
    name,
    roster_status: status,
    roster_status_label: label,
    availability: 'Unavailable',
    reason: `Off the active roster (${label}).`,
  }
}

const STL_OFF_ROSTER_EVIDENCE = [
  offRosterEvidenceEntry(21, 'Ike Injured', 'IL_60', '60-Day IL'),
  offRosterEvidenceEntry(22, 'Cal Optioned', 'MINORS', 'Optioned / Minors'),
  offRosterEvidenceEntry(23, 'Dom Designated', 'DFA', 'DFA'),
  offRosterEvidenceEntry(24, 'Ned Nonroster', 'NON_ROSTER', 'Non-Roster'),
  offRosterEvidenceEntry(25, 'Saul Suspended', 'SUSPENDED', 'Suspended List'),
  offRosterEvidenceEntry(26, 'Pat Paternity', 'PATERNITY', 'Paternity List'),
  offRosterEvidenceEntry(27, 'Rex Restricted', 'RESTRICTED', 'Restricted List'),
]

const STL_ACTIVE_EVIDENCE = [{
  pitcher_id: 20, name: 'Andre Active', roster_status: 'ACTIVE',
  roster_status_label: 'Active MLB', availability: 'Available', reason: 'On the active roster.',
}]

export const rosterContextExcludedBoard = makeBoard({
  cardsByStatus: {
    Available: [
      card(20, 'Andre Active', 'Available', { short_reason: 'Low recent workload' }),
    ],
    Unavailable: [
      card(21, 'Ike Injured', 'Unavailable', {
        confidence: 'high',
        short_reason: 'Roster status: 60-Day IL.',
        reasons: ['Roster status: 60-Day IL.'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
        roster_status: {
          status: 'IL_60',
          label: '60-Day IL',
          source: 'test_fixture',
          is_authoritative: true,
          is_active_mlb: false,
          is_inactive_context: true,
          confidence: 'high',
          evidence: ['Stored roster status: 60-Day IL.'],
          limitations: [],
        },
      }),
    ],
  },
  rosterAuthority: {
    capability: 'roster_authority_v1',
    version: 'fixture',
    source: 'backend',
    invariant: true,
    reference_date: '2026-06-04',
    team: null,
    population: { total_candidates: 8, known_count: 8, unknown_count: 0, roster_status_coverage: 1.0 },
    counts: {
      bullpen_arms: 1, active_bullpen_arms: 1, inactive_roster_context_count: 7, roster_unknown_count: 0,
      available_count: 1, monitor_count: 0, limited_count: 0, avoid_count: 0, unavailable_count: 0, availability_unknown_count: 0,
    },
    evidence: {
      bullpen_arms: STL_ACTIVE_EVIDENCE,
      active_bullpen_arms: STL_ACTIVE_EVIDENCE,
      inactive_roster_context_count: STL_OFF_ROSTER_EVIDENCE,
      roster_unknown_count: [],
      available_count: STL_ACTIVE_EVIDENCE,
      monitor_count: [], limited_count: [], avoid_count: [], unavailable_count: [], availability_unknown_count: [],
    },
    field_invariance: {
      bullpen_arms: true, active_bullpen_arms: true, inactive_roster_context_count: true,
      roster_unknown_count: true, available_count: true, monitor_count: true, limited_count: true,
      avoid_count: true, unavailable_count: true, availability_unknown_count: true,
    },
    limitations: [],
  },
})

// NYY-like case: two 40-man (not active) arms are surfaced as cards for roster
// awareness. They are inspectable, so the visible "Unavailable Pitchers" count
// maps exactly to the two cards and no "off roster (not shown)" line appears.
function fortyManNotActiveCard(pitcherId, name) {
  return card(pitcherId, name, 'Unavailable', {
    confidence: 'high',
    short_reason: 'Roster status: 40-Man (not active).',
    reasons: ['Roster status: 40-Man (not active).'],
    limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
    roster_status: {
      status: '40_MAN_ONLY',
      label: '40-Man (not active)',
      source: 'test_fixture',
      is_authoritative: true,
      is_active_mlb: false,
      is_inactive_context: true,
      confidence: 'high',
      evidence: ['Stored roster status: 40-Man (not active).'],
      limitations: [],
    },
  })
}

export const fortyManShownBoard = makeBoard({
  cardsByStatus: {
    Unavailable: [
      fortyManNotActiveCard(30, 'Milo Marquez'),
      fortyManNotActiveCard(31, 'Nate Nunez'),
    ],
  },
})
