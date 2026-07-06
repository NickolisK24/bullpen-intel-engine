import { useFetch } from '../../hooks/useFetch'
import { getTeamReliefWork } from '../../utils/api'

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
  const label = textValue(payload?.freshness?.label)
  if (!label) return null

  return (
    <Section title="Data Currency">
      <Sentence>{label}</Sentence>
    </Section>
  )
}

function ReliefWorkByDate({ groups, absenceSentence }) {
  const dateGroups = asArray(groups)
  const hasAbsence = Boolean(textValue(absenceSentence))
  if (dateGroups.length === 0 && !hasAbsence) return null

  return (
    <Section title="Relief Work by Date">
      <Sentence>{absenceSentence}</Sentence>
      {dateGroups.map((group, groupIndex) => (
        <div
          key={`${group?.game_date || 'group'}:${groupIndex}`}
          className="rounded border border-dirt/70 bg-chalk/30 p-2"
        >
          <Sentence>{group?.sentence}</Sentence>
          {asArray(group?.appearances).length > 0 && (
            <ul className="mt-2 divide-y divide-dirt/70">
              {asArray(group.appearances).map((appearance, index) => (
                <li
                  key={`${appearance?.pitcher_id || 'pitcher'}:${appearance?.game_date || 'date'}:${index}`}
                  className="py-2 first:pt-0 last:pb-0"
                >
                  <Sentence>{appearance?.sentence}</Sentence>
                  <Sentence>{appearance?.roster_status_sentence}</Sentence>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </Section>
  )
}

function WorkWindow({ value }) {
  if (
    !textValue(value?.sentence)
    && !textValue(value?.pitchers_sentence)
    && !textValue(value?.pitches_sentence)
    && !textValue(value?.start_relief_unknown_sentence)
  ) {
    return null
  }

  return (
    <div className="rounded border border-dirt/70 bg-chalk/30 p-2">
      <Sentence>{value?.sentence}</Sentence>
      <Sentence>{value?.pitchers_sentence}</Sentence>
      <Sentence>{value?.pitches_sentence}</Sentence>
      <Sentence>{value?.start_relief_unknown_sentence}</Sentence>
    </div>
  )
}

function ReliefWorkWindows({ windows }) {
  const window7 = windows?.window_7
  const window14 = windows?.window_14
  if (!window7 && !window14) return null

  return (
    <Section title="Relief Work Windows">
      <WorkWindow value={window7} />
      <WorkWindow value={window14} />
    </Section>
  )
}

export default function TeamReliefWorkPanel({
  teamId,
  payload,
  loading: loadingOverride,
  error: errorOverride,
}) {
  const fetched = useFetch(
    () => (payload !== undefined || !isFilled(teamId)
      ? Promise.resolve(payload ?? null)
      : getTeamReliefWork(teamId)),
    [teamId, payload],
  )
  const data = payload !== undefined ? payload : fetched.data
  const error = errorOverride ?? (payload !== undefined ? null : fetched.error)
  const loading = loadingOverride ?? (error ? false : (payload !== undefined ? false : fetched.loading))

  if (loading) {
    return (
      <section className="rounded border border-dirt bg-field/45 p-3">
        <div className="font-mono text-sm text-chalk400">Loading recent bullpen work…</div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="rounded border border-dirt bg-field/45 p-3">
        <div className="font-mono text-sm text-chalk400">Recent bullpen work is unavailable.</div>
      </section>
    )
  }

  return (
    <section className="space-y-3" aria-labelledby="team-relief-work-title">
      <div>
        <div id="team-relief-work-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
          Recent Bullpen Work
        </div>
      </div>
      <Sentence>{data?.scope_sentence}</Sentence>
      <DataCurrency payload={data} />
      <ReliefWorkByDate
        groups={data?.relief_by_date}
        absenceSentence={data?.absence_sentence}
      />
      <ReliefWorkWindows windows={data?.windows} />
    </section>
  )
}
