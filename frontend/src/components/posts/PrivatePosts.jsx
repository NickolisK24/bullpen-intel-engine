import { useEffect, useMemo, useState } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { useAuthState } from '../../hooks/useAuthState'
import {
  getPrivatePostsDashboard,
  getSlateBriefing,
  getSlateBriefingHistory,
  markSlateBriefingPosted,
} from '../../utils/api'
import { ErrorState, LoadingPane, StaleDataNotice } from '../UI'
import {
  PRIVATE_POSTS_PATH,
  PRIVATE_POSTS_ROBOTS,
  flattenTakeDrafts,
  getPrivatePostTakes,
  defaultSlateCandidateId,
  resolveGeneratedDraftPackage,
  slateCandidateLabel,
} from './privatePostsView'

export default function PrivatePosts() {
  usePrivateRobotsMeta()
  const auth = useAuthState()

  if (auth.loading) {
    return <PrivatePostsAccessState loading />
  }

  if (!auth.authenticated) {
    return <PrivatePostsAccessDenied />
  }

  return <PrivatePostsAuthorized />
}

function PrivatePostsAuthorized() {
  const dash = useFetch(getPrivatePostsDashboard)
  const briefing = useFetch(() => getSlateBriefing({ date: 'tomorrow' }))
  const history = useFetch(() => getSlateBriefingHistory({ limit: 10 }))

  if (isPrivatePostsAccessError(dash.error) && !dash.data) {
    return <PrivatePostsAccessDenied />
  }

  return (
    <PrivatePostsView
      dashboard={dash.data}
      loading={dash.loading}
      error={dash.error}
      staleWithError={dash.staleWithError}
      onRetry={dash.refetch}
      briefing={briefing.data}
      briefingLoading={briefing.loading}
      briefingError={briefing.error}
      onBriefingRetry={briefing.refetch}
      postingHistory={history.data?.posting_records || []}
      onHistoryRefresh={history.refetch}
    />
  )
}

function isPrivatePostsAccessError(error) {
  return /^API (401|403):/.test(String(error || ''))
}

