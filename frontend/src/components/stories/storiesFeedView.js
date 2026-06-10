import { getBullpenStories } from '../home/homeIntelligenceView'

// The BaseballOS story feed — the browseable version of the Today story
// surfaces. Reuses the exact story derivation that powers the homepage and
// only adds a feed category on top so simple client-side filters work.
// No new signals, no new endpoints.

export const STORY_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'stressed', label: 'Stressed' },
  { key: 'rested', label: 'Rested' },
  { key: 'watch', label: 'Watch List' },
  { key: 'league', label: 'League Notes' },
]

// Feed categories ride on data the stories already carry: a story about a
// specific club is bucketed by its tone (stress / rest / watch); stories
// without a club are league notes.
const TONE_CATEGORY = {
  stress: 'stressed',
  rest: 'rested',
  watch: 'watch',
}

export const FEED_EMPTY_COPY = {
  all: 'A quiet day in the bullpens — no stories in the feed this morning.',
  stressed: 'No pens are running hot right now — a quiet day on the stress front.',
  rested: 'No standout rested pens in today’s feed.',
  watch: 'The watch list is clear today.',
  league: 'No league notes today.',
}

export function getStoryFeed(dashboard, observations = null) {
  const stories = getBullpenStories(dashboard, observations)
  const items = stories.items.map(story => ({
    ...story,
    category: story.teamId == null
      ? 'league'
      : (TONE_CATEGORY[story.tone] || 'league'),
  }))
  return { hasStories: items.length > 0, items, fallback: stories.fallback }
}

export function filterStoryFeed(items, filter) {
  const list = Array.isArray(items) ? items : []
  if (!filter || filter === 'all') return list
  return list.filter(item => item.category === filter)
}

export function getFilterCounts(items) {
  const list = Array.isArray(items) ? items : []
  const counts = { all: list.length, stressed: 0, rested: 0, watch: 0, league: 0 }
  for (const item of list) {
    if (counts[item.category] != null) counts[item.category] += 1
  }
  return counts
}
