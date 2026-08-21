import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'

export const PERFORMANCE_UNAVAILABLE_MESSAGE = 'A governed active-bullpen performance read is not available.'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null

function PerformanceSkeleton() {
  return (
    <section className="foundation-section min-w-0" aria-labelledby="performance-title" aria-busy="true" data-testid="performance-skeleton">
      <h2 id="performance-title" className="type-section-title">Performance</h2>
      <span className="sr-only">Loading performance context.</span>
      <SkeletonBlock className="mt-panel h-16 w-full" />
    </section>
  )
}

export default function TeamBoardPerformance({ read, loading = false, error = null, onRetry }) {
  if (loading) return <PerformanceSkeleton />

  const performance = read?.performance
  const status = read?.sectionStatus?.performance
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const metrics = Array.isArray(performance?.metrics)
    ? performance.metrics.filter(metric => textValue(metric?.label) && textValue(metric?.value))
    : []
  const metricColumns = metrics.length > 1 ? 'grid-cols-2' : 'grid-cols-1'
  const summary = textValue(performance?.summary)
  const sampleSummary = textValue(performance?.sample_summary)
  const limitation = (Array.isArray(performance?.limitations) ? performance.limitations : [])
    .find(value => textValue(value))
  const hasGovernedContent = metrics.length > 0 || Boolean(summary)

  return (
    <section className="foundation-section min-w-0" aria-labelledby="performance-title" data-testid="team-board-performance">
      <header className="mb-panel border-b border-line-subtle pb-panel">
        <div className="type-overline text-text-tertiary">Supporting context</div>
        <h2 id="performance-title" className="type-section-title mt-meta">Performance</h2>
        <p className="type-metadata mt-meta max-w-reading text-text-tertiary">Supporting context for the current active bullpen.</p>
      </header>

      {error ? (
        <SectionState status="error" title="Performance unavailable" message="Current performance context could not be loaded." onRetry={onRetry} />
      ) : !read || !performance || statusName === 'unavailable' || !hasGovernedContent ? (
        <SectionState status="unavailable" title="Performance unavailable" message={PERFORMANCE_UNAVAILABLE_MESSAGE} onRetry={!read ? onRetry : undefined} />
      ) : (
        <>
          {metrics.length > 0 ? (
            <dl className={`grid ${metricColumns} gap-px overflow-hidden rounded-sm border border-line-subtle bg-line-subtle`} aria-label="Active bullpen performance metrics">
              {metrics.map(metric => (
                <div key={metric.key || metric.metric_id} className="min-w-0 bg-surface-base p-panel">
                  <dt className="type-overline break-words text-text-tertiary">{metric.label}</dt>
                  <dd className="mt-meta font-board text-2xl font-semibold tabular-nums text-text-primary">{metric.value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <div className="section-state section-state--partial" role="status" data-state="partial">
              <h3 className="type-section-title">{summary}</h3>
              {sampleSummary && <p className="type-compact mt-meta">{sampleSummary}</p>}
            </div>
          )}

          {metrics.length > 0 && summary && <p className="type-compact mt-panel max-w-reading text-text-secondary">{summary}</p>}
          {metrics.length > 0 && sampleSummary && <p className="type-metadata mt-panel text-text-tertiary">{sampleSummary}</p>}
          {statusName === 'partial' && limitation && (
            <p className="type-metadata mt-row max-w-reading text-text-withheld" role="status" data-state="partial">{limitation}</p>
          )}
        </>
      )}
    </section>
  )
}
