import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { formatDateOnly } from '../../../utils/dateDisplay'
import WorkloadTrend from './WorkloadTrend'
import { getWorkloadColumns, getWorkloadTrendView, getWorkloadWindowRows } from './teamBoardWorkloadView'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
export { getWorkloadWindowRows } from './teamBoardWorkloadView'

function firstLimitation(status, workloadOverview) {
  return [
    ...(Array.isArray(status?.limitations) ? status.limitations : []),
    ...(Array.isArray(workloadOverview?.limitations) ? workloadOverview.limitations : []),
  ].find(value => textValue(value))?.trim() || null
}

function WorkloadOverviewSkeleton() {
  return (
    <section className="min-w-0" aria-labelledby="workload-overview-title" aria-busy="true" data-testid="workload-overview-skeleton">
      <h2 id="workload-overview-title" className="type-section-title">Workload Overview</h2>
      <span className="sr-only">Loading workload overview.</span>
      <div className="mt-panel rounded-sm border border-line-subtle bg-surface-raised/35 p-panel">
        {[0, 1].map(index => (
          <div key={index} className="grid min-w-0 grid-cols-3 gap-row border-b border-line-subtle py-row first:pt-0 last:border-b-0 last:pb-0">
            <SkeletonBlock className="h-5 w-20 max-w-full" />
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
  const columns = getWorkloadColumns(rows)
  const gridTemplateColumns = `minmax(0, 1fr) repeat(${columns.length}, minmax(0, 0.65fr))`
  const trend = getWorkloadTrendView(read?.recentReliefWork?.read)
  const concentration = workloadOverview?.concentration
  const concentrationLabel = textValue(concentration?.label)
  const concentrationSummary = textValue(concentration?.summary)
  const limitation = firstLimitation(status, workloadOverview)

  return (
    <section className="min-w-0" aria-labelledby="workload-overview-title" data-testid="team-board-workload-overview">
      <header className="mb-panel border-b border-line-subtle pb-row">
        <div className="type-overline text-brand-gold">Group burden</div>
        <h2 id="workload-overview-title" className="mt-meta font-board text-xl font-semibold text-text-primary">Workload Overview</h2>
      </header>

      {error ? (
        <SectionState status="error" title="Workload Overview unavailable" message="Workload overview could not be loaded." onRetry={onRetry} />
      ) : !read || !workloadOverview ? (
        <SectionState status="unavailable" title="Workload Overview unavailable" message="A governed workload overview is not available." onRetry={onRetry} />
      ) : (
        <>
          {rows.length > 0 && (
            <div className="min-w-0 rounded-sm border border-line-subtle bg-surface-raised/35 px-panel" role="table" aria-label="Recent team relief workload windows">
              <div className="grid min-w-0 gap-row border-b border-line-default py-row" style={{ gridTemplateColumns }} role="row">
                <div className="type-overline" role="columnheader">Window</div>
                {columns.map(column => (
                  <div key={column.key} className="type-overline text-right" role="columnheader">
                    {column.key === 'appearances' ? (
                      <><span className="tablet:hidden">Apps</span><span className="hidden tablet:inline">{column.label}</span></>
                    ) : column.label}
                  </div>
                ))}
              </div>
              {rows.map(row => (
                <div key={row.key} role="row" className="grid min-w-0 items-center gap-row border-b border-line-subtle py-panel last:border-b-0" style={{ gridTemplateColumns }}>
                  <div className="min-w-0" role="rowheader">
                    <div className="font-board text-board-body font-semibold text-text-primary">{row.label}</div>
                    {row.through && <div className="type-overline mt-meta">Through {formatDateOnly(row.through, { month: 'short' })}</div>}
                  </div>
                  {columns.map(column => (
                    <div key={column.key} className={`min-w-0 text-right font-board text-lg font-semibold tabular-nums ${row[column.key] == null ? 'text-text-withheld' : 'text-text-primary'}`} role="cell">
                      {row[column.key] ?? '—'}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {(concentrationLabel || concentrationSummary) ? (
            <div className="mt-panel rounded-sm border border-line-subtle bg-surface-base p-panel">
              <h3 className="type-overline text-brand-gold">Concentration</h3>
              {concentrationLabel && <p className="mt-meta font-board text-board-body font-semibold text-text-primary">{concentrationLabel}</p>}
              {concentrationSummary && <p className="type-compact mt-meta max-w-3xl text-text-secondary">{concentrationSummary}</p>}
            </div>
          ) : rows.length > 0 ? (
            <SectionState status="unavailable" title="Concentration unavailable" message="A backend-authored workload concentration read is not available." className="mt-row" />
          ) : null}

          <div className="mt-panel border-t border-line-subtle pt-panel">
            <WorkloadTrend view={trend} />
          </div>

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
