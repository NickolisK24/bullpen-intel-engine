import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { getRestStatusView } from './teamBoardWorkloadView'

function RestStatusSkeleton() {
  return (
    <section className="min-w-0" aria-labelledby="rest-status-title" aria-busy="true" data-testid="rest-status-skeleton">
      <h2 id="rest-status-title" className="type-section-title">Rest Status</h2>
      <span className="sr-only">Loading rest status.</span>
      <div className="mt-panel grid grid-cols-3 gap-panel rounded-sm border border-line-subtle bg-surface-raised/35 p-panel">
        {[0, 1, 2].map(index => <SkeletonBlock key={index} className="h-12 w-full max-w-28" />)}
      </div>
    </section>
  )
}

export default function TeamBoardRestStatus({ read, loading = false, error = null, onRetry }) {
  if (loading) return <RestStatusSkeleton />

  const status = read?.sectionStatus?.rest_status
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const view = getRestStatusView(read?.restStatus)

  return (
    <section className="min-w-0" aria-labelledby="rest-status-title" data-testid="team-board-rest-status">
      <header className="mb-panel border-b border-line-subtle pb-row">
        <div className="type-overline text-brand-gold">Recovery runway</div>
        <h2 id="rest-status-title" className="mt-meta font-board text-xl font-semibold text-text-primary">Rest Status</h2>
      </header>

      {error ? (
        <SectionState status="error" title="Rest Status unavailable" message="Rest status could not be loaded." onRetry={onRetry} />
      ) : !read || statusName === 'unavailable' || !view.available ? (
        <SectionState status="unavailable" title="Rest Status unavailable" message="Current Rest Status is unavailable." onRetry={!read ? onRetry : undefined} />
      ) : (
        <>
          <div className="rounded-sm border border-line-subtle bg-surface-raised/35 p-panel tablet:p-section">
            <dl className="grid grid-cols-3 divide-x divide-line-subtle" aria-label="Current bullpen rest coverage">
              {[
                ['Rested arms', view.rested_arm_count],
                ['Worked yesterday', view.worked_yesterday_count],
                ['Back-to-back', view.back_to_back_count],
              ].map(([label, value], index) => (
                <div key={label} className={`min-w-0 ${index === 0 ? 'pr-panel' : index === 2 ? 'pl-panel' : 'px-panel'}`}>
                  <dt className="type-overline break-words">{label}</dt>
                  <dd className="mt-meta font-board text-2xl font-semibold tabular-nums text-text-primary">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="type-compact mt-panel border-t border-line-subtle pt-row text-text-secondary">{view.summary}</p>
          </div>
          {statusName === 'partial' && (
            <SectionState status="partial" title="Rest Status is partially available" message="Some rest evidence is unavailable." className="mt-row" />
          )}
        </>
      )}
    </section>
  )
}
