import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'

const metrics = [
  { key: 'pitches', label: 'Pitches' },
  { key: 'appearances', label: 'Appearances', compactLabel: 'Apps' },
  { key: 'outs', label: 'Outs' },
]

function WorkloadMetric({ fact }) {
  if (!fact) return <span className="text-text-withheld">—</span>
  const label = fact.status === 'complete'
    ? String(fact.value)
    : fact.status === 'unavailable' ? 'Not published' : '—'
  return (
    <span className={fact.status === 'complete' ? 'text-text-primary' : 'text-text-withheld'}>
      <span className="block font-board text-base font-semibold tabular-nums tablet:text-lg">{label}</span>
      {fact.status !== 'complete' && <span className="block text-xs font-normal capitalize text-text-tertiary">{fact.status}</span>}
    </span>
  )
}

function WorkloadOverviewSkeleton() {
  return (
    <section className="min-w-0" aria-labelledby="workload-overview-title" aria-busy="true" data-testid="workload-overview-skeleton">
      <h2 id="workload-overview-title" className="type-section-title">Workload Overview</h2>
      <span className="sr-only">Loading workload overview.</span>
      <div className="mt-panel rounded-sm border border-line-subtle bg-surface-raised/35 p-panel">
        {[0, 1, 2, 3].map(index => <SkeletonBlock key={index} className="my-row h-5 w-full" />)}
      </div>
    </section>
  )
}

function Contribution({ label, value }) {
  if (!value) return null
  return (
    <p className="type-compact text-text-secondary">
      <span className="font-semibold text-text-primary">{label}:</span>{' '}
      {value.pitches} pitches · {value.appearances} {value.appearances === 1 ? 'appearance' : 'appearances'}
    </p>
  )
}

export default function TeamBoardWorkloadOverview({ read, loading = false, error = null, onRetry }) {
  if (loading) return <WorkloadOverviewSkeleton />
  const workload = read?.frozenTeamWorkload
  const concentration = workload?.concentration

  return (
    <section className="min-w-0" aria-labelledby="workload-overview-title" data-testid="team-board-workload-overview">
      <header className="mb-panel border-b border-line-subtle pb-row">
        <div className="type-overline text-brand-gold">Group burden</div>
        <h2 id="workload-overview-title" className="mt-meta font-board text-xl font-semibold text-text-primary">Workload Overview</h2>
      </header>
      {error ? (
        <SectionState status="error" title="Workload Overview unavailable" message="Workload overview could not be loaded." onRetry={onRetry} />
      ) : !workload ? (
        <SectionState status="unavailable" title="Workload Overview unavailable" message="Frozen team workload is not published for this Team Board." />
      ) : (
        <>
          <div className="min-w-0 overflow-hidden rounded-sm border border-line-subtle bg-surface-raised/35">
            <table className="w-full table-fixed border-collapse text-left" aria-label="Team relief workload by baseball-date window">
              <thead>
                <tr className="border-b border-line-default">
                  <th scope="col" className="w-[23%] px-2 py-row type-overline tablet:px-panel">Window</th>
                  {metrics.map(metric => (
                    <th key={metric.key} scope="col" className="px-1 py-row text-right type-overline tablet:px-panel">
                      {metric.compactLabel ? <><span className="tablet:hidden">{metric.compactLabel}</span><span className="hidden tablet:inline">{metric.label}</span></> : metric.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {workload.windows.map(window => (
                  <tr key={window.days} className="border-b border-line-subtle last:border-b-0" data-window-days={window.days}>
                    <th scope="row" className="px-2 py-panel font-board text-sm font-semibold text-text-primary tablet:px-panel tablet:text-base">{window.label}</th>
                    {metrics.map(metric => (
                      <td key={metric.key} className="px-1 py-panel text-right tablet:px-panel" aria-label={`${window.label} ${metric.label}: ${window[metric.key]?.status === 'complete' ? window[metric.key].value : window[metric.key]?.status || 'unknown'}`}>
                        <WorkloadMetric fact={window[metric.key]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="type-compact mt-meta text-text-tertiary">Baseball-date windows through {workload.dataThrough}. Each metric reflects its own evidence state.</p>
          <div className="mt-panel border-t border-line-subtle pt-panel">
            <h3 className="type-overline text-brand-gold">Seven-day pitch contributors</h3>
            {concentration?.status === 'complete' ? (
              <>
                {concentration.topThreeShare !== null && (
                  <p className="mt-meta font-board text-board-body font-semibold text-text-primary">
                    Top 3 arms account for {Math.round(concentration.topThreeShare * 100)}% of 7-day pitches.
                  </p>
                )}
                <p className="type-compact mt-meta text-text-secondary">
                  {concentration.pitcherCount} {concentration.pitcherCount === 1 ? 'pitcher contributed' : 'pitchers contributed'} relief workload in this window.
                </p>
                {concentration.topThree.length > 0 && (
                  <ol className="mt-row divide-y divide-line-subtle" aria-label="Leading seven-day pitch contributors">
                    {concentration.topThree.map(item => (
                      <li key={item.pitcherId} className="flex min-w-0 items-baseline justify-between gap-row py-row type-compact">
                        <span className="min-w-0 text-text-primary">{item.name} <span className="text-text-tertiary">· {item.currentActive ? 'Current active' : 'Off-active'}</span></span>
                        <span className="shrink-0 font-semibold tabular-nums text-text-primary">{item.pitches} pitches</span>
                      </li>
                    ))}
                  </ol>
                )}
                <div className="mt-row space-y-1 border-t border-line-subtle pt-row">
                  <Contribution label="Current active bullpen" value={concentration.activeCurrentContribution} />
                  {concentration.offActiveContribution?.appearances > 0 && <Contribution label="Recent off-active contributors" value={concentration.offActiveContribution} />}
                </div>
              </>
            ) : (
              <p className="type-compact mt-meta text-text-tertiary">Seven-day concentration {concentration?.status === 'partial' ? 'is incomplete' : 'is not published'}.</p>
            )}
          </div>
        </>
      )}
    </section>
  )
}
