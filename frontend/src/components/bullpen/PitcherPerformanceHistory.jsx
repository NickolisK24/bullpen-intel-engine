import { useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { getPitcherPublicationHistory } from '../../utils/api'

const metrics = [
  ['era', 'ERA'], ['whip', 'WHIP'], ['k_bb_percent', 'K−BB%'],
  ['hr9', 'HR per 9 IP'], ['inherited', 'Inherited runners scored'],
]

export function PitcherPerformance({ performance }) {
  return <section aria-label="Individual relief performance" className="border-t border-dirt p-4 sm:p-5">
    <h2 className="font-display text-lg text-chalk100">Individual relief performance</h2>
    {performance ? <>
      <p className="my-2 text-sm text-chalk400">Recorded regular-season relief outings across all clubs. Each rate requires inputs for every outing in its window. K−BB% uses batters faced.</p>
      <table className="w-full text-left text-sm">
        <thead><tr><th scope="col">Metric</th>{['recent', 'season'].map(key => {
          const window = performance[key]
          return <th scope="col" key={key} className="p-2">{key === 'recent' ? 'Last 30 days' : 'Season to date'}
            <span className="block text-xs font-normal">{window.start} – {window.through} · {window.outings} outings</span>
          </th>
        })}</tr></thead>
        <tbody>{metrics.map(([key, label]) => <tr key={key} className="border-t border-dirt">
          <th scope="row">{label}</th>{['recent', 'season'].map(period => {
            const window = performance[period]
            const metric = window.metrics[key]
            return <td key={period} className="p-2 font-mono">{metric.value ?? 'Withheld'}
              {key === 'k_bb_percent' && metric.value != null && '%'}
              <span className="block text-xs text-chalk400">{metric.covered}/{window.outings} with inputs
                {metric.denominator != null && ` · ${metric.denominator} ${metric.unit}`}</span></td>
          })}
        </tr>)}</tbody>
      </table>
      <p className="mt-2 text-xs text-chalk400">Source: BaseballOS appearance ledger. ERA, HR, strikeouts minus walks, and inherited-runner outcomes require matching final box-score evidence. A zero denominator withholds a rate.</p>
    </> : <p className="text-sm text-chalk400">A dated performance sample is unavailable.</p>}
  </section>
}

export function PublicationDays({ days }) {
  return <ol className="mt-3 divide-y divide-dirt">{days.map(({ date, edition, changes }) =>
    <li key={date} className="py-2 text-sm">
      <span className="font-mono">{date}</span>{edition ? <>
        {' · '}{edition.team} · <a href={edition.citation} className="underline">Team State edition · snapshot {edition.snapshot_id}</a>
        <div>Role: {edition.role ?? 'Withheld'} · Arm read: {edition.read ?? 'Withheld'} (reference {edition.reference_date})</div>
        {Object.entries(changes).map(([key, previous]) => <div key={key}>
          {key === 'role' ? 'Role' : 'Arm read'} changed from <a className="underline" href={previous.citation}>{previous.from}</a> to {edition[key]}.
        </div>)}
      </> : <span className="text-chalk400"> · No citable pitcher label for this date.</span>}
    </li>)}</ol>
}

export function PitcherPublicationHistory({ pitcherId, latest }) {
  const [end, setEnd] = useState(latest)
  const { data, loading, error, refetch } = useFetch(
    options => getPitcherPublicationHistory(pitcherId, end, options), [pitcherId, end],
  )
  return <section aria-label="Published role and arm reads" className="border-t border-dirt p-4 sm:p-5">
    <h2 className="font-display text-lg text-chalk100">Published role and arm reads</h2>
    <p className="my-2 text-sm text-chalk400">One week by Team Board data-through date. Changes compare consecutive editions for the same club.</p>
    <label className="text-sm">Week ending <input type="date" className="bg-field text-chalk100" value={end} max={latest}
      onChange={event => { if (event.target.value && event.target.validity.valid) setEnd(event.target.value) }} /></label>
    {error ? <p>History unavailable. <button type="button" className="underline" onClick={refetch}>Retry</button></p>
      : loading || data?.through !== end || String(data?.pitcher_id) !== String(pitcherId)
        ? <p aria-live="polite">Loading published editions…</p> : <PublicationDays days={data.days} />}
  </section>
}
