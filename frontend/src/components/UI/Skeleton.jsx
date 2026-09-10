export function SkeletonBlock({ className = '' }) {
  return <span className={`foundation-skeleton block ${className}`.trim()} aria-hidden="true" />
}

export function TeamBoardSkeleton({ message = 'Building current bullpen board...' }) {
  return (
    <section
      className="team-board-loading-continuity min-w-0 pb-section-lg"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={message}
      data-testid="team-board-skeleton"
    >
      <span className="sr-only">{message}</span>
      <div aria-hidden="true">
        <div
          className="foundation-panel -mx-4 overflow-hidden border-y border-line-default bg-surface-raised/55 px-4 py-5 md:-mx-6 md:px-6 md:py-6 xl:-mx-8 xl:px-8 desktop:mx-0 desktop:rounded-md desktop:border desktop:px-7 desktop:py-7"
          data-testid="team-board-loading-answer"
        >
          <div className="flex min-w-0 flex-col gap-panel tablet:flex-row tablet:items-end tablet:justify-between">
            <div className="min-w-0 flex-1">
              <SkeletonBlock className="h-3 w-24" />
              <SkeletonBlock className="mt-meta h-8 w-full max-w-sm" />
            </div>
            <div className="flex min-w-0 flex-col gap-2 tablet:items-end">
              <SkeletonBlock className="h-11 w-full max-w-56 tablet:w-56" />
              <SkeletonBlock className="h-4 w-24" />
            </div>
          </div>

          <div className="mt-section min-w-0 desktop:grid desktop:grid-cols-[minmax(0,1fr)_minmax(16rem,0.42fr)] desktop:gap-section-lg">
            <div className="min-w-0">
              <SkeletonBlock className="h-5 w-full max-w-2xl" />
              <SkeletonBlock className="mt-meta h-5 w-4/5 max-w-xl" />
            </div>
            <div className="mt-section border-t border-line-subtle pt-panel desktop:mt-0 desktop:border-l desktop:border-t-0 desktop:pl-section desktop:pt-0">
              <SkeletonBlock className="h-3 w-36" />
              <SkeletonBlock className="mt-meta h-3 w-48 max-w-full" />
            </div>
          </div>
        </div>

        <div
          className="foundation-panel -mx-4 border-b border-line-default bg-surface-nav/45 px-4 pb-5 pt-4 md:-mx-6 md:px-6 xl:-mx-8 xl:px-8 desktop:mx-0 desktop:mt-2 desktop:rounded-md desktop:border desktop:px-6 desktop:py-5"
          data-testid="team-board-loading-summary"
        >
          <div className="flex items-center justify-between gap-panel">
            <SkeletonBlock className="h-3 w-32" />
            <SkeletonBlock className="hidden h-3 w-40 tablet:block" />
          </div>
          <div className="mt-panel grid grid-cols-2 gap-pair border-t border-line-subtle pt-panel tablet:grid-cols-3 desktop:grid-cols-5">
            {[0, 1, 2, 3, 4].map(index => (
              <div key={index} className={index === 4 ? 'col-span-2 tablet:col-span-1' : ''}>
                <SkeletonBlock className="h-3 w-20 max-w-full" />
                <SkeletonBlock className="mt-meta h-7 w-12" />
                <SkeletonBlock className="mt-meta h-3 w-24 max-w-full" />
              </div>
            ))}
          </div>
        </div>

        <div
          className="foundation-section mt-section-lg border-t border-line-strong pt-section-lg"
          data-testid="team-board-loading-active-bullpen"
        >
          <div className="mb-panel border-b border-line-default pb-panel">
            <SkeletonBlock className="h-3 w-28" />
            <SkeletonBlock className="mt-meta h-6 w-44 max-w-full" />
            <SkeletonBlock className="mt-meta h-4 w-full max-w-lg" />
          </div>
          <div className="overflow-hidden rounded-sm border border-line-default bg-surface-raised/25 px-panel">
            {[0, 1, 2, 3].map(index => (
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
        </div>

        <div
          className="mt-section-lg border-y border-line-subtle bg-surface-nav/25 px-panel py-section tablet:rounded-sm tablet:border"
          data-testid="team-board-loading-continuation"
        >
          <div className="grid min-w-0 grid-cols-1 gap-section tablet:grid-cols-2">
            {[0, 1].map(index => (
              <div key={index} className="min-w-0">
                <SkeletonBlock className="h-3 w-32" />
                <SkeletonBlock className="mt-panel h-4 w-full max-w-sm" />
                <SkeletonBlock className="mt-meta h-4 w-3/4 max-w-xs" />
                <SkeletonBlock className="mt-panel h-20 w-full" />
              </div>
            ))}
          </div>
          <SkeletonBlock className="mt-section h-3 w-52 max-w-full" />
        </div>
      </div>
    </section>
  )
}
