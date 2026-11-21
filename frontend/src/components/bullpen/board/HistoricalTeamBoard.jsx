import HistoricalTransactions from '../../history/HistoricalTransactions'
import HistoricalPitchHand from '../HistoricalPitchHand'
import { Link } from 'react-router-dom'
import { useFetch } from '../../../hooks/useFetch'
import { getRehearsalTeamBoard } from '../../../utils/api'
import { buildRehearsalPitcherHref, buildTeamHistoryHref } from '../../../utils/evidenceLinks'
import { historicalPitcherWorkload } from '../../../utils/appearanceLanguage'
import { historicalRoleMovements, readWorkloadConcentration } from '../../../adapters/teamBoardV2'
import { RoleMovementNote } from './TeamBoardRolesDeployment'
import { PitchContributors } from './TeamBoardWorkloadOverview'
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

export function HistoricalGroupPerformance({ performance, team, through }) {
  const windows = performance?.team === team && performance.through === through ? performance.windows : null
  return <section aria-labelledby="historical-group-performance">
    <h2 id="historical-group-performance">Performance of the dated active bullpen</h2>
    <p>Regular-season relief appearances for this club.</p>
    {[['recent_30', 'Last 30 days'], ['season', 'Season through ' + through]].map(([key, label]) => {
      const facts = windows?.[key]
      const sample = facts?.sample?.through === through ? facts.sample : null
      const metrics = sample ? Object.entries(facts).filter(([metric, field]) =>
        metric !== 'sample' && field?.label && field.value != null) : []
      return <div key={key} className="mt-3">
        <h3>{label}</h3>
        {sample?.value && <p>{sample.value}</p>}
        {metrics.length ? <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {metrics.map(([metric, field]) => <div key={metric}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
        </dl> : <p>No qualified performance metrics for this window.</p>}
      </div>
    })}
  </section>
}

export function HistoricalRosterListings({ roster, listings, team, through }) {
  const covered = roster?.team === team && roster.represented === through
    && Number.isSafeInteger(roster.active_listed) && Number.isSafeInteger(roster.forty_man_listed)
    && roster.active_listed >= 0 && roster.forty_man_listed >= 0
    && Array.isArray(roster.forty_man_listed_outside_active)
    && roster.forty_man_listed_outside_active.length <= roster.forty_man_listed
  const active = listings?.active, outside = listings?.forty_man_only
  const validRow = row => Number.isSafeInteger(row?.mlb_id) && row.mlb_id > 0
    && (row.name === null || (typeof row.name === 'string' && row.name.trim().length > 0))
  const listsCovered = covered && Array.isArray(active) && Array.isArray(outside)
    && active.length === roster.active_listed && outside.length === roster.forty_man_listed_outside_active.length
    && [...active, ...outside].every(validRow)
    && new Set([...active, ...outside].map(row => row.mlb_id)).size === active.length + outside.length
    && outside.every((row, index) => row.mlb_id === roster.forty_man_listed_outside_active[index])
  return <section aria-labelledby="historical-roster-listings">
    <h2 id="historical-roster-listings">Pitchers on MLB roster lists</h2>
    {covered ? <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <div><dt>Active list</dt><dd>{roster.active_listed}</dd></div>
      <div><dt>40-man list</dt><dd>{roster.forty_man_listed}</dd></div>
      <div><dt>Listed on the 40-man roster only</dt><dd>{roster.forty_man_listed_outside_active.length}</dd></div>
    </dl> : <p>Roster comparison unavailable for this date.</p>}
    {listsCovered && <details><summary>Pitchers listed for {through}</summary>
      {[[active, 'Active roster'], [outside, '40-man roster only']].map(([rows, title]) => <div key={title}>
        <h3>{title}</h3>
        {rows.length ? <ul>{rows.map(row => <li key={row.mlb_id}>{row.name || `MLB player ${row.mlb_id}`}</li>)}</ul> : <p>None listed.</p>}
      </div>)}
    </details>}
  </section>
}

export function HistoricalRotation({ rotation, team, through }) {
  const windows = rotation?.team === team && rotation.through === through ? rotation.windows : null
  return <section aria-labelledby="historical-rotation">
    <h2 id="historical-rotation">Rotation workload</h2>
    <p>Regular-season games through {through}. Opener and bullpen games are counted separately.</p>
    {[7, 14].map(days => {
      const window = windows?.[days]
      const pressure = window?.gaps && Object.keys(window.gaps).length === 0 ? window.pressure : null
      const covered = Number.isSafeInteger(pressure?.games_in_window) && Number.isSafeInteger(pressure?.games_analyzed)
        && pressure.games_analyzed >= 0 && pressure.games_in_window >= pressure.games_analyzed
      return <div key={days} className="mt-3">
        <h3>Last {days} days</h3>
        {!covered ? <p>Rotation evidence unavailable for this window.</p> : <>
          <p>{pressure.games_analyzed} rotation {pressure.games_analyzed === 1 ? 'start' : 'starts'} in{' '}
            {pressure.games_in_window} club {pressure.games_in_window === 1 ? 'game' : 'games'}.</p>
          {pressure.games_analyzed > 0 && <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {[['Short starts', pressure.short_start_count], ['Starter outs', pressure.starter_outs],
              ['Relief outs after rotation starts', pressure.bullpen_outs_required]].map(([label, value]) =>
              <div key={label}><dt>{label}</dt><dd>{value ?? 'Unavailable'}</dd></div>)}
          </dl>}
          {pressure.opener_bulk_games > 0 && <p>Opener and bulk-follower games · {pressure.opener_bulk_games}</p>}
          {pressure.bullpen_games > 0 && <p>Bullpen games · {pressure.bullpen_games}</p>}
          {pressure.games_excluded > 0 && <p>Games with incomplete pitching evidence · {pressure.games_excluded}</p>}
        </>}
      </div>
    })}
  </section>
}

export function HistoricalReliefGames({ ledger, through }) {
  const games = ledger?.status === 'verified_games_only' && ledger.through === through && Array.isArray(ledger.games)
    ? ledger.games : null
  const hasGaps = games && [ledger.regular_gaps, ledger.postseason_gaps].some(gaps => Object.keys(gaps || {}).length > 0)
  return <section aria-labelledby="historical-relief-games">
    <h2 id="historical-relief-games">Recent relief games</h2>
    {games?.length ? (
      <table>
        <caption className="sr-only">Verified club relief appearances on the latest five represented appearance dates</caption>
        <thead><tr>{['Date', 'Opponent', 'Appearances', 'IP', 'Pitches'].map(label =>
          <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead>
        <tbody>{games.map(game => <tr key={game.mlb_game_pk}>
          <th scope="row"><a className="underline" href={`https://www.mlb.com/gameday/${game.mlb_game_pk}`}
            aria-label={`MLB game ${game.mlb_game_pk} on ${game.game_date}`}>{game.game_date}</a>
            {games.some(other => other !== game && other.game_date === game.game_date)
              && (game.game_number ? ` · Game ${game.game_number}` : ` · MLB ${game.mlb_game_pk}`)}
          </th>
          <td className="p-2">{game.home_away === 'away' ? 'at' : 'vs.'} {game.opponent_abbreviation}
            {game.scope === 'verified_postseason_finals' && ' · Postseason'}</td>
          <td className="p-2">{game.relief_appearances ?? 'Unavailable'}</td>
          <td className="p-2">{game.innings ?? 'Unavailable'}</td>
          <td className="p-2">{game.pitches_total ?? 'Unavailable'}</td>
        </tr>)}</tbody>
      </table>
    ) : <p>{games ? 'No verified relief games in the retained window.' : 'Relief game evidence unavailable.'}</p>}
    {hasGaps && <p>Some dates have incomplete evidence.</p>}
  </section>
}

export default function HistoricalTeamBoard({ team, revision, generation }) {
  const board = useFetch(async options => verifyHistoricalBoard(
    await getRehearsalTeamBoard(team, revision, options), team, revision, generation,
  ), [team, revision, generation])
  if (board.loading) return <LoadingPane message="Loading historical Team Board…" />
  if (board.error || !board.data) return <ErrorState message={board.error || 'Historical board unavailable.'} onRetry={board.refetch} />
  const data = board.data
  const state = data.team.team_state
  const history = buildTeamHistoryHref(data.team.team_abbreviation)
  const movements = historicalRoleMovements(data.sections?.roles?.value, team, data.data_through)
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
      {data.active_bullpen.length > 0 && <p>Seven-day {data.active_bullpen.every(arm => arm.weekly_workload?.scope === 'competitive_bullpen_workload')
        ? 'regular-season and postseason' : 'regular-season'} bullpen workload across clubs.</p>}
      {data.active_bullpen.length ? <ul>{data.active_bullpen.map(arm => {
        const href = buildRehearsalPitcherHref(arm.public_pitcher_id, revision, generation)
        const label = arm.name || `MLB pitcher ${arm.mlb_id}`
        const week = historicalPitcherWorkload(arm.weekly_workload?.value, data.data_through)
        return <li key={arm.mlb_id}>
          {href ? <Link className="underline" to={href}>{label}</Link> : label}
          <HistoricalPitchHand hand={arm.pitch_hand} className="block" />
          {week ? <p>{week.appearances ?? 'Unknown'} {week.appearances === 1 ? 'appearance' : 'appearances'} · {' '}
            {week.pitches_thrown == null ? 'Pitch count unavailable' : `${week.pitches_thrown} pitches`}</p>
            : <p>Seven-day workload unavailable.</p>}
          <RoleMovementNote movement={movements?.get(arm.mlb_id)} />
        </li>
      })}</ul> : <p>No represented active bullpen members.</p>}
    </section>
    <section><h2>Club relief workload</h2>
      <table><thead><tr>{['Window', 'Appearances', 'Pitches', 'Outs'].map(label => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead>
        <tbody>{Object.values(data.competitive_workload.windows || {}).map(window =>
          <tr key={window.start}><th scope="row">{window.start} – {window.through}</th>
            {['appearances', 'pitches', 'outs'].map(key => <td key={key} className="p-2">{metric(window[key])}</td>)}
          </tr>)}</tbody>
      </table>
      <PitchContributors concentration={readWorkloadConcentration(data.competitive_workload.concentration_7_day)}
        represented={data.data_through} />
    </section>
    <HistoricalGroupPerformance performance={data.active_group_performance} team={team} through={data.data_through} />
    <HistoricalTransactions transactions={data.official_transactions} team={team} through={data.data_through} />
    {data.prior_transaction_days?.length > 0 && <details>
      <summary>Earlier transaction evidence · {data.prior_transaction_days.at(-1).represented}
        {data.prior_transaction_days.length > 1 && ` – ${data.prior_transaction_days[0].represented}`}</summary>
      {data.prior_transaction_days.map(day => <div key={day.generation}>
        <HistoricalTransactions transactions={day} team={team} through={day.represented} />
        <Link className="underline" to={`/trust?rehearsalRevision=${day.selection_revision}&rehearsalGeneration=${day.generation}`}>
          Inspect the {day.represented} edition
        </Link>
      </div>)}
    </details>}
    <HistoricalRosterListings roster={data.roster_depth_evidence} listings={data.roster_listings} team={team} through={data.data_through} />
    <HistoricalRotation rotation={data.sections?.rotation?.value} team={team} through={data.data_through} />
    <HistoricalReliefGames ledger={data.recent_relief_games} through={data.data_through} />
    <HistoricalChanges row={data.what_changed} team={team} />
    {history && <Link className="underline" to={`${history}?rehearsalRevision=${revision}&rehearsalGeneration=${generation}`}>
      Open {data.team.team_name} History
    </Link>}
    <p><Link className="underline" to={`/stories?team=${team}&rehearsalRevision=${revision}&rehearsalGeneration=${generation}`}>Inspect editorial observations</Link></p>
    <Link className="underline" to={`/trust?rehearsalRevision=${revision}&rehearsalGeneration=${generation}`}>Inspect evidence for this edition</Link>
  </main>
}
