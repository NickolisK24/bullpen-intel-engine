import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { formatDateOnly } from '../../../utils/dateDisplay'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
const countValue = value => Number.isInteger(value) && value >= 0 ? value : null

function inningsFromOuts(value) {
  const outs = countValue(value)
  if (outs == null) return null
  return `${Math.floor(outs / 3)}.${outs % 3} IP`
}

function pitchesLabel(value) {
  const pitches = countValue(value)
  if (pitches == null) return null
  return `${pitches} ${pitches === 1 ? 'pitch' : 'pitches'}`
}

export function getRecentUsageRows(recentUsage) {
  const appearances = Array.isArray(recentUsage?.appearances) ? recentUsage.appearances : []
  return appearances.map((appearance, index) => ({
    key: appearance?.game_id != null && appearance?.pitcher_id != null
      ? `${appearance.game_id}-${appearance.pitcher_id}`
      : `appearance-${index}`,
    pitcherName: textValue(appearance?.pitcher_name) || 'Pitcher unavailable',
    gameDate: textValue(appearance?.game_date),
    dateLabel: formatDateOnly(appearance?.game_date, { month: 'short' }),
    pitches: countValue(appearance?.pitches_thrown),
    innings: inningsFromOuts(appearance?.outs_recorded),
    opponent: textValue(appearance?.opponent_abbreviation) || textValue(appearance?.opponent),
  }))
}

function firstLimitation(status, recentUsage) {
  const values = [
    ...(Array.isArray(status?.limitations) ? status.limitations : []),
    ...(Array.isArray(recentUsage?.limitations) ? recentUsage.limitations : []),
  ]
  return values.find(value => textValue(value))?.trim() || null
}

function RecentUsageSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="recent-usage-title" aria-busy="true" data-testid="recent-usage-skeleton">
      <h2 id="recent-usage-title" className="type-section-title">Recent Usage</h2>
      <span className="sr-only">Loading recent usage.</span>
      <div className="mt-row border-y border-dirt">
        {[0, 1, 2].map(index => (
          <div key={index} className="grid min-w-0 gap-row border-b border-dirt px-panel py-row last:border-b-0 tablet:grid-cols-[minmax(10rem,1.4fr)_minmax(8rem,0.8fr)_minmax(8rem,0.8fr)_minmax(8rem,1fr)]">
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

export default function TeamBoardRecentUsage({ read, loading = false, error = null, onRetry }) {
  if (loading) return <RecentUsageSkeleton />

  const recentUsage = read?.recentUsage
  const status = read?.sectionStatus?.recent_usage
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const rows = getRecentUsageRows(recentUsage)
  const limitation = firstLimitation(status, recentUsage)

  return (
    <section className="foundation-section" aria-labelledby="recent-usage-title" data-testid="team-board-recent-usage">
      <header className="mb-row flex min-w-0 flex-wrap items-end justify-between gap-meta">
        <h2 id="recent-usage-title" className="type-section-title">Recent Usage</h2>
        {recentUsage?.population_basis && <p className="type-metadata">Recent relief appearances</p>}
      </header>

      {error ? (
        <SectionState status="error" title="Recent Usage unavailable" message="Recent usage could not be loaded." onRetry={onRetry} />
      ) : !read || !recentUsage ? (
        <SectionState status="unavailable" title="Recent Usage unavailable" message="A recent usage read is not available." onRetry={onRetry} />
      ) : (
        <>
          {rows.length > 0 && (
            <div className="border-y border-dirt" role="list" aria-label="Recent relief appearances">
              {rows.map(row => (
                <article key={row.key} role="listitem" className="grid min-w-0 gap-row border-b border-dirt px-panel py-row last:border-b-0 tablet:grid-cols-[minmax(10rem,1.4fr)_minmax(8rem,0.8fr)_minmax(8rem,0.8fr)_minmax(8rem,1fr)] tablet:items-center">
                  <div className="min-w-0">
                    <h3 className="type-data break-words text-chalk100">{row.pitcherName}</h3>
                  </div>
                  <div className="min-w-0">
                    <div className="type-overline">Appearance</div>
                    <div className="type-data mt-meta">
                      {row.gameDate && row.dateLabel
                        ? <time dateTime={row.gameDate}>{row.dateLabel}</time>
                        : <span>Unavailable</span>}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className="type-overline">Work</div>
                    <div className="type-data mt-meta">
                      {[row.innings, pitchesLabel(row.pitches)].filter(Boolean).join(' · ') || 'Unavailable'}
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className="type-overline">Context</div>
                    <div className="type-data mt-meta">{row.opponent ? `vs. ${row.opponent}` : 'Unavailable'}</div>
                  </div>
                </article>
              ))}
            </div>
          )}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Recent Usage is partially available" message={limitation || 'Some recent appearance evidence is unavailable.'} className={rows.length > 0 ? 'mt-row' : ''} />
          )}
          {statusName === 'unavailable' && (
            <SectionState status="unavailable" title="Recent Usage unavailable" message="Recent appearance evidence is unavailable." className={rows.length > 0 ? 'mt-row' : ''} />
          )}
          {statusName === 'available' && rows.length === 0 && (
            <div className="section-state" role="status" data-state="empty">
              <h3 className="type-section-title">No recent relief appearances</h3>
              <p className="type-compact mt-meta">The governed recent appearance population is empty.</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}
