import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import {
  getBullpenDashboard,
  getBullpenLandscape,
  getTeams,
  getTodayIntelligence,
  getTonightIntelligence,
} from '../../utils/api'
import {
  DataThroughStamp,
  FreshnessBadge,
  LastSyncLabel,
  StaleDataNotice,
  UnavailableDataState,
} from '../UI'
import { getLandscapeView } from '../dashboard/bullpenLandscapeView'

const AROUND_BASEBALL_UNAVAILABLE =
  'No other league bullpen movement is ready to show yet.'
const TONIGHT_EMPTY_TITLE =
  'No Tonight bullpen read has cleared the bar yet.'
const TONIGHT_EMPTY_BODY =
  'BaseballOS will only surface a pregame card when schedule context and bullpen evidence are strong enough.'
const TONIGHT_ERROR_TITLE =
  "Tonight's bullpen reads are temporarily unavailable."
const TONIGHT_ERROR_BODY =
  'The rest of the Intelligence Surface can still be used.'

const EMPTY_REASON_COPY = {
  no_completed_game_contexts: 'No completed-game contexts are available for the current reference date.',
  no_publishable_coin_story: 'No publishable bullpen story is available from the current completed-game context.',
  lead_story_unavailable: 'The lead story service is unavailable right now.',
}

const EXPLORE_LINKS = [
  {
    title: 'Teams',
    body: 'Open the team bullpen board.',
    to: '/bullpen',
  },
  {
    title: 'Compare',
    body: 'Compare two bullpen pictures side by side.',
    to: '/bullpen?view=compare',
  },
  {
    title: 'Trust',
    body: 'Review data freshness and evidence.',
    to: '/trust',
  },
  {
    title: 'Methodology',
    body: 'See how the bullpen read is built.',
    to: '/methodology',
  },
]

