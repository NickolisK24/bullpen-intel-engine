export const TEAM_BOARD_V2_CAPABILITY = 'team_board_v2'
export const TEAM_BOARD_V2_CONTRACT_VERSION = 'team-board-2.0.0'
export const TEAM_BOARD_CORE_CAPABILITY = 'team_board_answer_core'
export const TEAM_BOARD_CORE_CONTRACT_VERSION = 'team_board_answer_core_v1'
export const TEAM_BOARD_DETAILS_CAPABILITY = 'team_board_deferred_details'
export const TEAM_BOARD_DETAILS_CONTRACT_VERSION = 'team_board_deferred_details_v1'
export const TEAM_BOARD_RECENT_USAGE_REST_CONTRACT = 'team_board_recent_usage_rest_v1'
export const TEAM_BOARD_FROZEN_WORKLOAD_CONTRACT = 'team_board_workload_overview_v1'
export const TEAM_BOARD_PUBLIC_DEPLOYMENT_CONTRACT = 'team_board_public_deployment_context_v1'
export const TEAM_BOARD_PERFORMANCE_CONTRACT = 'public_team_performance_v1'
export const TEAM_BOARD_ROTATION_GAMES_CONTRACT = 'team_board_recent_rotation_games_v1'
export const TEAM_BOARD_ROSTER_TRANSACTIONS_CONTRACT = 'team_board_roster_transactions_v1'
export const TEAM_BOARD_WHAT_CHANGED_CONTRACT = 'team_board_what_changed_v1'

const whatChangedDomains = new Set([
  'team_state', 'roster', 'workload_rest', 'transactions', 'rotation',
])

export function readTeamBoardFrozenWhatChanged(carrier, publicationIdentity) {
  const receipt = carrier?.comparison_identity
  if (!carrier || typeof carrier !== 'object' || Array.isArray(carrier)
    || carrier.contract !== TEAM_BOARD_WHAT_CHANGED_CONTRACT
    || carrier.method_version !== TEAM_BOARD_WHAT_CHANGED_CONTRACT
    || !publicationIdentity || publicationIdentity.publication_authority_contract !== 'trusted_dashboard_publication_v1'
    || carrier.team_id !== publicationIdentity.team_id
    || carrier.current_snapshot_id !== publicationIdentity.snapshot_id
    || carrier.current_represented_date !== publicationIdentity.represented_date
    || !['changes', 'quiet', 'unavailable'].includes(carrier.state)
    || !['complete', 'partial', 'unavailable'].includes(carrier.comparison_status)
    || (carrier.state !== 'unavailable' && !receipt)
    || !carrier.domains || typeof carrier.domains !== 'object'
    || Object.values(carrier.domains).some(domain => !domain || !['complete', 'partial', 'unavailable', 'not_comparable'].includes(domain.status))
    || !Array.isArray(carrier.events)
    || carrier.events.length > 5
    || (carrier.state === 'quiet' && carrier.events.length > 0)
    || (receipt && (receipt.contract !== 'what_changed_comparison_identity_v1'
      || receipt.current_snapshot_id !== publicationIdentity.snapshot_id
      || receipt.current_data_through !== publicationIdentity.represented_date
      || receipt.previous_snapshot_id !== carrier.previous_snapshot_id
      || receipt.previous_data_through !== carrier.previous_represented_date))) return null
  const events = carrier.events.map((event, index) => {
    if (!event || !whatChangedDomains.has(event.domain)
      || typeof event.event_type !== 'string' || !event.event_type
      || event.evidence_status !== 'complete'
      || event.current_snapshot_id !== carrier.current_snapshot_id
      || event.previous_snapshot_id !== carrier.previous_snapshot_id
      || event.method_version !== 'team_board_what_changed_event_v1'
      || typeof event.summary !== 'string' || !event.summary.trim()) return null
    return {
      key: `${event.domain}-${event.event_type}-${event.subject_id ?? 'team'}-${event.event_date || index}`,
      type: event.event_type,
      domain: event.domain,
      subjectId: event.subject_id,
      eventDate: event.event_date,
      previousValue: event.previous_value,
      currentValue: event.current_value,
      facts: event.facts && typeof event.facts === 'object' ? event.facts : {},
      summary: event.summary,
    }
  })
  if (events.some(event => !event)) return null
  return {
    contract: carrier.contract,
    state: carrier.state,
    comparisonStatus: carrier.comparison_status,
    currentRepresentedDate: carrier.current_represented_date,
    previousRepresentedDate: carrier.previous_represented_date,
    quietMessage: carrier.quiet_message,
    domains: carrier.domains,
    events,
  }
}

