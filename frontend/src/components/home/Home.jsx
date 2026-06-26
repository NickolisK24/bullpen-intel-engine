import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { usePreferredTeamPreference } from '../../hooks/usePreferredTeamPreference'
import {
  useStoryImpressionObservations,
  useTodayLoadedObservation,
} from '../../hooks/useProductIntelligence'
import { getBullpenDashboard, getTeamBullpenBoard, getTeamChanges, getTeams, recordStoryShareClicked, recordStoryTeamBoardOpened } from '../../utils/api'
import { observeStoryShareClicked, observeStoryTeamBoardOpened } from '../../utils/productIntelligence'
import {
  buildPreferredTeamHref,
  preferredTeamLabel,
  preferredTeamSelectionValue,
  readPreferredTeamPreference,
  savePreferredTeamSelectionValue,
} from '../../utils/preferredTeam'
import {
  relationshipFor,
  resolveTodayViewTeam,
  searchWithoutDigestReturnParams,
} from '../../utils/todayDigestReturn'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import TeamShareButton from '../share/TeamShareButton'
import TeamMark from '../team/TeamMark'
import WhatChangedCard from '../dashboard/WhatChangedCard'
import {
  getBoardContextView,
  getBullpenStressView,
} from '../bullpen/board/tonightsBullpenBoardView'
import BullpenStories, { SectionHeading, StoryPresentation } from './BullpenStories'
import DigestReturnNotice from './DigestReturnNotice'
import {
  getHomeRosterStatusLine,
  getMastheadView,
  homeTone,
} from './homePresentationView'
import {
  getCanonicalHeroStory,
  getCanonicalHomeStories,
  getCanonicalLeagueContext,
} from './homeCanonicalStoriesView'

// The Morning Bullpen Report — BaseballOS's story-led front page. Curated,
// not exhaustive: one flagship observation, three things to watch, short
// league context, and a handoff to Stories. The Stories page carries the
// browseable feed and the Bullpen page remains the team directory.
export default function Home() {
  const [searchParams, setSearchParams] = useSearchParams()
  const dash = useFetch(getBullpenDashboard)
  const teams = useFetch(getTeams)
  const teamList = teams.data || []
  const {
    preferredTeam,
    promptDismissed,
    setPreferredTeam,
    dismissPrompt,
    loading: preferredTeamLoading,
    authLoading,
    authenticated,
  } = usePreferredTeamPreference(teamList)
  const search = searchParams.toString() ? `?${searchParams.toString()}` : ''
  const teamsLoaded = Array.isArray(teams.data) || Boolean(teams.error)
  const todayView = resolveTodayViewTeam({
    search,
    teams: teamList,
    teamsLoaded,
    preferredTeam,
  })
  const activeTeam = todayView.viewTeam
  const activeTeamId = activeTeam?.team_id ?? null
  const teamRelationship = relationshipFor({
    urlTeamValid: todayView.urlTeamValid,
    authenticated,
    authLoading,
    viewTeam: activeTeam,
    followedTeam: preferredTeam,
  })
  const preferredBoard = useFetch(
    () => (
      activeTeamId == null
        ? Promise.resolve(null)
        : getTeamBullpenBoard(activeTeamId)
    ),
    [activeTeamId],
  )
  const preferredChanges = useFetch(
    () => (
      activeTeamId == null
        ? Promise.resolve(null)
        : getTeamChanges(activeTeamId)
    ),
    [activeTeamId],
  )

  // An explicit team choice (digest "Switch followed team" or the first-visit
  // picker) must win over the digest link. Persist
  // the choice, then drop the view-only ?team=/source= params so Today follows
  // the followed team instead of staying pinned to the team from the email —
  // keeping the sidebar and Today in agreement. Nothing is cleared on page load
  // or on dismiss; only an explicit selection clears the override.
  const handleSelectPreferredTeam = (team) => {
    if (!team) return
    setPreferredTeam(team)
    const { params, changed } = searchWithoutDigestReturnParams(searchParams)
    if (changed) setSearchParams(params, { replace: true })
  }

  return (
    <HomeView
      dashboard={dash.data}
      teams={teamList}
      teamsLoading={teams.loading}
      teamsError={teams.error}
      preferredTeam={preferredTeam}
      viewTeam={activeTeam}
      teamRelationship={teamRelationship}
      authenticated={authenticated}
      authLoading={authLoading}
      preferredTeamLoading={preferredTeamLoading}
      isDigestReturn={todayView.isDigestReturn && todayView.urlTeamValid}
      urlTeamPending={todayView.urlTeamPending}
      preferredTeamPromptDismissed={promptDismissed}
      onSelectPreferredTeam={handleSelectPreferredTeam}
      onDismissPreferredTeamPrompt={dismissPrompt}
      preferredTeamBoard={preferredBoard.data}
      preferredTeamBoardLoading={activeTeamId != null && preferredBoard.loading}
      preferredTeamBoardError={activeTeamId != null ? preferredBoard.error : null}
      preferredTeamChanges={preferredChanges.data}
      preferredTeamChangesLoading={activeTeamId != null && preferredChanges.loading}
      preferredTeamChangesError={activeTeamId != null ? preferredChanges.error : null}
      onRetryPreferredTeamChanges={preferredChanges.refetch}
      loading={dash.loading}
      error={dash.error}
      staleWithError={dash.staleWithError}
      onRetry={dash.refetch}
    />
  )
}

