import { useEffect } from 'react'
import { useFetch } from '../../hooks/useFetch'
import {
  getAvailabilityBacktest,
  getBullpenDashboard,
  getBullpenOverview,
  getSyncStatus,
} from '../../utils/api'
import { ANALYTICS_EVENTS, trackAnalyticsEventOnce } from '../../utils/analytics'
import { SectionHeader, StaleDataNotice } from '../UI'
import { SyncStatusContent } from '../dashboard/SyncStatus'
import { freshnessDataThrough } from '../dashboard/syncStatusView'
import AvailabilityDashboardSummary from '../dashboard/AvailabilityDashboardSummary'
import AvailabilityBacktestCard from './AvailabilityBacktestCard'
import { getDataProvenance } from '../bullpen/board/tonightsBullpenBoardView'

// Data & Trust owns freshness, reliability checks, and data limitations.
const TRUST_LINKS = [
  { href: '/methodology#methodology', label: 'Methodology' },
  { href: '/methodology#data-sources', label: 'Data Sources' },
  { href: '/methodology#known-limitations', label: 'Known Limitations' },
  { href: '#freshness-update-schedule', label: 'Freshness / Update Schedule' },
]

export default function DataTrust() {
  const backtest = useFetch(getAvailabilityBacktest)
  const dashboard = useFetch(getBullpenDashboard)
  const overview = useFetch(getBullpenOverview)
  const sync = useFetch(getSyncStatus)

  useEffect(() => {
    trackAnalyticsEventOnce(ANALYTICS_EVENTS.TRUST_SURFACE_VIEWED, {
      surface: 'trust',
      route: '/trust',
      source: 'page',
    })
    trackAnalyticsEventOnce(ANALYTICS_EVENTS.FRESHNESS_SURFACE_VIEWED, {
      surface: 'freshness',
      route: '/trust',
      source: 'trust_page',
    })
  }, [])

  return (
    <DataTrustView
      backtest={backtest}
      dashboard={dashboard}
      overview={overview}
      sync={sync}
    />
  )
}

export function DataTrustView({
  backtest,
  dashboard,
  overview,
  sync,
}) {
  const servedFreshness = dashboard?.data?.freshness || null
  const servedDataThrough = freshnessDataThrough(servedFreshness)

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
      <SectionHeader
        title="Data & Trust"
        subtitle="Freshness, sync health, reliability checks, and data limitations behind the bullpen picture"
      />

      <p className="mb-6 max-w-3xl text-sm leading-relaxed text-chalk400">
        The bullpen views show the summary you need to act. This page keeps the
        reliability layer: how fresh the data is, what completed games are
        included, whether sync is healthy, and how availability tiers have
        matched completed-game usage.
      </p>

      <section className="mb-6 rounded border border-dirt bg-dugout/50 p-4" aria-label="Public trust links">
        <div className="font-mono text-xs uppercase tracking-widest text-chalk500">
          Public Trust
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {TRUST_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="inline-flex rounded border border-dirt px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/50 hover:text-amber"
            >
              {link.label}
            </a>
          ))}
        </div>
      </section>

      <AvailabilityBacktestCard
        data={backtest.data}
        loading={backtest.loading}
        error={backtest.staleWithError ? null : backtest.error}
        onRetry={backtest.refetch}
      />
      {backtest.staleWithError && (
        <StaleDataNotice
          message="The operational backtest shown is the last loaded result because the latest refresh failed."
          onRetry={backtest.refetch}
        />
      )}

      {/* Freshness & sync */}
      <section id="freshness-update-schedule" className="mb-6" aria-label="Data freshness and sync detail">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">Freshness &amp; Sync</h2>
        <p className="mb-3 max-w-3xl text-xs leading-relaxed text-chalk500">
          Last checked means BaseballOS ran. Last data update means new baseball data was written.
          Data through is the latest completed MLB date included in the bullpen picture.
          BaseballOS updates after completed MLB games and when the latest sync succeeds.
        </p>
        {(() => {
          const provenance = getDataProvenance(servedFreshness)
          return (
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <span
                className="inline-flex items-center gap-2 rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest"
                style={{ borderColor: provenance.tone.borderColor, backgroundColor: provenance.tone.backgroundColor, color: provenance.tone.color }}
              >
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: provenance.tone.dot }} aria-hidden="true" />
                {provenance.completedGamesLine
                  ? provenance.completedGamesLine
                  : 'No completed MLB data loaded'}
              </span>
              <span className="font-mono text-[11px] text-chalk500">{provenance.throughHint}</span>
            </div>
          )
        })()}
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

      {/* Pitcher workload inventory */}
      <section className="mb-6" aria-label="Pitcher workload inventory">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">Pitcher Workload Inventory</h2>
        {overview.staleWithError && (
          <StaleDataNotice
            message="Inventory diagnostics are from the last loaded overview because the latest refresh failed."
            onRetry={overview.refetch}
          />
        )}
        <AvailabilityDashboardSummary summary={overview.data?.scored_pitcher_inventory} initialDetailsOpen />
      </section>
    </div>
  )
}
