import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getMethodology } from '../../utils/api'
import { LoadingPane, ErrorState, SectionHeader, Divider } from '../UI'
import { FeedbackCTA } from '../feedback/FeedbackLink'

const TIER_HEX = {
  LOW:      { bg: '#0f1f1a', border: '#10b981', text: '#34d399' },
  MODERATE: { bg: '#1f1c0f', border: '#fbbf24', text: '#fcd34d' },
  HIGH:     { bg: '#2a1a0f', border: '#fb923c', text: '#fdba74' },
  CRITICAL: { bg: '#2a0f0f', border: '#ef4444', text: '#fca5a5' },
}

function displayCopy(value) {
  return String(value ?? '')
    .replace(/\bgameLog endpoint\b/gi, 'game log feed')
    .replace(/\bendpoints\b/gi, 'data feeds')
    .replace(/\bendpoint\b/gi, 'data feed')
    .replace(/\bbackend\b/gi, 'BaseballOS service')
    .replace(/\bsnapshot\b/gi, 'read')
    .replace(/\bdeterministically\b/gi, 'consistently')
    .replace(/\bdeterministic\b/gi, 'consistent')
    .replace(/\bRecommendation V2\b/gi, 'BaseballOS read')
    .replace(/\bV[2-4]\b/gi, 'BaseballOS')
    .replace(/\bCOIN\b/gi, 'BaseballOS')
    .replace(/\brecommendation engine\b/gi, 'BaseballOS read')
    .replace(/\bgovernance layer\b/gi, 'review layer')
}

export default function Methodology() {
  const { data, loading, error, refetch } = useFetch(getMethodology)

  if (loading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto">
        <LoadingPane message="Loading methodology..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    )
  }

  return <MethodologyView data={data} />
}

export function MethodologyView({ data }) {
  const fe       = data?.fatigue_engine
  const insights = data?.insights
  const sources  = data?.data_sources ?? []
  const stack    = data?.stack ?? []

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-10">
      <SectionHeader
        title="Methodology"
        subtitle="How availability, workload, trust, and readiness reads are computed"
      />

      <section className="card p-5 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
        <div className="font-mono text-xs uppercase tracking-widest text-amber/75">
          Reliability Check
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
          BaseballOS checks whether availability tiers match real bullpen usage after games are completed. The live reliability read belongs in Data &amp; Trust so methodology stays focused on definitions and interpretation.
        </p>
        <Link
          to="/trust"
          className="mt-4 inline-flex rounded border border-amber/35 px-3 py-2 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:bg-amber/10"
        >
          View Data &amp; Trust
        </Link>
      </section>

      {/* ── Workload Read ──────────────────────────────────────────────── */}
      {fe && (
        <section
          className="card p-6 animate-fade-up opacity-0"
          style={{ animationDelay: '100ms', animationFillMode: 'forwards' }}
        >
          <div className="font-display text-2xl tracking-wider text-chalk100 mb-2">
            {displayCopy(fe.title)}
          </div>
          <p className="text-chalk300 text-sm leading-relaxed mb-6 max-w-3xl">
            {displayCopy(fe.summary)}
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
                    {displayCopy(c.name)}
                  </div>
                  <div className="text-chalk400 text-xs leading-relaxed">
                    {displayCopy(c.rationale)}
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
                    {displayCopy(t.interpretation)}
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
                  {displayCopy(fe.excluded.name)}
                </div>
                <div className="text-chalk400 text-xs leading-relaxed">
                  {displayCopy(fe.excluded.reason)}
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {/* ── Secondary Exploratory Insight ──────────────────────────────── */}
      {insights && (
        <section
          className="card p-6 animate-fade-up opacity-0"
          style={{ animationDelay: '200ms', animationFillMode: 'forwards' }}
        >
          <div className="font-display text-2xl tracking-wider text-chalk100 mb-2">
            {displayCopy(insights.title)}
          </div>
          <p className="text-chalk300 text-sm leading-relaxed mb-4 max-w-3xl">
            {displayCopy(insights.summary)}
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
              {displayCopy(insights.finding)}
            </div>
          </div>

          {insights.samples && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 mb-4 text-xs font-mono">
              <span className="text-chalk600 uppercase tracking-widest">Sample sizes:</span>
              {['LOW', 'MODERATE', 'HIGH', 'CRITICAL'].map((tier) => (
                <span key={tier} className="text-chalk400">
                  {tier} <span className="text-chalk200">n={(insights.samples[tier] ?? 0).toLocaleString()}</span>
                </span>
              ))}
            </div>
          )}

          {(insights.measured || insights.not_measured) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {insights.measured && (
                <div>
                  <div className="font-mono text-chalk400 text-xs uppercase tracking-widest mb-2">
                    What was measured
                  </div>
                  <ul className="space-y-1">
                    {insights.measured.map((m) => (
                      <li key={m} className="text-chalk400 text-xs leading-relaxed flex gap-2">
                        <span className="text-emerald-400">✓</span>{displayCopy(m)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {insights.not_measured && (
                <div>
                  <div className="font-mono text-chalk400 text-xs uppercase tracking-widest mb-2">
                    What was not measured
                  </div>
                  <ul className="space-y-1">
                    {insights.not_measured.map((m) => (
                      <li key={m} className="text-chalk400 text-xs leading-relaxed flex gap-2">
                        <span className="text-chalk600">—</span>{displayCopy(m)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {insights.caveat && (
            <div className="text-chalk500 text-xs leading-relaxed italic max-w-3xl">
              {displayCopy(insights.caveat)}
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
                    {displayCopy(s.use)}
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
                  {displayCopy(s)}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <FeedbackCTA
        eyebrow="Methodology Feedback"
        title="Questions or feedback on the methodology?"
        body="BaseballOS is being refined through real user feedback."
      />
    </div>
  )
}
