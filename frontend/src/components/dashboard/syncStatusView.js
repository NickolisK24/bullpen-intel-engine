const STALE_HOURS = 36
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

const failedStatuses = new Set(['failed', 'error'])
const successfulStatuses = new Set(['success', 'ok'])

export function getSyncStatusView(data, { now = Date.now() } = {}) {
  const status = data?.status
  const latestAttempt = data?.last_sync
  const successfulSync = data?.last_successful_sync || (successfulStatuses.has(status) ? latestAttempt : null)
  const dataThrough = fmtDataDate(data?.data?.latest_game_date)
  const logCount = data?.data?.game_logs
  const limitations = data?.freshness?.limitations || []

  if (failedStatuses.has(status)) {
    return {
      variant: 'failed',
      dot: '#ef4444',
      style: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5' },
      syncLabel: 'Last sync failed',
      syncValue: fmtSyncDate(latestAttempt) || 'Latest attempt failed',
      dataLabel: dataThrough ? 'Data Through' : null,
      dataValue: dataThrough,
      helper: data?.message || 'Latest sync attempt failed.',
      limitations,
    }
  }

  if (successfulSync) {
    const ageHours = (now - new Date(successfulSync).getTime()) / 3_600_000
    const stale = ageHours > STALE_HOURS
    return {
      variant: stale ? 'stale' : 'synced',
      dot: stale ? '#f5a623' : '#10b981',
      style: stale
        ? { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' }
        : { color: '#d1dce8' },
      syncLabel: 'Synced',
      syncValue: fmtSyncDate(successfulSync),
      dataLabel: dataThrough ? 'Data Through' : null,
      dataValue: dataThrough,
      refreshed: data?.pitchers_updated > 0 ? `${data.pitchers_updated.toLocaleString()} refreshed` : null,
      helper: stale ? 'Sync metadata is older than the freshness target.' : data?.freshness?.label,
      limitations,
    }
  }

  if (logCount > 0 && dataThrough) {
    return {
      variant: 'metadata_unavailable',
      dot: '#f5a623',
      style: { borderColor: '#f5a62355', backgroundColor: '#f5a62312', color: '#f5a623' },
      syncLabel: 'Sync metadata',
      syncValue: 'Unavailable',
      dataLabel: 'Data Through',
      dataValue: dataThrough,
      helper: 'Sync metadata unavailable; data coverage is based on game logs.',
      limitations,
    }
  }

  return {
    variant: 'empty',
    dot: '#4a5568',
    style: {},
    syncLabel: 'No data loaded',
    syncValue: null,
    dataLabel: null,
    dataValue: null,
    helper: 'No sync metadata or game logs are available.',
    limitations,
  }
}