export function PrivatePostsAccessState({ loading = false }) {
  return (
    <div
      className="mx-auto flex min-h-[60vh] max-w-3xl items-center p-4 sm:p-5 lg:p-6"
      data-private-posts-access={loading ? 'checking' : 'denied'}
    >
      <div className="w-full border border-dirt bg-dugout p-5">
        {loading ? (
          <LoadingPane message="Checking access..." />
        ) : (
          <>
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
              Page unavailable
            </div>
            <h1 className="mt-2 font-display text-3xl leading-none tracking-wider text-chalk100">
              Access Restricted
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-chalk400">
              This page is restricted to authorized accounts.
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export function PrivatePostsAccessDenied() {
  return <PrivatePostsAccessState />
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

function getDraftGenerationEndpoint() {
  return typeof import.meta !== 'undefined'
    ? (import.meta.env?.VITE_POST_DRAFT_GENERATION_URL || '').trim()
    : ''
}

async function requestDraftsFromEndpoint(payload) {
  const endpoint = getDraftGenerationEndpoint()
  if (!endpoint) return null
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Draft generation request failed with ${response.status}`)
  }
  return response.json()
}

function useEndpointDraftPackages(takes) {
  const [packagesByStoryId, setPackagesByStoryId] = useState({})

  useEffect(() => {
    const endpoint = getDraftGenerationEndpoint()
    if (!endpoint || takes.length === 0) {
      setPackagesByStoryId({})
      return undefined
    }

    let cancelled = false
    Promise.all(
      takes.map(async take => {
        const draftPackage = await resolveGeneratedDraftPackage(take, {
          requestDrafts: requestDraftsFromEndpoint,
        })
        return [take.storyId || take.abbr, draftPackage]
      }),
    ).then(entries => {
      if (!cancelled) setPackagesByStoryId(Object.fromEntries(entries))
    })

    return () => {
      cancelled = true
    }
  }, [takes])

  return packagesByStoryId
}

export function PrivatePostsView({
  dashboard,
  loading = false,
  error = null,
  staleWithError = false,
  onRetry,
  briefing = null,
  briefingLoading = false,
  briefingError = null,
  onBriefingRetry,
  postingHistory = [],
  onHistoryRefresh,
}) {
  const [activeTab, setActiveTab] = useState('postable-takes')
  const takes = useMemo(() => getPrivatePostTakes(dashboard), [dashboard])
  const endpointDraftPackages = useEndpointDraftPackages(takes)
  const generatedAt = dashboard?.freshness?.data_through
    || dashboard?.freshness?.latest_workload_date
    || dashboard?.freshness?.generated_at
    || dashboard?.generated_at
    || 'latest read'
  const scheduleFreshness = dashboard?.schedule_authority?.freshness || {}
  const scheduleDataThrough = scheduleFreshness.schedule_data_through || 'unavailable'

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
            <span className="rounded border border-dirt bg-dugout px-2 py-1">
              Schedule through {scheduleDataThrough}
            </span>
            <span className="rounded border border-amber/30 bg-amber/5 px-2 py-1 text-amber/80">
              noindex
            </span>
          </div>
        </div>
      </header>

      <nav className="mb-5 flex gap-2" aria-label="Private posting board sections">
        <button type="button" onClick={() => setActiveTab('postable-takes')} data-private-posts-tab="postable-takes" className={`rounded border px-3 py-2 font-mono text-[11px] uppercase tracking-widest ${activeTab === 'postable-takes' ? 'border-amber/50 bg-amber/10 text-amber' : 'border-dirt bg-dugout text-chalk400'}`}>
          Postable Takes
        </button>
        <button type="button" onClick={() => setActiveTab('slate-briefing')} data-private-posts-tab="slate-briefing" className={`rounded border px-3 py-2 font-mono text-[11px] uppercase tracking-widest ${activeTab === 'slate-briefing' ? 'border-amber/50 bg-amber/10 text-amber' : 'border-dirt bg-dugout text-chalk400'}`}>
          Slate Briefing
        </button>
      </nav>

      {activeTab === 'slate-briefing' ? (
        <SlateBriefingPanel
          briefing={briefing}
          loading={briefingLoading}
          error={briefingError}
          onRetry={onBriefingRetry}
          postingHistory={postingHistory}
          onPosted={async () => {
            await Promise.all([onBriefingRetry?.(), onHistoryRefresh?.()])
          }}
        />
      ) : (
        <>
      {loading && !dashboard ? (
        <LoadingPane message="Loading postable takes..." />
      ) : error && !dashboard ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <>
          {staleWithError && (
            <StaleDataNotice
              dataThrough={dashboard?.freshness?.data_through}
              onRetry={onRetry}
            />
          )}

          {scheduleFreshness.is_fresh !== true && (
            <div
              className="mb-5 border border-amber/40 bg-amber/10 px-4 py-3 text-sm text-amber"
              role="status"
              data-schedule-freshness={scheduleFreshness.state || 'unavailable'}
            >
              Schedule data is {scheduleFreshness.state || 'unavailable'} through {scheduleDataThrough}.
              Postable takes are withheld until a fresh schedule refresh completes.
            </div>
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
              <p className="font-semibold text-chalk100">No schedule-cleared team stories are available in this read.</p>
              <p className="mt-2 text-sm leading-relaxed text-chalk400">
                The private board stays empty instead of inventing a post angle.
              </p>
            </div>
          ) : (
            <section className="space-y-5" aria-label="Postable takes">
              {takes.map((take, index) => (
                <PostableTakeCard
                  key={take.storyId || `${take.abbr}-${index}`}
                  take={take}
                  rank={index + 1}
                  draftPackage={endpointDraftPackages[take.storyId || take.abbr] || take.draftPackage}
                />
              ))}
            </section>
          )}
        </>
      )}
        </>
      )}
    </div>
  )
}

export function SlateBriefingPanel({
  briefing,
  loading = false,
  error = null,
  onRetry,
  postingHistory = [],
  onPosted,
}) {
  const [expandedId, setExpandedId] = useState(() => defaultSlateCandidateId(briefing))

  useEffect(() => {
    setExpandedId(defaultSlateCandidateId(briefing))
  }, [briefing?.briefing_date, briefing?.top_recommendation, briefing?.ranked_highest])

  if (loading && !briefing) return <LoadingPane message="Loading slate briefing..." />
  if (error && !briefing) return <ErrorState message={error} onRetry={onRetry} />
  const candidates = briefing?.candidates || []
  return (
    <section aria-label="Slate Briefing" data-slate-briefing-date={briefing?.briefing_date || 'unavailable'}>
      {error && briefing && <StaleDataNotice dataThrough={briefing.briefing_date} onRetry={onRetry} />}
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border border-dirt bg-dugout p-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">Ranked editorial slate</div>
          <h2 className="mt-1 font-display text-3xl tracking-wide text-chalk100">{briefing?.briefing_date || 'Tomorrow'}</h2>
        </div>
        <div className="font-mono text-[11px] text-chalk400">
          {briefing?.has_publishable_candidate ? 'Publishable recommendation available' : 'No publishable story in this slate'}
        </div>
      </div>
      {candidates.length === 0 ? (
        <div className="card p-5" data-slate-empty="true">
          <p className="font-semibold text-chalk100">No games are available for this slate.</p>
          <p className="mt-2 text-sm text-chalk400">The briefing remains empty instead of inventing a matchup.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {candidates.map(candidate => (
            <SlateCandidateCard
              key={candidate.candidate_id}
              candidate={candidate}
              expanded={expandedId === candidate.candidate_id}
              onToggle={() => setExpandedId(expandedId === candidate.candidate_id ? null : candidate.candidate_id)}
              onPosted={onPosted}
            />
          ))}
        </div>
      )}
      <RecentPostingHistory records={postingHistory} />
    </section>
  )
}

function SlateCandidateCard({ candidate, expanded, onToggle, onPosted }) {
  const label = slateCandidateLabel(candidate)
  const featured = candidate.featured_team || {}
  const status = candidate.games || []
  return (
    <article className="card p-4" data-slate-candidate={candidate.candidate_id} data-publishable={String(Boolean(candidate.publishable))}>
      <button type="button" onClick={onToggle} className="w-full text-left" aria-expanded={expanded}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap gap-2">
              <span className={`rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-widest ${candidate.recommended_to_post ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200' : 'border-amber/30 bg-amber/5 text-amber'}`}>{label}</span>
              <span className="rounded border border-dirt bg-field/70 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">#{candidate.rank} · Score {candidate.final_editorial_score}</span>
              {candidate.doubleheader && <span className="rounded border border-dirt px-2 py-1 font-mono text-[10px] text-chalk400">DH</span>}
            </div>
            <h3 className="mt-2 font-display text-2xl tracking-wide text-chalk100">{candidate.matchup?.label}</h3>
            <p className="mt-1 text-sm text-chalk400">First pitch {formatEasternTime(candidate.first_pitch_et)} · Featured: {featured.team_name || featured.team_abbreviation} · {candidate.shape || 'No publishable shape'}</p>
          </div>
          <span className="font-mono text-xs text-chalk500">{expanded ? 'Collapse' : 'Expand'}</span>
        </div>
      </button>
      {expanded && (
        <div className="mt-4 space-y-4 border-t border-dirt pt-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricTile label="Home story" value={candidate.home_team_story_score} />
            <MetricTile label="Away story" value={candidate.away_team_story_score} />
            <MetricTile label="Contrast" value={candidate.matchup_contrast_score} />
            <MetricTile label="Evidence" value={candidate.evidence_completeness?.featured_team ? 'Complete' : 'Incomplete'} />
          </div>
          <p className="border-l-2 border-amber/40 pl-3 text-sm leading-relaxed text-chalk200">{candidate.plain_one_liner || 'No deterministic one-liner is released while this candidate is withheld.'}</p>
          <FreshnessAndReasons candidate={candidate} />
          <div className="grid gap-3 lg:grid-cols-2">
            <NamedArmsTable label={candidate.matchup?.away_team_name} evidence={candidate.named_arms_evidence?.away_team} />
            <NamedArmsTable label={candidate.matchup?.home_team_name} evidence={candidate.named_arms_evidence?.home_team} />
          </div>
          <ComponentScores breakdown={candidate.component_breakdown} />
          {candidate.publishable ? <SlatePostingEditor candidate={candidate} onPosted={onPosted} /> : (
            <div className="border border-amber/40 bg-amber/10 p-3 text-sm text-amber">This candidate cannot be marked posted until every withholding reason clears.</div>
          )}
          {status.length > 0 && <div className="font-mono text-[10px] text-chalk600">Games: {status.map(game => `#${game.game_pk} ${game.status?.detailed || game.status?.normalized}`).join(' · ')}</div>}
        </div>
      )}
    </article>
  )
}

function formatEasternTime(value) {
  if (!value) return 'TBD'
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York', timeZoneName: 'short' }).format(new Date(value))
}

function FreshnessAndReasons({ candidate }) {
  const schedule = candidate.schedule_freshness || {}
  const bullpen = candidate.bullpen_data_freshness || {}
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="border border-dirt bg-field/50 p-3 text-xs text-chalk400">Schedule: {schedule.state || 'unavailable'} through {schedule.schedule_data_through || 'unavailable'}<br />Bullpen: away {bullpen.away_team?.state || 'unavailable'}, home {bullpen.home_team?.state || 'unavailable'}</div>
      <div className="border border-dirt bg-field/50 p-3 text-xs text-chalk400">Withholding: {(candidate.withholding_reasons || []).length ? candidate.withholding_reasons.join(', ') : 'none'}</div>
    </div>
  )
}

function NamedArmsTable({ label, evidence = {} }) {
  return (
    <div className="overflow-x-auto border border-dirt bg-field/50 p-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label} named arms</div>
      <table className="mt-2 min-w-full text-left text-xs">
        <thead className="text-chalk600"><tr><th className="pr-3">Pitcher</th><th className="pr-3">Last outing</th><th className="pr-3">7d pitches/share</th><th>Outings</th></tr></thead>
        <tbody className="text-chalk300">
          {(evidence.top_relievers || []).map(arm => <tr key={arm.player_id} className="border-t border-dirt"><td className="py-2 pr-3 font-semibold">{arm.name}</td><td className="pr-3">{arm.last_outing_date}</td><td className="pr-3">{arm.trailing_pitches} / {arm.workload_share_pct}%</td><td>{(arm.appearances || []).map(item => `${item.date}: ${item.pitch_count}`).join(', ')}</td></tr>)}
          {(evidence.top_relievers || []).length === 0 && <tr><td colSpan="4" className="py-2 text-chalk600">No complete named-arm evidence.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function ComponentScores({ breakdown = {} }) {
  return <details className="border border-dirt bg-field/50 p-3"><summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk500">Component score breakdown</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap text-[10px] text-chalk400">{JSON.stringify(breakdown, null, 2)}</pre></details>
}

function SlatePostingEditor({ candidate, onPosted }) {
  const platforms = Object.keys(candidate.platform_drafts || {})
  const [platform, setPlatform] = useState(platforms[0] || 'X')
  const [finalText, setFinalText] = useState(candidate.platform_drafts?.[platform]?.text || '')
  const [externalUrl, setExternalUrl] = useState('')
  const [state, setState] = useState({ saving: false, error: null, record: null })
  const selectPlatform = (value) => {
    setPlatform(value)
    setFinalText(candidate.platform_drafts?.[value]?.text || '')
  }
  const submit = async () => {
    setState({ saving: true, error: null, record: null })
    try {
      const generated = candidate.platform_drafts?.[platform]?.text || ''
      const response = await markSlateBriefingPosted({ candidate_id: candidate.candidate_id, evidence_reference: candidate.evidence_reference, source_briefing_date: candidate.briefing_date, platform, generated_draft_text: generated, final_post_text: finalText, external_post_url: externalUrl || undefined })
      setState({ saving: false, error: null, record: response.posting_record })
      await onPosted?.()
    } catch (error) {
      setState({ saving: false, error: error.message || 'Failed to mark posted', record: null })
    }
  }
  return (
    <section className="border border-dirt bg-dugout p-3" aria-label="Posting editor">
      <div className="mb-3 grid gap-3 lg:grid-cols-2">
        {platforms.map(value => (
          <DraftCard key={value} draft={{
            label: value,
            audience: `${value} slate draft`,
            text: candidate.platform_drafts[value].text,
            sourceLabel: 'Deterministic slate draft',
          }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">{platforms.map(value => <button type="button" key={value} onClick={() => selectPlatform(value)} className={`rounded border px-2 py-1 font-mono text-[10px] ${platform === value ? 'border-amber/50 text-amber' : 'border-dirt text-chalk500'}`}>{value}</button>)}</div>
      <label className="mt-3 block text-xs text-chalk500">Editable final post<textarea value={finalText} onChange={event => setFinalText(event.target.value)} rows="5" className="mt-1 w-full border border-dirt bg-field p-2 text-sm text-chalk200" /></label>
      <label className="mt-3 block text-xs text-chalk500">External URL (optional)<input value={externalUrl} onChange={event => setExternalUrl(event.target.value)} className="mt-1 w-full border border-dirt bg-field p-2 text-sm text-chalk200" /></label>
      {state.error && <p className="mt-2 text-sm text-red-200" role="alert">{state.error}</p>}
      {state.record && <p className="mt-2 text-sm text-emerald-200" role="status">Recorded as posted on {state.record.platform}.</p>}
      <button type="button" onClick={submit} disabled={state.saving || !finalText.trim()} className="mt-3 rounded border border-emerald-400/40 bg-emerald-400/10 px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-emerald-200 disabled:opacity-50">{state.saving ? 'Saving...' : 'Mark posted'}</button>
    </section>
  )
}

function RecentPostingHistory({ records }) {
  return (
    <section className="mt-5 border border-dirt bg-dugout p-4" aria-label="Recent posting history">
      <h3 className="font-display text-xl tracking-wide text-chalk100">Recent Posting History</h3>
      {records.length === 0 ? <p className="mt-2 text-sm text-chalk500">No posting receipts yet.</p> : <ul className="mt-2 space-y-2 text-xs text-chalk400">{records.map(record => <li key={record.id} className="border-t border-dirt pt-2"><span className="font-semibold text-chalk200">{record.platform}</span> · {record.story_shape} · {record.posted_at}{record.external_post_url && <> · <a href={record.external_post_url} className="text-amber">Open post</a></>}</li>)}</ul>}
    </section>
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

function PostableTakeCard({ take, rank, draftPackage }) {
  const activeDraftPackage = draftPackage || take.draftPackage
  const activeTake = activeDraftPackage?.drafts ? { ...take, drafts: activeDraftPackage.drafts } : take
  const reviewFlagCount = flattenTakeDrafts(activeTake)
    .reduce((total, draft) => total + (draft.reviewFlags?.length || 0), 0)

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
            <span className="rounded border border-dirt bg-field/70 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-chalk500">
              {activeDraftPackage?.sourceLabel || 'Generated draft'}
            </span>
            {reviewFlagCount > 0 && (
              <span className="rounded border border-red-400/40 bg-red-400/10 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-red-200">
                {reviewFlagCount} fact flag{reviewFlagCount === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <h2 className="mt-3 font-display text-3xl leading-tight tracking-wide text-chalk100">
            {take.signal}
          </h2>
          <p className="mt-2 max-w-4xl text-sm leading-relaxed text-chalk400">{take.suggestedAudience}</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)]">
        <TakeInternals take={take} />
        <DraftPanel take={activeTake} draftPackage={activeDraftPackage} />
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

      <div className="mt-4 font-mono text-[10px] uppercase tracking-widest text-chalk600">Verified Facts Object</div>
      <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words border border-dirt bg-dugout p-2 font-mono text-[10px] leading-relaxed text-chalk400">
        {JSON.stringify(take.verifiedFacts, null, 2)}
      </pre>
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

function DraftPanel({ take, draftPackage }) {
  return (
    <section className="grid grid-cols-1 gap-3" aria-label={`${take.abbr} post drafts`}>
      {draftPackage?.fallbackReason && (
        <div className="border border-amber/30 bg-amber/5 px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-amber/80">
          {draftPackage.fallbackReason}
        </div>
      )}
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
          <div className="mt-1 flex flex-wrap gap-1.5">
            {draft.sourceLabel && (
              <span className="rounded border border-dirt bg-field/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-chalk500">
                {draft.sourceLabel}
              </span>
            )}
            {draft.factCheck?.checked && draft.reviewFlags?.length === 0 && (
              <span className="rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-emerald-200">
                Fact check clear
              </span>
            )}
          </div>
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
      {draft.reviewFlags?.length > 0 && (
        <div className="mt-3 border border-red-400/40 bg-red-400/10 p-2">
          <div className="font-mono text-[10px] uppercase tracking-widest text-red-200">
            Fact Guard
          </div>
          <ul className="mt-1 space-y-1 text-xs text-red-100">
            {draft.reviewFlags.map(flag => <li key={flag}>{flag}</li>)}
          </ul>
        </div>
      )}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-chalk300">{text}</p>
    </section>
  )
}
