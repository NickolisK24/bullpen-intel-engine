// Canonical Home stories adapter (Phase 2).
//
// Maps the backend canonical story feed (dashboard.stories) into the exact
// shapes Home's existing components already render — the hero story, the watch
// cards, and the league context — so Home can read backend stories behind a
// feature flag without any client-side story generation.
//
// This module only formats and presents backend-authored copy. It never invents
// story content: headlines, narrative, and the league read all come verbatim
// from the canonical payload; only short status labels and count facts are
// derived from structured fields.

export const CANONICAL_HOME_STORIES_FALLBACK =
  'A quiet day in the bullpens — no standout stories this morning. Check back after tonight’s games.'

function canonicalFeed(dashboard) {
  const feed = dashboard?.stories
  return feed && typeof feed === 'object' ? feed : null
}

// The canonical payload is usable when it is present and carries an items array.
// A present-but-empty feed (a quiet day) is still usable; only a missing or
// malformed payload falls back to the legacy engine.
export function hasUsableCanonicalStories(dashboard) {
  const feed = canonicalFeed(dashboard)
  return Boolean(feed && Array.isArray(feed.items))
}

const VALID_TONES = new Set(['stress', 'rest', 'watch', 'neutral'])
function toneOf(item) {
  return VALID_TONES.has(item?.tone) ? item.tone : 'neutral'
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

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function cleanTeamId(value) {
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isInteger(id) ? id : null
}

function teamHref(item) {
  const abbr = cleanText(item?.team_abbreviation)
  return abbr ? `/bullpen?view=board&team=${encodeURIComponent(abbr)}` : null
}

function teamOf(item) {
  if (item?.team_id == null && !cleanText(item?.team_name)) return null
  return {
    team_id: item.team_id,
    team_name: item.team_name,
    team_abbreviation: item.team_abbreviation,
    teamName: item.team_name,
    abbr: item.team_abbreviation,
    href: teamHref(item),
  }
}

function beatsByKey(item) {
  const beats = Array.isArray(item?.beats) ? item.beats : []
  const map = {}
  for (const beat of beats) {
    if (beat && beat.key) map[beat.key] = cleanText(beat.text)
  }
  return map
}

// Descriptive prose = observation + baseline + cause beats. The constraint beat
// becomes the forward-looking "why it matters". Falls back to the full narrative.
function descriptiveNarrative(item) {
  const map = beatsByKey(item)
  const parts = ['observation', 'baseline', 'cause'].map(key => map[key]).filter(Boolean)
  if (parts.length) return parts.join('\n\n')
  return cleanText(item?.narrative)
}

function whyItMattersOf(item) {
  const map = beatsByKey(item)
  return map.constraint || cleanText(item?.share_summary)
}

// Continuity state -> a short, factual status label. This presents the backend
// continuity metadata; it makes no baseball claim about the bullpen.
const STATUS_BY_CONTINUITY_STATE = {
  new: { label: 'New', description: 'First appearance in today’s briefing.', tone: 'neutral' },
  ongoing: { label: 'Ongoing', description: 'Carried over from the previous briefing.', tone: 'watch' },
  unchanged: { label: 'Ongoing', description: 'Holding steady since the previous briefing.', tone: 'watch' },
  changed: { label: 'Updated', description: 'The read on this bullpen changed since the previous briefing.', tone: 'watch' },
}
function storyStatusOf(item) {
  const continuity = item?.continuity
  if (!continuity || continuity.compared === false) return null
  return STATUS_BY_CONTINUITY_STATE[continuity.state] || null
}

function publishableItems(dashboard) {
  const feed = canonicalFeed(dashboard)
  const items = feed && Array.isArray(feed.items) ? feed.items : []
  return items.filter(item => item && item.story_available === true)
}

function storyMatchesTeam(item, team) {
  if (!item || !team) return false

  const storyTeamId = cleanTeamId(item.team_id ?? item.teamId)
  const preferredTeamId = cleanTeamId(team.team_id ?? team.teamId)
  if (storyTeamId != null && preferredTeamId != null) {
    return storyTeamId === preferredTeamId
  }

  const storyAbbr = cleanText(item.team_abbreviation ?? item.teamAbbreviation ?? item.abbr)?.toLowerCase()
  const preferredAbbr = cleanText(team.team_abbreviation ?? team.teamAbbreviation ?? team.teamAbbr ?? team.abbr)?.toLowerCase()
  if (storyAbbr && preferredAbbr) {
    return storyAbbr === preferredAbbr
  }

  const storyName = cleanText(item.team_name ?? item.teamName)?.toLowerCase()
  const preferredName = cleanText(team.team_name ?? team.teamName)?.toLowerCase()
  return Boolean(storyName && preferredName && storyName === preferredName)
}

function preferredTeamLead(dashboard, preferredTeam) {
  if (!preferredTeam) return null
  return publishableItems(dashboard).find(item => storyMatchesTeam(item, preferredTeam)) || null
}

// One canonical published story -> a Home story card (BullpenStories shape).
function toStoryCard(item) {
  const href = teamHref(item)
  return {
    storyId: item.story_id || null,
    storyType: item.story_type || null,
    teamId: item.team_id != null ? item.team_id : null,
    storyKind: item.category === 'rested' ? 'team_recovery' : 'team_story',
    family: 'canonical_story',
    tone: toneOf(item),
    kicker: kickerOf(item),
    title: cleanText(item.headline) || 'Bullpen story',
    narrative: cleanText(item.narrative),
    blueprint: Array.isArray(item.blueprint) ? item.blueprint : [],
    disclosureNote: null,
    href,
    cta: href ? 'Step inside this pen' : null,
    team: teamOf(item),
    continuity: item.continuity || null,
    source: 'canonical',
  }
}

// Watch cards for the "Three Things To Watch" section.
export function getCanonicalHomeStories(dashboard, { limit = 3 } = {}) {
  const items = publishableItems(dashboard).slice(0, limit).map(toStoryCard)
  return {
    hasStories: items.length > 0,
    items,
    fallback: CANONICAL_HOME_STORIES_FALLBACK,
    source: 'canonical',
  }
}

// The flagship hero — the preferred team story when available, then the
// strongest publishable story, or a league/quiet read.
export function getCanonicalHeroStory(dashboard, { preferredTeam = null } = {}) {
  const lead = preferredTeamLead(dashboard, preferredTeam) || publishableItems(dashboard)[0] || null
  if (lead) {
    return {
      hasStory: true,
      storyId: lead.story_id || null,
      storyType: lead.story_type || null,
      teamId: lead.team_id != null ? lead.team_id : null,
      storyKind: lead.category === 'rested' ? 'team_recovery' : 'team_story',
      tone: toneOf(lead),
      kicker: kickerOf(lead),
      team: teamOf(lead),
      read: null,
      headline: cleanText(lead.headline) || 'Bullpen story',
      observation: descriptiveNarrative(lead),
      narrative: descriptiveNarrative(lead),
      blueprint: Array.isArray(lead.blueprint) ? lead.blueprint : [],
      whyItMatters: whyItMattersOf(lead),
      storyStatus: storyStatusOf(lead),
      whatBaseballOSSaw: [],
      chips: [],
      source: 'canonical',
    }
  }

  const league = canonicalFeed(dashboard)?.league_context || null
  return {
    hasStory: false,
    storyKind: 'league_check_in',
    tone: 'neutral',
    kicker: 'League Check-In',
    team: null,
    read: null,
    headline: cleanText(league?.headline) || 'A quiet morning across baseball’s bullpens',
    observation: cleanText(league?.summary) || 'No club stands out for bullpen stress or heavy workload today.',
    narrative: cleanText(league?.summary),
    blueprint: [],
    whyItMatters: 'Quiet days give bullpens a reset point and make the next real pressure point easier to spot.',
    storyStatus: null,
    whatBaseballOSSaw: [],
    chips: [],
    source: 'canonical',
  }
}

function factCount(value) {
  return Number.isFinite(value) ? String(value) : '0'
}

// The league context card — driven by the backend league_context read.
export function getCanonicalLeagueContext(dashboard) {
  const league = canonicalFeed(dashboard)?.league_context || null
  const evidence = (league && league.evidence) || {}
  const summary = league
    ? [cleanText(league.headline), cleanText(league.summary)].filter(Boolean).join(' ')
    : 'The league context is waiting on a complete bullpen dashboard.'

  const pressure = evidence.constrained_team_count != null
    ? evidence.constrained_team_count
    : evidence.pressure_story_count
  const available = evidence.available_team_count != null
    ? evidence.available_team_count
    : evidence.rest_story_count
  const watch = evidence.watch_story_count

  return {
    summary,
    facts: [
      { key: 'pressure', label: 'Bullpen Pressure', tone: pressure > 0 ? 'stress' : 'neutral', value: factCount(pressure), detail: 'clubs carrying late-inning pressure' },
      { key: 'concentration', label: 'Usage Trend', tone: watch > 0 ? 'watch' : 'neutral', value: factCount(watch), detail: 'clubs on the watch list' },
      { key: 'clean', label: 'Rested Options', tone: available > 0 ? 'rest' : 'neutral', value: factCount(available), detail: 'clubs with rested depth' },
    ],
    href: '/stories',
    cta: 'Open Stories for more observations',
    mode: league?.mode || null,
    dayClass: league?.day_class || null,
    continuity: league?.continuity || null,
    source: 'canonical',
  }
}
