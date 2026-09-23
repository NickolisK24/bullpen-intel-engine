import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'
import { getWhatChangedView } from './whatChangedView'

function WhatChangedSkeleton() {
  return (
    <section id="what-changed" className="foundation-section" aria-labelledby="what-changed-title" aria-busy="true" data-testid="what-changed-skeleton">
      <div className="rounded-sm border border-line-default bg-surface-nav/30 p-panel">
        <div className="type-overline text-brand-gold">Exact trusted comparison</div>
        <h2 id="what-changed-title" className="mt-meta font-board text-xl font-semibold text-text-primary">What Changed</h2>
        <span className="sr-only">Loading governed bullpen changes.</span>
        <SkeletonBlock className="mt-meta h-4 w-64 max-w-full" />
        <SkeletonBlock className="mt-panel h-10 w-full" />
      </div>
    </section>
  )
}

function ComparisonWindow({ view }) {
  if (!view.previousDate) return null
  return (
    <p className="type-metadata mt-meta text-text-tertiary" data-testid="what-changed-comparison">
      Since <time dateTime={view.previousDate}>{view.previousDateLabel}</time>
      {view.currentDate && view.currentDateLabel ? <>{' · through '}<time dateTime={view.currentDate}>{view.currentDateLabel}</time></> : null}
    </p>
  )
}

function ChangeItem({ event, onSelectPitcher }) {
  const canSelect = event.subjectId != null && event.subject && typeof onSelectPitcher === 'function'
  return (
    <li className="min-w-0 py-panel first:pt-0 last:pb-0" data-domain={event.domain}>
      <div className="flex min-w-0 flex-wrap items-center gap-x-panel gap-y-meta">
        <span className="type-overline text-text-tertiary">{event.domainLabel}</span>
        {event.eventDate && event.eventDateLabel ? <time className="type-metadata text-text-tertiary" dateTime={event.eventDate}>{event.eventDateLabel}</time> : null}
      </div>
      <p className="type-data mt-meta break-words font-semibold text-text-primary">{event.summary}</p>
      <div className="mt-meta flex flex-wrap gap-panel">
        {canSelect ? (
          <button type="button" className="min-h-11 text-left font-board text-board-metadata font-semibold text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus" onClick={click => onSelectPitcher(event.subjectId, click.currentTarget)}>
            Review {event.subject}
          </button>
        ) : null}
        {event.handoff ? <a className="inline-flex min-h-11 items-center font-board text-board-metadata font-semibold text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus" href={event.handoff.href}>{event.handoff.label}</a> : null}
      </div>
    </li>
  )
}

export default function TeamBoardWhatChanged({ changes, loading = false, error = null, onRetry, onSelectPitcher }) {
  if (loading) return <WhatChangedSkeleton />
  const view = getWhatChangedView(changes)
  const compact = view.valid && view.state === 'quiet' && !error

  return (
    <section id="what-changed" className="foundation-section" aria-labelledby="what-changed-title" data-testid="team-board-what-changed">
      <div className={`-mx-4 border-y border-line-default bg-surface-nav/30 px-4 tablet:mx-0 tablet:rounded-sm tablet:border tablet:px-section ${compact ? 'py-panel' : 'py-section tablet:py-section-lg'}`}>
        <header className={compact ? '' : 'border-b border-line-default pb-panel'}>
          <div className="type-overline text-brand-gold">Exact trusted comparison</div>
          <h2 id="what-changed-title" className={`mt-meta font-board font-semibold text-text-primary ${compact ? 'text-xl' : 'text-2xl tablet:text-3xl'}`}>What Changed</h2>
          <ComparisonWindow view={view} />
          {view.teamStateOutcome === 'unchanged' ? <p className="type-metadata mt-meta text-text-secondary">Team State was unchanged across this exact pair.</p> : null}
        </header>

        {error ? (
          <SectionState status="error" title="What Changed unavailable" message="Current bullpen changes could not be loaded." onRetry={onRetry} className="mt-section" />
        ) : !view.valid ? (
          <SectionState status="unavailable" title="What Changed unavailable" message="This trusted update does not contain a frozen comparison." className="mt-section" />
        ) : view.state === 'unavailable' ? (
          <SectionState status="unavailable" title={view.previousDate ? 'What Changed unavailable' : 'No prior trusted comparison'} message={view.previousDate ? 'The frozen comparison is unavailable for this update.' : 'No exact earlier trusted update is available for comparison.'} className="mt-section" />
        ) : view.state === 'quiet' ? (
          <div className="section-state mt-panel rounded-sm border border-line-subtle bg-surface-raised/20" role="status" data-state="quiet">
            <p className="type-compact">{view.quietMessage || 'No material bullpen changes since the previous trusted update.'}</p>
          </div>
        ) : view.events.length ? (
          <ul className="mt-section divide-y divide-line-subtle rounded-sm border border-line-subtle bg-surface-raised/20 p-panel tablet:p-section" aria-label="Material bullpen changes">
            {view.events.map(event => <ChangeItem key={event.key} event={event} onSelectPitcher={onSelectPitcher} />)}
          </ul>
        ) : (
          <SectionState status="unavailable" title="Published changes unavailable" message="No governed material-change event is available for this comparison." className="mt-section" />
        )}

        {view.comparisonStatus === 'partial' && view.state !== 'unavailable' ? (
          <p className="type-metadata mt-panel text-text-tertiary" role="note">
            Partial comparison. Not compared: {view.unavailableDomains.map(domain => domain.label).join(', ')}.
          </p>
        ) : null}
      </div>
    </section>
  )
}