function textValue(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
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

function firstTextValue(...values) {
  return values.map(textValue).find(Boolean) || null
}

function firstObjectValue(...values) {
  return values.find(value => value && typeof value === 'object') || null
}

function dashboardFreshness(dashboard) {
  return firstObjectValue(dashboard?.freshness)
}

function SectionFreshnessRow({
  dataThrough,
  lastSync,
  stale = false,
  className = '',
}) {
  if (!dataThrough && !lastSync && !stale) return null
  return (
    <div className={`mb-3 flex flex-wrap items-center gap-2 ${className}`}>
      <FreshnessBadge state={stale ? 'stale' : 'current'} />
      <DataThroughStamp date={dataThrough} />
      <LastSyncLabel value={lastSync} />
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
  if (cleanOptionsCount != null) rows.push(`Clean options: ${cleanOptionsCount}`)
  if (optionalityBand) rows.push(`Current standing: ${optionalityBand}`)
  if (concentrationBand) rows.push(`Workload shape: ${concentrationBand}`)
  if (cleanOptions.length > 0) {
    rows.push(`Named clean options: ${cleanOptions.slice(0, 3).join(', ')}`)
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
  const headline = textValue(draft?.headline) || 'BaseballOS is watching this bullpen story.'
  const body = textValue(draft?.body || draft?.text) || ''
  const team = resolveLeadTeam(lead, teams)

  return {
    hasStory: true,
    team,
    headline,
    body,
    observations: cleanDraftList(draft?.observations),
    evidence: cleanDraftList(draft?.evidence),
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
  if (rawTitle && !/\bmoved\s+from\b/i.test(rawTitle)) return rawTitle
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
      const body = textValue(item.public_summary)
      if (!title || !body) return null
      return {
        key: textValue(item.key) || `${team?.teamId || team?.teamAbbr || title}`,
        title,
        body,
        teamName: team?.teamName || team?.teamAbbr || 'Team',
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
      const headline = textValue(card?.headline)
      const summary = textValue(card?.summary)
      if (!teamName || !headline || !summary) return null
      return {
        key: textValue(card?.key) || [
          team?.teamId,
          team?.teamAbbr,
          teamName,
          headline,
        ].filter(Boolean).join('-'),
        teamName,
        headline,
        summary,
        evidence: cleanDraftList(card?.evidence),
        limitations: cleanDraftList(card?.limitations),
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

  const specs = [
    {
      sourceKey: 'available',
      title: 'Most Available',
      metric: 'available',
      suffix: 'rested enough to use',
    },
    {
      sourceKey: 'constrained',
      title: 'Most Constrained',
      metric: 'restricted',
      suffix: 'needing rest or unavailable',
    },
    {
      sourceKey: 'monitoring',
      title: 'Worth Watching',
      metric: 'monitor',
      suffix: 'on watch',
    },
  ]

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
  return (
    <header className="mb-7 max-w-4xl pt-2 sm:pt-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-amber/75">
        Intelligence Surface
      </div>
      <h1 className="mt-3 font-display text-5xl leading-none tracking-wide text-chalk100 sm:text-6xl lg:text-7xl">
        What BaseballOS Sees
      </h1>
      <p className="mt-4 max-w-3xl text-base leading-relaxed text-chalk300 sm:text-lg">
        Every morning BaseballOS watches every bullpen in baseball and surfaces the bullpen story that mattered most.
      </p>
    </header>
  )
}

function StoryEmptyState({ intelligence }) {
  const emptyReason = emptyReasonText(intelligence?.empty_reason)
  return (
    <UnavailableDataState
      title="No lead bullpen story has cleared the bar yet."
      message="BaseballOS is still reviewing the latest completed-game context and will only surface a lead story when the evidence is strong enough."
      detail={emptyReason}
      className="p-5 sm:p-7"
      titleClassName="font-display text-3xl leading-none tracking-wide text-chalk100"
      messageClassName="mt-3 max-w-3xl text-sm leading-relaxed text-chalk400"
    />
  )
}

function StoryLoadingState() {
  return (
    <article
      className="relative min-h-[28rem] overflow-hidden border border-amber/25 bg-dugout bg-stadium-glow p-5 sm:p-7 lg:min-h-[30rem] lg:p-8"
      role="status"
      aria-live="polite"
    >
      <div className="pointer-events-none absolute inset-0 bg-grid-lines opacity-50" />
      <div className="relative z-10">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Today's Story
        </div>
        <h3 className="mt-4 max-w-3xl font-display text-4xl leading-none tracking-wide text-chalk100 sm:text-5xl lg:text-6xl">
          Reading the latest completed-game context...
        </h3>
        <p className="mt-5 max-w-2xl text-sm leading-relaxed text-chalk400 sm:text-base">
          Loading today's lead story...
        </p>
        <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
          <div className="space-y-3" aria-hidden="true">
            <div className="h-3 w-32 animate-pulse bg-dirt" />
            <div className="h-3 w-full max-w-xl animate-pulse bg-dirt" />
            <div className="h-3 w-11/12 max-w-lg animate-pulse bg-dirt" />
            <div className="h-3 w-2/3 max-w-md animate-pulse bg-dirt" />
          </div>
          <div className="border border-dirt/80 bg-field/50 p-4" aria-hidden="true">
            <div className="h-3 w-36 animate-pulse bg-dirt" />
            <div className="mt-4 space-y-3">
              <div className="h-3 w-4/5 animate-pulse bg-dirt" />
              <div className="h-3 w-3/5 animate-pulse bg-dirt" />
              <div className="h-3 w-2/3 animate-pulse bg-dirt" />
            </div>
          </div>
        </div>
      </div>
    </article>
  )
}

function LeadMetadata({ items }) {
  if (!items.length) return null
  return (
    <dl className="mt-5 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
      {items.map(item => (
        <div key={item.label} className="border border-dirt/70 bg-field/45 px-3 py-2">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            {item.label}
          </dt>
          <dd className="mt-1 text-sm leading-snug text-chalk200">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function TodaysStory({
  intelligence,
  teams,
  loading,
  error,
  staleWithError,
  onRetry,
  freshness,
}) {
  const story = getLeadStoryView(intelligence, teams)
  const dataThrough = firstTextValue(intelligence?.reference_date, freshness?.data_through)
  const lastSync = textValue(freshness?.last_successful_sync)
  return (
    <SectionShell
      id="todays-story"
      eyebrow="Today's Story"
      title="Today's Story"
      subtitle="The single bullpen story BaseballOS saw first."
      className="mb-12"
    >
      {loading && !intelligence ? (
        <StoryLoadingState />
      ) : error && !intelligence ? (
        <UnavailableDataState
          title="No current bullpen read available."
          message="Today's lead story is temporarily unavailable."
          onRetry={onRetry}
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
          />

          {!story.hasStory ? (
            <StoryEmptyState intelligence={intelligence} />
          ) : (
            <article className="relative overflow-hidden border border-amber/30 bg-dugout bg-stadium-glow p-5 sm:p-7 lg:p-8">
              <div className="pointer-events-none absolute inset-0 bg-grid-lines opacity-60" />
              <div className="relative z-10">
                <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-chalk500">
                  <span>{story.team.label}</span>
                  {story.referenceDate && (
                    <>
                      <span aria-hidden="true">/</span>
                      <span>{story.referenceDate}</span>
                    </>
                  )}
                </div>

                <h3 className="mt-4 max-w-4xl break-words font-display text-4xl leading-none tracking-wide text-chalk100 sm:text-5xl lg:text-6xl">
                  {story.headline}
                </h3>
                {story.body && (
                  <p className="mt-5 max-w-3xl text-lg leading-relaxed text-chalk200 sm:text-xl">
                    {story.body}
                  </p>
                )}

                <div className="mt-7 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
                  <div className="min-w-0">
                    <StoryList title="Why BaseballOS Sees It" items={story.observations} />
                    <StoryList title="Evidence" items={story.evidence} mono />
                  </div>
                  <div className="min-w-0 border border-dirt/80 bg-field/50 p-4">
                    <h4 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                      Bullpen Read
                    </h4>
                    {story.snapshot.length ? (
                      <ul className="mt-3 space-y-2">
                        {story.snapshot.map(item => (
                          <li key={item} className="text-sm leading-relaxed text-chalk300">
                            {item}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-3 text-sm leading-relaxed text-chalk500">
                        No current bullpen read is included with this story.
                      </p>
                    )}
                  </div>
                </div>

                <LeadMetadata items={story.metadata} />

                <div className="mt-6 flex flex-wrap gap-3">
                  <Link
                    to={story.team.href}
                    className="inline-flex min-h-10 items-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
                  >
                    Open Team Board
                  </Link>
                  <Link
                    to="/stories"
                    className="inline-flex min-h-10 items-center rounded border border-dirt bg-field/60 px-4 py-2 font-mono text-xs uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
                  >
                    More Stories
                  </Link>
                </div>
              </div>
            </article>
          )}
        </>
      )}
    </SectionShell>
  )
}

function StoryList({ title, items, mono = false }) {
  if (!items.length) return null
  return (
    <div className="mb-5">
      <h4 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {title}
      </h4>
      <ul className="mt-3 space-y-2">
        {items.map(item => (
          <li key={item} className="flex gap-2 text-sm leading-relaxed text-chalk300">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber/70" aria-hidden="true" />
            <span className={mono ? 'font-mono text-xs text-chalk300' : ''}>{item}</span>
          </li>
        ))}
      </ul>
    </div>
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
  const dataThrough = textValue(freshness?.data_through)
  const lastSync = textValue(freshness?.last_successful_sync)
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
          />
          {items.length ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {items.map(item => (
                <Link
                  key={item.key}
                  to={item.href}
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
  return (
    <article className="flex min-w-0 flex-col border border-dirt bg-dugout p-4 sm:p-5">
      <div className="font-mono text-[10px] uppercase tracking-widest text-amber/75">
        {card.teamName}
      </div>
      <h3 className="mt-3 break-words font-display text-2xl leading-tight tracking-wide text-chalk100">
        {card.headline}
      </h3>
      <p className="mt-3 text-sm leading-relaxed text-chalk400">
        {card.summary}
      </p>
      {card.evidence.length > 0 && (
        <div className="mt-4">
          <h4 className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Evidence
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

function TonightSection({
  tonight,
  teams,
  loading,
  error,
  staleWithError,
  onRetry,
  dashboard,
  leadStory,
  dashboardLoading,
  dashboardError,
  dashboardStaleWithError,
  onRetryDashboard,
}) {
  const cards = getTonightCards(tonight, teams)
  const sectionLimitations = cleanDraftList(tonight?.limitations)
  const freshness = dashboardFreshness(dashboard)
  const dataThrough = firstTextValue(tonight?.reference_date, freshness?.data_through)
  const lastSync = textValue(freshness?.last_successful_sync)
  const fallbackItems = getAroundBaseballItems(dashboard, leadStory)
  const canShowFallback = !loading && (
    fallbackItems.length > 0 ||
    (dashboardLoading && !dashboard) ||
    (dashboardStaleWithError && dashboard)
  )

  if (loading && !tonight) {
    return (
      <SectionShell
        id="tonight"
        eyebrow="Tonight"
        title="Tonight"
        subtitle="Bullpen situations BaseballOS is watching before first pitch."
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
        title="Tonight"
        subtitle="Bullpen situations BaseballOS is watching before first pitch."
      >
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

  if (canShowFallback) {
    return (
      <AroundBaseball
        dashboard={dashboard}
        leadStory={leadStory}
        loading={dashboardLoading}
        error={dashboardError}
        staleWithError={dashboardStaleWithError}
        onRetry={onRetryDashboard}
      />
    )
  }

  return (
    <SectionShell
      id="tonight"
      eyebrow="Tonight"
      title="Tonight"
      subtitle="Bullpen situations BaseballOS is watching before first pitch."
    >
      <SectionFreshnessRow
        dataThrough={dataThrough}
        lastSync={lastSync}
        stale={Boolean(error && !tonight)}
      />
      <TonightEmptyState isError={Boolean(error && !tonight)} onRetry={onRetry} />
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
  const dataThrough = firstTextValue(
    landscape?.games?.as_of_date,
    landscape?.reference_date,
    freshness?.data_through,
  )
  const lastSync = textValue(freshness?.last_successful_sync)
  return (
    <SectionShell
      id="bullpen-picture"
      eyebrow="Today's Bullpen Picture"
      title="Today's Bullpen Picture"
      subtitle="A quick look at which bullpens look rested, constrained, or worth monitoring."
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
                      No bullpen currently meets this threshold.
                    </p>
                  )}
                </div>
              ))}
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
      eyebrow="Explore"
      title="Explore"
      subtitle="Quiet paths into the deeper product."
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
  intelligence = null,
  intelligenceLoading = false,
  intelligenceError = null,
  intelligenceStaleWithError = false,
  onRetryIntelligence,
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
  dashboardLoading = false,
  dashboardError = null,
  dashboardStaleWithError = false,
  onRetryDashboard,
  teams = [],
}) {
  const leadStory = getLeadStoryView(intelligence, teams)
  const pageFreshness = dashboardFreshness(dashboard)
  return (
    <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 lg:px-8">
      <SeesHeader />
      <TodaysStory
        intelligence={intelligence}
        teams={teams}
        loading={intelligenceLoading}
        error={intelligenceError}
        staleWithError={intelligenceStaleWithError}
        onRetry={onRetryIntelligence}
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
        leadStory={leadStory}
        dashboardLoading={dashboardLoading}
        dashboardError={dashboardError}
        dashboardStaleWithError={dashboardStaleWithError}
        onRetryDashboard={onRetryDashboard}
      />
      <BullpenPicture
        landscape={landscape}
        loading={landscapeLoading}
        error={landscapeError}
        staleWithError={landscapeStaleWithError}
        onRetry={onRetryLandscape}
        freshness={pageFreshness}
      />
      <Explore />
    </div>
  )
}

export default function IntelligenceSurfacePage() {
  const intelligence = useFetch(getTodayIntelligence)
  const tonight = useFetch(getTonightIntelligence)
  const landscape = useFetch(getBullpenLandscape)
  const dashboard = useFetch(getBullpenDashboard)
  const teams = useFetch(getTeams)

  return (
    <IntelligenceSurfaceView
      intelligence={intelligence.data}
      intelligenceLoading={intelligence.loading}
      intelligenceError={intelligence.error}
      intelligenceStaleWithError={intelligence.staleWithError}
      onRetryIntelligence={intelligence.refetch}
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
