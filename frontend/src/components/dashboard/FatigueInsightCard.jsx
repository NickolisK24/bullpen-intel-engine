import { useFetch } from '../../hooks/useFetch'
import { getFatigueEraInsight } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, EmptyState } from '../UI'

// Inline hex — Tailwind purge can't drop these.
const RESTED_STYLE = {
  bg: '#0f1f1a',
  border: '#10b981',
  text: '#34d399',
  label: '#10b981',
}

const ELEVATED_STYLE = {
  bg: '#2a1a0f',
  border: '#fb923c',
  text: '#fdba74',
  label: '#fb923c',
}

function ComparisonCard({ label, era, apps, sublabel, style }) {
  const display = era !== null && era !== undefined ? era.toFixed(2) : '—'

  return (
    <div
      className="rounded-lg border p-6 flex flex-col items-center justify-center"
      style={{ backgroundColor: style.bg, borderColor: `${style.border}55` }}
    >
      <div
        className="font-mono text-xs uppercase tracking-widest mb-3"
        style={{ color: style.label }}
      >
        {label}
      </div>
      <div
        className="font-display text-6xl tracking-wider leading-none mb-2"
        style={{ color: style.text }}
      >
        {display}
      </div>
      <div className="text-chalk600 text-xs font-mono uppercase tracking-wider">
        ERA · {apps?.toLocaleString() ?? 0} appearances
      </div>
      {sublabel && (
        <div className="text-chalk500 text-[10px] font-mono mt-2 text-center">
          {sublabel}
        </div>
      )}
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

          {data?.comparison?.pct_difference !== null &&
           data?.comparison?.pct_difference !== undefined && (
            <div className="flex items-baseline justify-center gap-3 mb-6">
              <div
                className="font-display text-7xl md:text-8xl tracking-wider leading-none"
                style={{ color: '#fb923c' }}
              >
                +{data.comparison.pct_difference}%
              </div>
              <div className="text-chalk400 text-sm font-mono uppercase tracking-widest">
                ERA when fatigued
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <ComparisonCard
              label="Rested"
              era={data?.comparison?.baseline_era}
              apps={data?.comparison?.baseline_apps}
              sublabel="MODERATE fatigue tier"
              style={RESTED_STYLE}
            />
            <ComparisonCard
              label="Elevated"
              era={data?.comparison?.elevated_era}
              apps={data?.comparison?.elevated_apps}
              sublabel="HIGH or CRITICAL fatigue tier"
              style={ELEVATED_STYLE}
            />
          </div>

          <div className="text-chalk400 text-xs font-mono pt-3 border-t border-dirt">
            Based on {data?.total_appearances_analyzed?.toLocaleString() ?? 0} appearances across the 2024-2025 seasons
          </div>
        </>
      )}
    </div>
  )
}