const recentUsageRestStates = new Set(['complete', 'partial', 'unknown', 'unavailable'])
const workloadWindowKeys = [3, 7, 14, 30]
const workloadMetricKeys = ['pitches', 'appearances', 'outs']

const nonnegativeCount = value => Number.isSafeInteger(value) && value >= 0
const baseballInnings = value => typeof value === 'string' && /^\d+\.[012]$/.test(value)

function readCurrentRosterStatus(source) {
  if (!source || !recentUsageRestStates.has(source.status)
    || !['active', 'active_roster', 'off_active', null].includes(source.membership)
    || typeof source.label !== 'string' || !source.label.trim()) return null
  return { status: source.status, membership: source.membership, label: source.label }
}

export function readTeamBoardFrozenRosterTransactions(carrier, publicationIdentity, activeArmIds = null) {
  const group = carrier?.current_group
  const offActive = carrier?.off_active_recent_contributors
  if (!carrier || typeof carrier !== 'object' || Array.isArray(carrier)
    || carrier.contract !== TEAM_BOARD_ROSTER_TRANSACTIONS_CONTRACT
    || !publicationIdentity || publicationIdentity.publication_authority_contract !== 'trusted_dashboard_publication_v1'
    || carrier.team_id !== publicationIdentity.team_id
    || carrier.data_through !== publicationIdentity.represented_date
    || !['available', 'partial', 'unavailable'].includes(carrier.status)
    || !Array.isArray(carrier.events) || !Array.isArray(carrier.limitations)
    || !group || !nonnegativeCount(group.active_count)
    || !Array.isArray(group.active_pitcher_ids)
    || group.active_count !== group.active_pitcher_ids.length
    || group.active_pitcher_ids.some(id => !nonnegativeCount(id))
    || (activeArmIds && JSON.stringify([...group.active_pitcher_ids].sort((a, b) => a - b))
      !== JSON.stringify([...activeArmIds].sort((a, b) => a - b)))
    || !offActive || !recentUsageRestStates.has(offActive.status)
    || offActive.window_days !== 7 || !Array.isArray(offActive.contributors)
    || (offActive.status !== 'complete' && offActive.contributors.length > 0)) return null
  const events = carrier.events.map(event => {
    const currentRoster = readCurrentRosterStatus(event?.current_roster)
    if (!event || !nonnegativeCount(event.player_id)
      || typeof event.player_name !== 'string' || !event.player_name.trim()
      || typeof event.date !== 'string' || event.date > carrier.data_through
      || typeof event.label !== 'string' || !event.label.trim()
      || typeof event.description !== 'string' || !event.description.trim()
      || !['addition', 'removal', 'other'].includes(event.direction)
      || event.evidence_status !== 'complete'
      || typeof event.source !== 'string' || !event.source
      || !currentRoster) return null
    return {
      eventId: event.event_id,
      pitcherId: event.player_id,
      name: event.player_name,
      date: event.date,
      type: event.type,
      label: event.label,
      description: event.description,
      direction: event.direction,
      currentRoster,
    }
  })
  const contributors = offActive.contributors.map(item => {
    const currentRoster = readCurrentRosterStatus(item?.current_roster)
    if (!item || !nonnegativeCount(item.pitcher_id)
      || typeof item.name !== 'string' || !item.name.trim()
      || !currentRoster) return null
    return { pitcherId: item.pitcher_id, name: item.name, currentRoster }
  })
  if (events.some(item => !item) || contributors.some(item => !item)) return null
  return {
    contract: carrier.contract,
    teamId: carrier.team_id,
    dataThrough: carrier.data_through,
    status: carrier.status,
    windowStart: carrier.window_start_date,
    windowEnd: carrier.window_end_date,
    limitations: carrier.limitations,
    currentGroup: { activeCount: group.active_count },
    events,
    offActiveRecentContributors: { status: offActive.status, contributors },
  }
}

