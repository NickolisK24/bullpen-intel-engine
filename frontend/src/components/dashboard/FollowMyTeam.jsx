import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { useFollowedTeamPreference } from '../../hooks/useFollowedTeamPreference'
import { getTeamBullpenBoard, getTeams } from '../../utils/api'
import {
  buildFollowedTeamHref,
  resolveFollowedTeam,
} from '../../utils/followedTeamPreference'
import { getBoardContextView } from '../bullpen/board/tonightsBullpenBoardView'

function teamLabel(team) {
  return team?.team_name || team?.team_abbreviation || 'Followed team'
}

function teamShortLabel(team) {
  return team?.team_abbreviation || team?.team_name || 'Team'
}

function teamSelectValue(team) {
  return team?.team_id == null ? '' : String(team.team_id)
}

function findTeamByValue(teams, value) {
  const selectedId = Number(value)
  if (!Number.isInteger(selectedId)) return null
  return (Array.isArray(teams) ? teams : []).find(team => Number(team?.team_id) === selectedId) || null
}

function TeamSelect({ teams, value, onSelectTeam, label = 'Choose followed team', disabled = false }) {
  return (
    <label className="flex min-w-[13rem] flex-col gap-1 font-mono text-[11px] uppercase tracking-wider text-chalk500">
      {label}
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => {
          const team = findTeamByValue(teams, event.target.value)
          if (team) onSelectTeam(team)
        }}
        className="rounded border border-dirt bg-field px-3 py-2 text-xs normal-case tracking-normal text-chalk200 outline-none transition-colors hover:border-chalk500 focus:border-amber/60 disabled:cursor-not-allowed disabled:opacity-60"
        aria-label={label}
      >
        <option value="">Choose team</option>
        {(Array.isArray(teams) ? teams : []).map(team => (
          <option key={team.team_id} value={team.team_id}>
            {team.team_abbreviation ? `${team.team_abbreviation} - ${team.team_name}` : team.team_name}
          </option>
        ))}
      </select>
    </label>
  )
}

function FollowedTeamSummary({ board }) {
  if (!board) {
    return (
      <p className="text-sm leading-relaxed text-chalk500">
        Team bullpen context will appear here when the board data is available.
      </p>
    )
  }

  const context = getBoardContextView(board)
  const snapshot = context.snapshot.filter(row => (
    row.status === 'Available'
    || row.status === 'Monitor'
    || row.status === 'Limited'
    || row.status === 'Avoid'
    || row.status === 'Unavailable'
  ))

  return (
    <div className="space-y-3">
      <div className="rounded border border-dirt bg-field/50 p-3" role="status">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-display text-lg tracking-wide text-chalk100">
            {context.label || 'Bullpen context unavailable.'}
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Confidence: {context.confidenceLabel}
          </div>
        </div>
        {context.reasons[0] && (
          <p className="mt-1 text-xs leading-relaxed text-chalk400">{context.reasons[0]}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {snapshot.map(row => (
          <div key={row.status} className="rounded border border-dirt/80 bg-dugout/70 p-2">
            <div className="font-mono text-[10px] uppercase tracking-wider text-chalk500">{row.label}</div>
            <div className="mt-0.5 font-mono text-xl text-chalk100">{row.count}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FollowMyTeamCard({
  teams = [],
  teamsLoading = false,
  teamsError = null,
  followedTeam = null,
  board = null,
  boardLoading = false,
  boardError = null,
  onSelectTeam = () => {},
  onClearTeam = () => {},
}) {
  const hasFollowedTeam = !!followedTeam
  const selectedValue = teamSelectValue(followedTeam)
  const followedHref = buildFollowedTeamHref(followedTeam)

  return (
    <section className="mb-6" aria-label="Follow My Team">
      <div className={`card p-4 ${hasFollowedTeam ? 'border-amber/30 bg-amber/5' : ''}`}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
              Follow My Team
            </div>
            {hasFollowedTeam ? (
              <>
                <h2 className="mt-1 font-display text-2xl tracking-wide text-chalk100">
                  {teamLabel(followedTeam)}
                </h2>
                <p className="mt-1 text-sm leading-relaxed text-chalk400">
                  What shape is my bullpen in tonight?
                </p>
              </>
            ) : (
              <>
                <h2 className="mt-1 font-display text-xl tracking-wide text-chalk100">
                  Make BaseballOS open with your bullpen
                </h2>
                <p className="mt-1 text-sm leading-relaxed text-chalk400">
                  Follow your team to make BaseballOS open with the bullpen you care about.
                </p>
              </>
            )}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <TeamSelect
              teams={teams}
              value={selectedValue}
              onSelectTeam={onSelectTeam}
              label={hasFollowedTeam ? 'Change team' : 'Choose followed team'}
              disabled={teamsLoading || teams.length === 0}
            />
            {hasFollowedTeam && (
              <button
                type="button"
                onClick={onClearTeam}
                className="rounded border border-dirt px-3 py-2 font-mono text-xs uppercase tracking-wider text-chalk400 transition-colors hover:border-amber/40 hover:text-amber"
              >
                Clear followed team
              </button>
            )}
          </div>
        </div>

        {teamsLoading && teams.length === 0 && (
          <p className="mt-3 font-mono text-xs text-chalk500">Loading team list...</p>
        )}
        {teamsError && (
          <p className="mt-3 font-mono text-xs text-chalk500">Team list unavailable.</p>
        )}

        {hasFollowedTeam && (
          <div className="mt-4 space-y-3">
            {boardLoading ? (
              <p className="font-mono text-xs text-chalk500">Loading followed-team bullpen context...</p>
            ) : boardError ? (
              <p className="font-mono text-xs text-chalk500">Followed-team bullpen context unavailable.</p>
            ) : (
              <FollowedTeamSummary board={board} />
            )}

            <Link
              to={followedHref}
              className="inline-flex rounded border border-amber/30 bg-amber/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/15"
            >
              Open {teamShortLabel(followedTeam)} Bullpen Board -&gt;
            </Link>
          </div>
        )}
      </div>
    </section>
  )
}

export default function FollowMyTeam() {
  const teams = useFetch(getTeams)
  const teamList = teams.data || []
  const {
    followedTeam,
    setFollowedTeam,
    clearFollowedTeam,
  } = useFollowedTeamPreference()
  const resolvedFollowedTeam = resolveFollowedTeam(followedTeam, teamList)
  const followedTeamId = resolvedFollowedTeam?.team_id ?? null

  const board = useFetch(
    () => (
      followedTeamId == null
        ? Promise.resolve(null)
        : getTeamBullpenBoard(followedTeamId)
    ),
    [followedTeamId],
  )

  return (
    <FollowMyTeamCard
      teams={teamList}
      teamsLoading={teams.loading}
      teamsError={teams.error}
      followedTeam={resolvedFollowedTeam}
      board={board.data}
      boardLoading={followedTeamId != null && board.loading}
      boardError={followedTeamId != null ? board.error : null}
      onSelectTeam={setFollowedTeam}
      onClearTeam={clearFollowedTeam}
    />
  )
}
