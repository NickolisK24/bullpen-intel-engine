import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import {
  getAvailabilityBacktest,
  getBullpenDashboard,
  getSyncStatus,
} from '../../utils/api'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import { SyncStatusContent } from '../dashboard/SyncStatus'
import { freshnessDataThrough } from '../dashboard/syncStatusView'
import { getDataProvenance } from '../bullpen/board/tonightsBullpenBoardView'
import { PUBLIC_BOUNDARIES } from '../../utils/publicBoundaries'
import AvailabilityBacktestCard from './AvailabilityBacktestCard'

// Data & Trust answers, in order: is the public bullpen picture current, what
// completed-game data it includes, and whether the four availability labels held
// up against observed next-day usage. It links to Methodology (how reads are
// formed) and How to Read (what labels mean) rather than repeating them.
const TRUST_LIMITATIONS = [
  'The usage labels describe recent workload context. They do not diagnose health.',
  PUBLIC_BOUNDARIES.noManagerCertainty,
  'A next-day appearance rate is a look back at completed games, not a forecast of whether a pitcher will appear.',
  'A team state describes a bullpen’s current shape. It is not a ranking.',
  PUBLIC_BOUNDARIES.saysSoInsteadOfGuessing,
]

const INSPECT_LINKS = [
  { to: '/methodology', label: 'Methodology — how reads are formed' },
  { to: '/how-to-read', label: 'How to Read — what the public labels mean' },
  { to: '/bullpen', label: 'Team Bullpens — inspect a team’s live evidence' },
  { to: '/bullpen?view=pitchers', label: 'Reliever Finder — inspect one reliever' },
  { to: '/bullpen?view=compare', label: 'Compare Bullpens — put two pens side by side' },
]

export default function DataTrust() {
  const backtest = useFetch(getAvailabilityBacktest)
  const dashboard = useFetch(getBullpenDashboard)
  const sync = useFetch(getSyncStatus)

  return (
    <DataTrustView
      backtest={backtest}
      dashboard={dashboard}
      sync={sync}
    />
  )
}

// The lead answer: is the served public bullpen picture current? The served
// dashboard freshness is the authority (getDataProvenance already fails closed to
// a non-current state for sample, stale, fallback, or missing data). A usage-check
// or sync failure never reaches this section, and a current claim is never shown
// when the served view is anything other than live.
function CurrentDataAnswer({ dashboard }) {
  if (dashboard.loading && !dashboard.data) {
    return <LoadingPane message="Checking whether the public bullpen picture is current..." />
  }

  const servedFreshness = dashboard?.data?.freshness || null
  if (servedFreshness == null && dashboard.error) {
    return (
      <ErrorState
        message="The current public data status could not be loaded."
        onRetry={dashboard.refetch}
      />
    )
  }

  const provenance = getDataProvenance(servedFreshness)
  const headline = provenance.isLive
    ? 'The public bullpen picture is current.'
    : provenance.state === 'none'
      ? 'No public bullpen data is loaded right now.'
      : 'The public bullpen picture is not current.'

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <span
          className="inline-flex items-center gap-2 rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest"
          style={{ borderColor: provenance.tone.borderColor, backgroundColor: provenance.tone.backgroundColor, color: provenance.tone.color }}
        >
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: provenance.tone.dot }} aria-hidden="true" />
          {provenance.label}
        </span>
        {provenance.dataThrough && (
          <span className="font-mono text-[11px] text-chalk400">
            Data through {provenance.dataThrough}
          </span>
        )}
      </div>
      <p className="mt-3 max-w-3xl text-lg leading-snug text-chalk100">
        {headline}
      </p>
      {provenance.completedGamesLine && (
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk300">
          {provenance.completedGamesLine}
        </p>
      )}
      {provenance.throughHint && (
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk400">
          {provenance.throughHint}
        </p>
      )}
      <p className="mt-2 max-w-3xl text-xs leading-relaxed text-chalk500">
        &ldquo;Current&rdquo; means the latest completed-game data is included — not real-time,
        in-game tracking.
      </p>
      {dashboard.staleWithError && (
        <StaleDataNotice
          message="These are the last successfully loaded values; the latest refresh failed."
          dataThrough={freshnessDataThrough(servedFreshness)}
          onRetry={dashboard.refetch}
        />
      )}
    </div>
  )
}

