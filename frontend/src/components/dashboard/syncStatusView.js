import {
  formatDateOnly,
  formatUtcDateTimeEt,
} from '../../utils/dateDisplay'

export const fmtSyncDate = (iso) => {
  return formatUtcDateTimeEt(iso, { includeDate: true })
}

export const fmtDataDate = (ymd) => {
  return formatDateOnly(ymd, { month: 'short' })
}

export const completedGamesDataLine = (ymd) => {
  const formatted = fmtDataDate(ymd)
  return formatted ? `Updated after completed games through ${formatted}` : null
}

const failedStatuses = new Set(['failed', 'error'])
const successfulStatuses = new Set(['success', 'ok'])
const currentStates = new Set(['current', 'fresh', 'healthy', 'success', 'ok'])
const staleStates = new Set(['stale', 'historical'])
const missingStates = new Set(['missing', 'metadata_unavailable', 'unknown'])
const limitedStates = new Set(['limited', 'partial', 'degraded', 'incomplete'])

function normalizedKey(value) {
  return String(value || '').trim().toLowerCase().replace(/[-\s]+/g, '_')
}

function firstPresent(...values) {
  return values.find(value => value !== undefined && value !== null && value !== '')
}

function boolValue(value) {
  if (value === true || value === false) return value
  if (typeof value === 'string') {
    const normalized = normalizedKey(value)
    if (normalized === 'true') return true
    if (normalized === 'false') return false
  }
  return null
}

export function freshnessDataThrough(freshness) {
  if (!freshness || typeof freshness !== 'object') return null
  return firstPresent(
    freshness.data_through,
    freshness.dataThrough,
    freshness.latest_workload_date,
    freshness.latestWorkloadDate,
  ) || null
}

function freshnessState(freshness) {
  if (!freshness || typeof freshness !== 'object') return ''
  return normalizedKey(firstPresent(
    freshness.freshness_state,
    freshness.freshnessState,
    freshness.state,
    freshness.status,
    freshness.data_status,
    freshness.dataStatus,
  ))
}

function freshnessSyncStatus(freshness) {
  if (!freshness || typeof freshness !== 'object') return ''
  return normalizedKey(firstPresent(
    freshness.sync_status,
    freshness.syncStatus,
    freshness.latest_sync_status,
    freshness.latestSyncStatus,
    freshness.current_sync_status,
    freshness.currentSyncStatus,
  ))
}

function freshnessFlag(freshness, ...keys) {
  if (!freshness || typeof freshness !== 'object') return null
  for (const key of keys) {
    const value = boolValue(freshness[key])
    if (value !== null) return value
  }
  return null
}

function freshnessIsSample(freshness) {
  if (!freshness || typeof freshness !== 'object') return false
  const state = freshnessState(freshness)
  return freshnessFlag(freshness, 'sample', 'demo', 'is_demo', 'isDemo', 'non_live', 'nonLive') === true
    || freshnessFlag(freshness, 'is_live', 'isLive') === false
    || state === 'sample'
    || state === 'sample_state'
    || state === 'demo'
    || state === 'demo_state'
}

function freshnessIsPublishable(freshness) {
  if (!freshness || typeof freshness !== 'object') return false
  const coverage = freshness.slate_coverage || freshness.slateCoverage || {}
  const completeEnough = freshnessFlag(freshness, 'complete_enough_to_publish', 'completeEnoughToPublish')
  const validationsPassed = freshnessFlag(freshness, 'validations_passed', 'validationsPassed')
  const coverageComplete = freshnessFlag(coverage, 'complete_enough_to_publish', 'completeEnoughToPublish')
  const coverageValidated = freshnessFlag(coverage, 'validations_passed', 'validationsPassed')

  return completeEnough === true
    && validationsPassed !== false
    && coverageComplete !== false
    && coverageValidated !== false
}

