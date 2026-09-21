export const TEAM_BOARD_V2_CAPABILITY = 'team_board_v2'
export const TEAM_BOARD_V2_CONTRACT_VERSION = 'team-board-2.0.0'
export const TEAM_BOARD_CORE_CAPABILITY = 'team_board_answer_core'
export const TEAM_BOARD_CORE_CONTRACT_VERSION = 'team_board_answer_core_v1'
export const TEAM_BOARD_DETAILS_CAPABILITY = 'team_board_deferred_details'
export const TEAM_BOARD_DETAILS_CONTRACT_VERSION = 'team_board_deferred_details_v1'
export const TEAM_BOARD_RECENT_USAGE_REST_CONTRACT = 'team_board_recent_usage_rest_v1'
export const TEAM_BOARD_FROZEN_WORKLOAD_CONTRACT = 'team_board_workload_overview_v1'

const recentUsageRestStates = new Set(['complete', 'partial', 'unknown', 'unavailable'])
const workloadWindowKeys = [3, 7, 14, 30]
const workloadMetricKeys = ['pitches', 'appearances', 'outs']

const nonnegativeCount = value => Number.isSafeInteger(value) && value >= 0

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
    rotationImpact: payload.rotation_impact,
    recentTransactions: payload.recent_transactions,
    rosterContext: payload.roster_context,
    recentReliefWork: payload.recent_relief_work,
    gameContext: payload.game_context,
    performance: payload.performance,
    whatChanged: payload.what_changed,
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
    rotationImpact: corePayload.rotation_impact,
    recentTransactions: details.recent_transactions || null,
    rosterContext: corePayload.roster_context,
    recentReliefWork: details.recent_relief_work || null,
    gameContext: details.game_context || null,
    performance: details.performance || null,
    whatChanged: details.what_changed || null,
    operatingState: corePayload.operating_state,
    sectionStatus: {
      ...(corePayload.section_status || {}),
      ...(detailsValid ? detailsPayload.section_status : {}),
    },
    detailsAttached: detailsValid,
    detailsRejected: Boolean(detailsPayload) && !detailsValid,
    recentUsageRestRejected: Boolean(details.recent_usage_rest) && !recentUsageRest,
    frozenTeamWorkloadRejected: Boolean(details.workload_overview?.frozen_team_workload) && !frozenTeamWorkload,
    limitations: corePayload.limitations,
  }
}
