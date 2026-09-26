import { SkeletonBlock } from '../UI'
import { TONIGHT_COPY } from './tonightView'

const VARIANTS = {
  quiet: { title: TONIGHT_COPY.quiet, role: 'status' },
  unavailable: { title: TONIGHT_COPY.unavailable, role: 'status' },
  error: { title: TONIGHT_COPY.error, role: 'alert' },
}

export function TonightLoading() {
  return (
    <div role="status" aria-live="polite" aria-busy="true" data-testid="tonight-loading">
      <span className="sr-only">{TONIGHT_COPY.loading}</span>
      <div aria-hidden="true">
        <SkeletonBlock className="h-4 w-40" />
        <SkeletonBlock className="mt-2 h-3 w-64 max-w-full" />
        <SkeletonBlock className="mt-section h-24 w-full" />
        <div className="mt-section grid grid-cols-1 gap-3 desktop:grid-cols-2">
          <SkeletonBlock className="h-56 w-full" />
          <SkeletonBlock className="h-56 w-full" />
        </div>
      </div>
    </div>
  )
}

export default function TonightEmptyState({ variant, detail = null, onRetry = null }) {
  const config = VARIANTS[variant] || VARIANTS.unavailable
  return (
    <section
      className="mt-section border border-dirt bg-dugout p-4"
      role={config.role}
      aria-live={config.role === 'alert' ? undefined : 'polite'}
      data-testid={`tonight-${variant}`}
    >
      <h2 className="font-display text-2xl leading-tight tracking-wide text-chalk100">{config.title}</h2>
      {detail && <p className="mt-2 font-mono text-xs uppercase tracking-wider text-chalk300">{detail}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 inline-flex min-h-11 items-center rounded border border-amber/50 px-4 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
        >
          Try again
        </button>
      )}
    </section>
  )
}
