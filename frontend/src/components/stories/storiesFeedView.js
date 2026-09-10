// Shared browse/filter utilities for the BaseballOS Stories feed — the filter
// definitions, active labels, counts, and empty states the canonical Stories
// page (storiesCanonicalFeedView) renders with.

export const DEFAULT_STORY_FILTER = 'all'

export const STORY_FILTERS = [
  {
    key: DEFAULT_STORY_FILTER,
    label: 'All',
    activeLabel: 'All Stories',
    description: 'Every bullpen story with enough movement to explain today.',
  },
  {
    key: 'stressed',
    label: 'Pressure',
    activeLabel: 'Pressure Stories',
    description: 'Pens where recent work is narrowing late-game choices for the manager.',
  },
  {
    key: 'rested',
    label: 'Rest',
    activeLabel: 'Rest Stories',
    description: 'Pens where rested options are widening choices for the manager.',
  },
  {
    key: 'watch',
    label: 'Watch',
    activeLabel: 'Watch Stories',
    description: 'Pens where the same arms may be absorbing more recent work.',
  },
  {
    key: 'league',
    label: 'League',
    activeLabel: 'League Stories',
    description: 'League-wide bullpen movement not tied to a single club.',
  },
]

const STORY_FILTER_BY_KEY = Object.fromEntries(STORY_FILTERS.map(option => [option.key, option]))

export const FEED_EMPTY_COPY = {
  all: 'No bullpen story has enough movement yet today.',
  stressed: 'No team has enough recent workload strain for a pressure story today.',
  rested: 'No team has a standout recovery story yet today.',
  watch: 'No team is clearly leaning on the same arms today.',
  league: 'No league-wide bullpen movement stands out yet.',
}

export const FEED_EMPTY_SUPPORT_COPY = 'Return to the full feed or check back after the next completed games.'

export function normalizeStoryFilter(filter) {
  return STORY_FILTER_BY_KEY[filter] ? filter : DEFAULT_STORY_FILTER
}

export function getStoryFilterOption(filter) {
  return STORY_FILTER_BY_KEY[normalizeStoryFilter(filter)]
}

export function getActiveStoryFilterLabel(filter, count) {
  const option = getStoryFilterOption(filter)
  return `${option.activeLabel} (${Number.isFinite(count) ? count : 0})`
}

export function getFeedEmptyState(filter) {
  const normalized = normalizeStoryFilter(filter)
  return {
    filter: normalized,
    title: FEED_EMPTY_COPY[normalized],
    body: FEED_EMPTY_SUPPORT_COPY,
    resetFilter: DEFAULT_STORY_FILTER,
  }
}

export function filterStoryFeed(items, filter) {
  const list = Array.isArray(items) ? items : []
  const normalized = normalizeStoryFilter(filter)
  if (normalized === DEFAULT_STORY_FILTER) return list
  return list.filter(item => item.category === normalized)
}

export function getFilterCounts(items) {
  const list = Array.isArray(items) ? items : []
  const counts = { all: list.length, stressed: 0, rested: 0, watch: 0, league: 0 }
  for (const item of list) {
    if (counts[item.category] != null) counts[item.category] += 1
  }
  return counts
}
