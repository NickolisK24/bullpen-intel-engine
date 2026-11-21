function Chart({ title, caption, rows, empty }) {
  const known = rows.filter(row => Number.isFinite(row.value))
  const max = Math.max(1, ...known.map(row => row.value))
  return (
    <figure className="min-w-0 border-t border-dirt pt-4">
      <figcaption className="font-display text-base text-chalk100">{title}</figcaption>
      {caption && <p className="mt-1 text-xs text-chalk400">{caption}</p>}
      {rows.length ? (
        <ul className="mt-3 space-y-2">
          {rows.map(({ label, value }, index) => (
            <li key={index} className="grid grid-cols-[minmax(6rem,1fr)_1fr_auto] items-center gap-2 font-mono text-xs">
              <span className="text-chalk300">{label}</span>
              <span aria-hidden="true" className="h-1.5 bg-field">
                {Number.isFinite(value) && <span className="block h-full bg-amber" style={{ width: `${100 * value / max}%` }} />}
              </span>
              <span>{value ?? 'Unknown'}</span>
            </li>
          ))}
        </ul>
      ) : <p className="mt-2 text-sm text-chalk400">{empty}</p>}
    </figure>
  )
}

export default function PitcherTrends({ work, deployment, pitches }) {
  const dates = work?.workload_series || []
  const context = deployment?.context
  const entries = context?.entry_inning
  const leverage = context?.leverage
  const distribution = []
  if (entries?.known_appearances > 0) {
    for (const item of entries.by_inning) distribution.push({ label: `Inning ${item.inning}`, value: item.appearances })
  }
  if (leverage?.known_appearances > 0) {
    for (const key of ['low', 'middle', 'high']) distribution.push({ label: `${key} leverage`, value: leverage[key] })
  }
  const pitchRows = (pitches?.months || []).flatMap(month => month.types.length
    ? month.types.map(type => ({
      label: `${month.month} · ${type.type} · ${type.pitches} pitches (${type.mix_percent}%)`,
      value: type.mean_mph,
    }))
    : [{ label: `${month.month} · ${month.verified_outings}/${month.outings} verified outings`, value: null }])
  const movement = deployment?.movement
  const movementRows = []
  for (const window of [movement?.prior_window, movement?.recent_window]) {
    if (!window) continue
    for (const [signal, label, count, known] of [
      ['eighth_or_later_entry', '8th or later', 'eighth_or_later_appearances', 'known_entry_appearances'],
      ['high_recorded_leverage', 'high leverage', 'high_leverage_appearances', 'known_leverage_appearances'],
    ]) {
      if (movement.signals.some(item => item.name === signal && item.status === 'complete')) {
        movementRows.push({ label: `${window.start_date}–${window.through_date} · ${label} (of ${window[known]})`, value: window[count] })
      }
    }
  }
  return (
    <section aria-label="Pitcher trends" className="mt-6 grid min-w-0 gap-5 md:grid-cols-2">
      <Chart title="30-day workload" caption={work?.data_through && [`Pitches per recorded outing through ${work.data_through}`, work.workload_series_note].filter(Boolean).join(' · ')}
        rows={dates.map(p => ({ label: [p.date, p.opponent].filter(Boolean).join(' · '), value: p.pitches }))}
        empty={work?.absence_sentence || 'Outing pitch counts unavailable.'} />
      <Chart title="Season velocity and pitch mix" rows={pitchRows}
        caption={pitches && `Mean release speed (mph) and pitch share in recorded regular-season relief outings through ${pitches.through}. Source: MLB final play-by-play.`}
        empty="No verified season pitch measurements available." />
      <Chart title="Inning and leverage usage" caption={context && `14 days through ${deployment.through}. Known entry innings: ${entries?.known_appearances ?? 0} of ${entries?.appearances ?? 0}. Known leverage: ${leverage?.known_appearances ?? 0} of ${leverage?.appearances ?? 0}.`}
        rows={distribution} empty={deployment?.current_serving_eligible === false ? 'Historical inning and leverage evidence unavailable.' : 'Published inning and leverage evidence unavailable.'} />
      <Chart title="Observed deployment movement" caption={movement?.public_label}
        rows={movementRows} empty={deployment?.current_serving_eligible === false ? 'Two comparable historical seven-day windows are unavailable.' : 'Two comparable published seven-day windows are unavailable.'} />
    </section>
  )
}
