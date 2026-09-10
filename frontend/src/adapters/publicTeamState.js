// Canonical public Team State catalogue — validation and non-semantic tone only.
//
// The backend is the sole semantic owner of the internal-to-public Team State
// mapping (backend/services/team_state_public_vocabulary.py). Nothing in this
// file maps an internal readiness code, a bullpen-health state, a lane, a count,
// or a stress summary into a Team State. It only:
//
//   1. states the exact allowed public set so an unexpected value fails closed;
//   2. keys a purely visual tone off an already-decided canonical public state.
//
// Adding a fourth public Team State here is not possible without changing both
// lists below, which the contract tests pin against the backend authority.

export const PUBLIC_TEAM_STATE_CODES = Object.freeze(['fresh', 'stretched', 'vulnerable'])

export const PUBLIC_TEAM_STATE_LABELS = Object.freeze(['Fresh', 'Stretched', 'Vulnerable'])

// code -> label, used only to verify that a backend-supplied pair is internally
// consistent. This is not a mapping from any internal value.
const CANONICAL_LABEL_FOR_CODE = Object.freeze({
  fresh: 'Fresh',
  stretched: 'Stretched',
  vulnerable: 'Vulnerable',
})

// Non-semantic presentation only. State must stay understandable without color:
// every surface renders the canonical label as text, and the tone is decoration
// keyed by a state the backend already decided.
const PUBLIC_TEAM_STATE_TONE = Object.freeze({
  fresh: { borderColor: '#10b98155', backgroundColor: '#10b98112', color: '#6ee7b7', dot: '#10b981' },
  stretched: { borderColor: '#f9731655', backgroundColor: '#f9731612', color: '#fdba74', dot: '#f97316' },
  vulnerable: { borderColor: '#ef444455', backgroundColor: '#ef444412', color: '#fca5a5', dot: '#ef4444' },
})

// The one tone used whenever there is no Team State to show. It is deliberately
// neutral so a fail-closed read never reads as a fourth state.
export const NO_TEAM_STATE_TONE = Object.freeze({
  borderColor: 'rgba(148,163,184,0.32)',
  backgroundColor: 'rgba(148,163,184,0.09)',
  color: '#cbd5e1',
  dot: '#94a3b8',
})

// Used only when the backend omitted its own governed message.
export const TEAM_STATE_UNAVAILABLE_FALLBACK =
  'A current Team State read is not available for this bullpen.'

function textOrNull(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

export function isCanonicalTeamStateLabel(label) {
  return PUBLIC_TEAM_STATE_LABELS.includes(textOrNull(label))
}

/**
 * Read the backend-owned Team State block and fail closed on anything else.
 *
 * A Team State is rendered only when the backend said it is available AND the
 * supplied code/label pair is exactly one of the canonical pairs. A missing
 * block, an unsupported label, a mismatched pair, or a fail-closed outcome all
 * produce a label-less read carrying the backend's governed non-state message.
 * The raw value is never displayed and nothing is repaired locally.
 */
export function readPublicTeamState(teamState) {
  const block = teamState && typeof teamState === 'object' ? teamState : null
  const unavailableMessage =
    textOrNull(block?.unavailable_message) || TEAM_STATE_UNAVAILABLE_FALLBACK
  const unavailable = {
    available: false,
    publicState: null,
    publicLabel: null,
    summary: null,
    tone: NO_TEAM_STATE_TONE,
    unavailableMessage,
    dataThrough: textOrNull(block?.data_through),
    hasContract: Boolean(block),
  }

  if (!block || block.available !== true) return unavailable

  const publicState = textOrNull(block.public_state)
  const publicLabel = textOrNull(block.public_label)
  const summary = textOrNull(block.summary)
  if (!publicState || !PUBLIC_TEAM_STATE_CODES.includes(publicState)) return unavailable
  if (CANONICAL_LABEL_FOR_CODE[publicState] !== publicLabel) return unavailable

  return {
    available: true,
    publicState,
    publicLabel,
    summary,
    tone: PUBLIC_TEAM_STATE_TONE[publicState],
    unavailableMessage: null,
    dataThrough: textOrNull(block.data_through),
    hasContract: true,
  }
}
