// Permanent public Share Artifact citation page (Share Cards SC-04) at
// /share/:publicId. It renders a historical, immutable BaseballOS artifact read
// ENTIRELY from the public Share Artifact API. It never recalculates or overwrites
// the artifact, never fetches current/live team state, never calls internal/admin
// endpoints, never invokes generation, and never imports a deprecated client-side
// intelligence generator. Missing values are shown honestly — never filled with a
// fabricated team, state, count, label, or timestamp.

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  SHARE_STATE,
  fetchPublicShareArtifact,
  publicSharePath,
} from '../../utils/publicShareArtifact'

const SITE = 'BaseballOS'

function useDocumentMetadata(state, artifact, publicId) {
  useEffect(() => {
    if (typeof document === 'undefined') return
    const indexable = state === SHARE_STATE.OK || state === SHARE_STATE.SUPERSEDED
    const team = artifact?.team?.team_name
    const label = artifact?.team_state?.status_label
    const title =
      indexable && team
        ? `${team} bullpen — ${label || 'Team State'} (${artifact?.product_date || ''}) · ${SITE}`
        : `Shared BaseballOS artifact · ${SITE}`
    document.title = title
    setMeta('description', indexable ? (artifact?.copy?.summary || `A published ${SITE} bullpen intelligence snapshot.`) : `A ${SITE} shared artifact.`)
    setLink('canonical', `${location.origin}${publicSharePath(publicId)}`)
    // Withdrawn / not-found / error pages must not promote removed or absent claims.
    setMeta('robots', indexable ? 'index,follow' : 'noindex,nofollow')
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
    <section className="public-share-artifact" aria-live="polite">
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
  // Stable skeleton matching the final hierarchy — no fake team/state/counts/times.
  return (
    <div className="share-skeleton" role="status" aria-busy="true">
      <p>Loading the shared BaseballOS artifact…</p>
    </div>
  )
}

function HistoricalLabel({ productDate, publishedAt }) {
  return (
    <p className="share-historical-label">
      Historical snapshot — this is a published {SITE} read
      {productDate ? (
        <>
          {' '}for <time dateTime={productDate}>{productDate}</time>
        </>
      ) : null}
      {publishedAt ? (
        <>
          , published <time dateTime={publishedAt}>{publishedAt}</time>
        </>
      ) : null}
      . It is not a live current read.
    </p>
  )
}

export function ArtifactView({ artifact, superseded }) {
  if (!artifact) return <ApiErrorState publicId={null} />
  const team = artifact.team || {}
  const teamState = artifact.team_state || {}
  const trust = artifact.trust || {}
  const routes = artifact.routes || {}
  const evidence = Array.isArray(artifact.evidence) ? artifact.evidence : []
  const limitations = Array.isArray(artifact.limitations) ? artifact.limitations : []

  return (
    <article className="share-artifact">
      <h1>
        {team.team_name || 'Team'} bullpen — {teamState.status_label || 'Team State'}
      </h1>
      <HistoricalLabel productDate={artifact.product_date} publishedAt={artifact.published_at} />

      {superseded && artifact.superseded ? (
        <aside className="share-superseded-notice" role="note">
          <p>
            This original artifact remains unchanged. A newer artifact has since
            superseded it.
          </p>
          {artifact.superseded.replacement_url ? (
            <a href={artifact.superseded.replacement_url}>View the newer artifact</a>
          ) : null}
        </aside>
      ) : null}

      {/* Artifact hero — rendered from the immutable projected view (presentation only). */}
      <div className="share-hero" data-status-code={teamState.status_code || ''}>
        <p className="share-hero-status">{teamState.status_label || 'Team State'}</p>
        {teamState.summary ? <p className="share-hero-summary">{teamState.summary}</p> : null}
      </div>

      <section aria-labelledby="share-original-read">
        <h2 id="share-original-read">Original read</h2>
        <dl>
          <dt>Team</dt>
          <dd>{team.team_name || '—'} ({team.team_abbreviation || '—'})</dd>
          <dt>State</dt>
          <dd>{teamState.status_label || '—'}</dd>
          <dt>Explanation</dt>
          <dd>{teamState.summary || '—'}</dd>
          <dt>Generated</dt>
          <dd>{artifact.generated_at ? <time dateTime={artifact.generated_at}>{artifact.generated_at}</time> : '—'}</dd>
          <dt>Product date</dt>
          <dd>{artifact.product_date ? <time dateTime={artifact.product_date}>{artifact.product_date}</time> : '—'}</dd>
        </dl>
      </section>

      <section aria-labelledby="share-evidence">
        <h2 id="share-evidence">Evidence</h2>
        {evidence.length ? (
          <ul className="share-evidence-list">
            {evidence.map((item, index) => (
              <li key={item.evidence_id || index}>
                <span className="share-evidence-label">{item.label || item.kind || 'Evidence'}</span>
                {item.detail ? <span className="share-evidence-detail">: {item.detail}</span> : null}
                {item.severity ? <span className="share-evidence-severity"> ({item.severity})</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p>No evidence receipts were recorded on this artifact.</p>
        )}
      </section>

      <section aria-labelledby="share-trust">
        <h2 id="share-trust">Trust &amp; freshness</h2>
        <dl>
          <dt>Confidence</dt>
          <dd>{trust.confidence || '—'}</dd>
          <dt>Data state</dt>
          <dd>{trust.data_state || '—'}</dd>
          <dt>Freshness</dt>
          <dd>{trust.freshness_state || '—'}</dd>
          <dt>Data through</dt>
          <dd>
            {artifact.freshness?.data_through ? (
              <time dateTime={artifact.freshness.data_through}>{artifact.freshness.data_through}</time>
            ) : '—'}
          </dd>
        </dl>
      </section>

      <section aria-labelledby="share-limitations">
        <h2 id="share-limitations">Limitations</h2>
        {limitations.length ? (
          <ul className="share-limitations-list">
            {limitations.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        ) : (
          <p>No limitations were recorded on this artifact.</p>
        )}
      </section>

      <nav aria-label="Methodology and destinations" className="share-destinations">
        <h2>Where to learn more</h2>
        <ul>
          {routes.methodology_url ? <li><a href={routes.methodology_url}>Methodology</a></li> : null}
          {routes.data_trust_url ? <li><a href={routes.data_trust_url}>Data &amp; Trust</a></li> : null}
          {routes.team_url ? (
            <li>
              <a href={routes.team_url}>Current live bullpen surface</a> (the live destination; this page is historical)
            </li>
          ) : null}
        </ul>
      </nav>
    </article>
  )
}

export function WithdrawnState({ artifact }) {
  return (
    <div className="share-withdrawn" role="alert">
      <h1>This shared artifact has been withdrawn</h1>
      <p>
        {SITE} has withdrawn this artifact
        {artifact?.withdrawn_reason ? ` (${artifact.withdrawn_reason})` : ''}. The
        original claim is no longer shown.
      </p>
      <a href="/">Return to {SITE}</a>
    </div>
  )
}

export function NotFoundState() {
  return (
    <div className="share-not-found" role="alert">
      <h1>Shared artifact not found</h1>
      <p>No published {SITE} artifact exists for this link.</p>
      <a href="/">Return to {SITE}</a>
    </div>
  )
}

export function IntegrityErrorState() {
  return (
    <div className="share-integrity-error" role="alert">
      <h1>This shared artifact could not be verified</h1>
      <p>
        {SITE} could not verify the integrity of this artifact, so its content is
        not shown. Please try again later.
      </p>
      <a href="/">Return to {SITE}</a>
    </div>
  )
}

export function ApiErrorState({ publicId }) {
  return (
    <div className="share-api-error" role="alert">
      <h1>Temporarily unavailable</h1>
      <p>This shared {SITE} artifact could not be loaded right now.</p>
      {publicId ? <a href={publicSharePath(publicId)}>Retry</a> : null}
    </div>
  )
}
