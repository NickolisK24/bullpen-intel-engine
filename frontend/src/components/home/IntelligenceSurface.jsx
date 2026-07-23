import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import {
  getBullpenDashboard,
  getBullpenLandscape,
  getTeams,
  getTonightIntelligence,
  signupAudience,
} from '../../utils/api'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
import {
  DataThroughStamp,
  FreshnessBadge,
  isSampleFreshness,
  LastSyncLabel,
  SlateDateStamp,
  StaleDataNotice,
  UnavailableDataState,
} from '../UI'
import { formatFreshnessDate } from '../UI/Freshness'
import {
  BULLPEN_LANDSCAPE_COLUMNS,
  getLandscapeView,
} from '../dashboard/bullpenLandscapeView'
import {
  freshnessDataThrough,
  freshnessIsCurrent,
} from '../dashboard/syncStatusView'

const TONIGHT_SECTION_TITLE = "Tonight's Bullpen Watch"
const TONIGHT_SECTION_SUBTITLE =
  'What BaseballOS is watching before first pitch.'
const TONIGHT_EMPTY_TITLE =
  'No standout bullpen watch point tonight.'
const TONIGHT_EMPTY_BODY =
  "Games are on tonight's slate, but no bullpen situation cleared the BaseballOS publication standard."
const TONIGHT_OFF_DAY_TITLE =
  'No MLB games scheduled tonight.'
const TONIGHT_OFF_DAY_BODY =
  'A league off-day. Bullpen Watch returns with the next MLB game slate.'
const TONIGHT_SCHEDULE_UNVERIFIED_TITLE =
  "Tonight's schedule view is unavailable."
const TONIGHT_SCHEDULE_UNVERIFIED_BODY =
  "BaseballOS could not verify tonight's MLB schedule, so Bullpen Watch is holding its read instead of guessing."
const TONIGHT_ERROR_TITLE =
  "Tonight's bullpen reads are temporarily unavailable."
const TONIGHT_ERROR_BODY =
  'The rest of Today can still be used.'
const TONIGHT_EMPTY_REASON_OFF_DAY = 'no_teams_playing_today'
const TONIGHT_EMPTY_REASON_SCHEDULE_UNVERIFIED = 'no_schedule_context'
const SINCE_YESTERDAY_STATES = new Set([
  'changes_detected',
  'no_meaningful_changes',
  'insufficient_context',
])
const SINCE_YESTERDAY_ALPHABETICAL_ORDERING = 'team_abbreviation_then_team_name'
const SINCE_YESTERDAY_SOURCE = 'since_yesterday'
const SINCE_YESTERDAY_TEAM_LINK_SOURCE = SINCE_YESTERDAY_SOURCE
const SINCE_YESTERDAY_EXPLAINER =
  'Comparing complete, adjacent daily views only. Movement is descriptive, not predictive.'
const SINCE_YESTERDAY_UNAVAILABLE_COPY =
  'Since-yesterday movement is unavailable because the two daily views could not be compared safely. BaseballOS only compares complete, adjacent days.'
const SINCE_YESTERDAY_WAITING_FOR_PAIR_COPY =
  'Movement comparison is paused while BaseballOS waits for two consecutive complete daily views. It resumes automatically when two consecutive complete game-day views are available — no movement is being hidden or assumed.'
const SINCE_YESTERDAY_OFF_DAY_GAP_COPY =
  'The two most recent complete daily views are not adjacent days — a league off-day gap. Movement comparison resumes automatically after the next comparable game-day view.'
const SINCE_YESTERDAY_WAITING_REASONS = new Set([
  'no_prior_snapshot',
  'prior_snapshot_unpublished',
])
const SINCE_YESTERDAY_OFF_DAY_GAP_REASON = 'snapshots_not_comparable'
// Descriptive movement lanes, authored by the backend (item.movement_lane).
// The frontend only maps the lane key to a display label and a fixed order; it
// never infers a lane from headline wording. An unknown/absent lane fails
// closed into the neutral lane rather than being dropped.
const SINCE_YESTERDAY_LANE_ORDER = [
  { key: 'more_breathing_room', label: 'More breathing room', shortLabel: 'More room', summaryLabel: 'gained breathing room', summaryCountKey: 'moreBreathingRoomCount' },
  { key: 'tighter_today', label: 'Tighter today', shortLabel: 'Tighter', summaryLabel: 'became tighter', summaryCountKey: 'tighterTodayCount' },
  { key: 'structure_changed', label: 'Structure changed', shortLabel: 'Structure', summaryLabel: 'changed structurally', summaryCountKey: 'structureChangedCount' },
  { key: 'other_meaningful_changes', label: 'Other meaningful change', shortLabel: 'Other', summaryLabel: 'had other meaningful movement', summaryCountKey: 'otherMeaningfulChangeCount' },
]
const SINCE_YESTERDAY_LANE_KEYS = new Set(SINCE_YESTERDAY_LANE_ORDER.map(lane => lane.key))
const SINCE_YESTERDAY_LANE_BY_KEY = new Map(SINCE_YESTERDAY_LANE_ORDER.map(lane => [lane.key, lane]))
const SINCE_YESTERDAY_NEUTRAL_LANE = 'other_meaningful_changes'
const SINCE_YESTERDAY_TEAM_SEARCH_ID = 'since-yesterday-team-search'
// The "All changes" tab is not a backend lane; it shows every detailed card.
const SINCE_YESTERDAY_ALL_TAB_KEY = 'all'
const SINCE_YESTERDAY_ALL_TAB_LABEL = 'All changes'
const SINCE_YESTERDAY_ALL_TAB_SHORT_LABEL = 'All'
const SINCE_YESTERDAY_TAB_ID_PREFIX = 'since-yesterday-tab-'
const SINCE_YESTERDAY_PANEL_ID_PREFIX = 'since-yesterday-panel-'
const sinceYesterdayTabId = key => `${SINCE_YESTERDAY_TAB_ID_PREFIX}${key}`
const sinceYesterdayPanelId = key => `${SINCE_YESTERDAY_PANEL_ID_PREFIX}${key}`
export const AUDIENCE_SIGNUP_IDLE = 'idle'
export const AUDIENCE_SIGNUP_LOADING = 'loading'
export const AUDIENCE_SIGNUP_SUCCESS = 'success'
export const AUDIENCE_SIGNUP_INVALID = 'invalid'
export const AUDIENCE_SIGNUP_ERROR = 'error'
const AUDIENCE_SIGNUP_SOURCE = 'homepage_hero'
const AUDIENCE_SIGNUP_SUCCESS_MESSAGE =
  'You are on the list for BaseballOS bullpen notes.'
const AUDIENCE_SIGNUP_INVALID_MESSAGE = 'Enter a valid email address.'
const AUDIENCE_SIGNUP_ERROR_MESSAGE =
  'We could not save that signup. Please try again.'
const AUDIENCE_SIGNUP_IDLE_MESSAGE =
  'No picks. No betting. Just bullpen context and product updates.'

const INTERNAL_TODAY_COPY_PATTERN =
  /\b(COIN|V2|V3|V4|deterministic|snapshot|endpoint|backend|recommendation engine|baseline distribution|governance layer|sample state)\b/i
const INTERNAL_TONIGHT_COPY_PATTERN =
  /\b(fatigue score|confidence score|internal_strength|ranking_score|signal_family|signal_type|recommend(?:ed|ation)?|ranked|ranking|projection|prediction|bet(?:ting|s)?|odds|pick|edge|guaranteed|expected to happen|will happen|healthy|injury-free)\b/i

const EMPTY_REASON_COPY = {
  no_completed_game_contexts: 'No completed-game contexts are available for the current reference date.',
  no_publishable_coin_story: 'No publishable bullpen story is available from the current completed-game context.',
  lead_story_unavailable: 'The lead story service is unavailable right now.',
}

const FAIL_CLOSED_EMPTY_REASONS = new Set([
  'lead_story_unavailable',
  'tonight_live_build_timeout',
  'tonight_snapshot_build_unavailable',
  'tonight_snapshot_unavailable',
])

const FAIL_CLOSED_SERVED_FROM = new Set([
  'live_build_timeout',
  'live_build_failed',
  'snapshot_unavailable',
])

export function isValidAudienceEmail(value) {
  const email = String(value || '').trim()
  if (!email || /\s/.test(email)) return false
  const parts = email.split('@')
  if (parts.length !== 2) return false
  const [local, domain] = parts
  return Boolean(local && domain && domain.includes('.'))
}

export async function submitAudienceSignup({
  email,
  signup = signupAudience,
  setStatus = () => {},
  setError = () => {},
} = {}) {
  const trimmedEmail = String(email || '').trim()
  if (!isValidAudienceEmail(trimmedEmail)) {
    setError(null)
    setStatus(AUDIENCE_SIGNUP_INVALID)
    return false
  }

  setError(null)
  setStatus(AUDIENCE_SIGNUP_LOADING)
  try {
    const response = await signup(trimmedEmail)
    if (response?.success === false) {
      setStatus(response.reason === 'invalid_email'
        ? AUDIENCE_SIGNUP_INVALID
        : AUDIENCE_SIGNUP_ERROR)
      return false
    }
    setStatus(AUDIENCE_SIGNUP_SUCCESS)
    return true
  } catch (error) {
    setError(error)
    setStatus(AUDIENCE_SIGNUP_ERROR)
    return false
  }
}

