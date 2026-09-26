import { useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getTonightV1 } from '../../utils/api'
import FeaturedGames from './FeaturedGames'
import LeadDevelopment from './LeadDevelopment'
import LeagueChanges from './LeagueChanges'
import TonightEmptyState, { TonightLoading } from './TonightEmptyState'
import TonightHeader from './TonightHeader'
import TonightSlate from './TonightSlate'
import { classifyTonightResponse, unavailableDetail } from './tonightView'

function GoDeeper() {
  return (
    <nav className="mt-section-lg min-w-0 border-t border-dirt pt-panel" aria-label="Go deeper" data-testid="tonight-go-deeper">
      <p className="text-sm text-chalk300">
        Every game above links to both Team Boards and its Matchup.
      </p>
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
      <GoDeeper />
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
