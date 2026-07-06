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

function Section({ title, children }) {
  return (
    <section className="rounded border border-dirt bg-field/45 p-3">
      <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">{title}</div>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  )
}

function Sentence({ children }) {
  if (!textValue(children)) return null
  return <p className="font-mono text-sm leading-relaxed text-chalk200">{children}</p>
}

function DataCurrency({ payload }) {
  const freshness = payload?.freshness || {}
  const dataThrough = textValue(payload?.data_through) || textValue(freshness.data_through)
  const freshnessLabel = textValue(freshness.label)

  return (
    <Section title="Roster & Data Currency">
      <Sentence>{payload?.roster_status?.sentence}</Sentence>
      <Sentence>{freshnessLabel}</Sentence>
      {dataThrough && (
        <div className="inline-flex max-w-full items-center gap-2 rounded border border-dirt/70 bg-chalk/30 px-2 py-1 font-mono text-xs text-chalk400">
          <span className="text-chalk600">Data through</span>
          <span className="text-chalk200">{dataThrough}</span>
        </div>
      )}
    </Section>
  )
}

function LastAppearance({ lastAppearance, absenceSentence }) {
  const factSentences = asArray(lastAppearance?.fact_sentences)
  if (!lastAppearance && !textValue(absenceSentence)) return null

  return (
    <Section title="Last Appearance">
      <Sentence>{lastAppearance?.sentence}</Sentence>
      <Sentence>{lastAppearance?.timing_sentence}</Sentence>
      <Sentence>{absenceSentence}</Sentence>
      {factSentences.length > 0 && (
        <ul className="space-y-1">
          {factSentences.map((sentence) => (
            <li key={sentence} className="font-mono text-xs leading-relaxed text-chalk400">
              {sentence}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

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

function RecentAppearances({ lines }) {
  const appearances = asArray(lines)
  if (appearances.length === 0) return null

  return (
    <Section title="Recent Appearances">
      <ul className="divide-y divide-dirt/70">
        {appearances.map((line, index) => {
          const date = textValue(line?.game_date)
          const opponent = appearanceOpponent(line)
          const stats = appearanceStats(line)
          const key = [date, line?.game_pk, line?.id, index].filter(isFilled).join(':')

          return (
            <li key={key} className="py-2 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs">
                {date && <span className="text-chalk200">{date}</span>}
                {opponent && <span className="text-chalk500">{opponent}</span>}
              </div>
              {stats.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5">
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
      </ul>
    </Section>
  )
}

function WorkloadWindow({ window }) {
  if (!window?.sentence && !window?.pitches_sentence) return null
  return (
    <div className="rounded border border-dirt/70 bg-chalk/30 p-2">
      <Sentence>{window.sentence}</Sentence>
      <Sentence>{window.pitches_sentence}</Sentence>
    </div>
  )
}

function RecentWorkload({ workload }) {
  const window7 = workload?.window_7
  const window14 = workload?.window_14
  if (!window7?.sentence && !window7?.pitches_sentence && !window14?.sentence && !window14?.pitches_sentence) {
    return null
  }

  return (
    <Section title="Recent Workload">
      <WorkloadWindow window={window7} />
      <WorkloadWindow window={window14} />
    </Section>
  )
}

export default function RecentWorkPanel({
  pitcherId,
  payload,
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
      <div>
        <div id="recent-work-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
          Recent Work
        </div>
      </div>
      <DataCurrency payload={data} />
      <LastAppearance
        lastAppearance={data?.last_appearance}
        absenceSentence={data?.absence_sentence}
      />
      <RecentAppearances lines={data?.recent_appearances} />
      <RecentWorkload workload={data?.workload} />
    </section>
  )
}
