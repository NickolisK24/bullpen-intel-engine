import { Link } from 'react-router-dom'
import { useFetch } from '../../../hooks/useFetch'
import { getRehearsalTeamBoard } from '../../../utils/api'
import { buildRehearsalPitcherHref } from '../../../utils/evidenceLinks'
import HistoricalChanges from '../../history/HistoricalChanges'
import { ErrorState, LoadingPane } from '../../UI'

export function verifyHistoricalBoard(board, team, revision, generation) {
  const changes = board?.what_changed
  if (board?.scope !== 'isolated_historical_core' || board.status !== 'represented'
      || board.current_serving_eligible !== false || board.generation !== generation
      || board.selection_revision !== revision || board.team?.team_id !== team || !board.team.team_name
      || !board.data_through || !board.availability_reference || !Array.isArray(board.active_bullpen)
      || board.team.team_state?.data_through !== board.data_through
      || board.competitive_workload?.data_through !== board.data_through
      || changes?.status !== 'represented' || changes.scope !== board.scope || changes.team !== team
      || changes.selection_revision !== revision || changes.generation !== generation
      || changes.current_serving_eligible !== false || changes.represented !== board.data_through) {
    throw new Error('The requested historical Team Board edition could not be verified.')
  }
  return board
}

function metric(fact) {
  return fact?.status === 'complete' && Number.isSafeInteger(fact.value) && fact.value >= 0 ? fact.value : 'Unavailable'
}

export default function HistoricalTeamBoard({ team, revision, generation }) {
  const board = useFetch(async options => verifyHistoricalBoard(
    await getRehearsalTeamBoard(team, revision, options), team, revision, generation,
  ), [team, revision, generation])
  if (board.loading) return <LoadingPane message="Loading historical Team Board…" />
  if (board.error || !board.data) return <ErrorState message={board.error || 'Historical board unavailable.'} onRetry={board.refetch} />
  const data = board.data
  const state = data.team.team_state
  return <main className="mx-auto max-w-5xl space-y-6 p-6">
    <header>
      <p>Historical Team Board · Revision {revision}</p>
      <h1 className="font-display text-3xl">{data.team.team_name}</h1>
      <p>Data through {data.data_through} · Availability reference {data.availability_reference}</p>
    </header>
    <section><h2>Team State on the reference date</h2>
      <p>{state.available ? state.public_label : state.unavailable_message || 'Unavailable'}</p>
    </section>
    <section><h2>Active bullpen through {data.data_through}</h2>
      {data.active_bullpen.length ? <ul>{data.active_bullpen.map(arm => {
        const href = buildRehearsalPitcherHref(arm.public_pitcher_id, revision, generation)
        const label = arm.name || `MLB pitcher ${arm.mlb_id}`
        return <li key={arm.mlb_id}>{href ? <Link className="underline" to={href}>{label}</Link> : label}</li>
      })}</ul> : <p>No represented active bullpen members.</p>}
    </section>
    <section><h2>Club relief workload</h2>
      <table><thead><tr>{['Window', 'Appearances', 'Pitches', 'Outs'].map(label => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead>
        <tbody>{Object.values(data.competitive_workload.windows || {}).map(window =>
          <tr key={window.start}><th scope="row">{window.start} – {window.through}</th>
            {['appearances', 'pitches', 'outs'].map(key => <td key={key} className="p-2">{metric(window[key])}</td>)}
          </tr>)}</tbody>
      </table>
    </section>
    <HistoricalChanges row={data.what_changed} team={team} />
    <p><Link className="underline" to={`/stories?team=${team}&rehearsalRevision=${revision}&rehearsalGeneration=${generation}`}>Inspect editorial observations</Link></p>
    <Link className="underline" to={`/trust?rehearsalRevision=${revision}&rehearsalGeneration=${generation}`}>Inspect evidence for this edition</Link>
  </main>
}
