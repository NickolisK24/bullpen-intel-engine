// The BaseballOS story feed — the browseable surface behind Today's briefing.
// The page normalizes backend-authored four-beat stories and keeps its
// browse/filter behavior local to this surface.

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
    label: 'Pressure',
    activeLabel: 'Pressure Stories',
    description: 'Pens that have been worked hard and are short on rest.',
  },
  {
    key: 'rested',
    label: 'Rest',
    activeLabel: 'Rest Stories',
    description: 'Pens with rested options and room to maneuver.',
  },
  {
    key: 'watch',
    label: 'Watch',
    activeLabel: 'Watch Stories',
    description: 'Pens quietly leaning on the same arms.',
  },
  {
    key: 'league',
    label: 'League',
    activeLabel: 'League Stories',
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
const STORY_FILTER_KEYS = new Set(STORY_FILTERS.map(option => option.key))

export const FEED_EMPTY_COPY = {
  all: 'No bullpen stories today.',
  stressed: 'No pressure stories today.',
  rested: 'No rest stories today.',
  watch: 'No watch stories today.',
  league: 'No league stories today.',
}

export const FEED_EMPTY_SUPPORT_COPY = 'Try another category or return to the full feed.'
export const FOUR_BEAT_STORIES_FALLBACK = 'No bullpen stories today.'

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

function normalizeStoryCategory(story, teamId) {
  if (STORY_FILTER_KEYS.has(story?.category) && story.category !== DEFAULT_STORY_FILTER) {
    return story.category
  }
  if (teamId == null) return 'league'
  return TONE_CATEGORY[story?.tone] || 'watch'
}

function normalizeFourBeatStory(story) {
  if (!story || typeof story !== 'object') return null
  const teamId = story.team_id ?? story.teamId ?? null
  const teamName = story.team_name || story.teamName || null
  const abbr = story.team_abbreviation || story.abbr || null
  const beats = Array.isArray(story.beats)
    ? story.beats
        .map(beat => ({
          key: beat?.key,
          label: beat?.label,
          text: typeof beat?.text === 'string' ? beat.text.trim() : '',
        }))
        .filter(beat => beat.key && beat.text)
    : []
  return {
    ...story,
    teamId,
    teamName,
    abbr,
    kicker: story.kicker || story.rule_label || 'Bullpen Story',
    tone: story.tone || 'watch',
    category: normalizeStoryCategory(story, teamId),
    title: story.title || story.signal || story.rule_label || 'Bullpen story',
    body: story.body || beats.map(beat => beat.text).join(' '),
    href: story.href || null,
    cta: story.cta || 'Open the team board',
    beats,
    source: 'backend_four_beat',
  }
}

export function getFourBeatStoryFeed(dashboard) {
  const payload = dashboard?.four_beat_stories || dashboard?.fourBeatStories
  const items = Array.isArray(payload?.items)
    ? payload.items.map(normalizeFourBeatStory).filter(Boolean)
    : []
  return {
    hasStories: items.length > 0,
    items,
    fallback: payload?.fallback || FOUR_BEAT_STORIES_FALLBACK,
    payload: payload || null,
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
