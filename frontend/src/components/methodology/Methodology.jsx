import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getMethodology } from '../../utils/api'
import { ANALYTICS_EVENTS, trackAnalyticsEventOnce } from '../../utils/analytics'
import { LoadingPane, ErrorState, SectionHeader, Divider } from '../UI'
import { PUBLIC_BOUNDARIES } from '../../utils/publicBoundaries'

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
    .replace(/\bMonitor\b/g, 'On Watch')
    .replace(/\brestricted\b/g, 'limited')
    .replace(/\bRestricted\b/g, 'Limited')
    .replace(/\bconstrained\b/g, 'stretched')
    .replace(/\bConstrained\b/g, 'Stretched')
}

export default function Methodology() {
  const { data, loading, error, refetch } = useFetch(getMethodology)

  useEffect(() => {
    trackAnalyticsEventOnce(ANALYTICS_EVENTS.METHODOLOGY_VIEWED, {
      surface: 'methodology',
      route: '/methodology',
      source: 'page',
    })
  }, [])

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
  const sources  = data?.data_sources ?? []
  const stack    = data?.stack ?? []

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-10">
      <SectionHeader
        title="Methodology"
        subtitle="How availability, workload, trust, and readiness reads are computed"
      />

      <section id="methodology" className="card p-5 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
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

          {(fe.interpretation ?? []).length > 0 && (
            <>
              <Divider label="Public Read" />
              <ul className="mb-6 space-y-2 text-sm leading-relaxed text-chalk400">
                {fe.interpretation.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="text-amber" aria-hidden="true">&bull;</span>
                    <span>{displayCopy(item)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

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

      {/* ── Data Sources & Stack ───────────────────────────────────────── */}
      <section
        id="data-sources"
        className="card p-6 animate-fade-up opacity-0"
        style={{ animationDelay: '200ms', animationFillMode: 'forwards' }}
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

      <section
        id="known-limitations"
        className="card p-6 animate-fade-up opacity-0"
        style={{ animationDelay: '300ms', animationFillMode: 'forwards' }}
      >
        <div className="font-mono text-chalk400 text-xs uppercase tracking-widest mb-3">
          Known Limitations
        </div>
        <p className="max-w-3xl text-sm leading-relaxed text-chalk300">
          BaseballOS describes current bullpen context from public MLB data. It reads workload,
          availability, usage, and recent game context; it stays descriptive and evidence-backed.
        </p>
        <ul className="mt-4 space-y-2 text-sm leading-relaxed text-chalk400">
          {/* The boundary statements render from the canonical public boundary
              language so Methodology stays word-for-word aligned with About
              and How to Read. */}
          <li>{PUBLIC_BOUNDARIES.unknowns}</li>
          <li>
            Injury and injured-list context is limited to public roster and injury signals.{' '}
            {PUBLIC_BOUNDARIES.notHealthClaim}
          </li>
          <li>
            Freshness labels show the latest completed-game bullpen data available to the page.
          </li>
        </ul>
      </section>
    </div>
  )
}
