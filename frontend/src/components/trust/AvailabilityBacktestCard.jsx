import { LoadingPane, ErrorState, EmptyState } from '../UI'

const TIER_TONES = {
  Available: 'border-emerald-400/35 bg-emerald-400/5 text-emerald-300',
  Monitor: 'border-sky-300/35 bg-sky-300/5 text-sky-200',
  Limited: 'border-amber/35 bg-amber/10 text-amber',
  Avoid: 'border-orange-400/35 bg-orange-400/10 text-orange-300',
  Unavailable: 'border-red-400/35 bg-red-400/10 text-red-300',
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function formatPct(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric.toFixed(1)}%`
}

function formatCount(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '0'
  return numeric.toLocaleString()
}

function formatDateTime(value) {
  if (!value) return 'Not computed'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatDate(value) {
  if (!value) return 'Not available'
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function TierRateRow({ tier }) {
  const tone = TIER_TONES[tier.tier] || 'border-dirt bg-field/45 text-chalk300'
  return (
    <div className={`rounded border p-3 ${tone}`}>
      <div className="font-mono text-[10px] uppercase tracking-widest opacity-80">
        {tier.tier}
      </div>
      <div className="mt-2 flex items-baseline justify-between gap-3">
        <span className="font-display text-3xl tracking-wide">
          {formatPct(tier.next_day_rate_pct)}
        </span>
        <span className="font-mono text-[11px] text-chalk400">
          n={formatCount(tier.n)}
        </span>
      </div>
      <div className="mt-1 text-[11px] leading-snug text-chalk500">
        next-day relief appearance rate
      </div>
    </div>
  )
}

function WindowPanel({ window }) {
  const tiers = asArray(window.tiers)
  const stability = window.stability || {}

  return (
    <section className="rounded border border-dirt bg-field/45 p-4" aria-label={`${window.label} backtest`}>
      <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="font-mono text-xs uppercase tracking-widest text-chalk300">
            {window.label}
          </div>
          <div className="mt-1 text-xs leading-relaxed text-chalk500">
            Data through {formatDate(window.data_through || window.window_end)}
          </div>
        </div>
        <div className="font-mono text-[11px] text-chalk500">
          No-appearance tier flips: {formatPct(stability.no_appearance_tier_flip_rate_pct)}
          {' '}({formatCount(stability.no_appearance_tier_flips)} / {formatCount(stability.no_appearance_days)})
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {tiers.map((tier) => (
          <TierRateRow key={tier.tier} tier={tier} />
        ))}
      </div>
    </section>
  )
}

export default function AvailabilityBacktestCard({
  data,
  loading = false,
  error = null,
  onRetry,
  embedded = false,
}) {
  const framing = data?.framing || {}
  const windows = asArray(data?.windows)
  const primary = windows.find(window => window.is_primary) || windows[0]
  const secondary = windows.filter(window => window !== primary)

  return (
    <section className={`${embedded ? 'p-4' : 'card mb-6 p-5'} animate-fade-up opacity-0`} style={{ animationFillMode: 'forwards' }}>
      <div className="mb-4 flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="font-mono text-xs uppercase tracking-widest text-amber/75">
            Operational Backtest
          </div>
          <h2 className="mt-1 font-display text-2xl tracking-wider text-chalk100">
            {framing.title || 'Availability Tier Usage Check'}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
            {framing.summary || 'Stored next-day usage results are not available yet.'}
          </p>
        </div>
        <div className="rounded border border-dirt bg-field/60 px-3 py-2 font-mono text-[11px] text-chalk500">
          Computed {formatDateTime(data?.computed_at)}
        </div>
      </div>

      {loading ? (
        <LoadingPane message="Loading operational backtest..." />
      ) : error ? (
        <ErrorState message="Operational backtest could not be loaded." onRetry={onRetry} />
      ) : data?.status !== 'ok' ? (
        <EmptyState
          icon="📊"
          title="Operational backtest not computed"
          subtitle="Stored backtest results will appear after the backtest refresh runs."
        />
      ) : (
        <div className="space-y-4">
          {framing.claim && (
            <div className="rounded border border-emerald-400/25 bg-emerald-400/5 p-3 text-sm leading-relaxed text-emerald-100">
              {framing.claim}
            </div>
          )}

          {primary && <WindowPanel window={primary} />}
          {secondary.map((window) => (
            <WindowPanel key={window.season || window.label} window={window} />
          ))}

          <div className="rounded border border-dirt bg-chalk/20 p-3 text-xs leading-relaxed text-chalk500">
            {framing.caveat}
          </div>
        </div>
      )}
    </section>
  )
}
