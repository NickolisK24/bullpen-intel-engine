import { useFetch } from '../../hooks/useFetch'
import { getPitcherRecentWork } from '../../utils/api'
import { fmtIP } from '../../utils/formatters'

const APPEARANCE_FLAGS = [
  ['save', 'SV'],
  ['hold', 'HLD'],
  ['blown_save', 'BS'],
  ['win', 'W'],
  ['loss', 'L'],
  ['save_situation', 'SV SIT'],
]

const asArray = (value) => (Array.isArray(value) ? value : [])
const isFilled = (value) => value !== undefined && value !== null && value !== ''
const textValue = (value) => (typeof value === 'string' && value.trim() ? value : null)
const displayValue = (value) => (isFilled(value) ? value : '—')

function appearanceOpponent(line) {
  const opponent = textValue(line?.opponent_abbreviation) || textValue(line?.opponent)
  return opponent ? `vs ${opponent}` : null
}

function appearanceStats(line) {
  const stats = []
  if (isFilled(line?.innings_pitched) || isFilled(line?.innings_pitched_outs)) {
    stats.push(`${fmtIP(line?.innings_pitched, line?.innings_pitched_outs)} IP`)
  }
  if (isFilled(line?.pitches_thrown)) stats.push(`${line.pitches_thrown} P`)
  if (isFilled(line?.strikeouts)) stats.push(`${line.strikeouts} K`)
  if (isFilled(line?.walks)) stats.push(`${line.walks} BB`)
  if (isFilled(line?.hits_allowed)) stats.push(`${line.hits_allowed} H`)
  if (isFilled(line?.runs_allowed)) stats.push(`${line.runs_allowed} R`)
  for (const [field, label] of APPEARANCE_FLAGS) {
    if (line?.[field] === true) stats.push(label)
  }
  return stats
}

function RecentWorkSummary({ workload, inningsLastSevenDays }) {
  const window14 = workload?.window_14
  const facts = [
    {
      label: 'IP / 7d',
      value: isFilled(inningsLastSevenDays) ? fmtIP(inningsLastSevenDays) : '—',
    },
    { label: 'Appearances / 14d', value: displayValue(window14?.appearances) },
    { label: 'Pitches / 14d', value: displayValue(window14?.pitches_total) },
  ]
  const hasSummary = isFilled(inningsLastSevenDays) || window14

  if (!hasSummary) return null

  return (
    <div className="rounded border border-dirt bg-field/45 p-3" aria-labelledby="recent-work-summary-title">
      <h4 id="recent-work-summary-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
        Recent Work Summary
      </h4>
      <dl className="mt-2 grid grid-cols-3 gap-2">
        {facts.map(({ label, value }) => (
          <div key={label} className="min-w-0 border-t border-dirt/70 pt-2">
            <dt className="font-mono text-[10px] leading-tight text-chalk600">{label}</dt>
            <dd className="mt-1 break-words font-mono text-sm font-semibold text-chalk200">{value}</dd>
          </div>
        ))}
      </dl>
      {window14?.pitches_total == null && textValue(window14?.pitches_sentence) && (
        <p className="mt-2 font-mono text-xs leading-relaxed text-chalk400">
          {window14.pitches_sentence}
        </p>
      )}
    </div>
  )
}

function RecentAppearanceLedger({ lines, absenceSentence }) {
  const appearances = asArray(lines)

  return (
    <div className="rounded border border-dirt bg-field/45 p-3" aria-labelledby="recent-appearance-ledger-title">
      <h4 id="recent-appearance-ledger-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
        Recent Appearances
      </h4>
      {appearances.length === 0 ? (
        <p className="mt-2 font-mono text-sm leading-relaxed text-chalk400">
          {textValue(absenceSentence) || 'No recent appearances are represented.'}
        </p>
      ) : (
        <ol className="mt-2 divide-y divide-dirt/70">
          {appearances.map((line, index) => {
            const date = textValue(line?.game_date)
            const opponent = appearanceOpponent(line)
            const stats = appearanceStats(line)
            const key = [date, line?.game_pk, line?.id, index].filter(isFilled).join(':')

            return (
              <li
                key={key}
                className="grid min-w-0 gap-1.5 py-2 first:pt-0 last:pb-0 sm:grid-cols-[minmax(9rem,1fr)_minmax(0,2fr)] sm:items-start sm:gap-3"
              >
                <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 font-mono text-xs">
                  {date && <time dateTime={date} className="text-chalk200">{date}</time>}
                  {opponent && <span className="break-words text-chalk500">{opponent}</span>}
                </div>
                {stats.length > 0 && (
                  <div className="flex min-w-0 flex-wrap gap-1.5 sm:justify-end">
                    {stats.map((stat) => (
                      <span
                        key={stat}
                        className="rounded border border-dirt/70 bg-chalk/30 px-1.5 py-0.5 font-mono text-[11px] text-chalk400"
                      >
                        {stat}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

export default function RecentWorkPanel({
  pitcherId,
  payload,
  inningsLastSevenDays,
  loading: loadingOverride,
  error: errorOverride,
}) {
  const fetched = useFetch(
    () => (payload !== undefined || !isFilled(pitcherId)
      ? Promise.resolve(payload ?? null)
      : getPitcherRecentWork(pitcherId)),
    [pitcherId, payload],
  )
  const data = payload !== undefined ? payload : fetched.data
  const error = errorOverride ?? (payload !== undefined ? null : fetched.error)
  const loading = loadingOverride ?? (error ? false : (payload !== undefined ? false : fetched.loading))

  if (loading) {
    return (
      <section className="rounded border border-dirt bg-field/45 p-3" role="status">
        <div className="font-mono text-sm text-chalk400">Loading recent work…</div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="rounded border border-dirt bg-field/45 p-3" role="status">
        <div className="font-mono text-sm text-chalk400">Recent work is unavailable.</div>
      </section>
    )
  }

  return (
    <section className="space-y-3" aria-labelledby="recent-work-title">
      <h3 id="recent-work-title" className="font-display text-base tracking-wider text-chalk100">
        Recent Work
      </h3>
      <RecentWorkSummary
        workload={data?.workload}
        inningsLastSevenDays={inningsLastSevenDays}
      />
      <RecentAppearanceLedger
        lines={data?.recent_appearances}
        absenceSentence={data?.absence_sentence}
      />
    </section>
  )
}
