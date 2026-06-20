import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard, getTeams } from '../../utils/api'
import { LoadingPane, ErrorState, StaleDataNotice } from '../UI'
import { FeedbackCTA } from '../feedback/FeedbackLink'
import TeamShareButton from '../share/TeamShareButton'
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

  return (
    <HomeView
      dashboard={dash.data}
      teams={teams.data || []}
      teamsLoading={teams.loading}
      teamsError={teams.error}
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

          <section className="mb-8" aria-label="What BaseballOS sees today">
            <div className="mb-3 font-mono text-xs uppercase tracking-widest text-chalk400">
              What BaseballOS Sees Today
            </div>
            <HeroStory hero={hero} />
          </section>
          <WhatChangedSinceYesterday
            changes={whatChanged}
            teams={teams}
            teamsLoading={teamsLoading}
            teamsError={teamsError}
          />
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

const WHAT_CHANGED_TEAM_STORAGE_KEY = 'baseballos.whatChangedTeam'

function getBrowserStorage() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage || null
  } catch {
    return null
  }
}

export function readWhatChangedTeamSelection(storage = getBrowserStorage()) {
  if (!storage) return null
  try {
    const value = storage.getItem(WHAT_CHANGED_TEAM_STORAGE_KEY)
    return value && typeof value === 'string' ? value : null
  } catch {
    return null
  }
}

export function saveWhatChangedTeamSelection(value, storage = getBrowserStorage()) {
  const clean = typeof value === 'string' ? value.trim() : ''
  if (!clean || !storage) return false
  try {
    storage.setItem(WHAT_CHANGED_TEAM_STORAGE_KEY, clean)
    return true
  } catch {
    return false
  }
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

function selectedWhatChangedTeam(options, value) {
  return options.find(option => option.value === value) || null
}

function selectedWhatChangedItem(items, option) {
  return items.find(item => changeMatchesTeam(item, option)) || null
}

function WhatChangedSinceYesterday({ changes, teams = [], teamsLoading = false, teamsError = null }) {
  const items = Array.isArray(changes?.items) ? changes.items : []
  const teamOptions = useMemo(
    () => buildWhatChangedTeamOptions(teams, items),
    [teams, items],
  )
  const [storedTeamValue, setStoredTeamValue] = useState(() => readWhatChangedTeamSelection())
  const fallbackValue = defaultWhatChangedTeamValue(teamOptions, items)
  const selectedValue = teamOptions.some(option => option.value === storedTeamValue)
    ? storedTeamValue
    : fallbackValue
  const selectedTeam = selectedWhatChangedTeam(teamOptions, selectedValue)
  const selectedItem = selectedWhatChangedItem(items, selectedTeam)

  if (!changes?.hasChanges || items.length < 1) return null

  const handleTeamChange = (event) => {
    const nextValue = event.target.value
    setStoredTeamValue(nextValue)
    saveWhatChangedTeamSelection(nextValue)
  }

  return (
    <section className="mb-8" aria-label="What Changed Since Yesterday">
      <SectionHeading
        title="What Changed Since Yesterday"
        subtitle="Pick one club and see how its bullpen picture moved from the prior window."
      />

      <div className="border border-dirt bg-dugout p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <label className="flex w-full max-w-[20rem] flex-col gap-1 font-mono text-[11px] uppercase tracking-wider text-chalk500 sm:min-w-[14rem] sm:max-w-none">
            Team Selector
            <select
              value={selectedValue}
              onChange={handleTeamChange}
              disabled={teamOptions.length === 0}
              className="rounded border border-dirt bg-field px-3 py-2 text-xs normal-case tracking-normal text-chalk200 outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
              aria-label="Choose team for What Changed Since Yesterday"
            >
              {teamOptions.map(team => (
                <option key={team.value} value={team.value}>
                  {team.teamName}{team.teamAbbr ? ` (${team.teamAbbr})` : ''}
                </option>
              ))}
            </select>
          </label>
          <div className="font-mono text-[11px] text-chalk500">
            {teamsLoading && teamOptions.length <= items.length
              ? 'Loading full team list...'
              : teamsError
                ? 'Team list unavailable; showing changed teams.'
                : `${teamOptions.length} teams available`}
          </div>
        </div>

        {selectedItem ? (
          <SelectedChangePanel item={selectedItem} team={selectedTeam} comparison={changes.comparison} />
        ) : (
          <NoSelectedChange team={selectedTeam} comparison={changes.comparison} />
        )}

        {items.length > 1 && (
          <details className="mt-4 border-t border-dirt/70 pt-3">
            <summary className="cursor-pointer list-none font-mono text-[11px] uppercase tracking-widest text-chalk400 transition-colors hover:text-amber">
              View League-Wide Changes -&gt;
            </summary>
            <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {items.map(item => (
                <li key={item.key} className="border border-dirt/80 bg-field/50 p-3">
                  <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                    {item.teamAbbr || item.teamName}
                  </div>
                  <p className="mt-1 text-sm leading-snug text-chalk200">{item.headline}</p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </section>
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
  const fact = item.fact || {}
  return (
    <div className="mt-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
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

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[0.8fr_0.8fr_1.3fr_1.3fr]">
        <ChangeSlot label="Yesterday" value={fact.yesterday || 'Prior bullpen picture'} />
        <ChangeSlot label="Today" value={fact.today || 'Current bullpen picture'} />
        <ChangeSlot label="Change" value={item.summary} />
        <ChangeSlot label="Why It Matters" value={item.context || item.headline} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Link
          to={item.href || team?.href || '/bullpen?view=board'}
          className="inline-flex rounded border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/20"
        >
          Open Team Board -&gt;
        </Link>
      </div>
    </div>
  )
}

function ChangeSlot({ label, value }) {
  return (
    <div className="min-w-0 max-w-[20rem] border border-dirt/80 bg-field/50 p-3 sm:max-w-none">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {label}
      </div>
      <p className="mt-1 break-words text-sm leading-relaxed text-chalk100">
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
