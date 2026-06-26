import { completedGamesDataLine } from '../dashboard/syncStatusView'

// Shared presentation helpers for the Morning Bullpen Report homepage: neutral
// display tones, the team deep-link builder, and the masthead view-model.

// Neutral display tones shared across the homepage. Tones describe the
// situation being observed (stress / watch / rest), never quality.
export const HOME_TONES = {
  stress: { color: '#fca5a5', dot: '#ef4444', borderColor: 'rgba(239,68,68,0.35)', backgroundColor: 'rgba(239,68,68,0.06)' },
  watch: { color: '#fde047', dot: '#eab308', borderColor: 'rgba(234,179,8,0.35)', backgroundColor: 'rgba(234,179,8,0.06)' },
  rest: { color: '#6ee7b7', dot: '#10b981', borderColor: 'rgba(16,185,129,0.35)', backgroundColor: 'rgba(16,185,129,0.06)' },
  neutral: { color: '#8899aa', dot: '#8899aa', borderColor: 'rgba(136,153,170,0.30)', backgroundColor: 'rgba(136,153,170,0.05)' },
}

export const homeTone = (key) => HOME_TONES[key] || HOME_TONES.neutral

// Deep-link into the existing bullpen board, reusing the /bullpen?view= pattern
// the rest of the app already understands. source= identifies the homepage
// section for later UX analytics.
export function buildHomeTeamHref(entry, source = 'home') {
  const param = entry?.team_abbreviation || entry?.abbr
    || (entry?.team_id != null ? String(entry.team_id) : null)
    || (entry?.teamId != null ? String(entry.teamId) : null)
  if (!param) return null
  const query = new URLSearchParams({ view: 'board', team: param, source })
  return `/bullpen?${query.toString()}`
}

// ── Masthead ───────────────────────────────────────────────────────────────
export function getMastheadView(dashboard, now = new Date()) {
  const freshness = dashboard?.freshness || {}
  const dataLine = completedGamesDataLine(freshness.data_through)
  const isLive = freshness.is_current !== false
    && (freshness.sync_status === 'success' || freshness.sync_status === 'ok')
  return {
    editionDate: now.toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    }),
    dataLine: dataLine
      ? dataLine
      : 'Waiting on the first completed games',
    isLive,
  }
}

// Home "Tonight's Bullpen Picture" roster line. Reads the off-the-active-roster count from
// Roster Authority — the single source of roster truth (CRC). This count is invariant across
// board views; the legacy roster_status board summary it used to read (which was 0 on Home's
// default board regardless of reality) was retired in CRC-10.
export function getHomeRosterStatusLine(board) {
  const count = Number(board?.roster_authority?.counts?.inactive_roster_context_count || 0)
  if (!Number.isFinite(count) || count < 1) return 'None off the active roster'
  return `${count} off the active roster`
}
