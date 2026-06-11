import { getBullpenStories } from '../home/homeIntelligenceView'

// The BaseballOS story feed — the browseable version of the Today story
// surfaces. Reuses the exact story derivation that powers the homepage and
// only adds a feed category on top so simple client-side filters work.
// No new signals, no new endpoints.

export const DEFAULT_STORY_FILTER = 'all'

export const STORY_FILTERS = [
  {
    key: DEFAULT_STORY_FILTER,
    label: 'All',
    activeLabel: 'All Stories',
    description: 'Every storyline BaseballOS is carrying today.',
  },
  {
    key: 'stressed',
    label: 'Stressed',
    activeLabel: 'Stressed Stories',
    description: 'Stories involving bullpens carrying elevated workload strain.',
  },
  {
    key: 'rested',
    label: 'Rested',
    activeLabel: 'Rested Stories',
    description: 'Stories involving bullpens entering the day with cleaner availability.',
  },
  {
    key: 'watch',
    label: 'Watch List',
    activeLabel: 'Watch List Stories',
    description: 'Stories where workload patterns are worth monitoring.',
  },
  {
    key: 'league',
    label: 'League Notes',
    activeLabel: 'League Notes',
    description: 'League-wide observations not tied to a single bullpen.',
  },
]

const STORY_FILTER_BY_KEY = Object.fromEntries(STORY_FILTERS.map(option => [option.key, option]))

// Feed categories ride on data the stories already carry: a story about a
// specific club is bucketed by its tone (stress / rest / watch); stories
// without a club are league notes.
const TONE_CATEGORY = {
  stress: 'stressed',
  rest: 'rested',
  watch: 'watch',
}

export const FEED_EMPTY_COPY = {
  all: 'No bullpen stories are active today.',
  stressed: 'No bullpen stories currently match the stressed filter.',
  rested: 'No rested bullpen stories are active today.',
  watch: 'No watch-list bullpen stories are active today.',
  league: 'No league-wide notes are active today.',
}

export const FEED_EMPTY_SUPPORT_COPY = 'Try another category or return to the full feed.'

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

export function getStoryFeed(dashboard, observations = null) {
  const stories = getBullpenStories(dashboard, observations)
  const items = stories.items.map(story => ({
    ...story,
    category: story.teamId == null
      ? 'league'
      : (TONE_CATEGORY[story.tone] || 'watch'),
  }))
  return { hasStories: items.length > 0, items, fallback: stories.fallback }
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
