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
const staleStates = new Set(['stale', 'historical'])
const missingStates = new Set(['missing', 'metadata_unavailable', 'unknown'])

export function getSyncStatusView(data, { now = Date.now(), freshnessAuthority } = {}) {
  const status = data?.status
  const latestAttempt = data?.last_checked || data?.last_sync
  const successfulSync = data?.last_successful_sync || (successfulStatuses.has(status) ? data?.last_sync : null)
  const rawDataThroughSource = data?.data_through || data?.data?.latest_game_date
  const hasFreshnessAuthority = freshnessAuthority !== undefined
  const dataThroughSource = hasFreshnessAuthority
    ? freshnessAuthority?.data_through
    : rawDataThroughSource
  const dataThrough = formatDateOnly(dataThroughSource, { month: 'long' })
  const checkedDataThrough = formatDateOnly(rawDataThroughSource, { month: 'long' })
  const dataCoverageLine = completedGamesDataLine(dataThroughSource)
  const lastCheckedValue = formatUtcDateTimeEt(latestAttempt, { includeDate: false })
  const lastDataUpdateValue = formatUtcDateTimeEt(successfulSync, { includeDate: false })
  const logCount = data?.data?.game_logs
  const freshness = data?.freshness || {}
  const limitations = freshness.limitations || []
  const reasonCodes = Array.isArray(freshness.reason_codes) ? freshness.reason_codes : []
  const freshnessState = freshness.freshness_state
    || freshness.state
    || (freshness.is_current === true ? 'current' : null)
  const stale = freshness.is_stale === true
    || staleStates.has(String(freshnessState || '').toLowerCase())
    || reasonCodes.includes('workload_data_outside_active_window')
  const missing = missingStates.has(String(freshnessState || '').toLowerCase())
  const coverageValue = data?.pitchers_updated > 0
    ? `${data.pitchers_updated.toLocaleString()} Pitchers Refreshed`
    : null
  const checkedDateAheadOfPublic = hasFreshnessAuthority
    && dataThroughSource
    && rawDataThroughSource
    && rawDataThroughSource > dataThroughSource
  const authorityLabel = freshnessAuthority?.label
  const freshnessHelper = (baseHelper, { limited = false } = {}) => {
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
    const limited = stale || missing || freshness.is_current === false || limitations.length > 0
    return {
      variant: stale ? 'stale' : (limited ? 'limited' : 'synced'),
      healthLabel: stale ? 'Not Current' : (limited ? 'Limited' : 'Healthy'),
      dot: stale || limited ? '#f5a623' : '#10b981',
      style: stale
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
        stale
          ? (freshness.label || 'Workload data is outside the active freshness window.')
          : freshness.label,
        { limited },
      ),
      limitations,
      reasonCodes,
      freshnessState,
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
