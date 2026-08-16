import { useEffect, useState } from 'react'
import { useFetch } from '../../../hooks/useFetch'
import { toOperatingStateReadModel } from '../../../adapters/operatingStateReadModel'
import { getTeamBullpenBoard, getTeamGameContext, getTeamStory, getTeamShareCard } from '../../../utils/api'
import { FreshnessStamp, LoadingPane, ErrorState, EmptyState } from '../../UI'
import BullpenOperatingStateCard, { BullpenReadDisclosure } from '../BullpenOperatingStateCard'
import BullpenAvailabilityDistribution from './BullpenAvailabilityDistribution'
import BullpenBoardView, { RosterStatusBanner } from './BullpenBoardView'
import RestStatus from './RestStatus'
import WorkloadOverview from './WorkloadOverview'
import RecentUsage from './RecentUsage'
import { useTeamReliefWork } from './useTeamReliefWork'
import TeamGameContextCard from './TeamGameContextCard'
import StoryCard from './StoryCard'
import TeamReliefWorkPanel from '../TeamReliefWorkPanel'
import { buildTeamBoardHref, resolveTeamId } from '../../../utils/evidenceLinks'
import { EVIDENCE_CARD_ORIGIN, buildTeamShareCardFromArtifact } from '../../../utils/shareCardArtifact'
import EvidenceShareMenu from '../../share/EvidenceShareMenu'
import {
  BULLPEN_VIEW_MODE_ACTIVE,
  BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE,
  filterBoardForViewMode,
  rosterCountsAreWithheld,
} from './tonightsBullpenBoardView'

export { resolveTeamId } from '../../../utils/evidenceLinks'

const staticFetchState = (data) => ({
  data,
  loading: false,
  error: null,
  refetch: () => {},
})

