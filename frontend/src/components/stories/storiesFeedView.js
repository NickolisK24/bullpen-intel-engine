// The BaseballOS story feed — the browseable surface behind Today's briefing.
// The page normalizes backend-authored four-beat stories and keeps its
// browse/filter behavior local to this surface.

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
    description: "Pens where recent work is narrowing the manager's late-game choices.",
  },
  {
    key: 'rested',
    label: 'Rest',
    activeLabel: 'Rest Stories',
    description: "Pens where rested options are widening the manager's choices.",
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
  all: 'No bullpen story has enough movement yet today.',
  stressed: 'No team has enough recent workload strain for a pressure story today.',
  rested: 'No team has a standout recovery story yet today.',
  watch: 'No team is clearly leaning on the same arms today.',
  league: 'No league-wide bullpen movement stands out yet.',
}

export const FEED_EMPTY_SUPPORT_COPY = 'Return to the full feed or check back after the next completed games.'
export const FOUR_BEAT_STORIES_FALLBACK = 'No bullpen story has enough movement yet today.'

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
  const narrative = typeof story.narrative === 'string'
    ? story.narrative.trim()
    : (typeof story.story_body === 'string' ? story.story_body.trim() : '')
  const disclosureNote = typeof story.disclosure_note === 'string'
    ? story.disclosure_note.trim()
    : (typeof story.disclosureNote === 'string' ? story.disclosureNote.trim() : '')
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
    narrative,
    body: narrative || story.body || beats.map(beat => beat.text).join(' '),
    disclosureNote,
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
