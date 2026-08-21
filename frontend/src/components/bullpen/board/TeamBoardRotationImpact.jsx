import SectionState from '../../UI/SectionState'
import { SkeletonBlock } from '../../UI/Skeleton'

const textValue = value => typeof value === 'string' && value.trim() ? value.trim() : null
const numberValue = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null

function focusReliefWork(event, targetId) {
  if (typeof document === 'undefined') return
  const target = document.getElementById(targetId)
  if (!target) return
  event.preventDefault()
  target.focus({ preventScroll: true })
  target.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export function getRotationImpactMetrics(rotationImpact) {
  const read = rotationImpact?.read || {}
  const gamesAnalyzed = numberValue(read.games_analyzed)
  const shortStarts = numberValue(read.short_start_count)
  return [
    { key: 'starter-average', label: 'Average starter length', value: numberValue(read.starter_avg_innings), unit: 'IP' },
    {
      key: 'short-starts',
      label: 'Short starts',
      value: shortStarts,
      displayValue: shortStarts != null && gamesAnalyzed != null ? `${shortStarts} of ${gamesAnalyzed}` : shortStarts,
      unit: null,
    },
    { key: 'bullpen-innings', label: 'Bullpen innings covered', value: numberValue(read.bullpen_innings_required), unit: 'IP' },
  ].filter(metric => metric.value != null)
}

function firstLimitation(status, rotationImpact) {
  const read = rotationImpact?.read || {}
  return [
    ...(Array.isArray(status?.limitations) ? status.limitations : []),
    ...(Array.isArray(read.limitations) ? read.limitations : []),
  ].find(value => textValue(value))?.trim() || null
}

function RotationImpactSkeleton() {
  return (
    <section className="foundation-section" aria-labelledby="rotation-impact-title" aria-busy="true" data-testid="rotation-impact-skeleton">
      <h2 id="rotation-impact-title" className="type-section-title">Rotation Impact</h2>
      <span className="sr-only">Loading rotation impact.</span>
      <SkeletonBlock className="mt-row h-5 w-full max-w-2xl" />
      <div className="mt-row grid grid-cols-2 border-y border-dirt tablet:grid-cols-3">
        {[0, 1, 2].map(index => <SkeletonBlock key={index} className="m-panel h-10 w-24 max-w-full" />)}
      </div>
    </section>
  )
}

export default function TeamBoardRotationImpact({ read, loading = false, error = null, onRetry }) {
  if (loading) return <RotationImpactSkeleton />

  const rotationImpact = read?.rotationImpact
  const rotationRead = rotationImpact?.read
  const status = read?.sectionStatus?.rotation_impact
  const statusName = ['available', 'partial', 'unavailable'].includes(status?.status)
    ? status.status
    : 'unavailable'
  const summary = textValue(rotationRead?.summary)
  const metrics = getRotationImpactMetrics(rotationImpact)
  const windowDays = numberValue(rotationRead?.window_days)
  const gamesAnalyzed = numberValue(rotationRead?.games_analyzed)
  const gamesInWindow = numberValue(rotationRead?.games_in_window)
  const representedDate = textValue(rotationRead?.reference_date) || textValue(status?.represented_date)
  const limitation = firstLimitation(status, rotationImpact)
  const handoff = rotationRead?.relief_work_handoff
  const handoffTarget = textValue(handoff?.target)
  const handoffSummary = textValue(handoff?.summary)
  const receiptGames = Array.isArray(handoff?.games) ? handoff.games : []
  const hasFacts = Boolean(summary || metrics.length > 0)

  return (
    <section className="foundation-section" aria-labelledby="rotation-impact-title" data-testid="team-board-rotation-impact">
      <header className="mb-row">
        <h2 id="rotation-impact-title" className="type-section-title">Rotation Impact</h2>
      </header>

      {error ? (
        <SectionState status="error" title="Rotation Impact unavailable" message="Current rotation context could not be loaded." onRetry={onRetry} />
      ) : !read || !rotationImpact || !rotationRead || statusName === 'unavailable' ? (
        <SectionState status="unavailable" title="Rotation Impact unavailable" message="A current backend-authored rotation read is not available." onRetry={!read ? onRetry : undefined} />
      ) : (
        <>
          {summary && <p className="type-compact max-w-3xl text-chalk200">{summary}</p>}

          {metrics.length > 0 && (
            <dl className="mt-row grid grid-cols-2 border-y border-dirt tablet:grid-cols-3" aria-label="Recent rotation support facts">
              {metrics.map(metric => (
                <div key={metric.key} className="min-w-0 border-b border-dirt px-panel py-row last:col-span-2 last:border-b-0 tablet:border-b-0 tablet:border-r tablet:last:col-span-1 tablet:last:border-r-0">
                  <dt className="type-overline break-words">{metric.label}</dt>
                  <dd className="type-data mt-meta text-lg text-chalk100">
                    {metric.displayValue ?? metric.value}{metric.unit ? ` ${metric.unit}` : ''}
                  </dd>
                </div>
              ))}
            </dl>
          )}

          {(windowDays != null || representedDate || gamesAnalyzed != null || gamesInWindow != null) && (
            <p className="type-metadata mt-row">
              {windowDays != null ? `${windowDays}-day window` : null}
              {windowDays != null && (gamesAnalyzed != null || representedDate) ? ' · ' : null}
              {gamesAnalyzed != null
                ? `${gamesAnalyzed}${gamesInWindow != null ? ` of ${gamesInWindow}` : ''} starts analyzed`
                : null}
              {gamesAnalyzed != null && representedDate ? ' · ' : null}
              {representedDate ? <>Through <time dateTime={representedDate}>{representedDate}</time></> : null}
            </p>
          )}

          {handoffTarget && handoffSummary && receiptGames.length > 0 && (
            <a
              href={`#${handoffTarget}`}
              className="mt-row inline-flex min-h-11 items-center text-brand-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-line-focus"
              onClick={event => focusReliefWork(event, handoffTarget)}
            >
              {handoffSummary}
            </a>
          )}

          {statusName === 'partial' && (
            <SectionState status="partial" title="Rotation Impact is partially available" message={limitation || 'Some recent rotation context is unavailable.'} className={hasFacts ? 'mt-row' : ''} />
          )}
          {statusName === 'available' && !hasFacts && (
            <div className="section-state" role="status" data-state="empty">
              <h3 className="type-section-title">No recent rotation context</h3>
              <p className="type-compact mt-meta">The governed rotation read contains no current facts.</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}