export function readTeamBoardFrozenRotationGames(carrier, publicationIdentity) {
  if (!carrier || typeof carrier !== 'object' || Array.isArray(carrier)
    || carrier.contract !== TEAM_BOARD_ROTATION_GAMES_CONTRACT
    || !publicationIdentity || publicationIdentity.publication_authority_contract !== 'trusted_dashboard_publication_v1'
    || carrier.team_id !== publicationIdentity.team_id
    || carrier.data_through !== publicationIdentity.represented_date
    || carrier.window_days !== 7
    || !['complete', 'partial', 'unknown', 'unavailable'].includes(carrier.status)
    || !nonnegativeCount(carrier.games_in_window)
    || !nonnegativeCount(carrier.games_excluded)
    || !nonnegativeCount(carrier.games_analyzed)
    || (carrier.games_analyzed > 0
      ? !baseballInnings(carrier.starter_innings) || !baseballInnings(carrier.bullpen_innings)
        || !nonnegativeCount(carrier.short_start_count) || typeof carrier.summary !== 'string'
      : carrier.starter_innings !== null || carrier.bullpen_innings !== null
        || carrier.short_start_count !== null || carrier.summary !== null)
    || !Array.isArray(carrier.starts)) return null
  const starts = carrier.starts.map(game => {
    const starterStatus = game?.starter_evidence?.status
    const bullpenStatus = game?.bullpen_evidence?.status
    const shortStatus = game?.short_start_evidence?.status
    if (!nonnegativeCount(game?.mlb_game_pk)
      || typeof game.game_date !== 'string'
      || !recentUsageRestStates.has(starterStatus)
      || !recentUsageRestStates.has(bullpenStatus)
      || !recentUsageRestStates.has(shortStatus)
      || (starterStatus === 'complete' ? !nonnegativeCount(game.starter_outs) || !baseballInnings(game.starter_innings) : game.starter_outs !== null || game.starter_innings !== null)
      || (bullpenStatus === 'complete' ? !nonnegativeCount(game.bullpen_outs) || !baseballInnings(game.bullpen_innings) : game.bullpen_outs !== null || game.bullpen_innings !== null)
      || (shortStatus === 'complete' ? typeof game.short_start !== 'boolean' : game.short_start !== null)
      || !recentUsageRestStates.has(game.status)
      || game.starter_pitcher_id !== null && !nonnegativeCount(game.starter_pitcher_id)
      || game.starter_name !== null && typeof game.starter_name !== 'string') return null
    return {
      gameId: game.mlb_game_pk,
      date: game.game_date,
      starterPitcherId: game.starter_pitcher_id,
      starterName: game.starter_name,
      starterOuts: game.starter_outs,
      starterInnings: game.starter_innings,
      starterEvidence: game.starter_evidence,
      bullpenOuts: game.bullpen_outs,
      bullpenInnings: game.bullpen_innings,
      bullpenEvidence: game.bullpen_evidence,
      shortStart: game.short_start,
      shortStartEvidence: game.short_start_evidence,
    }
  })
  if (starts.some(game => !game)) return null
  return {
    contract: carrier.contract,
    teamId: carrier.team_id,
    dataThrough: carrier.data_through,
    windowStart: carrier.window_start,
    windowDays: carrier.window_days,
    status: carrier.status,
    reasonCodes: Array.isArray(carrier.reason_codes) ? [...carrier.reason_codes] : [],
    gamesInWindow: carrier.games_in_window,
    gamesExcluded: carrier.games_excluded,
    gamesAnalyzed: carrier.games_analyzed,
    starterInnings: carrier.starter_innings,
    bullpenInnings: carrier.bullpen_innings,
    shortStartCount: carrier.short_start_count,
    summary: carrier.summary,
    starts,
  }
}

const publicRoleLabels = new Set(['Trusted Arm', 'Setup Arm', 'Coverage Arm', 'Middle Relief Arm', 'Role Unclear'])