export function HomeView({
  dashboard,
  teams = [],
  teamsLoading = false,
  teamsError = null,
  preferredTeam = null,
  viewTeam = preferredTeam,
  teamRelationship = relationshipFor({ viewTeam: preferredTeam, followedTeam: preferredTeam }),
  authenticated = false,
  authLoading = false,
  preferredTeamLoading = false,
  isDigestReturn = false,
  urlTeamPending = false,
  preferredTeamPromptDismissed = true,
  onSelectPreferredTeam = () => {},
  onDismissPreferredTeamPrompt = () => {},
  preferredTeamBoard = null,
  preferredTeamBoardLoading = false,
  preferredTeamBoardError = null,
  preferredTeamChanges = null,
  preferredTeamChangesLoading = false,
  preferredTeamChangesError = null,
  onRetryPreferredTeamChanges = null,
  loading = false,
  error = null,
  staleWithError = false,
  onRetry,
}) {
  const masthead = getMastheadView(dashboard)
  // The story surfaces read the canonical backend feed (dashboard.stories). The
  // canonical adapters return safe neutral reads for an empty, missing, or
  // malformed payload, so Home never blanks on a quiet morning.
  const hero = getCanonicalHeroStory(dashboard, { preferredTeam })
  const watchItems = getCanonicalHomeStories(dashboard)
  const leagueContext = getCanonicalLeagueContext(dashboard)
  const teamOptions = useMemo(() => buildWhatChangedTeamOptions(teams), [teams])
  const activeTeam = viewTeam || null
  const heroTeam = activeTeam || preferredTeam
  const teamHero = getCanonicalHeroStory(dashboard, { preferredTeam: heroTeam })
  const showFirstVisitPicker = !activeTeam && !urlTeamPending && !preferredTeamPromptDismissed
  const productLoaded = Boolean(dashboard) && !loading && !urlTeamPending && !authLoading && !preferredTeamLoading
  const productSource = isDigestReturn ? 'digest' : 'direct'
  const storySurface = isDigestReturn ? 'digest_web' : 'home'

  useTodayLoadedObservation({
    loaded: productLoaded,
    teamId: activeTeam?.team_id ?? activeTeam?.teamId ?? null,
    source: productSource,
  })
  const registerStoryImpression = useStoryImpressionObservations({
    enabled: productLoaded,
    surface: storySurface,
  })

  const handleSelectTeam = (team) => {
    if (team) onSelectPreferredTeam(team)
  }

  const teamBlock = urlTeamPending ? (
    <TeamReturnLoading />
  ) : activeTeam ? (
    <PreferredTeamHeader
      team={activeTeam}
      relationship={teamRelationship}
      authenticated={authenticated}
    />
  ) : showFirstVisitPicker ? (
    <FirstVisitTeamPicker
      teamOptions={teamOptions}
      teamsLoading={teamsLoading}
      teamsError={teamsError}
      onSelectTeam={handleSelectTeam}
      onDismiss={onDismissPreferredTeamPrompt}
    />
  ) : null

  const heroSection = (
    <section className="mb-8" aria-label="What BaseballOS sees today">
      <div className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">
        What BaseballOS Sees Today
      </div>
      <HeroStory
        hero={hero}
        impressionRef={registerStoryImpression(hero)}
        onTeamBoardOpen={() => observeStoryTeamBoardOpened({ story: hero, surface: storySurface, send: recordStoryTeamBoardOpened })}
        onShareClick={() => observeStoryShareClicked({ story: hero, surface: storySurface, send: recordStoryShareClicked })}
      />
    </section>
  )

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-7xl mx-auto">
      <Masthead masthead={masthead} />

      {loading && !dashboard ? (
        <LoadingPane message="Pulling together this morning's bullpen report..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice
              message="This briefing is from the last loaded dashboard snapshot because the latest refresh failed."
              onRetry={onRetry}
            />
          )}

          {isDigestReturn && activeTeam && (
            <DigestReturnNotice
              team={activeTeam}
              relationship={teamRelationship}
              onFollowTeam={handleSelectTeam}
            />
          )}

          {teamBlock}

          {!activeTeam && heroSection}

          {activeTeam && (
            <>
              <WhatChangedCard
                followedTeam={activeTeam}
                changes={preferredTeamChanges}
                loading={preferredTeamChangesLoading}
                error={preferredTeamChangesError}
                onRetry={onRetryPreferredTeamChanges}
              />
              <TonightsTeamBullpenPicture
                team={activeTeam}
                board={preferredTeamBoard}
                loading={preferredTeamBoardLoading}
                error={preferredTeamBoardError}
              />
              <section className="mb-8" aria-label="What BaseballOS sees today">
                <div className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">
                  What BaseballOS Sees Today
                </div>
                <HeroStory
                  hero={teamHero}
                  impressionRef={registerStoryImpression(teamHero)}
                  onTeamBoardOpen={() => observeStoryTeamBoardOpened({ story: teamHero, surface: storySurface, send: recordStoryTeamBoardOpened })}
                  onShareClick={() => observeStoryShareClicked({ story: teamHero, surface: storySurface, send: recordStoryShareClicked })}
                />
              </section>
            </>
          )}
          <BullpenStories
            stories={watchItems}
            showCta={false}
            registerImpressionRef={registerStoryImpression}
            onTeamBoardOpen={(story) => observeStoryTeamBoardOpened({ story, surface: storySurface, send: recordStoryTeamBoardOpened })}
          />
          <LeagueContext context={leagueContext} />
        </>
      )}

      <FeedbackCTA
        compact
        className="mb-2"
        eyebrow="User Validation"
        title="Help shape BaseballOS"
        body="Share what is useful, unclear, or missing while BaseballOS is being tested with real users."
      />
    </div>
  )
}

