import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthState } from '../../hooks/useAuthState'
import {
  coverageStateLabel,
  fetchOperationsArtifacts,
  fetchOperationsAudits,
  fetchOperationsOverview,
  integrityStateLabel,
  operationalStatusLabel,
  OPERATIONS_LIST_LIMIT,
  SHARE_ARTIFACT_OPERATIONS_PATH,
} from '../../utils/shareArtifactOperations'
import { ErrorState, LoadingPane, SectionHeader } from '../UI'
import { formatAdminDateTime } from '../../utils/adminDateTime'

export const SHARE_ARTIFACT_OPERATIONS_ROBOTS_CONTENT = 'noindex,nofollow'

function fmtValue(value) {
  if (value === null || value === undefined) return '—'
  // Plain string form — identifiers (snapshot ids) must not gain thousands
  // separators, and coverage counts are small integers.
  return String(value)
}

export function Timestamp({ value }) {
  const formatted = formatAdminDateTime(value)
  return <time title={formatted.title || undefined} dateTime={formatted.title || undefined}>{formatted.display}</time>
}

export function useShareArtifactOperationsRobotsMeta() {
  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const existing = document.querySelector('meta[name="robots"]')
    const previousContent = existing?.getAttribute('content') || null
    const meta = existing || document.createElement('meta')
    meta.setAttribute('name', 'robots')
    meta.setAttribute('content', SHARE_ARTIFACT_OPERATIONS_ROBOTS_CONTENT)
    if (!existing) document.head.appendChild(meta)
    return () => {
      if (existing) {
        if (previousContent) existing.setAttribute('content', previousContent)
        else existing.removeAttribute('content')
      } else {
        meta.remove()
      }
    }
  }, [])
}

export default function ShareArtifactOperations() {
  useShareArtifactOperationsRobotsMeta()
  const auth = useAuthState()
  if (auth.loading) return <ShareArtifactOperationsAccessState state="checking" />
  if (!auth.authenticated) return <ShareArtifactOperationsAccessState state="unauthenticated" />
  return <ShareArtifactOperationsController />
}

function useBoundedList(fetcher) {
  const [offset, setOffset] = useState(0)
  const [retryKey, setRetryKey] = useState(0)
  const [state, setState] = useState({ data: null, loading: true, error: null })

  useEffect(() => {
    let active = true
    setState(previous => ({ ...previous, loading: true, error: null }))
    fetcher({ limit: OPERATIONS_LIST_LIMIT, offset })
      .then(data => { if (active) setState({ data, loading: false, error: null }) })
      .catch(error => { if (active) setState(previous => ({ ...previous, loading: false, error })) })
    return () => { active = false }
  }, [offset, retryKey])

  return {
    ...state,
    offset,
    onPage: next => setOffset(value => Math.max(0, next ? value + OPERATIONS_LIST_LIMIT : value - OPERATIONS_LIST_LIMIT)),
    onRetry: () => setRetryKey(value => value + 1),
  }
}

function ShareArtifactOperationsController() {
  const [overview, setOverview] = useState({ data: null, loading: true, error: null })
  const [overviewRetry, setOverviewRetry] = useState(0)

  useEffect(() => {
    let active = true
    setOverview(previous => ({ ...previous, loading: true, error: null }))
    fetchOperationsOverview()
      .then(data => { if (active) setOverview({ data, loading: false, error: null }) })
      .catch(error => { if (active) setOverview(previous => ({ ...previous, loading: false, error })) })
    return () => { active = false }
  }, [overviewRetry])

  const artifacts = useBoundedList(params => fetchOperationsArtifacts(params))
  const audits = useBoundedList(params => fetchOperationsAudits(params))

  return (
    <ShareArtifactOperationsView
      overview={overview}
      artifacts={artifacts}
      audits={audits}
      onRetry={() => setOverviewRetry(value => value + 1)}
      onArtifactsPage={artifacts.onPage}
      onAuditsPage={audits.onPage}
    />
  )
}