function readDeploymentDomain(source, fields) {
  if (!source || !recentUsageRestStates.has(source.status)
    || !nonnegativeCount(source.appearances) || !nonnegativeCount(source.known_appearances)
    || source.known_appearances > source.appearances
    || fields.some(field => !nonnegativeCount(source[field]))) return null
  return {
    status: source.status,
    appearances: source.appearances,
    knownAppearances: source.known_appearances,
    reasonCodes: Array.isArray(source.reason_codes) ? [...source.reason_codes] : [],
    ...Object.fromEntries(fields.map(field => [field, source[field]])),
  }
}

export function readTeamBoardFrozenDeployment(carrier, publicationIdentity) {
  if (!carrier || typeof carrier !== 'object' || Array.isArray(carrier)
    || carrier.contract !== TEAM_BOARD_PUBLIC_DEPLOYMENT_CONTRACT
    || carrier.method_version !== TEAM_BOARD_PUBLIC_DEPLOYMENT_CONTRACT
    || !publicationIdentity || publicationIdentity.publication_authority_contract !== 'trusted_dashboard_publication_v1'
    || carrier.team_id !== publicationIdentity.team_id
    || carrier.data_through !== publicationIdentity.represented_date
    || carrier.window_days !== 14 || !Array.isArray(carrier.profiles)) return null
  const profiles = carrier.profiles.map(item => {
    const role = item?.public_role_read
    const context = item?.context
    const entry = readDeploymentDomain(context?.entry_inning, ['eighth_or_later_appearances', 'extra_inning_appearances'])
    const score = readDeploymentDomain(context?.score_context, ['leading', 'tied', 'trailing'])
    const leverage = readDeploymentDomain(context?.leverage, ['high', 'middle', 'low'])
    const observed = item?.observed_profile
    if (!nonnegativeCount(item?.pitcher_id) || item.team_id !== carrier.team_id
      || typeof item.pitcher_name !== 'string' || !item.pitcher_name.trim()
      || !role || !publicRoleLabels.has(role.label)
      || context?.pitcher_id !== item.pitcher_id || !entry || !score || !leverage
      || context.leverage.basis !== 'recorded_game_log_leverage_index_only'
      || !Array.isArray(context.entry_inning.by_inning)
      || context.entry_inning.by_inning.some(row => !nonnegativeCount(row?.inning) || !nonnegativeCount(row?.appearances))
      || observed && (observed.pitcher_id !== item.pitcher_id || ['appearances_analyzed', 'saves', 'holds', 'games_finished', 'multi_inning_appearances', 'appearances_with_games_finished', 'appearances_with_outs'].some(key => !nonnegativeCount(observed[key])))) return null
    return {
      pitcherId: item.pitcher_id,
      name: item.pitcher_name,
      role: { key: role.key, label: role.label, confidence: role.confidence ?? null },
      entry: { ...entry, byInning: context.entry_inning.by_inning.map(row => ({ inning: row.inning, appearances: row.appearances })) },
      score,
      leverage,
      observed: observed ? {
        appearances: observed.appearances_analyzed,
        saves: observed.saves,
        holds: observed.holds,
        gamesFinished: observed.games_finished,
        knownGamesFinished: observed.appearances_with_games_finished,
        multiInning: observed.multi_inning_appearances,
        knownOuts: observed.appearances_with_outs,
        limitations: Array.isArray(observed.limitations) ? [...observed.limitations] : [],
      } : null,
    }
  })
  if (profiles.some(profile => !profile)) return null
  return { contract: carrier.contract, teamId: carrier.team_id, dataThrough: carrier.data_through, windowDays: 14, profiles }
}

function readWorkloadMetric(metric) {
  if (!metric || typeof metric !== 'object' || !recentUsageRestStates.has(metric.status)) return null
  if (metric.value !== null && !nonnegativeCount(metric.value)) return null
  if (metric.status === 'complete' && metric.value === null) return null
  if (metric.status !== 'complete' && metric.value !== null) return null
  return { value: metric.value, status: metric.status, reasonCodes: Array.isArray(metric.reason_codes) ? [...metric.reason_codes] : [] }
}

function readWorkloadContributor(item) {
  if (!item || !nonnegativeCount(item.pitcher_id) || typeof item.name !== 'string' || !nonnegativeCount(item.pitches) || !nonnegativeCount(item.appearances) || (item.outs !== null && !nonnegativeCount(item.outs)) || typeof item.current_active !== 'boolean') return null
  return { pitcherId: item.pitcher_id, name: item.name, pitches: item.pitches, appearances: item.appearances, outs: item.outs, currentActive: item.current_active }
}