// Compact first-use entry path: the four primary product surfaces a new
// visitor most often wants, using the existing bullpen routes and query views.
// It sits after the daily read, never replacing it, so returning visitors still
// reach today's answer first.
const FIRST_USE_ACTIONS = [
  {
    title: "See Today's Bullpen Read",
    body: 'Fresh, stretched, and vulnerable pens tonight.',
    to: '/',
  },
  {
    title: 'Find a Team',
    body: 'Open any team bullpen board.',
    to: '/bullpen',
  },
  {
    title: 'Compare Two Bullpens',
    body: 'Put two pens side by side.',
    to: '/bullpen?view=compare',
  },
  {
    title: 'Find a Reliever',
    body: 'Search a reliever and scan workload.',
    to: '/bullpen?view=pitchers',
  },
]

const EXPLORE_LINKS = [
  {
    title: 'About BaseballOS',
    body: 'Why BaseballOS exists, in a minute.',
    to: '/about',
  },
  {
    title: 'How to Read BaseballOS',
    body: 'Learn every term in one line each.',
    to: '/how-to-read',
  },
  {
    title: 'Methodology',
    body: 'See how each read is built.',
    to: '/methodology',
  },
  {
    title: 'Data & Trust',
    body: 'Check freshness and how we know.',
    to: '/trust',
  },
]

