import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { formatDateOnly } from '../../../utils/dateDisplay'

const PATTERN_FIELDS = Object.freeze([
  ['pitchedYesterday', 'Pitched yesterday'],
  ['backToBack', 'Back-to-back'],
  ['threeInFour', '3 appearances in 4 days'],
  ['fourInSix', '4 appearances in 6 days'],
  ['recentMultiInning', 'Multi-inning outing'],
  ['highPitchOuting', '25+ pitch outing'],
])

const numericValue = fact => (
  Number.isInteger(fact?.value) && fact.value >= 0 ? fact.value : null
)

function RecentUsageSkeleton() {
  return (
    <section className="min-w-0" aria-labelledby="recent-usage-title" aria-busy="true" data-testid="recent-usage-skeleton">
      <h2 id="recent-usage-title" className="type-section-title">Recent Usage</h2>
      <span className="sr-only">Loading recent usage and rest patterns.</span>
      <div className="mt-panel space-y-row rounded-sm border border-line-subtle bg-surface-raised/35 p-panel">
        {[0, 1, 2].map(index => (
          <div key={index} className="grid min-w-0 gap-row border-b border-line-subtle pb-row last:border-b-0 last:pb-0 desktop:grid-cols-[minmax(12rem,1fr)_minmax(0,3fr)]">
            <SkeletonBlock className="h-5 w-44 max-w-full" />
            <div className="grid grid-cols-3 gap-row">
              {[0, 1, 2].map(cell => <SkeletonBlock key={cell} className="h-14 w-full" />)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function PublishedNumber({ fact, label }) {
  const value = numericValue(fact)
  const withheld = value == null
  return (
    <div className="min-w-0" aria-label={`${label}: ${withheld ? fact?.status || 'unavailable' : value}`}>
      <dt className="type-overline text-text-tertiary">{label}</dt>
      <dd className={`mt-meta font-board text-board-body font-semibold tabular-nums ${withheld ? 'text-text-withheld' : 'text-text-primary'}`}>
        {withheld ? '—' : value}
      </dd>
    </div>
  )
}

function UsageWindow({ window }) {
  return (
    <div className="min-w-0 border-l border-line-subtle pl-row first:border-l-0 first:pl-0">
      <div className="font-board text-board-label font-semibold uppercase text-text-secondary">{window?.label || 'Window'}</div>
      <dl className="mt-row grid min-w-0 gap-meta">
        <PublishedNumber fact={window?.appearances} label="Appearances" />
        <PublishedNumber fact={window?.pitches} label="Pitches" />
        <PublishedNumber fact={window?.outs} label="Outs" />
      </dl>
    </div>
  )
}

function PatternList({ pitcher }) {
  const published = PATTERN_FIELDS.filter(([key]) => pitcher?.[key]?.value === true)
  const limited = PATTERN_FIELDS.filter(([key]) => pitcher?.[key]?.status !== 'complete')

  return (
    <div className="mt-row border-t border-line-subtle pt-row" aria-label={`Rest and usage patterns for ${pitcher.pitcherName || 'reliever'}`}>
      <div className="type-overline">Rest / Usage Patterns</div>
      <div className="mt-meta flex min-w-0 flex-wrap gap-meta">
        {published.map(([key, label]) => (
          <span key={key} className="inline-flex min-h-7 items-center rounded-sm border border-line-default bg-surface-raised px-2 py-1 font-board text-board-metadata font-medium text-text-secondary">
            {label}
          </span>
        ))}
        {published.length === 0 && limited.length === 0 && (
          <span className="type-metadata">No listed usage pattern in the published window.</span>
        )}
      </div>
      {limited.length > 0 && (
        <p className="type-metadata mt-meta text-text-withheld">
          Evidence incomplete: {limited.map(([, label]) => label).join(', ')}.
        </p>
      )}
    </div>
  )
}

function PitcherUsageRow({ pitcher, onSelectPitcher, subdued = false }) {
  const canOpen = pitcher.pitcherId != null && typeof onSelectPitcher === 'function'
  return (
    <article className={`min-w-0 border-b border-line-subtle py-panel first:pt-row last:border-b-0 last:pb-row ${subdued ? 'opacity-80' : ''}`}>
      <div className="grid min-w-0 gap-panel desktop:grid-cols-[minmax(12rem,1fr)_minmax(0,3fr)] desktop:items-start">
        <div className="min-w-0">
          {canOpen ? (
            <button
              type="button"
              className="min-h-11 max-w-full text-left font-board text-board-body font-semibold text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
              onClick={event => onSelectPitcher(pitcher.pitcherId, event.currentTarget)}
              aria-label={`Open pitcher context for ${pitcher.pitcherName || 'reliever'}`}
            >
              {pitcher.pitcherName || 'Reliever'}
            </button>
          ) : (
            <h3 className="font-board text-board-body font-semibold text-text-primary">{pitcher.pitcherName || 'Reliever'}</h3>
          )}
        </div>
        <div className="grid min-w-0 grid-cols-3 gap-row" aria-label={`Published usage windows for ${pitcher.pitcherName || 'reliever'}`}>
          {pitcher.windows.map((window, index) => <UsageWindow key={window?.key || `window-${index}`} window={window} />)}
        </div>
      </div>
      <PatternList pitcher={pitcher} />
    </article>
  )
}

function PitcherGroup({ pitchers, label, onSelectPitcher, subdued = false }) {
  if (pitchers.length === 0) return null
  return (
    <div className={`min-w-0 rounded-sm border px-panel ${subdued ? 'mt-panel border-line-subtle bg-surface-base/50' : 'border-line-default bg-surface-raised/25'}`}>
      {label && <h3 className="border-b border-line-subtle py-row font-board text-board-body font-semibold text-text-secondary">{label}</h3>}
      <div role="list" aria-label={label || 'Current active bullpen recent usage'}>
        {pitchers.map((pitcher, index) => (
          <div key={pitcher.pitcherId ?? `${pitcher.pitcherName}-${index}`} role="listitem">
            <PitcherUsageRow pitcher={pitcher} onSelectPitcher={onSelectPitcher} subdued={subdued} />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function TeamBoardRecentUsage({ read, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <RecentUsageSkeleton />

  const carrier = read?.recentUsageRest
  const rejected = read?.recentUsageRestRejected === true
  const available = carrier && carrier.status !== 'unavailable'

  return (
    <section className="min-w-0" aria-labelledby="recent-usage-title" data-testid="team-board-recent-usage">
      <header className="mb-panel flex min-w-0 flex-wrap items-end justify-between gap-meta border-b border-line-subtle pb-row">
        <div className="min-w-0">
          <div className="type-overline text-brand-gold">Named-arm workload</div>
          <h2 id="recent-usage-title" className="mt-meta font-board text-xl font-semibold text-text-primary">Recent Usage</h2>
          <p className="type-compact mt-meta max-w-reading">Published workload across yesterday, three days, and seven days, plus factual usage patterns. Current rest remains in Active Bullpen.</p>
        </div>
        {carrier?.dataThrough && <p className="type-metadata">Published through {formatDateOnly(carrier.dataThrough, { month: 'short' })}</p>}
      </header>

      {error ? (
        <SectionState status="error" title="Recent Usage unavailable" message="Recent usage and rest patterns could not be loaded." onRetry={onRetry} />
      ) : rejected ? (
        <SectionState status="unavailable" title="Recent Usage unavailable" message="Recent usage does not match this Team Board publication." />
      ) : !read || !available ? (
        <SectionState status="unavailable" title="Recent Usage unavailable" message="A publication-bound recent usage and rest read is not available." onRetry={onRetry} />
      ) : (
        <>
          <PitcherGroup pitchers={carrier.activePitchers} onSelectPitcher={onSelectPitcher} />
          {carrier.activePitchers.length === 0 && (
            <SectionState status="unavailable" title="No active bullpen usage rows" message="The publication contains no active-pitcher usage rows." />
          )}
          <PitcherGroup
            pitchers={carrier.offActiveHistoricalContributors}
            label="Recent workload from pitchers no longer active"
            onSelectPitcher={onSelectPitcher}
            subdued
          />
          {carrier.status === 'partial' && (
            <SectionState
              status="partial"
              title="Recent Usage is partially available"
              message="Some usage or rest evidence is incomplete; unpublished values remain withheld."
              className="mt-row"
            />
          )}
        </>
      )}
    </section>
  )
}