export function freshnessIsCurrent(freshness) {
  if (!freshness || typeof freshness !== 'object') return false
  if (!freshnessDataThrough(freshness)) return false
  if (freshnessIsSample(freshness)) return false
  if (freshnessFlag(freshness, 'fail_closed', 'failClosed') === true) return false

  const state = freshnessState(freshness)
  const syncStatus = freshnessSyncStatus(freshness)
  const staleFlag = freshnessFlag(freshness, 'is_stale', 'isStale', 'stale')
  const currentFlag = freshnessFlag(freshness, 'is_current', 'isCurrent', 'current')
  const publishable = freshnessIsPublishable(freshness)

  if (failedStatuses.has(syncStatus)) return false
  if (publishable) return true
  if (currentFlag === false || staleFlag === true) return false
  if (staleStates.has(state) || missingStates.has(state) || limitedStates.has(state)) return false
  if (currentFlag === true) return true
  return currentStates.has(state) || successfulStatuses.has(syncStatus)
}

export function getSyncStatusView(data, { now = Date.now(), freshnessAuthority } = {}) {
  const status = data?.status
  const latestAttempt = data?.last_checked || data?.last_sync
  const successfulSync = data?.last_successful_sync || (successfulStatuses.has(status) ? data?.last_sync : null)
  const rawDataThroughSource = data?.data_through || data?.data?.latest_game_date
  const hasFreshnessAuthority = freshnessAuthority !== undefined
  const dataThroughSource = hasFreshnessAuthority
    ? freshnessDataThrough(freshnessAuthority)
    : rawDataThroughSource
  const dataThrough = formatDateOnly(dataThroughSource, { month: 'long' })
  const checkedDataThrough = formatDateOnly(rawDataThroughSource, { month: 'long' })
  const dataCoverageLine = completedGamesDataLine(dataThroughSource)
  const lastCheckedValue = formatUtcDateTimeEt(latestAttempt, { includeDate: false })
  const lastDataUpdateValue = formatUtcDateTimeEt(successfulSync, { includeDate: false })
  const logCount = data?.data?.game_logs
  const freshness = data?.freshness || {}
  const limitations = Array.isArray(freshness.limitations) ? freshness.limitations : []
  const reasonCodes = Array.isArray(freshness.reason_codes)
    ? freshness.reason_codes
    : (Array.isArray(freshness.reasonCodes) ? freshness.reasonCodes : [])
  const freshnessState = firstPresent(
    freshness.freshness_state,
    freshness.freshnessState,
    freshness.state,
    freshness.status,
  )
    || (freshness.is_current === true ? 'current' : null)
  const normalizedFreshnessState = normalizedKey(freshnessState)
  const stale = freshnessFlag(freshness, 'is_stale', 'isStale', 'stale') === true
    || staleStates.has(normalizedFreshnessState)
    || reasonCodes.includes('workload_data_outside_active_window')
  const missing = missingStates.has(normalizedFreshnessState)
  const coverageValue = data?.pitchers_updated > 0
    ? `${data.pitchers_updated.toLocaleString()} Pitchers Refreshed`
    : null
  const checkedDateAheadOfPublic = hasFreshnessAuthority
    && dataThroughSource
    && rawDataThroughSource
    && rawDataThroughSource > dataThroughSource
  const authorityIsCurrent = freshnessIsCurrent(freshnessAuthority)
  const rawAuthorityLabel = freshnessAuthority?.label || freshnessAuthority?.message
  const authorityLabel = authorityIsCurrent
    ? (
        rawAuthorityLabel && !/incomplete and is not publishable/i.test(rawAuthorityLabel)
          ? rawAuthorityLabel
          : (dataThrough ? `Public bullpen data is current through ${dataThrough}.` : null)
      )
    : rawAuthorityLabel
  const freshnessHelper = (baseHelper, { limited = false } = {}) => {
    if (authorityIsCurrent) {
      return authorityLabel
    }

    if (!checkedDateAheadOfPublic || !dataThrough || !checkedDataThrough) {
      return hasFreshnessAuthority && !limited && authorityLabel
        ? authorityLabel
        : baseHelper
    }

    if (limited) {
      return [
        baseHelper,
        `Public bullpen data remains through ${dataThrough}.`,
        `Latest checked baseball date ${checkedDataThrough} is not publishable yet.`,
      ].filter(Boolean).join(' ')
    }

    return authorityLabel || `Public bullpen data is through ${dataThrough}.`
  }

  if (failedStatuses.has(status)) {
    return {
      variant: stale ? 'stale' : 'failed',
      healthLabel: stale ? 'Not Current' : 'Limited',
      dot: stale ? '#f5a623' : '#ef4444',
      style: stale
        ? { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' }
        : { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5' },
      syncLabel: 'Last sync failed',
      syncValue: fmtSyncDate(latestAttempt) || 'Latest attempt failed',
      lastCheckedLabel: 'Last checked',
      lastCheckedValue,
      lastDataUpdateLabel: 'Last data update',
      lastDataUpdateValue,
      dataLabel: dataThrough ? 'Data through' : null,
      dataValue: dataThrough,
      dataCoverageLine,
      coverageValue,
      helper: freshnessHelper(
        stale
          ? (freshness.label || data?.message || 'Latest sync attempt failed.')
          : (data?.message || 'Latest sync attempt failed.'),
        { limited: true },
      ),
      limitations,
      reasonCodes,
      freshnessState,
    }
  }

  if (successfulSync) {
    const rawLimited = stale || missing || freshnessFlag(freshness, 'is_current', 'isCurrent', 'current') === false || limitations.length > 0
    const limited = authorityIsCurrent ? false : rawLimited
    const displayStale = authorityIsCurrent ? false : stale
    return {
      variant: displayStale ? 'stale' : (limited ? 'limited' : 'synced'),
      healthLabel: displayStale ? 'Not Current' : (limited ? 'Limited' : 'Healthy'),
      dot: displayStale || limited ? '#f5a623' : '#10b981',
      style: displayStale
        ? { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' }
        : limited
          ? { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' }
        : { color: '#d1dce8' },
      syncLabel: 'Last data update',
      syncValue: fmtSyncDate(successfulSync),
      lastCheckedLabel: 'Last checked',
      lastCheckedValue,
      lastDataUpdateLabel: 'Last data update',
      lastDataUpdateValue,
      dataLabel: dataThrough ? 'Data through' : null,
      dataValue: dataThrough,
      dataCoverageLine,
      coverageValue,
      refreshed: coverageValue,
      helper: freshnessHelper(
        displayStale
          ? (freshness.label || 'Workload data is outside the active freshness window.')
          : freshness.label,
        { limited },
      ),
      limitations: authorityIsCurrent ? [] : limitations,
      reasonCodes: authorityIsCurrent ? [] : reasonCodes,
      freshnessState: authorityIsCurrent ? 'current' : freshnessState,
    }
  }

  if (logCount > 0 && dataThrough) {
    return {
      variant: 'metadata_unavailable',
      healthLabel: 'Limited',
      dot: '#f5a623',
      style: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' },
      syncLabel: 'Sync metadata',
      syncValue: 'Unavailable',
      lastCheckedLabel: 'Last checked',
      lastCheckedValue,
      lastDataUpdateLabel: 'Last data update',
      lastDataUpdateValue,
      dataLabel: 'Data through',
      dataValue: dataThrough,
      dataCoverageLine,
      coverageValue,
      helper: 'Sync metadata unavailable; data coverage is based on game logs.',
      limitations,
      reasonCodes,
      freshnessState,
    }
  }

  return {
    variant: 'empty',
    healthLabel: 'Limited',
    dot: '#4a5568',
    style: {},
    syncLabel: 'No data loaded',
    syncValue: null,
    lastCheckedLabel: 'Last checked',
    lastCheckedValue,
    lastDataUpdateLabel: 'Last data update',
    lastDataUpdateValue,
    dataLabel: null,
    dataValue: null,
    dataCoverageLine,
    coverageValue,
    helper: 'No sync metadata or game logs are available.',
    limitations,
    reasonCodes,
    freshnessState,
  }
}
