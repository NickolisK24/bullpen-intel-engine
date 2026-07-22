import { LoadingPane, ErrorState, EmptyState } from '../UI'
import {
  formatDateOnly,
  formatUtcDateTimeEt,
} from '../../utils/dateDisplay'
import { getAvailabilityStatusLabel, getPublicAvailabilityStatus } from '../bullpen/availabilityView'

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

// The backend keeps five internal availability tiers; the public vocabulary has
// four states, with the Avoid tier folded into Unavailable
// (getPublicAvailabilityStatus). Rendering the raw tiers produced two rows both
// labeled "Unavailable" (the Avoid rate and the strict-Unavailable rate). Merge
// tiers by their public status first — summing sample sizes and recomputing the
// next-day rate from the combined next-day appearances — so each public label
// appears exactly once with its sample size intact. This never invents a label:
// Monitor stays On Watch, and a genuine non-availability tier (were the backend
// to add one) would surface under its own public status, not Unavailable.
function mergeTiersByPublicStatus(tiers) {
  const order = []
  const groups = new Map()
  for (const tier of asArray(tiers)) {
    const publicStatus = getPublicAvailabilityStatus(tier.tier) || tier.tier
    let group = groups.get(publicStatus)
    if (!group) {
      group = { tier: tier.tier, n: 0, next_day_appearances: 0 }
      groups.set(publicStatus, group)
      order.push(publicStatus)
    }
    const n = Number(tier.n) || 0
    let appearances = Number(tier.next_day_appearances)
    if (!Number.isFinite(appearances)) {
      // Older stored rows may omit the raw next-day count; reconstruct it from
      // the stored rate so the merged percentage stays faithful to the data.
      const rate = Number.isFinite(Number(tier.next_day_rate))
        ? Number(tier.next_day_rate)
        : (Number(tier.next_day_rate_pct) || 0) / 100
      appearances = Math.round(rate * n)
    }
    group.n += n
    group.next_day_appearances += appearances
    // Keep the most-severe raw tier (Avoid then Unavailable arrive in tier order)
    // as the label/tone source, so the merged row reads and colors as Unavailable.
    group.tier = tier.tier
  }
  return order.map((publicStatus) => {
    const group = groups.get(publicStatus)
    const rate = group.n > 0 ? group.next_day_appearances / group.n : 0
    return {
      tier: group.tier,
      n: group.n,
      next_day_appearances: group.next_day_appearances,
      next_day_rate: rate,
      next_day_rate_pct: Math.round(rate * 1000) / 10,
    }
  })
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
  return formatUtcDateTimeEt(value, { includeDate: true }) || 'Not computed'
}

function formatDate(value) {
  return formatDateOnly(value, { month: 'long' }) || 'Not available'
}

function publicAvailabilityCopy(value) {
  return String(value || '')
    .replace(/\bAvoid\s+and\s+Unavailable\s+were\b/g, 'Unavailable was')
    .replace(/\bAvoid\s+and\s+Unavailable\b/g, 'Unavailable')
    .replace(/\bAvoid\s+or\s+Unavailable\b/g, 'Unavailable')
    .replace(/\bAvoid\b/g, 'Unavailable')
    .replace(/\bbacktest\b/gi, 'usage check')
}

// The framing block (title / summary / claim / caveat) is backend-supplied
// copy. It is quoted, never trusted: a framing string that reads as
// prediction, accuracy, betting, ranking, or internal tooling is withheld and
// the card falls back to its fixed descriptive copy — same pattern as the
// internal-language guards on the Today and Stories surfaces.
export const BLOCKED_FRAMING_COPY_PATTERN = new RegExp(
  `\\b(${[
    'predict\\w*', 'forecast\\w*', 'accura\\w*', 'probabilit\\w*', 'proves?',
    'odds', 'bet', 'bets', 'betting', 'wager\\w*', 'picks?', 'edge',
    'guarantee\\w*', 'rank\\w*', 'scores?', 'scored', 'model\\w*',
    'deterministic\\w*', 'endpoint\\w*', 'backend', 'governance', 'snapshot\\w*',
    'COIN', 'V[2-5]',
  ].join('|')})\\b`,
  'i',
)

export function publicFramingCopy(value) {
  const text = publicAvailabilityCopy(value)
  if (!text) return ''
  return BLOCKED_FRAMING_COPY_PATTERN.test(text) ? '' : text
}

const FALLBACK_CAVEAT =
  'Observed next-day relief usage on completed games. Descriptive context only — not a claim about future outings.'

function TierRateRow({ tier }) {
  const tone = TIER_TONES[tier.tier] || 'border-dirt bg-field/45 text-chalk300'
  return (
    <div className={`rounded border p-3 ${tone}`}>
      <div className="font-mono text-[10px] uppercase tracking-widest opacity-80">
        {getAvailabilityStatusLabel(tier.tier)}
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
  const tiers = mergeTiersByPublicStatus(window.tiers)
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
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
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
            Usage Check
          </div>
          <h2 className="mt-1 font-display text-2xl tracking-wider text-chalk100">
            {publicFramingCopy(framing.title) || 'Availability Tier Usage Check'}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
            {publicFramingCopy(framing.summary) || 'Stored next-day usage results are not available yet.'}
          </p>
        </div>
        <div className="rounded border border-dirt bg-field/60 px-3 py-2 font-mono text-[11px] text-chalk500">
          Computed {formatDateTime(data?.computed_at)}
        </div>
      </div>

      {loading ? (
        <LoadingPane message="Loading the usage check..." />
      ) : error ? (
        <ErrorState message="The usage check could not be loaded." onRetry={onRetry} />
      ) : data?.status !== 'ok' ? (
        <EmptyState
          icon="📊"
          title="Usage check not computed yet"
          subtitle="Stored next-day usage results will appear after the next scheduled data refresh."
        />
      ) : (
        <div className="space-y-4">
          {publicFramingCopy(framing.claim) && (
            <div className="rounded border border-emerald-400/25 bg-emerald-400/5 p-3 text-sm leading-relaxed text-emerald-100">
              {publicFramingCopy(framing.claim)}
            </div>
          )}

          {primary && <WindowPanel window={primary} />}
          {secondary.map((window) => (
            <WindowPanel key={window.season || window.label} window={window} />
          ))}

          <div className="rounded border border-dirt bg-chalk/20 p-3 text-xs leading-relaxed text-chalk500">
            {publicFramingCopy(framing.caveat) || FALLBACK_CAVEAT}
          </div>
        </div>
      )}
    </section>
  )
}
