import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { getRestStatusView } from './teamBoardWorkloadView'

function RestStatusSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="rest-status-title" aria-busy="true" data-testid="rest-status-skeleton">
      <h2 id="rest-status-title" className="type-section-title">Rest Status</h2>
      <span className="sr-only">Loading rest status.</span>
      <div className="mt-row grid border-y border-dirt tablet:grid-cols-3">
        {[0, 1, 2].map(index => <SkeletonBlock key={index} className="m-panel h-10 w-24 max-w-full" />)}
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
    <section className="foundation-section" aria-labelledby="rest-status-title" data-testid="team-board-rest-status">
      <header className="mb-row">
        <h2 id="rest-status-title" className="type-section-title">Rest Status</h2>
      </header>

      {error ? (
        <SectionState status="error" title="Rest Status unavailable" message="Rest status could not be loaded." onRetry={onRetry} />
      ) : !read || statusName === 'unavailable' || !view.available ? (
        <SectionState status="unavailable" title="Rest Status unavailable" message="A current backend-authored Rest Status is not available." onRetry={!read ? onRetry : undefined} />
      ) : (
        <>
          <dl className="grid border-y border-dirt tablet:grid-cols-3" aria-label="Current bullpen rest coverage">
            {[
              ['Rested arms', view.rested_arm_count],
              ['Worked yesterday', view.worked_yesterday_count],
              ['Back-to-back', view.back_to_back_count],
            ].map(([label, value]) => (
              <div key={label} className="min-w-0 border-b border-dirt px-panel py-row last:border-b-0 tablet:border-b-0 tablet:border-r tablet:last:border-r-0">
                <dt className="type-overline">{label}</dt>
                <dd className="type-data mt-meta text-lg text-chalk100">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="type-compact mt-row max-w-3xl">{view.summary}</p>
          {statusName === 'partial' && (
            <SectionState status="partial" title="Rest Status is partially available" message="Some rest evidence is unavailable." className="mt-row" />
          )}
        </>
      )}
    </section>
  )
}
