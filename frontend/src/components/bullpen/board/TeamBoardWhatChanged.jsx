import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { getWhatChangedView } from './whatChangedView'

function ComparisonLine({ comparison }) {
  if (!comparison.fromDate && !comparison.toDate) return null
  return (
    <p className="type-metadata mt-meta text-text-tertiary" data-testid="what-changed-comparison">
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
    return <span className="type-data break-words font-semibold text-text-primary">{row.subject}</span>
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
  if (groupKey === 'team-state') {
    const hasWindow = row.fromDate && row.toDate && row.fromDateLabel && row.toDateLabel
    return (
      <li className="min-w-0 py-panel first:pt-row last:pb-row">
        {row.transition && <p className="font-board text-lg font-semibold break-words text-text-primary">{row.transition}</p>}
        {row.summary && <p className="type-compact mt-meta max-w-3xl break-words text-text-secondary">{row.summary}</p>}
        {hasWindow && (
          <p className="type-metadata mt-meta text-text-tertiary">
            Since <time dateTime={row.fromDate}>{row.fromDateLabel}</time>
            {' · through '}
            <time dateTime={row.toDate}>{row.toDateLabel}</time>
          </p>
        )}
      </li>
    )
  }

  const detail = groupKey === 'arm-read'
    ? row.transition
    : row.gameDate && row.dateLabel
      ? <><time dateTime={row.gameDate}>{row.dateLabel}</time>{row.pitches != null ? ` · ${row.pitches} pitches` : ''}</>
      : row.pitches != null ? `${row.pitches} pitches` : null

  return (
    <li className="grid min-w-0 gap-meta py-panel first:pt-row last:pb-row tablet:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.7fr)] tablet:gap-panel">
      <div className="min-w-0"><PitcherSubject row={row} onSelectPitcher={onSelectPitcher} /></div>
      <div className="min-w-0">
        {detail && <p className="type-data break-words font-medium text-text-primary">{detail}</p>}
        {row.summary && <p className="type-compact mt-meta max-w-3xl break-words text-text-secondary">{row.summary}</p>}
      </div>
    </li>
  )
}

function ChangeGroup({ group, onSelectPitcher }) {
  const isTeamState = group.key === 'team-state'
  return (
    <section
      className={`mt-section rounded-sm border p-panel tablet:p-section ${isTeamState ? 'border-line-default bg-surface-raised/45' : 'border-line-subtle bg-surface-raised/20'}`}
      aria-labelledby={`what-changed-${group.key}-title`}
    >
      <div className="flex min-w-0 items-center justify-between gap-panel border-b border-line-subtle pb-panel">
        <h3 id={`what-changed-${group.key}-title`} className={`type-overline ${isTeamState ? 'text-brand-gold' : 'text-text-tertiary'}`}>{group.label}</h3>
        <span className="type-metadata tabular-nums text-text-tertiary">{group.rows.length}</span>
      </div>
      <ul className="divide-y divide-line-subtle">
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
      <div className="rounded-sm border border-line-default bg-surface-nav/30 p-panel tablet:p-section">
        <div className="type-overline text-brand-gold">Since the last completed game</div>
        <h2 id="what-changed-title" className="type-section-title mt-meta">What Changed</h2>
        <span className="sr-only">Loading governed bullpen changes.</span>
        <SkeletonBlock className="mt-meta h-4 w-64 max-w-full" />
        <div className="mt-section rounded-sm border border-line-subtle bg-surface-raised/20 p-panel">
          <SkeletonBlock className="h-5 w-44 max-w-full" />
          <SkeletonBlock className="mt-meta h-4 w-full max-w-2xl" />
        </div>
      </div>
    </section>
  )
}

export default function TeamBoardWhatChanged({ changes, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <WhatChangedSkeleton />

  const view = getWhatChangedView(changes)
  const limitation = view.limitations[0] || null
  const teamStateUnavailable = view.teamStateComparison.status === 'unavailable'
  const teamStateLimitation = view.teamStateComparison.limitation
  const hasGroups = view.groups.length > 0

  return (
    <section className="foundation-section" aria-labelledby="what-changed-title" data-testid="team-board-what-changed">
      <div className="relative left-1/2 w-screen -translate-x-1/2 border-y border-line-default bg-surface-nav/30 px-4 py-section tablet:left-auto tablet:w-auto tablet:translate-x-0 tablet:rounded-sm tablet:border tablet:px-section tablet:py-section-lg">
        <header className="border-b border-line-default pb-panel">
          <div className="type-overline text-brand-gold">Since the last completed game</div>
          <div className="mt-meta flex min-w-0 flex-wrap items-end justify-between gap-panel">
            <div className="min-w-0">
              <h2 id="what-changed-title" className="font-board text-2xl font-semibold text-text-primary tablet:text-3xl">What Changed</h2>
              <p className="type-compact mt-meta max-w-reading text-text-secondary">Material bullpen movement, kept separate from the deeper receipts below.</p>
            </div>
            <ComparisonLine comparison={view.comparison} />
          </div>
        </header>

        {error ? (
          <SectionState status="error" title="What Changed unavailable" message="Current bullpen changes could not be loaded." onRetry={onRetry} className="mt-section" />
        ) : !view.capabilityValid || view.state === 'unavailable' ? (
          <SectionState status="unavailable" title="What Changed unavailable" message={limitation || 'A governed bullpen comparison is not available.'} className="mt-section" />
        ) : view.state === 'no_baseline' ? (
          <SectionState status="unavailable" title="No comparison baseline" message={limitation || 'No earlier completed game is available for comparison.'} className="mt-section" />
        ) : view.state === 'stale' ? (
          <SectionState status="unavailable" title="Comparison freshness blocked" message={limitation || 'Current workload data is not fresh enough to compare safely.'} className="mt-section" />
        ) : view.state === 'no_changes' && teamStateUnavailable ? (
          <SectionState
            status="partial"
            title="Team State comparison unavailable"
            message={teamStateLimitation}
            className="mt-section"
          />
        ) : view.state === 'no_changes' ? (
          <div className="section-state mt-section rounded-sm border border-line-subtle bg-surface-raised/20" role="status" data-state="quiet">
            <p className="type-compact">No material changes were detected for this published comparison.</p>
          </div>
        ) : view.state === 'changes' && hasGroups ? (
          <>
            {view.groups.map(group => <ChangeGroup key={group.key} group={group} onSelectPitcher={onSelectPitcher} />)}
            {teamStateUnavailable && teamStateLimitation && (
              <SectionState status="partial" title="Team State comparison unavailable" message={teamStateLimitation} className="mt-section" />
            )}
            {limitation && <SectionState status="partial" title="Some change context is limited" message={limitation} className="mt-section" />}
          </>
        ) : (
          <SectionState status="unavailable" title="Published changes unavailable" message="No supported structured change category is available for this comparison." className="mt-section" />
        )}
      </div>
    </section>
  )
}
