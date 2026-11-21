const labels = {
  active_roster_added: 'Added to the active roster',
  active_roster_removed: 'Removed from the active roster',
  relief_appearance: 'Relief appearance',
  new_short_start: 'Short start',
  team_state_changed: 'Team State',
  arm_read_changed: 'Arm read',
  clean_option_count_changed: 'Clean options',
  observed_deployment_changed: 'Observed deployment',
  workload_7_day_changed: 'Seven-day bullpen workload',
  workload_14_day_changed: 'Fourteen-day bullpen workload',
}

const patterns = {
  back_to_back: 'Back-to-back usage',
  three_in_four: 'Three appearances in four days',
  four_in_six: 'Four appearances in six days',
  recent_multi_inning: 'Recent multi-inning outing',
  high_pitch_outing: 'Qualifying high-pitch outing',
}

function eventLabel(kind) {
  if (Object.hasOwn(labels, kind)) return labels[kind]
  for (const [key, label] of Object.entries(patterns)) {
    if (kind === key + '_started') return label + ' began'
    if (kind === key + '_ended') return label + ' ended'
  }
  return null
}

function transition(event) {
  if (event.kind === 'workload_7_day_changed' || event.kind === 'workload_14_day_changed') {
    return ['appearances', 'outs', 'pitches']
      .filter(key => Number.isInteger(event.previous?.[key]) && Number.isInteger(event.current?.[key]))
      .map(key => `${key} ${event.previous[key]} → ${event.current[key]}`).join(' · ')
  }
  if (Number.isInteger(event.previous) && Number.isInteger(event.current)) return `${event.previous} → ${event.current}`
  if (typeof event.previous === 'string' && typeof event.current === 'string') {
    return [event.previous, event.current].map(value => value.replaceAll('_', ' ')).join(' → ')
  }
  return null
}

export default function HistoricalChanges({ row, team }) {
  const comparisons = row.comparisons || []
  const events = (row.events || []).filter(({ event, represented, team: club, citation }) =>
    club === team && represented === row.represented && event?.event_id && eventLabel(event.kind)
    && citation?.input_digest && comparisons.some(({ citation: source }) =>
      source?.input_digest === citation.input_digest && source.facts_digest === citation.facts_digest
      && source.methodology === citation.methodology && source.revision === citation.revision
      && source.subject === citation.subject && source.mlb_id === citation.mlb_id))
  return <section className="my-3">
    <h3 className="font-board font-semibold">What changed</h3>
    {events.length ? <ul>{events.map(({ event, citation }) => {
      const change = transition(event)
      return <li key={event.event_id} className="py-1">
        <details><summary>{eventLabel(event.kind)}
          {event.player && ` · ${event.pitcher_name || 'MLB pitcher ' + event.player}`}
          {change && ` · ${change}`}
        </summary>
          {event.game && <a className="underline" href={`https://www.mlb.com/gameday/${event.game}`}>MLB game {event.game}</a>}
          <p className="break-all">Event {event.event_id}</p>
          <p className="break-all">Comparison source digest {citation.input_digest}</p>
        </details>
      </li>
    })}</ul> : <p>No cited changes available for this revision.</p>}
    {comparisons.some(c => c.status !== 'complete') && <p>Some comparisons have incomplete coverage.</p>}
  </section>
}
