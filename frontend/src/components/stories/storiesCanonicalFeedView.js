// Canonical Stories feed adapter (Phase 3).
//
// Maps the backend canonical story feed (dashboard.stories) into the exact
// `{ hasStories, items, fallback }` shape the Stories page already renders, so
// the page can read backend stories behind a feature flag instead of the legacy
// Four-Beat feed. Home and Stories then share one story source.
//
// This module only formats and presents backend-authored copy. It never invents
// story content: titles, narrative, and the league read come verbatim from the
// canonical payload; only short status labels and the league card framing are
// derived from structured fields.

export const CANONICAL_STORIES_PAGE_FLAG = 'VITE_USE_CANONICAL_STORIES_PAGE'

export const CANONICAL_STORIES_FALLBACK =
  'No bullpen story has enough movement yet today.'

// Read the feature flag. Default is safe (off): only an explicit truthy value
// enables canonical Stories. `env` is injectable for tests.
export function canonicalStoriesPageEnabled(env) {
  let source = env
  if (source == null) {
    source = typeof import.meta !== 'undefined' ? import.meta.env : undefined
  }
  const raw = (source || {})[CANONICAL_STORIES_PAGE_FLAG]
  if (raw === true) return true
  const value = String(raw == null ? '' : raw).trim().toLowerCase()
  return value === 'true' || value === '1' || value === 'on' || value === 'yes'
}

function canonicalFeed(dashboard) {
  const feed = dashboard?.stories
  return feed && typeof feed === 'object' ? feed : null
}

// Usable when the payload is present and carries an items array. A present-but-
// empty feed is still usable (the league card covers quiet days); only a missing
// or malformed payload falls back to the legacy Four-Beat feed.
export function hasUsableCanonicalStoriesFeed(dashboard) {
  const feed = canonicalFeed(dashboard)
  return Boolean(feed && Array.isArray(feed.items))
}

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

const VALID_TONES = new Set(['stress', 'rest', 'watch', 'neutral'])
function toneOf(item) {
  return VALID_TONES.has(item?.tone) ? item.tone : 'neutral'
}

const VALID_CATEGORIES = new Set(['stressed', 'rested', 'watch', 'league'])
function categoryOf(item) {
  return VALID_CATEGORIES.has(item?.category) ? item.category : 'watch'
}

const KICKER_BY_STORY_TYPE = {
  coverage_pressure: 'Carrying The Load',
  sustainability_question: 'Same Few Arms',
  depth_constraint: 'Thin Margin',
  route_change: 'Route Change',
  availability_depth: 'More Options',
}
function kickerOf(item) {
  return (
    KICKER_BY_STORY_TYPE[item?.story_type]
    || (item?.category === 'rested' ? 'More Options' : 'Bullpen Story')
  )
}

function teamHref(item) {
  const abbr = cleanText(item?.team_abbreviation)
  return abbr ? `/bullpen?view=board&team=${encodeURIComponent(abbr)}` : null
}

// Continuity -> the existing card "read" badge, for the noteworthy states only.
// This presents backend continuity metadata; it makes no baseball claim.
function continuityRead(continuity) {
  if (!continuity || continuity.compared === false) return null
  if (continuity.state === 'new') {
    return { display: 'New', detail: 'First appearance in the feed today.', tone: 'neutral' }
  }
  if (continuity.state === 'changed') {
    return { display: 'Updated', detail: 'The read on this bullpen changed since the previous briefing.', tone: 'watch' }
  }
  return null // ongoing / unchanged / resolved / unavailable: no badge
}

const LEAGUE_TONE_BY_MODE = {
  broadly_constrained: 'stress',
  availability_tightening: 'stress',
  pressure_concentrated: 'watch',
  depth_healthy: 'rest',
  availability_easing: 'rest',
  broadly_stable: 'neutral',
  neutral: 'neutral',
}
function leagueTone(mode) {
  return LEAGUE_TONE_BY_MODE[mode] || 'neutral'
}

// One canonical published story -> a Stories feed card (FeedStoryCard shape).
function toFeedCard(item) {
  return {
    teamId: item.team_id != null ? item.team_id : null,
    teamName: item.team_name || null,
    abbr: item.team_abbreviation || null,
    kicker: kickerOf(item),
    tone: toneOf(item),
    category: categoryOf(item),
    title: cleanText(item.headline) || 'Bullpen story',
    narrative: cleanText(item.narrative),
    body: cleanText(item.narrative),
    disclosureNote: null,
    href: teamHref(item),
    cta: 'Open the team board',
    read: continuityRead(item.continuity),
    continuity: item.continuity || null,
    source: 'canonical',
  }
}

// The league context -> a single league-lane card (page-level league read). It
// renders every day, including quiet days when no team story is publishable.
function leagueContextCard(league) {
  if (!league || typeof league !== 'object') return null
  return {
    teamId: null,
    teamName: null,
    abbr: null,
    kicker: 'League Note',
    tone: leagueTone(league.mode),
    category: 'league',
    title: cleanText(league.headline) || 'Around the league',
    narrative: cleanText(league.summary),
    body: cleanText(league.summary),
    disclosureNote: null,
    href: null,
    cta: null,
    read: null,
    mode: league.mode || null,
    dayClass: league.day_class || null,
    source: 'canonical_league',
  }
}

// The full canonical feed in the page's expected shape. Publishable team stories
// first, then the league card; suppressed stories are not rendered.
export function getCanonicalStoryFeed(dashboard) {
  const feed = canonicalFeed(dashboard)
  const rawItems = feed && Array.isArray(feed.items) ? feed.items : []
  const teamCards = rawItems
    .filter(item => item && item.story_available === true)
    .map(toFeedCard)
  const leagueCard = leagueContextCard(feed?.league_context)
  const items = leagueCard ? [...teamCards, leagueCard] : teamCards
  return {
    hasStories: items.length > 0,
    items,
    fallback: CANONICAL_STORIES_FALLBACK,
    source: 'canonical',
  }
}
