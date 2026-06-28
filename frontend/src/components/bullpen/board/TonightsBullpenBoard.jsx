import { useEffect, useRef, useState } from 'react'
import { useFetch } from '../../../hooks/useFetch'
import { usePreferredTeamPreference } from '../../../hooks/usePreferredTeamPreference'
import { toOperatingStateReadModel } from '../../../adapters/operatingStateReadModel'
import { getTeamBullpenBoard, getTeamGameContext, getTeamStory } from '../../../utils/api'
import { LoadingPane, ErrorState, EmptyState } from '../../UI'
import BullpenOperatingStateCard from '../BullpenOperatingStateCard'
import BullpenBoardView from './BullpenBoardView'
import TeamGameContextCard from './TeamGameContextCard'
import StoryCard from './StoryCard'
import PitcherDetail from '../PitcherDetail'
import {
  BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY,
  BULLPEN_VIEW_MODES,
  DEFAULT_BULLPEN_VIEW_MODE,
  bullpenViewModeRequiresUnavailableContext,
  filterBoardForViewMode,
  getBullpenViewModeEmptyState,
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

// Tonight's Bullpen Board lives inside the Bullpen workflow. It receives the
// shared teams fetch so it does not double-load the team list, manages its own
// single-team selection, and renders the grouped board for that team. A
// `requestedTeam` deep-link (e.g. from the landscape drilldown) preselects a team.
export default function TonightsBullpenBoard({ teams, requestedTeam = null }) {
  const teamList = teams?.data || []
  const { preferredTeam } = usePreferredTeamPreference(teamList)
  const preferredTeamId = preferredTeam?.team_id ?? null
  const [selectedTeam, setSelectedTeam] = useState(null)
  const [boardViewMode, setBoardViewMode] = useState(DEFAULT_BULLPEN_VIEW_MODE)
  // Opening a pitcher's detail reuses the existing PitcherDetail panel — the
  // board never duplicates that screen.
  const [detailPitcherId, setDetailPitcherId] = useState(null)
  const detailRef = useRef(null)
  // Apply a given requestedTeam deep-link only once, so a later manual team
  // click is never overridden by the URL.
  const appliedRequestRef = useRef(null)

  useEffect(() => {
    if (detailPitcherId != null) detailRef.current?.focus()
  }, [detailPitcherId])

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

  // If the user has picked a preferred team, make the board open there unless
  // the URL explicitly requested another club.
  useEffect(() => {
    if (requestedTeam || selectedTeam != null || teamList.length === 0 || preferredTeamId == null) return
    setSelectedTeam(preferredTeamId)
  }, [preferredTeamId, requestedTeam, selectedTeam, teamList.length])

  // Default to the first team once the list loads so the board shows a bullpen
  // immediately — unless a resolvable deep link is pending (avoids a flash).
  useEffect(() => {
    if (selectedTeam != null || teamList.length === 0) return
    if (requestedTeam && resolveTeamId(teamList, requestedTeam) != null) return
    if (preferredTeamId != null) return
    setSelectedTeam(teamList[0].team_id)
  }, [teamList, selectedTeam, requestedTeam, preferredTeamId])

  const board = useFetch(
    () => {
      if (selectedTeam == null) return Promise.resolve(null)
      return getTeamBullpenBoard(
        selectedTeam,
        bullpenViewModeRequiresUnavailableContext(boardViewMode) ? { include_stale: true } : {},
      )
    },
    [selectedTeam, boardViewMode],
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
  const filteredBoard = filterBoardForViewMode(board.data, boardViewMode)
  const selectedViewMode = BULLPEN_VIEW_MODES.find(mode => mode.id === boardViewMode)
  const teamOperatingRead = toOperatingStateReadModel(board.data || {}, {
    scope: 'team',
    team: board.data?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density: 'compact',
  })

  // The Team Board's single story surface is the canonical StoryCard near the
  // board. The board strips render compact alongside it, except in the
  // unavailable-only view mode.
  const compactBoardContext = boardViewMode !== BULLPEN_VIEW_MODE_UNAVAILABLE_ONLY

  return (
    <div>
      {/* Team selector — single team; the board is always one bullpen. */}
      <div className="mb-4 flex flex-wrap gap-1.5">
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

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">View</div>
          <div className="mt-1 flex w-fit max-w-full flex-wrap gap-1 rounded-lg border border-dirt bg-chalk/30 p-1">
            {BULLPEN_VIEW_MODES.map(mode => (
              <button
                key={mode.id}
                type="button"
                onClick={() => setBoardViewMode(mode.id)}
                aria-pressed={boardViewMode === mode.id}
                title={mode.description}
                className={`rounded px-3 py-1.5 font-mono text-xs transition-all ${
                  boardViewMode === mode.id
                    ? 'bg-chalk text-chalk200 shadow'
                    : 'text-chalk400 hover:text-chalk200'
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>
          {selectedViewMode?.description && (
            <p className="sr-only" aria-live="polite">
              {selectedViewMode.description}
            </p>
          )}
        </div>
        {bullpenViewModeRequiresUnavailableContext(boardViewMode) && (
          <span className="w-fit rounded border border-dirt bg-dugout px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Unavailable relievers are context only.
          </span>
        )}
      </div>

      {selectedTeam == null ? (
        <EmptyState title="Pick a team" subtitle="Select a team above to see its current bullpen board." />
      ) : board.loading ? (
        <LoadingPane message="Building current bullpen board..." />
      ) : board.error ? (
        <ErrorState message={board.error} onRetry={board.refetch} />
      ) : (
        <div className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <div className="min-w-0 flex-1">
            <BullpenOperatingStateCard
              readModel={teamOperatingRead}
              staleWithError={teamOperatingRead.freshness?.isStale || teamOperatingRead.freshness?.failClosed}
              onRetry={board.refetch}
              lastSyncLabel="Bullpen read synced"
              density="compact"
              className="mb-4"
            />
            <BullpenBoardView
              board={filteredBoard}
              onSelectPitcher={setDetailPitcherId}
              compact={compactBoardContext}
              showRoutineFreshness={false}
              emptyState={getBullpenViewModeEmptyState(boardViewMode)}
            />
            <StoryCard
              story={story.data}
              loading={story.loading}
              error={story.error}
              onRetry={story.refetch}
            />
            <TeamGameContextCard
              gameContext={gameContext.data}
              loading={gameContext.loading}
              error={gameContext.error}
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
