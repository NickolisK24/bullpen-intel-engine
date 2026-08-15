import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard, getSyncStatus } from '../../utils/api'
import { ProductPageHeader, QuietState, displayDate } from './ProductPrimitives'

function TrustFact({ label, value, note }) {
  if (!value) return null
  return <div className="border-t border-line py-5"><dt className="bos-eyebrow text-chalk500">{label}</dt><dd className="mt-2 font-mono text-sm text-chalk100">{value}</dd>{note && <p className="mt-2 text-xs leading-5 text-chalk500">{note}</p>}</div>
}

export default function ProductDataTrust() {
  const dashboard = useFetch(getBullpenDashboard)
  const sync = useFetch(getSyncStatus)
  const freshness = dashboard.data?.freshness || {}
  const coverage = freshness.slate_coverage || {}
  const roster = dashboard.data?.roster_readiness || dashboard.data?.availability_summary?.roster_readiness || {}
  const represented = coverage.games_fully_ingested != null && coverage.games_final != null
    ? `${coverage.games_fully_ingested} of ${coverage.games_final} games`
    : null
  const current = freshness.is_current === true && freshness.complete_enough_to_publish === true

  return (
    <div className="bos-page bos-page--reading py-8 md:py-10">
      <ProductPageHeader
        eyebrow="Data & Trust"
        title="Data & Trust"
        description={current ? 'Current means the latest completed-game data is included — not real-time, in-game tracking.' : freshness.label || 'The current publication state is shown exactly as served.'}
      />
      <dl className="grid gap-x-8 py-8 md:grid-cols-2 lg:grid-cols-4">
        <TrustFact label="Baseball date" value={displayDate(freshness.reference_date)} note="The baseball date this publication evaluates." />
        <TrustFact label="Data through" value={displayDate(freshness.data_through)} note="Latest completed-game date represented." />
        <TrustFact label="Appearance ledger" value={represented} note="Final games with verified postgame processing." />
        <TrustFact label="Publication" value={current ? 'Current' : 'Delayed or limited'} note={freshness.last_successful_sync ? `Last successful sync ${freshness.last_successful_sync}` : null} />
      </dl>

      {!current && <QuietState title="Publication limited">{freshness.label || 'A current league-wide read is not publishable from the served evidence.'}</QuietState>}

      <section className="border-t border-line py-9">
        <h2 className="font-display text-2xl font-semibold text-chalk100">Completed-game evidence</h2>
        <p className="mt-3 max-w-definition text-sm leading-6 text-chalk500">These domains support current reads. Missing evidence narrows or withholds only the dependent claim.</p>
        <div className="mt-6 divide-y divide-line border-y border-line">
          <div className="grid gap-2 py-4 sm:grid-cols-[1fr_auto_auto]"><span className="text-sm text-chalk200">Completed-game pitching</span><span className="font-mono text-xs text-chalk400">{coverage.validations_passed ? 'Complete' : 'Incomplete'}</span><span className="font-mono text-xs text-chalk500">{represented || 'Coverage unavailable'}</span></div>
          <div className="grid gap-2 py-4 sm:grid-cols-[1fr_auto_auto]"><span className="text-sm text-chalk200">Active roster status</span><span className="font-mono text-xs text-chalk400">{roster.claims_available ? 'Complete' : 'Limited'}</span><span className="font-mono text-xs text-chalk500">{roster.coverage?.teams_covered != null ? `${roster.coverage.teams_covered} of ${roster.coverage.teams_expected} clubs` : 'Coverage unavailable'}</span></div>
          <div className="grid gap-2 py-4 sm:grid-cols-[1fr_auto_auto]"><span className="text-sm text-chalk200">Sync authority</span><span className="font-mono text-xs text-chalk400">{sync.data?.status || freshness.sync_status || 'Unavailable'}</span><span className="font-mono text-xs text-chalk500">{sync.data?.last_successful_sync || freshness.last_successful_sync || 'No timestamp served'}</span></div>
        </div>
      </section>
    </div>
  )
}
