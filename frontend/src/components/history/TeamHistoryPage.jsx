import HistoricalTransactions from './HistoricalTransactions'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import HistoricalChanges from './HistoricalChanges'
import { GameContext, PitchHistoryPicker } from './HistoryWorkload'
import { getHistoricalTeamDecisions, getTeamStateHistory } from '../../utils/api'
import { buildTeamBoardHref, parseRehearsalRevision } from '../../utils/evidenceLinks'
import { readPublicTeamState } from '../../adapters/publicTeamState'
import { formatFreshnessDate } from '../UI/Freshness'
import { EmptyState, ErrorState, LoadingPane } from '../UI'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function safeTeamAbbreviation(value) {
  const normalized = String(value || '').trim().toUpperCase()
  return /^[A-Z0-9-]{2,5}$/.test(normalized) ? normalized : null
}

function monthKey(dateValue) {
  return String(dateValue || '').slice(0, 7)
}

function monthLabel(key) {
  const [year, month] = String(key || '').split('-').map(Number)
  return month >= 1 && month <= 12 ? `${MONTHS[month - 1]} ${year}` : key
}

function timelineEntries(payload, games) {
  const entries = [
    ...games.map(event => ({ type: 'game', date: event.date, event })),
    ...(payload?.rows || []).map(row => ({ type: 'state', date: row.represented_date, row })),
    ...(payload?.coverage?.missing_dates || []).map(date => ({ type: 'gap', date })),
  ]
  entries.sort((a, b) => String(b.date).localeCompare(String(a.date)))
  return entries
}

function groupedEntries(payload, games) {
  const groups = new Map()
  for (const entry of timelineEntries(payload, games)) {
    const key = monthKey(entry.date)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(entry)
  }
  return [...groups.entries()]
}

function isTeamStateChangeEvent(event) {
  return Boolean(
    event?.event_type === 'team_state_change'
    && event?.event_id
    && event?.label
    && event?.from_state?.code
    && event?.from_state?.label
    && event?.to_state?.code
    && event?.to_state?.label
  )
}

function isQualifiedTransactionEvent(event, representedDate) {
  return Boolean(
    event?.event_type === 'qualified_transaction'
    && event?.event_id
    && event?.event_date === representedDate
    && event?.label
    && event?.description
    && event?.pitcher?.pitcher_id
    && event?.pitcher?.name
    && event?.team_relationship?.relationship
  )
}

export function historyRowCategory(row) {
  if (row?.artifact?.corrected_publication) return 'corrected'
  if (
    row?.event_overlay?.status === 'available'
    && row?.event_overlay?.outcome === 'changed'
    && (row?.events || []).some(isTeamStateChangeEvent)
  ) return 'meaningful-change'
  if (row?.arm_changes?.events?.length) return 'arm-change'
  if ((row?.transactions || []).some(event => isQualifiedTransactionEvent(event, row?.represented_date))) {
    return 'roster-context'
  }
  if (row?.comparison?.status && row.comparison.status !== 'comparable') return 'boundary'
  if (
    row?.comparison?.status === 'comparable'
    && row?.event_overlay?.status === 'available'
    && row?.event_overlay?.outcome === 'unchanged'
    && row?.transaction_overlay?.status === 'available'
  ) return 'ordinary-unchanged'
  return 'standalone'
}

function ComparisonContext({ comparison, eventOverlay }) {
  if (eventOverlay?.status === 'available' && eventOverlay?.outcome === 'unchanged') {
    return (
      <p className="mt-2 font-mono text-[11px] uppercase tracking-wider text-text-tertiary">
        Published comparison · Team State unchanged
      </p>
    )
  }
  if (!comparison) return null
  if (!comparison.boundary) return null
  return (
    <p className="mt-2 border-l-2 border-warning/60 pl-3 text-xs leading-relaxed text-warning" role="note">
      Comparison boundary — these adjacent publications are not proven comparable.
    </p>
  )
}

function EventState({ state }) {
  const value = readPublicTeamState({
    available: true,
    public_state: state?.code,
    public_label: state?.label,
  })
  if (!value.available) return null
  return (
    <span
      className="inline-flex min-h-8 items-center rounded-sm border px-2 py-1 font-board text-sm font-semibold"
      style={value.tone}
    >
      {value.publicLabel}
    </span>
  )
}

