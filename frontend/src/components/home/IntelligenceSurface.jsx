import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import {
  getBullpenDashboard,
  getBullpenLandscape,
  getTeams,
  getTonightIntelligence,
  signupAudience,
} from '../../utils/api'
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
  ANALYTICS_EVENTS,
  trackAnalyticsEvent,
  trackAnalyticsEventOnce,
} from '../../utils/analytics'
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
const SINCE_YESTERDAY_TEAM_LINK_SOURCE = 'since-yesterday'
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

function teamBoardHref(team, source = 'intelligence-surface') {
  const teamParam = textValue(team?.teamAbbr) || (
    team?.teamId != null ? String(team.teamId) : null
  )
  if (!teamParam) return '/bullpen?view=board'
  const query = new URLSearchParams({
    view: 'board',
    team: teamParam,
    source,
  })
  return `/bullpen?${query.toString()}`
}

function teamBoardHrefIfResolvable(team, source = 'intelligence-surface') {
  const teamParam = textValue(team?.teamAbbr) || (
    team?.teamId != null ? String(team.teamId) : null
  )
  if (!teamParam) return null
  const query = new URLSearchParams({
    view: 'board',
    team: teamParam,
    source,
  })
  return `/bullpen?${query.toString()}`
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

  if (!teamName && !headline && !summary && !context) return null

  return {
    key: textValue(item.key) || `${resolvedTeamId || teamAbbr || teamName || 'team'}-${index}`,
    teamId: resolvedTeamId,
    teamName: teamName || teamAbbr || 'This club',
    teamAbbr,
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

export function trackSinceYesterdayViewed(view, options = {}) {
  if (!view?.state) return Promise.resolve(false)
  return trackAnalyticsEventOnce(ANALYTICS_EVENTS.WHAT_CHANGED_VIEWED, {
    surface: 'home',
    route: '/',
    source: SINCE_YESTERDAY_SOURCE,
    state: view.state,
  }, options)
}

export function trackSinceYesterdayItemOpened(item, options = {}) {
  if (!item) return Promise.resolve(false)
  return trackAnalyticsEvent(ANALYTICS_EVENTS.WHAT_CHANGED_ITEM_OPENED, {
    surface: 'home',
    route: '/',
    source: SINCE_YESTERDAY_SOURCE,
    team_id: item.teamId,
    team_abbrev: item.teamAbbr,
  }, options)
}

export function trackSinceYesterdayTeamClicked(item, options = {}) {
  if (!item) return Promise.resolve(false)
  return trackAnalyticsEvent(ANALYTICS_EVENTS.WHAT_CHANGED_TEAM_CLICKED, {
    surface: 'home',
    route: '/',
    source: SINCE_YESTERDAY_SOURCE,
    team_id: item.teamId,
    team_abbrev: item.teamAbbr,
  }, options)
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
        href: teamBoardHrefIfResolvable(team, 'intelligence-tonight'),
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
    const submitted = await submitAudienceSignup({
      email,
      signup: (value) => signupAudience(value, { source: AUDIENCE_SIGNUP_SOURCE }),
      setStatus,
      setError,
    })
    if (submitted) {
      trackAnalyticsEvent(ANALYTICS_EVENTS.NEWSLETTER_INTEREST_CLICKED, {
        surface: 'home',
        route: '/',
        source: 'email_capture_form',
      })
    }
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
          onClick={() => trackAnalyticsEvent(ANALYTICS_EVENTS.TEAM_INTEREST_CLICKED, {
            surface: 'home',
            route: '/',
            source: 'tonights_bullpen_watch',
            team_abbrev: card.teamAbbr,
            team_id: card.teamId,
          })}
          className="mt-5 inline-flex min-h-10 w-fit items-center rounded border border-dirt bg-field/60 px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
          aria-label={`Open the bullpen board for ${card.teamName}`}
        >
          View Team Bullpen State
        </Link>
      )}
    </article>
  )
}