function readWorkloadContribution(item) {
  if (!item || !nonnegativeCount(item.pitches) || !nonnegativeCount(item.appearances) || (item.outs !== null && !nonnegativeCount(item.outs))) return null
  return { pitches: item.pitches, appearances: item.appearances, outs: item.outs }
}

export function readTeamBoardFrozenWorkload(carrier, publicationIdentity) {
  if (!carrier || typeof carrier !== 'object' || Array.isArray(carrier)
    || carrier.contract !== TEAM_BOARD_FROZEN_WORKLOAD_CONTRACT
    || !publicationIdentity || carrier.data_through !== publicationIdentity.represented_date
    || publicationIdentity.publication_authority_contract !== 'trusted_dashboard_publication_v1'
    || !carrier.windows || typeof carrier.windows !== 'object') return null
  const windows = workloadWindowKeys.map(days => {
    const window = carrier.windows[`window_${days}`]
    if (!window || typeof window.start !== 'string' || window.through !== carrier.data_through) return null
    const metrics = Object.fromEntries(workloadMetricKeys.map(key => [key, readWorkloadMetric(window[key])]))
    if (workloadMetricKeys.some(key => !metrics[key])) return null
    return { days, label: `${days} Days`, start: window.start, through: window.through, ...metrics }
  })
  if (windows.some(window => !window)) return null
  const source = carrier.concentration_7_day
  if (!source || !recentUsageRestStates.has(source.status) || !Array.isArray(source.contributors)
    || !Array.isArray(source.top_3_contributors)) return null
  const contributors = source.contributors.map(readWorkloadContributor)
  const topThree = source.top_3_contributors.map(readWorkloadContributor)
  if (contributors.some(item => !item) || topThree.some(item => !item)
    || !Object.prototype.hasOwnProperty.call(source, 'top_3_share')
    || !Object.prototype.hasOwnProperty.call(source, 'pitcher_count')
    || (source.top_3_share !== null && !(typeof source.top_3_share === 'number' && source.top_3_share >= 0 && source.top_3_share <= 1))
    || (source.pitcher_count !== null && !nonnegativeCount(source.pitcher_count))
    || (source.status === 'complete' && (!nonnegativeCount(source.total_pitches) || !nonnegativeCount(source.pitcher_count)))) return null
  return {
    contract: carrier.contract,
    dataThrough: carrier.data_through,
    windows,
    concentration: {
      status: source.status,
      reasonCodes: Array.isArray(source.reason_codes) ? [...source.reason_codes] : [],
      totalPitches: source.total_pitches,
      topThreeShare: source.top_3_share,
      pitcherCount: source.pitcher_count,
      contributors,
      topThree,
      activeCurrentContribution: source.active_current_contribution === null ? null : readWorkloadContribution(source.active_current_contribution),
      offActiveContribution: source.off_active_contribution === null ? null : readWorkloadContribution(source.off_active_contribution),
    },
  }
}

export function readTeamBoardFrozenPerformance(read, publicationIdentity) {
  if (!read || typeof read !== 'object' || Array.isArray(read)
    || !publicationIdentity
    || publicationIdentity.publication_authority_contract !== 'trusted_dashboard_publication_v1'
    || read.capability !== 'public_team_performance'
    || read.contract_version !== TEAM_BOARD_PERFORMANCE_CONTRACT
    || read.through !== publicationIdentity.represented_date
    || read.population_basis !== 'represented_default_visible_active_bullpen'
    || !['available', 'partial', 'unavailable'].includes(read.status)
    || (read.status !== 'unavailable' && (!read.window || !read.sample))
    || (read.window && (read.window.through !== read.through
      || read.window.policy !== 'current_mlb_regular_season_through_represented_date'))
    || !Array.isArray(read.metrics)
    || !read.capabilities || typeof read.capabilities !== 'object') return null
  const expected = ['active_bullpen_era', 'active_bullpen_whip']
  if (read.status !== 'unavailable' && (read.metrics.length !== 2
    || read.metrics.some((metric, index) => metric?.key !== expected[index]
      || metric.metric_id !== `M-00${index + 1}`))) return null
  if (read.metrics.some(metric => !metric || !['M-001', 'M-002'].includes(metric.metric_id)
    || !['complete', 'partial', 'unknown', 'unavailable'].includes(metric.evidence_state?.status)
    || !['qualified', 'below_minimum', 'unavailable'].includes(metric.qualification?.status)
    || (metric.value !== null && typeof metric.value !== 'string')
    || (metric.qualification.status === 'qualified' && metric.value === null)
    || (metric.qualification.status !== 'qualified' && metric.value !== null))) return null
  if (['k_bb_percent', 'home_runs_allowed', 'inherited_runner_context'].some(key => {
    const capability = read.capabilities[key]
    return !capability || capability.status !== 'unavailable' || capability.value !== null
  })) return null
  return read
}

