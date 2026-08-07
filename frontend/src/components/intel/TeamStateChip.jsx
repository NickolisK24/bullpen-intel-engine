// Canonical public Team State presentation.
//
// Data authority: the backend. This component consumes the already-validated
// output of `readPublicTeamState` and renders nothing else. It does not map an
// internal readiness value, does not infer a state from counts or lanes, and
// does not invent a fourth state — an unavailable read renders the backend's
// own governed non-state message.
//
// It is deliberately not a badge, a score, or a traffic light: the canonical
// label is rendered as text with a screen-reader-visible "Team State" prefix,
// and the tone keyed off the canonical state is decoration only. Meaning
// survives with color removed.

import { NO_TEAM_STATE_TONE } from '../../adapters/publicTeamState'

export function TeamStateChip({ teamState, className = '' }) {
  if (!teamState) return null

  const available = teamState.available === true
  const tone = teamState.tone || NO_TEAM_STATE_TONE

  if (!available) {
    return (
      <span
        className={`inline-flex items-center gap-2 text-[0.9375rem] font-semibold tracking-[-0.01em] ${className}`}
        style={{ color: tone.color }}
      >
        <span
          aria-hidden="true"
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: tone.dot }}
        />
        <span>No current state</span>
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-2 text-[0.9375rem] font-semibold tracking-[-0.01em] ${className}`}
      style={{ color: tone.color }}
    >
      <span
        aria-hidden="true"
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: tone.dot }}
      />
      <span className="sr-only">Team State: </span>
      <span>{teamState.publicLabel}</span>
    </span>
  )
}

// The full read: the canonical label when one is supplied, otherwise the
// backend's governed explanation of why there is no state to show. Used where
// there is room to say why rather than only that.
export function TeamStateRead({ teamState, className = '' }) {
  if (!teamState) return null
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-2 ${className}`}>
      <TeamStateChip teamState={teamState} />
      {teamState.available !== true && teamState.unavailableMessage && (
        <p className="bos-meta max-w-measure normal-case">
          {teamState.unavailableMessage}
        </p>
      )}
    </div>
  )
}

export default TeamStateChip