function SinceYesterdayItem({ item }) {
  return (
    <details
      className="group border border-dirt bg-dugout p-0"
      onToggle={event => {
        if (event.currentTarget.open) {
          trackSinceYesterdayItemOpened(item)
        }
      }}
    >
      <summary className="flex cursor-pointer list-none flex-col gap-1 px-4 py-3 transition-colors hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
        <span className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
          {item.teamName}
        </span>
        {item.headline && (
          <span className="font-display text-xl leading-tight tracking-wide text-chalk100">
            {item.headline}
          </span>
        )}
      </summary>
      <div className="border-t border-dirt px-4 py-4">
        {item.summary && (
          <p className="text-sm leading-relaxed text-chalk300">
            {item.summary}
          </p>
        )}
        {item.context && (
          <p className="mt-2 text-sm leading-relaxed text-chalk500">
            {item.context}
          </p>
        )}
        {item.publicEvidence.length > 0 && (
          <div className="mt-4 border border-dirt/75 bg-field/45 p-3">
            <h3 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Evidence shown
            </h3>
            <dl className="mt-2 space-y-2">
              {item.publicEvidence.map(row => (
                <div key={row.key} className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-baseline sm:gap-3">
                  <dt className="text-chalk300">{row.label}</dt>
                  <dd className="font-mono text-xs uppercase tracking-wider text-chalk500">
                    Yesterday {row.yesterday}
                  </dd>
                  <dd className="font-mono text-xs uppercase tracking-wider text-chalk500">
                    Today {row.today}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {item.hasRestedCounts && (
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:max-w-sm">
            <div className="border border-dirt/75 bg-field/45 p-3">
              <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Yesterday
              </dt>
              <dd className="mt-1 font-display text-2xl tracking-wide text-chalk100">
                {item.yesterdayRestedCount}
              </dd>
              <dd className="mt-1 text-xs text-chalk500">
                rested relievers
              </dd>
            </div>
            <div className="border border-dirt/75 bg-field/45 p-3">
              <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Today
              </dt>
              <dd className="mt-1 font-display text-2xl tracking-wide text-chalk100">
                {item.todayRestedCount}
              </dd>
              <dd className="mt-1 text-xs text-chalk500">
                rested relievers
              </dd>
            </div>
          </dl>
        )}
        {item.workloadAdded.length > 0 && (
          <div className="mt-4 border border-dirt/75 bg-field/45 p-3">
            <h3 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Workload added
            </h3>
            <ul className="mt-2 space-y-1">
              {item.workloadAdded.map(row => (
                <li key={row.key} className="flex flex-wrap items-baseline justify-between gap-2 text-sm text-chalk300">
                  <span>{row.name}</span>
                  <span className="font-mono text-xs uppercase tracking-wider text-chalk500">
                    {row.pitches} {row.pitches === 1 ? 'pitch' : 'pitches'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {item.href && (
          <div className="mt-4">
            <Link
              to={item.href}
              onClick={() => trackSinceYesterdayTeamClicked(item)}
              className="inline-flex min-h-10 items-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
              aria-label={`Open the bullpen board for ${item.teamName}`}
            >
              Open team bullpen board
            </Link>
          </div>
        )}
      </div>
    </details>
  )
}

function SinceYesterdaySection({ dashboard, teams }) {
  const view = getSinceYesterdayView(dashboard, teams)

  useEffect(() => {
    trackSinceYesterdayViewed(view)
  }, [view?.state])

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
        <>
          <div className="grid grid-cols-1 gap-3">
            {view.items.map(item => (
              <SinceYesterdayItem key={item.key} item={item} />
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-chalk500">
            {view.footerCopy}
          </p>
        </>
      ) : (
        <div className="border border-dirt bg-dugout p-4" role="status">
          <p className="text-sm leading-relaxed text-chalk300">
            {view.state === 'no_meaningful_changes'
              ? view.quietCopy
              : view.unavailableCopy}
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
                      <Link
                        to={column.lead.teamHref || '/bullpen'}
                        onClick={() => trackAnalyticsEvent(ANALYTICS_EVENTS.TEAM_INTEREST_CLICKED, {
                          surface: 'home',
                          route: '/',
                          source: 'bullpen_picture',
                          team_abbrev: column.lead.teamAbbrev,
                          team_id: column.lead.teamId,
                        })}
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

  useEffect(() => {
    trackAnalyticsEventOnce(ANALYTICS_EVENTS.HOMEPAGE_VIEWED, {
      surface: 'home',
      route: '/',
      source: 'page',
    })
  }, [])

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
