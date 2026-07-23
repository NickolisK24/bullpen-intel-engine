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

// Null-aware numeric parse: a missing, empty, or non-finite value is unknown
// (null), never silently coerced to zero. Only a genuine finite number — including
// an explicit 0 — survives. Every count and rate on this card flows through this.
function toNumber(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
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
      group = { tier: tier.tier, n: 0, appearances: 0, nKnown: true, appearancesKnown: true }
      groups.set(publicStatus, group)
      order.push(publicStatus)
    }
    const n = toNumber(tier.n)
    if (n == null) group.nKnown = false
    else group.n += n

    let appearances = toNumber(tier.next_day_appearances)
    if (appearances == null) {
      // Older stored rows may omit the raw next-day count. Reconstruct it only
      // when both a trustworthy stored rate and a known sample size are present,
      // so the merged percentage stays faithful; otherwise it stays unknown.
      const rate = toNumber(tier.next_day_rate)
      const ratePct = toNumber(tier.next_day_rate_pct)
      const effectiveRate = rate != null ? rate : (ratePct != null ? ratePct / 100 : null)
      if (effectiveRate != null && n != null) {
        appearances = Math.round(effectiveRate * n)
      }
    }
    if (appearances == null) group.appearancesKnown = false
    else group.appearances += appearances
    // Keep the most-severe raw tier (Avoid then Unavailable arrive in tier order)
    // as the label/tone source, so the merged row reads and colors as Unavailable.
    group.tier = tier.tier
  }
  return order.map((publicStatus) => {
    const group = groups.get(publicStatus)
    // Fail closed: if any folded source row is missing a required part, the
    // merged sample size or rate stays unknown rather than looking complete.
    const n = group.nKnown ? group.n : null
    const appearances = group.nKnown && group.appearancesKnown ? group.appearances : null
    const rate = n != null && appearances != null && n > 0 ? appearances / n : null
    return {
      tier: group.tier,
      n,
      next_day_appearances: appearances,
      next_day_rate_pct: rate == null ? null : Math.round(rate * 1000) / 10,
    }
  })
}

function formatPct(value) {
  const numeric = toNumber(value)
  // Unknown stays unknown; an impossible percentage fails closed rather than
  // rendering a misleading number. An explicit 0 remains 0.0%.
  if (numeric == null || numeric < 0 || numeric > 100) return '—'
  return `${numeric.toFixed(1)}%`
}

function formatCount(value) {
  const numeric = toNumber(value)
  // A missing count is an em dash, never a fabricated zero; an explicit 0 stays 0.
  if (numeric == null) return '—'
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
      <div className="mt-2 font-display text-3xl tracking-wide">
        {formatPct(tier.next_day_rate_pct)}
      </div>
      <div className="mt-1 text-[11px] leading-snug text-chalk500">
        pitched in relief the next day
      </div>
      <div className="mt-2 font-mono text-[11px] text-chalk400">
        Sample: {formatCount(tier.n)} pitcher-days
      </div>
    </div>
  )
}

function WindowPanel({ window }) {
  const tiers = mergeTiersByPublicStatus(window.tiers)

  return (
    <section className="rounded border border-dirt bg-field/45 p-4" aria-label={`${window.label} usage check`}>
      <div className="mb-3">
        <div className="font-mono text-xs uppercase tracking-widest text-chalk300">
          {window.label}
        </div>
        <div className="mt-1 text-xs leading-relaxed text-chalk500">
          Data through {formatDate(window.data_through || window.window_end)}
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
            How the labels matched next-day usage
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk400">
            After BaseballOS assigned each public workload label, how often did that
            reliever make a relief appearance the next day? Each rate below is a
            look back at completed games — descriptive context about what happened,
            not a claim about future outings or about who a manager will use.
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
