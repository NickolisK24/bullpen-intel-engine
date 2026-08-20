export function SkeletonBlock({ className = '' }) {
  return <span className={`foundation-skeleton block ${className}`.trim()} aria-hidden="true" />
}

export function TeamBoardSkeleton({ message = 'Building current bullpen board...' }) {
  return (
    <section
      className="foundation-panel"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={message}
      data-testid="team-board-skeleton"
    >
      <span className="sr-only">{message}</span>
      <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-start tablet:justify-between">
        <div className="min-w-0 flex-1">
          <SkeletonBlock className="h-3 w-24" />
          <SkeletonBlock className="mt-row h-8 w-full max-w-sm" />
          <SkeletonBlock className="mt-meta h-4 w-full max-w-xl" />
        </div>
        <SkeletonBlock className="h-8 w-28 shrink-0" />
      </div>

      <div className="mt-section grid min-w-0 grid-cols-1 gap-pair tablet:grid-cols-2">
        <SkeletonBlock className="h-24 w-full" />
        <SkeletonBlock className="h-24 w-full" />
      </div>

      <div className="mt-section border-t border-dirt" aria-hidden="true">
        {[0, 1, 2].map(index => (
          <div key={index} className="active-arm-row">
            <div>
              <SkeletonBlock className="h-5 w-40 max-w-full" />
              <SkeletonBlock className="mt-meta h-3 w-24 max-w-full" />
            </div>
            <SkeletonBlock className="h-7 w-24 max-w-full" />
            <SkeletonBlock className="h-4 w-full max-w-48" />
            <SkeletonBlock className="h-11 w-24 max-w-full" />
          </div>
        ))}
      </div>
    </section>
  )
}
