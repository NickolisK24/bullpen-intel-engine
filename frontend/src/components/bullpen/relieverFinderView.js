// Pure view-model for the Reliever Finder (/bullpen?view=pitchers). It keeps the
// finder's intent gating, neutral default order, and honest workload formatting
// testable without a live data fetch. No bullpen calculation, availability
// classification, or role authority lives here — the eligible population and its
// public availability status stay owned by the backend and the shared
// availability view.

import {
  AVAILABILITY_FILTERS,
  getAvailabilityStatusLabel,
  getRowAvailabilityStatus,
} from './availabilityView.js'

// The finder renders a broad reliever list only once the visitor has asked for
// something specific: a name search, a single team, or a single public
// availability status. Provenance-only params (source) never count as intent, so
// arriving from Today or a share link does not, by itself, expose the league.
export function computeFinderIntent({
  searchTerm = '',
  selectedTeam = null,
  availabilityFilter = 'ALL',
} = {}) {
  const hasSearchIntent = String(searchTerm || '').trim().length > 0
  const hasTeamIntent = selectedTeam != null
  const hasAvailabilityIntent = Boolean(availabilityFilter) && availabilityFilter !== 'ALL'
  return {
    hasSearchIntent,
    hasTeamIntent,
    hasAvailabilityIntent,
    hasIntent: hasSearchIntent || hasTeamIntent || hasAvailabilityIntent,
  }
}

// Full, unambiguous team name for the compact team select — never a bare city
// (ambiguous across co-located clubs) or an invented abbreviation.
export function getTeamOptionLabel(team) {
  if (!team || typeof team !== 'object') return ''
  return (
    team.team_name
    || team.teamName
    || team.team_abbreviation
    || team.teamAbbreviation
    || ''
  )
}

// The four canonical public availability statuses plus the neutral "all" option.
// The internal Avoid tier is folded into Unavailable upstream and never surfaces
// here as its own option.
export function getAvailabilityFilterOptions() {
  return AVAILABILITY_FILTERS.map(value => ({
    value,
    label: value === 'ALL' ? 'All statuses' : getAvailabilityStatusLabel(value),
  }))
}

// Case-insensitive, partial-name search across the reliever's name, team, and
// public availability wording — matching the population the backend already
// authorized, never a wider MLB pitcher list.
export function filterRelieverRowsBySearch(rows, searchTerm) {
  const normalized = String(searchTerm || '').trim().toLowerCase()
  const list = Array.isArray(rows) ? rows : []
  if (!normalized) return list
  return list.filter(row => {
    const haystack = [
      row?.pitcher?.full_name,
      row?.pitcher?.team_name,
      row?.pitcher?.team_abbreviation,
      getRowAvailabilityStatus(row),
      getAvailabilityStatusLabel(getRowAvailabilityStatus(row)),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(normalized)
  })
}

export const FINDER_SORTS = Object.freeze({
  NAME: 'name',
  PITCHES: 'pitches',
  REST: 'rest',
})

// Neutral default order: pitcher name A–Z. The finder must never open ranked by
// workload, which would read as a leaderboard.
export const DEFAULT_FINDER_SORT = FINDER_SORTS.NAME

function compareName(a, b) {
  const an = a?.pitcher?.full_name || ''
  const bn = b?.pitcher?.full_name || ''
  return an.localeCompare(bn)
}

// Missing workload facts stay missing: they are never coerced to zero for
// sorting. An unknown value always sorts to the end of an explicit workload or
// rest ordering, whichever direction the user chose.
function nullsLast(aValue, bValue, compare) {
  const aMissing = aValue == null
  const bMissing = bValue == null
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  return compare(aValue, bValue)
}

export function sortRelieverRows(rows, sortBy = DEFAULT_FINDER_SORT) {
  const list = Array.isArray(rows) ? [...rows] : []
  if (sortBy === FINDER_SORTS.PITCHES) {
    return list.sort((a, b) => {
      const byWorkload = nullsLast(
        a?.pitches_last_7_days,
        b?.pitches_last_7_days,
        (x, y) => y - x,
      )
      return byWorkload !== 0 ? byWorkload : compareName(a, b)
    })
  }
  if (sortBy === FINDER_SORTS.REST) {
    return list.sort((a, b) => {
      const byRest = nullsLast(
        a?.days_since_last_appearance,
        b?.days_since_last_appearance,
        (x, y) => x - y,
      )
      return byRest !== 0 ? byRest : compareName(a, b)
    })
  }
  return list.sort(compareName)
}

// A missing workload count reads as an em dash, never a fabricated zero.
export function formatWorkloadCount(value) {
  return value == null ? '—' : value
}

export function formatRestDays(value) {
  return value == null ? '—' : `${value}d`
}

// Plain-language description of the active order so the result list is never
// silently ranked — the reader always sees how the rows are ordered.
export function describeActiveSort(sortBy = DEFAULT_FINDER_SORT) {
  if (sortBy === FINDER_SORTS.PITCHES) return 'pitches, last 7 days (high to low)'
  if (sortBy === FINDER_SORTS.REST) return 'rest (fewest days since last outing first)'
  return 'pitcher name (A–Z)'
}
