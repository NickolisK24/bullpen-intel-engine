import { useFetch } from '../../hooks/useFetch'
import { getFatigueEraInsight } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, EmptyState } from '../UI'

// Inline hex backgrounds — Tailwind purge can't drop these.
const TIER_STYLE = {
  LOW:      { bg: '#0f1f1a', border: '#10b981', text: '#34d399', label: '#10b981' },
  MODERATE: { bg: '#1f1c0f', border: '#fbbf24', text: '#fcd34d', label: '#fbbf24' },
  HIGH:     { bg: '#2a1a0f', border: '#fb923c', text: '#fdba74', label: '#fb923c' },
  CRITICAL: { bg: '#2a0f0f', border: '#ef4444', text: '#fca5a5', label: '#ef4444' },
}

const TIERS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

function TierCell({ tier, era, sample }) {
  const style = TIER_STYLE[tier]
  const display = era !== null && era !== undefined ? era.toFixed(2) : '—'

  return (
    <div
      className="rounded-lg border p-4 flex flex-col items-center justify-center"
      style={{ backgroundColor: style.bg, borderColor: `${style.border}55` }}
    >
      <div
        className="font-mono text-xs uppercase tracking-widest mb-2"
        style={{ color: style.label }}
      >
        {tier}
      </div>
      <div
        className="font-display text-4xl tracking-wider leading-none"
        style={{ color: style.text }}
      >
        {display}
      </div>
      <div className="text-chalk600 text-xs font-mono mt-2">
        ERA · {sample ?? 0} apps
      </div>
    </div>
  )
}

export default function FatigueInsightCard() {
  const { data, loading, error, refetch } = useFetch(getFatigueEraInsight)

  return (
    <div
      className="card p-6 mb-8 animate-fade-up opacity-0"
      style={{ animationDelay: '350ms', animationFillMode: 'forwards' }}
    >
      <SectionHeader
        title="FATIGUE COSTS RUNS"
        subtitle="2024-2025 reliever data"
      />

      {loading ? (
        <LoadingPane message="Loading insight..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : data?.status === 'not_generated' ? (
        <EmptyState
          icon="📊"
          title="Analysis not generated"
          subtitle={data.message}
        />
      ) : (
        <>
          <p className="text-chalk100 text-lg md:text-xl leading-relaxed font-mono mb-6">
            {data?.headline}
          </p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            {TIERS.map((tier) => {
              const t = data?.tiers?.[tier] || {}
              return (
                <TierCell
                  key={tier}
                  tier={tier}
                  era={t.era}
                  sample={t.appearances}
                />
              )
            })}
          </div>

          <div className="text-chalk400 text-xs font-mono pt-3 border-t border-dirt">
            Based on {data?.total_appearances_analyzed ?? 0} appearances across the 2024-2025 seasons
          </div>
        </>
      )}
    </div>
  )
}