function TeamStateChangeEvent({ event, primaryCitation }) {
  if (!isTeamStateChangeEvent(event)) return null

  const previousCitation = event.citations?.previous?.citation_url
  const currentCitation = event.citations?.current?.citation_url
  const secondaryCurrentCitation = currentCitation && currentCitation !== primaryCitation
    ? currentCitation
    : null
  return (
    <div
      className="mt-3 border-l-2 border-brand-blue/40 pl-3"
      data-testid="team-state-change-marker"
    >
      <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-brand-blue">
        {event.label}
      </p>
      <div
        className="mt-2 flex min-w-0 flex-wrap items-center gap-2"
        aria-label={`${event.from_state.label} to ${event.to_state.label}`}
      >
        <EventState state={event.from_state} />
        <span aria-hidden="true" className="font-mono text-sm text-text-tertiary">→</span>
        <span className="sr-only">to</span>
        <EventState state={event.to_state} />
      </div>
      {(previousCitation || secondaryCurrentCitation) && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0 text-xs">
          {previousCitation && (
            <Link
              to={previousCitation}
              className="inline-flex min-h-11 items-center text-text-secondary underline-offset-4 hover:text-brand-blue hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
            >
              View previous observation
            </Link>
          )}
          {secondaryCurrentCitation && (
            <Link
              to={secondaryCurrentCitation}
              className="inline-flex min-h-11 items-center text-text-secondary underline-offset-4 hover:text-brand-blue hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
            >
              View current observation
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

function QualifiedTransactionEvent({ event }) {
  if (!isQualifiedTransactionEvent(event, event?.event_date)) return null

  return (
    <li className="min-w-0 text-sm leading-relaxed text-text-secondary">
      <span className="font-semibold text-text-primary">{event.label}</span>
      <span aria-hidden="true"> · </span>
      <span className="sr-only">: </span>
      {event.description}
    </li>
  )
}

function TransactionContext({ overlay, events, representedDate }) {
  const qualified = (events || []).filter(event => (
    isQualifiedTransactionEvent(event, representedDate)
  ))
  const isPartial = overlay?.status === 'partial'
  const isUnavailable = overlay?.status === 'unavailable'
  if (!qualified.length && !isPartial && !isUnavailable) return null

  return (
    <div
      className="mt-3 border-l-2 border-line-default pl-3"
      data-testid="qualified-transaction-overlay"
      role={isPartial || isUnavailable ? 'note' : undefined}
    >
      {qualified.length > 0 && (
        <>
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-text-secondary">
            Roster moves
          </p>
          <ul className="mt-1 space-y-1">
            {qualified.map(event => (
              <QualifiedTransactionEvent key={event.event_id} event={event} />
            ))}
          </ul>
        </>
      )}
      {isPartial && (
        <p className={`${qualified.length ? 'mt-2 ' : ''}text-xs leading-relaxed text-text-withheld`}>
          Transaction context is incomplete for this date.
        </p>
      )}
      {isUnavailable && (
        <p className={`${qualified.length ? 'mt-2 ' : ''}text-xs leading-relaxed text-text-withheld`}>
          Transaction context is unavailable for this date.
        </p>
      )}
    </div>
  )
}

function PublishedObservationLink({ row, className = '' }) {
  if (!row?.artifact?.citation_url) return null
  return (
    <Link
      to={row.artifact.citation_url}
      className={`${className} inline-flex min-h-11 max-w-full items-center break-words font-board text-sm font-semibold text-brand-blue underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-line-focus`}
      aria-label={`View the published Team State observation for ${row.represented_date}`}
    >
      View published observation
    </Link>
  )
}

function StateBadge({ state }) {
  return (
    <div
      className="inline-flex min-h-8 items-center gap-2 rounded-sm border px-3 py-1 font-board text-sm font-semibold"
      style={state.tone}
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: state.tone.dot }} aria-hidden="true" />
      {state.publicLabel || 'Team State unavailable'}
    </div>
  )
}

function ExpandedRowDetails({ row, showComparison = true }) {
  return (
    <>
      {row.explanation && <p className="mt-3 max-w-reading text-sm leading-relaxed text-text-primary">{row.explanation}</p>}
      {(row.events || []).map(event => (
        <TeamStateChangeEvent
          key={event.event_id}
          event={event}
          primaryCitation={row.artifact?.citation_url}
        />
      ))}
      {row.arm_changes?.events?.length > 0 && (
        <section className="mt-3" aria-label="Published pitcher changes">
          <h3 className="text-sm font-semibold">Pitcher workload and deployment changes</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {row.arm_changes.events.map(event => (
              <li key={`${event.domain}-${event.event_type}-${event.subject_id}`}>{event.summary}</li>
            ))}
          </ul>
          {row.arm_changes.citations?.previous?.citation_url && (
            <Link className="text-xs underline" to={row.arm_changes.citations.previous.citation_url}>
              Previous published observation
            </Link>
          )}
        </section>
      )}
      {row.arm_changes && (row.arm_changes.board_limit_applied || Object.values(row.arm_changes.domains).some(domain => domain.status !== 'complete')) && (
        <p className="mt-2 text-xs text-text-tertiary">Pitcher change coverage is partial for this comparison.</p>
      )}
      {row.arm_changes === null && (
        <p className="mt-2 text-xs text-text-tertiary">No published pitcher-change comparison for this date.</p>
      )}
      <TransactionContext
        overlay={row.transaction_overlay}
        events={row.transactions}
        representedDate={row.represented_date}
      />
      {showComparison && <ComparisonContext comparison={row.comparison} eventOverlay={row.event_overlay} />}
      {row.limitations?.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs leading-relaxed text-text-tertiary">
          {row.limitations.map((item, index) => <li key={`${index}-${item}`}>• {item}</li>)}
        </ul>
      )}
      <PublishedObservationLink row={row} className="mt-3" />
    </>
  )
}

export function HistoryStateRow({ row, defaultDetailsOpen = false }) {
  const [detailsOpen, setDetailsOpen] = useState(defaultDetailsOpen)
  const state = readPublicTeamState({
    available: true,
    public_state: row?.team_state?.public_code,
    public_label: row?.team_state?.public_label,
    summary: row?.explanation,
  })
  const category = historyRowCategory(row)
  const isOrdinary = category === 'ordinary-unchanged'
  const dateLabel = formatFreshnessDate(row.represented_date, { includeYear: true }) || row.represented_date
  const detailId = `history-row-details-${row.artifact?.public_id || row.represented_date}`
  return (
    <article
      className={`grid min-w-0 gap-3 border-t ${isOrdinary ? 'border-line-subtle py-3' : 'border-line-default py-5'} tablet:grid-cols-[8rem_minmax(0,1fr)] tablet:gap-6`}
      data-testid="history-state-row"
      data-row-category={category}
    >
      <div>
        <time dateTime={row.represented_date} className="font-mono text-xs font-semibold uppercase tracking-wider text-text-secondary">
          {dateLabel}
        </time>
        {row.artifact?.corrected_publication && (
          <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-brand-gold">Corrected publication</p>
        )}
      </div>
      <div className="min-w-0">
        {isOrdinary ? (
          <>
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
              <StateBadge state={state} />
              <p className="font-mono text-[11px] uppercase tracking-wider text-text-tertiary">
                <span className="sr-only">Published comparison — Team State </span>
                Unchanged
              </p>
              <button
                type="button"
                aria-expanded={detailsOpen ? 'true' : 'false'}
                aria-controls={detailId}
                aria-label={`${detailsOpen ? 'Hide' : 'View'} details for ${dateLabel}`}
                onClick={() => setDetailsOpen(open => !open)}
                className="ml-auto inline-flex min-h-11 shrink-0 items-center px-2 font-board text-sm font-semibold text-brand-blue underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
              >
                {detailsOpen ? 'Hide details' : 'View details'}
              </button>
            </div>
            {detailsOpen && (
              <div id={detailId} data-testid="history-row-details">
                <ExpandedRowDetails row={row} showComparison={false} />
              </div>
            )}
          </>
        ) : (
          <>
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <StateBadge state={state} />
              {category === 'boundary' && (
                <span className="font-mono text-[11px] uppercase tracking-wider text-text-withheld">
                  {row.comparison?.boundary ? 'Comparison boundary' : 'Comparison unavailable'}
                </span>
              )}
            </div>
            <ExpandedRowDetails row={row} />
          </>
        )}
      </div>
    </article>
  )
}

function GapRow({ date }) {
  return (
    <div className="grid gap-2 border-t border-dashed border-line-subtle py-4 text-text-withheld tablet:grid-cols-[8rem_minmax(0,1fr)] tablet:gap-6" role="note">
      <time dateTime={date} className="font-mono text-xs uppercase tracking-wider">
        {formatFreshnessDate(date, { includeYear: true }) || date}
      </time>
      <p className="text-sm">Historical Team State unavailable. No state is carried forward.</p>
    </div>
  )
}

export function matchesHistoryCursor(page, team, revision) {
  const matchesClub = typeof team === 'string' ? page?.team_abbreviation === team : page?.team === team
  if (!matchesClub || !Number.isSafeInteger(page?.team) || page.team <= 0
      || page.scope !== 'isolated_historical_team_history' || page.current_serving_eligible !== false
      || page.status !== 'historical_decisions' || !Array.isArray(page.rows)
      || !page.rows.length || page.rows.length > 30) return false
  return page.rows.every((row, index) => {
    const expected = revision - index
    return expected > 0 && row?.selection_revision === expected && row.predecessor === (expected === 1 ? null : expected - 1)
  }) && page.next_revision === page.rows.at(-1).predecessor
}

function EarlierDecisions({ team, revision }) {
  const read = useFetch(options => getHistoricalTeamDecisions(team, revision, options), [team, revision])
  if (read.loading) return <LoadingPane message="Loading earlier decisions…" />
  if (read.error) return <ErrorState message={read.error} onRetry={read.refetch} />
  const page = read.data
  if (!matchesHistoryCursor(page, team, revision)) {
    return <ErrorState message="Earlier History decisions could not be verified." onRetry={read.refetch} />
  }
  return <HistoricalSelectionHistory payload={page} continuation />
}

function HistoricalSelectionHistory({ payload, continuation = false }) {
  const [expanded, setExpanded] = useState(false)
  const last = payload.rows.at(-1)
  const cursor = payload.next_revision
  const canContinue = Number.isSafeInteger(cursor) && cursor > 0 && cursor < last?.selection_revision
    && cursor === last.predecessor
  return (
    <section className={continuation ? "space-y-5" : "mx-auto max-w-5xl space-y-5 px-4 py-6"}>
      {!continuation && <h1 className="font-board text-2xl font-semibold">{payload.team_name} historical rehearsal</h1>}
      {payload.status === 'unknown_revision' && <p>Requested History revision unavailable.</p>}
      {payload.rows.map(row => {
        const state = readPublicTeamState(row.team_state)
        return <article key={row.selection_revision} className="border-t border-line-subtle py-3">
          <h2 className="font-board text-xl">Revision {row.selection_revision} · {row.action === 'rollback' ? 'Rollback' : 'Selection'}</h2>
          {row.generation ? <>
            <p>Data through <time>{row.represented}</time> · Availability reference <time>{row.availability_reference}</time></p>
            <p>{state.publicLabel || state.statusLabel || state.unavailableMessage}</p>
            <HistoricalChanges row={row} team={payload.team} />
            {row.official_transactions?.events?.length > 0 &&
              <HistoricalTransactions transactions={row.official_transactions} team={payload.team} through={row.represented} />}
            {row.calendar_context.events.map(event => <GameContext key={event.kind + event.game_pks.join('-')} event={event} />)}
            {row.calendar_context.calendar_limitation && <p>Calendar evidence is incomplete.</p>}
            <details><summary>Team State evidence</summary>
              <p className="break-all">Generation {row.generation}</p>
              <p className="break-all">Readiness source digest {row.readiness_citation.input_digest}</p>
            </details>
          </> : <p>No historical generation selected.</p>}
        </article>
      })}
      {canContinue && (expanded
        ? <EarlierDecisions key={cursor} team={payload.team} revision={cursor} />
        : <button type="button" className="min-h-11 text-brand-blue underline" onClick={() => setExpanded(true)}>
          Load earlier decisions from revision {cursor}
        </button>)}
    </section>
  )
}

export function TeamHistoryPageView({ payload, loading = false, error = null, onRetry = null }) {
  if (loading) return <LoadingPane message="Loading Team State history…" />
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  if (payload?.scope === 'isolated_historical_team_history' && payload.current_serving_eligible === false) {
    return <HistoricalSelectionHistory key={`${payload.team}-${payload.rows[0]?.selection_revision}`} payload={payload} />
  }
  if (!payload?.team) return <ErrorState message="This team history destination is unavailable." onRetry={onRetry} />

  const teamName = payload.team.team_name || payload.team.team_abbreviation || 'Team'
  const coverage = payload.coverage || {}
  const groups = groupedEntries(payload, payload.workload?.events || [])
  const boardHref = payload.team.team_board_href || buildTeamBoardHref(payload.team)
  const coverageLabel = coverage.start && coverage.end
    ? `${formatFreshnessDate(coverage.start, { includeYear: true })} – ${formatFreshnessDate(coverage.end, { includeYear: true })}`
    : null

  return (
    <div id="history-top" className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <header className="border-b border-line-default pb-6">
        <p className="type-overline text-brand-blue">History · {payload.season}</p>
        <h1 className="mt-2 break-words font-board text-[2rem] font-semibold leading-tight tracking-[-0.02em] text-text-primary tablet:text-[2.5rem]">
          {teamName} Team State History
        </h1>
        {coverageLabel && <p className="mt-2 font-mono text-xs uppercase tracking-wider text-text-tertiary">Retained coverage · {coverageLabel}</p>}
        {coverage.is_partial && (
          <p className="mt-3 max-w-reading text-sm leading-relaxed text-text-secondary" role="status">
            This is partial retained history. Missing dates are shown explicitly and are not reconstructed.
          </p>
        )}
        <Link
          to={boardHref}
          className="mt-4 inline-flex min-h-11 items-center font-board text-sm font-semibold text-brand-blue underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
        >
          Open current {teamName} Team Board
        </Link>
      </header>

      {payload.workload === null && <p role="status">Historical workload unavailable.</p>}
      {payload.workload && <>
        <PitchHistoryPicker key={payload.team.team_abbreviation} team={payload.team.team_abbreviation} season={payload.season} pitchers={payload.workload.pitchers} />
        <p className="text-sm text-text-secondary">Game context uses retained regular-season MLB records. Published Team States are dated separately.</p>
        {!payload.workload.events.length && <p>No verified game workload or off-day context for this season.</p>}
      </>}
      {groups.length === 0 ? (
        <EmptyState
          title="Historical Team State is not available"
          subtitle={`No retained Team State publications are available for ${teamName} in ${payload.season}.`}
        />
      ) : (
        <>
          {groups.length > 1 && (
            <nav className="mt-6 border-y border-line-subtle py-3" aria-label="History months">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-tertiary">Jump to month</p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {groups.map(([month]) => (
                  <a
                    key={month}
                    href={`#history-month-${month}`}
                    className="inline-flex min-h-11 items-center font-board text-sm font-semibold text-brand-blue underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
                  >
                    {monthLabel(month)}
                  </a>
                ))}
              </div>
            </nav>
          )}
          <div className="mt-7 space-y-8" data-testid="team-state-history-timeline">
            {groups.map(([month, entries]) => (
              <section key={month} className="scroll-mt-6" aria-labelledby={`history-month-${month}`}>
                <h2 id={`history-month-${month}`} className="font-board text-xl font-semibold text-text-primary">{monthLabel(month)}</h2>
                <div className="mt-2">
                  {entries.map(entry => entry.type === 'game'
                    ? <GameContext key={`game-${entry.date}-${entry.event.game_pks.join('-')}`} event={entry.event} />
                    : entry.type === 'gap'
                    ? <GapRow key={`gap-${entry.date}`} date={entry.date} />
                    : <HistoryStateRow key={entry.row.artifact.public_id} row={entry.row} />)}
                </div>
              </section>
            ))}
          </div>
          <a
            href="#history-top"
            className="mt-6 inline-flex min-h-11 items-center font-board text-sm font-semibold text-text-secondary underline-offset-4 hover:text-brand-blue hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
          >
            Back to History top
          </a>
        </>
      )}
    </div>
  )
}

