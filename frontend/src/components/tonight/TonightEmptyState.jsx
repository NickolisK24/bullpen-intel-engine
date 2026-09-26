import { useRef, useState } from 'react'
import { SkeletonBlock } from '../UI'
import { TONIGHT_COPY } from './tonightView'

function CardSkeleton() {
  return (
    <div className="card min-w-0 p-3 sm:p-4">
      <SkeletonBlock className="h-5 w-3/4" />
      <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 tablet:grid-cols-2">
        {[0, 1].map(side => (
          <div key={side}>
            <SkeletonBlock className="h-3 w-20" />
            <SkeletonBlock className="mt-1.5 h-8 w-32" />
            <SkeletonBlock className="mt-2 h-3 w-36" />
            <SkeletonBlock className="mt-2.5 h-3 w-16" />
            <SkeletonBlock className="mt-1 h-4 w-44 max-w-full" />
            <SkeletonBlock className="mt-1 h-4 w-40 max-w-full" />
          </div>
        ))}
      </div>
      <SkeletonBlock className="mt-3 h-10 w-full" />
      <SkeletonBlock className="mt-3 h-11 w-64 max-w-full" />
    </div>
  )
}

// Shapes only: no numbers, names or labels, so nothing reads as baseball data.
export function TonightLoading() {
  return (
    <div role="status" aria-busy="true" data-testid="tonight-loading">
      <span className="sr-only">{TONIGHT_COPY.loading}</span>
      <div aria-hidden="true">
        <SkeletonBlock className="mt-section h-32 w-full" />
        <SkeletonBlock className="mt-section h-3 w-28" />
        <div className="mt-3 grid grid-cols-1 gap-3 desktop:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    </div>
  )
}

// Quiet day and unavailable are calm trust states (status). A failed request
// is an error (alert) with one retry action that cannot fire twice.
export default function TonightEmptyState({ variant, detail = null, onRetry = null }) {
  // The ref blocks a second activation synchronously (two clicks in one task
  // both see the pre-render state); the state disables the button visually.
  const retryStarted = useRef(false)
  const [retrying, setRetrying] = useState(false)
  if (variant === 'error') {
    return (
      <section
        className="mt-section border border-l-4 border-dirt border-l-amber bg-dugout p-4"
        role="alert"
        data-testid="tonight-error"
      >
        <h2 className="font-display text-2xl leading-tight tracking-wide text-chalk100">{TONIGHT_COPY.error}</h2>
        {onRetry && (
          <button
            type="button"
            disabled={retrying}
            onClick={() => {
              if (retryStarted.current) return
              retryStarted.current = true
              setRetrying(true)
              onRetry()
            }}
            className="mt-3 inline-flex min-h-11 items-center rounded border border-amber/50 px-4 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60 disabled:opacity-60"
          >
            Try again
          </button>
        )}
      </section>
    )
  }
  const title = variant === 'quiet' ? TONIGHT_COPY.quiet : TONIGHT_COPY.unavailable
  return (
    <section
      className="mt-section border border-dirt bg-dugout/60 px-4 py-5"
      role="status"
      data-testid={`tonight-${variant === 'quiet' ? 'quiet' : 'unavailable'}`}
    >
      <h2 className="text-lg leading-snug text-chalk100 sm:text-xl">{title}</h2>
      {detail && <p className="mt-2 font-mono text-xs uppercase tracking-wider text-chalk300">{detail}</p>}
    </section>
  )
}