const identityFields = [
  'contract', 'team_id', 'team_abbreviation', 'snapshot_id', 'sync_run_id',
  'represented_date', 'availability_reference_date', 'published_at',
  'snapshot_generated_at', 'dashboard_payload_version',
  'publication_authority_contract', 'team_board_package_contract',
  'team_board_contract_version', 'team_state_contract',
  'bullpen_membership_method_version', 'rest_status_method_version',
  'workload_windows_method_version', 'deployment_profile_method_version',
  'rotation_impact_method_version',
]

export function teamBoardIdentityKey(identity) {
  if (!identity) return null
  return JSON.stringify(identityFields.map(field => identity[field] ?? null))
}

export function getTeamBoardDetailsIdentity(corePayload, teamId) {
  if (!isTeamBoardCorePayload(corePayload)) return null
  const requestedTeamId = Number(teamId)
  const identity = corePayload.publication_identity
  if (!Number.isSafeInteger(requestedTeamId) || requestedTeamId <= 0) return null
  return identity.team_id === requestedTeamId ? identity : null
}

export function teamBoardIdentitiesMatch(left, right) {
  if (!left || !right) return false
  return identityFields.every(field => left[field] === right[field])
}

function readEvidenceFact(fact) {
  if (!fact || typeof fact !== 'object' || Array.isArray(fact)) return null
  if (!recentUsageRestStates.has(fact.status)) return null
  return {
    value: Object.prototype.hasOwnProperty.call(fact, 'value') ? fact.value : null,
    status: fact.status,
    reasonCodes: Array.isArray(fact.reason_codes) ? [...fact.reason_codes] : [],
    mostRecentDate: fact.most_recent_date ?? null,
    threshold: fact.threshold ?? null,
  }
}

function readUsageWindow(window, key, label) {
  if (!window || typeof window !== 'object' || Array.isArray(window)) return null
  return {
    key,
    label,
    windowDays: window.window_days ?? null,
    startDate: window.start_date ?? null,
    throughDate: window.through_date ?? null,
    appearances: readEvidenceFact(window.appearances),
    pitches: readEvidenceFact(window.pitches),
    outs: readEvidenceFact(window.outs),
  }
}

function readUsagePitcher(pitcher) {
  if (!pitcher || typeof pitcher !== 'object' || Array.isArray(pitcher)) return null
  const windows = pitcher.windows || {}
  return {
    pitcherId: pitcher.pitcher_id ?? null,
    pitcherName: pitcher.pitcher_name ?? null,
    rosterState: pitcher.roster_state ?? null,
    windows: [
      readUsageWindow(windows.yesterday, 'yesterday', 'Yesterday'),
      readUsageWindow(windows.last_3_days, 'last_3_days', '3 Days'),
      readUsageWindow(windows.last_7_days, 'last_7_days', '7 Days'),
    ],
    daysSinceLastAppearance: readEvidenceFact(pitcher.days_since_last_appearance),
    pitchedYesterday: readEvidenceFact(pitcher.pitched_yesterday),
    backToBack: readEvidenceFact(pitcher.back_to_back),
    threeInFour: readEvidenceFact(pitcher.three_in_four),
    fourInSix: readEvidenceFact(pitcher.four_in_six),
    recentMultiInning: readEvidenceFact(pitcher.recent_multi_inning),
    highPitchOuting: readEvidenceFact(pitcher.high_pitch_outing),
  }
}

