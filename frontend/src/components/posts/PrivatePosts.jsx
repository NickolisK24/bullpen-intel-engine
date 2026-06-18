import { useEffect, useMemo, useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { getBullpenDashboard } from '../../utils/api'
import { ErrorState, LoadingPane, StaleDataNotice } from '../UI'
import {
  PRIVATE_POSTS_PATH,
  PRIVATE_POSTS_ROBOTS,
  flattenTakeDrafts,
  getPrivatePostTakes,
} from './privatePostsView'

export default function PrivatePosts() {
  usePrivateRobotsMeta()
  const dash = useFetch(getBullpenDashboard)

  return (
    <PrivatePostsView
      dashboard={dash.data}
      loading={dash.loading}
      error={dash.error}
      staleWithError={dash.staleWithError}
      onRetry={dash.refetch}
    />
  )
}

function usePrivateRobotsMeta() {
  useEffect(() => {
    const existing = document.querySelector('meta[name="robots"]')
    const previousContent = existing?.getAttribute('content') || null
    const meta = existing || document.createElement('meta')
    meta.setAttribute('name', 'robots')
    meta.setAttribute('content', PRIVATE_POSTS_ROBOTS)
    if (!existing) document.head.appendChild(meta)

    return () => {
      if (existing) {
        if (previousContent) {
          existing.setAttribute('content', previousContent)
        } else {
          existing.removeAttribute('content')
        }
      } else {
        meta.remove()
      }
    }
  }, [])
}

export function PrivatePostsView({
  dashboard,
  loading = false,
  error = null,
  staleWithError = false,
  onRetry,
}) {
  const takes = useMemo(() => getPrivatePostTakes(dashboard), [dashboard])
  const generatedAt = dashboard?.freshness?.data_through
    || dashboard?.freshness?.latest_workload_date
    || dashboard?.freshness?.generated_at
    || dashboard?.generated_at
    || 'latest snapshot'

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-5 lg:p-6" data-private-posts-path={PRIVATE_POSTS_PATH}>
      <header className="mb-5 border-b border-dirt pb-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
              Private Posting Board
            </div>
            <h1 className="mt-1 font-display text-4xl leading-none tracking-wider text-chalk100">
              TONIGHT'S POSTABLE TAKES
            </h1>
          </div>
          <div className="flex flex-wrap gap-2 font-mono text-[11px] text-chalk400">
            <span className="rounded border border-dirt bg-dugout px-2 py-1">{generatedAt}</span>
            <span className="rounded border border-amber/30 bg-amber/5 px-2 py-1 text-amber/80">
              noindex
            </span>
          </div>
        </div>
      </header>

      {loading && !dashboard ? (
        <LoadingPane message="Loading postable takes..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice
              message="Using the last loaded dashboard snapshot because the latest refresh failed."
              onRetry={onRetry}
            />
          )}

          <section className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3" aria-label="Private take summary">
            <MetricTile label="Selected Takes" value={takes.length} />
            <MetricTile
              label="Tension Takes"
              value={takes.filter(take => take.postability.hasTension).length}
            />
            <MetricTile
              label="Superlatives"
              value={takes.filter(take => take.postability.hasSuperlative).length}
            />
          </section>

          {takes.length === 0 ? (
            <div className="card p-5">
              <p className="font-semibold text-chalk100">No four-beat team stories are available in this snapshot.</p>
              <p className="mt-2 text-sm leading-relaxed text-chalk400">
                The private board stays empty instead of inventing a post angle.
              </p>
            </div>
          ) : (
            <section className="space-y-5" aria-label="Postable takes">
              {takes.map((take, index) => (
                <PostableTakeCard key={take.storyId || `${take.abbr}-${index}`} take={take} rank={index + 1} />
              ))}
            </section>
          )}
        </>
      )}
    </div>
  )
}

function MetricTile({ label, value }) {
  return (
    <div className="border border-dirt bg-dugout px-4 py-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</div>
      <div className="mt-1 font-display text-3xl leading-none tracking-wide text-chalk100">{value}</div>
    </div>
  )
}

function PostableTakeCard({ take, rank }) {
  return (
    <article className="card p-4 sm:p-5" data-team={take.abbr} data-postability-score={take.postability.score}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded border border-amber/30 bg-amber/10 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-amber">
              #{rank} {take.abbr}
            </span>
            <span className="rounded border border-dirt bg-field/70 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
              {take.ruleLabel || take.ruleKey}
            </span>
            <span className="rounded border border-dirt bg-field/70 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
              Score {take.postability.score}
            </span>
          </div>
          <h2 className="mt-3 font-display text-3xl leading-tight tracking-wide text-chalk100">
            {take.signal}
          </h2>
          <p className="mt-2 max-w-4xl text-sm leading-relaxed text-chalk400">{take.suggestedAudience}</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)]">
        <TakeInternals take={take} />
        <DraftPanel take={take} />
      </div>
    </article>
  )
}

function TakeInternals({ take }) {
  return (
    <section className="border border-dirt bg-field/50 p-3" aria-label={`${take.abbr} story internals`}>
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">Story Authority</div>
      <dl className="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2 lg:grid-cols-1">
        <KeyValue label="Story ID" value={take.storyId || 'n/a'} />
        <KeyValue label="Rule" value={take.ruleKey || 'n/a'} />
        <KeyValue label="Lead" value={take.postability.leadDimension || 'n/a'} />
        <KeyValue label="Lead Score" value={Math.round(take.postability.leadScore || 0)} />
      </dl>

      <div className="mt-4 font-mono text-[10px] uppercase tracking-widest text-chalk600">Rationale</div>
      <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-chalk400">
        {take.postability.rationale.length > 0 ? (
          take.postability.rationale.map(item => <li key={item}>{item}</li>)
        ) : (
          <li>Neutral read; ranked below tension and superlative stories.</li>
        )}
      </ul>

      <div className="mt-4 font-mono text-[10px] uppercase tracking-widest text-chalk600">Raw Numbers</div>
      <div className="mt-2 space-y-2">
        {take.facts.items.map(fact => (
          <div key={`${fact.key}-${fact.value}`} className="border-l border-dirt pl-2">
            <div className="text-xs font-semibold text-chalk200">{fact.value}</div>
            <div className="mt-0.5 font-mono text-[10px] text-chalk600">{fact.source}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function KeyValue({ label, value }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</dt>
      <dd className="mt-0.5 break-words font-mono text-xs text-chalk300">{value}</dd>
    </div>
  )
}

function DraftPanel({ take }) {
  return (
    <section className="grid grid-cols-1 gap-3" aria-label={`${take.abbr} post drafts`}>
      {flattenTakeDrafts(take).map(draft => (
        <DraftCard key={draft.label} draft={draft} />
      ))}
    </section>
  )
}

function DraftCard({ draft }) {
  const [copied, setCopied] = useState(false)
  const text = draft.text || draft.lead
  const handleCopy = async () => {
    if (!navigator?.clipboard?.writeText) return
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1200)
  }

  return (
    <section className="border border-dirt bg-dugout p-3" aria-label={draft.label}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">{draft.label}</div>
          <div className="mt-0.5 text-xs text-chalk500">{draft.audience}</div>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          data-copy-draft={draft.label}
          className="rounded border border-dirt bg-field/70 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {draft.lead && (
        <div className="mt-3 rounded border border-amber/20 bg-amber/5 p-2">
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
            Lead {draft.characterCount}/{280}
          </div>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-chalk200">{draft.lead}</p>
        </div>
      )}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-chalk300">{text}</p>
    </section>
  )
}
