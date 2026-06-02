import { useFetch } from '../../hooks/useFetch'
import { getSyncStatus } from '../../utils/api'
import { getSyncStatusView } from './syncStatusView'

const Pill = ({ dot, style = {}, title, children }) => (
  <div
    className="inline-flex items-center gap-2 px-3 py-1 rounded-md border text-[11px] font-mono max-w-full"
    style={{ borderColor: '#242b35', backgroundColor: 'rgba(26,31,38,0.4)', ...style }}
    title={title}
  >
    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: dot }} />
    {children}
  </div>
)

export function SyncStatusContent({ data, loading, error, now }) {
  if (loading) {
    return <Pill dot="#8899aa"><span className="animate-pulse">Checking sync…</span></Pill>
  }
  if (error) {
    return <Pill dot="#4a5568">Sync status unavailable</Pill>
  }

  const view = getSyncStatusView(data, now ? { now } : undefined)
  const title = [view.helper, ...view.limitations].filter(Boolean).join(' ')

  return (
    <Pill dot={view.dot} style={view.style} title={title || undefined}>
      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 min-w-0">
        <span>
          <span className="text-chalk600 normal-case">
            {view.syncLabel}{view.syncValue ? ':' : ''}
          </span>
          {view.syncValue && <span className="ml-1">{view.syncValue}</span>}
        </span>
        {view.dataLabel && view.dataValue && (
          <span>
            <span className="text-chalk600 normal-case">{view.dataLabel}:</span>
            <span className="ml-1">{view.dataValue}</span>
          </span>
        )}
        {view.refreshed && <span className="text-chalk600 normal-case">· {view.refreshed}</span>}
      </span>
    </Pill>
  )
}

export default function SyncStatus() {
  const { data, loading, error } = useFetch(getSyncStatus)
  return <SyncStatusContent data={data} loading={loading} error={error} />
}
