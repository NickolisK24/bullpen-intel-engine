import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { formatDateOnly } from '../../../utils/dateDisplay'
import { getRecentUsageView } from './recentUsageView'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
function firstLimitation(status) {
  const values = [
    ...(Array.isArray(status?.limitations) ? status.limitations : []),
  ]
  return values.find(value => textValue(value))?.trim() || null
}

const publishedValue = value => Number.isInteger(value) && value >= 0 ? value : '—'

function RecentUsageSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="recent-usage-title" aria-busy="true" data-testid="recent-usage-skeleton">
      <h2 id="recent-usage-title" className="type-section-title">Recent Usage</h2>
      <span className="sr-only">Loading recent usage.</span>
      <div className="mt-row border-y border-dirt">
        {[0, 1].map(index => (
          <div key={index} className="grid min-w-0 gap-row border-b border-dirt py-row last:border-b-0 tablet:grid-cols-[minmax(10rem,1.2fr)_repeat(3,minmax(6rem,0.6fr))]">
            <SkeletonBlock className="h-5 w-40 max-w-full" />
            <SkeletonBlock className="h-4 w-24 max-w-full" />
            <SkeletonBlock className="h-4 w-28 max-w-full" />
            <SkeletonBlock className="h-4 w-20 max-w-full" />
          </div>
        ))}
      </div>
    </section>
  )
}

function UsageWindowRow({ row }) {
  return (
    <article role="listitem" className="min-w-0 border-b border-line-subtle py-row last:border-b-0">
      <div className="grid min-w-0 grid-cols-3 gap-panel tablet:grid-cols-[minmax(10rem,1.2fr)_repeat(3,minmax(6rem,0.6fr))] tablet:items-center">
        <div className="col-span-3 min-w-0 tablet:col-span-1">
          <h3 className="type-label text-text-primary">Last {row.days} days</h3>
          <p className="type-metadata mt-meta text-text-tertiary">
            Through <time dateTime={row.through}>{formatDateOnly(row.through, { month: 'short' })}</time>
          </p>
        </div>
        {[
          ['Appearances', publishedValue(row.reliefAppearances)],
          ['Arms', publishedValue(row.pitchersInRelief)],
          ['Pitches', publishedValue(row.pitchesTotal)],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0 tablet:text-right">
            <div className="type-overline tablet:hidden">{label}</div>
            <div className={`type-data mt-meta tabular-nums ${value === '—' ? 'text-text-withheld' : 'text-text-primary'}`}>{value}</div>
          </div>
        ))}
      </div>
      <p className="type-compact mt-row max-w-[48rem] text-text-secondary">{row.sentence}</p>
      {row.limitations.map((limitation, index) => (
        <p key={`${row.key}-limitation-${index}`} className="type-metadata mt-meta max-w-[48rem] text-text-withheld">{limitation}</p>
      ))}
    </article>
  )
}

function LatestPublishedUsage({ group, onSelectPitcher }) {
  if (!group) return null
  const dateLabel = formatDateOnly(group.gameDate, { month: 'short' })

  return (
    <div className="border-b border-line-default pb-row">
      <div className="type-overline">Most recent published date</div>
      <h3 className="type-data mt-meta text-text-primary">
        <time dateTime={group.gameDate}>{dateLabel}</time>
      </h3>
      <p className="type-compact mt-meta max-w-[48rem] text-text-secondary">{group.sentence}</p>
      {group.arms.length > 0 && (
        <div className="mt-row" aria-label={`Arms used on ${dateLabel}`}>
          <div className="type-overline">Arms used</div>
          <div className="mt-meta flex min-w-0 flex-wrap gap-x-panel gap-y-meta">
            {group.arms.map(arm => arm.pitcherId != null && typeof onSelectPitcher === 'function' ? (
              <button
                key={arm.key}
                type="button"
                className="min-h-11 rounded-sm font-board text-board-body text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
                onClick={event => onSelectPitcher(arm.pitcherId, event.currentTarget)}
              >
                {arm.name}
              </button>
            ) : (
              <span key={arm.key} className="inline-flex min-h-11 items-center font-board text-board-body text-text-secondary">{arm.name}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function TeamBoardRecentUsage({ read, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <RecentUsageSkeleton />

  const reliefWork = read?.recentReliefWork?.read
  const status = read?.sectionStatus?.recent_usage
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const view = getRecentUsageView(reliefWork)
  const rows = view.available ? view.windows : []
  const limitation = firstLimitation(status)

  return (
    <section className="foundation-section" aria-labelledby="recent-usage-title" data-testid="team-board-recent-usage">
      <header className="mb-row flex min-w-0 flex-wrap items-end justify-between gap-meta">
        <h2 id="recent-usage-title" className="type-section-title">Recent Usage</h2>
        {reliefWork?.data_through && <p className="type-metadata">Published through {formatDateOnly(reliefWork.data_through, { month: 'short' })}</p>}
      </header>

      {error ? (
        <SectionState status="error" title="Recent Usage unavailable" message="Recent usage could not be loaded." onRetry={onRetry} />
      ) : !read || !view.available ? (
        <SectionState status="unavailable" title="Recent Usage unavailable" message="A recent usage read is not available." onRetry={onRetry} />
      ) : (
        <>
          <LatestPublishedUsage group={view.latestGroup} onSelectPitcher={onSelectPitcher} />
          {rows.length > 0 && (
            <div className="mt-row min-w-0" role="list" aria-label="Published recent relief usage windows">
              <div className="hidden grid-cols-[minmax(10rem,1.2fr)_repeat(3,minmax(6rem,0.6fr))] gap-panel border-b border-line-default pb-meta font-board text-board-label font-medium uppercase text-text-tertiary tablet:grid">
                <div>Window</div>
                <div className="text-right">Appearances</div>
                <div className="text-right">Arms</div>
                <div className="text-right">Pitches</div>
              </div>
              {rows.map(row => <UsageWindowRow key={row.key} row={row} />)}
            </div>
          )}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Recent Usage is partially available" message={limitation || 'Some recent appearance evidence is unavailable.'} className={rows.length > 0 ? 'mt-row' : ''} />
          )}
          {statusName === 'unavailable' && (
            <SectionState status="unavailable" title="Recent Usage unavailable" message="Recent usage evidence is unavailable." className={rows.length > 0 ? 'mt-row' : ''} />
          )}
        </>
      )}
    </section>
  )
}
