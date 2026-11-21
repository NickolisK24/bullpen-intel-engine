import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getRehearsalStoryFeed } from '../../utils/api'
import { ErrorState, LoadingPane } from '../UI'

const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const teamId = value => Number.isSafeInteger(value) && value > 0

export function matchesStoryReview(page, revision, generation) {
  if (page?.scope !== 'historical_story_feed_review' || page.selection_revision !== revision
      || page.current_serving_eligible !== false || !digest(page.generation)
      || (generation !== null && page.generation !== generation) || !page.data_through || !page.availability_reference
      || !Array.isArray(page.season_complete_clubs) || !page.season_complete_clubs.every(teamId)
      || !Array.isArray(page.clubs) || !Array.isArray(page.items)) return false
  const complete = new Set(page.season_complete_clubs)
  if (complete.size !== page.season_complete_clubs.length) return false
  if (page.status === 'incomplete_league_availability') return page.items.length === 0 && page.clubs.length === 0
    && Array.isArray(page.unresolved_clubs) && page.unresolved_clubs.length > 0 && page.unresolved_clubs.every(id => teamId(id) && !complete.has(id))
    && new Set(page.unresolved_clubs).size === page.unresolved_clubs.length
  if (page.status !== 'reviewed' || !page.clubs.every(club => teamId(club?.team_id) && !complete.has(club.team_id) && typeof club.team_name === 'string'
      && ['selected', 'withheld'].includes(club.selection?.status))) return false
  const clubs = new Map(page.clubs.map(club => [club.team_id, club]))
  return clubs.size === page.clubs.length && new Set(page.items.map(item => item?.team_id)).size === page.items.length
    && page.items.every(item => {
      const selection = clubs.get(item?.team_id)?.selection
      return selection?.status === 'selected' && item.observation_type === selection.observation_type
        && typeof item.observation_type === 'string' && digest(item.feed_copy_sha256) && digest(item.club_copy_sha256)
        && item.club_copy_sha256 === selection.copy_sha256 && Array.isArray(item.source_layers) && item.source_layers.length > 0
        && Array.isArray(selection.source_layers) && item.source_layers.length === selection.source_layers.length
        && item.source_layers.every((layer, index) => typeof layer === 'string' && layer === selection.source_layers[index])
    })
}

export default function HistoricalStoryFeed({ revision, generation }) {
  const read = useFetch(async options => {
    const page = await getRehearsalStoryFeed(revision, options)
    if (!matchesStoryReview(page, revision, generation)) throw new Error('The historical Stories edition could not be verified.')
    return page
  }, [revision, generation])
  if (read.loading) return <LoadingPane message="Loading historical Stories…" />
  if (read.error) return <ErrorState message={read.error} onRetry={read.refetch} />
  const page = read.data
  const clubs = new Map(page.clubs.map(club => [club.team_id, club]))
  return <main className="mx-auto max-w-5xl space-y-5 p-6">
    <h1 className="font-display text-3xl">Historical Stories</h1>
    <p>Editorial review for {page.availability_reference} · Workload through {page.data_through}</p>
    {page.season_complete_clubs.length > 0 && <p>{page.season_complete_clubs.length} clubs had completed their season.</p>}
    {page.status === 'incomplete_league_availability'
      ? <p>League selection withheld. A comparable availability read is unavailable for {page.unresolved_clubs.length} clubs.</p>
      : page.items.length === 0 ? <p>No observations qualified for the league feed.</p>
        : <ol>{page.items.map(item => <li key={item.team_id} className="border-t border-dirt py-3">
          <Link className="underline" to={`/stories?team=${item.team_id}&rehearsalRevision=${revision}&rehearsalGeneration=${page.generation}`}>
            {clubs.get(item.team_id).team_name}
          </Link> · {item.observation_type.replaceAll('_', ' ')}
        </li>)}</ol>}
  </main>
}
