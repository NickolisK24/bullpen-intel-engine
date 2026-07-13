import { useEffect, useRef, useState } from 'react'
import { useFetch } from '../../../hooks/useFetch'
import { toOperatingStateReadModel } from '../../../adapters/operatingStateReadModel'
import { getTeamBullpenBoard, getTeamGameContext, getTeamStory } from '../../../utils/api'
import { ANALYTICS_EVENTS, trackAnalyticsEvent } from '../../../utils/analytics'
import { LoadingPane, ErrorState, EmptyState } from '../../UI'
import BullpenOperatingStateCard from '../BullpenOperatingStateCard'
import BullpenBoardView from './BullpenBoardView'
import TeamGameContextCard from './TeamGameContextCard'
import StoryCard from './StoryCard'
import PitcherDetail from '../PitcherDetail'
import TeamReliefWorkPanel from '../TeamReliefWorkPanel'
import {
  BULLPEN_VIEW_MODE_ACTIVE,
  BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE,
  filterBoardForViewMode,
  rosterCountsAreWithheld,
} from './tonightsBullpenBoardView'

// Resolve a deep-link `team` param (abbreviation like "SF", a team id, or a name)
// against the loaded team list. Returns the matching team_id, or null.
export function resolveTeamId(teamList, requested) {
  if (requested == null) return null
  const raw = String(requested).trim()
  if (!raw || !Array.isArray(teamList)) return null

  const asNum = Number(raw)
  if (Number.isInteger(asNum)) {
    const byId = teamList.find(team => team.team_id === asNum)
    if (byId) return byId.team_id
  }
  const lower = raw.toLowerCase()
  const byAbbr = teamList.find(team => (team.team_abbreviation || '').toLowerCase() === lower)
  if (byAbbr) return byAbbr.team_id
  const byName = teamList.find(team => (team.team_name || '').toLowerCase() === lower)
  return byName ? byName.team_id : null
}

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
  initialSelectedTeam = null,
  boardPayload,
  gameContextPayload,
  storyPayload,
  teamReliefWorkPayload,
  teamReliefWorkLoading,
  teamReliefWorkError,
}) {
  const teamList = teams?.data || []
  const selectedTeamSeed = initialSelectedTeam ?? resolveTeamId(teamList, requestedTeam)
  const [selectedTeam, setSelectedTeam] = useState(selectedTeamSeed)
  // One control instead of the old three-mode "View" row: the board shows the
  // active bullpen by default, and the toggle adds roster-unavailable arms as
  // context. The unavailable-only audit view moved out of the public controls
  // in phase-0-clarity/03 (the roster banner's evidence list covers that job).
  const [showUnavailable, setShowUnavailable] = useState(false)
  const boardViewMode = showUnavailable
    ? BULLPEN_VIEW_MODE_ACTIVE_PLUS_UNAVAILABLE
    : BULLPEN_VIEW_MODE_ACTIVE
  // Opening a pitcher's detail reuses the existing PitcherDetail panel — the
  // board never duplicates that screen.
  const [detailPitcherId, setDetailPitcherId] = useState(null)
  const detailRef = useRef(null)
  const selectedTeamInfo = teamList.find(team => team.team_id === selectedTeam)
  // Apply a given requestedTeam deep-link only once, so a later manual team
  // click is never overridden by the URL.
  const appliedRequestRef = useRef(null)

  useEffect(() => {
    if (detailPitcherId != null) {
      detailRef.current?.focus()
      trackAnalyticsEvent(ANALYTICS_EVENTS.PITCHER_SURFACE_VIEWED, {
        surface: 'bullpen',
        route: '/bullpen',
        source: 'team_board',
        team_abbrev: selectedTeamInfo?.team_abbreviation,
        team_id: selectedTeam,
        player_id: detailPitcherId,
      })
    }
  }, [detailPitcherId, selectedTeam, selectedTeamInfo?.team_abbreviation])

  useEffect(() => {
    if (selectedTeam == null) return
    trackAnalyticsEvent(ANALYTICS_EVENTS.TEAM_SURFACE_VIEWED, {
      surface: 'bullpen',
      route: '/bullpen',
      source: 'team_board',
      team_abbrev: selectedTeamInfo?.team_abbreviation,
      team_id: selectedTeam,
    })
  }, [selectedTeam, selectedTeamInfo?.team_abbreviation])

  // Preselect the deep-linked team (landscape drilldown), once per requested value.
  useEffect(() => {
    if (!requestedTeam || teamList.length === 0) return
    if (appliedRequestRef.current === requestedTeam) return
    const resolved = resolveTeamId(teamList, requestedTeam)
    if (resolved != null) {
      setSelectedTeam(resolved)
      appliedRequestRef.current = requestedTeam
    }
  }, [requestedTeam, teamList])

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
                onClick={() => setSelectedTeam(team.team_id)}
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
        <div className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <div className="min-w-0 flex-1">
            <BullpenOperatingStateCard
              readModel={teamOperatingRead}
              staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
              onRetry={boardState.refetch}
              lastSyncLabel="Bullpen read synced"
              density="compact"
              className="mb-4"
            />
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
              onSelectPitcher={setDetailPitcherId}
              showRoutineFreshness={false}
            />
            <StoryCard
              story={storyState.data}
              loading={storyState.loading}
              error={storyState.error}
              onRetry={storyState.refetch}
            />
            <TeamGameContextCard
              gameContext={gameContextState.data}
              loading={gameContextState.loading}
              error={gameContextState.error}
              compact
            />
          </div>
          {detailPitcherId != null && (
            <div
              ref={detailRef}
              tabIndex={-1}
              role="region"
              aria-label="Selected pitcher detail"
              className="fixed inset-0 z-40 overflow-y-auto bg-field/95 p-4 focus:outline-none lg:static lg:inset-auto lg:z-auto lg:bg-transparent lg:p-0 2xl:w-[34rem] 2xl:shrink-0"
            >
              <PitcherDetail pitcherId={detailPitcherId} onClose={() => setDetailPitcherId(null)} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
