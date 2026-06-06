import { useEffect, useRef, useState } from 'react'
import { useFetch } from '../../../hooks/useFetch'
import { getTeamBullpenBoard, getTeamGameContext } from '../../../utils/api'
import { LoadingPane, ErrorState, EmptyState } from '../../UI'
import BullpenBoardView from './BullpenBoardView'
import TeamGameContextCard from './TeamGameContextCard'
import PitcherDetail from '../PitcherDetail'

// Tonight's Bullpen Board lives inside the Bullpen workflow. It receives the
// shared teams fetch so it does not double-load the team list, manages its own
// single-team selection, and renders the grouped board for that team.
export default function TonightsBullpenBoard({ teams }) {
  const teamList = teams?.data || []
  const [selectedTeam, setSelectedTeam] = useState(null)
  const [includeStale, setIncludeStale] = useState(false)
  // Opening a pitcher's detail reuses the existing PitcherDetail panel — the
  // board never duplicates that screen.
  const [detailPitcherId, setDetailPitcherId] = useState(null)
  const detailRef = useRef(null)

  useEffect(() => {
    if (detailPitcherId != null) detailRef.current?.focus()
  }, [detailPitcherId])

  // Default to the first team once the list loads so the board shows a bullpen
  // immediately instead of an empty prompt.
  useEffect(() => {
    if (selectedTeam == null && teamList.length > 0) {
      setSelectedTeam(teamList[0].team_id)
    }
  }, [teamList, selectedTeam])

  const board = useFetch(
    () => {
      if (selectedTeam == null) return Promise.resolve(null)
      return getTeamBullpenBoard(selectedTeam, includeStale ? { include_stale: true } : {})
    },
    [selectedTeam, includeStale],
  )

  // Today's Game Context for the selected team (stored game-log only).
  const gameContext = useFetch(
    () => (selectedTeam == null ? Promise.resolve(null) : getTeamGameContext(selectedTeam)),
    [selectedTeam],
  )

  return (
    <div>
      {/* Team selector — single team; the board is always one bullpen. */}
      <div className="mb-5 flex flex-wrap gap-2">
        {teams?.loading && teamList.length === 0 ? (
          <span className="font-mono text-xs text-chalk500">Loading teams…</span>
        ) : (
          teamList.map(team => (
            <button
              key={team.team_id}
              onClick={() => setSelectedTeam(team.team_id)}
              aria-pressed={selectedTeam === team.team_id}
              className={`px-3 py-1.5 rounded border text-xs font-mono transition-all ${
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

      <div className="mb-5">
        <label className="inline-flex cursor-pointer items-center gap-2 font-mono text-xs text-chalk400">
          <input
            type="checkbox"
            checked={includeStale}
            onChange={() => setIncludeStale(v => !v)}
            className="h-3.5 w-3.5 accent-amber"
          />
          Include inactive pitchers (no games in the last 14 days)
        </label>
      </div>

      {selectedTeam == null ? (
        <EmptyState title="Pick a team" subtitle="Select a team above to see tonight's bullpen." />
      ) : board.loading ? (
        <LoadingPane message="Building tonight's board…" />
      ) : board.error ? (
        <ErrorState message={board.error} onRetry={board.refetch} />
      ) : (
        <div className="flex flex-col gap-6 2xl:flex-row 2xl:items-start">
          <div className="min-w-0 flex-1">
            <TeamGameContextCard
              gameContext={gameContext.data}
              loading={gameContext.loading}
              error={gameContext.error}
            />
            <BullpenBoardView board={board.data} onSelectPitcher={setDetailPitcherId} />
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
