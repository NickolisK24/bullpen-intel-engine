import { getBullpenStories } from '../home/homeIntelligenceView'

// The BaseballOS story feed — the browseable surface behind Today's briefing.
// The current path keeps its frontend derivation here; the comparison path
// normalizes backend-authored four-beat stories when they are present.

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
    description: 'Pens that have been worked hard and are short on rest.',
  },
  {
    key: 'rested',
    label: 'Rested',
    activeLabel: 'Rested Stories',
    description: 'Pens with rested options and room to maneuver.',
  },
  {
    key: 'watch',
    label: 'Watch List',
    activeLabel: 'Watch List Stories',
    description: 'Pens quietly leaning on the same arms.',
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
export const FOUR_BEAT_STORIES_FALLBACK = 'No four-beat bullpen stories are active today.'

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
    kicker: story.kicker || story.rule_label || 'Four Beat Story',
    tone: story.tone || 'watch',
    category: story.category || (story.tone === 'stress' ? 'stressed' : 'rested'),
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
