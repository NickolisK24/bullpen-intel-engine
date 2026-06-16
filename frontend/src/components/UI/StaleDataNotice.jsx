export default function StaleDataNotice({
  message = 'Last refresh failed; showing the last loaded data.',
  onRetry,
  compact = false,
}) {
  return (
    <div
      className={`rounded border border-amber/35 bg-amber/10 ${compact ? 'px-3 py-2' : 'mb-4 px-4 py-3'} font-mono text-[11px] leading-relaxed text-amber`}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="uppercase tracking-widest">Refresh delayed</span>
        <span className="text-chalk200">{message}</span>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded border border-amber/35 bg-dugout px-2 py-1 uppercase tracking-widest text-amber transition-colors hover:border-amber/60 hover:bg-amber/15"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
