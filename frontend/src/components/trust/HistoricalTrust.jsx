import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getRehearsalTrust } from '../../utils/api'
import { ErrorState, LoadingPane } from '../UI'

const comparisonLabels = {
  core_comparison_complete: 'Core historical comparison complete',
  season_complete_withholding: 'Season-complete withholding',
  withheld: 'Core historical comparison withheld',
}

function validSource(source) {
  if (!['received', 'invalid', 'failed'].includes(source?.outcome) || !Number.isSafeInteger(source.receipts)
      || source.receipts < 1 || !(source.refusal_reason === null || typeof source.refusal_reason === 'string')) return false
  const first = source.earliest_acquisition
  const last = source.latest_acquisition
  if (first === null && last === null) return source.outcome !== 'received'
  return typeof first === 'string' && typeof last === 'string' && Date.parse(first) <= Date.parse(last)
}

export function HistoricalTransactionReceipt({ source, represented }) {
  let summary = 'This edition has no retained transaction receipt.'
  const scoped = source?.parameters?.sportId === 1 && source.parameters.startDate === represented
    && source.parameters.endDate === represented
  const body = scoped && /^[a-f0-9]{64}$/.test(source.digest) && Number.isFinite(Date.parse(source.acquired_at))
  if (source != null) {
    summary = 'Transaction evidence could not be verified for this date.'
    if (scoped && source.outcome === 'failed' && source.digest === null && source.acquired_at === null
        && Number.isFinite(Date.parse(source.recorded_at))) {
      summary = `Acquisition failed at ${source.recorded_at}.`
    } else if (body && (source.outcome === 'invalid' || (source.outcome === 'received' && source.reason))) {
      summary = `Response withheld. ${source.reason || 'Invalid response'}`
    } else if (body && source.outcome === 'received' && source.reason === null
        && Number.isSafeInteger(source.reported_records) && source.reported_records >= 0
        && Number.isSafeInteger(source.confirmed_transactions) && source.confirmed_transactions >= 0
        && source.confirmed_transactions <= source.reported_records && /^[a-f0-9]{64}$/.test(source.revisions_digest)) {
      summary = `The retained MLB response contained ${source.reported_records} ${source.reported_records === 1 ? 'record' : 'records'}. BaseballOS confirmed ${source.confirmed_transactions}.`
    }
  }
  return <section><h2>MLB transaction evidence for {represented}</h2>
    <p>{summary}</p>
    {body && <details><summary>Retained response</summary>
      <p>Acquired {source.acquired_at}</p>
      <p className="break-all">SHA-256 <code>{source.digest}</code></p>
    </details>}
  </section>
}

export function verifiedHistoricalInventory(page, revision, generation) {
  return page?.status === 'verified_historical_inventory' && page.selection_revision === revision
    && page.trusted_snapshot_id === null && page.current_serving_eligible === false
    && typeof page.generation === 'string' && /^[a-f0-9]{64}$/.test(page.generation)
    && (generation === null || page.generation === generation) && Boolean(page.represented && page.availability_reference)
    && Object.hasOwn(comparisonLabels, page.comparison?.status) && Array.isArray(page.comparison.reason_codes)
    && page.comparison.reason_codes.every(reason => typeof reason === 'string')
    && Array.isArray(page.methods) && page.methods.length > 0
    && page.methods.every(m => ['team', 'pitcher', 'game'].includes(m?.subject) && typeof m.methodology === 'string'
      && m.methodology.length > 0 && Number.isSafeInteger(m.scopes) && m.scopes > 0)
    && Array.isArray(page.sources) && page.sources.length > 0 && page.sources.every(validSource)
}

export default function HistoricalTrust({ revision, generation }) {
  const inventory = useFetch(async options => {
    const page = await getRehearsalTrust(revision, options)
    if (!verifiedHistoricalInventory(page, revision, generation)) throw new Error('The historical evidence inventory could not be verified.')
    return page
  }, [revision, generation])
  if (inventory.loading) return <LoadingPane message="Verifying the historical evidence inventory…" />
  if (inventory.error) return <ErrorState message={inventory.error} onRetry={inventory.refetch} />
  const page = inventory.data
  return <main className="mx-auto max-w-5xl space-y-6 p-6">
    <header>
      <h1 className="font-display text-3xl">Historical evidence · Revision {revision}</h1>
      <p>Baseball data through {page.represented} · Availability reference {page.availability_reference}</p>
      <p>Rehearsal only · {comparisonLabels[page.comparison.status]}</p>
      {page.comparison.reason_codes.map(reason => <p key={reason}>{reason.replaceAll('_', ' ')}</p>)}
      <p className="break-all">Generation <code>{page.generation}</code></p>
    </header>
    <section><h2>Source acquisition</h2>
      <p>Times below describe when source payloads were acquired.</p>
      <ul>{page.sources.map(source => <li key={JSON.stringify([source.outcome, source.refusal_reason])}>
        {source.receipts} {source.outcome} · {source.refusal_reason || 'No recorded refusal'}
        <p>{source.earliest_acquisition ? `${source.earliest_acquisition} – ${source.latest_acquisition}` : 'Payload acquisition time unavailable'}</p>
      </li>)}</ul>
    </section>
    <HistoricalTransactionReceipt source={page.transaction_source} represented={page.represented} />
    <section><h2>Calculation methods</h2>
      <ul>{page.methods.map(method => <li key={method.subject + '/' + method.methodology}>
        <code>{method.methodology}</code> · {method.scopes} {method.subject} records
      </li>)}</ul>
    </section>
    <Link className="underline" to={`/dashboard?rehearsalRevision=${revision}&rehearsalGeneration=${page.generation}`}>Open this League edition</Link>
  </main>
}