export function readWhatChangedTeamSelection(storage) {
  return preferredTeamSelectionValue(readPreferredTeamPreference(storage)) || null
}

export function saveWhatChangedTeamSelection(value, storage) {
  return savePreferredTeamSelectionValue(value, storage)
}

function cleanTeamText(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function teamIdValue(value) {
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isInteger(id) ? id : null
}

function teamOptionValue(team) {
  const teamId = teamIdValue(team.teamId ?? team.team_id)
  if (teamId != null) return `team:${teamId}`
  const abbr = cleanTeamText(team.teamAbbr ?? team.team_abbreviation)
  if (abbr) return `abbr:${abbr.toUpperCase()}`
  const name = cleanTeamText(team.teamName ?? team.team_name)
  return name ? `name:${name.toLowerCase()}` : null
}

function normalizeTeamOption(team) {
  if (!team || typeof team !== 'object') return null
  const teamId = teamIdValue(team.teamId ?? team.team_id)
  const teamName = cleanTeamText(team.teamName ?? team.team_name)
  const teamAbbr = cleanTeamText(team.teamAbbr ?? team.team_abbreviation)
  const value = teamOptionValue({ teamId, teamName, teamAbbr })
  if (!value || (!teamName && !teamAbbr)) return null

  return {
    value,
    teamId,
    teamName: teamName || teamAbbr,
    teamAbbr,
    href: buildWhatChangedTeamHref({ teamId, teamAbbr }),
  }
}

function buildWhatChangedTeamHref(team) {
  const teamParam = team?.teamAbbr || (
    team?.teamId != null ? String(team.teamId) : null
  )
  if (!teamParam) return '/bullpen?view=board'
  const query = new URLSearchParams({
    view: 'board',
    team: teamParam,
    source: 'home-what-changed',
  })
  return `/bullpen?${query.toString()}`
}

export function buildWhatChangedTeamOptions(teams = [], items = []) {
  const seen = new Set()
  const options = []
  const add = (raw) => {
    const option = normalizeTeamOption(raw)
    if (!option) return
    const keys = [
      option.value,
      option.teamAbbr ? `abbr:${option.teamAbbr.toLowerCase()}` : null,
      option.teamName ? `name:${option.teamName.toLowerCase()}` : null,
    ].filter(Boolean)
    if (keys.some(key => seen.has(key))) return
    keys.forEach(key => seen.add(key))
    options.push(option)
  }

  for (const team of (Array.isArray(teams) ? teams : [])) add(team)
  for (const item of (Array.isArray(items) ? items : [])) add({
    teamId: item.teamId,
    teamName: item.teamName,
    teamAbbr: item.teamAbbr,
  })

  return options.sort((left, right) => (
    left.teamName.localeCompare(right.teamName)
    || String(left.teamAbbr || '').localeCompare(String(right.teamAbbr || ''))
  ))
}

function selectedWhatChangedTeam(options, value) {
  return options.find(option => option.value === value) || null
}

function TeamReturnLoading() {
  return (
    <section className="mb-6" aria-label="Loading team update">
      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        <p className="font-mono text-xs text-chalk500">Loading team update...</p>
      </div>
    </section>
  )
}

function PreferredTeamHeader({
  team,
  relationship = {},
  authenticated = false,
}) {
  const teamLabel = preferredTeamLabel(team)
  const boardHref = buildPreferredTeamHref(team, 'home-my-team')
  const isFollowing = relationship.isFollowing === true
  const canManageFollowedTeam = (
    authenticated
    || isFollowing
    || relationship.kind === 'digest-switch'
    || relationship.kind === 'digest-followed'
  )
  const changeTeamHref = canManageFollowedTeam
    ? '/trust?focus=digest-preferences'
    : '/signin'
  const eyebrow = isFollowing
    ? 'My Team'
    : relationship.kind === 'digest-switch' || relationship.kind === 'digest-preview' || relationship.kind === 'digest-followed'
      ? 'Digest Update'
      : 'Team Preview'
  const subtitle = relationship.kind?.startsWith('digest')
    ? `Here's what changed for the ${teamLabel} since their last game.`
    : isFollowing
      ? 'Your bullpen. Tonight.'
      : `${teamLabel} bullpen preview.`

  return (
    <section className="mb-7" aria-label={isFollowing ? 'My team' : 'Team preview'}>
      <div className="relative min-h-[15rem] overflow-hidden border border-amber/25 bg-dugout bg-stadium-glow p-8 sm:p-10 lg:p-12">
        <div className="pointer-events-none absolute inset-0 bg-grid-lines opacity-45" />
        <div className="relative z-10 flex min-h-[12rem] flex-col justify-between gap-8 lg:min-h-[13rem]">
          <div className="flex min-w-0 flex-col gap-7 sm:flex-row sm:items-center sm:gap-10">
            <TeamMark
              team={team}
              className="h-36 w-36 border-amber/25 bg-white/[0.04] p-3 shadow-inner sm:h-40 sm:w-40 lg:h-48 lg:w-48"
              fallbackClassName="text-6xl"
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-mono text-[10px] uppercase tracking-widest text-amber">
                  {eyebrow}
                </span>
                {isFollowing && (
                  <span className="rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-emerald-300">
                    Following
                  </span>
                )}
              </div>
              <h2 className="mt-5 break-words font-display text-6xl leading-none tracking-wide text-chalk100 sm:text-7xl lg:text-8xl">
                {teamLabel}
              </h2>
              <p className="mt-4 text-xl leading-relaxed text-chalk300">
                {subtitle}
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-1.5 pt-2 opacity-50 transition-opacity hover:opacity-90 sm:flex-row sm:items-end lg:absolute lg:bottom-7 lg:right-7 lg:pt-0">
            <Link
              to={changeTeamHref}
              className="inline-flex min-h-7 items-center justify-center rounded border border-dirt/80 bg-transparent px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-chalk600 transition-colors hover:border-amber/40 hover:text-amber"
            >
              Change followed team
            </Link>
            <Link
              to={boardHref}
              className="inline-flex min-h-7 items-center justify-center rounded border border-dirt/80 bg-transparent px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-chalk600 transition-colors hover:border-amber/40 hover:text-amber"
            >
              Open Team Board -&gt;
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

function FirstVisitTeamPicker({
  teamOptions = [],
  teamsLoading = false,
  teamsError = null,
  onSelectTeam = () => {},
  onDismiss = () => {},
}) {
  const [draftValue, setDraftValue] = useState('')
  const selectedValue = teamOptions.some(option => option.value === draftValue)
    ? draftValue
    : teamOptions[0]?.value || ''
  const selectedTeam = selectedWhatChangedTeam(teamOptions, selectedValue)

  const handleConfirm = () => {
    if (selectedTeam) onSelectTeam(selectedTeam)
  }

  return (
    <section className="mb-6" aria-label="Pick your team">
      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
              Pick Your Team
            </div>
            <h2 className="mt-1 font-display text-2xl tracking-wide text-chalk100">
              Make Today open around your bullpen
            </h2>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-chalk400">
              Choose one club to make What Changed, the team board, and navigation start from that bullpen.
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex min-w-[14rem] flex-col gap-1 font-mono text-[11px] uppercase tracking-wider text-chalk500">
              Team
              <select
                value={selectedValue}
                onChange={(event) => setDraftValue(event.target.value)}
                disabled={teamOptions.length === 0}
                className="baseballos-select rounded border border-dirt px-3 py-2 text-xs normal-case tracking-normal outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Choose preferred team"
              >
                {teamOptions.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.teamName}{option.teamAbbr ? ` (${option.teamAbbr})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!selectedTeam}
              className="rounded border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded border border-dirt px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk400 transition-colors hover:border-chalk400 hover:text-chalk200"
            >
              Skip for now
            </button>
          </div>
        </div>

        <div className="mt-3 font-mono text-[11px] text-chalk500">
          {teamsLoading && teamOptions.length === 0
            ? 'Loading teams...'
            : teamsError
              ? 'Team list unavailable right now.'
              : `${teamOptions.length} teams available`}
        </div>
      </div>
    </section>
  )
}

function boardSnapshotCount(board, status) {
  const context = getBoardContextView(board)
  const row = context.snapshot.find(item => item.status === status)
  return Number(row?.count) || 0
}

function TonightsTeamBullpenPicture({
  team,
  board = null,
  loading = false,
  error = null,
}) {
  if (!team) return null

  const teamLabel = preferredTeamLabel(team)
  const boardHref = buildPreferredTeamHref(team, 'home-tonight-picture')
  const hasBoard = Boolean(board)
  const stress = getBullpenStressView(board?.stress)
  const available = hasBoard ? boardSnapshotCount(board, 'Available') : null
  const monitor = hasBoard ? boardSnapshotCount(board, 'Monitor') : null
  const limited = hasBoard ? boardSnapshotCount(board, 'Limited') : 0
  const avoid = hasBoard ? boardSnapshotCount(board, 'Avoid') : 0
  const unavailable = hasBoard ? boardSnapshotCount(board, 'Unavailable') : 0
  const needingRest = limited + avoid + unavailable

  return (
    <section className="mb-9" aria-label="Tonight's bullpen picture">
      <SectionHeading
        title="Tonight's Bullpen Picture"
        subtitle={`The quick read on ${teamLabel}'s usable depth tonight.`}
      />

      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        {loading ? (
          <p className="font-mono text-xs text-chalk500">Loading {teamLabel} bullpen picture...</p>
        ) : error ? (
          <p className="font-mono text-xs text-chalk500">Team bullpen picture is unavailable right now.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
            <div className="min-w-0 border border-dirt/70 bg-field/30 p-4">
              <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Supporting Signals
              </div>
              <div className="mt-4 grid grid-cols-1 gap-4 divide-dirt/60 sm:grid-cols-3 sm:divide-x">
                <TeamPictureMetric
                  label="Available Tonight"
                  value={available}
                  detail="relievers usable now"
                  tone="rest"
                  surface="bare"
                  valueClassName="text-4xl"
                />
                <TeamPictureMetric
                  label="On Watch"
                  value={monitor}
                  detail="relievers to monitor"
                  tone="watch"
                  surface="bare"
                  valueClassName="text-4xl"
                  className="sm:pl-4"
                />
                <TeamPictureMetric
                  label="Needing Rest"
                  value={needingRest}
                  detail="limited, avoid, or unavailable"
                  tone="stress"
                  surface="bare"
                  valueClassName="text-4xl"
                  className="sm:pl-4"
                />
              </div>
            </div>

            <TeamPictureSlot label="Bullpen Health" tone={stress.state === 'constrained' || stress.state === 'elevated' ? 'stress' : 'rest'} surface="highlight">
              <p className="font-display text-5xl leading-none tracking-wide text-chalk100">
                {stress.label || 'No Read'}
              </p>
              <p className="mt-3 text-base leading-relaxed text-chalk200">
                {stress.summary || 'No current bullpen health read is available.'}
              </p>
              <p className="mt-5 border-t border-dirt/60 pt-3 font-mono text-[11px] uppercase tracking-wider text-chalk500">
                {getHomeRosterStatusLine(board)}
              </p>
            </TeamPictureSlot>
          </div>
        )}

        <div className="mt-3 border-t border-dirt/70 pt-3">
          <Link
            to={boardHref}
            className="inline-flex rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
          >
            See full bullpen depth, roles, and usage -&gt;
          </Link>
        </div>
      </div>
    </section>
  )
}

function TeamPictureSlot({ label, tone = 'rest', className = '', surface = 'card', children }) {
  const toneClass = tone === 'stress'
    ? 'text-red-300'
    : tone === 'watch'
      ? 'text-yellow-300'
      : 'text-emerald-300'
  const surfaceClass = surface === 'bare'
    ? 'min-w-0'
    : surface === 'highlight'
      ? 'min-w-0 border border-amber/30 bg-amber/10 p-5 sm:p-6'
      : 'min-w-0 border border-dirt/80 bg-field/50 p-4'
  return (
    <div className={`${surfaceClass} ${className}`}>
      <div className={`font-mono text-[10px] uppercase tracking-widest ${toneClass}`}>
        {label}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  )
}

function TeamPictureMetric({ label, value, detail, tone, className = '', surface = 'card', valueClassName = 'text-5xl' }) {
  return (
    <TeamPictureSlot label={label} tone={tone} className={className} surface={surface}>
      <p className={`font-display ${valueClassName} leading-none tracking-wide text-chalk100`}>
        {Number.isFinite(value) ? value : '-'}
      </p>
      <p className="mt-1 text-sm leading-relaxed text-chalk300">{detail}</p>
    </TeamPictureSlot>
  )
}

function restedCountDelta(item) {
  const today = item?.todayRestedCount
  const yesterday = item?.yesterdayRestedCount
  if (!Number.isFinite(today) || !Number.isFinite(yesterday)) return null
  return today - yesterday
}

function Masthead({ masthead }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3 border-b border-dirt pb-4 animate-fade-up opacity-0" style={{ animationFillMode: 'forwards' }}>
      <div>
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
          The Morning Bullpen Report
        </div>
        <h1 className="mt-1 font-display text-4xl tracking-wider text-chalk100 leading-none">
          BASEBALL<span className="text-gradient-amber">OS</span> TODAY
        </h1>
      </div>
      <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-chalk400">
        <span>{masthead.editionDate}</span>
        <span className="text-chalk600" aria-hidden="true">·</span>
        <span className="rounded border border-dirt bg-dugout px-2 py-1 text-chalk400">
          {masthead.dataLine}
        </span>
        <Link
          to="/dashboard"
          className="rounded border border-dirt bg-dugout px-2 py-1 text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
        >
          League dashboard →
        </Link>
      </div>
    </header>
  )
}

// The flagship observation, told the way a baseball writer would lead a
// column. Stories deliberately explores the observations behind and beyond it.
function HeroStory({ hero, impressionRef, onTeamBoardOpen, onShareClick }) {
  const tone = homeTone(hero.tone)

  return (
    <div ref={impressionRef} className="relative overflow-hidden rounded-xl border border-dirt bg-dugout bg-stadium-glow p-5 sm:p-7">
      <div className="absolute inset-0 bg-grid-lines opacity-100 pointer-events-none" />
      <div className="relative z-10">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
            style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
            {hero.kicker}
          </span>
          {hero.read && (
            <span
              className="inline-flex items-center gap-1.5 rounded border border-dirt bg-field/60 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-chalk200"
              title={`${hero.read.display}: ${hero.read.detail}`}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: homeTone(hero.read.tone).dot }} aria-hidden="true" />
              {hero.read.display}
            </span>
          )}
        </div>

        <h2 className="mt-3 max-w-full break-words font-display text-4xl leading-none tracking-wide text-chalk100 sm:max-w-4xl sm:text-5xl">
          {hero.headline}
        </h2>

        <FlagshipStoryStatus status={hero.storyStatus} />

        <StoryPresentation
          story={hero}
          observation={hero.observation}
          className="mt-4 max-w-3xl"
          observationBodyClassName="text-chalk200 sm:text-base"
          forceContext
        />

        <div className="mt-4 max-w-3xl rounded border-l-4 border-amber/70 bg-field/60 p-3 sm:p-4">
          <p className="text-sm leading-relaxed text-chalk200">{hero.whyItMatters}</p>
        </div>

        <FlagshipEvidence facts={hero.whatBaseballOSSaw} />

        {hero.chips.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {hero.chips.map(chip => (
              <span
                key={chip.key}
                className="inline-flex items-center gap-2 rounded border border-dirt bg-field/60 px-2.5 py-1 font-mono text-[11px] text-chalk400"
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: homeTone(chip.tone).dot }} aria-hidden="true" />
                {chip.label}
                <span className="text-sm text-chalk100">{chip.value}</span>
              </span>
            ))}
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3">
          {hero.team?.href && (
            <Link
              to={hero.team.href}
              onClick={onTeamBoardOpen}
              className="rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
            >
              Step inside the {hero.team.abbr || hero.team.teamName} pen →
            </Link>
          )}
          {hero.team && <TeamShareButton team={hero.team} onShareClick={onShareClick} />}
          <Link
            to="/bullpen"
            className="rounded border border-dirt bg-field/60 px-4 py-2 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
          >
            Browse every bullpen →
          </Link>
        </div>
      </div>
    </div>
  )
}

