import { Link } from 'react-router-dom'
import {
  DataThroughStamp,
  FreshnessBadge,
  LastSyncLabel,
  StaleDataNotice,
  UnavailableDataState,
} from '../UI'
import { toOperatingStateReadModel } from '../../adapters/operatingStateReadModel'

function limitationKey(value) {
  const normalized = String(value || '').trim().replace(/\s+/g, ' ').toLowerCase()
  if (normalized.includes('availability classifications are workload-based only')) {
    return 'availability-classifications-workload-based-only'
  }
  return normalized
}

function uniqueList(list) {
  const seen = new Set()
  return list.filter(item => {
    const key = limitationKey(item)
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

// The compact card used to filter evidence through an allow-list of six regexes
// and keep only sentences that matched one. Any backend evidence phrased another
// way — including anything newly authored — was deleted before the reader saw
// it, and the reader had no way to know. Density is now a deterministic count
// cap that reads evidence in the order the backend published it and never
// inspects what a sentence says.
const COMPACT_EVIDENCE_LIMIT = 5

function compactEvidenceList(view) {
  return uniqueList(view.evidence).slice(0, COMPACT_EVIDENCE_LIMIT)
}

function compactLimitationList(view, staleWithError) {
  if (view.isUnavailable || staleWithError) return view.limitations

  const compact = []
  const represented = new Set()
  const hasWorkloadBoundary = view.limitations.some(item => (
    /workload-based only/i.test(item) ||
    /manager intent|bullpen phone activity|private medical|unreported injuries|final game-day/i.test(item)
  ))
  if (hasWorkloadBoundary) {
    compact.push('workload-based only; excludes manager intent, bullpen phone activity, private medical availability, unreported injuries, and final game-day decisions.')
    represented.add('workload')
  }

  for (const item of view.limitations) {
    const coveredByWorkload = (
      /workload-based only/i.test(item) ||
      /manager intent|bullpen phone activity|private medical|unreported injuries|final game-day/i.test(item)
    )
    if (coveredByWorkload && represented.has('workload')) continue
    compact.push(item)
  }

  return uniqueList(compact).slice(0, 3)
}

function getTeamContextReadRows(view) {
  return [
    { key: 'cleanOptions', label: 'Clean Options', read: view.cleanOptions },
    { key: 'coverageSafety', label: 'Coverage Safety', read: view.coverageSafety },
    { key: 'workloadConcentration', label: 'Workload Concentration', read: view.workloadConcentration },
    { key: 'starterSupport', label: 'Recent Starter Length', read: view.starterSupportPressure },
  ].filter(row => row.read?.label || row.read?.summary || row.read?.reasons?.length)
}

export function getBullpenOperatingStateView({
  readModel,
  team,
  teamLabel,
  scope,
  scopeLabel,
  context,
  freshness,
  ctaHref,
  ctaLabel,
  density = 'full',
} = {}) {
  const model = readModel || (
    context?.unsupportedFields && Object.prototype.hasOwnProperty.call(context, 'stateLabel')
      ? context
      : toOperatingStateReadModel(
        {
          ...(context && typeof context === 'object' ? context : {}),
          freshness,
          team: team || (teamLabel ? { team_name: teamLabel } : null),
        },
        {
          scope: scope || (teamLabel && teamLabel !== 'League-Wide' ? 'team' : 'league'),
          team,
          cta: ctaHref ? { href: ctaHref, label: ctaLabel } : null,
          density,
        },
      )
  )
  const cta = ctaHref
    ? { href: ctaHref, label: ctaLabel || model.cta?.label || model.ctaLabel || 'Open Bullpen Board' }
    : model.cta

  return {
    ...model,
    scopeLabel: scopeLabel || model.scopeLabel,
    // Backend-authored state copy only; there is no local substitute.
    stateDetail: model.stateDetail || model.stateSummary || null,
    tone: model.tone || model.stateTone,
    cta,
    ctaHref: cta?.href || model.ctaHref || null,
    ctaLabel: cta?.label || model.ctaLabel || 'Open Bullpen Board',
    density: density || model.density,
  }
}

export default function BullpenOperatingStateCard({
  readModel,
  team,
  teamLabel,
  scope,
  scopeLabel,
  context,
  freshness,
  staleWithError = false,
  onRetry,
  ctaHref,
  ctaLabel,
  lastSyncLabel = 'Dashboard read synced',
  density = 'full',
  // Opt-in: the surrounding page already states this team's identity as its own
  // page heading, so the card drops its team-name heading rather than repeating
  // it directly underneath. Only the Team Board passes this. It defaults to
  // false so every other caller — the Dashboard above all — is unchanged, and it
  // is deliberately explicit rather than inferred from scope or density, which
  // are presentation facts and would couple this to the wrong thing.
  titleOwnedByPage = false,
  className = '',
}) {
  const view = getBullpenOperatingStateView({
    readModel,
    team,
    teamLabel,
    scope,
    scopeLabel,
    context,
    freshness,
    ctaHref,
    ctaLabel,
    density,
  })
  const isCompact = density === 'compact'

  if (isCompact) {
    return (
      <CompactBullpenOperatingStateCard
        view={view}
        staleWithError={staleWithError}
        onRetry={onRetry}
        lastSyncLabel={lastSyncLabel}
        titleOwnedByPage={titleOwnedByPage}
        className={className}
      />
    )
  }

  return (
    <article
      data-density="full"
      className={`card p-4 ${className}`}
      style={{
        borderColor: view.tone.borderColor,
        backgroundColor: view.tone.backgroundColor,
      }}
      role="region"
      aria-label={`${view.teamLabel} bullpen operating state`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            {view.scopeLabel}
          </div>
          {!titleOwnedByPage && (
            <h3 className="mt-1 break-words font-display text-2xl leading-tight tracking-wide text-chalk100">
              {view.teamLabel}
            </h3>
          )}
        </div>
        {view.stateLabel && (
          <StateBadge view={view} />
        )}
      </div>

      {view.isUnavailable ? (
        <UnavailableDataState
          title="No current bullpen read available."
          message="BaseballOS will show this card when enough current bullpen context is available."
          onRetry={onRetry}
          className="mt-4 border-dirt/70 bg-field/35"
          titleClassName="font-display text-xl leading-tight tracking-wide text-chalk100"
        />
      ) : (
        <>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <OperatingStateRow
              label="Current Bullpen State"
              title={view.stateLabel}
              body={view.stateLabel ? view.stateDetail : view.stateUnavailableMessage}
            />
            {view.primaryConcern && (
              <OperatingStateRow
                label="Primary Concern"
                title={view.primaryConcern.label}
                body={view.primaryConcern.body}
              />
            )}
            {view.secondaryConcern && (
              <OperatingStateRow
                label="Secondary Concern"
                title={view.secondaryConcern.label}
                body={view.secondaryConcern.body}
              />
            )}
            {view.why && (
              <OperatingStateRow
                label="Why BaseballOS Sees This"
                title={view.why}
              />
            )}
            {getTeamContextReadRows(view).map(row => (
              <OperatingContextReadRow
                key={row.key}
                label={row.label}
                read={row.read}
              />
            ))}
          </div>

          {view.evidence.length > 0 && (
            <section className="mt-4 border-t border-dirt/70 pt-3">
              <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Evidence
              </div>
              <ul className="mt-2 space-y-1.5">
                {view.evidence.map((item, index) => (
                  <li key={`${index}-${item}`} className="text-xs leading-relaxed text-chalk300">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <section className="mt-4 border-t border-dirt/70 pt-3">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Freshness
        </div>
        {staleWithError && (
          <div className="mt-2">
            <StaleDataNotice
              dataThrough={view.freshness?.data_through}
              onRetry={onRetry}
              compact
            />
          </div>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          {view.hasFreshness ? (
            <>
              <FreshnessBadge freshness={view.freshness} />
              <DataThroughStamp
                date={view.freshness?.data_through}
                label="Bullpen data through"
              />
              <LastSyncLabel
                label={lastSyncLabel}
                value={view.freshness?.last_successful_sync}
              />
            </>
          ) : (
            <FreshnessBadge state="unavailable" label="Freshness unavailable" />
          )}
        </div>
        {view.isSample && (
          <p className="mt-2 text-xs leading-relaxed text-chalk500">
            Not live MLB data.
          </p>
        )}
      </section>

      {view.limitations.length > 0 && (
        <section className="mt-4 border-t border-dirt/70 pt-3">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Limitations
          </div>
          <ul className="mt-2 space-y-1.5">
            {view.limitations.map((item, index) => (
              <li key={`${index}-${item}`} className="text-xs leading-relaxed text-chalk400">
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}

      {view.ctaHref && (
        <div className="mt-4 border-t border-dirt/70 pt-3">
          <OperatingStateCta view={view} />
        </div>
      )}
    </article>
  )
}

function CompactBullpenOperatingStateCard({
  view,
  staleWithError,
  onRetry,
  lastSyncLabel,
  titleOwnedByPage = false,
  className = '',
}) {
  const evidence = compactEvidenceList(view)
  const limitations = compactLimitationList(view, staleWithError)

  return (
    <article
      data-density="compact"
      className={`card p-2.5 sm:p-3.5 ${className}`}
      style={{
        borderColor: view.tone.borderColor,
        backgroundColor: view.tone.backgroundColor,
      }}
      role="region"
      aria-label={`${view.teamLabel} bullpen operating state`}
    >
      <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            {view.scopeLabel}
          </div>
          {!titleOwnedByPage && (
            <h3 className="mt-0.5 break-words font-display text-lg leading-tight tracking-wide text-chalk100 sm:text-xl">
              {view.teamLabel}
            </h3>
          )}
        </div>
        {view.stateLabel && <StateBadge view={view} compact />}
      </div>

      {view.isUnavailable ? (
        <UnavailableDataState
          title="No current bullpen read available."
          message="BaseballOS will show this card when enough current bullpen context is available."
          onRetry={onRetry}
          className="mt-3 border-dirt/70 bg-field/35 p-3"
          titleClassName="font-display text-lg leading-tight tracking-wide text-chalk100"
          messageClassName="mt-1 text-xs leading-relaxed text-chalk500"
        />
      ) : (
        <>
          <div className="mt-2 text-xs leading-snug text-chalk400">
            {(view.stateLabel ? view.stateDetail : view.stateUnavailableMessage) && (
              <p>
                <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                  Current Bullpen State:
                </span>{' '}
                {view.stateLabel ? view.stateDetail : view.stateUnavailableMessage}
              </p>
            )}
          </div>

          {/* The Why, between State and Evidence. The compact card computed this
              and never rendered it, so Team Board showed State then Evidence with
              the explanation missing. Rendered verbatim from the backend. */}
          {view.why && (
            <p className="mt-2 break-words text-sm leading-snug text-chalk300" data-testid="compact-why">
              {view.why}
            </p>
          )}

          {(view.primaryConcern || view.secondaryConcern) && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {view.primaryConcern && (
                <CompactConcern label="Primary Concern" concern={view.primaryConcern} />
              )}
              {view.secondaryConcern && (
                <CompactConcern label="Secondary Concern" concern={view.secondaryConcern} />
              )}
            </div>
          )}

          <CompactContextReads view={view} />

          {evidence.length > 0 && (
            <section className="mt-2" aria-label="Evidence">
              <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Evidence
              </div>
              <ul className="mt-1 flex flex-col gap-0.5 sm:flex-row sm:flex-wrap sm:gap-1.5">
                {evidence.map((item, index) => (
                  <li
                    key={`${index}-${item}`}
                    className="text-[11px] leading-snug text-chalk300 sm:rounded sm:border sm:border-dirt/70 sm:bg-field/40 sm:px-2 sm:py-1 sm:leading-relaxed"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <section className="mt-2 border-t border-dirt/60 pt-1.5" aria-label="Freshness">
        {staleWithError && (
          <div className="mb-2">
            <StaleDataNotice
              dataThrough={view.freshness?.data_through}
              onRetry={onRetry}
              compact
            />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Freshness
          </span>
          {view.hasFreshness ? (
            <>
              <FreshnessBadge freshness={view.freshness} className="min-h-5 px-1.5 py-0.5 text-[9px] sm:min-h-6 sm:px-2 sm:text-[10px]" />
              <DataThroughStamp
                date={view.freshness?.data_through}
                label="Bullpen data through"
                className="min-h-5 px-1.5 py-0.5 text-[9px] sm:min-h-6 sm:px-2 sm:text-[10px]"
              />
              <LastSyncLabel
                label={lastSyncLabel}
                value={view.freshness?.last_successful_sync}
                className="min-h-5 px-1.5 py-0.5 text-[9px] sm:min-h-6 sm:px-2 sm:text-[10px]"
              />
            </>
          ) : (
            <FreshnessBadge state="unavailable" label="Freshness unavailable" className="min-h-5 px-1.5 py-0.5 text-[9px] sm:min-h-6 sm:px-2 sm:text-[10px]" />
          )}
        </div>
        {view.isSample && (
          <p className="mt-1 text-xs leading-relaxed text-chalk500">
            Not live MLB data.
          </p>
        )}
      </section>

      {limitations.length > 0 && (
        <section className="mt-1.5 text-[11px] leading-snug text-chalk400" aria-label="Limitations">
          <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
            Limitations:
          </span>{' '}
          {limitations.join('; ')}
        </section>
      )}

      {view.ctaHref && (
        <div className="mt-2">
          <OperatingStateCta view={view} compact />
        </div>
      )}
    </article>
  )
}

function StateBadge({ view, compact = false }) {
  return (
    <div
      className={`inline-flex max-w-full items-center gap-2 rounded border font-mono uppercase tracking-widest ${
        compact ? 'min-h-7 px-2.5 py-1 text-[10px]' : 'min-h-8 px-3 py-1.5 text-[11px]'
      }`}
      style={{ borderColor: view.tone.borderColor, color: view.tone.color }}
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: view.tone.dot }} aria-hidden="true" />
      <span className="min-w-0 break-words">Current Bullpen State: {view.stateLabel}</span>
    </div>
  )
}

function CompactConcern({ label, concern }) {
  return (
    <div className="min-w-[10.5rem] flex-1 rounded border border-dirt/70 bg-field/25 px-2.5 py-1">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {label}
      </div>
      {concern.label && (
        <div className="mt-1 break-words font-display text-sm leading-tight tracking-wide text-chalk100">
          {concern.label}
        </div>
      )}
    </div>
  )
}

function CompactContextReads({ view }) {
  const rows = getTeamContextReadRows(view)
  if (rows.length === 0) return null
  return (
    <section className="mt-2 grid gap-1.5 sm:grid-cols-2 2xl:grid-cols-4" aria-label="Bullpen context">
      {rows.map(row => {
        const reasons = Array.isArray(row.read?.reasons)
          ? row.read.reasons.filter(Boolean).slice(0, 2)
          : []

        return (
          <div key={row.key} className="rounded border border-dirt/70 bg-field/25 px-2.5 py-1.5">
            <div className="font-mono text-[9px] uppercase tracking-widest text-chalk500">
              {row.label}
            </div>
            {row.read?.label && (
              <div className="mt-1 break-words font-display text-sm leading-tight tracking-wide text-chalk100">
                {row.read.label}
              </div>
            )}
            {row.read?.summary && (
              <p className="mt-1 text-[11px] leading-snug text-chalk400">
                {row.read.summary}
              </p>
            )}
            {reasons.length > 0 && (
              <div className="mt-1.5">
                <div className="font-mono text-[8px] uppercase tracking-widest text-chalk600">
                  Evidence
                </div>
                <ul className="mt-0.5 space-y-0.5">
                  {reasons.map((item, index) => (
                    <li key={`${index}-${item}`} className="text-[10px] leading-snug text-chalk500">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <ContextReadLink read={row.read} compact />
          </div>
        )
      })}
    </section>
  )
}

function OperatingStateCta({ view, compact = false }) {
  const className = `inline-flex min-h-9 items-center justify-center rounded border border-dirt bg-field/60 font-mono uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber ${
    compact ? 'px-2.5 py-1.5 text-[11px]' : 'px-3 py-2 text-xs'
  }`
  if (String(view.ctaHref).startsWith('#')) {
    return (
      <a href={view.ctaHref} className={className}>
        {view.ctaLabel}
      </a>
    )
  }
  return (
    <Link to={view.ctaHref} className={className}>
      {view.ctaLabel}
    </Link>
  )
}

function focusAnchorTarget(href) {
  if (typeof document === 'undefined' || typeof window === 'undefined') return
  if (!String(href || '').startsWith('#')) return
  const target = document.getElementById(String(href).slice(1))
  if (!target || typeof target.focus !== 'function') return
  window.requestAnimationFrame(() => {
    target.focus({ preventScroll: true })
  })
}

function ContextReadLink({ read, compact = false }) {
  if (!read?.receiptsHref || !read?.receiptsLabel) return null
  return (
    <a
      href={read.receiptsHref}
      onClick={() => focusAnchorTarget(read.receiptsHref)}
      className={`mt-2 inline-flex min-h-8 items-center rounded border border-dirt bg-field/50 font-mono uppercase tracking-wider text-chalk400 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/50 ${
        compact ? 'px-2 py-1 text-[10px]' : 'px-2.5 py-1.5 text-[11px]'
      }`}
    >
      {read.receiptsLabel}
    </a>
  )
}

function OperatingStateRow({ label, title, body }) {
  if (!title && !body) return null
  return (
    <div className="border-t border-dirt/70 pt-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {label}
      </div>
      {title && (
        <div className="mt-1 break-words font-display text-lg leading-tight tracking-wide text-chalk100">
          {title}
        </div>
      )}
      {body && (
        <p className="mt-1 text-xs leading-relaxed text-chalk400">
          {body}
        </p>
      )}
    </div>
  )
}

function OperatingContextReadRow({ label, read }) {
  if (!read?.label && !read?.summary && !read?.reasons?.length) return null
  const reasons = Array.isArray(read.reasons) ? read.reasons.filter(Boolean) : []
  return (
    <div className="border-t border-dirt/70 pt-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
        {label}
      </div>
      {read.label && (
        <div className="mt-1 break-words font-display text-lg leading-tight tracking-wide text-chalk100">
          {read.label}
        </div>
      )}
      {read.summary && (
        <p className="mt-1 text-xs leading-relaxed text-chalk400">
          {read.summary}
        </p>
      )}
      {reasons.length > 0 && (
        <div className="mt-2">
          <div className="font-mono text-[9px] uppercase tracking-widest text-chalk600">
            Evidence
          </div>
          <ul className="mt-1 space-y-1">
            {reasons.map((item, index) => (
              <li key={`${index}-${item}`} className="text-xs leading-relaxed text-chalk400">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
      <ContextReadLink read={read} />
    </div>
  )
}