export function readTeamBoardRecentUsageRest(carrier, publicationIdentity) {
  if (
    !carrier
    || typeof carrier !== 'object'
    || Array.isArray(carrier)
    || carrier.contract !== TEAM_BOARD_RECENT_USAGE_REST_CONTRACT
    || !recentUsageRestStates.has(carrier.status)
    || !publicationIdentity
    || carrier.data_through !== publicationIdentity.represented_date
    || carrier.reference_date !== publicationIdentity.availability_reference_date
    || !Array.isArray(carrier.active_pitchers)
    || !Array.isArray(carrier.off_active_historical_contributors)
  ) return null

  return {
    contract: carrier.contract,
    status: carrier.status,
    reasonCode: carrier.reason_code ?? null,
    dataThrough: carrier.data_through,
    referenceDate: carrier.reference_date,
    windowPolicy: carrier.window_policy ?? null,
    populationBasis: carrier.population_basis ?? null,
    thresholds: carrier.thresholds && typeof carrier.thresholds === 'object'
      ? { ...carrier.thresholds }
      : {},
    activePitchers: carrier.active_pitchers.map(readUsagePitcher).filter(Boolean),
    offActiveHistoricalContributors: carrier.off_active_historical_contributors
      .map(readUsagePitcher)
      .filter(Boolean),
  }
}

export function isTeamBoardV2Payload(payload) {
  return Boolean(
    payload
    && typeof payload === 'object'
    && !Array.isArray(payload)
    && payload.capability === TEAM_BOARD_V2_CAPABILITY
    && payload.contract_version === TEAM_BOARD_V2_CONTRACT_VERSION
    && payload.team_state
    && typeof payload.team_state === 'object'
    && payload.active_bullpen
    && Array.isArray(payload.active_bullpen.arms)
    && payload.section_status
    && typeof payload.section_status === 'object'
  )
}

export function readTeamBoardV2(payload) {
  if (!isTeamBoardV2Payload(payload)) return null

  const recentUsageRest = readTeamBoardRecentUsageRest(
    payload.recent_usage_rest,
    payload.publication_identity,
  )
  return {
    capability: payload.capability,
    contractVersion: payload.contract_version,
    publicationIdentity: payload.publication_identity,
    team: payload.team,
    representedDate: payload.represented_date,
    freshness: payload.freshness,
    teamState: payload.team_state,
    summary: payload.summary,
    activeBullpen: payload.active_bullpen,
    recentUsage: payload.recent_usage,
    recentUsageRest,
    recentlyUsedArms: payload.recently_used_arms,
    offActiveCount: payload.off_active_count,
    restStatus: payload.rest_status,
    workloadOverview: payload.workload_overview,
    frozenTeamWorkload: readTeamBoardFrozenWorkload(payload.workload_overview?.frozen_team_workload, payload.publication_identity),
    rolesDeployment: payload.roles_deployment,
    frozenPublicDeployment: readTeamBoardFrozenDeployment(payload.roles_deployment?.frozen_public_deployment, payload.publication_identity),
    rotationImpact: payload.rotation_impact,
    frozenRotationGames: readTeamBoardFrozenRotationGames(payload.rotation_impact?.frozen_recent_games, payload.publication_identity),
    recentTransactions: readTeamBoardFrozenRosterTransactions(
      payload.recent_transactions, payload.publication_identity,
      payload.active_bullpen.arms.map(arm => arm.pitcher_id),
    ),
    rosterContext: payload.roster_context,
    recentReliefWork: payload.recent_relief_work,
    gameContext: payload.game_context,
    performance: payload.performance,
    whatChanged: readTeamBoardFrozenWhatChanged(payload.what_changed, payload.publication_identity),
    operatingState: payload.operating_state,
    sectionStatus: payload.section_status,
    limitations: payload.limitations,
  }
}

export function isTeamBoardCorePayload(payload) {
  return Boolean(
    payload
    && payload.capability === TEAM_BOARD_CORE_CAPABILITY
    && payload.contract_version === TEAM_BOARD_CORE_CONTRACT_VERSION
    && payload.publication_identity
    && payload.team_state
    && Array.isArray(payload.active_bullpen?.arms)
  )
}

