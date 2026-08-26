import { Link, useParams } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getTeamStateHistory } from '../../utils/api'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
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

function timelineEntries(payload) {
  const entries = [
    ...(payload?.rows || []).map(row => ({ type: 'state', date: row.represented_date, row })),
    ...(payload?.coverage?.missing_dates || []).map(date => ({ type: 'gap', date })),
  ]
  entries.sort((a, b) => String(b.date).localeCompare(String(a.date)))
  return entries
}

function groupedEntries(payload) {
  const groups = new Map()
  for (const entry of timelineEntries(payload)) {
    const key = monthKey(entry.date)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(entry)
  }
  return [...groups.entries()]
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

function TeamStateChangeEvent({ event }) {
  if (
    event?.event_type !== 'team_state_change'
    || !event?.event_id
    || !event?.label
    || !event?.from_state?.code
    || !event?.from_state?.label
    || !event?.to_state?.code
    || !event?.to_state?.label
  ) return null

  const previousCitation = event.citations?.previous?.citation_url
  const currentCitation = event.citations?.current?.citation_url
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
      {(previousCitation || currentCitation) && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0 text-xs">
          {previousCitation && (
            <Link
              to={previousCitation}
              className="inline-flex min-h-11 items-center text-text-secondary underline-offset-4 hover:text-brand-blue hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
            >
              Open earlier published observation
            </Link>
          )}
          {currentCitation && (
            <Link
              to={currentCitation}
              className="inline-flex min-h-11 items-center text-text-secondary underline-offset-4 hover:text-brand-blue hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
            >
              Open later published observation
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

function StateRow({ row }) {
  const state = readPublicTeamState({
    available: true,
    public_state: row?.team_state?.public_code,
    public_label: row?.team_state?.public_label,
    summary: row?.explanation,
  })
  return (
    <article className="grid min-w-0 gap-3 border-t border-line-subtle py-5 tablet:grid-cols-[8rem_minmax(0,1fr)] tablet:gap-6">
      <div>
        <time dateTime={row.represented_date} className="font-mono text-xs font-semibold uppercase tracking-wider text-text-secondary">
          {formatFreshnessDate(row.represented_date, { includeYear: true }) || row.represented_date}
        </time>
        {row.artifact?.corrected_publication && (
          <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-brand-gold">Corrected publication</p>
        )}
      </div>
      <div className="min-w-0">
        <div
          className="inline-flex min-h-8 items-center gap-2 rounded-sm border px-3 py-1 font-board text-sm font-semibold"
          style={state.tone}
        >
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: state.tone.dot }} aria-hidden="true" />
          {state.publicLabel || 'Team State unavailable'}
        </div>
        {row.explanation && <p className="mt-3 max-w-reading text-sm leading-relaxed text-text-primary">{row.explanation}</p>}
        {(row.events || []).map(event => (
          <TeamStateChangeEvent key={event.event_id} event={event} />
        ))}
        <ComparisonContext comparison={row.comparison} eventOverlay={row.event_overlay} />
        {row.limitations?.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs leading-relaxed text-text-tertiary">
            {row.limitations.map((item, index) => <li key={`${index}-${item}`}>• {item}</li>)}
          </ul>
        )}
        {row.artifact?.citation_url && (
          <Link
            to={row.artifact.citation_url}
            className="mt-3 inline-flex min-h-11 items-center font-board text-sm font-semibold text-brand-blue underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-line-focus"
            aria-label={`Open the published Team State citation for ${row.represented_date}`}
          >
            Open published citation
          </Link>
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

export function TeamHistoryPageView({ payload, loading = false, error = null, onRetry = null }) {
  if (loading) return <LoadingPane message="Loading Team State history…" />
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  if (!payload?.team) return <ErrorState message="This team history destination is unavailable." onRetry={onRetry} />

  const teamName = payload.team.team_name || payload.team.team_abbreviation || 'Team'
  const coverage = payload.coverage || {}
  const groups = groupedEntries(payload)
  const boardHref = payload.team.team_board_href || buildTeamBoardHref(payload.team)
  const coverageLabel = coverage.start && coverage.end
    ? `${formatFreshnessDate(coverage.start, { includeYear: true })} – ${formatFreshnessDate(coverage.end, { includeYear: true })}`
    : null

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
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

      {groups.length === 0 ? (
        <EmptyState
          title="Historical Team State is not available"
          subtitle={`No retained Team State publications are available for ${teamName} in ${payload.season}.`}
        />
      ) : (
        <div className="mt-7 space-y-8" data-testid="team-state-history-timeline">
          {groups.map(([month, entries]) => (
            <section key={month} aria-labelledby={`history-month-${month}`}>
              <h2 id={`history-month-${month}`} className="font-board text-xl font-semibold text-text-primary">{monthLabel(month)}</h2>
              <div className="mt-2">
                {entries.map(entry => entry.type === 'gap'
                  ? <GapRow key={`gap-${entry.date}`} date={entry.date} />
                  : <StateRow key={entry.row.artifact.public_id} row={entry.row} />)}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

export default function TeamHistoryPage() {
  const { abbr } = useParams()
  const teamAbbreviation = safeTeamAbbreviation(abbr)
  const history = useFetch(
    () => (teamAbbreviation
      ? getTeamStateHistory(teamAbbreviation, 2026)
      : Promise.reject(new Error('This History destination does not contain a valid team abbreviation.'))),
    [teamAbbreviation],
  )
  return (
    <TeamHistoryPageView
      payload={history.data}
      loading={history.loading}
      error={history.error}
      onRetry={history.refetch}
    />
  )
}
