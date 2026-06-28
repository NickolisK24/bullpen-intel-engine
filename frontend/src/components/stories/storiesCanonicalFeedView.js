// Canonical Stories feed adapter (Phase 3; canonical-only since Phase 5D).
//
// Maps the backend canonical story feed (dashboard.stories) into the exact
// `{ hasStories, items, fallback }` shape the Stories page renders. Home and
// Stories share this one canonical story source.
//
// This module only formats and presents backend-authored copy. It never invents
// story content: titles, narrative, and the league read come verbatim from the
// canonical payload; only short status labels and the league card framing are
// derived from structured fields.

export const CANONICAL_STORIES_FALLBACK =
  'No bullpen story has enough movement yet today.'
export const STORIES_LIMITATIONS_FALLBACK =
  'Stories are descriptive bullpen reads. BaseballOS does not know manager intent, bullpen phone activity, private medical availability, or final game-day decisions.'

const INTERNAL_STORIES_COPY_PATTERN =
  /\b(COIN|V2|V3|V4|deterministic|snapshot|endpoint|backend|recommendation engine|baseline distribution|governance layer|sample state|review state|sample intelligence|raw feed|canonical feed|model output|quality_status|suppression_reason|source)\b/i

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

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function limitationText(value) {
  if (typeof value === 'string') return cleanText(value)
  if (isObject(value)) {
    return cleanText(value.summary || value.text || value.body || value.label)
  }
  return ''
}

function cleanLimitations(values) {
  const raw = (Array.isArray(values) ? values : [])
    .map(limitationText)
    .filter(Boolean)
  const hasUnsafe = raw.some(text => INTERNAL_STORIES_COPY_PATTERN.test(text))
  if (raw.length === 0 || hasUnsafe) {
    return {
      items: [STORIES_LIMITATIONS_FALLBACK],
      source: 'fallback',
    }
  }
  return {
    items: [...new Set(raw)].slice(0, 4),
    source: 'payload',
  }
}

function combinedLimitations(feed, cards) {
  const feedLimitations = Array.isArray(feed?.limitations) ? feed.limitations : []
  const cardLimitations = cards.flatMap(card => (
    Array.isArray(card.limitations) ? card.limitations : []
  ))
  return cleanLimitations([...feedLimitations, ...cardLimitations])
}

function cleanFreshness(value) {
  return isObject(value) ? value : null
}

function sharedCardFreshness(cards) {
  const freshnessValues = cards
    .map(card => cleanFreshness(card.freshness))
    .filter(Boolean)
  if (freshnessValues.length === 0) return null
  const dataThroughValues = new Set(freshnessValues.map(item => cleanText(item.data_through)).filter(Boolean))
  if (dataThroughValues.size > 1) return null
  return freshnessValues[0]
}

function pageFreshness(dashboard, feed, cards) {
  return (
    cleanFreshness(dashboard?.freshness)
    || cleanFreshness(feed?.freshness)
    || sharedCardFreshness(cards)
  )
}

function qualityStatusOf(item) {
  const status = cleanText(item?.quality_status).toLowerCase()
  if (['published', 'review', 'suppressed', 'neutral'].includes(status)) return status
  return null
}

function isRenderableStory(item) {
  if (!item || item.story_available !== true) return false
  const status = qualityStatusOf(item)
  return status !== 'suppressed' && status !== 'neutral'
}

function reviewNoteOf(item) {
  return qualityStatusOf(item) === 'review'
    ? {
        label: 'Under review',
        helper: 'Shown as a developing read while BaseballOS continues checking the signal.',
      }
    : null
}

function storyIdentity(value) {
  const teamId = Number(value?.team_id ?? value?.teamId)
  const storyType = cleanText(value?.story_type ?? value?.storyType)
  if (!Number.isInteger(teamId) || !storyType) return null
  return { teamId, storyType }
}

function storyMatchesIdentity(story, identity) {
  if (!identity) return false
  const candidate = storyIdentity(story)
  return Boolean(
    candidate
    && candidate.teamId === identity.teamId
    && candidate.storyType === identity.storyType
  )
}

function todayFlagshipIdentity(dashboard, feed, explicit) {
  return storyIdentity(explicit)
    || storyIdentity(feed?.today_flagship)
    || storyIdentity(feed?.todayFlagship)
    || storyIdentity(feed?.flagship_story)
    || storyIdentity(dashboard?.today_flagship)
    || storyIdentity(dashboard?.todayFlagship)
}

function deemphasizeTodayMatch(cards, identity) {
  if (!identity || cards.length < 2) {
    return { items: cards, deEmphasized: false }
  }
  const matched = []
  const others = []
  for (const card of cards) {
    if (storyMatchesIdentity(card, identity)) matched.push(card)
    else others.push(card)
  }
  if (matched.length === 0 || others.length === 0) {
    return { items: cards, deEmphasized: false }
  }
  return { items: [...others, ...matched], deEmphasized: true }
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
  trust_lane: 'Trust Lane',
  bridge: 'Fragile Bridge',
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
  const limitations = Array.isArray(item?.limitations)
    ? item.limitations.map(limitationText).filter(Boolean)
    : []
  return {
    storyId: item.story_id || null,
    storyType: item.story_type || null,
    teamId: item.team_id != null ? item.team_id : null,
    teamName: item.team_name || null,
    abbr: item.team_abbreviation || null,
    kicker: kickerOf(item),
    tone: toneOf(item),
    category: categoryOf(item),
    title: cleanText(item.headline) || 'Bullpen story',
    narrative: cleanText(item.narrative),
    body: cleanText(item.narrative),
    blueprint: Array.isArray(item.blueprint) ? item.blueprint : [],
    disclosureNote: null,
    href: teamHref(item),
    cta: 'Open the team board',
    read: continuityRead(item.continuity),
    continuity: item.continuity || null,
    freshness: cleanFreshness(item.freshness),
    limitations,
    qualityStatus: qualityStatusOf(item),
    reviewNote: reviewNoteOf(item),
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
    freshness: cleanFreshness(league.freshness),
    limitations: Array.isArray(league.limitations)
      ? league.limitations.map(limitationText).filter(Boolean)
      : [],
    qualityStatus: qualityStatusOf(league),
    reviewNote: reviewNoteOf(league),
    source: 'canonical_league',
  }
}

// The full canonical feed in the page's expected shape. Publishable team stories
// first, then the league card; suppressed stories are not rendered.
export function getCanonicalStoryFeed(dashboard, options = {}) {
  const feed = canonicalFeed(dashboard)
  const rawItems = feed && Array.isArray(feed.items) ? feed.items : []
  const teamCards = rawItems
    .filter(isRenderableStory)
    .map(toFeedCard)
  const leagueCard = leagueContextCard(feed?.league_context)
  const withLeague = leagueCard ? [...teamCards, leagueCard] : teamCards
  const identity = todayFlagshipIdentity(dashboard, feed, options.todayFlagship)
  const { items, deEmphasized } = deemphasizeTodayMatch(withLeague, identity)
  const limitations = combinedLimitations(feed, items)
  return {
    hasStories: items.length > 0,
    items,
    fallback: CANONICAL_STORIES_FALLBACK,
    freshness: pageFreshness(dashboard, feed, items),
    limitations: limitations.items,
    limitationsSource: limitations.source,
    todayFlagshipDeemphasized: deEmphasized,
    source: 'canonical',
  }
}

export function storiesTextHasInternalLanguage(value) {
  return INTERNAL_STORIES_COPY_PATTERN.test(String(value || ''))
}
