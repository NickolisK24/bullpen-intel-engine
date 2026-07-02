import { fmtDataDate } from './syncStatusView'

// Neutral tones per callout column — describing situations, never "good/bad".
const COLUMN_TONE = {
  constrained: { color: '#fca5a5', dot: '#ef4444' },
  available: { color: '#6ee7b7', dot: '#10b981' },
  monitoring: { color: '#fde047', dot: '#eab308' },
}

export const BULLPEN_LANDSCAPE_COLUMNS = [
  {
    key: 'available',
    sourceKey: 'available_bullpens',
    title: 'Most Available',
    subtitle: 'Most room to maneuver',
    metric: 'available',
    suffix: 'rested and available',
  },
  {
    key: 'monitoring',
    sourceKey: 'monitoring_concentration',
    title: 'On Watch',
    subtitle: 'Recent workload watch groups',
    metric: 'monitor',
    suffix: 'on watch',
  },
  {
    key: 'constrained',
    sourceKey: 'constrained_bullpens',
    title: 'Most Stretched',
    subtitle: 'Fewest clean late-inning options',
    metric: 'restricted',
    suffix: 'needing rest or unavailable',
  },
]

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
    teamAbbrev: entry?.team_abbreviation || null,
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
    gamesLabel = `Scheduled MLB games today: ${count} game${count === 1 ? '' : 's'}`
  } else if (asOfDate) {
    const count = games.as_of_count || 0
    gamesLabel = `Bullpen data through ${asOfDate} (${count} completed MLB game${count === 1 ? '' : 's'})`
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
    columns: BULLPEN_LANDSCAPE_COLUMNS.map(column => ({
      ...column,
      tone: COLUMN_TONE[column.key],
      entries: mapEntries(landscape[column.sourceKey]),
    })),
    notes: Array.isArray(landscape.notes) ? landscape.notes : [],
  }
}

// Tonight's Storylines — a compact, descriptive recap of current bullpen
// situations already present in the landscape data. This is storytelling, not a new
// analytics layer: every observation is derived from the same availability/workload
// counts that power the constrained/available/monitoring columns. No rankings,
// recommendations, predictions, or matchup advice — just plain baseball language.
export const STORYLINES_FALLBACK =
  'No bullpen story has enough movement in the current data yet.'

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
    items.push(`${storyTeamName(topConstrained)} has ${topConstrained.restricted} ${topConstrained.restricted === 1 ? 'reliever' : 'relievers'} needing rest or unavailable, narrowing the late-game margin.`)
  }

  const topAvailable = available[0]
  if (topAvailable && topAvailable.available > 0 && storyTeamName(topAvailable)) {
    items.push(`${storyTeamName(topAvailable)} has ${topAvailable.available} rested ${topAvailable.available === 1 ? 'reliever' : 'relievers'}, giving the manager more ways through the late innings.`)
  }

  const topMonitor = monitoring[0]
  if (topMonitor && topMonitor.monitor > 0 && storyTeamName(topMonitor)) {
    items.push(`${storyTeamName(topMonitor)} has ${topMonitor.monitor} ${topMonitor.monitor === 1 ? 'reliever' : 'relievers'} on watch, so recent work may still be leaning on the same group.`)
  }

  const stressedCount = constrained.filter(entry => entry.restricted > 0).length
  if (stressedCount >= 2) {
    items.push(`${capitalize(countWord(stressedCount))} clubs have at least one reliever needing rest or unavailable, which can tighten late-game choices.`)
  }

  const trimmed = items.slice(0, 4)
  return {
    hasStorylines: trimmed.length > 0,
    items: trimmed,
    fallback: STORYLINES_FALLBACK,
  }
}
