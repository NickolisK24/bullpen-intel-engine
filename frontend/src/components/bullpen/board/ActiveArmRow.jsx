import SemanticLabel from '../../UI/SemanticLabel'
import { SkeletonBlock } from '../../UI/Skeleton'

function Fact({ label, value }) {
  return (
    <div className="min-w-0">
      <dt className="type-overline">{label}</dt>
      <dd className="type-data active-arm-row__text mt-meta">{value || '—'}</dd>
    </div>
  )
}

export function ActiveArmRowSkeleton() {
  return (
    <div className="active-arm-row" role="status" aria-label="Loading reliever record" aria-busy="true">
      <div>
        <SkeletonBlock className="h-5 w-40 max-w-full" />
        <SkeletonBlock className="mt-meta h-3 w-24 max-w-full" />
      </div>
      <SkeletonBlock className="h-7 w-24 max-w-full" />
      <SkeletonBlock className="h-4 w-full max-w-48" />
      <SkeletonBlock className="h-11 w-24 max-w-full" />
    </div>
  )
}

export default function ActiveArmRow({
  name,
  roleLabel,
  readLabel,
  readTone = 'neutral',
  lastUsed,
  recentWorkload,
  pattern,
  href,
  actionLabel = 'View pitcher',
  partialMessage,
  loading = false,
}) {
  if (loading) return <ActiveArmRowSkeleton />

  return (
    <article className="active-arm-row" aria-label={`${name || 'Reliever'} record`}>
      <div className="min-w-0">
        <h3 className="type-section-title active-arm-row__text">{name || 'Reliever'}</h3>
        <p className="type-metadata active-arm-row__text mt-meta">{roleLabel || '—'}</p>
      </div>

      <div className="min-w-0">
        <div className="type-overline mb-meta">Current Arm Read</div>
        <SemanticLabel label={readLabel || '—'} tone={readTone} />
      </div>

      <dl className="grid min-w-0 grid-cols-2 gap-pair">
        <Fact label="Last Used" value={lastUsed} />
        <Fact label="Recent Workload" value={recentWorkload} />
        {pattern && <Fact label="Multi-Day Pattern" value={pattern} />}
      </dl>

      <div className="min-w-0">
        {href && (
          <a
            href={href}
            className="inline-flex min-h-11 w-full items-center justify-center rounded-sm border border-signal/50 px-3 py-2 font-mono text-metadata text-signal transition-colors hover:border-signal hover:bg-signal/10 tablet:w-auto"
          >
            {actionLabel}<span aria-hidden="true" className="ml-2">→</span>
          </a>
        )}
        {partialMessage && (
          <p className="type-metadata active-arm-row__text mt-meta" role="status">
            {partialMessage}
          </p>
        )}
      </div>
    </article>
  )
}