function FlagshipStoryStatus({ status }) {
  if (!status) return null
  const tone = homeTone(status.tone)

  return (
    <div
      className="mt-3 inline-flex max-w-3xl flex-wrap items-center gap-x-2 gap-y-1 rounded border px-2.5 py-1.5 text-xs leading-relaxed"
      style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor }}
      aria-label="Story Status"
    >
      <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        Story Status
      </span>
      <span className="font-semibold text-chalk100">{status.label}</span>
      <span className="text-chalk400">{status.description}</span>
    </div>
  )
}

function FlagshipEvidence({ facts = [] }) {
  if (!Array.isArray(facts) || facts.length < 1) return null

  return (
    <div className="mt-3 max-w-3xl border-t border-dirt/70 pt-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">What BaseballOS Saw</div>
      <ul className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {facts.map(fact => (
          <li key={fact.key} className="flex min-w-0 items-start gap-2 border border-dirt/70 bg-field/40 px-2.5 py-2">
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber/70" aria-hidden="true" />
            <span className="min-w-0">
              <span className="block font-mono text-[10px] uppercase tracking-widest text-chalk500">{fact.label}</span>
              <span className="mt-0.5 block text-sm leading-tight text-chalk100">{fact.value}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function leagueContextDeltaLines(changes = {}) {
  const items = Array.isArray(changes?.items) ? changes.items : []
  const restedDeltas = items.map(restedCountDelta).filter(Number.isFinite)
  const hasItems = items.length > 0
  const netRested = restedDeltas.reduce((sum, value) => sum + value, 0)
  const changedBoards = restedDeltas.filter(value => value !== 0).length
  const workloadAdded = items.reduce((sum, item) => {
    const workload = Array.isArray(item?.workloadAdded) ? item.workloadAdded.length : 0
    return sum + workload
  }, 0)
  const restedTone = netRested < 0
    ? 'text-red-300'
    : netRested > 0
      ? 'text-emerald-300'
      : 'text-chalk300'

  return {
    pressure: {
      value: hasItems ? signedCount(netRested) : '-',
      label: netRested === 0
        ? 'net rested change on changed boards'
        : `${netRested < 0 ? 'fewer' : 'more'} rested relievers on changed boards`,
      toneClass: restedTone,
    },
    concentration: {
      value: hasItems ? String(workloadAdded) : '-',
      label: 'pitchers added workload yesterday',
      toneClass: workloadAdded > 0 ? 'text-yellow-300' : 'text-chalk300',
    },
    clean: {
      value: hasItems ? String(changedBoards) : '-',
      label: 'teams with rested-option movement',
      toneClass: changedBoards > 0 ? 'text-amber' : 'text-chalk300',
    },
  }
}

function signedCount(value) {
  if (!Number.isFinite(value)) return '-'
  if (value > 0) return `+${value}`
  if (value < 0) return `-${Math.abs(value)}`
  return '0'
}

function LeagueContext({ context, changes }) {
  const deltaLines = leagueContextDeltaLines(changes)
  return (
    <section className="mb-8" aria-label="League context">
      <SectionHeading
        title="League Context"
        subtitle="The short read behind the morning briefing."
      />

      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        <p className="max-w-3xl text-sm leading-relaxed text-chalk300">
          {context.summary}
        </p>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {context.facts.map(fact => {
            const tone = homeTone(fact.tone)
            const delta = deltaLines[fact.key] || {
              value: '-',
              label: 'day-over-day change unavailable',
              toneClass: 'text-chalk300',
            }
            return (
              <div key={fact.key} className="border border-dirt bg-field/50 p-3">
                <div
                  className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
                  style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
                >
                  <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
                  {fact.label}
                </div>
                <div className={`mt-3 font-display text-3xl leading-none tracking-wide ${delta.toneClass}`}>
                  {delta.value}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-chalk300">{delta.label}</p>
                <div className="mt-3 border-t border-dirt/60 pt-3">
                  <div className="font-display text-xl leading-none tracking-wide text-chalk100">
                    {fact.value}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-chalk500">{fact.detail}</p>
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-4 text-right">
          <Link
            to={context.href}
            className="inline-flex items-center rounded border border-amber/40 bg-amber/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-amber transition-colors hover:bg-amber/20"
          >
            {context.cta} →
          </Link>
        </div>
      </div>
    </section>
  )
}
