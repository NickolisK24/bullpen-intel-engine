import { fmtDataDate } from './syncStatusView'

// Neutral tones per callout column — describing situations, never "good/bad".
const COLUMN_TONE = {
  constrained: { color: '#fca5a5', dot: '#ef4444' },
  available: { color: '#6ee7b7', dot: '#10b981' },
  monitoring: { color: '#fde047', dot: '#eab308' },
}

function entryLabel(entry) {
  return entry?.team_abbreviation || entry?.team_name || `Team ${entry?.team_id ?? ''}`.trim()
}

function mapEntries(list) {
  return (Array.isArray(list) ? list : []).map(entry => ({
    teamId: entry?.team_id,
    label: entryLabel(entry),
    teamName: entry?.team_name || null,
    available: Number(entry?.available) || 0,
    monitor: Number(entry?.monitor) || 0,
    restricted: Number(entry?.restricted) || 0,
    total: Number(entry?.total_relievers) || 0,
    pctAvailable: Number(entry?.pct_available) || 0,
    pctRestricted: Number(entry?.pct_restricted) || 0,
    healthLabel: entry?.health_label || null,
  }))
}

export function getLandscapeView(landscape) {
  if (!landscape) return { hasLandscape: false }
  const games = landscape.games || {}
  const dataState = games.data_state || 'unavailable'
  const asOfDate = fmtDataDate(games.as_of_date)

  let gamesLabel
  if (games.available === false || dataState === 'unavailable') {
    gamesLabel = games.message || 'Schedule context unavailable'
  } else if (games.is_today && games.today_count > 0) {
    gamesLabel = `${games.today_count} game${games.today_count === 1 ? '' : 's'} in today's stored data`
  } else {
    const count = games.as_of_count || 0
    gamesLabel = `No games in today's stored data · latest stored slate ${asOfDate || 'unavailable'} (${count} game${count === 1 ? '' : 's'})`
  }

  return {
    hasLandscape: true,
    referenceDate: fmtDataDate(landscape.reference_date),
    teamsEvaluated: Number(landscape.teams_evaluated) || 0,
    games: {
      available: games.available !== false,
      isToday: !!games.is_today,
      dataState,
      label: gamesLabel,
      asOfDate,
    },
    columns: [
      { key: 'constrained', title: 'Most constrained bullpen situations', metric: 'restricted',
        suffix: 'Avoid / Unavailable', tone: COLUMN_TONE.constrained, entries: mapEntries(landscape.constrained_bullpens) },
      { key: 'available', title: 'Most available bullpen situations', metric: 'available',
        suffix: 'Available Tonight', tone: COLUMN_TONE.available, entries: mapEntries(landscape.available_bullpens) },
      { key: 'monitoring', title: 'Monitoring concentration', metric: 'monitor',
        suffix: 'in Monitor', tone: COLUMN_TONE.monitoring, entries: mapEntries(landscape.monitoring_concentration) },
    ],
    notes: Array.isArray(landscape.notes) ? landscape.notes : [],
  }
}