function textValue(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function publicTerminology(value) {
  return String(value || '')
    .replace(/\bMonitor\b/g, 'On Watch')
    .replace(/\brestricted\b/g, 'limited')
    .replace(/\bRestricted\b/g, 'Limited')
    .replace(/\bconstrained\b/g, 'stretched')
    .replace(/\bConstrained\b/g, 'Stretched')
    .replace(/\brecommendation engine\b/gi, 'how BaseballOS reads workload')
    .replace(/\bclean options\b/g, 'Clean Options')
    .replace(/\bClean options\b/g, 'Clean Options')
}

function numberValue(value) {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function displayKey(value) {
  const text = textValue(value)
  if (!text) return null
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function emptyReasonText(value) {
  const key = textValue(value)
  if (!key) return null
  return EMPTY_REASON_COPY[key] || displayKey(key)
}

function cleanTeamName(value) {
  const text = textValue(value)
  if (!text) return null
  return text.replace(/^the\s+/i, '')
}

function teamIdOf(value) {
  const id = numberValue(value)
  return Number.isInteger(id) ? id : null
}

function teamOptionValue(team) {
  const teamId = teamIdOf(team?.team_id ?? team?.teamId)
  const teamName = textValue(team?.team_name ?? team?.teamName)
  const teamAbbr = textValue(team?.team_abbreviation ?? team?.teamAbbr)
  if (teamId == null && !teamName && !teamAbbr) return null
  return {
    teamId,
    teamName,
    teamAbbr,
  }
}

function teamBoardHref(team, source = 'today') {
  return buildTeamBoardHref(team, { source })
}

function teamBoardHrefIfResolvable(team, source = 'today') {
  const teamParam = textValue(team?.teamAbbr) || (
    team?.teamId != null ? String(team.teamId) : null
  )
  if (!teamParam) return null
  return buildTeamBoardHref(team, { source })
}

function buildTeamsById(teams = []) {
  const byId = new Map()
  for (const team of (Array.isArray(teams) ? teams : [])) {
    const option = teamOptionValue(team)
    if (option?.teamId != null) byId.set(option.teamId, option)
  }
  return byId
}

function normalizeTeamName(value) {
  return cleanTeamName(value)
    ?.toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim() || null
}

function findTeamByName(name, teams = []) {
  const normalized = normalizeTeamName(name)
  if (!normalized) return null
  const options = (Array.isArray(teams) ? teams : [])
    .map(teamOptionValue)
    .filter(Boolean)
  const exact = options.find(team => normalizeTeamName(team.teamName) === normalized)
  if (exact) return exact
  return options.find(team => {
    const candidate = normalizeTeamName(team.teamName)
    return candidate && (
      candidate.endsWith(` ${normalized}`) || normalized.endsWith(` ${candidate}`)
    )
  }) || null
}

function resolveLeadTeam(leadStory, teams = []) {
  const teamId = teamIdOf(leadStory?.team_id ?? leadStory?.package?.team_id)
  const byId = buildTeamsById(teams)
  const fromTeams = teamId != null ? byId.get(teamId) : null
  if (fromTeams) {
    return {
      ...fromTeams,
      label: fromTeams.teamName || fromTeams.teamAbbr || `Team ${teamId}`,
      href: teamBoardHref(fromTeams),
    }
  }

  const completed = leadStory?.package?.completed_game_context || {}
  const teamName = cleanTeamName(completed.team_name)
  const teamAbbr = textValue(completed.team_abbreviation)
  const fallback = {
    teamId,
    teamName,
    teamAbbr,
  }
  return {
    ...fallback,
    label: teamName || teamAbbr || (teamId != null ? `Team ${teamId}` : 'The lead club'),
    href: teamBoardHref(fallback),
  }
}

function firstAvailableDraft(drafts = {}) {
  if (drafts?.team_story) return drafts.team_story
  const values = Object.values(drafts || {})
  return values.find(value => value && typeof value === 'object') || null
}

function cleanDraftList(value) {
  return (Array.isArray(value) ? value : [])
    .map(textValue)
    .filter(Boolean)
}

function cleanStoryCopy(value) {
  const text = textValue(value)
  if (!text || INTERNAL_TODAY_COPY_PATTERN.test(text)) return null
  return publicTerminology(text)
}

function cleanStoryList(...values) {
  return values
    .flatMap(value => (Array.isArray(value) ? value : [value]))
    .map(cleanStoryCopy)
    .filter(Boolean)
}

function cleanTonightCopy(value) {
  const text = textValue(value)
  if (!text || INTERNAL_TONIGHT_COPY_PATTERN.test(text)) return null
  return publicTerminology(text)
}

function cleanTonightList(...values) {
  return values
    .flatMap(value => (Array.isArray(value) ? value : [value]))
    .map(cleanTonightCopy)
    .filter(Boolean)
}

function firstTextValue(...values) {
  return values.map(textValue).find(Boolean) || null
}

function firstObjectValue(...values) {
  return values.find(value => value && typeof value === 'object') || null
}

function dashboardFreshness(dashboard) {
  return firstObjectValue(dashboard?.freshness)
}

function payloadHasSampleMarker(payload) {
  if (!payload || typeof payload !== 'object') return false
  return Boolean(
    isSampleFreshness(payload) ||
    isSampleFreshness(payload.freshness) ||
    isSampleFreshness(payload.metadata) ||
    isSampleFreshness(payload.trust) ||
    isSampleFreshness(payload.snapshot)
  )
}

function payloadIsFailClosed(payload) {
  if (!payload || typeof payload !== 'object') return false
  const status = String(payload.status || '').toLowerCase()
  const emptyReason = String(payload.empty_reason || '').toLowerCase()
  const servedFrom = String(payload.snapshot?.served_from || '').toLowerCase()
  return (
    status === 'error' ||
    FAIL_CLOSED_EMPTY_REASONS.has(emptyReason) ||
    FAIL_CLOSED_SERVED_FROM.has(servedFrom)
  )
}

function sectionFreshness(payload, fallbackFreshness) {
  const payloadFreshness = firstObjectValue(
    payload?.freshness,
    payload?.metadata?.freshness,
    payload?.trust?.freshness,
    payload?.snapshot?.freshness,
  )
  const base = {
    ...(fallbackFreshness && typeof fallbackFreshness === 'object' ? fallbackFreshness : {}),
    ...(payloadFreshness && typeof payloadFreshness === 'object' ? payloadFreshness : {}),
  }

  if (payloadHasSampleMarker(payload)) {
    return {
      ...base,
      freshness_state: 'sample',
      sample: true,
      is_current: false,
    }
  }

  if (payloadIsFailClosed(payload)) {
    return {
      ...base,
      freshness_state: 'stale',
      is_current: false,
      is_stale: true,
      fail_closed: true,
    }
  }

  return Object.keys(base).length ? base : null
}

function formatComparisonDate(value, fallback) {
  return formatFreshnessDate(value) || textValue(value) || fallback
}

function normalizeSinceYesterdayWorkload(value) {
  return (Array.isArray(value) ? value : [])
    .map((row, index) => {
      if (!row || typeof row !== 'object') return null
      const name = firstTextValue(row.name, row.pitcher_name, row.player_name)
      const pitches = numberValue(row.pitches)
      if (!name || pitches == null) return null
      return {
        key: `${name}-${pitches}-${index}`,
        name,
        pitches,
      }
    })
    .filter(Boolean)
}

function sinceYesterdayEvidenceValue(value) {
  if (value == null) return null
  const text = String(value).trim()
  return text || null
}

function normalizeSinceYesterdayEvidence(value) {
  return (Array.isArray(value) ? value : [])
    .map((row, index) => {
      if (!row || typeof row !== 'object') return null
      const label = textValue(row.label)
      const yesterday = sinceYesterdayEvidenceValue(row.yesterday)
      const today = sinceYesterdayEvidenceValue(row.today)
      if (!label || !yesterday || !today) return null
      return {
        key: `${label}-${yesterday}-${today}-${index}`,
        label,
        yesterday,
        today,
      }
    })
    .filter(Boolean)
}

function sinceYesterdayDeltaValue(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return sinceYesterdayEvidenceValue(value)
}

function normalizeSinceYesterdayPrimaryDelta(value) {
  if (!value || typeof value !== 'object') return null
  const label = textValue(value.label)
  const previous = sinceYesterdayDeltaValue(value.previous)
  const current = sinceYesterdayDeltaValue(value.current)
  if (!label || previous == null || current == null) return null
  // A signed net is only meaningful when the backend actually provides one;
  // a missing/null net_delta must stay null (never coerced to 0).
  const rawNet = value.net_delta
  const netDelta = rawNet == null ? null : numberValue(rawNet)
  return {
    label,
    previous,
    current,
    netDelta,
  }
}

function normalizeSinceYesterdaySummary(value) {
  if (!value || typeof value !== 'object') return null
  const count = key => numberValue(value[key])
  const summary = {
    meaningfulChangeCount: count('meaningful_change_count'),
    moreBreathingRoomCount: count('more_breathing_room_count'),
    tighterTodayCount: count('tighter_today_count'),
    structureChangedCount: count('structure_changed_count'),
    otherMeaningfulChangeCount: count('other_meaningful_change_count'),
    countsComplete: value.counts_complete === true,
  }
  // Steady is only trustworthy when the whole population was comparable, so the
  // backend only emits steady_count then. Never synthesize it here.
  const steadyCount = count('steady_count')
  if (steadyCount != null) {
    summary.steadyCount = steadyCount
    summary.steadyTeams = (Array.isArray(value.steady_teams) ? value.steady_teams : [])
      .map(team => {
        if (!team || typeof team !== 'object') return null
        const teamAbbr = textValue(team.team_abbreviation)
        const teamName = cleanTeamName(team.team_name) || teamAbbr
        if (!teamName) return null
        return { teamId: teamIdOf(team.team_id), teamName, teamAbbr }
      })
      .filter(Boolean)
  }
  return summary
}

function sinceYesterdayLaneKey(item) {
  return item.movementLane && SINCE_YESTERDAY_LANE_KEYS.has(item.movementLane)
    ? item.movementLane
    : SINCE_YESTERDAY_NEUTRAL_LANE
}

function buildSinceYesterdayLanes(items) {
  const byLane = new Map()
  for (const item of items) {
    const laneKey = sinceYesterdayLaneKey(item)
    if (!byLane.has(laneKey)) byLane.set(laneKey, [])
    byLane.get(laneKey).push(item)
  }
  return SINCE_YESTERDAY_LANE_ORDER
    .map(lane => ({
      key: lane.key,
      label: lane.label,
      summaryLabel: lane.summaryLabel,
      items: byLane.get(lane.key) || [],
    }))
    .filter(lane => lane.items.length > 0)
}

function sinceYesterdayItemMatchesQuery(item, query) {
  return [item.teamName, item.teamAbbr]
    .some(value => value && String(value).toLowerCase().includes(query))
}

export function filterSinceYesterdayLanes(lanes, query) {
  const normalized = String(query || '').trim().toLowerCase()
  if (!normalized) return lanes
  return lanes
    .map(lane => ({
      ...lane,
      items: lane.items.filter(item => sinceYesterdayItemMatchesQuery(item, normalized)),
    }))
    .filter(lane => lane.items.length > 0)
}

// Search filters the cards shown inside the active tab. It never changes a
// tab's count: the counts are computed once, before any search, so a team the
// user filtered away is never mistaken for a team that did not move.
export function filterSinceYesterdayItems(items, query) {
  const list = Array.isArray(items) ? items : []
  const normalized = String(query || '').trim().toLowerCase()
  if (!normalized) return list
  return list.filter(item => sinceYesterdayItemMatchesQuery(item, normalized))
}

// Tabs are the "All changes" view plus one tab per non-empty movement lane, in
// canonical order. Empty lanes never get a tab (there is nothing to show and no
// "Steady" tab, so steadiness is never framed as a movement category). Every
// item lands in exactly one lane, so the category counts always sum to the All
// count.
export function buildSinceYesterdayTabs(items) {
  const list = Array.isArray(items) ? items : []
  const allTab = {
    key: SINCE_YESTERDAY_ALL_TAB_KEY,
    label: SINCE_YESTERDAY_ALL_TAB_LABEL,
    shortLabel: SINCE_YESTERDAY_ALL_TAB_SHORT_LABEL,
    items: list,
    count: list.length,
  }
  const categoryTabs = buildSinceYesterdayLanes(list).map(lane => {
    const meta = SINCE_YESTERDAY_LANE_BY_KEY.get(lane.key)
    return {
      key: lane.key,
      label: meta.label,
      shortLabel: meta.shortLabel,
      items: lane.items,
      count: lane.items.length,
    }
  })
  return [allTab, ...categoryTabs]
}

// The complete, trusted league-wide count for a tab: the total meaningful
// changes for "All", or the lane count for a category. This is the number the
// league summary reports, which can exceed the number of detailed cards because
// some teams are inside the trusted league population but have no public-safe
// detailed card.
function sinceYesterdayCompleteCount(tab, summary) {
  if (!tab || !summary) return null
  if (tab.key === SINCE_YESTERDAY_ALL_TAB_KEY) {
    return typeof summary.meaningfulChangeCount === 'number'
      ? summary.meaningfulChangeCount
      : null
  }
  const lane = SINCE_YESTERDAY_LANE_BY_KEY.get(tab.key)
  if (!lane) return null
  const laneCount = summary[lane.summaryCountKey]
  return typeof laneCount === 'number' ? laneCount : null
}

// Small number-to-word table for the withheld-card sentence, which starts with
// the spelled-out count. MLB has 30 teams, so the withheld count never exceeds
// that; anything beyond the table falls back to digits rather than guessing.
const SINCE_YESTERDAY_NUMBER_WORDS = [
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
  'seventeen', 'eighteen', 'nineteen', 'twenty', 'twenty-one', 'twenty-two',
  'twenty-three', 'twenty-four', 'twenty-five', 'twenty-six', 'twenty-seven',
  'twenty-eight', 'twenty-nine', 'thirty',
]

function sinceYesterdaySentenceCountWord(value) {
  const word = SINCE_YESTERDAY_NUMBER_WORDS[value] || String(value)
  return word.charAt(0).toUpperCase() + word.slice(1)
}

// Explains, in the panel, how the detailed cards relate to the complete league
// movement counts. When every moving team has a detailed card, it reassures
// that all are shown. When there are fewer cards than complete movements, it
// says the additional teams are part of the trusted league counts but have no
// public-safe detailed card — and, on the All tab, that they are still not
// counted as steady. It never invents a denominator or shows "of 0"; if the
// complete count is unknown or smaller than the cards on hand, it just reports
// what is shown, with no withheld-card explanation.
export function sinceYesterdayCountClarity(tab, summary) {
  if (!tab) return null
  const count = tab.count
  const isAll = tab.key === SINCE_YESTERDAY_ALL_TAB_KEY
  const scope = isAll ? '' : ' in this category'
  const complete = sinceYesterdayCompleteCount(tab, summary)
  if (complete == null || complete < count) {
    const noun = count === 1 ? 'team change' : 'team changes'
    return `Showing ${count} detailed ${noun}${scope}.`
  }
  if (complete === count) {
    const noun = count === 1 ? 'team change' : 'team changes'
    return `Showing all ${count} detailed ${noun}${scope}.`
  }
  const withheld = complete - count
  const withheldWord = sinceYesterdaySentenceCountWord(withheld)
  const withheldTeams = withheld === 1 ? 'team' : 'teams'
  const isIncluded = withheld === 1 ? 'is' : 'are'
  const hasCard = withheld === 1 ? 'does not have' : 'do not have'
  // The league summary is the complete-population framing for All; a single
  // lane's tab reconciles against that lane's league count instead.
  const population = isAll ? 'league summary' : 'league count'
  let explanation =
    `${withheldWord} additional ${withheldTeams} ${isIncluded} included in the ${population} but ${hasCard} a publishable detailed card.`
  if (isAll) {
    const steadySubject = withheld === 1 ? 'It is' : 'They are'
    explanation += ` ${steadySubject} not counted as steady.`
  }
  return `Showing ${count} of ${complete} teams with movement${scope}. ${explanation}`
}

function normalizeSinceYesterdayItem(item, teamsById, teams, index) {
  if (!item || typeof item !== 'object') return null
  const teamId = teamIdOf(item.team_id ?? item.teamId)
  const fromTeams = teamId != null ? teamsById.get(teamId) : null
  const directTeam = teamOptionValue(item)
  const fromName = findTeamByName(item.team_name, teams)
  const teamName = cleanTeamName(item.team_name)
    || fromTeams?.teamName
    || fromName?.teamName
    || directTeam?.teamName
    || directTeam?.teamAbbr
    || (teamId != null ? `Team ${teamId}` : null)
  const teamAbbr = textValue(item.team_abbreviation)
    || fromTeams?.teamAbbr
    || fromName?.teamAbbr
    || directTeam?.teamAbbr
  const resolvedTeamId = teamId ?? fromTeams?.teamId ?? fromName?.teamId ?? directTeam?.teamId
  const href = teamBoardHrefIfResolvable({
    teamId: resolvedTeamId,
    teamAbbr,
  }, SINCE_YESTERDAY_TEAM_LINK_SOURCE)
  const headline = textValue(item.public_headline)
  const summary = textValue(item.public_summary)
  const context = textValue(item.public_context)
  const yesterdayRestedCount = numberValue(item.yesterday_rested_count)
  const todayRestedCount = numberValue(item.today_rested_count)
  const workloadAdded = normalizeSinceYesterdayWorkload(item.workload_added)
  const publicEvidence = normalizeSinceYesterdayEvidence(item.public_evidence)
  const movementLane = textValue(item.movement_lane)
  const movementLabel = textValue(item.movement_label)
  const primaryDelta = normalizeSinceYesterdayPrimaryDelta(item.primary_delta)

  if (!teamName && !headline && !summary && !context) return null

  return {
    key: textValue(item.key) || `${resolvedTeamId || teamAbbr || teamName || 'team'}-${index}`,
    teamId: resolvedTeamId,
    teamName: teamName || teamAbbr || 'This club',
    teamAbbr,
    movementLane,
    movementLabel,
    primaryDelta,
    headline,
    summary,
    context,
    yesterdayRestedCount,
    todayRestedCount,
    hasRestedCounts: yesterdayRestedCount != null && todayRestedCount != null,
    workloadAdded,
    publicEvidence,
    href,
  }
}

export function getSinceYesterdayView(dashboard, teams = []) {
  if (!dashboard || typeof dashboard !== 'object' || payloadIsFailClosed(dashboard)) {
    return null
  }
  const block = dashboard.what_changed_since_yesterday
  if (!block || typeof block !== 'object') return null

  const state = textValue(block.state)
  if (!SINCE_YESTERDAY_STATES.has(state)) return null

  const comparison = block.comparison && typeof block.comparison === 'object'
    ? block.comparison
    : {}
  const previousDate = textValue(comparison.previous_data_through)
  const currentDate = textValue(comparison.current_data_through)
  const itemCountValue = numberValue(block.item_count)
  const baseView = {
    state,
    comparisonAvailable: comparison.comparison_available === true,
    previousDate,
    currentDate,
    previousDateLabel: formatComparisonDate(previousDate, 'the previous view'),
    currentDateLabel: formatComparisonDate(currentDate, 'the current view'),
  }

  const summary = normalizeSinceYesterdaySummary(block.summary)

  if (state === 'changes_detected') {
    const teamsById = buildTeamsById(teams)
    const items = (Array.isArray(block.items) ? block.items : [])
      .map((item, index) => normalizeSinceYesterdayItem(item, teamsById, teams, index))
      .filter(Boolean)
    if (items.length === 0) return null
    const itemCount = itemCountValue ?? items.length
    const countCopy = `${itemCount} teams show meaningful, evidence-backed movement in this daily comparison.`
    return {
      ...baseView,
      items,
      itemCount,
      lanes: buildSinceYesterdayLanes(items),
      tabs: buildSinceYesterdayTabs(items),
      summary,
      orderingBasis: textValue(block.ordering_basis),
      footerCopy: block.ordering_basis === SINCE_YESTERDAY_ALPHABETICAL_ORDERING
        ? `Teams are listed alphabetically. ${countCopy}`
        : countCopy,
    }
  }

  if (state === 'no_meaningful_changes') {
    return {
      ...baseView,
      items: [],
      itemCount: itemCountValue ?? 0,
      lanes: [],
      summary,
      quietCopy: `No meaningful bullpen movement was found between ${baseView.previousDateLabel} and ${baseView.currentDateLabel}. Quiet days are reported as quiet — nothing is padded.`,
    }
  }

  return {
    ...baseView,
    items: [],
    itemCount: itemCountValue ?? 0,
    unavailableCopy: sinceYesterdayUnavailableCopy(block, comparison),
  }
}

function sinceYesterdayUnavailableCopy(block, comparison) {
  const reasonCodes = new Set(
    []
      .concat(Array.isArray(block?.reason_codes) ? block.reason_codes : [])
      .concat(Array.isArray(comparison?.reason_codes) ? comparison.reason_codes : [])
      .map(value => String(value || '').toLowerCase()),
  )
  // Reason-specific fail-closed copy: the comparison stays withheld either
  // way; only the explanation changes. Never implies zero movement.
  if ([...SINCE_YESTERDAY_WAITING_REASONS].some(reason => reasonCodes.has(reason))) {
    return SINCE_YESTERDAY_WAITING_FOR_PAIR_COPY
  }
  if (reasonCodes.has(SINCE_YESTERDAY_OFF_DAY_GAP_REASON)) {
    return SINCE_YESTERDAY_OFF_DAY_GAP_COPY
  }
  return SINCE_YESTERDAY_UNAVAILABLE_COPY
}

function publishedFreshnessBadgeLabel(stale, freshness) {
  const sample = isSampleFreshness(freshness)
  const syncStatus = String(freshness?.sync_status || freshness?.syncStatus || '').toLowerCase()
  const staleState = String(freshness?.freshness_state || freshness?.freshnessState || freshness?.state || '').toLowerCase()
  const publishedCurrent = !sample
    && !stale
    && freshnessIsCurrent(freshness)
    && freshness?.is_stale !== true
    && freshness?.isStale !== true
    && staleState !== 'stale'
    && staleState !== 'historical'
    && syncStatus !== 'failed'
    && syncStatus !== 'error'
  return publishedCurrent ? 'Published view current' : undefined
}

function SectionFreshnessRow({
  dataThrough,
  lastSync,
  stale = false,
  freshness,
  dataThroughLabel = 'Published view through',
  className = '',
}) {
  const sample = isSampleFreshness(freshness)
  if (!dataThrough && !lastSync && !stale && !freshness) return null
  return (
    <div className={`mb-3 flex flex-wrap items-center gap-2 ${className}`}>
      <FreshnessBadge
        state={stale ? 'stale' : 'current'}
        freshness={freshness}
        label={publishedFreshnessBadgeLabel(stale, freshness)}
      />
      <DataThroughStamp date={dataThrough} label={dataThroughLabel} />
      <LastSyncLabel value={lastSync} />
      {sample && (
        <span className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
          Not live MLB data.
        </span>
      )}
    </div>
  )
}

function TonightFreshnessRow({
  slateDate,
  dataThrough,
  lastSync,
  generatedAt,
  stale = false,
  slateUnavailable = false,
  publishedViewCurrent = false,
  freshness,
}) {
  const sample = isSampleFreshness(freshness)
  const scopedStaleLabel = slateUnavailable && publishedViewCurrent
    ? 'Tonight slate unavailable'
    : null
  if (!slateDate && !dataThrough && !lastSync && !generatedAt && !stale && !freshness) return null
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <SlateDateStamp date={slateDate} />
      {(dataThrough || lastSync || stale || freshness) && (
        <FreshnessBadge
          state={stale ? 'stale' : 'current'}
          freshness={freshness}
          label={scopedStaleLabel || publishedFreshnessBadgeLabel(stale, freshness)}
        />
      )}
      <DataThroughStamp date={dataThrough} label="Published view through" />
      <LastSyncLabel value={generatedAt} label="Tonight watch generated" />
      <LastSyncLabel value={lastSync} />
      {sample && (
        <span className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
          Not live MLB data.
        </span>
      )}
    </div>
  )
}

function cleanOptionNames(items) {
  return (Array.isArray(items) ? items : [])
    .map(item => textValue(item?.name ?? item?.player_name ?? item?.full_name))
    .filter(Boolean)
}

function buildBullpenSnapshot(packagePayload = {}) {
  const availability = packagePayload.availability_snapshot || {}
  const bullpen = packagePayload.bullpen_snapshot || {}
  const workload = packagePayload.workload_snapshot || {}
  const rows = []
  const available = numberValue(availability.available_arms_count)
  const monitor = numberValue(availability.monitor_arms_count)
  const unavailable = numberValue(availability.unavailable_arms_count)
  const cleanOptionsCount = numberValue(bullpen.clean_options_count)
  const optionalityBand = displayKey(
    bullpen.optionality_band || availability.optionality_band,
  )
  const concentrationBand = displayKey(workload.concentration_band)
  const cleanOptions = cleanOptionNames(bullpen.clean_options)

  if (available != null) rows.push(`Available arms: ${available}`)
  if (monitor != null) rows.push(`On watch: ${monitor}`)
  if (unavailable != null) rows.push(`Unavailable: ${unavailable}`)
  if (cleanOptionsCount != null) rows.push(`Clean Options: ${cleanOptionsCount}`)
  if (optionalityBand) rows.push(`Clean Options: ${optionalityBand}`)
  if (concentrationBand) rows.push(`Workload Concentration: ${concentrationBand}`)
  if (cleanOptions.length > 0) {
    rows.push(`Named Clean Options: ${cleanOptions.slice(0, 3).join(', ')}`)
  }

  return rows
}

function buildSelectionMetadata(selection = {}) {
  return [
    ['Priority', displayKey(selection.story_priority)],
    ['Confidence', displayKey(selection.confidence)],
  ]
    .filter(([, value]) => Boolean(value))
    .map(([label, value]) => ({ label, value }))
}

export function getLeadStoryView(response, teams = []) {
  if (!response || response.status !== 'ok' || !response.lead_story) {
    return {
      hasStory: false,
      emptyReason: emptyReasonText(response?.empty_reason),
      candidatesConsidered: numberValue(response?.candidates_considered),
      publishableCandidates: numberValue(response?.publishable_candidates),
    }
  }

  const lead = response.lead_story
  const draft = firstAvailableDraft(lead.drafts)
  const packagePayload = lead.package || {}
  const headline = cleanStoryCopy(draft?.headline) || 'BaseballOS is watching this bullpen story.'
  const body = cleanStoryCopy(draft?.body || draft?.text) || ''
  const team = resolveLeadTeam(lead, teams)

  return {
    hasStory: true,
    team,
    headline,
    body,
    observations: cleanStoryList(draft?.observations),
    evidence: cleanStoryList(draft?.evidence),
    limitations: cleanStoryList(
      draft?.limitations,
      lead.limitations,
      packagePayload.limitations,
      packagePayload.public_limitations,
    ).slice(0, 3),
    snapshot: buildBullpenSnapshot(packagePayload),
    metadata: buildSelectionMetadata(lead.selection || {}),
    referenceDate: textValue(response.reference_date),
    candidateSummary: {
      considered: numberValue(response.candidates_considered),
      publishable: numberValue(response.publishable_candidates),
      errors: numberValue(response.errors),
    },
  }
}

function resolveTonightTeam(card, teams = []) {
  const direct = teamOptionValue(card)
  const byId = buildTeamsById(teams)
  const fromId = direct?.teamId != null ? byId.get(direct.teamId) : null
  if (fromId) return fromId
  if (direct?.teamAbbr) return direct
  return findTeamByName(direct?.teamName ?? card?.team_name, teams) || direct
}

export function getTonightCards(response, teams = [], limit = 3) {
  if (!response || response.status !== 'ok') return []
  const rawCards = Array.isArray(response.cards) ? response.cards : []

  return rawCards
    .map(card => {
      const team = resolveTonightTeam(card, teams)
      const teamName = cleanTeamName(card?.team_name ?? card?.teamName ?? team?.teamName)
      const story = firstObjectValue(card?.pregame_story) || {}
      const headline = cleanTonightCopy(story?.headline) || cleanTonightCopy(card?.headline)
      const summary = cleanTonightCopy(story?.watching) || cleanTonightCopy(card?.summary)
      if (!teamName || !headline || !summary) return null
      return {
        key: textValue(card?.key) || [
          team?.teamId,
          team?.teamAbbr,
          teamName,
          headline,
        ].filter(Boolean).join('-'),
        teamName,
        label: cleanTonightCopy(story?.label) || TONIGHT_SECTION_TITLE,
        headline,
        summary,
        teamContext: cleanTonightCopy(story?.team_context),
        whyItMatters: cleanTonightCopy(story?.why_it_matters),
        keyNote: cleanTonightCopy(story?.key_note),
        starterDependency: cleanTonightCopy(story?.starter_dependency)
          ? 'Starter-length context lives on the team board with recent completed-game detail.'
          : null,
        watchPoint: cleanTonightCopy(story?.watch_point),
        evidence: cleanTonightList(card?.evidence),
        limitations: cleanTonightList(card?.limitations),
        teamAbbr: team?.teamAbbr || null,
        teamId: team?.teamId ?? null,
        href: teamBoardHrefIfResolvable(team, 'today'),
      }
    })
    .filter(Boolean)
    .slice(0, limit)
}

function pictureColumnByKey(landscapeView, key) {
  const column = (landscapeView?.columns || []).find(item => item.key === key)
  return column || { entries: [] }
}

const BULLPEN_PICTURE_EMPTY_COPY = {
  available: 'No bullpen currently stands out as rested and available.',
  monitoring: 'No bullpen currently has enough arms on watch to stand out.',
  constrained: 'No bullpen currently shows enough stretched workload to stand out.',
}

export function getBullpenPictureView(landscape) {
  const view = getLandscapeView(landscape)
  if (!view.hasLandscape) {
    return {
      hasLandscape: false,
      teamsEvaluated: 0,
      gamesLabel: null,
      columns: [],
    }
  }

  const specs = BULLPEN_LANDSCAPE_COLUMNS.map(column => ({
    sourceKey: column.key,
    title: column.title,
    metric: column.metric,
    suffix: column.suffix,
    emptyCopy: BULLPEN_PICTURE_EMPTY_COPY[column.key],
  }))

  return {
    hasLandscape: true,
    teamsEvaluated: view.teamsEvaluated,
    gamesLabel: view.games?.label || null,
    columns: specs.map(spec => {
      const column = pictureColumnByKey(view, spec.sourceKey)
      const entries = Array.isArray(column.entries) ? column.entries : []
      return {
        ...spec,
        entries,
        // Today shows a teaser: one standout team per lane. The full lane
        // lists live on the Dashboard league board.
        lead: entries[0] || null,
        moreCount: Math.max(0, entries.length - 1),
      }
    }),
  }
}

function SectionShell({ id, title, eyebrow, subtitle, children, className = '' }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`mb-10 ${className}`}>
      <div className="mb-3 border-t border-dirt pt-4">
        {eyebrow && (
          <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-amber/75">
            {eyebrow}
          </div>
        )}
        <h2 id={`${id}-title`} className="font-display text-2xl tracking-wide text-chalk100 sm:text-3xl">
          {title}
        </h2>
        {subtitle && (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk500">
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </section>
  )
}

function audienceSignupMessage(status) {
  if (status === AUDIENCE_SIGNUP_SUCCESS) return AUDIENCE_SIGNUP_SUCCESS_MESSAGE
  if (status === AUDIENCE_SIGNUP_INVALID) return AUDIENCE_SIGNUP_INVALID_MESSAGE
  if (status === AUDIENCE_SIGNUP_ERROR) return AUDIENCE_SIGNUP_ERROR_MESSAGE
  return AUDIENCE_SIGNUP_IDLE_MESSAGE
}

export function AudienceSignupFormView({
  email,
  status,
  onEmailChange,
  onSubmit,
}) {
  const isLoading = status === AUDIENCE_SIGNUP_LOADING
  const isInvalid = status === AUDIENCE_SIGNUP_INVALID
  const isError = status === AUDIENCE_SIGNUP_ERROR
  const isSuccess = status === AUDIENCE_SIGNUP_SUCCESS
  const message = audienceSignupMessage(status)
  const messageTone = isInvalid || isError
    ? 'text-red-300'
    : isSuccess
      ? 'text-amber'
      : 'text-chalk500'

  return (
    <form
      className="w-full max-w-xl"
      onSubmit={onSubmit}
      noValidate
    >
      <label
        htmlFor="audience-signup-email"
        className="mb-2 block text-xs font-semibold uppercase tracking-widest text-chalk300"
      >
        Get BaseballOS bullpen notes in your inbox.
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="audience-signup-email"
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={onEmailChange}
          placeholder="you@example.com"
          aria-invalid={isInvalid ? 'true' : 'false'}
          aria-describedby="audience-signup-message"
          disabled={isLoading}
          className="min-h-11 flex-1 rounded border border-dirt bg-black/20 px-3 py-2 text-sm text-chalk100 placeholder:text-chalk500 transition-colors focus:border-amber/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/50 disabled:cursor-wait disabled:opacity-70"
        />
        <button
          type="submit"
          disabled={isLoading}
          className="inline-flex min-h-11 items-center justify-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60 disabled:cursor-wait disabled:border-dirt disabled:bg-field/50 disabled:text-chalk500 sm:w-auto"
        >
          {isLoading ? 'Joining...' : 'Get bullpen notes'}
        </button>
      </div>
      <p
        id="audience-signup-message"
        className={`mt-2 text-xs leading-relaxed ${messageTone}`}
        role={isInvalid || isError ? 'alert' : 'status'}
        aria-live="polite"
      >
        {message}
      </p>
    </form>
  )
}

function AudienceSignupForm() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(AUDIENCE_SIGNUP_IDLE)
  const [, setError] = useState(null)

  const handleEmailChange = (event) => {
    setEmail(event.target.value)
    if (
      status === AUDIENCE_SIGNUP_INVALID ||
      status === AUDIENCE_SIGNUP_ERROR ||
      status === AUDIENCE_SIGNUP_SUCCESS
    ) {
      setStatus(AUDIENCE_SIGNUP_IDLE)
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    await submitAudienceSignup({
      email,
      signup: (value) => signupAudience(value, { source: AUDIENCE_SIGNUP_SOURCE }),
      setStatus,
      setError,
    })
  }

  return (
    <AudienceSignupFormView
      email={email}
      status={status}
      onEmailChange={handleEmailChange}
      onSubmit={handleSubmit}
    />
  )
}

function SeesHeader() {

  return (
    <header className="mb-7 max-w-4xl pt-2 sm:pt-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-amber/75">
        MLB BULLPEN INTELLIGENCE — UPDATED DAILY
      </div>
      <h1 className="mt-3 font-display text-5xl leading-none tracking-wide text-chalk100 sm:text-6xl lg:text-7xl">
        See which bullpens are fresh, stretched, or vulnerable tonight — and why.
      </h1>
      <p className="mt-4 max-w-3xl text-base leading-relaxed text-chalk300 sm:text-lg">
        BaseballOS reads public MLB usage and workload after every game, so you can tell which pens are gassed and which are loaded — with the data date and confidence always shown.
      </p>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-chalk500">
        Descriptive only — we show what we see and what we can't. No picks, no predictions.
      </p>
      <div className="mt-5 grid max-w-4xl gap-4 lg:grid-cols-[auto_minmax(20rem,1fr)] lg:items-start">
        <a
          href="#bullpen-picture"
          className="inline-flex min-h-11 w-full items-center justify-center rounded border border-amber/40 bg-amber/10 px-4 py-3 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60 lg:w-auto"
        >
          Explore today's bullpen picture
        </a>
        <AudienceSignupForm />
      </div>
    </header>
  )
}

function TonightLoadingState() {
  return (
    <div className="min-h-40 border border-amber/20 bg-dugout p-4 sm:p-5" role="status" aria-live="polite">
      <p className="font-mono text-xs uppercase tracking-widest text-chalk500">
        Reading tonight's bullpen context...
      </p>
      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3" aria-hidden="true">
        {[0, 1, 2].map(index => (
          <div key={index} className="border border-dirt/80 bg-field/40 p-4">
            <div className="h-3 w-20 animate-pulse bg-dirt" />
            <div className="mt-4 h-4 w-4/5 animate-pulse bg-dirt" />
            <div className="mt-3 h-3 w-full animate-pulse bg-dirt" />
            <div className="mt-2 h-3 w-2/3 animate-pulse bg-dirt" />
          </div>
        ))}
      </div>
    </div>
  )
}

function TonightEmptyState({ isError, emptyReason, onRetry }) {
  if (!isError && emptyReason === TONIGHT_EMPTY_REASON_OFF_DAY) {
    // Verified from stored schedule evidence: zero MLB games on this slate.
    // A deliberate league-off-day pause, not an analysis that found nothing.
    return (
      <div className="border border-dirt bg-dugout p-4 sm:p-5" role="status">
        <h3 className="font-display text-2xl leading-tight tracking-wide text-chalk100">
          {TONIGHT_OFF_DAY_TITLE}
        </h3>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-chalk400">
          {TONIGHT_OFF_DAY_BODY}
        </p>
      </div>
    )
  }
  if (!isError && emptyReason === TONIGHT_EMPTY_REASON_SCHEDULE_UNVERIFIED) {
    // Fail closed: the stored schedule near this date could not be verified,
    // so this is a limited read — never presented as a verified off-day.
    return (
      <UnavailableDataState
        title={TONIGHT_SCHEDULE_UNVERIFIED_TITLE}
        message={TONIGHT_SCHEDULE_UNVERIFIED_BODY}
        onRetry={onRetry}
        className="sm:p-5"
      />
    )
  }
  return (
    <UnavailableDataState
      title={isError ? TONIGHT_ERROR_TITLE : TONIGHT_EMPTY_TITLE}
      message={isError ? TONIGHT_ERROR_BODY : TONIGHT_EMPTY_BODY}
      onRetry={isError ? onRetry : null}
      className="sm:p-5"
    />
  )
}

function TonightCard({ card }) {
  const storyRows = [
    ['Why It Matters Tonight', card.whyItMatters],
    ['Key Note', card.keyNote],
    ['Starter Length', card.starterDependency],
    ['Watch Point', card.watchPoint],
  ].filter(([, body]) => Boolean(body))

  return (
    <article className="flex min-w-0 flex-col border border-dirt bg-dugout p-4 sm:p-5">
      <div className="font-mono text-[10px] uppercase tracking-widest text-amber/75">
        {card.teamName}
      </div>
      <h3 className="mt-3 break-words font-display text-2xl leading-tight tracking-wide text-chalk100">
        {card.headline}
      </h3>
      {card.teamContext && (
        <p className="mt-2 text-xs leading-relaxed text-chalk500">
          {card.teamContext}
        </p>
      )}
      <p className="mt-3 text-sm leading-relaxed text-chalk400">
        {card.summary}
      </p>
      {storyRows.length > 0 && (
        <div className="mt-4 space-y-3">
          {storyRows.map(([label, body]) => (
            <div key={label}>
              <h4 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                {label}
              </h4>
              <p className="mt-1 text-xs leading-relaxed text-chalk400">
                {body}
              </p>
            </div>
          ))}
        </div>
      )}
      {card.evidence.length > 0 && (
        <div className="mt-4">
          <h4 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Usage Notes
          </h4>
          <ul className="mt-2 space-y-2">
            {card.evidence.map(item => (
              <li key={item} className="flex gap-2 text-xs leading-relaxed text-chalk400">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber/70" aria-hidden="true" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {card.limitations.length > 0 && (
        <div className="mt-4 border-t border-dirt/80 pt-3">
          <h4 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Limitations
          </h4>
          <ul className="mt-2 space-y-1">
            {card.limitations.map(item => (
              <li key={item} className="text-xs leading-relaxed text-chalk500">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
      {card.href && (
        <Link
          to={card.href}
          className="mt-5 inline-flex min-h-10 w-fit items-center rounded border border-dirt bg-field/60 px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
          aria-label={`Open the bullpen board for ${card.teamName}`}
        >
          View Team Bullpen State
        </Link>
      )}
    </article>
  )
}

function sinceYesterdayNetLabel(netDelta) {
  if (typeof netDelta !== 'number' || netDelta === 0) return null
  return netDelta > 0 ? `+${netDelta}` : String(netDelta)
}

function SinceYesterdayPrimaryDelta({ delta }) {
  if (!delta) return null
  const net = sinceYesterdayNetLabel(delta.netDelta)
  return (
    <div className="mt-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {delta.label}
      </p>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-display text-3xl leading-none tracking-wide text-chalk100">
          <span className="sr-only">Yesterday </span>{delta.previous}
        </span>
        <span aria-hidden="true" className="font-display text-2xl leading-none text-chalk500">
          →
        </span>
        <span className="font-display text-3xl leading-none tracking-wide text-amber">
          <span className="sr-only">today </span>{delta.current}
        </span>
        {net && (
          <span className="font-mono text-xs uppercase tracking-wider text-chalk300">
            <span className="sr-only">net change </span>{net}
          </span>
        )}
      </p>
    </div>
  )
}

function SinceYesterdayWorkload({ rows }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className="mt-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        Worked yesterday
      </p>
      <ul className="mt-1 space-y-1">
        {rows.map(row => (
          <li
            key={row.key}
            className="flex flex-wrap items-baseline justify-between gap-2 text-sm text-chalk300"
          >
            <span>{row.name}</span>
            <span className="font-mono text-xs uppercase tracking-wider text-chalk500">
              {row.pitches} {row.pitches === 1 ? 'pitch' : 'pitches'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SinceYesterdayEvidenceRow({ label, yesterday, today }) {
  return (
    <div className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-baseline sm:gap-3">
      <dt className="text-chalk300">{label}</dt>
      <dd className="font-mono text-xs uppercase tracking-wider text-chalk500">
        Yesterday {yesterday}
      </dd>
      <dd className="font-mono text-xs uppercase tracking-wider text-chalk500">
        Today {today}
      </dd>
    </div>
  )
}

function SinceYesterdayEvidence({ item }) {
  const showRested = item.hasRestedCounts
  const rows = item.publicEvidence
  if (!showRested && rows.length === 0) return null
  return (
    <details className="group mt-3 border border-dirt/75 bg-field/45">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-chalk500 transition-colors hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        <span className="group-open:hidden">View evidence</span>
        <span className="hidden group-open:inline">Hide evidence</span>
      </summary>
      <dl className="space-y-2 border-t border-dirt/75 px-3 py-3">
        {showRested && (
          <SinceYesterdayEvidenceRow
            label="Rested relievers"
            yesterday={item.yesterdayRestedCount}
            today={item.todayRestedCount}
          />
        )}
        {rows.map(row => (
          <SinceYesterdayEvidenceRow
            key={row.key}
            label={row.label}
            yesterday={row.yesterday}
            today={row.today}
          />
        ))}
      </dl>
    </details>
  )
}

function SinceYesterdayCard({ item }) {
  const explanation = item.summary || item.headline
  return (
    <article className="flex flex-col border border-dirt bg-dugout p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
          {item.teamName}
        </h3>
        {item.movementLabel && (
          <span className="shrink-0 border border-dirt/75 bg-field/60 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-chalk300">
            {item.movementLabel}
          </span>
        )}
      </div>
      <SinceYesterdayPrimaryDelta delta={item.primaryDelta} />
      {explanation && (
        <p className="mt-3 text-sm leading-relaxed text-chalk300">{explanation}</p>
      )}
      <SinceYesterdayWorkload rows={item.workloadAdded} />
      {item.context && (
        <p className="mt-3 text-sm leading-relaxed text-chalk500">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Why it matters{' '}
          </span>
          {item.context}
        </p>
      )}
      <SinceYesterdayEvidence item={item} />
      {item.href && (
        <div className="mt-4">
          <Link
            to={item.href}
            className="inline-flex min-h-10 items-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
            aria-label={`Open the bullpen board for ${item.teamName}`}
          >
            Open bullpen board
          </Link>
        </div>
      )}
    </article>
  )
}

function SinceYesterdayTabs({ tabs, activeKey, onActivate }) {
  const tabRefs = useRef(new Map())
  const activeIndex = Math.max(0, tabs.findIndex(tab => tab.key === activeKey))
  const focusTab = key => {
    const node = tabRefs.current.get(key)
    if (node && typeof node.focus === 'function') node.focus()
  }
  const handleKeyDown = event => {
    let nextIndex = null
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextIndex = (activeIndex + 1) % tabs.length
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextIndex = (activeIndex - 1 + tabs.length) % tabs.length
    } else if (event.key === 'Home') {
      nextIndex = 0
    } else if (event.key === 'End') {
      nextIndex = tabs.length - 1
    }
    if (nextIndex == null) return
    event.preventDefault()
    const nextKey = tabs[nextIndex].key
    onActivate(nextKey)
    focusTab(nextKey)
  }
  return (
    <div
      role="tablist"
      aria-label="Movement categories"
      aria-orientation="horizontal"
      className="mb-4 flex flex-wrap gap-2"
      onKeyDown={handleKeyDown}
    >
      {tabs.map(tab => {
        const selected = tab.key === activeKey
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={sinceYesterdayTabId(tab.key)}
            aria-selected={selected ? 'true' : 'false'}
            aria-controls={sinceYesterdayPanelId(tab.key)}
            aria-label={`${tab.label}, ${tab.count} ${tab.count === 1 ? 'team' : 'teams'}`}
            tabIndex={selected ? 0 : -1}
            ref={node => {
              if (node) tabRefs.current.set(tab.key, node)
              else tabRefs.current.delete(tab.key)
            }}
            onClick={() => onActivate(tab.key)}
            className={`inline-flex min-h-10 items-center gap-2 border px-3 py-2 font-mono text-xs uppercase tracking-wider transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/40 ${
              selected
                ? 'border-amber bg-amber/10 text-amber'
                : 'border-dirt bg-field/60 text-chalk300 hover:text-amber'
            }`}
          >
            <span>{tab.shortLabel}</span>
            <span
              aria-hidden="true"
              className={`font-display text-sm leading-none tracking-wide ${
                selected ? 'text-amber' : 'text-chalk500'
              }`}
            >
              {tab.count}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function SinceYesterdayLeagueSummary({ summary }) {
  if (!summary) return null
  const rows = [
    ['more_breathing_room', summary.moreBreathingRoomCount, 'gained breathing room'],
    ['tighter_today', summary.tighterTodayCount, 'became tighter'],
    ['structure_changed', summary.structureChangedCount, 'changed structurally'],
    ['other_meaningful', summary.otherMeaningfulChangeCount, 'had other meaningful movement'],
  ].filter(([, count]) => typeof count === 'number' && count > 0)
  const showSteady = typeof summary.steadyCount === 'number' && summary.steadyCount > 0
  if (rows.length === 0 && !showSteady) return null
  return (
    <div className="mb-4 border border-dirt bg-dugout p-4">
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
        Across MLB since yesterday
      </h3>
      <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
        {rows.map(([key, count, label]) => (
          <li key={key} className="text-sm text-chalk300">
            <span className="font-display text-xl tracking-wide text-chalk100">{count}</span>{' '}
            {label}
          </li>
        ))}
        {showSteady && (
          <li className="text-sm text-chalk300">
            <span className="font-display text-xl tracking-wide text-chalk100">
              {summary.steadyCount}
            </span>{' '}
            remained steady
          </li>
        )}
      </ul>
    </div>
  )
}

function SinceYesterdaySteadyDisclosure({ summary }) {
  if (!summary || typeof summary.steadyCount !== 'number' || summary.steadyCount === 0) {
    return null
  }
  const teams = summary.steadyTeams || []
  return (
    <details className="group mt-4 border border-dirt bg-dugout">
      <summary className="cursor-pointer list-none px-4 py-3 text-sm text-chalk300 transition-colors hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        {summary.steadyCount} {summary.steadyCount === 1 ? 'team' : 'teams'} had no meaningful
        bullpen movement in this comparison.
      </summary>
      {teams.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t border-dirt px-4 py-3 text-sm text-chalk500">
          {teams.map(team => (
            <li key={team.teamId ?? team.teamAbbr ?? team.teamName}>{team.teamName}</li>
          ))}
        </ul>
      )}
    </details>
  )
}

function SinceYesterdayTeamSearch({ query, onChange, onReset }) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <label
        htmlFor={SINCE_YESTERDAY_TEAM_SEARCH_ID}
        className="font-mono text-[10px] uppercase tracking-widest text-chalk500"
      >
        Find a team
      </label>
      <input
        id={SINCE_YESTERDAY_TEAM_SEARCH_ID}
        type="search"
        value={query}
        onChange={event => onChange(event.target.value)}
        placeholder="Team name or abbreviation"
        autoComplete="off"
        className="min-h-10 flex-1 border border-dirt bg-field/60 px-3 py-2 text-sm text-chalk100 placeholder:text-chalk500 focus:border-amber/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/40"
      />
      {query && (
        <button
          type="button"
          onClick={onReset}
          className="min-h-10 border border-dirt bg-field/60 px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/40"
        >
          Reset
        </button>
      )}
    </div>
  )
}

function SinceYesterdayBriefing({ view }) {
  const tabs = view.tabs && view.tabs.length > 0
    ? view.tabs
    : buildSinceYesterdayTabs(view.items || [])
  const [activeKey, setActiveKey] = useState(SINCE_YESTERDAY_ALL_TAB_KEY)
  // Search persists across tab switches; it only ever filters the cards inside
  // whichever tab is active.
  const [query, setQuery] = useState('')
  // If the active tab is no longer available (data refreshed), fall back to All
  // so the panel and tablist can never disagree.
  const activeTab = tabs.find(tab => tab.key === activeKey) || tabs[0]
  const effectiveKey = activeTab ? activeTab.key : SINCE_YESTERDAY_ALL_TAB_KEY
  const clarity = sinceYesterdayCountClarity(activeTab, view.summary)
  const visibleItems = filterSinceYesterdayItems(activeTab ? activeTab.items : [], query)
  const trimmedQuery = query.trim()
  const hasMatches = visibleItems.length > 0
  return (
    <>
      <SinceYesterdayLeagueSummary summary={view.summary} />
      <SinceYesterdayTabs tabs={tabs} activeKey={effectiveKey} onActivate={setActiveKey} />
      <SinceYesterdayTeamSearch
        query={query}
        onChange={setQuery}
        onReset={() => setQuery('')}
      />
      <div
        role="tabpanel"
        id={sinceYesterdayPanelId(effectiveKey)}
        aria-labelledby={sinceYesterdayTabId(effectiveKey)}
        tabIndex={0}
        className="focus:outline-none"
      >
        {clarity && (
          <p className="mb-3 font-mono text-[11px] leading-relaxed text-chalk500">
            {clarity}
          </p>
        )}
        {hasMatches ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {visibleItems.map(item => (
              <SinceYesterdayCard key={item.key} item={item} />
            ))}
          </div>
        ) : (
          <div className="border border-dirt bg-dugout p-4" role="status">
            <p className="text-sm leading-relaxed text-chalk300">
              No published movement in this tab matches “{trimmedQuery}”. That does not mean those
              teams were steady — reset to see every team with movement here.
            </p>
            <button
              type="button"
              onClick={() => setQuery('')}
              className="mt-3 inline-flex min-h-10 items-center border border-dirt bg-field/60 px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/40"
            >
              Reset search
            </button>
          </div>
        )}
      </div>
      <SinceYesterdaySteadyDisclosure summary={view.summary} />
      <p className="mt-4 text-xs leading-relaxed text-chalk500">{view.footerCopy}</p>
    </>
  )
}

function SinceYesterdayQuiet({ view }) {
  return (
    <>
      <SinceYesterdayLeagueSummary summary={view.summary} />
      <div className="border border-dirt bg-dugout p-4" role="status">
        <p className="text-sm leading-relaxed text-chalk300">{view.quietCopy}</p>
      </div>
      <SinceYesterdaySteadyDisclosure summary={view.summary} />
    </>
  )
}

function SinceYesterdaySection({ dashboard, teams }) {
  const view = getSinceYesterdayView(dashboard, teams)

  if (!view) return null

  return (
    <SectionShell
      id="since-yesterday"
      eyebrow="SINCE YESTERDAY"
      title="What changed across MLB bullpens"
      subtitle={SINCE_YESTERDAY_EXPLAINER}
    >
      {(view.previousDate || view.currentDate) && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <DataThroughStamp date={view.previousDate} label="Previous view" />
          <DataThroughStamp date={view.currentDate} label="Current view" />
        </div>
      )}
      {view.state === 'changes_detected' ? (
        <SinceYesterdayBriefing view={view} />
      ) : view.state === 'no_meaningful_changes' ? (
        <SinceYesterdayQuiet view={view} />
      ) : (
        <div className="border border-dirt bg-dugout p-4" role="status">
          <p className="text-sm leading-relaxed text-chalk300">
            {view.unavailableCopy}
          </p>
        </div>
      )}
    </SectionShell>
  )
}

function TonightSection({
  tonight,
  teams,
  loading,
  error,
  staleWithError,
  onRetry,
  dashboard,
}) {
  const cards = getTonightCards(tonight, teams)
  const sectionLimitations = cleanTonightList(tonight?.limitations)
  const freshness = dashboardFreshness(dashboard)
  const publishedViewCurrent = freshnessIsCurrent(freshness)
  const missingCompletedPayload = !tonight && !loading && !error
  const tonightPayloadUnavailable = payloadIsFailClosed(tonight)
  const rowFreshness = sectionFreshness(
    missingCompletedPayload ? { status: 'error' } : tonight,
    freshness,
  )
  const slateDate = textValue(tonight?.reference_date)
  const dataThrough = textValue(freshnessDataThrough(rowFreshness))
  const lastSync = firstTextValue(rowFreshness?.last_successful_sync, rowFreshness?.lastSuccessfulSync)
  const generatedAt = textValue(tonight?.snapshot?.generated_at)
  const emptyReason = textValue(tonight?.empty_reason)
  const snapshotUnavailable = [
    'tonight_live_build_timeout',
    'tonight_snapshot_build_unavailable',
    'tonight_snapshot_unavailable',
  ].includes(emptyReason)
  const scheduleUnverified = emptyReason === TONIGHT_EMPTY_REASON_SCHEDULE_UNVERIFIED
  const slateUnavailable = (
    snapshotUnavailable
    || scheduleUnverified
    || missingCompletedPayload
    || tonightPayloadUnavailable
  )
  const showUnavailable = Boolean(error && !tonight) || snapshotUnavailable

  if (loading && !tonight) {
    return (
      <SectionShell
        id="tonight"
        eyebrow="Tonight"
        title={TONIGHT_SECTION_TITLE}
        subtitle={TONIGHT_SECTION_SUBTITLE}
      >
        <TonightLoadingState />
      </SectionShell>
    )
  }

  if (cards.length > 0) {
    return (
      <SectionShell
        id="tonight"
        eyebrow="Tonight"
        title={TONIGHT_SECTION_TITLE}
        subtitle={TONIGHT_SECTION_SUBTITLE}
      >
        {staleWithError && (
          <StaleDataNotice
            dataThrough={dataThrough}
            onRetry={onRetry}
          />
        )}
        <TonightFreshnessRow
          slateDate={slateDate}
          dataThrough={dataThrough}
          lastSync={lastSync}
          generatedAt={generatedAt}
          stale={staleWithError}
          slateUnavailable={staleWithError}
          publishedViewCurrent={publishedViewCurrent}
          freshness={rowFreshness}
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {cards.map(card => (
            <TonightCard key={card.key} card={card} />
          ))}
        </div>
        {sectionLimitations.length > 0 && (
          <div className="mt-3 border border-dirt bg-dugout p-4">
            <h3 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Limitations
            </h3>
            <ul className="mt-2 space-y-1">
              {sectionLimitations.map(item => (
                <li key={item} className="text-xs leading-relaxed text-chalk500">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </SectionShell>
    )
  }

  return (
    <SectionShell
      id="tonight"
      eyebrow="Tonight"
      title={TONIGHT_SECTION_TITLE}
      subtitle={TONIGHT_SECTION_SUBTITLE}
    >
      {!Boolean(error && !tonight) && (
        <TonightFreshnessRow
          slateDate={slateDate}
          dataThrough={dataThrough}
          lastSync={lastSync}
          generatedAt={generatedAt}
          stale={staleWithError || slateUnavailable}
          slateUnavailable={staleWithError || slateUnavailable}
          publishedViewCurrent={publishedViewCurrent}
          freshness={rowFreshness}
        />
      )}
      <TonightEmptyState
        isError={showUnavailable}
        emptyReason={emptyReason}
        onRetry={onRetry}
      />
    </SectionShell>
  )
}

function BullpenPicture({
  landscape,
  loading,
  error,
  staleWithError,
  onRetry,
  freshness,
}) {
  const picture = getBullpenPictureView(landscape)
  const rowFreshness = freshnessIsCurrent(freshness)
    ? freshness
    : sectionFreshness(landscape, freshness)
  const dataThrough = firstTextValue(
    landscape?.games?.as_of_date,
    freshnessDataThrough(rowFreshness),
  )
  const lastSync = firstTextValue(rowFreshness?.last_successful_sync, rowFreshness?.lastSuccessfulSync)
  return (
    <SectionShell
      id="bullpen-picture"
      eyebrow="Today's Bullpen Picture"
      title="Today's Bullpen Picture"
      subtitle="A quick look at which bullpens look rested and available, stretched, or on watch."
    >
      {loading && !landscape ? (
        <div className="border border-dirt bg-dugout p-4" role="status" aria-live="polite">
          <p className="font-mono text-xs uppercase tracking-widest text-chalk500">
            Loading bullpen picture...
          </p>
        </div>
      ) : error && !landscape ? (
        <UnavailableDataState
          title="No current bullpen read available."
          message="Today's bullpen picture is temporarily unavailable."
          onRetry={onRetry}
        />
      ) : !picture.hasLandscape ? (
        <UnavailableDataState
          title="No current bullpen read available."
          message="No league bullpen picture is available for the current view."
        />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice
              dataThrough={dataThrough}
              onRetry={onRetry}
            />
          )}
          <SectionFreshnessRow
            dataThrough={dataThrough}
            lastSync={lastSync}
            stale={staleWithError}
            freshness={rowFreshness}
          />
          {/* Teaser strip: one standout team per lane. The Dashboard owns the
              full league landscape — Today only points there. */}
          <div className="border border-dirt bg-dugout p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <p className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
                {picture.teamsEvaluated} tracked teams
              </p>
              {picture.gamesLabel && (
                <p className="font-mono text-[11px] leading-relaxed text-chalk600">
                  {picture.gamesLabel}
                </p>
              )}
            </div>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              {picture.columns.map(column => (
                <div key={column.title} className="min-w-0 border border-dirt/75 bg-field/45 p-3">
                  <h3 className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
                    {column.title}
                  </h3>
                  {column.lead ? (
                    <>
                      {column.lead.teamHref ? (
                        <Link
                          to={column.lead.teamHref}
                          className="group mt-2 flex min-w-0 items-baseline justify-between gap-2 rounded px-1 py-1 transition-colors hover:bg-amber/5"
                          aria-label={`Open the bullpen board for ${column.lead.teamName || column.lead.label}`}
                        >
                          <span className="truncate text-sm text-chalk200 group-hover:text-amber">
                            {column.lead.label}
                          </span>
                          <span className="shrink-0 font-mono text-xs leading-snug text-chalk400">
                            {column.lead[column.metric]} <span className="text-chalk600">{column.suffix}</span>
                          </span>
                        </Link>
                      ) : (
                        // Fail closed: without a resolvable team identifier there is no
                        // exact Team Board to open, so the standout stays a plain read
                        // instead of a link that promises a team page it cannot deliver.
                        <div className="mt-2 flex min-w-0 items-baseline justify-between gap-2 px-1 py-1">
                          <span className="truncate text-sm text-chalk200">
                            {column.lead.label}
                          </span>
                          <span className="shrink-0 font-mono text-xs leading-snug text-chalk400">
                            {column.lead[column.metric]} <span className="text-chalk600">{column.suffix}</span>
                          </span>
                        </div>
                      )}
                      {column.moreCount > 0 && (
                        <p className="mt-1 px-1 font-mono text-[11px] text-chalk600">
                          +{column.moreCount} more on the league board
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="mt-3 text-xs text-chalk600">
                      {column.emptyCopy}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-start">
              <Link
                to="/dashboard"
                className="inline-flex min-h-10 items-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
              >
                View full league board
              </Link>
            </div>
          </div>
        </>
      )}
    </SectionShell>
  )
}

// Compact primary-action row placed right after the daily read. It helps a
// first-time visitor reach the strongest surfaces without hunting through the
// product, and stays short so it never reads as a marketing landing page.
function ExploreBaseballOS() {
  return (
    <section id="explore-baseballos" aria-labelledby="explore-baseballos-title" className="mb-10">
      <div className="mb-3 border-t border-dirt pt-4">
        <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-amber/75">
          Explore BaseballOS
        </div>
        <h2 id="explore-baseballos-title" className="font-display text-2xl tracking-wide text-chalk100">
          Where do you want to go next?
        </h2>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {FIRST_USE_ACTIONS.map(action => (
          <Link
            key={action.title}
            to={action.to}
            className="min-w-0 rounded border border-dirt bg-dugout p-4 transition-colors hover:border-amber/40 hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
          >
            <h3 className="font-display text-lg tracking-wide text-chalk100">
              {action.title}
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-chalk500">
              {action.body}
            </p>
          </Link>
        ))}
      </div>
    </section>
  )
}

function Explore() {
  return (
    <SectionShell
      id="explore"
      eyebrow="Learn & Explore"
      title="Learn & Explore BaseballOS"
      subtitle="Get to know BaseballOS, then dig into every bullpen."
      className="mb-6"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {EXPLORE_LINKS.map(link => (
          <Link
            key={link.title}
            to={link.to}
            className="min-w-0 border border-dirt bg-dugout p-4 transition-colors hover:border-amber/35 hover:bg-amber/5"
          >
            <h3 className="font-display text-xl tracking-wide text-chalk100">
              {link.title}
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-chalk500">
              {link.body}
            </p>
          </Link>
        ))}
      </div>
    </SectionShell>
  )
}

export function IntelligenceSurfaceView({
  tonight = null,
  tonightLoading = false,
  tonightError = null,
  tonightStaleWithError = false,
  onRetryTonight,
  landscape = null,
  landscapeLoading = false,
  landscapeError = null,
  landscapeStaleWithError = false,
  onRetryLandscape,
  dashboard = null,
  teams = [],
}) {
  const pageFreshness = dashboardFreshness(dashboard)

  return (
    <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 lg:px-8">
      <SeesHeader />
      <BullpenPicture
        landscape={landscape}
        loading={landscapeLoading}
        error={landscapeError}
        staleWithError={landscapeStaleWithError}
        onRetry={onRetryLandscape}
        freshness={pageFreshness}
      />
      <ExploreBaseballOS />
      <SinceYesterdaySection dashboard={dashboard} teams={teams} />
      <TonightSection
        tonight={tonight}
        teams={teams}
        loading={tonightLoading}
        error={tonightError}
        staleWithError={tonightStaleWithError}
        onRetry={onRetryTonight}
        dashboard={dashboard}
      />
      <Explore />
    </div>
  )
}

export default function IntelligenceSurfacePage() {
  const tonight = useFetch(getTonightIntelligence)
  const landscape = useFetch(getBullpenLandscape)
  const dashboard = useFetch(getBullpenDashboard)
  const teams = useFetch(getTeams)

  return (
    <IntelligenceSurfaceView
      tonight={tonight.data}
      tonightLoading={tonight.loading}
      tonightError={tonight.error}
      tonightStaleWithError={tonight.staleWithError}
      onRetryTonight={tonight.refetch}
      landscape={landscape.data}
      landscapeLoading={landscape.loading}
      landscapeError={landscape.error}
      landscapeStaleWithError={landscape.staleWithError}
      onRetryLandscape={landscape.refetch}
      dashboard={dashboard.data}
      dashboardLoading={dashboard.loading}
      dashboardError={dashboard.error}
      dashboardStaleWithError={dashboard.staleWithError}
      onRetryDashboard={dashboard.refetch}
      teams={teams.data || []}
    />
  )
}
