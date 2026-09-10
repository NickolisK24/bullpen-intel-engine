// Permanent public Share Artifact citation page (Share Cards SC-04 / SC-04B) at
// /share/:publicId. It renders a historical, immutable BaseballOS artifact read
// ENTIRELY from the public Share Artifact API, styled in the BaseballOS design
// system. It never recalculates, never fetches current/live team state, never
// calls internal/admin endpoints, never invokes generation, and never imports a
// deprecated client-side intelligence generator. All baseball meaning and public
// copy come from the immutable artifact; this page only formats and arranges it.
// Missing values are shown honestly — never a fabricated team/state/count/label.

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { formatConfidence, READ_CONFIDENCE_FIELD_LABEL } from '../bullpen/availabilityView'
import {
  DATA_THROUGH_LABEL,
  GENERATED_AT_LABEL,
  PUBLISHED_AT_LABEL,
} from '../../utils/bullpenConcepts'
import {
  SHARE_STATE,
  fetchPublicShareArtifact,
  publicSharePath,
} from '../../utils/publicShareArtifact'
import { formatDateOnly, formatUtcDateTimeEt } from '../../utils/dateDisplay'
import TeamStateArtifactCard from './TeamStateArtifactCard'

const SITE = 'BaseballOS'

// Reader-facing accent per public Team State (Fresh / Stretched / Vulnerable).
// Literal class strings so the Tailwind compiler keeps them.
const STATE_ACCENT = {
  fresh: { border: 'border-pine/50', bg: 'bg-pine/10', dot: 'bg-pine' },
  stretched: { border: 'border-warning/50', bg: 'bg-warning/10', dot: 'bg-warning' },
  vulnerable: { border: 'border-danger/50', bg: 'bg-danger/10', dot: 'bg-danger' },
}
const NEUTRAL_ACCENT = { border: 'border-dirt', bg: 'bg-chalk/20', dot: 'bg-chalk500' }

const SEVERITY_ACCENT = {
  blocking: 'border-danger/40',
  caution: 'border-warning/40',
  informational: 'border-dirt',
}

function accentFor(publicState) {
  return STATE_ACCENT[publicState] || NEUTRAL_ACCENT
}

function fmtDate(value) {
  return formatDateOnly(value, { month: 'long' })
}

function fmtDateTime(value) {
  return formatUtcDateTimeEt(value)
}

function useDocumentMetadata(state, artifact, publicId) {
  useEffect(() => {
    if (typeof document === 'undefined') return
    const indexable = state === SHARE_STATE.OK || state === SHARE_STATE.SUPERSEDED
    const team = artifact?.team?.team_name
    const label = artifact?.artifact_type === 'since_yesterday_change'
      ? 'Since Yesterday'
      : artifact?.team_state?.public_label
    const title =
      indexable && team
        ? `${team} bullpen — ${label || 'Team State'} (${artifact?.product_date || ''}) · ${SITE}`
        : `Shared ${SITE} artifact · ${SITE}`
    document.title = title
    const description = artifact?.copy?.description || `A published ${SITE} bullpen intelligence snapshot.`
    setMeta('description', indexable ? description : `A ${SITE} shared artifact.`)
    const canonicalUrl = `${location.origin}${publicSharePath(publicId)}`
    setLink('canonical', canonicalUrl)
    setMeta('robots', indexable ? 'index,follow' : 'noindex,nofollow')
    setPropertyMeta('og:title', title)
    setPropertyMeta('og:description', indexable ? description : `A ${SITE} shared artifact.`)
    setPropertyMeta('og:url', canonicalUrl)
    setPropertyMeta('og:type', 'article')
    setMeta('twitter:card', 'summary')
    setMeta('twitter:title', title)
    setMeta('twitter:description', indexable ? description : `A ${SITE} shared artifact.`)
  }, [state, artifact, publicId])
}

function setMeta(name, content) {
  let el = document.head.querySelector(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content || '')
}

