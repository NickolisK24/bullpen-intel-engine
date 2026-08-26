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

function ComparisonContext({ comparison }) {
  if (!comparison) return null
  if (comparison.status === 'comparable' && comparison.transition) {
    return (
      <p className="mt-2 font-mono text-[11px] uppercase tracking-wider text-text-tertiary">
        Published comparison · {comparison.transition.from_state} → {comparison.transition.to_state}
      </p>
    )
  }
  if (!comparison.boundary) return null
  return (
    <p className="mt-2 border-l-2 border-warning/60 pl-3 text-xs leading-relaxed text-warning" role="note">
      Comparison boundary — these adjacent publications are not proven comparable.
    </p>
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
        <ComparisonContext comparison={row.comparison} />
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