// Tonight's Bullpen Board lives inside the Bullpen workflow. It receives the
// shared teams fetch so it does not double-load the team list, manages its own
// single-team selection, and renders the grouped board for that team. A
// `requestedTeam` deep-link (e.g. from the landscape drilldown) preselects a team.
export default function TonightsBullpenBoard({
  teams,
  requestedTeam = null,
  requestedSection = null,
  initialSelectedTeam = null,
  onSelectTeam = () => {},
  onSelectPitcher = () => {},
  boardPayload,
  gameContextPayload,
  storyPayload,
  teamReliefWorkPayload,
  teamReliefWorkLoading,
  teamReliefWorkError,
}) {
  const teamList = teams?.data || []
  const selectedTeam = initialSelectedTeam ?? resolveTeamId(teamList, requestedTeam)
  const selectedTeamRecord = teamList.find(team => Number(team.team_id) === Number(selectedTeam)) || boardPayload?.team || null
  // One control instead of the old three-mode "View" row: the board shows the
  // active bullpen by default, and the toggle adds roster-unavailable arms as
  // context. The unavailable-only audit view moved out of the public controls
  // in phase-0-clarity/03 (the roster banner's evidence list covers that job).
  const [showUnavailable, setShowUnavailable] = useState(false)
  const boardViewMode = showUnavailable
    ? BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE
    : BULLPEN_VIEW_MODE_ACTIVE

  const board = useFetch(
    () => {
      if (selectedTeam == null) return Promise.resolve(null)
      return getTeamBullpenBoard(
        selectedTeam,
        showUnavailable ? { include_stale: true } : {},
      )
    },
    [selectedTeam, showUnavailable],
  )

  // Game context for the selected team (stored game-log only).
  const gameContext = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamGameContext(selectedTeam)),
    [selectedTeam],
  )
  const story = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamStory(selectedTeam)),
    [selectedTeam],
  )
  // SC-03A cutover: the Share Card is sourced from the canonical, published,
  // integrity-verified immutable artifact (never composed client-side).
  const shareCard = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamShareCard(selectedTeam)),
    [selectedTeam],
  )
  const boardState = boardPayload !== undefined ? staticFetchState(boardPayload) : board
  const gameContextState = gameContextPayload !== undefined ? staticFetchState(gameContextPayload) : gameContext
  const hasReliefWorkOverride = (
    teamReliefWorkPayload !== undefined
    || teamReliefWorkLoading !== undefined
    || teamReliefWorkError !== undefined
  )
  const storyState = storyPayload !== undefined ? staticFetchState(storyPayload) : story
  const reliefWork = useTeamReliefWork(selectedTeam, !hasReliefWorkOverride)
  const reliefWorkState = hasReliefWorkOverride
    ? {
        data: teamReliefWorkPayload ?? null,
        loading: teamReliefWorkLoading === true,
        error: teamReliefWorkError ?? null,
        refetch: () => {},
      }
    : reliefWork
  const rosterContextLimited = rosterCountsAreWithheld(boardState.data)
  const filteredBoard = filterBoardForViewMode(boardState.data, boardViewMode)
  const teamOperatingRead = toOperatingStateReadModel(boardState.data || {}, {
    scope: 'team',
    team: boardState.data?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density: 'compact',
  })
  const normalizedRequestedSection = String(requestedSection || '').replace(/^#/, '')
  // Canonical artifact-backed card; null when no published artifact exists, which
  // drives the share menu's controlled unavailable state (no legacy fallback).
  const teamCard = buildTeamShareCardFromArtifact(shareCard.data)
  const teamLinkFallbackPath = buildTeamBoardHref(selectedTeamRecord, { section: normalizedRequestedSection })
  const teamDestinationUrl = teamCard?.destinationUrl
    || (teamLinkFallbackPath ? `${EVIDENCE_CARD_ORIGIN}${teamLinkFallbackPath}` : null)
  const teamEvidenceTarget = teamCard?.evidenceTarget
    || (normalizedRequestedSection === 'team-relief-work'
      ? 'team_relief_work'
      : normalizedRequestedSection === 'pitcher-lanes'
        ? 'pitcher_lanes'
        : 'team_read')
  const teamShareText = teamCard?.shareText
    || `Current ${teamOperatingRead.teamName || 'team'} bullpen evidence on BaseballOS.`

  useEffect(() => {
    if (rosterContextLimited && showUnavailable) {
      setShowUnavailable(false)
    }
  }, [rosterContextLimited, showUnavailable])

  return (
    <div>
      {/* Compact selection keeps all 30 teams to one accessible control. */}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 sm:max-w-xs">
          {teamList.length === 0 ? (
            <span className="inline-flex min-h-11 items-center font-mono text-xs text-chalk500">
              {teams?.loading ? 'Loading teams…' : 'Teams unavailable.'}
            </span>
          ) : (
            <>
              <label htmlFor="team-board-selector" className="block font-mono text-[10px] uppercase tracking-widest text-chalk500">Team</label>
              <select
                id="team-board-selector"
                aria-label="Select team for Team Board"
                value={selectedTeam ?? ''}
                onChange={event => onSelectTeam(event.target.value ? Number(event.target.value) : null)}
                className="mt-1 min-h-11 w-full rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none focus:border-amber/50 focus-visible:ring-2 focus-visible:ring-amber/60"
              >
                <option value="">Pick a team</option>
                {teamList.map(team => <option key={team.team_id} value={team.team_id}>{team.team_name || team.team_abbreviation}</option>)}
              </select>
            </>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            type="button"
            onClick={() => setShowUnavailable(value => !value)}
            aria-pressed={showUnavailable}
            disabled={rosterContextLimited}
            className={`min-h-11 rounded border px-2.5 py-2 font-mono text-xs transition-all ${
              rosterContextLimited
                ? 'cursor-not-allowed border-dirt text-chalk600 opacity-70'
                : showUnavailable
                  ? 'bg-amber/10 border-amber/40 text-amber'
                  : 'border-dirt text-chalk400 hover:border-chalk400'
            }`}
          >
            Show unavailable arms
          </button>
          {rosterContextLimited ? (
            <span className="rounded border border-dirt bg-dugout px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Unavailable roster context withheld.
            </span>
          ) : showUnavailable && (
            <span className="rounded border border-dirt bg-dugout px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Unavailable relievers are context only.
            </span>
          )}
        </div>
      </div>

      {selectedTeam == null ? (
        <EmptyState title="Pick a team" subtitle="Select a team above to see its current bullpen board." />
      ) : boardState.loading ? (
        <LoadingPane message="Building current bullpen board..." />
      ) : boardState.error ? (
        <ErrorState message={boardState.error} onRetry={boardState.refetch} />
      ) : (
        // Keyed by team so a team switch fully remounts the answer: no prior
        // team's state, distribution, evidence, or disclosure state can linger.
        <div key={selectedTeam} className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <div className="min-w-0 flex-1">
            {/* Baseball answer zone: state, why, game context, freshness, counts. */}
            <div className="mb-4">
              <BullpenOperatingStateCard
                readModel={teamOperatingRead}
                staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
                onRetry={boardState.refetch}
                density="compact"
                // The Team Board's page heading already reads
                // "{Full Team Name} Bullpen", so the card would otherwise repeat
                // the club name as a second title directly beneath it. The
                // card's region label still carries the team for anyone landing
                // on it out of context.
                titleOwnedByPage
                readerFirst
              />
              {(gameContextState.loading || gameContextState.error || gameContextState.data) && (
                <TeamGameContextCard
                  gameContext={gameContextState.data}
                  loading={gameContextState.loading}
                  error={gameContextState.error}
                  compact
                />
              )}
              <FreshnessStamp freshness={boardState.data?.freshness} className="mt-3 px-1" showExceptional={false} />
              <BullpenAvailabilityDistribution board={filteredBoard} restedOptions={teamOperatingRead.cleanOptions} />
            </div>
            <BullpenBoardView
              board={filteredBoard}
              onSelectPitcher={onSelectPitcher}
              showRoutineFreshness={false}
              showRosterContext={false}
            />
            <div className="mt-5 grid items-start gap-4 lg:grid-cols-2">
              <RecentUsage
                payload={reliefWorkState.data}
                loading={reliefWorkState.loading}
                error={reliefWorkState.error}
              />
              <div className="self-start space-y-4">
                <RestStatus restStatus={boardState.data?.rest_status} />
                <WorkloadOverview read={teamOperatingRead.workloadConcentration} />
              </div>
            </div>
            {storyState.data?.story_available === true && <section className="mt-6" aria-labelledby="what-changed-title">
              <h2 id="what-changed-title" className="font-display text-xl tracking-wide text-chalk100">What Changed</h2>
              <div className="mt-2">
                <StoryCard
                  story={storyState.data}
                  loading={storyState.loading}
                  error={storyState.error}
                  onRetry={storyState.refetch}
                  hideFreshnessMeta
                />
              </div>
            </section>}
            <div className="mt-6">
              <TeamReliefWorkPanel
                payload={reliefWorkState.data}
                loading={reliefWorkState.loading}
                error={reliefWorkState.error}
                rosterContextLimited={rosterContextLimited}
                hideRoutineFreshness
                boardDataThrough={boardState.data?.freshness?.data_through || boardState.data?.freshness?.dataThrough || boardState.data?.data_through}
              />
            </div>
            <div className="mt-4"><RosterStatusBanner board={filteredBoard} /></div>
            <div className="mt-4 flex justify-end">
              <EvidenceShareMenu
                cardModel={teamCard}
                destinationUrl={teamDestinationUrl}
                shareText={teamShareText}
                context={{
                  surface: 'bullpen_board',
                  cardType: 'team',
                  team_ref: teamOperatingRead.teamAbbreviation,
                  evidence_target: teamEvidenceTarget,
                  data_through: teamOperatingRead.freshness?.dataThrough,
                }}
              />
            </div>
            <BullpenReadDisclosure
              readModel={teamOperatingRead}
              staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
              className="mt-4"
            />
          </div>
        </div>
      )}
    </div>
  )
}
