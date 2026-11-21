import { useCallback, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getRehearsalTonight, getTonightV1 } from '../../utils/api'
import { buildRehearsalMatchupHref, buildRehearsalTeamBoardHref, readRehearsalEdition } from '../../utils/evidenceLinks'
import { ErrorState } from '../UI'
import FeaturedGames from './FeaturedGames'
import LeadDevelopment from './LeadDevelopment'
import LeagueChanges from './LeagueChanges'
import TonightEmptyState, { TonightLoading } from './TonightEmptyState'
import TonightHeader from './TonightHeader'
import TonightSlate from './TonightSlate'
import { classifyTonightResponse, unavailableDetail } from './tonightView'

// The game-link sentence describes rendered game cards, so it is shown only
// when games are on the page; Browse Team Boards is always offered.
function GoDeeper({ hasGames = false }) {
  return (
    <nav className="mt-section-lg min-w-0 border-t border-dirt pt-panel" aria-label="Go deeper" data-testid="tonight-go-deeper">
      {hasGames && (
        <p className="text-sm text-chalk300">
          Every game above links to both Team Boards and its Matchup.
        </p>
      )}
      <Link
        to="/bullpen"
        className="mt-2 inline-flex min-h-11 items-center rounded border border-dirt px-3 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
      >
        Browse Team Boards
      </Link>
    </nav>
  )
}

function TonightBody({ payload, loading, error, onRetry, completedInitiallyExpanded }) {
  if (loading && !payload) return <TonightLoading />
  if (error && !payload) return <TonightEmptyState variant="error" onRetry={onRetry} />
  const kind = classifyTonightResponse(payload)
  if (kind === 'unavailable') {
    return <TonightEmptyState variant="unavailable" detail={unavailableDetail(payload)} />
  }
  if (kind === 'quiet') {
    return (
      <>
        <TonightEmptyState variant="quiet" />
        <LeagueChanges changes={payload.league_changes} />
        <GoDeeper />
      </>
    )
  }
  return (
    <>
      <LeadDevelopment lead={payload.lead} games={payload.games} />
      <FeaturedGames payload={payload} />
      <TonightSlate games={payload.games} initialCompletedExpanded={completedInitiallyExpanded} />
      <LeagueChanges changes={payload.league_changes} />
      <GoDeeper hasGames={Array.isArray(payload.games) && payload.games.length > 0} />
    </>
  )
}

// completedInitiallyExpanded exists for server-rendered inspection only; the
// routed page never sets it, so Completed Games is collapsed on every load.
export function TonightPageView({ payload, loading = false, error = null, onRetry = null, headingRef = null, completedInitiallyExpanded = false }) {
  const available = classifyTonightResponse(payload) !== 'unavailable'
  return (
    <div className="mx-auto min-w-0 max-w-6xl px-4 py-5 sm:px-6 lg:px-8" data-testid="tonight-page">
      <TonightHeader
        ref={headingRef}
        edition={available ? payload.edition : null}
        summary={available ? payload.summary : null}
        loading={loading && !payload}
      />
      <TonightBody payload={payload} loading={loading} error={error} onRetry={onRetry} completedInitiallyExpanded={completedInitiallyExpanded} />
    </div>
  )
}

export default function TonightPage() {
  const [params] = useSearchParams()
  try {
    const edition = readRehearsalEdition(params)
    return edition ? <HistoricalTonight key={JSON.stringify(edition)} {...edition} /> : <PublicTonight />
  } catch (error) {
    return <ErrorState message={error.message} />
  }
}

export function historicalSlate(page, revision, generation) {
  if (page?.scope !== 'isolated_historical_core' || page.status !== 'represented' || page.current_serving_eligible !== false
    || page.selection_revision !== revision || typeof page.generation !== 'string' || !/^[a-f0-9]{64}$/.test(page.generation)
    || (generation !== null && page.generation !== generation) || !page.data_through || !page.availability_reference
    || !Array.isArray(page.games) || page.summary?.game_count !== page.games.length
    || page.quiet_day !== (page.games.length === 0) || !Array.isArray(page.league_changes)) return null
  const ids = new Set()
  const games = []
  for (const game of page.games) {
    const pk = game?.game_pk
    const matchup = buildRehearsalMatchupHref(pk, revision, page.generation)
    const away = buildRehearsalTeamBoardHref(game?.away?.team_id, revision, page.generation)
    const home = buildRehearsalTeamBoardHref(game?.home?.team_id, revision, page.generation)
    const authority = game?.historical_availability
    if (!matchup || ids.has(pk) || !away || !home || away === home
        || authority?.generation !== page.generation || authority.current_serving_eligible !== false
        || authority.reference_date !== page.availability_reference || authority.data_through !== page.data_through) return null
    ids.add(pk)
    games.push({ ...game, links: { matchup, away_team_board: away, home_team_board: home } })
  }
  if (page.league_changes.some(change => change?.occurred_on !== page.data_through
    || !change.source_ref?.startsWith(page.generation + '/'))) return null
  return { ...page, games }
}

function HistoricalTonight({ revision, generation }) {
  const slate = useFetch(async options => {
    const page = historicalSlate(await getRehearsalTonight(revision, options), revision, generation)
    if (!page) throw new Error('The requested historical slate could not be verified.')
    return page
  }, [revision, generation])
  if (slate.loading) return <TonightLoading />
  if (slate.error) return <ErrorState message={slate.error} onRetry={slate.refetch} />
  const page = slate.data
  return <main className="mx-auto min-w-0 max-w-6xl p-6">
    <h1 className="font-display text-3xl">Historical Tonight · {page.availability_reference}</h1>
    <p>Data through {page.data_through} · Revision {revision}</p>
    {page.quiet_day ? <p>No games on the represented slate.</p> : <>
      <LeadDevelopment lead={page.lead} games={page.games} />
      <FeaturedGames payload={page} />
      <TonightSlate games={page.games} />
    </>}
    <LeagueChanges changes={page.league_changes} edition={{ revision, generation: page.generation }} />
    <Link className="underline" to={`/dashboard?rehearsalRevision=${revision}&rehearsalGeneration=${page.generation}`}>Open this League edition</Link>
  </main>
}

function PublicTonight() {
  const headingRef = useRef(null)
  const fetchTonight = useCallback(options => getTonightV1(options), [])
  const { data, loading, error, refetch } = useFetch(fetchTonight, [fetchTonight])
  // Retry keeps keyboard focus on the stable page heading rather than on a
  // button that unmounts once the request starts.
  const retry = useCallback(() => {
    headingRef.current?.focus()
    refetch()
  }, [refetch])
  return <TonightPageView payload={data} loading={loading} error={error} onRetry={retry} headingRef={headingRef} />
}
