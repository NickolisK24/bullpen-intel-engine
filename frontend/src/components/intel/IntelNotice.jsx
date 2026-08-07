// Designed limited / quiet / unavailable states.
//
// A missing read is a real product state, not an absence. These notices give a
// withheld or quiet read the same structural weight as a published one — an
// eyebrow, a plain statement, and, when it helps, a next destination — so a
// reader can tell the difference between "nothing happened", "we are holding
// this read", and "something broke".
//
// Nothing here invents a reason. The caller supplies governed copy; this file
// only gives it a shape.

const TONE = {
  // A designed quiet day: the product looked and found nothing worth leading
  // with. Neutral, never alarming.
  quiet: {
    frame: 'border-line bg-panel',
    eyebrow: 'text-chalk500',
  },
  // A read BaseballOS is deliberately holding back because it cannot be
  // supported. Marked, but not styled as a failure.
  limited: {
    frame: 'border-brass/30 bg-panel',
    eyebrow: 'text-brass',
  },
  // Something could not be loaded. Retry is offered only when retry is real.
  unavailable: {
    frame: 'border-line-strong bg-panel',
    eyebrow: 'text-chalk400',
  },
}

export default function IntelNotice({
  eyebrow,
  title,
  message,
  tone = 'quiet',
  onRetry,
  retryLabel = 'Try again',
  children,
  className = '',
}) {
  const styles = TONE[tone] || TONE.quiet
  return (
    <div
      className={`rounded-panel border p-4 sm:p-6 ${styles.frame} ${className}`}
      role="status"
      aria-live="polite"
    >
      {eyebrow && (
        <p className={`font-mono text-[11px] uppercase tracking-[0.22em] ${styles.eyebrow}`}>
          {eyebrow}
        </p>
      )}
      {title && <h3 className={`bos-card-title ${eyebrow ? 'mt-2' : ''}`}>{title}</h3>}
      {message && <p className="bos-support mt-2 max-w-measure">{message}</p>}
      {children}
      {onRetry && (
        <button type="button" onClick={onRetry} className="bos-action bos-action--quiet mt-4">
          {retryLabel}
        </button>
      )}
    </div>
  )
}

// Skeleton that matches the final hierarchy rather than a spinner: the main
// claim never moves once the read arrives.
export function IntelSkeleton({ label, lines = 3, className = '' }) {
  return (
    <div
      className={`rounded-panel border border-line bg-panel p-4 sm:p-6 ${className}`}
      role="status"
      aria-live="polite"
    >
      <p className="bos-micro">{label}</p>
      <div className="mt-5 space-y-3" aria-hidden="true">
        <div className="h-6 w-3/4 animate-pulse rounded-edge bg-panel-2" />
        {Array.from({ length: Math.max(0, lines) }).map((unused, index) => (
          <div
            key={index}
            className="h-3 animate-pulse rounded-edge bg-panel-2"
            style={{ width: `${88 - index * 14}%` }}
          />
        ))}
      </div>
    </div>
  )
}
