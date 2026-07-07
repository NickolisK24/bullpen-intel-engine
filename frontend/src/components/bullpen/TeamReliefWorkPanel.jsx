import { useFetch } from '../../hooks/useFetch'
import { getTeamReliefWork } from '../../utils/api'

const asArray = (value) => (Array.isArray(value) ? value : [])
const isFilled = (value) => value !== undefined && value !== null && value !== ''
const textValue = (value) => (typeof value === 'string' && value.trim() ? value : null)

function Section({ title, children, compact = false }) {
  return (
    <section className={`rounded border border-dirt bg-field/45 ${compact ? 'p-2.5' : 'p-3'}`}>
      <div className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">{title}</div>
      <div className={`mt-2 ${compact ? 'space-y-1.5' : 'space-y-2'}`}>{children}</div>
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
    <Section title="Data Currency" compact>
      <Sentence>{label}</Sentence>
    </Section>
  )
}

const displayValue = (value) => (value === undefined || value === null || value === '' ? '--' : value)

export function formatBaseballIpFromOuts(outs) {
  if (!Number.isFinite(outs)) return '--'
  return `${Math.floor(outs / 3)}.${outs % 3}`
}

function inningsValue(appearance) {
  if (Number.isFinite(appearance?.innings_pitched_outs)) {
    return formatBaseballIpFromOuts(appearance.innings_pitched_outs)
  }

  if (!isFilled(appearance?.innings_pitched)) return '--'
  const numericInnings = Number(appearance.innings_pitched)
  if (!Number.isFinite(numericInnings)) return String(appearance.innings_pitched)

  const rawText = String(appearance.innings_pitched)
  if (/^\d+\.[012]$/.test(rawText)) return rawText

  return formatBaseballIpFromOuts(Math.round(numericInnings * 3))
}

function DateSummary({ children }) {
  if (!textValue(children)) return null
  return <span className="font-mono text-sm leading-snug text-chalk100">{children}</span>
}

function AppearanceRow({ appearance }) {
  const status = textValue(appearance?.roster_status_sentence)
  return (
    <li
      className="grid gap-1.5 px-2 py-1.5 text-xs text-chalk300 sm:grid-cols-[minmax(9rem,1.5fr)_repeat(6,minmax(2.25rem,auto))_minmax(8rem,1fr)] sm:items-center"
      title={textValue(appearance?.sentence) || undefined}
    >
      <span className="font-mono text-chalk200">{displayValue(appearance?.pitcher_full_name)}</span>
      <span className="font-mono"><span className="text-chalk600">IP </span>{inningsValue(appearance)}</span>
      <span className="font-mono"><span className="text-chalk600">P </span>{displayValue(appearance?.pitches_thrown)}</span>
      <span className="font-mono"><span className="text-chalk600">K </span>{displayValue(appearance?.strikeouts)}</span>
      <span className="font-mono"><span className="text-chalk600">BB </span>{displayValue(appearance?.walks)}</span>
      <span className="font-mono"><span className="text-chalk600">H </span>{displayValue(appearance?.hits_allowed)}</span>
      <span className="font-mono"><span className="text-chalk600">R </span>{displayValue(appearance?.runs_allowed)}</span>
      {status && (
        <span className="font-mono text-[11px] leading-snug text-chalk500 sm:text-right">
          {status}
        </span>
      )}
    </li>
  )
}

function ReliefWorkByDate({ groups, absenceSentence }) {
  const dateGroups = asArray(groups)
  const hasAbsence = Boolean(textValue(absenceSentence))
  if (dateGroups.length === 0 && !hasAbsence) return null

  return (
    <Section title="Relief Work by Date" compact>
      <Sentence>{absenceSentence}</Sentence>
      {dateGroups.map((group, groupIndex) => (
        <details
          key={`${group?.game_date || 'group'}:${groupIndex}`}
          className="overflow-hidden rounded border border-dirt/70 bg-chalk/20"
          aria-label={textValue(group?.sentence) || `Relief work date ${groupIndex + 1}`}
          open={groupIndex === 0}
        >
          <summary
            className="cursor-pointer list-none border-l-2 border-l-amber/40 bg-dugout/70 px-3 py-2.5 marker:hidden transition-colors hover:bg-dugout focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/50"
            data-testid="team-relief-date-summary"
          >
            <DateSummary>{group?.sentence}</DateSummary>
          </summary>
          {asArray(group?.appearances).length > 0 && (
            <ul className="divide-y divide-dirt/60 border-t border-dirt/60">
              {asArray(group.appearances).map((appearance, index) => (
                <AppearanceRow
                  key={`${appearance?.pitcher_id || 'pitcher'}:${appearance?.game_date || 'date'}:${index}`}
                  appearance={appearance}
                />
              ))}
            </ul>
          )}
        </details>
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
    <div className="rounded border border-dirt/60 bg-chalk/25 p-2">
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
    <Section title="Relief Work Windows" compact>
      <div className="grid gap-2 md:grid-cols-2">
        <WorkWindow value={window7} />
        <WorkWindow value={window14} />
      </div>
    </Section>
  )
}

function PanelShell({ children }) {
  return (
    <section className="space-y-2.5" aria-labelledby="team-relief-work-title">
      <div>
        <div id="team-relief-work-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
          Recent Bullpen Work
        </div>
      </div>
      {children}
    </section>
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
      <PanelShell>
        <section className="rounded border border-dirt bg-field/45 p-3">
          <div className="font-mono text-sm text-chalk400">Loading recent bullpen work…</div>
        </section>
      </PanelShell>
    )
  }

  if (error) {
    return (
      <PanelShell>
        <section className="rounded border border-dirt bg-field/45 p-3">
          <div className="font-mono text-sm text-chalk400">Recent bullpen work is unavailable.</div>
        </section>
      </PanelShell>
    )
  }

  return (
    <PanelShell>
      <Sentence>{data?.scope_sentence}</Sentence>
      <DataCurrency payload={data} />
      <ReliefWorkWindows windows={data?.windows} />
      <ReliefWorkByDate
        groups={data?.relief_by_date}
        absenceSentence={data?.absence_sentence}
      />
    </PanelShell>
  )
}
