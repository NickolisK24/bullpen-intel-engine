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

// Deep-link a landscape team row into its bullpen board, reusing the existing
// /bullpen?view= deep-link pattern. Prefers the abbreviation (e.g. SF) and falls
// back to the numeric team id; source=landscape is passed for later UX analytics.
export function buildLandscapeTeamHref(entry) {
  const param = entry?.team_abbreviation || (entry?.team_id != null ? String(entry.team_id) : null)
  if (!param) return null
  const query = new URLSearchParams({ view: 'board', team: param, source: 'landscape' })
  return `/bullpen?${query.toString()}`
}

function mapEntries(list) {
  return (Array.isArray(list) ? list : []).map(entry => ({
    teamId: entry?.team_id,
    label: entryLabel(entry),
    teamName: entry?.team_name || null,
    teamHref: buildLandscapeTeamHref(entry),
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
    gamesLabel = games.message || 'Schedule data unavailable'
  } else if (games.is_today && games.today_count > 0) {
    const count = games.today_count
    gamesLabel = `Today's MLB slate: ${count} game${count === 1 ? '' : 's'}`
  } else if (asOfDate) {
    const count = games.as_of_count || 0
    gamesLabel = `Showing bullpen intelligence using latest completed MLB slate: ${asOfDate} (${count} game${count === 1 ? '' : 's'})`
  } else {
    gamesLabel = 'Schedule data unavailable'
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
        suffix: 'Available', tone: COLUMN_TONE.available, entries: mapEntries(landscape.available_bullpens) },
      { key: 'monitoring', title: 'Monitoring concentration', metric: 'monitor',
        suffix: 'in Monitor', tone: COLUMN_TONE.monitoring, entries: mapEntries(landscape.monitoring_concentration) },
    ],
    notes: Array.isArray(landscape.notes) ? landscape.notes : [],
  }
}

// Tonight's Storylines — a compact, descriptive recap of current bullpen
// situations already present in the landscape data. This is storytelling, not a new
// analytics layer: every observation is derived from the same availability/workload
// counts that power the constrained/available/monitoring columns. No rankings,
// recommendations, predictions, or matchup advice — just plain baseball language.
export const STORYLINES_FALLBACK =
  'No notable bullpen storylines available from the current dataset.'

const COUNT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six',
                     'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']

function countWord(n) {
  return COUNT_WORDS[n] || String(n)
}

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}

// Prefer the full club name for natural reading ("Chicago Cubs appears to have…"),
// falling back to the abbreviation when the name is unavailable.
function storyTeamName(entry) {
  return entry?.teamName || entry?.label || null
}

export function getStorylines(landscape) {
  if (!landscape) return { hasStorylines: false, items: [], fallback: STORYLINES_FALLBACK }

  const constrained = mapEntries(landscape.constrained_bullpens)
  const available = mapEntries(landscape.available_bullpens)
  const monitoring = mapEntries(landscape.monitoring_concentration)

  const items = []

  // Leaders mirror the ordering the dashboard already uses for each column, so
  // the storyline matches what a user would see when scanning that section.
  const topConstrained = constrained[0]
  if (topConstrained && topConstrained.restricted > 0 && storyTeamName(topConstrained)) {
    items.push(`${storyTeamName(topConstrained)} is carrying a constrained bullpen read today.`)
  }

  const topAvailable = available[0]
  if (topAvailable && topAvailable.available > 0 && storyTeamName(topAvailable)) {
    items.push(`${storyTeamName(topAvailable)} currently has a deep available-reliever group.`)
  }

  const topMonitor = monitoring[0]
  if (topMonitor && topMonitor.monitor > 0 && storyTeamName(topMonitor)) {
    items.push(`${storyTeamName(topMonitor)} shows a concentrated Monitor-arm read.`)
  }

  const stressedCount = constrained.filter(entry => entry.restricted > 0).length
  if (stressedCount >= 2) {
    items.push(`${capitalize(countWord(stressedCount))} clubs currently show elevated bullpen stress.`)
  }

  const trimmed = items.slice(0, 4)
  return {
    hasStorylines: trimmed.length > 0,
    items: trimmed,
    fallback: STORYLINES_FALLBACK,
  }
}
