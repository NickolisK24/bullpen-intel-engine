import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { getWhatChangedView } from './whatChangedView'

function ComparisonLine({ comparison }) {
  if (!comparison.fromDate && !comparison.toDate) return null
  return (
    <p className="type-metadata mt-meta" data-testid="what-changed-comparison">
      {comparison.fromDate && comparison.fromLabel
        ? <>Since <time dateTime={comparison.fromDate}>{comparison.fromLabel}</time></>
        : null}
      {comparison.fromDate && comparison.toDate ? ' · ' : null}
      {comparison.toDate && comparison.toLabel
        ? <>through <time dateTime={comparison.toDate}>{comparison.toLabel}</time></>
        : null}
    </p>
  )
}
function PitcherSubject({ row, onSelectPitcher }) {
  if (row.pitcherId == null || typeof onSelectPitcher !== 'function') {
    return <span className="type-data break-words text-text-primary">{row.subject}</span>
  }
  return (
    <button
      type="button"
      className="min-h-11 break-words text-left font-board text-board-body font-semibold text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
      onClick={event => onSelectPitcher(row.pitcherId, event.currentTarget)}
    >
      {row.subject}
    </button>
  )
}

function ChangeRow({ row, groupKey, onSelectPitcher }) {
  const detail = groupKey === 'arm-read'
    ? row.transition
    : row.gameDate && row.dateLabel
      ? <><time dateTime={row.gameDate}>{row.dateLabel}</time>{row.pitches != null ? ` · ${row.pitches} pitches` : ''}</>
      : row.pitches != null ? `${row.pitches} pitches` : null

  return (
    <li className="grid min-w-0 gap-meta py-row tablet:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.7fr)] tablet:gap-panel">
      <div className="min-w-0"><PitcherSubject row={row} onSelectPitcher={onSelectPitcher} /></div>
      <div className="min-w-0">
        {detail && <p className="type-data break-words text-text-secondary">{detail}</p>}
        {row.summary && <p className="type-compact mt-meta max-w-3xl break-words text-text-secondary">{row.summary}</p>}
      </div>
    </li>
  )
}

function ChangeGroup({ group, onSelectPitcher }) {
  return (
    <section className="mt-section" aria-labelledby={`what-changed-${group.key}-title`}>
      <h3 id={`what-changed-${group.key}-title`} className="type-overline">{group.label}</h3>
      <ul className="mt-meta divide-y divide-line-subtle border-y border-line-subtle">
        {group.rows.map(row => (
          <ChangeRow key={row.key} row={row} groupKey={group.key} onSelectPitcher={onSelectPitcher} />
        ))}
      </ul>
    </section>
  )
}

function WhatChangedSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="what-changed-title" aria-busy="true" data-testid="what-changed-skeleton">
      <h2 id="what-changed-title" className="type-section-title">What Changed</h2>
      <span className="sr-only">Loading governed bullpen changes.</span>
      <SkeletonBlock className="mt-meta h-4 w-64 max-w-full" />
      <div className="mt-section border-y border-line-subtle py-row">
        <SkeletonBlock className="h-5 w-44 max-w-full" />
        <SkeletonBlock className="mt-meta h-4 w-full max-w-2xl" />
      </div>
    </section>
  )
}

export default function TeamBoardWhatChanged({ changes, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <WhatChangedSkeleton />

  const view = getWhatChangedView(changes)
  const limitation = view.limitations[0] || null
  const hasGroups = view.groups.length > 0

  return (
    <section className="foundation-section" aria-labelledby="what-changed-title" data-testid="team-board-what-changed">
      <header>
        <h2 id="what-changed-title" className="type-section-title">What Changed</h2>
        <ComparisonLine comparison={view.comparison} />
      </header>

      {error ? (
        <SectionState status="error" title="What Changed unavailable" message="Current bullpen changes could not be loaded." onRetry={onRetry} className="mt-row" />
      ) : !view.capabilityValid || view.state === 'unavailable' ? (
        <SectionState status="unavailable" title="What Changed unavailable" message={limitation || 'A governed bullpen comparison is not available.'} className="mt-row" />
      ) : view.state === 'no_baseline' ? (
        <SectionState status="unavailable" title="No comparison baseline" message={limitation || 'No earlier completed game is available for comparison.'} className="mt-row" />
      ) : view.state === 'stale' ? (
        <SectionState status="unavailable" title="Comparison freshness blocked" message={limitation || 'Current workload data is not fresh enough to compare safely.'} className="mt-row" />
      ) : view.state === 'no_changes' ? (
        <div className="section-state mt-row" role="status" data-state="quiet">
          <p className="type-compact">No material changes were detected for this published comparison.</p>
        </div>
      ) : view.state === 'changes' && hasGroups ? (
        <>
          {view.groups.map(group => <ChangeGroup key={group.key} group={group} onSelectPitcher={onSelectPitcher} />)}
          {limitation && <SectionState status="partial" title="Some change context is limited" message={limitation} className="mt-row" />}
        </>
      ) : (
        <SectionState status="unavailable" title="Published changes unavailable" message="No supported structured change category is available for this comparison." className="mt-row" />
      )}
    </section>
  )
}
