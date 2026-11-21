import { useFetch } from '../../hooks/useFetch'
import { getRehearsalLeague } from '../../utils/api'
import { ErrorState, LoadingPane } from '../UI'
import LeagueTeamStateLandscape from './LeagueTeamStateLandscape'
import { historicalLeagueView } from './leagueTeamStateListingView'

export default function HistoricalLeague({ revision, generation }) {
  const league = useFetch(async options => {
    const page = await getRehearsalLeague(revision, options)
    const view = historicalLeagueView(page, revision, generation)
    if (!view) throw new Error('The requested historical League edition could not be verified.')
    return view
  }, [revision, generation])
  if (league.loading) return <LoadingPane message="Loading historical League…" />
  if (league.error) return <ErrorState message={league.error} onRetry={league.refetch} />
  return <main className="mx-auto max-w-7xl p-6">
    <h1 className="mb-4 font-display text-3xl">Historical League · Revision {revision}</h1>
    <LeagueTeamStateLandscape view={league.data} historical />
  </main>
}
