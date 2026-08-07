// Ambient trust presentation.
//
// Data authority: the governed freshness block already served with the page.
// This component renders supplied values only — it never derives a data-through
// date, never asserts coverage, and never claims verification the application
// did not supply. Every stamp disappears when its value is absent rather than
// rendering a placeholder.
//
// Trust is kept quiet on purpose: the Product Experience Standard's hierarchy
// is baseball first, receipt second, limitation third. A strip of stamps sits
// beside the claim it qualifies; it does not become an operations dashboard.

import { DataThroughStamp, LastSyncLabel, SlateDateStamp } from '../UI'

export function TrustStrip({
  dataThrough,
  dataThroughLabel = 'Data through',
  lastSync,
  lastSyncLabel = 'Last synced',
  slateDate,
  slateLabel = 'Tonight slate',
  children,
  className = '',
}) {
  const hasAny = Boolean(dataThrough || lastSync || slateDate || children)
  if (!hasAny) return null
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {slateDate && <SlateDateStamp date={slateDate} label={slateLabel} />}
      {dataThrough && <DataThroughStamp date={dataThrough} label={dataThroughLabel} />}
      {lastSync && <LastSyncLabel value={lastSync} label={lastSyncLabel} />}
      {children}
    </div>
  )
}

// One labelled fact inside the edition masthead or a trust panel. Renders
// nothing at all when the application has no value to show, so an unavailable
// field never becomes an empty slot or a guessed default.
export function TrustFact({ label, value, detail }) {
  if (!value) return null
  return (
    <div className="min-w-0">
      <dt className="bos-micro">{label}</dt>
      <dd className="mt-1.5 min-w-0 break-words font-mono text-[13px] leading-snug text-chalk100">
        {value}
      </dd>
      {detail && <p className="bos-meta mt-1 normal-case">{detail}</p>}
    </div>
  )
}

export default TrustStrip