export function ShareArtifactOperationsAccessState({ state = 'unauthenticated' }) {
  const checking = state === 'checking'
  const forbidden = state === 'forbidden'
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-3xl items-center p-4 sm:p-6" data-operations-access={state}>
      <div className="w-full border border-dirt bg-dugout p-5">
        {checking ? (
          <LoadingPane message="Checking access..." />
        ) : (
          <>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Internal operations</div>
            <h1 className="mt-2 font-display text-3xl leading-none tracking-wider text-chalk100">Access Restricted</h1>
            <p className="mt-3 text-sm leading-relaxed text-chalk400">
              {forbidden
                ? 'This account is not authorized to view Share Artifact operations.'
                : 'Sign in with an authorized account to view Share Artifact operations.'}
            </p>
            {!forbidden && (
              <Link
                to={`/signin?next=${encodeURIComponent(SHARE_ARTIFACT_OPERATIONS_PATH)}`}
                className="mt-4 inline-flex border border-amber/40 bg-amber/10 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-amber"
              >
                Sign in
              </Link>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export function ShareArtifactOperationsView({
  overview = { data: null, loading: true, error: null },
  artifacts = { data: null, loading: true, error: null },
  audits = { data: null, loading: true, error: null },
  onRetry = () => {},
  onArtifactsPage = () => {},
  onAuditsPage = () => {},
}) {
  const authError = overview.error || artifacts.error || audits.error
  if (authError?.status === 401) return <ShareArtifactOperationsAccessState state="unauthenticated" />
  if (authError?.status === 403) return <ShareArtifactOperationsAccessState state="forbidden" />

  const data = overview.data
  const lastActivity = audits.data?.audits?.[0]?.created_at || null

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8" data-operations-dashboard>
      <h1 className="sr-only">Share Artifact Operations</h1>
      <SectionHeader title="Share Artifact Operations" subtitle="Internal, read-only view of immutable Team State generation health" />

      {overview.loading && !data ? (
        <LoadingPane message="Loading Share Artifact operations..." />
      ) : overview.error ? (
        <div>
          <ErrorState message="Share Artifact operations are unavailable." />
          <button type="button" onClick={onRetry} className="mt-3 border border-amber/40 px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-amber">Retry</button>
        </div>
      ) : data ? (
        <>
          <OperationsHeader data={data} lastActivity={lastActivity} />
          {data.status === 'unavailable' ? (
            <div className="mb-5 border border-dirt bg-dugout p-5 text-sm leading-relaxed text-chalk400">
              No trusted published snapshot is available, so operational coverage cannot be constructed.
              {data.reason ? ` Reason: ${data.reason}.` : ''}
            </div>
          ) : (
            <>
              <CoverageSummary data={data} />
              <TeamCoverageTable teams={data.teams || []} />
            </>
          )}
          <RecentAuditsSection audits={audits} onPage={onAuditsPage} />
          <RecentArtifactsSection artifacts={artifacts} onPage={onArtifactsPage} />
        </>
      ) : null}
    </div>
  )
}

function OperationsHeader({ data, lastActivity }) {
  return (
    <section className="mb-5 border border-dirt bg-dugout p-4" aria-label="Operations status">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Field label="Operational status" value={operationalStatusLabel(data.status)} strong />
        <Field label="Automatic generation" value={data.autogeneration_enabled ? 'Enabled' : 'Disabled'} />
        <Field label="Latest trusted snapshot" value={fmtValue(data.source_snapshot_id)} />
        <Field label="Product date" value={fmtValue(data.product_date)} />
        <Field label="Snapshot published" value={<Timestamp value={data.snapshot_published_at} />} />
        <Field label="Last generation activity" value={<Timestamp value={lastActivity} />} />
      </div>
    </section>
  )
}

function Field({ label, value, strong = false }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</div>
      <div className={`mt-1 ${strong ? 'font-display text-xl text-chalk100' : 'text-sm text-chalk300'}`}>{value}</div>
    </div>
  )
}

function CoverageSummary({ data }) {
  const cells = [
    ['Canonical teams', data.canonical_team_count],
    ['Accounted', data.accounted_team_count],
    ['Generated', data.generated_team_count],
    ['Reused', data.reused_team_count],
    ['Refused', data.refused_team_count],
    ['Failed', data.failed_team_count],
    ['Missing', data.missing_team_count],
    ['Integrity failures', data.integrity_failure_count],
    ['Artifacts (snapshot)', data.artifact_count],
  ]
  return (
    <section className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5" aria-label="Coverage summary">
      {cells.map(([label, value]) => (
        <article key={label} className="border border-dirt bg-dugout p-4">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</div>
          <div className="mt-2 font-display text-3xl text-chalk100">{fmtValue(value)}</div>
        </article>
      ))}
    </section>
  )
}

function TeamCoverageTable({ teams }) {
  return (
    <section className="mb-5 overflow-x-auto border border-dirt bg-dugout p-4" aria-label="Team coverage">
      <h2 className="mb-3 font-display text-lg tracking-wide text-chalk100">Team Coverage</h2>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Coverage outcome for each canonical MLB team for the latest trusted snapshot</caption>
        <thead>
          <tr className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
            <th scope="col" className="py-2 pr-3">Team</th>
            <th scope="col" className="py-2 pr-3">Outcome</th>
            <th scope="col" className="py-2 pr-3">Public ID</th>
            <th scope="col" className="py-2 pr-3">Reason / failure</th>
            <th scope="col" className="py-2 pr-3">Integrity</th>
            <th scope="col" className="py-2 pr-3">Attempted</th>
          </tr>
        </thead>
        <tbody>
          {teams.map(team => (
            <tr key={team.team_id} className="border-t border-dirt/60 text-chalk300" data-team-state={team.state}>
              <th scope="row" className="py-2 pr-3 font-normal text-chalk200">
                {team.team_name || team.team_abbreviation || `Team ${team.team_id}`}
                <span className="ml-1 text-chalk600">#{team.team_id}</span>
              </th>
              <td className="py-2 pr-3">{coverageStateLabel(team.state)}</td>
              <td className="py-2 pr-3 font-mono text-xs">{team.public_id || '—'}</td>
              <td className="py-2 pr-3 font-mono text-xs">{team.reason_code || team.failure_code || '—'}</td>
              <td className="py-2 pr-3">{integrityStateLabel(team.integrity_state)}</td>
              <td className="py-2 pr-3"><Timestamp value={team.attempt_at} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function RecentAuditsSection({ audits, onPage }) {
  return (
    <section className="mb-5 overflow-x-auto border border-dirt bg-dugout p-4" aria-label="Recent generation attempts">
      <h2 className="mb-3 font-display text-lg tracking-wide text-chalk100">Recent Generation Attempts</h2>
      {audits.loading && !audits.data ? (
        <LoadingPane message="Loading generation attempts..." />
      ) : audits.error ? (
        <ErrorState message="Generation attempts are unavailable." />
      ) : (audits.data?.audits || []).length === 0 ? (
        <p className="text-sm text-chalk500">No generation attempts recorded.</p>
      ) : (
        <>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Recent Team State generation audit attempts, newest first</caption>
            <thead>
              <tr className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
                <th scope="col" className="py-2 pr-3">Team</th>
                <th scope="col" className="py-2 pr-3">Outcome</th>
                <th scope="col" className="py-2 pr-3">Snapshot</th>
                <th scope="col" className="py-2 pr-3">Product date</th>
                <th scope="col" className="py-2 pr-3">Actor</th>
                <th scope="col" className="py-2 pr-3">Public ID</th>
                <th scope="col" className="py-2 pr-3">Reason / failure</th>
                <th scope="col" className="py-2 pr-3">When</th>
              </tr>
            </thead>
            <tbody>
              {(audits.data?.audits || []).map(audit => (
                <tr key={audit.id} className="border-t border-dirt/60 text-chalk300" data-audit-outcome={audit.outcome}>
                  <th scope="row" className="py-2 pr-3 font-normal text-chalk200">#{audit.team_id}</th>
                  <td className="py-2 pr-3">{coverageStateLabel(audit.outcome === 'published' ? 'generated' : audit.outcome === 'failed_closed' ? 'failed' : audit.outcome)}</td>
                  <td className="py-2 pr-3">{fmtValue(audit.source_snapshot_id)}</td>
                  <td className="py-2 pr-3">{fmtValue(audit.resolved_product_date)}</td>
                  <td className="py-2 pr-3">{fmtValue(audit.actor)}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{audit.artifact_public_id || '—'}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{audit.reason_code || audit.failure_code || '—'}</td>
                  <td className="py-2 pr-3"><Timestamp value={audit.created_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager offset={audits.offset} count={(audits.data?.audits || []).length} onPage={onPage} label="generation attempts" />
        </>
      )}
    </section>
  )
}

function RecentArtifactsSection({ artifacts, onPage }) {
  return (
    <section className="mb-5 overflow-x-auto border border-dirt bg-dugout p-4" aria-label="Recent artifacts">
      <h2 className="mb-3 font-display text-lg tracking-wide text-chalk100">Recent Artifacts</h2>
      {artifacts.loading && !artifacts.data ? (
        <LoadingPane message="Loading artifacts..." />
      ) : artifacts.error ? (
        <ErrorState message="Artifacts are unavailable." />
      ) : (artifacts.data?.artifacts || []).length === 0 ? (
        <p className="text-sm text-chalk500">No immutable artifacts recorded.</p>
      ) : (
        <>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Recent immutable Share Artifacts, newest first</caption>
            <thead>
              <tr className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
                <th scope="col" className="py-2 pr-3">Public ID</th>
                <th scope="col" className="py-2 pr-3">Type</th>
                <th scope="col" className="py-2 pr-3">Team</th>
                <th scope="col" className="py-2 pr-3">Product date</th>
                <th scope="col" className="py-2 pr-3">Snapshot</th>
                <th scope="col" className="py-2 pr-3">Lifecycle</th>
                <th scope="col" className="py-2 pr-3">Schema</th>
                <th scope="col" className="py-2 pr-3">Render</th>
                <th scope="col" className="py-2 pr-3">Integrity</th>
                <th scope="col" className="py-2 pr-3">Published</th>
              </tr>
            </thead>
            <tbody>
              {(artifacts.data?.artifacts || []).map(artifact => (
                <tr key={artifact.public_id} className="border-t border-dirt/60 text-chalk300" data-lifecycle={artifact.lifecycle_state}>
                  <th scope="row" className="py-2 pr-3 font-mono text-xs font-normal text-chalk200">{artifact.public_id}</th>
                  <td className="py-2 pr-3">{fmtValue(artifact.artifact_type)}</td>
                  <td className="py-2 pr-3">{artifact.team_name || `#${artifact.team_id}`}</td>
                  <td className="py-2 pr-3">{fmtValue(artifact.product_date)}</td>
                  <td className="py-2 pr-3">{fmtValue(artifact.source_snapshot_id)}</td>
                  <td className="py-2 pr-3">{fmtValue(artifact.lifecycle_state)}</td>
                  <td className="py-2 pr-3">{fmtValue(artifact.schema_version)}</td>
                  <td className="py-2 pr-3">{fmtValue(artifact.render_version)}</td>
                  <td className="py-2 pr-3">{integrityStateLabel(artifact.integrity_state)}</td>
                  <td className="py-2 pr-3"><Timestamp value={artifact.published_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager offset={artifacts.offset} count={(artifacts.data?.artifacts || []).length} onPage={onPage} label="artifacts" />
        </>
      )}
    </section>
  )
}

function Pager({ offset, count, onPage, label }) {
  const atStart = offset <= 0
  const atEnd = count < OPERATIONS_LIST_LIMIT
  return (
    <div className="mt-3 flex items-center gap-2" aria-label={`${label} pagination`}>
      <button
        type="button"
        onClick={() => onPage(false)}
        disabled={atStart}
        className="border border-dirt px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk400 disabled:opacity-40"
      >
        Previous
      </button>
      <button
        type="button"
        onClick={() => onPage(true)}
        disabled={atEnd}
        className="border border-dirt px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk400 disabled:opacity-40"
      >
        Next
      </button>
    </div>
  )
}
