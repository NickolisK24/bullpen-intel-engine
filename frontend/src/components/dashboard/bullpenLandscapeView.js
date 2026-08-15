import { DATA_THROUGH_LABEL } from '../../utils/bullpenConcepts'
import { fmtDataDate } from './syncStatusView'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
import { readPublicTeamState } from '../../adapters/publicTeamState'

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
    title: 'Rested & Available',
    subtitle: 'Clubs shown with rested, available depth',
    metric: 'available',
    suffix: 'rested and available',
  },
  {
    key: 'monitoring',
    sourceKey: 'monitoring_concentration',
    title: 'On Watch',
    subtitle: 'Clubs shown with recent workload watch groups',
    metric: 'monitor',
    suffix: 'on watch',
  },
  {
    key: 'constrained',
    sourceKey: 'constrained_bullpens',
    title: 'Needs Rest / Unavailable',
    subtitle: 'Clubs shown with tighter late-inning options',
    metric: 'restricted',
    suffix: 'needing rest or unavailable',
  },
]

function entryLabel(entry) {
  return entry?.team_name || entry?.team_abbreviation || `Team ${entry?.team_id ?? ''}`.trim()
}

function numberOrNull(value) {
  if (value == null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

// Deep-link a landscape team row into its bullpen board, reusing the existing
// /bullpen?view= deep-link pattern. Prefers the abbreviation (e.g. SF) and falls
// back to the numeric team id; source=landscape preserves navigation context.
export function buildLandscapeTeamHref(entry) {
  if (!entry?.team_abbreviation && entry?.team_id == null) return null
  return buildTeamBoardHref(entry, { source: 'landscape' })
}

function mapEntries(list) {
  return (Array.isArray(list) ? list : []).map(entry => ({
    teamId: entry?.team_id,
    teamAbbrev: entry?.team_abbreviation || null,
    label: entryLabel(entry),
    teamName: entry?.team_name || null,
    teamHref: buildLandscapeTeamHref(entry),
    available: numberOrNull(entry?.available),
    monitor: numberOrNull(entry?.monitor),
    restricted: numberOrNull(entry?.restricted),
    total: numberOrNull(entry?.total_relievers),
    pctAvailable: numberOrNull(entry?.pct_available),
    pctRestricted: numberOrNull(entry?.pct_restricted),
    healthLabel: entry?.health_label || null,
    // Backend-owned canonical Team State, validated and failed closed. The lane a
    // team sits in is league orientation and is never read as its Team State.
    teamState: readPublicTeamState(entry?.team_state),
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
    const count = numberOrNull(games.as_of_count)
    gamesLabel = count == null
      ? `${DATA_THROUGH_LABEL} ${asOfDate} (completed MLB games)`
      : `${DATA_THROUGH_LABEL} ${asOfDate} (${count} completed MLB game${count === 1 ? '' : 's'})`
  } else {
    gamesLabel = 'Schedule data unavailable'
  }

  return {
    hasLandscape: true,
    referenceDate: fmtDataDate(landscape.reference_date),
    teamsEvaluated: numberOrNull(landscape.teams_evaluated),
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

// Storylines are backend-authored public copy. Preserve the supplied sentences
// verbatim and fail closed when the endpoint does not publish them; lane counts
// are never turned into new league prose in the browser.
export function getStorylines(landscape) {
  const source = Array.isArray(landscape?.storylines) ? landscape.storylines : []
  const items = source
    .map(item => typeof item === 'string'
      ? item
      : item?.public_text || item?.storyline || item?.text || null)
    .filter(item => typeof item === 'string' && item.trim())
    .slice(0, 4)
  return {
    hasStorylines: items.length > 0,
    items,
  }
}