export function DataTrustView({
  backtest,
  dashboard,
  sync,
}) {
  const servedFreshness = dashboard?.data?.freshness || null
  const servedDataThrough = freshnessDataThrough(servedFreshness)

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-4xl mx-auto">
      <header className="mb-8 border-b border-dirt pb-4">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/75">
          Data &amp; Trust
        </div>
        <h1 className="mt-1 font-display text-3xl sm:text-4xl tracking-wide text-chalk100">
          Is this current — and do the labels hold up?
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-chalk300">
          This page keeps the reliability layer behind the bullpen picture: whether
          the public data is current, which completed games it includes, and how the
          four availability labels matched what pitchers actually did the next day.
        </p>
      </header>

      <div className="space-y-10">
        {/* 1. Is the public bullpen picture current? */}
        <section aria-labelledby="current-data" className="scroll-mt-24">
          <h2 id="current-data" className="mb-3 font-display text-2xl tracking-wide text-chalk100">
            Is the public bullpen picture current?
          </h2>
          <CurrentDataAnswer dashboard={dashboard} />
        </section>

        {/* 2. What completed games, when checked, when updated. */}
        <section id="freshness-update-schedule" className="scroll-mt-24" aria-labelledby="freshness-detail">
          <h2 id="freshness-detail" className="mb-3 font-display text-2xl tracking-wide text-chalk100">
            Freshness and coverage detail
          </h2>
          <p className="mb-3 max-w-2xl text-xs leading-relaxed text-chalk500">
            <span className="text-chalk300">Data through</span> is the latest completed
            MLB date included. <span className="text-chalk300">Last data update</span> is
            when new baseball data was successfully written.{' '}
            <span className="text-chalk300">Last checked</span> is when BaseballOS last ran —
            a check is not the same as a successful update. BaseballOS updates after
            completed MLB games, and may withhold or limit a read when coverage is
            incomplete.
          </p>
          {sync.staleWithError && (
            <StaleDataNotice
              message="Sync details are from the last loaded status because the latest refresh failed."
              onRetry={sync.refetch}
            />
          )}
          {dashboard?.staleWithError && (
            <StaleDataNotice
              dataThrough={servedDataThrough}
              onRetry={dashboard.refetch}
            />
          )}
          <SyncStatusContent
            data={sync.data}
            loading={sync.loading}
            error={sync.staleWithError ? null : sync.error}
            freshnessAuthority={servedFreshness}
          />
        </section>

        {/* 3. Do the labels hold up against observed next-day usage? */}
        <section aria-label="Availability label usage check" className="scroll-mt-24">
          <AvailabilityBacktestCard
            data={backtest.data}
            loading={backtest.loading}
            error={backtest.staleWithError ? null : backtest.error}
            onRetry={backtest.refetch}
          />
          {backtest.staleWithError && (
            <StaleDataNotice
              message="The usage check shown is the last loaded result because the latest refresh failed."
              onRetry={backtest.refetch}
            />
          )}
        </section>

        {/* 4. Limitations and where to inspect the live evidence. */}
        <section aria-labelledby="trust-limitations" className="scroll-mt-24">
          <h2 id="trust-limitations" className="mb-3 font-display text-2xl tracking-wide text-chalk100">
            What these checks do not prove
          </h2>
          <ul className="max-w-2xl space-y-2 text-sm leading-relaxed text-chalk400">
            {TRUST_LIMITATIONS.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="text-amber" aria-hidden="true">&bull;</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <ul className="mt-5 space-y-2">
            {INSPECT_LINKS.map((link) => (
              <li key={link.to}>
                <Link
                  to={link.to}
                  className="inline-flex min-w-0 rounded border border-dirt bg-chalk/10 px-3 py-2 text-sm text-chalk200 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
