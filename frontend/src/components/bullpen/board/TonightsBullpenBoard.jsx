import { useEffect, useState } from 'react'
import { useFetch } from '../../../hooks/useFetch'
import { toOperatingStateReadModel } from '../../../adapters/operatingStateReadModel'
import { getTeamBullpenBoard, getTeamGameContext, getTeamStory } from '../../../utils/api'
import { LoadingPane, ErrorState, EmptyState } from '../../UI'
import BullpenOperatingStateCard from '../BullpenOperatingStateCard'
import BullpenAvailabilityDistribution from './BullpenAvailabilityDistribution'
import BullpenBoardView from './BullpenBoardView'
import TeamGameContextCard from './TeamGameContextCard'
import StoryCard from './StoryCard'
import TeamReliefWorkPanel from '../TeamReliefWorkPanel'
import { buildTeamBoardHref, resolveTeamId } from '../../../utils/evidenceLinks'
import { EVIDENCE_CARD_ORIGIN, buildTeamEvidenceCard } from '../../../utils/evidenceCardModel'
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
  const boardState = boardPayload !== undefined ? staticFetchState(boardPayload) : board
  const gameContextState = gameContextPayload !== undefined ? staticFetchState(gameContextPayload) : gameContext
  const storyState = storyPayload !== undefined ? staticFetchState(storyPayload) : story
  const rosterContextLimited = rosterCountsAreWithheld(boardState.data)
  const filteredBoard = filterBoardForViewMode(boardState.data, boardViewMode)
  const teamOperatingRead = toOperatingStateReadModel(boardState.data || {}, {
    scope: 'team',
    team: boardState.data?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density: 'compact',
  })
  const normalizedRequestedSection = String(requestedSection || '').replace(/^#/, '')
  const teamCard = buildTeamEvidenceCard(teamOperatingRead)
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
      {/* One controls row: team selector plus the unavailable toggle. */}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {teams?.loading && teamList.length === 0 ? (
            <span className="font-mono text-xs text-chalk500">Loading teams…</span>
          ) : (
            teamList.map(team => (
              <button
                key={team.team_id}
                onClick={() => onSelectTeam(team.team_id)}
                aria-pressed={selectedTeam === team.team_id}
                className={`rounded border px-2.5 py-1 text-xs font-mono transition-all ${
                  selectedTeam === team.team_id
                    ? 'bg-amber/10 border-amber/40 text-amber'
                    : 'border-dirt text-chalk400 hover:border-chalk400'
                }`}
              >
                {team.team_abbreviation || team.team_name}
              </button>
            ))
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            type="button"
            onClick={() => setShowUnavailable(value => !value)}
            aria-pressed={showUnavailable}
            disabled={rosterContextLimited}
            className={`rounded border px-2.5 py-1 font-mono text-xs transition-all ${
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
            {/* Answer zone: team identity, current state, one-sentence why,
                immediate receipts, freshness, and limitations live in the
                operating-state card; the availability distribution sits directly
                beneath it so the four public counts are part of the fast answer. */}
            <div className="mb-4">
              <div className="mb-2 flex justify-end">
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
              <BullpenOperatingStateCard
                readModel={teamOperatingRead}
                staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
                onRetry={boardState.refetch}
                lastSyncLabel="Bullpen read synced"
                density="compact"
              />
              <BullpenAvailabilityDistribution board={filteredBoard} />
            </div>
            <div className="mb-4">
              <TeamReliefWorkPanel
                teamId={selectedTeam}
                payload={teamReliefWorkPayload}
                loading={teamReliefWorkLoading}
                error={teamReliefWorkError}
                rosterContextLimited={rosterContextLimited}
              />
            </div>
            <BullpenBoardView
              board={filteredBoard}
              onSelectPitcher={onSelectPitcher}
              showRoutineFreshness={false}
            />
            {/* Secondary narrative context moves behind clear disclosures so the
                default view stays focused on the bullpen answer. Neither carries
                an inbound evidence anchor, so collapsing them breaks no links. */}
            <details className="mt-6 rounded-lg border border-dirt bg-dugout/35" aria-label="Team story">
              <summary className="flex cursor-pointer items-center justify-between gap-2 px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-chalk300 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
                <span>Read the team story</span>
                <span className="text-[10px] text-chalk600">Today's bullpen storyline</span>
              </summary>
              <div className="px-3 pb-3">
                <StoryCard
                  story={storyState.data}
                  loading={storyState.loading}
                  error={storyState.error}
                  onRetry={storyState.refetch}
                />
              </div>
            </details>
            <details className="mt-4 rounded-lg border border-dirt bg-dugout/35" aria-label="Recent game context">
              <summary className="flex cursor-pointer items-center justify-between gap-2 px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-chalk300 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
                <span>See recent game context</span>
                <span className="text-[10px] text-chalk600">Latest completed-game detail</span>
              </summary>
              <div className="px-3 pb-3">
                <TeamGameContextCard
                  gameContext={gameContextState.data}
                  loading={gameContextState.loading}
                  error={gameContextState.error}
                  compact
                />
              </div>
            </details>
          </div>
        </div>
      )}
    </div>
  )
}
