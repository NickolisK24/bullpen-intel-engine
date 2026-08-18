import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'

const countValue = value => Number.isInteger(value) && value >= 0 ? value : null
const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null

export function getWorkloadWindowRows(workloadOverview) {
  const windows = Array.isArray(workloadOverview?.windows) ? workloadOverview.windows : []
  return windows.map((window, index) => ({
    key: countValue(window?.window_days) == null ? `window-${index}` : `window-${window.window_days}`,
    label: countValue(window?.window_days) == null ? 'Window unavailable' : `${window.window_days} days`,
    appearances: countValue(window?.relief_appearances),
    pitchers: countValue(window?.pitchers_in_relief),
    pitches: countValue(window?.pitches_total),
  }))
}

function firstLimitation(status, workloadOverview) {
  return [
    ...(Array.isArray(status?.limitations) ? status.limitations : []),
    ...(Array.isArray(workloadOverview?.limitations) ? workloadOverview.limitations : []),
  ].find(value => textValue(value))?.trim() || null
}

function WorkloadOverviewSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="workload-overview-title" aria-busy="true" data-testid="workload-overview-skeleton">
      <h2 id="workload-overview-title" className="type-section-title">Workload Overview</h2>
      <span className="sr-only">Loading workload overview.</span>
      <div className="mt-row border-y border-dirt">
        {[0, 1].map(index => (
          <div key={index} className="grid min-w-0 grid-cols-2 gap-row border-b border-dirt px-panel py-row last:border-b-0 tablet:grid-cols-4">
            <SkeletonBlock className="h-5 w-20 max-w-full" />
            <SkeletonBlock className="h-5 w-16 max-w-full" />
            <SkeletonBlock className="h-5 w-16 max-w-full" />
            <SkeletonBlock className="h-5 w-16 max-w-full" />
          </div>
        ))}
      </div>
    </section>
  )
}

export default function TeamBoardWorkloadOverview({ read, loading = false, error = null, onRetry }) {
  if (loading) return <WorkloadOverviewSkeleton />

  const workloadOverview = read?.workloadOverview
  const status = read?.sectionStatus?.workload_overview
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const rows = getWorkloadWindowRows(workloadOverview)
  const concentration = workloadOverview?.concentration
  const concentrationLabel = textValue(concentration?.label)
  const concentrationSummary = textValue(concentration?.summary)
  const limitation = firstLimitation(status, workloadOverview)

  return (
    <section className="foundation-section" aria-labelledby="workload-overview-title" data-testid="team-board-workload-overview">
      <header className="mb-row">
        <h2 id="workload-overview-title" className="type-section-title">Workload Overview</h2>
      </header>

      {error ? (
        <SectionState status="error" title="Workload Overview unavailable" message="Workload overview could not be loaded." onRetry={onRetry} />
      ) : !read || !workloadOverview ? (
        <SectionState status="unavailable" title="Workload Overview unavailable" message="A governed workload overview is not available." onRetry={onRetry} />
      ) : (
        <>
          {rows.length > 0 && (
            <div className="border-y border-dirt" role="list" aria-label="Recent team relief workload windows">
              {rows.map(row => (
                <article key={row.key} role="listitem" className="grid min-w-0 grid-cols-2 gap-row border-b border-dirt px-panel py-row last:border-b-0 tablet:grid-cols-4 tablet:items-center">
                  <div className="min-w-0">
                    <div className="type-overline">Window</div>
                    <div className="type-data mt-meta text-chalk100">{row.label}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="type-overline">Relief appearances</div>
                    <div className="type-data mt-meta">{row.appearances ?? 'Unavailable'}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="type-overline">Relievers</div>
                    <div className="type-data mt-meta">{row.pitchers ?? 'Unavailable'}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="type-overline">Pitches</div>
                    <div className="type-data mt-meta">{row.pitches ?? 'Unavailable'}</div>
                  </div>
                </article>
              ))}
            </div>
          )}

          {(concentrationLabel || concentrationSummary) ? (
            <div className="mt-row border-b border-dirt px-panel pb-row">
              <h3 className="type-overline">Concentration</h3>
              {concentrationLabel && <p className="type-data mt-meta text-chalk100">{concentrationLabel}</p>}
              {concentrationSummary && <p className="type-compact mt-meta max-w-3xl">{concentrationSummary}</p>}
            </div>
          ) : rows.length > 0 ? (
            <SectionState status="unavailable" title="Concentration unavailable" message="A backend-authored workload concentration read is not available." className="mt-row" />
          ) : null}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Workload Overview is partially available" message={limitation || 'Some workload evidence is unavailable.'} className={(rows.length > 0 || concentrationLabel) ? 'mt-row' : ''} />
          )}
          {statusName === 'unavailable' && (
            <SectionState status="unavailable" title="Workload Overview unavailable" message="Recent team workload evidence is unavailable." className={(rows.length > 0 || concentrationLabel) ? 'mt-row' : ''} />
          )}
          {statusName === 'available' && rows.length === 0 && !concentrationLabel && (
            <div className="section-state" role="status" data-state="empty">
              <h3 className="type-section-title">No recent team workload</h3>
              <p className="type-compact mt-meta">The governed workload population is empty.</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}
