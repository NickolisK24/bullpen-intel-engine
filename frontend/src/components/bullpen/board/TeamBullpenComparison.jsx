import { useFetch } from '../../../hooks/useFetch'
import { getTeamBullpenComparison } from '../../../utils/api'
import { resolveTeamId } from '../../../utils/evidenceLinks'
import { LoadingPane, ErrorState, EmptyState } from '../../UI'
import BullpenComparisonView from './BullpenComparisonView'

function TeamSelect({ label, teams, value, onChange }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{label}</span>
      <select
        value={value ?? ''}
        onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
        aria-label={label}
        className="rounded border border-dirt bg-field/70 px-3 py-2 font-mono text-xs text-chalk200 outline-none focus:border-amber/50"
      >
        <option value="">Select a team…</option>
        {teams.map(team => (
          <option key={team.team_id} value={team.team_id}>
            {team.team_abbreviation || team.team_name}
          </option>
        ))}
      </select>
    </label>
  )
}

export function comparisonIsReady(teamA, teamB) {
  return teamA != null && teamB != null && teamA !== teamB
}

// Team Bullpen Comparison lives inside the Bullpen workflow. It receives the
// shared teams fetch, manages two team selections, and renders the descriptive
// side-by-side comparison plus both full boards.
export default function TeamBullpenComparison({
  teams,
  requestedTeamA = null,
  requestedTeamB = null,
  onTeamAChange = () => {},
  onTeamBChange = () => {},
}) {
  const teamList = teams?.data || []
  const teamA = resolveTeamId(teamList, requestedTeamA)
  const teamB = resolveTeamId(teamList, requestedTeamB)

  const ready = comparisonIsReady(teamA, teamB)
  const comparison = useFetch(
    () => (ready ? getTeamBullpenComparison(teamA, teamB) : Promise.resolve(null)),
    [teamA, teamB, ready],
  )

  return (
    <div>
      {/* 1. Team selectors */}
      <div className="mb-6 grid gap-3 sm:grid-cols-2 sm:max-w-xl">
        <TeamSelect label="Team A" teams={teamList} value={teamA} onChange={onTeamAChange} />
        <TeamSelect label="Team B" teams={teamList} value={teamB} onChange={onTeamBChange} />
      </div>

      {teamA == null || teamB == null ? (
        <EmptyState title="Pick two teams to compare" subtitle="Choose Team A and Team B above." />
      ) : teamA === teamB ? (
        <EmptyState title="Choose two different teams" subtitle="Team A and Team B must differ to compare bullpens." />
      ) : comparison.loading ? (
        <LoadingPane message="Comparing bullpens…" />
      ) : comparison.error ? (
        <ErrorState message={comparison.error} onRetry={comparison.refetch} />
      ) : (
        <BullpenComparisonView payload={comparison.data} />
      )}
    </div>
  )
}
