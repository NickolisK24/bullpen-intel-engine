import { formatConfidence } from '../availabilityView'
import { fmtDataDate } from '../../dashboard/syncStatusView'

const DATA_STATE_LABEL = {
  live: 'Live',
  historical: 'Historical',
  stale: 'Stale',
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

  return {
    hasContext: true,
    state,
    // Only a real stored game is "present"; no_game_found / unavailable are not.
    isPresent: ctx.available === true && state === 'stored_game_log',
    sourceLabel: ctx.source_label || 'Stored game-log context',
    dataState,
    dataStateLabel: DATA_STATE_LABEL[dataState] || 'Unknown',
    message: ctx.message || null,
    opponent: ctx.opponent || null,
    opponentAbbr: ctx.opponent_abbreviation || null,
    gameDate: fmtDataDate(ctx.game_date),
    confidenceLabel: formatConfidence(ctx.confidence),
    missingFields: missing,
    isToday: !!ctx.is_today,
  }
}