function setPropertyMeta(property, content) {
  let el = document.head.querySelector(`meta[property="${property}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('property', property)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content || '')
}

function setLink(rel, href) {
  let el = document.head.querySelector(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href || '')
}

export default function PublicShareArtifactPage() {
  const { publicId } = useParams()
  const [result, setResult] = useState({ state: SHARE_STATE.LOADING })

  useEffect(() => {
    let active = true
    setResult({ state: SHARE_STATE.LOADING })
    fetchPublicShareArtifact(publicId).then((next) => {
      if (active) setResult(next)
    })
    return () => {
      active = false
    }
  }, [publicId])

  useDocumentMetadata(result.state, result.artifact, publicId)

  return (
    <section
      className="public-share-artifact mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-8 lg:py-10"
      aria-live="polite"
    >
      {renderState(result, publicId)}
    </section>
  )
}

function renderState(result, publicId) {
  switch (result.state) {
    case SHARE_STATE.LOADING:
      return <LoadingState />
    case SHARE_STATE.OK:
      return <ArtifactView artifact={result.artifact} superseded={false} />
    case SHARE_STATE.SUPERSEDED:
      return <ArtifactView artifact={result.artifact} superseded />
    case SHARE_STATE.WITHDRAWN:
      return <WithdrawnState artifact={result.artifact} />
    case SHARE_STATE.NOT_FOUND:
      return <NotFoundState />
    case SHARE_STATE.INTEGRITY_ERROR:
      return <IntegrityErrorState />
    case SHARE_STATE.API_ERROR:
    default:
      return <ApiErrorState publicId={publicId} />
  }
}

function LoadingState() {
  return (
    <div className="share-skeleton card p-6" role="status" aria-busy="true">
      <div className="motion-safe:animate-pulse space-y-3">
        <div className="h-3 w-40 rounded bg-chalk/40" />
        <div className="h-8 w-64 rounded bg-chalk/40" />
        <div className="h-3 w-full rounded bg-chalk/30" />
        <div className="h-3 w-5/6 rounded bg-chalk/30" />
      </div>
      <p className="sr-only">Loading the shared {SITE} artifact…</p>
    </div>
  )
}

// A. Historical context bar — compact, clearly separate from the artifact.
// The scope label is backend-owned and derived from the artifact's DURABLE
// source-authority discriminator (team-progressive vs league snapshot), never
// inferred client-side. It falls back to the league label for older artifacts that
// predate the scope projection.
function HistoricalContextBar({ dataThrough, publishedAt, scope }) {
  const dataThroughText = fmtDate(dataThrough)
  const publishedText = fmtDateTime(publishedAt)
  const scopeLabel = (scope && scope.display_label) || `Published ${SITE} Snapshot`
  return (
    <div className="mb-4 flex flex-col gap-1 rounded-lg border border-dirt bg-field/40 px-4 py-3 text-xs sm:flex-row sm:items-center sm:justify-between">
      <span className="font-mono uppercase tracking-widest text-chalk500">
        {scopeLabel}
      </span>
      <span className="text-chalk400">
        {dataThroughText ? (
          <>Data through <time dateTime={dataThrough}>{dataThroughText}</time></>
        ) : null}
        {dataThroughText && publishedText ? <span aria-hidden="true"> · </span> : null}
        {publishedText ? (
          <>Published <time dateTime={publishedAt}>{publishedText}</time></>
        ) : null}
      </span>
    </div>
  )
}

export function ArtifactView({ artifact, superseded }) {
  if (!artifact) return <ApiErrorState publicId={null} />
  const freshness = artifact.freshness || {}
  const dataThrough = freshness.data_through || freshness.current_data_through || artifact.product_date
  const scope = artifact.publication_scope || null
  // A team-state-1.2.0 artifact carries a backend-owned card block. When present we
  // render the code-rendered card FIRST, then the historical/immutable explanation
  // and destinations. Older artifacts keep their original stored components verbatim.
  const card = artifact.card || null

  return (
    <article className="share-artifact space-y-5">
      <HistoricalContextBar dataThrough={dataThrough} publishedAt={artifact.published_at} scope={scope} />

      {scope && scope.historical_note ? (
        <p className="text-xs leading-relaxed text-chalk500">{scope.historical_note}</p>
      ) : null}

      {superseded && artifact.superseded ? (
        <aside className="rounded-lg border border-amber/40 bg-amber/10 px-4 py-3 text-sm text-chalk200" role="note">
          <p>
            This original artifact remains unchanged. A newer artifact has since
            superseded it.
          </p>
          {artifact.superseded.replacement_url ? (
            <a
              className="mt-1 inline-block font-medium text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70"
              href={artifact.superseded.replacement_url}
            >
              View the newer artifact
            </a>
          ) : null}
        </aside>
      ) : null}

      {artifact.artifact_type === 'since_yesterday_change'
        ? <SinceYesterdayArtifactBody artifact={artifact} />
        : card ? <TeamStateArtifactCard card={card} /> : <LegacyArtifactBody artifact={artifact} />}

      <ArtifactDestinations routes={artifact.routes || {}} team={artifact.team || {}} />
    </article>
  )
}

function SinceYesterdayArtifactBody({ artifact }) {
  const team = artifact.team || {}
  const change = artifact.change || {}
  const copy = artifact.copy || {}
  const freshness = artifact.freshness || {}
  const evidence = Array.isArray(artifact.evidence) ? artifact.evidence : []
  const delta = change.primary_delta || {}
  return (
    <>
      <section className="card border border-amber/30 p-5 sm:p-6" aria-labelledby="portable-change-title">
        <p className="font-mono text-[11px] uppercase tracking-widest text-metadata-accent">
          {team.team_name || 'Bullpen'} · Published change
        </p>
        <h1 id="portable-change-title" className="mt-2 font-display text-3xl leading-tight tracking-wide text-chalk100 sm:text-4xl">
          {copy.headline || 'Since Yesterday'}
        </h1>
        {copy.summary ? <p className="mt-3 text-base leading-relaxed text-chalk200">{copy.summary}</p> : null}
        {delta.label && delta.previous != null && delta.current != null ? (
          <div className="mt-4 border-t border-dirt pt-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-chalk500">{delta.label}</p>
            <p className="mt-1 font-display text-3xl tracking-wide text-chalk100">
              {delta.previous}<span className="mx-2 text-chalk500" aria-hidden="true">→</span><span className="text-amber">{delta.current}</span>
            </p>
          </div>
        ) : null}
        {copy.why ? <p className="mt-4 text-sm leading-relaxed text-chalk300"><span className="font-semibold text-chalk200">Why it matters: </span>{copy.why}</p> : null}
      </section>

      <section className="card p-5 sm:p-6" aria-labelledby="portable-change-evidence">
        <h2 id="portable-change-evidence" className="section-title text-xl">Evidence behind the change</h2>
        {evidence.length ? (
          <dl className="mt-3 space-y-3">
            {evidence.map((item, index) => (
              <div key={`${item.label || 'evidence'}-${index}`} className="border-t border-dirt pt-3 first:border-t-0 first:pt-0">
                <dt className="text-sm text-chalk300">{item.label || 'Bullpen evidence'}</dt>
                <dd className="mt-1 font-mono text-sm text-chalk100">
                  <span className="sr-only">Previous </span>{item.yesterday ?? '—'}
                  <span className="mx-2 text-chalk500" aria-hidden="true">→</span>
                  <span className="text-amber"><span className="sr-only">Current </span>{item.today ?? '—'}</span>
                </dd>
              </div>
            ))}
          </dl>
        ) : <p className="mt-3 text-sm text-chalk400">No supporting evidence was recorded on this artifact.</p>}
      </section>

      <section className="card p-5 sm:p-6" aria-labelledby="portable-change-dates">
        <h2 id="portable-change-dates" className="section-title text-xl">Compared views</h2>
        <p className="mt-3 text-sm text-chalk300">
          <time dateTime={freshness.previous_data_through}>{fmtDate(freshness.previous_data_through) || 'Previous view'}</time>
          <span className="mx-2 text-chalk500" aria-hidden="true">→</span>
          <time dateTime={freshness.current_data_through}>{fmtDate(freshness.current_data_through) || 'Current view'}</time>
        </p>
      </section>
    </>
  )
}

// The original SC-04B stored components for legacy (1.0.0 / 1.1.0) artifacts —
// hero, evidence receipts, trust & freshness, limitations — rendered verbatim from
// the immutable projected fields so existing artifacts are unchanged.
function LegacyArtifactBody({ artifact }) {
  const team = artifact.team || {}
  const teamState = artifact.team_state || {}
  const trust = artifact.trust || {}
  const copy = artifact.copy || {}
  const freshness = artifact.freshness || {}
  const evidence = Array.isArray(artifact.evidence) ? artifact.evidence : []
  const limitations = Array.isArray(artifact.limitations) ? artifact.limitations : []

  const teamName = team.team_name || 'This team'
  const publicLabel = teamState.public_label || 'Team State'
  const accent = accentFor(teamState.public_state)
  const why = copy.why || teamState.summary
  const dataThrough = freshness.data_through || artifact.product_date

  return (
    <>
      {/* B. Designed artifact hero — immutable projected fields only. */}
      <div
        className={`share-hero card overflow-hidden border ${accent.border}`}
        data-public-state={teamState.public_state || ''}
      >
        <div className={`px-5 pb-5 pt-4 sm:px-6 ${accent.bg}`}>
          <p className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
            {teamName} · Bullpen state
          </p>
          <h1 className="mt-1 flex items-center gap-2 font-display text-4xl leading-none tracking-wide text-chalk100 sm:text-5xl">
            <span className={`inline-block h-3 w-3 shrink-0 rounded-full ${accent.dot}`} aria-hidden="true" />
            <span className="min-w-0 break-words">{publicLabel}</span>
          </h1>
          {why ? <p className="mt-3 max-w-prose text-base leading-relaxed text-chalk200">{why}</p> : null}
        </div>

        <div className="border-t border-dirt px-5 py-3 text-xs text-chalk400 sm:px-6">
          <span className="font-mono uppercase tracking-widest text-chalk500">{teamName}</span>
          {team.team_abbreviation ? <span className="ml-2 text-chalk500">({team.team_abbreviation})</span> : null}
        </div>
      </div>

      {/* D. Evidence receipts. */}
      <section aria-labelledby="share-evidence" className="card p-5 sm:p-6">
        <h2 id="share-evidence" className="section-title text-xl">Evidence behind the read</h2>
        {evidence.length ? (
          <ul className="mt-3 space-y-2">
            {evidence.map((item, index) => (
              <li
                key={item.evidence_id || index}
                className={`rounded-lg border ${SEVERITY_ACCENT[item.severity] || 'border-dirt'} bg-field/40 px-4 py-3`}
              >
                <p className="font-mono text-[11px] uppercase tracking-widest text-chalk500">
                  {item.label || 'Bullpen evidence'}
                  {item.severity ? (
                    <span className="ml-2 normal-case tracking-normal text-chalk600">· {item.severity}</span>
                  ) : null}
                </p>
                {item.detail ? <p className="mt-1 text-sm leading-relaxed text-chalk200">{item.detail}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-chalk400">No evidence receipts were recorded on this artifact.</p>
        )}
      </section>

      {/* E. Trust and freshness — reader-facing language. */}
      <section aria-labelledby="share-trust" className="card p-5 sm:p-6">
        <h2 id="share-trust" className="section-title text-xl">Trust &amp; freshness</h2>
        {copy.trust_line ? <p className="mt-3 text-sm leading-relaxed text-chalk200">{copy.trust_line}</p> : null}
        <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">{READ_CONFIDENCE_FIELD_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">{formatConfidence(trust.confidence)}</dd>
          </div>
          <div>
            <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">{DATA_THROUGH_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">
              {fmtDate(dataThrough) ? <time dateTime={dataThrough}>{fmtDate(dataThrough)}</time> : '—'}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">{PUBLISHED_AT_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">
              {fmtDateTime(artifact.published_at) ? (
                <time dateTime={artifact.published_at}>{fmtDateTime(artifact.published_at)}</time>
              ) : '—'}
            </dd>
          </div>
          <div>
            <dt className="font-mono text-[11px] uppercase tracking-widest text-chalk500">{GENERATED_AT_LABEL}</dt>
            <dd className="mt-0.5 text-chalk200">
              {fmtDateTime(artifact.generated_at) ? (
                <time dateTime={artifact.generated_at}>{fmtDateTime(artifact.generated_at)}</time>
              ) : '—'}
            </dd>
          </div>
        </dl>
      </section>

      {/* F. Limitations — rendered only when a real limitation exists. */}
      {limitations.length ? (
        <section aria-labelledby="share-limitations" className="card p-5 sm:p-6">
          <h2 id="share-limitations" className="section-title text-xl">Limitations</h2>
          <ul className="mt-3 space-y-2">
            {limitations.map((text, index) => (
              <li key={index} className="text-sm leading-relaxed text-chalk300">{text}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  )
}

// G. Where to go next — historical page vs. live surface, clearly distinct. Shared
// by every artifact version so the historical/live boundary and the methodology /
// Data & Trust / current-bullpen destinations are always present.
function ArtifactDestinations({ routes, team }) {
  const teamName = team?.team_name || team?.team_abbreviation || 'team'
  return (
    <nav aria-label="Methodology and destinations" className="card p-5 sm:p-6">
      <h2 className="section-title text-xl">Where to go next</h2>
      <p className="mt-2 text-xs text-chalk500">
        This published observation is historical. The Team Board below shows current context.
      </p>
      <ul className="mt-3 flex flex-col gap-2 text-sm">
        {routes.methodology_url ? (
          <li>
            <a className="text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href={routes.methodology_url}>
              View methodology
            </a>
          </li>
        ) : null}
        {routes.data_trust_url ? (
          <li>
            <a className="text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href={routes.data_trust_url}>
              Review Data &amp; Trust
            </a>
          </li>
        ) : null}
        {routes.team_url ? (
          <li>
            <a className="text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href={routes.team_url}>
              Open current {teamName} bullpen board
            </a>{' '}
            <span className="text-chalk500">— live, not this historical snapshot</span>
          </li>
        ) : null}
      </ul>
    </nav>
  )
}

export function WithdrawnState({ artifact }) {
  return (
    <div className="share-withdrawn card p-6" role="alert">
      <h1 className="font-display text-3xl tracking-wide text-chalk100">This shared artifact has been withdrawn</h1>
      <p className="mt-2 text-sm leading-relaxed text-chalk300">
        {SITE} has withdrawn this artifact
        {artifact?.withdrawn_reason ? ` (${artifact.withdrawn_reason})` : ''}. The original claim is no longer shown.
      </p>
      <a className="mt-4 inline-block text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href="/">
        Return to {SITE}
      </a>
    </div>
  )
}

export function NotFoundState() {
  return (
    <div className="share-not-found card p-6" role="alert">
      <h1 className="font-display text-3xl tracking-wide text-chalk100">Shared artifact not found</h1>
      <p className="mt-2 text-sm leading-relaxed text-chalk300">No published {SITE} artifact exists for this link.</p>
      <a className="mt-4 inline-block text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href="/">
        Return to {SITE}
      </a>
    </div>
  )
}

export function IntegrityErrorState() {
  return (
    <div className="share-integrity-error card p-6" role="alert">
      <h1 className="font-display text-3xl tracking-wide text-chalk100">This shared artifact could not be verified</h1>
      <p className="mt-2 text-sm leading-relaxed text-chalk300">
        {SITE} could not verify the integrity of this artifact, so its content is not shown. Please try again later.
      </p>
      <a className="mt-4 inline-block text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href="/">
        Return to {SITE}
      </a>
    </div>
  )
}

export function ApiErrorState({ publicId }) {
  return (
    <div className="share-api-error card p-6" role="alert">
      <h1 className="font-display text-3xl tracking-wide text-chalk100">Temporarily unavailable</h1>
      <p className="mt-2 text-sm leading-relaxed text-chalk300">This shared {SITE} artifact could not be loaded right now.</p>
      {publicId ? (
        <a className="mt-4 inline-block text-amber underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/70" href={publicSharePath(publicId)}>
          Retry
        </a>
      ) : null}
    </div>
  )
}
