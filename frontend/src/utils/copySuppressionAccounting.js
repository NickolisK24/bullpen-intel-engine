// Temporary operator-visible accounting for suppressed public copy (FE-001 / #591).
//
// The backend now owns and guards the meaning-bearing public language on the
// State -> Why -> Evidence path, so the frontend should never need to withhold a
// governed sentence. A few refusal paths legitimately remain — a payload with no
// context at all, a Team State block that fails validation — and canonical trust
// rules require a refusal to be explicit rather than silent. Before this module,
// copy could vanish between the API response and the screen with nothing
// anywhere recording that it had.
//
// This is deliberately the smallest thing that satisfies that requirement:
//
//   * no UI, so nothing here can become a reader-facing surface;
//   * no network, no telemetry backend, no storage;
//   * no change to any public payload;
//   * an in-memory counter plus one console warning per distinct cause;
//   * readable and resettable from tests, which is what makes "the Why cannot
//     silently disappear" provable rather than asserted.
//
// It is meant to be deleted. Once production shows a sustained zero across the
// healthy surfaces, the remaining call sites can become hard refusals and this
// module goes with them.

const counts = new Map()
const warned = new Set()

const SAMPLE_LIMIT = 80

function keyFor({ surface, field, reason }) {
  return `${surface || 'unknown'}.${field || 'unknown'}.${reason || 'unspecified'}`
}

function truncate(sample) {
  if (typeof sample !== 'string') return null
  const trimmed = sample.trim()
  if (!trimmed) return null
  return trimmed.length > SAMPLE_LIMIT ? `${trimmed.slice(0, SAMPLE_LIMIT)}…` : trimmed
}

/**
 * Record that governed public copy was withheld.
 *
 * `sample` is truncated and only ever reaches the developer console — it is
 * never rendered, stored, or transmitted.
 */
export function recordCopySuppression({ surface, field, reason, sample } = {}) {
  const key = keyFor({ surface, field, reason })
  counts.set(key, (counts.get(key) || 0) + 1)

  if (!warned.has(key)) {
    warned.add(key)
    const detail = truncate(sample)
    // Operator channel only. Public copy is backend-owned and backend-guarded,
    // so reaching this line means a governed sentence did not make it to the
    // reader and someone should find out why.
    console.warn(
      `[BaseballOS] public copy withheld: ${key}${detail ? ` — ${detail}` : ''}`,
    )
  }

  return counts.get(key)
}

/** Current suppression counts, keyed `surface.field.reason`. Test/diagnostic use. */
export function getCopySuppressionCounts() {
  return Object.fromEntries(counts)
}

/** Total suppression events recorded. Zero is the expected healthy value. */
export function getCopySuppressionTotal() {
  let total = 0
  for (const value of counts.values()) total += value
  return total
}

/** Clear counters and the one-shot warning set. Test isolation. */
export function resetCopySuppressionCounts() {
  counts.clear()
  warned.clear()
}
