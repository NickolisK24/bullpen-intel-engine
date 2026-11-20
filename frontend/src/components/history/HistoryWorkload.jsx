import { useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { getTeamHistoryPitcher } from '../../utils/api'

function innings(outs) {
  return `${Math.floor(outs / 3)}.${outs % 3}`
}

export function GameContext({ event }) {
  const work = event.workload
  return (
    <article className="border-t border-line-subtle py-3 text-sm text-text-secondary">
      <time dateTime={event.date}>{event.date}</time>
      <strong className="ml-3 text-text-primary">{event.kind === 'off_day' ? 'Scheduled off-day' : 'Final game workload'}</strong>
      {event.extra_innings && <span> · Extra innings</span>}
      {work && <p>{work.short_start && 'Short start · '}Starter {innings(work.starter_outs)} IP · Bullpen {innings(work.bullpen_outs)} IP</p>}
      {event.week && <p>Seven days through {event.date} · {event.week.bullpen_outs == null
        ? 'Bullpen innings unavailable' : `${innings(event.week.bullpen_outs)} bullpen IP`}
        {' · '}{event.week.verified_games}/{event.week.final_games} retained final games verified</p>}
      <div className="flex flex-wrap gap-3">
        {event.game_pks.map(pk => <a key={pk} className="underline" href={`https://www.mlb.com/gameday/${pk}`}>MLB game {pk}</a>)}
      </div>
    </article>
  )
}

function signedChange(current, prior, unit) {
  if (!Number.isFinite(current) || !Number.isFinite(prior)) return ''
  const delta = Math.round((current - prior) * 10) / 10
  return ` (${delta > 0 ? '+' : ''}${delta} ${unit})`
}

export function PitchMonths({ months }) {
  return <ul className="mt-3 space-y-3">{months.map((month, index) => {
    const previous = months[index - 1]
    const adjacent = previous && previous.month.slice(0, 4) === month.month.slice(0, 4)
      && Number(month.month.slice(5)) - Number(previous.month.slice(5)) === 1
    return <li key={month.month}><strong>{month.month}</strong> · {month.verified_outings}/{month.outings} verified outings
      {month.types.length === 0 && <p>Pitch measurements unavailable.</p>}
      <ul>{month.types.map(type => {
        const prior = adjacent && previous.types.find(item => item.type === type.type)
        return <li key={type.type}>{type.type} · {type.pitches} pitches · {type.mean_mph == null ? 'Speed unknown' : `${type.mean_mph} mph`}
          {signedChange(type.mean_mph, prior?.mean_mph, 'mph')} · {type.mix_percent}% mix{signedChange(type.mix_percent, prior?.mix_percent, 'pp')}</li>
      })}</ul></li>
  })}</ul>
}

function PitchHistory({ team, season, pitcherId }) {
  const read = useFetch(options => getTeamHistoryPitcher(team, season, pitcherId, options), [team, season, pitcherId])
  if (read.loading) return <p>Loading pitch history…</p>
  if (read.error) return <p role="status">Pitch history unavailable. <button onClick={read.refetch}>Retry</button></p>
  return <PitchMonths months={read.data.months} />
}

export function PitchHistoryPicker({ team, season, pitchers }) {
  const [selected, setSelected] = useState('')
  return <section className="my-5 border-b border-line-default pb-4 text-sm">
    <h2 className="font-board text-xl font-semibold">Pitcher velocity and mix</h2>
    {pitchers.length ? <>
      <p className="my-2">MLB final play-by-play for this club’s recorded regular-season relief outings. Changes compare the same pitch type with the preceding month. Mix changes are in percentage points (pp).</p>
      <label>Pitcher <select className="bg-field p-2" value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Select a pitcher</option>
        {pitchers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      {selected && <PitchHistory key={selected} team={team} season={season} pitcherId={selected} />}
    </> : <p>No retained relief outings with a verified club assignment.</p>}
  </section>
}
