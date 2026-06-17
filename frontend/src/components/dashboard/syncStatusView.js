const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November', 'December']

export const fmtSyncDate = (iso) => {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return `${MONTHS_LONG[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}

export const fmtDataDate = (ymd) => {
  if (!ymd) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd)
  if (!m) return null
  const [, y, mm, dd] = m
  return `${MONTHS_SHORT[Number(mm) - 1]} ${Number(dd)}, ${y}`
}

export const completedGamesDataLine = (ymd) => {
  const formatted = fmtDataDate(ymd)
  return formatted ? `Built from completed games through ${formatted}` : null
}

const failedStatuses = new Set(['failed', 'error'])
const successfulStatuses = new Set(['success', 'ok'])
const staleStates = new Set(['stale', 'historical'])
const missingStates = new Set(['missing', 'metadata_unavailable', 'unknown'])

export function getSyncStatusView(data, { now = Date.now(), freshnessAuthority } = {}) {
  const status = data?.status
  const latestAttempt = data?.last_sync
  const successfulSync = data?.last_successful_sync || (successfulStatuses.has(status) ? latestAttempt : null)
  const dataThroughSource = freshnessAuthority === undefined
    ? data?.data?.latest_game_date
    : freshnessAuthority?.data_through
  const dataThrough = completedGamesDataLine(dataThroughSource)
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
      dataLabel: dataThrough ? 'Data coverage' : null,
      dataValue: dataThrough,
      coverageValue,
      helper: stale
        ? (freshness.label || data?.message || 'Latest sync attempt failed.')
        : (data?.message || 'Latest sync attempt failed.'),
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
      syncLabel: 'Last synced',
      syncValue: fmtSyncDate(successfulSync),
      dataLabel: dataThrough ? 'Data coverage' : null,
      dataValue: dataThrough,
      coverageValue,
      refreshed: coverageValue,
      helper: stale
        ? (freshness.label || 'Workload data is outside the active freshness window.')
        : freshness.label,
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
      dataLabel: 'Data coverage',
      dataValue: dataThrough,
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
    dataLabel: null,
    dataValue: null,
    coverageValue,
    helper: 'No sync metadata or game logs are available.',
    limitations,
    reasonCodes,
    freshnessState,
  }
}
