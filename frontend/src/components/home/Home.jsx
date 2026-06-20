import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { usePreferredTeamPreference } from '../../hooks/usePreferredTeamPreference'
import { getBullpenDashboard, getTeamBullpenBoard, getTeams } from '../../utils/api'
import {
  buildPreferredTeamHref,
  preferredTeamLabel,
  preferredTeamSelectionValue,
  readPreferredTeamPreference,
  savePreferredTeamSelectionValue,
} from '../../utils/preferredTeam'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import TeamShareButton from '../share/TeamShareButton'
import TeamMark from '../team/TeamMark'
import {
  getBoardContextView,
  getBullpenStressView,
} from '../bullpen/board/tonightsBullpenBoardView'
import BullpenStories, { SectionHeading, StoryPresentation } from './BullpenStories'
import {
  getHeroStory,
  getLeagueContext,
  getMastheadView,
  getTodayWatchItems,
  getWhatChangedSinceYesterday,
  homeTone,
} from './homeIntelligenceView'

// The Morning Bullpen Report — BaseballOS's story-led front page. Curated,
// not exhaustive: one flagship observation, three things to watch, short
// league context, and a handoff to Stories. The Stories page carries the
// browseable feed and the Bullpen page remains the team directory.
export default function Home() {
  const dash = useFetch(getBullpenDashboard)
  const teams = useFetch(getTeams)
  const teamList = teams.data || []
  const {
    preferredTeam,
    promptDismissed,
    setPreferredTeam,
    dismissPrompt,
  } = usePreferredTeamPreference(teamList)
  const preferredTeamId = preferredTeam?.team_id ?? null
  const preferredBoard = useFetch(
    () => (
      preferredTeamId == null
        ? Promise.resolve(null)
        : getTeamBullpenBoard(preferredTeamId)
    ),
    [preferredTeamId],
  )

  return (
    <HomeView
      dashboard={dash.data}
      teams={teamList}
      teamsLoading={teams.loading}
      teamsError={teams.error}
      preferredTeam={preferredTeam}
      preferredTeamPromptDismissed={promptDismissed}
      onSelectPreferredTeam={setPreferredTeam}
      onDismissPreferredTeamPrompt={dismissPrompt}
      preferredTeamBoard={preferredBoard.data}
      preferredTeamBoardLoading={preferredTeamId != null && preferredBoard.loading}
      preferredTeamBoardError={preferredTeamId != null ? preferredBoard.error : null}
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
  preferredTeamPromptDismissed = true,
  onSelectPreferredTeam = () => {},
  onDismissPreferredTeamPrompt = () => {},
  preferredTeamBoard = null,
  preferredTeamBoardLoading = false,
  preferredTeamBoardError = null,
  loading = false,
  error = null,
  staleWithError = false,
  onRetry,
}) {
  const masthead = getMastheadView(dashboard)
  const hero = getHeroStory(dashboard)
  const whatChanged = getWhatChangedSinceYesterday(dashboard)
  const watchItems = getTodayWatchItems(dashboard)
  const leagueContext = getLeagueContext(dashboard)
  const changeItems = Array.isArray(whatChanged?.items) ? whatChanged.items : []
  const teamOptions = useMemo(
    () => buildWhatChangedTeamOptions(teams, changeItems),
    [teams, changeItems],
  )
  const selectedValue = selectedWhatChangedTeamValue(teamOptions, changeItems, preferredTeam)
  const selectedTeam = selectedWhatChangedTeam(teamOptions, selectedValue)
  const selectedItem = selectedWhatChangedItem(changeItems, selectedTeam)
  const showFirstVisitPicker = !preferredTeam && !preferredTeamPromptDismissed

  const handleSelectTeam = (team) => {
    if (team) onSelectPreferredTeam(team)
  }

  const teamBlock = preferredTeam ? (
    <PreferredTeamHeader
      team={preferredTeam}
      teamOptions={teamOptions}
      selectedValue={selectedValue}
      onSelectTeam={handleSelectTeam}
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
      <HeroStory hero={hero} />
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

          {teamBlock}

          {!preferredTeam && heroSection}

          <WhatChangedSinceYesterday
            changes={whatChanged}
            teamOptions={teamOptions}
            selectedValue={selectedValue}
            selectedTeam={selectedTeam}
            selectedItem={selectedItem}
            teamsLoading={teamsLoading}
            teamsError={teamsError}
            onSelectTeam={handleSelectTeam}
          />
          {preferredTeam && (
            <>
              <TonightsTeamBullpenPicture
                team={preferredTeam}
                board={preferredTeamBoard}
                loading={preferredTeamBoardLoading}
                error={preferredTeamBoardError}
                selectedChange={selectedItem}
              />
              {heroSection}
            </>
          )}
          <BullpenStories stories={watchItems} showCta={false} />
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

function changeMatchesTeam(change, option) {
  if (!change || !option) return false
  if (option.teamId != null && change.teamId != null) {
    if (Number(option.teamId) === Number(change.teamId)) return true
  }
  if (option.teamAbbr && change.teamAbbr) {
    return option.teamAbbr.toLowerCase() === change.teamAbbr.toLowerCase()
  }
  return option.teamName?.toLowerCase() === change.teamName?.toLowerCase()
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

function defaultWhatChangedTeamValue(options, items) {
  const firstChangedItem = items.find(item => options.some(option => changeMatchesTeam(item, option)))
  const withChange = options.find(option => changeMatchesTeam(firstChangedItem, option))
  return withChange?.value || options[0]?.value || ''
}

function selectedWhatChangedTeamValue(options, items, preferredTeam) {
  const preferredValue = preferredTeamSelectionValue(preferredTeam)
  if (preferredValue && options.some(option => option.value === preferredValue)) {
    return preferredValue
  }
  const preferredOption = options.find(option => changeMatchesTeam(preferredTeam, option))
  if (preferredOption) return preferredOption.value
  return defaultWhatChangedTeamValue(options, items)
}

function selectedWhatChangedTeam(options, value) {
  return options.find(option => option.value === value) || null
}

function selectedWhatChangedItem(items, option) {
  return items.find(item => changeMatchesTeam(item, option)) || null
}

function WhatChangedSinceYesterday({
  changes,
  teamOptions = [],
  selectedValue = '',
  selectedTeam = null,
  selectedItem = null,
  teamsLoading = false,
  teamsError = null,
  onSelectTeam = () => {},
}) {
  const items = Array.isArray(changes?.items) ? changes.items : []

  if (!changes?.hasChanges || items.length < 1) return null

  const handleTeamChange = (event) => {
    const nextValue = event.target.value
    const nextTeam = selectedWhatChangedTeam(teamOptions, nextValue)
    if (nextTeam) onSelectTeam(nextTeam)
  }

  return (
    <section className="mb-10" aria-label="What Changed Since Yesterday">
      <div className="overflow-hidden border border-dirt bg-dugout">
        <div className="flex flex-col gap-4 border-b border-dirt/80 p-4 sm:p-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            {selectedTeam && (
              <TeamMark
                team={selectedTeam}
                className="h-12 w-12 border-amber/15 bg-white/[0.035] p-1.5"
                fallbackClassName="text-sm"
              />
            )}
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
                What Changed Since Yesterday
              </div>
              <h2 className="mt-1 font-display text-2xl leading-none tracking-wide text-chalk100 sm:text-3xl">
                {selectedTeam?.teamName || 'Selected bullpen'}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-chalk400">
                Yesterday, today, who worked, and what it changes for tonight.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex w-full min-w-[14rem] flex-col gap-1 font-mono text-[10px] uppercase tracking-widest text-chalk500 sm:w-auto">
              Change Team
              <select
                value={selectedValue}
                onChange={handleTeamChange}
                disabled={teamOptions.length === 0}
                className="min-h-10 rounded border border-dirt bg-field px-3 py-2 text-sm normal-case tracking-normal text-chalk100 outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Choose team for What Changed Since Yesterday"
              >
                {teamOptions.map(team => (
                  <option key={team.value} value={team.value}>
                    {team.teamName}{team.teamAbbr ? ` (${team.teamAbbr})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <div className="pb-0.5 font-mono text-[11px] text-chalk500 sm:text-right">
              {teamsLoading && teamOptions.length <= items.length
                ? 'Loading full team list...'
                : teamsError
                  ? 'Team list unavailable; showing changed teams.'
                  : `${teamOptions.length} teams available`}
            </div>
          </div>
        </div>

        <div className="p-4 sm:p-5">
          {selectedItem ? (
            <SelectedChangePanel item={selectedItem} team={selectedTeam} comparison={changes.comparison} />
          ) : (
            <NoSelectedChange team={selectedTeam} comparison={changes.comparison} />
          )}

          {items.length > 1 && (
            <details className="mt-3">
              <summary className="cursor-pointer list-none font-mono text-[11px] uppercase tracking-widest text-chalk400 transition-colors hover:text-amber">
                View League-Wide Changes ({items.length})
              </summary>
              <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {items.map(item => (
                  <li key={item.key} className="border border-dirt/80 bg-field/50 p-3">
                    <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                      {item.teamAbbr || item.teamName}
                    </div>
                    <p className="mt-1 text-sm leading-snug text-chalk200">
                      {restedCountLine(item)}
                    </p>
                    <p className="mt-1 text-xs leading-snug text-chalk500">
                      {workloadAddedLine(item)}
                    </p>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </section>
  )
}

function PreferredTeamHeader({ team, teamOptions = [], selectedValue = '', onSelectTeam = () => {} }) {
  const teamLabel = preferredTeamLabel(team)
  const boardHref = buildPreferredTeamHref(team, 'home-my-team')
  const canSwitch = teamOptions.length > 0
  const selectValue = teamOptions.some(option => option.value === selectedValue)
    ? selectedValue
    : ''

  const handleChange = (event) => {
    const option = selectedWhatChangedTeam(teamOptions, event.target.value)
    if (option) onSelectTeam(option)
  }

  return (
    <section className="mb-10" aria-label="My team">
      <div className="relative overflow-hidden border border-amber/25 bg-dugout bg-stadium-glow p-5 sm:p-6">
        <div className="pointer-events-none absolute inset-0 bg-grid-lines opacity-60" />
        <div className="relative z-10 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4 sm:gap-5">
            <TeamMark
              team={team}
              className="h-20 w-20 border-amber/25 bg-white/[0.04] p-2 shadow-inner sm:h-24 sm:w-24"
              fallbackClassName="text-3xl sm:text-4xl"
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] uppercase tracking-widest text-amber">
                  My Team
                </span>
                <span className="rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-emerald-300">
                  Following
                </span>
              </div>
              <h2 className="mt-2 break-words font-display text-4xl leading-none tracking-wide text-chalk100 sm:text-5xl">
                {teamLabel}
              </h2>
              <p className="mt-2 text-base leading-relaxed text-chalk300">
                Your bullpen. Tonight.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-end lg:flex-col lg:items-end">
            <label className="flex w-full min-w-[14rem] flex-col gap-1 font-mono text-[10px] uppercase tracking-widest text-chalk500 sm:w-auto">
              Change team
              <select
                value={selectValue}
                onChange={handleChange}
                disabled={!canSwitch}
                className="min-h-10 rounded border border-dirt bg-field px-3 py-2 text-sm normal-case tracking-normal text-chalk100 outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Change preferred team"
              >
                {!selectValue && <option value="">Choose team</option>}
                {teamOptions.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.teamName}{option.teamAbbr ? ` (${option.teamAbbr})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <Link
              to={boardHref}
              className="inline-flex min-h-10 items-center justify-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
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
                className="rounded border border-dirt bg-field px-3 py-2 text-xs normal-case tracking-normal text-chalk200 outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
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
  selectedChange = null,
}) {
  if (!team) return null

  const teamLabel = preferredTeamLabel(team)
  const workload = Array.isArray(selectedChange?.workloadAdded) ? selectedChange.workloadAdded : []
  const boardHref = buildPreferredTeamHref(team, 'home-tonight-picture')
  const hasBoard = Boolean(board)
  const stress = getBullpenStressView(board?.stress)
  const available = hasBoard ? boardSnapshotCount(board, 'Available') : null
  const monitor = hasBoard ? boardSnapshotCount(board, 'Monitor') : null
  const limited = hasBoard ? boardSnapshotCount(board, 'Limited') : 0
  const avoid = hasBoard ? boardSnapshotCount(board, 'Avoid') : 0
  const unavailable = hasBoard ? boardSnapshotCount(board, 'Unavailable') : 0
  const needingRest = limited + avoid + unavailable
  const inactiveCount = Number(board?.roster_status?.inactive_context_count || 0)

  return (
    <section className="mb-10" aria-label="Tonight's bullpen picture">
      <SectionHeading
        title="Tonight's Bullpen Picture"
        subtitle={`What ${teamLabel} changed, who worked, and how much room the bullpen has tonight.`}
      />

      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        {loading ? (
          <p className="font-mono text-xs text-chalk500">Loading {teamLabel} bullpen picture...</p>
        ) : error ? (
          <p className="font-mono text-xs text-chalk500">Team bullpen picture is unavailable right now.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-12">
            <TeamPictureSlot label="Worked Yesterday" tone="rest" className="xl:col-span-3">
              {workload.length > 0 ? (
                <ul className="space-y-2">
                  {workload.map(row => (
                    <li key={`${row.pitcherId || row.name}-${row.pitches}`} className="flex min-w-0 items-baseline justify-between gap-3">
                      <span className="min-w-0 break-words text-sm text-chalk100">{row.name}</span>
                      <span className="shrink-0 font-mono text-xs text-chalk300">
                        {row.pitches} {row.pitches === 1 ? 'pitch' : 'pitches'}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm leading-relaxed text-chalk300">
                  No meaningful bullpen workload stands out from yesterday.
                </p>
              )}
            </TeamPictureSlot>

            <TeamPictureMetric
              label="Available Tonight"
              value={available}
              detail="relievers usable now"
              tone="rest"
              className="xl:col-span-3"
            />
            <TeamPictureMetric
              label="On Watch"
              value={monitor}
              detail="relievers to monitor"
              tone="watch"
              className="xl:col-span-3"
            />
            <TeamPictureMetric
              label="Needing Rest"
              value={needingRest}
              detail="limited, avoid, or unavailable"
              tone="stress"
              className="xl:col-span-3"
            />

            <TeamPictureSlot label="Bullpen Health" tone={stress.state === 'constrained' || stress.state === 'elevated' ? 'stress' : 'rest'} className="xl:col-span-4">
              <p className="font-display text-2xl leading-none tracking-wide text-chalk100">
                {stress.label || 'No Read'}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-chalk300">
                {stress.summary || 'No current bullpen health read is available.'}
              </p>
              <p className="mt-2 font-mono text-[11px] uppercase tracking-wider text-chalk500">
                {inactiveCount} roster-status context {inactiveCount === 1 ? 'arm' : 'arms'}
              </p>
            </TeamPictureSlot>

            <TeamPictureSlot label="Why It Matters" tone="rest" className="xl:col-span-8">
              <p className="text-sm leading-relaxed text-chalk100">
                {selectedChange?.context || selectedChange?.summary || stress.summary || `${teamLabel} has a team bullpen board ready for tonight.`}
              </p>
            </TeamPictureSlot>
          </div>
        )}

        <div className="mt-4 border-t border-dirt/70 pt-4">
          <Link
            to={boardHref}
            className="inline-flex rounded border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
          >
            See full bullpen depth, roles, and usage -&gt;
          </Link>
        </div>
      </div>
    </section>
  )
}

function TeamPictureSlot({ label, tone = 'rest', className = '', children }) {
  const toneClass = tone === 'stress'
    ? 'text-red-300'
    : tone === 'watch'
      ? 'text-yellow-300'
      : 'text-emerald-300'
  const spanClass = className.includes('xl:col-span-') ? '' : 'xl:col-span-3'
  return (
    <div className={`min-w-0 border border-dirt/80 bg-field/50 p-4 ${spanClass} ${className}`}>
      <div className={`font-mono text-[10px] uppercase tracking-widest ${toneClass}`}>
        {label}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  )
}

function TeamPictureMetric({ label, value, detail, tone, className = '' }) {
  return (
    <TeamPictureSlot label={label} tone={tone} className={className}>
      <p className="font-display text-4xl leading-none tracking-wide text-chalk100">
        {Number.isFinite(value) ? value : '-'}
      </p>
      <p className="mt-1 text-sm leading-relaxed text-chalk300">{detail}</p>
    </TeamPictureSlot>
  )
}

function ComparisonWindow({ comparison }) {
  const previous = comparison?.previous_data_through
  const current = comparison?.current_data_through
  if (!previous || !current) return null
  return (
    <span className="rounded border border-dirt bg-field/60 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
      {previous} -&gt; {current}
    </span>
  )
}

function SelectedChangePanel({ item, team, comparison }) {
  const delta = restedCountDelta(item)
  const changeTone = delta < 0 ? 'text-red-300' : delta > 0 ? 'text-emerald-300' : 'text-chalk300'
  const changeWord = delta < 0 ? 'fewer' : delta > 0 ? 'more' : 'changed'
  const teamIdentity = team || item

  return (
    <div>
      <div className="mb-4 flex min-w-0 flex-wrap items-center gap-2">
        <TeamMark
          team={teamIdentity}
          className="h-8 w-8 border-amber/15 bg-white/[0.035] p-1"
          fallbackClassName="text-[10px]"
        />
        {item.teamAbbr && (
          <span className="shrink-0 rounded border border-amber/30 bg-amber/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-amber">
            {item.teamAbbr}
          </span>
        )}
        <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Showing
        </span>
        <h3 className="min-w-0 font-display text-2xl leading-none tracking-wide text-chalk100">
          {item.teamName}
        </h3>
        <ComparisonWindow comparison={comparison} />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.1fr_1.15fr_1.25fr]">
        <div className="min-w-0 border border-dirt/80 bg-field/60 p-3 sm:p-4">
          <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-3">
            <RestedCountInline label="Yesterday" count={item.yesterdayRestedCount} tone="rest" />
            <div className="h-full border-l border-dirt/80" aria-hidden="true" />
            <RestedCountInline label="Today" count={item.todayRestedCount} tone="watch" />
          </div>
          <div className="mt-4 border-t border-dirt/70 pt-4">
            <div className="flex items-baseline gap-2">
              <span className={`font-display text-4xl leading-none tracking-wide ${changeTone}`}>
                {Number.isFinite(delta) ? Math.abs(delta) : '-'}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                {Number.isFinite(delta) ? `${changeWord} rested relievers` : 'rested reliever change'}
              </span>
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-chalk300">
              {item.summary || restedCountLine(item)}
            </p>
          </div>
        </div>

        <WorkloadAddedSlot workload={item.workloadAdded} />
        <WhyItMattersSlot value={item.context || item.summary || item.headline} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-dirt/70 pt-3">
        <Link
          to={item.href || team?.href || '/bullpen?view=board'}
          className="inline-flex min-h-10 items-center rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
        >
          Open Team Board -&gt;
        </Link>
      </div>
    </div>
  )
}

function restedCountDelta(item) {
  const today = item?.todayRestedCount
  const yesterday = item?.yesterdayRestedCount
  if (!Number.isFinite(today) || !Number.isFinite(yesterday)) return null
  return today - yesterday
}

function restedRelieverLabel(count) {
  if (!Number.isFinite(count)) return 'rested relievers'
  return `rested ${count === 1 ? 'reliever' : 'relievers'}`
}

function restedCountLine(item) {
  const today = item?.todayRestedCount
  const yesterday = item?.yesterdayRestedCount
  if (Number.isFinite(today) && Number.isFinite(yesterday)) {
    return `${today} rested today, ${yesterday} yesterday`
  }
  if (Number.isFinite(today)) return `${today} rested today`
  return item?.teamName ? `${item.teamName} bullpen moved from yesterday.` : 'Bullpen moved from yesterday.'
}

function workloadAddedLine(item) {
  const count = Array.isArray(item?.workloadAdded) ? item.workloadAdded.length : 0
  if (count < 1) return 'No meaningful workload added yesterday'
  return `${count} ${count === 1 ? 'pitcher' : 'pitchers'} added meaningful workload yesterday`
}

function RestedCountInline({ label, count, tone = 'rest' }) {
  const toneClass = tone === 'watch' ? 'text-violet-300' : 'text-emerald-300'
  return (
    <div className="min-w-0">
      <div className={`font-mono text-[10px] uppercase tracking-widest ${toneClass}`}>
        {label}
      </div>
      <p className="mt-2 font-display text-4xl leading-none tracking-wide text-chalk100">
        {Number.isFinite(count) ? count : '-'}
      </p>
      <p className="mt-1 text-sm leading-relaxed text-chalk200">{restedRelieverLabel(count)}</p>
    </div>
  )
}

function WorkloadAddedSlot({ workload = [] }) {
  const rows = Array.isArray(workload) ? workload : []
  return (
    <div className="min-w-0 border border-dirt/80 bg-field/50 p-3 sm:p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-emerald-300">
        Workload Added Yesterday
      </div>
      {rows.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {rows.map(row => (
            <li key={`${row.pitcherId || row.name}-${row.pitches}`} className="flex min-w-0 items-baseline justify-between gap-3 text-sm leading-snug">
              <span className="min-w-0 break-words text-chalk100">{row.name}</span>
              <span className="shrink-0 font-mono text-xs text-chalk300">
                {row.pitches} {row.pitches === 1 ? 'pitch' : 'pitches'}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 break-words text-sm leading-relaxed text-chalk300">
          No meaningful bullpen movement stands out for this club in the current comparison.
        </p>
      )}
    </div>
  )
}

function WhyItMattersSlot({ value }) {
  return (
    <div className="min-w-0 border border-dirt/80 bg-field/50 p-3 sm:p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-emerald-300">
        Why It Matters
      </div>
      <p className="mt-3 break-words text-base leading-relaxed text-chalk100">
        {value}
      </p>
    </div>
  )
}

function NoSelectedChange({ team, comparison }) {
  return (
    <div className="mt-4 border border-dirt/80 bg-field/50 p-4" role="status" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Showing
        </span>
        <h3 className="font-display text-2xl leading-none tracking-wide text-chalk100">
          {team?.teamName || 'Selected team'}
        </h3>
        <ComparisonWindow comparison={comparison} />
      </div>
      <p className="mt-3 text-sm leading-relaxed text-chalk300">
        No meaningful bullpen movement stands out for this club in the current comparison.
      </p>
      {team?.href && (
        <Link
          to={team.href}
          className="mt-4 inline-flex rounded border border-dirt bg-dugout px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
        >
          Open Team Board -&gt;
        </Link>
      )}
    </div>
  )
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
function HeroStory({ hero }) {
  const tone = homeTone(hero.tone)

  return (
    <div className="relative overflow-hidden rounded-xl border border-dirt bg-dugout bg-stadium-glow p-5 sm:p-7">
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
              className="rounded border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
            >
              Step inside the {hero.team.abbr || hero.team.teamName} pen →
            </Link>
          )}
          {hero.team && <TeamShareButton team={hero.team} />}
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

function LeagueContext({ context }) {
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
            return (
              <div key={fact.key} className="border border-dirt bg-field/50 p-3">
                <div
                  className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
                  style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
                >
                  <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
                  {fact.label}
                </div>
                <div className="mt-2 font-display text-2xl leading-none tracking-wide text-chalk100">
                  {fact.value}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-chalk500">{fact.detail}</p>
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