export function isTeamBoardDetailsPayload(payload) {
  return Boolean(
    payload
    && payload.capability === TEAM_BOARD_DETAILS_CAPABILITY
    && payload.contract_version === TEAM_BOARD_DETAILS_CONTRACT_VERSION
    && payload.publication_identity
    && payload.section_status
  )
}

export function readTeamBoardDelivery(corePayload, detailsPayload = null) {
  if (!isTeamBoardCorePayload(corePayload)) return null
  const detailsValid = isTeamBoardDetailsPayload(detailsPayload)
    && teamBoardIdentitiesMatch(
      corePayload.publication_identity,
      detailsPayload.publication_identity,
    )
  const details = detailsValid ? detailsPayload : {}
  const recentUsageRest = detailsValid
    ? readTeamBoardRecentUsageRest(
        details.recent_usage_rest,
        corePayload.publication_identity,
      )
    : null
  const frozenTeamWorkload = detailsValid
    ? readTeamBoardFrozenWorkload(details.workload_overview?.frozen_team_workload, corePayload.publication_identity)
    : null
  const frozenPublicDeployment = detailsValid
    ? readTeamBoardFrozenDeployment(details.roles_deployment?.frozen_public_deployment, corePayload.publication_identity)
    : null
  const frozenPerformance = detailsValid
    ? readTeamBoardFrozenPerformance(details.performance, corePayload.publication_identity)
    : null
  const frozenRotationGames = detailsValid
    ? readTeamBoardFrozenRotationGames(details.rotation_impact?.frozen_recent_games, corePayload.publication_identity)
    : null
  const frozenRosterTransactions = detailsValid
    ? readTeamBoardFrozenRosterTransactions(
        details.recent_transactions, corePayload.publication_identity,
        corePayload.active_bullpen.arms.map(arm => arm.pitcher_id),
      )
    : null
  const frozenWhatChanged = detailsValid
    ? readTeamBoardFrozenWhatChanged(details.what_changed, corePayload.publication_identity)
    : null
  return {
    capability: corePayload.capability,
    contractVersion: corePayload.contract_version,
    publicationIdentity: corePayload.publication_identity,
    team: corePayload.team,
    representedDate: corePayload.represented_date,
    freshness: corePayload.freshness,
    teamState: corePayload.team_state,
    summary: corePayload.summary,
    activeBullpen: corePayload.active_bullpen,
    recentUsage: details.recent_usage || null,
    recentUsageRest,
    recentlyUsedArms: details.recently_used_arms || null,
    offActiveCount: corePayload.off_active_count,
    restStatus: corePayload.rest_status,
    workloadOverview: details.workload_overview || corePayload.workload_overview,
    frozenTeamWorkload,
    rolesDeployment: details.roles_deployment || corePayload.roles_deployment,
    frozenPublicDeployment,
    rotationImpact: corePayload.rotation_impact,
    frozenRotationGames,
    recentTransactions: frozenRosterTransactions,
    rosterContext: corePayload.roster_context,
    recentReliefWork: details.recent_relief_work || null,
    gameContext: details.game_context || null,
    performance: frozenPerformance,
    frozenPerformance,
    whatChanged: frozenWhatChanged,
    operatingState: corePayload.operating_state,
    sectionStatus: {
      ...(corePayload.section_status || {}),
      ...(detailsValid ? detailsPayload.section_status : {}),
    },
    detailsAttached: detailsValid,
    detailsRejected: Boolean(detailsPayload) && !detailsValid,
    recentUsageRestRejected: Boolean(details.recent_usage_rest) && !recentUsageRest,
    frozenTeamWorkloadRejected: Boolean(details.workload_overview?.frozen_team_workload) && !frozenTeamWorkload,
    frozenPublicDeploymentRejected: Boolean(details.roles_deployment?.frozen_public_deployment) && !frozenPublicDeployment,
    frozenPerformanceRejected: Boolean(details.performance) && !frozenPerformance,
    frozenRotationGamesRejected: Boolean(details.rotation_impact?.frozen_recent_games) && !frozenRotationGames,
    frozenRosterTransactionsRejected: Boolean(details.recent_transactions) && !frozenRosterTransactions,
    frozenWhatChangedRejected: Boolean(details.what_changed) && !frozenWhatChanged,
    limitations: corePayload.limitations,
  }
}
