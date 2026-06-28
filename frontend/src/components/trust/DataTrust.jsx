import { useFetch } from '../../hooks/useFetch'
import {
  getAvailabilityBacktest,
  getBullpenDashboard,
  getBullpenOverview,
  getSyncStatus,
} from '../../utils/api'
import { SectionHeader, StaleDataNotice } from '../UI'
import { SyncStatusContent } from '../dashboard/SyncStatus'
import AvailabilityDashboardSummary from '../dashboard/AvailabilityDashboardSummary'
import AvailabilityBacktestCard from './AvailabilityBacktestCard'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import { getDataProvenance } from '../bullpen/board/tonightsBullpenBoardView'

// Data & Trust owns freshness, reliability checks, and data limitations.
export default function DataTrust() {
  const backtest = useFetch(getAvailabilityBacktest)
  const dashboard = useFetch(getBullpenDashboard)
  const overview = useFetch(getBullpenOverview)
  const sync = useFetch(getSyncStatus)

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
      <section className="mb-6" aria-label="Data freshness and sync detail">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">Freshness &amp; Sync</h2>
        <p className="mb-3 max-w-3xl text-xs leading-relaxed text-chalk500">
          Last checked means BaseballOS ran. Last data update means new baseball data was written.
          Data through is the latest completed MLB date included in the bullpen picture.
        </p>
        {(() => {
          const provenance = getDataProvenance({
            data_through: servedFreshness?.data_through,
            is_current: servedFreshness?.is_current,
            sync_status: servedFreshness?.sync_status,
            is_stale: servedFreshness?.is_stale,
            freshness_state: servedFreshness?.freshness_state,
            served_consistency_state: servedFreshness?.served_consistency_state,
            current_sync_status: servedFreshness?.current_sync_status,
          })
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
            dataThrough={servedFreshness?.data_through}
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

      <FeedbackCTA
        className="mb-2"
        eyebrow="Trust Feedback"
        title="Help improve BaseballOS"
        body="Tell us what works, what does not, and what would make this more useful."
      />
    </div>
  )
}
