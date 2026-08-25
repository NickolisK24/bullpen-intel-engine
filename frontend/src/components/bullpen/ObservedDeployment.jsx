import { formatDateOnly } from '../../utils/dateDisplay'

const isRecord = value => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const isCount = value => Number.isInteger(value) && value >= 0
const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null

function coveredCount(numerator, denominator, noun) {
  if (!isCount(numerator) || !isCount(denominator) || denominator === 0) return null
  return `${numerator} of ${denominator} ${noun}`
}

export function getObservedDeploymentView(context) {
  if (!isRecord(context) || context.status !== 'complete') {
    return { state: 'unavailable', facts: [], limitations: [] }
  }

  const profile = isRecord(context.profile) ? context.profile : null
  if (!profile) {
    return {
      state: 'quiet',
      facts: [],
      limitations: [],
      dataThrough: textValue(context.data_through),
      windowDays: isCount(context.window_days) ? context.window_days : null,
    }
  }

  const mostRecentMultiInningDate = textValue(profile.most_recent_multi_inning_date)
  const facts = [
    isCount(profile.saves) ? { key: 'saves', label: 'Saves', value: String(profile.saves) } : null,
    isCount(profile.holds) ? { key: 'holds', label: 'Holds', value: String(profile.holds) } : null,
    {
      key: 'games_finished',
      label: 'Games finished',
      value: coveredCount(
        profile.games_finished,
        profile.appearances_with_games_finished,
        'recorded appearances',
      ),
    },
    {
      key: 'multi_inning',
      label: 'Multi-inning',
      value: coveredCount(
        profile.multi_inning_appearances,
        profile.appearances_with_outs,
        'appearances with recorded outs',
      ),
    },
    {
      key: 'most_recent_multi_inning',
      label: 'Last multi-inning',
      value: mostRecentMultiInningDate
        ? formatDateOnly(mostRecentMultiInningDate, { month: 'short' })
        : null,
      dateTime: mostRecentMultiInningDate,
    },
  ].filter(fact => fact?.value)

  return {
    state: 'available',
    facts,
    limitations: Array.isArray(context.limitations)
      ? context.limitations.filter(textValue)
      : [],
    dataThrough: textValue(context.data_through),
    windowDays: isCount(context.window_days) ? context.window_days : null,
  }
}

export default function ObservedDeployment({ context }) {
  const view = getObservedDeploymentView(context)

  return (
    <section
      className="rounded border border-dirt bg-field/45 p-3 sm:p-4"
      aria-labelledby="pitcher-observed-deployment-title"
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <h3 id="pitcher-observed-deployment-title" className="font-display text-base tracking-wider text-chalk100">
          Observed Deployment
        </h3>
        {(view.windowDays != null || view.dataThrough) && (
          <p className="font-mono text-[11px] text-chalk500">
            {view.windowDays != null && `${view.windowDays}-day window`}
            {view.windowDays != null && view.dataThrough && ' · '}
            {view.dataThrough && (
              <>Through <time dateTime={view.dataThrough}>{formatDateOnly(view.dataThrough, { month: 'short' })}</time></>
            )}
          </p>
        )}
      </div>

      {view.state === 'available' ? (
        <>
          <dl className="mt-3 grid min-w-0 grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
            {view.facts.map(({ key, label, value, dateTime }) => (
              <div key={key} className="min-w-0 border-t border-dirt/70 pt-2">
                <dt className="break-words font-mono text-[10px] leading-tight text-chalk600">{label}</dt>
                <dd className="mt-1 break-words font-mono text-sm font-semibold text-chalk200">
                  {dateTime ? <time dateTime={dateTime}>{value}</time> : value}
                </dd>
              </div>
            ))}
          </dl>
          {view.limitations.length > 0 && (
            <ul className="mt-3 space-y-1 border-t border-dirt/70 pt-2" aria-label="Observed deployment limitations">
              {view.limitations.map((limitation, index) => (
                <li key={`${limitation}-${index}`} className="break-words font-mono text-xs leading-relaxed text-chalk500">
                  {limitation}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : view.state === 'quiet' ? (
        <p className="mt-2 font-mono text-sm leading-relaxed text-chalk400" role="status">
          No relief deployment is represented in this window.
        </p>
      ) : (
        <p className="mt-2 font-mono text-sm leading-relaxed text-chalk400" role="status">
          Observed deployment is unavailable.
        </p>
      )}
    </section>
  )
}