export default function TeamHistoryPage() {
  const { abbr } = useParams()
  const teamAbbreviation = safeTeamAbbreviation(abbr)
  const [search] = useSearchParams()
  const revisionParam = search.get('rehearsalRevision')
  const repeated = search.getAll('rehearsalRevision').length > 1
  return <HistoryDestination key={JSON.stringify([teamAbbreviation, revisionParam, repeated])}
    teamAbbreviation={teamAbbreviation} revisionParam={revisionParam} repeated={repeated} />
}

function HistoryDestination({ teamAbbreviation, revisionParam, repeated }) {
  const history = useFetch(async options => {
    if (!teamAbbreviation) throw new Error('This History destination does not contain a valid team abbreviation.')
    const revision = parseRehearsalRevision(revisionParam, repeated)
    if (revision === null) return getTeamStateHistory(teamAbbreviation, 2026, options)
    const page = await getHistoricalTeamDecisions(teamAbbreviation, revision, options)
    if (!matchesHistoryCursor(page, teamAbbreviation, revision)) {
      throw new Error('The requested historical edition could not be verified.')
    }
    return page
  }, [teamAbbreviation, revisionParam, repeated])
  return (
    <TeamHistoryPageView
      payload={history.data}
      loading={history.loading}
      error={history.error}
      onRetry={history.refetch}
    />
  )
}
