import { useFetch } from '../../hooks/useFetch'
import { getMethodology } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, Divider } from '../UI'

const TIER_HEX = {
  LOW:      { bg: '#0f1f1a', border: '#10b981', text: '#34d399' },
  MODERATE: { bg: '#1f1c0f', border: '#fbbf24', text: '#fcd34d' },
  HIGH:     { bg: '#2a1a0f', border: '#fb923c', text: '#fdba74' },
  CRITICAL: { bg: '#2a0f0f', border: '#ef4444', text: '#fca5a5' },
}

export default function Methodology() {
  const { data, loading, error, refetch } = useFetch(getMethodology)

  if (loading) {
    return (
      <div className="p-8 max-w-5xl mx-auto">
        <LoadingPane message="Loading methodology..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8 max-w-5xl mx-auto">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    )
  }

  const fe       = data?.fatigue_engine
  const insights = data?.insights
  const sources  = data?.data_sources ?? []
  const stack    = data?.stack ?? []

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-10">
      <SectionHeader
        title="Methodology"
        subtitle="How every number on the dashboard was computed"
      />

      {/* ── Fatigue Engine ─────────────────────────────────────────────── */}
      {fe && (
        <section
          className="card p-6 animate-fade-up opacity-0"
          style={{ animationDelay: '100ms', animationFillMode: 'forwards' }}
        >
          <div className="font-display text-2xl tracking-wider text-chalk100 mb-2">
            {fe.title}
          </div>
          <p className="text-chalk300 text-sm leading-relaxed mb-6 max-w-3xl">
            {fe.summary}
          </p>

          <Divider label="Components" />
          <div className="space-y-3 mb-6">
            {(fe.components ?? []).map((c) => (
              <div
                key={c.name}
                className="flex items-start gap-4 p-4 rounded border border-dirt bg-chalk/20"
              >
                <div className="font-mono text-amber text-sm w-12 shrink-0">
                  {c.weight}
                </div>
                <div>
                  <div className="font-mono text-chalk100 text-sm font-semibold mb-1">
                    {c.name}
                  </div>
                  <div className="text-chalk400 text-xs leading-relaxed">
                    {c.rationale}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <Divider label="Risk Tiers" />
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
            {(fe.risk_tiers ?? []).map((t) => {
              const style = TIER_HEX[t.level] ?? TIER_HEX.MODERATE
              return (
                <div
                  key={t.level}
                  className="rounded border p-4"
                  style={{
                    backgroundColor: style.bg,
                    borderColor:     `${style.border}55`,
                  }}
                >
                  <div
                    className="font-mono text-xs uppercase tracking-widest mb-1"
                    style={{ color: style.border }}
                  >
                    {t.level}
                  </div>
                  <div
                    className="font-display text-2xl tracking-wider mb-2"
                    style={{ color: style.text }}
                  >
                    {t.range}
                  </div>
                  <div className="text-chalk400 text-xs leading-relaxed">
                    {t.interpretation}
                  </div>
                </div>
              )
            })}
          </div>

          {fe.excluded && (
            <>
              <Divider label="Excluded Component" />
              <div className="p-4 rounded border border-dirt bg-chalk/10">
                <div className="font-mono text-chalk100 text-sm font-semibold mb-2">
                  {fe.excluded.name}
                </div>
                <div className="text-chalk400 text-xs leading-relaxed">
                  {fe.excluded.reason}
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {/* ── Insights ───────────────────────────────────────────────────── */}
      {insights && (
        <section
          className="card p-6 animate-fade-up opacity-0"
          style={{ animationDelay: '200ms', animationFillMode: 'forwards' }}
        >
          <div className="font-display text-2xl tracking-wider text-chalk100 mb-2">
            {insights.title}
          </div>
          <p className="text-chalk300 text-sm leading-relaxed mb-4 max-w-3xl">
            {insights.summary}
          </p>

          <div
            className="p-4 rounded border-l-2 mb-4"
            style={{
              backgroundColor: '#2a1a0f',
              borderLeftColor: '#fb923c',
            }}
          >
            <div className="font-mono text-amber text-xs uppercase tracking-widest mb-2">
              Finding
            </div>
            <div className="text-chalk100 text-sm leading-relaxed">
              {insights.finding}
            </div>
          </div>

          {insights.caveat && (
            <div className="text-chalk500 text-xs leading-relaxed italic max-w-3xl">
              {insights.caveat}
            </div>
          )}
        </section>
      )}

      {/* ── Data Sources & Stack ───────────────────────────────────────── */}
      <section
        className="card p-6 animate-fade-up opacity-0"
        style={{ animationDelay: '300ms', animationFillMode: 'forwards' }}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <div className="font-mono text-chalk400 text-xs uppercase tracking-widest mb-3">
              Data Sources
            </div>
            <div className="space-y-2">
              {sources.map((s) => (
                <div key={s.name} className="text-sm">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-amber hover:underline"
                  >
                    {s.name}
                  </a>
                  <div className="text-chalk400 text-xs mt-0.5 leading-relaxed">
                    {s.use}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="font-mono text-chalk400 text-xs uppercase tracking-widest mb-3">
              Stack
            </div>
            <div className="flex flex-wrap gap-2">
              {stack.map((s) => (
                <span
                  key={s}
                  className="px-2 py-1 rounded font-mono text-xs"
                  style={{
                    backgroundColor: '#1a1f26',
                    color:           '#d1dce8',
                    border:          '1px solid #242b35',
                  }}
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}