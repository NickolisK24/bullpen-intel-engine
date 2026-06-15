import { useFetch } from '../../hooks/useFetch'
import {
  getAvailabilityBacktest,
  getBullpenOverview,
  getRecommendationV2BullpenState,
  getSyncStatus,
  getTeamOperationsBullpenReadiness,
} from '../../utils/api'
import { SectionHeader } from '../UI'
import { SyncStatusContent } from '../dashboard/SyncStatus'
import AvailabilityDashboardSummary from '../dashboard/AvailabilityDashboardSummary'
import OperationalReadinessSection from '../dashboard/OperationalReadinessSection'
import FatigueInsightCard from '../dashboard/FatigueInsightCard'
import AvailabilityBacktestCard from './AvailabilityBacktestCard'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import { getDataProvenance } from '../bullpen/board/tonightsBullpenBoardView'

// Data & Trust — the home for freshness, confidence, operational evidence,
// limitations, and diagnostics. The dashboard shows the summaries; the full
// depth lives here behind intentional navigation.
export default function DataTrust() {
  const backtest = useFetch(getAvailabilityBacktest)
  const overview = useFetch(getBullpenOverview)
  const sync = useFetch(getSyncStatus)
  const v2BullpenState = useFetch(() => getRecommendationV2BullpenState({ limit: 750 }))
  const teamOperationsReadiness = useFetch(() => getTeamOperationsBullpenReadiness({ include_details: true }))

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
      <SectionHeader
        title="Data & Trust"
        subtitle="Freshness, workload reads, governance protections, and evidence behind every number"
      />

      <p className="mb-6 max-w-3xl text-sm leading-relaxed text-chalk400">
        The bullpen views show the summary you need to act. This page keeps the
        full depth — how fresh the data is, how clear each workload read is,
        the operational backtest behind the availability tiers, and the
        supporting evidence and limitations.
      </p>

      <AvailabilityBacktestCard
        data={backtest.data}
        loading={backtest.loading}
        error={backtest.error}
        onRetry={backtest.refetch}
      />

      {/* Freshness & sync */}
      <section className="mb-6" aria-label="Data freshness and sync detail">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">Freshness &amp; Sync</h2>
        {(() => {
          const provenance = getDataProvenance({
            data_through: sync.data?.data?.latest_game_date,
            is_current: sync.data?.freshness?.is_current,
            sync_status: sync.data?.status,
          })
          return (
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <span
                className="inline-flex items-center gap-2 rounded border px-2.5 py-1 font-mono text-[11px] uppercase tracking-widest"
                style={{ borderColor: provenance.tone.borderColor, backgroundColor: provenance.tone.backgroundColor, color: provenance.tone.color }}
              >
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: provenance.tone.dot }} aria-hidden="true" />
                {provenance.dataThrough
                  ? `Latest completed MLB data: ${provenance.dataThrough}`
                  : 'No completed MLB data loaded'}
              </span>
              <span className="font-mono text-[11px] text-chalk500">{provenance.throughHint}</span>
            </div>
          )
        })()}
        <SyncStatusContent data={sync.data} loading={sync.loading} error={sync.error} />
      </section>

      {/* Scored pitcher inventory */}
      <section className="mb-6" aria-label="Scored pitcher inventory">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">Scored Pitcher Inventory</h2>
        <AvailabilityDashboardSummary summary={overview.data?.scored_pitcher_inventory} initialDetailsOpen />
      </section>

      {/* Operational context */}
      <OperationalReadinessSection
        v2State={v2BullpenState.data}
        v2Loading={v2BullpenState.loading}
        v2Error={v2BullpenState.error}
        onRetryV2={v2BullpenState.refetch}
        readinessState={teamOperationsReadiness.data}
        readinessLoading={teamOperationsReadiness.loading}
        readinessError={teamOperationsReadiness.error}
        onRetryReadiness={teamOperationsReadiness.refetch}
      />

      {/* Secondary exploratory study */}
      <section className="mb-6" aria-label="Exploratory fatigue insight">
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">Secondary Exploratory ERA Study</h2>
        <FatigueInsightCard embedded />
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
