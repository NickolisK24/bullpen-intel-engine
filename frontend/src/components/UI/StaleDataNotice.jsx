import { formatFreshnessDate } from './Freshness'

export default function StaleDataNotice({
  message,
  dataThrough,
  onRetry,
  compact = false,
}) {
  const formattedDate = formatFreshnessDate(dataThrough)
  const resolvedMessage = message || (
    formattedDate
      ? `showing last loaded data from ${formattedDate}.`
      : 'showing the last loaded data.'
  )

  return (
    <div
      className={`rounded-panel border border-brass/35 bg-brass/10 ${compact ? 'px-3 py-2' : 'mb-4 px-4 py-3'} font-mono text-[11px] leading-relaxed text-brass`}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="uppercase tracking-[0.18em]">Refresh delayed</span>
        <span className="text-chalk200">{resolvedMessage}</span>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="min-h-9 rounded-control border border-brass/35 bg-panel px-3 py-1 uppercase tracking-[0.18em] text-brass transition-colors hover:border-brass/70"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
