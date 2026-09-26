import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getTonightV1 } from '../../utils/api'
import FeaturedGames from './FeaturedGames'
import LeadDevelopment from './LeadDevelopment'
import LeagueChanges from './LeagueChanges'
import TonightEmptyState, { TonightLoading } from './TonightEmptyState'
import TonightHeader from './TonightHeader'
import TonightSlate from './TonightSlate'
import { TONIGHT_COPY, classifyTonightResponse, unavailableDetail } from './tonightView'

function PageShell({ children }) {
  return <div className="mx-auto min-w-0 max-w-6xl px-4 py-5 sm:px-6 lg:px-8" data-testid="tonight-page">{children}</div>
}

function StateHeading() {
  return (
    <h1 className="font-display text-3xl leading-none tracking-wide text-chalk100 sm:text-4xl lg:text-5xl">
      {TONIGHT_COPY.title}
    </h1>
  )
}

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

export function TonightPageView({ payload, loading = false, error = null, onRetry = null }) {
  if (loading && !payload) {
    return <PageShell><StateHeading /><TonightLoading /></PageShell>
  }
  if (error && !payload) {
    return <PageShell><StateHeading /><TonightEmptyState variant="error" onRetry={onRetry} /></PageShell>
  }
  const kind = classifyTonightResponse(payload)
  if (kind === 'unavailable') {
    return (
      <PageShell>
        <StateHeading />
        <TonightEmptyState variant="unavailable" detail={unavailableDetail(payload)} />
      </PageShell>
    )
  }
  if (kind === 'quiet') {
    return (
      <PageShell>
        <TonightHeader edition={payload.edition} summary={payload.summary} />
        <TonightEmptyState variant="quiet" />
        <LeagueChanges changes={payload.league_changes} />
        <GoDeeper />
      </PageShell>
    )
  }
  return (
    <PageShell>
      <TonightHeader edition={payload.edition} summary={payload.summary} />
      <LeadDevelopment lead={payload.lead} />
      <FeaturedGames payload={payload} />
      <TonightSlate games={payload.games} />
      <LeagueChanges changes={payload.league_changes} />
      <GoDeeper />
    </PageShell>
  )
}

export default function TonightPage() {
  const fetchTonight = useCallback(options => getTonightV1(options), [])
  const { data, loading, error, refetch } = useFetch(fetchTonight, [fetchTonight])
  return <TonightPageView payload={data} loading={loading} error={error} onRetry={refetch} />
}
