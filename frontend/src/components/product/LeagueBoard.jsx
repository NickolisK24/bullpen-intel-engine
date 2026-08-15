import { useFetch } from '../../hooks/useFetch'
import { getLeagueTeamStateBoard } from '../../utils/api'
import { ProductPageHeader, STATE_DEFINITIONS, StateRead, TeamRoute, displayDate } from './ProductPrimitives'

function TeamRow({ team }) {
  const nonState = team.team_state?.available !== true
  return (
    <TeamRoute team={team}>
      <div className="border-t border-line-quiet py-4 transition-colors hover:bg-panel-2/60">
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="font-display text-lg font-semibold text-chalk100">{team.team_name}</h3>
          <span className="font-mono text-[10px] text-chalk500">{team.team_abbreviation}</span>
        </div>
        <p className="mt-2 text-sm leading-5 text-chalk400">
          {nonState
            ? team.team_state?.unavailable_message || 'No current Team State is publishable.'
            : `${team.clean_option_count} clean options across ${team.active_read_count} current arm reads.`}
        </p>
      </div>
    </TeamRoute>
  )
}

export default function LeagueBoard() {
  const request = useFetch(getLeagueTeamStateBoard)
  const board = request.data
  const freshness = board?.freshness || {}

  return (
    <div className="bos-page py-8 md:py-10">
      <ProductPageHeader
        eyebrow="Dashboard"
        title="League Board"
        description="Every club appears once, grouped by its current Team State. A state describes an operating condition, not the quality of a bullpen — these groups are not a ranking."
        facts={[
          { label: 'League data through', value: displayDate(freshness.data_through) },
          { label: 'Current reads', value: board ? `${board.teams_in_current_state} of ${board.teams_expected} clubs` : null },
        ]}
      />

      {request.loading && !board && <p className="py-10 font-mono text-xs text-chalk500">Building the league board…</p>}
      {request.error && !board && <p className="py-10 text-sm text-chalk400">The league board is unavailable right now.</p>}
      {board && (
        <div className="grid gap-10 py-9 md:grid-cols-2 xl:grid-cols-3">
          {(board.groups || []).filter(group => group.key !== 'withheld').map(group => (
            <section key={group.key} aria-labelledby={`league-${group.key}`}>
              <div className="flex items-center justify-between border-b border-line pb-4">
                <StateRead state={group.key} label={group.label} />
                <span className="font-display text-2xl text-chalk200">{group.count}</span>
              </div>
              <p className="min-h-[4rem] py-4 text-sm leading-6 text-chalk500">{STATE_DEFINITIONS[group.key]}</p>
              <div>{group.teams.map(team => <TeamRow key={team.team_id} team={team} />)}</div>
            </section>
          ))}
        </div>
      )}

      {board?.groups?.find(group => group.key === 'withheld')?.count > 0 && (
        <section className="border-t border-line py-8">
          <div className="flex items-center gap-3"><StateRead state="withheld" label="Withheld" /><span className="font-mono text-xs text-chalk500">{board.teams_withheld}</span></div>
          <p className="mt-3 max-w-definition text-sm leading-6 text-chalk400">A withheld read is a state of the publication, not a fourth Team State.</p>
          <div className="mt-4 grid gap-x-8 md:grid-cols-2 xl:grid-cols-3">
            {board.groups.find(group => group.key === 'withheld').teams.map(team => <TeamRow key={team.team_id} team={team} />)}
          </div>
        </section>
      )}
    </div>
  )
}
