import { useFetch } from '../../hooks/useFetch'
import { getFatigueEraInsight } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, EmptyState, StaleDataNotice } from '../UI'

// Inline hex — Tailwind purge can't drop these.
const LOWER_STYLE = {
  bg: '#0f1f1a',
  border: '#10b981',
  text: '#34d399',
  label: '#10b981',
}

const HIGHER_STYLE = {
  bg: '#2a1a0f',
  border: '#fb923c',
  text: '#fdba74',
  label: '#fb923c',
}

const TIER_ORDER = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

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
        next-outing ERA · {apps?.toLocaleString() ?? 0} appearances
      </div>
      {sublabel && (
        <div className="text-chalk500 text-[10px] font-mono mt-2 text-center">
          {sublabel}
        </div>
      )}
    </div>
  )
}

export default function FatigueInsightCard({ embedded = false }) {
  const { data, loading, error, staleWithError, refetch } = useFetch(getFatigueEraInsight)

  return (
    <div
      className={`${embedded ? 'p-4' : 'p-6 mb-8'} card animate-fade-up opacity-0`}
      style={{ animationDelay: '350ms', animationFillMode: 'forwards' }}
    >
      <SectionHeader
        title="Fatigue Score vs. Next-Outing ERA"
        subtitle="Exploratory · 2024–2025 MLB game logs · all pitchers"
      />

      {loading ? (
        <LoadingPane message="Loading insight..." />
      ) : error && !staleWithError ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : data?.status === 'not_generated' ? (
        <EmptyState
          icon="📊"
          title="Analysis not generated"
          subtitle={data.message}
        />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice
              compact
              message="This exploratory study is the last loaded result because the latest refresh failed."
              onRetry={refetch}
            />
          )}

          <p className="text-chalk100 text-base md:text-lg leading-relaxed font-mono mb-5">
            {data?.headline}
          </p>

          {data?.comparison?.pct_difference !== null &&
           data?.comparison?.pct_difference !== undefined && (
            <div className="flex items-baseline justify-center gap-3 mb-5">
              <div
                className="font-display text-5xl md:text-7xl tracking-wider leading-none"
                style={{ color: '#fb923c' }}
              >
                {data.comparison.pct_difference >= 0 ? '+' : ''}{data.comparison.pct_difference}%
              </div>
              <div className="text-chalk400 text-sm font-mono uppercase tracking-widest">
                higher next-outing ERA<br />
                <span className="text-chalk600 normal-case tracking-normal">observed association — not causal</span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <ComparisonCard
              label="Lower fatigue"
              era={data?.comparison?.baseline_era}
              apps={data?.comparison?.baseline_apps}
              sublabel="MODERATE tier (rested baseline)"
              style={LOWER_STYLE}
            />
            <ComparisonCard
              label="Higher fatigue"
              era={data?.comparison?.elevated_era}
              apps={data?.comparison?.elevated_apps}
              sublabel="HIGH + CRITICAL tiers"
              style={HIGHER_STYLE}
            />
          </div>

          {/* Sample size by tier — kept visible so sparse buckets are obvious. */}
          {data?.tiers && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 mb-4 text-xs font-mono">
              <span className="text-chalk600 uppercase tracking-widest">Sample sizes:</span>
              {TIER_ORDER.map((tier) => (
                <span key={tier} className="text-chalk400">
                  {tier} <span className="text-chalk200">n={(data.tiers[tier]?.appearances ?? 0).toLocaleString()}</span>
                </span>
              ))}
            </div>
          )}

          <div className="text-chalk500 text-[11px] font-mono leading-relaxed pt-3 border-t border-dirt">
            Exploratory, correlational analysis across {data?.total_appearances_analyzed?.toLocaleString() ?? 0} appearances
            (2024–2025). Not a controlled study and not causal. The buckets are not adjusted for pitcher role
            (starters vs. relievers), opponent quality, park, leverage, game state, or defense — and higher-fatigue
            outings skew toward higher-workload (starter-style) appearances. LOW and CRITICAL tiers are sparse
            (see sample sizes above). See the Methodology page for the full method and limitations.
          </div>
        </>
      )}
    </div>
  )
}
