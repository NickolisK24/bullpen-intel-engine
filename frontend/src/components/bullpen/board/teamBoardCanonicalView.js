// Team Board canonical migration adapter (Phase 4B.4).
//
// Behind VITE_USE_CANONICAL_TEAM_BOARD, the Team Board renders a single canonical
// story — the StoryCard, already on the canonical `/story` endpoint (Story
// Intelligence V1, now with trust-lane and bridge-instability parity) — and stops
// mounting the duplicate client-generated TeamBullpenStoryPanel. Default off: when
// off the board keeps its current behavior (StoryCard + legacy panel).
//
// This module only reads the flag and decides whether the legacy panel should
// mount. It creates no story content and never changes the canonical StoryCard,
// the board data surfaces, Home, or Stories.

export const CANONICAL_TEAM_BOARD_FLAG = 'VITE_USE_CANONICAL_TEAM_BOARD'

// Read the feature flag. Default is safe (off): only an explicit truthy value
// enables the canonical-only Team Board. `env` is injectable for tests.
export function canonicalTeamBoardEnabled(env) {
  let source = env
  if (source == null) {
    source = typeof import.meta !== 'undefined' ? import.meta.env : undefined
  }
  const raw = (source || {})[CANONICAL_TEAM_BOARD_FLAG]
  if (raw === true) return true
  const value = String(raw == null ? '' : raw).trim().toLowerCase()
  return value === 'true' || value === '1' || value === 'on' || value === 'yes'
}

// The canonical story is "unavailable" only when its fetch genuinely failed or
// returned nothing. A neutral/quiet canonical story (story_available: false) is a
// valid canonical response, not a failure — the StoryCard renders that state
// cleanly. `story` is the useFetch result { data, loading, error }.
export function canonicalTeamStoryUnavailable(story) {
  if (!story || typeof story !== 'object') return true
  if (story.error) return true
  if (story.loading) return false
  return story.data == null
}

// Decide whether the legacy TeamBullpenStoryPanel should mount.
//
//   baseShouldShow  — the existing condition for the panel (e.g. not the
//                     unavailable-only view mode). Always respected.
//   enabled         — VITE_USE_CANONICAL_TEAM_BOARD is on.
//   storyUnavailable — the canonical story fetch failed / returned nothing.
//
// Flag off  → legacy behavior (mount when baseShouldShow).
// Flag on   → hide the panel (canonical-only), unless the canonical story is
//             unavailable, in which case the legacy panel returns as a safe
//             fallback so the board is never left without a story.
export function shouldMountLegacyStoryPanel({ enabled, storyUnavailable, baseShouldShow }) {
  if (!baseShouldShow) return false
  if (!enabled) return true
  return Boolean(storyUnavailable)
}
