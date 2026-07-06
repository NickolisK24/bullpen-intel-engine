import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import {
  getBullpenDashboard,
  getBullpenLandscape,
  getTeams,
  getTonightIntelligence,
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
import {
  BULLPEN_LANDSCAPE_COLUMNS,
  getLandscapeView,
} from '../dashboard/bullpenLandscapeView'
import {
  ANALYTICS_EVENTS,
  trackAnalyticsEvent,
  trackAnalyticsEventOnce,
} from '../../utils/analytics'

const AROUND_BASEBALL_UNAVAILABLE =
  'No other league bullpen movement is ready to show yet.'
const TONIGHT_SECTION_TITLE = "Tonight's Bullpen Watch"
const TONIGHT_SECTION_SUBTITLE =
  'What BaseballOS is watching before first pitch.'
const TONIGHT_EMPTY_TITLE =
  'No standout bullpen watch point tonight.'
const TONIGHT_EMPTY_BODY =
  'No standout bullpen watch point tonight based on the latest available usage data.'
const TONIGHT_ERROR_TITLE =
  "Tonight's bullpen reads are temporarily unavailable."
const TONIGHT_ERROR_BODY =
  'The rest of Today can still be used.'
const WEEKLY_NOTES_MAILTO =
  'mailto:baseballoshq@gmail.com?subject=BaseballOS%20weekly%20bullpen%20notes&body=I%27d%20like%20weekly%20bullpen%20notes.%0A%0AFavorite%20team%3A%20'

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

function aroundTeamLabel(team) {
  return cleanTeamName(team?.teamName) || textValue(team?.teamAbbr) || 'This bullpen'
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

function publishedFreshnessBadgeLabel(stale, freshness) {
  const sample = isSampleFreshness(freshness)
  const syncStatus = String(freshness?.sync_status || '').toLowerCase()
  const staleState = String(freshness?.freshness_state || freshness?.state || '').toLowerCase()
  const publishedCurrent = !sample
    && !stale
    && freshness?.is_current !== false
    && freshness?.is_stale !== true
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
  freshness,
}) {
  const sample = isSampleFreshness(freshness)
  if (!slateDate && !dataThrough && !lastSync && !generatedAt && !stale && !freshness) return null
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <SlateDateStamp date={slateDate} />
      {(dataThrough || lastSync || stale || freshness) && (
        <FreshnessBadge
          state={stale ? 'stale' : 'current'}
          freshness={freshness}
          label={publishedFreshnessBadgeLabel(stale, freshness)}
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

function sameTeam(left, right) {
  const leftId = teamIdOf(left?.team_id ?? left?.teamId)
  const rightId = teamIdOf(right?.team_id ?? right?.teamId)
  if (leftId != null && rightId != null) return leftId === rightId
  const leftAbbr = textValue(left?.team_abbreviation ?? left?.teamAbbr)
  const rightAbbr = textValue(right?.team_abbreviation ?? right?.teamAbbr)
  return Boolean(leftAbbr && rightAbbr && leftAbbr.toLowerCase() === rightAbbr.toLowerCase())
}

function restedMovement(item) {
  const text = [
    item?.public_headline,
    item?.public_summary,
  ].map(textValue).filter(Boolean).join(' ')

  const moved = /\bmoved\s+from\s+(\d+)\s+to\s+(\d+)\s+rested\s+relievers?\b/i.exec(text)
  if (moved) {
    const from = numberValue(moved[1])
    const to = numberValue(moved[2])
    if (from != null && to != null) return { from, to, delta: to - from }
  }

  const more = /\b(\d+)\s+more\s+rested\s+relievers?\b/i.exec(text)
  if (more) {
    const delta = numberValue(more[1])
    if (delta != null) return { from: null, to: null, delta }
  }

  const fewer = /\b(\d+)\s+fewer\s+rested\s+relievers?\b/i.exec(text)
  if (fewer) {
    const delta = numberValue(fewer[1])
    if (delta != null) return { from: null, to: null, delta: -delta }
  }

  return null
}

function aroundBaseballTitle(item, team) {
  const label = aroundTeamLabel(team)
  const movement = restedMovement(item)
  if (movement) {
    if (movement.delta > 1) return `${label} added ${movement.delta} rested arms`
    if (movement.delta === 1) return `${label} added a rested arm`
    if (movement.delta < -1) return `${label} lost ${Math.abs(movement.delta)} rested arms`
    if (movement.delta === -1) return `${label} lost a rested arm`
    return `${label} held steady`
  }

  const rawTitle = textValue(item?.public_headline)
  if (rawTitle && !/\bmoved\s+from\b/i.test(rawTitle)) return publicTerminology(rawTitle)
  return `${label} bullpen movement`
}

export function getAroundBaseballItems(dashboard, leadStory, limit = 3) {
  const rawItems = dashboard?.what_changed_since_yesterday?.items
  const items = Array.isArray(rawItems) ? rawItems : []
  const leadTeam = leadStory?.team || null

  return items
    .filter(item => !sameTeam(item, leadTeam))
    .map(item => {
      const team = teamOptionValue(item)
      const title = aroundBaseballTitle(item, team)
      const body = publicTerminology(textValue(item.public_summary))
      if (!title || !body) return null
      return {
        key: textValue(item.key) || `${team?.teamId || team?.teamAbbr || title}`,
        title,
        body,
        teamName: team?.teamName || team?.teamAbbr || 'Team',
        teamAbbr: team?.teamAbbr || null,
        teamId: team?.teamId ?? null,
        href: teamBoardHref(team, 'intelligence-around-baseball'),
      }
    })
    .filter(Boolean)
    .slice(0, limit)
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
        starterDependency: cleanTonightCopy(story?.starter_dependency),
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
      return {
        ...spec,
        entries: Array.isArray(column.entries) ? column.entries : [],
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

function SeesHeader() {
  const handleNewsletterInterest = () => {
    trackAnalyticsEvent(ANALYTICS_EVENTS.NEWSLETTER_INTEREST_CLICKED, {
      surface: 'home',
      route: '/',
      source: 'hero_cta',
    })
  }

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
      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <a
          href="#bullpen-picture"
          className="inline-flex w-full items-center justify-center rounded border border-amber/40 bg-amber/10 px-4 py-3 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60 sm:w-auto"
        >
          Explore today's bullpen picture
        </a>
        <a
          href={WEEKLY_NOTES_MAILTO}
          onClick={handleNewsletterInterest}
          className="inline-flex w-full items-center justify-center rounded border border-dirt bg-field/60 px-4 py-3 font-mono text-xs uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60 sm:w-auto"
        >
          Get the weekly Bullpen Report
        </a>
      </div>
      <p className="mt-3 max-w-xl text-xs leading-relaxed text-chalk500">
        One email a week. No spam, no picks.
      </p>
    </header>
  )
}

function UpcomingGames() {
  return (
    <SectionShell
      id="upcoming-games"
      eyebrow="Today"
      title="Upcoming Games"
      className="mb-12"
    >
      <div className="border border-dirt bg-dugout p-4">
        <p className="text-sm leading-relaxed text-chalk500">
          Upcoming games will appear here when today’s slate is available.
        </p>
      </div>
    </SectionShell>
  )
}

function AroundBaseball({
  dashboard,
  leadStory,
  loading,
  error,
  staleWithError,
  onRetry,
}) {
  const items = getAroundBaseballItems(dashboard, leadStory)
  const freshness = dashboardFreshness(dashboard)
  const rowFreshness = sectionFreshness(dashboard, freshness)
  const dataThrough = textValue(rowFreshness?.data_through)
  const lastSync = textValue(rowFreshness?.last_successful_sync)
  return (
    <SectionShell
      id="around-baseball"
      eyebrow="Around Baseball"
      title="Around Baseball"
      subtitle="Other bullpen movement BaseballOS is tracking across the league."
    >
      {loading && !dashboard ? (
        <div className="border border-dirt bg-dugout p-4" role="status" aria-live="polite">
          <p className="font-mono text-xs uppercase tracking-widest text-chalk500">
            Loading secondary observations...
          </p>
        </div>
      ) : error && !dashboard ? (
        <div className="border border-dirt bg-dugout p-4">
          <p className="text-sm leading-relaxed text-chalk500">
            {AROUND_BASEBALL_UNAVAILABLE}
          </p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 rounded border border-dirt px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
            >
              Try Again
            </button>
          )}
        </div>
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
          {items.length ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {items.map(item => (
                <Link
                  key={item.key}
                  to={item.href}
                  onClick={() => trackAnalyticsEvent(ANALYTICS_EVENTS.TEAM_INTEREST_CLICKED, {
                    surface: 'home',
                    route: '/',
                    source: 'around_baseball',
                    team_abbrev: item.teamAbbr,
                    team_id: item.teamId,
                  })}
                  className="min-w-0 border border-dirt bg-dugout p-4 transition-colors hover:border-amber/35 hover:bg-amber/5"
                  aria-label={`Open the bullpen board for ${item.teamName}`}
                >
                  <h3 className="break-words font-display text-xl leading-tight tracking-wide text-chalk100">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-chalk400">
                    {item.body}
                  </p>
                </Link>
              ))}
            </div>
          ) : (
            <div className="border border-dirt bg-dugout p-4">
              <p className="text-sm leading-relaxed text-chalk500">
                {AROUND_BASEBALL_UNAVAILABLE}
              </p>
            </div>
          )}
        </>
      )}
    </SectionShell>
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

function TonightEmptyState({ isError, onRetry }) {
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
  const missingCompletedPayload = !tonight && !loading && !error
  const rowFreshness = sectionFreshness(
    missingCompletedPayload ? { status: 'error' } : tonight,
    freshness,
  )
  const slateDate = textValue(tonight?.reference_date)
  const dataThrough = textValue(rowFreshness?.data_through)
  const lastSync = textValue(rowFreshness?.last_successful_sync)
  const generatedAt = textValue(tonight?.snapshot?.generated_at)
  const emptyReason = textValue(tonight?.empty_reason)
  const snapshotUnavailable = [
    'tonight_live_build_timeout',
    'tonight_snapshot_build_unavailable',
    'tonight_snapshot_unavailable',
  ].includes(emptyReason)
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
          stale={staleWithError || snapshotUnavailable || missingCompletedPayload}
          freshness={rowFreshness}
        />
      )}
      <TonightEmptyState isError={showUnavailable} onRetry={onRetry} />
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
  const rowFreshness = sectionFreshness(landscape, freshness)
  const dataThrough = firstTextValue(
    landscape?.games?.as_of_date,
    rowFreshness?.data_through,
  )
  const lastSync = textValue(rowFreshness?.last_successful_sync)
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
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {picture.columns.map(column => (
                <div key={column.title} className="min-w-0 border border-dirt/75 bg-field/45 p-3">
                  <h3 className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
                    {column.title}
                  </h3>
                  {column.entries.length ? (
                    <ol className="mt-3 space-y-2">
                      {column.entries.map(entry => (
                        <li key={entry.teamId ?? entry.label}>
                          <Link
                            to={entry.teamHref || '/bullpen'}
                            onClick={() => trackAnalyticsEvent(ANALYTICS_EVENTS.TEAM_INTEREST_CLICKED, {
                              surface: 'home',
                              route: '/',
                              source: 'bullpen_picture',
                              team_abbrev: entry.teamAbbrev,
                              team_id: entry.teamId,
                            })}
                            className="group flex min-w-0 flex-col items-start gap-1 rounded px-1 py-1 transition-colors hover:bg-amber/5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-2"
                            aria-label={`Open the bullpen board for ${entry.teamName || entry.label}`}
                          >
                            <span className="truncate text-sm text-chalk200 group-hover:text-amber">
                              {entry.label}
                            </span>
                            <span className="max-w-full break-words font-mono text-xs leading-snug text-chalk400 sm:shrink-0 sm:text-right">
                              {entry[column.metric]} <span className="text-chalk600">{column.suffix}</span>
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ol>
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
      <UpcomingGames />
      <BullpenPicture
        landscape={landscape}
        loading={landscapeLoading}
        error={landscapeError}
        staleWithError={landscapeStaleWithError}
        onRetry={onRetryLandscape}
        freshness={pageFreshness}
      />
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
