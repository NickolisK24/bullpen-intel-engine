import { formatConfidence } from '../availabilityView'
import { fmtDataDate } from '../../dashboard/syncStatusView'

const DATA_STATE_LABEL = {
  live: 'Current',
  historical: 'Historical',
  stale: 'Not Current',
  unavailable: 'Unavailable',
}

// Longer, plain labels for the subordinate metadata row.
const DATA_STATE_LONG_LABEL = {
  live: 'Current Game Log',
  historical: 'Historical Game Log',
  stale: 'Game Log Not Current',
  unavailable: 'Unavailable',
}

const MISSING_FIELD_LABEL = {
  home_away: 'Home/away',
  scheduled_time: 'Scheduled time',
  opponent: 'Opponent',
}

export function getTeamGameContextView(ctx) {
  if (!ctx) return { hasContext: false }
  const state = ctx.state || 'unavailable'
  const dataState = ctx.data_state || 'unavailable'
  const missing = (Array.isArray(ctx.missing_fields) ? ctx.missing_fields : [])
    .map(field => MISSING_FIELD_LABEL[field] || field)

  const team = ctx.team || {}
  return {
    hasContext: true,
    state,
    // Only a real stored game is "present"; no_game_found / unavailable are not.
    isPresent: ctx.available === true && state === 'stored_game_log',
    sourceLabel: ctx.source_label || 'Stored game-log context',
    dataState,
    dataStateLabel: DATA_STATE_LABEL[dataState] || 'Unknown',
    dataStateLongLabel: DATA_STATE_LONG_LABEL[dataState] || 'Unknown',
    message: ctx.message || null,
    teamName: team.team_name || team.team_abbreviation || null,
    opponent: ctx.opponent || null,
    opponentAbbr: ctx.opponent_abbreviation || null,
    gameDate: fmtDataDate(ctx.game_date),
    confidenceLabel: formatConfidence(ctx.confidence),
    statusLabel: ctx.is_today ? 'Scheduled' : 'Final',
    missingFields: missing,
    isToday: !!ctx.is_today,
  }
}
