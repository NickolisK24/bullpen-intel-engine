import { Link } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getRehearsalStoryEvidence } from '../../utils/api'
import { buildRehearsalTeamBoardHref } from '../../utils/evidenceLinks'
import { ErrorState, LoadingPane } from '../UI'

const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const label = value => value.replaceAll('_', ' ')
const withheld = new Set(['incomplete_rotation_calendar', 'conflicting_pinned_game_versions', 'unverified_club_game', 'missing_pinned_final'])

function matchesObservation(selection, rows) {
  if (selection == null) return true
  if (selection.status === 'withheld') return typeof selection.reason === 'string' && !selection.copy_sha256
  return selection.status === 'selected' && digest(selection.copy_sha256) && Array.isArray(selection.source_layers)
    && rows.some(item => item.type === selection.observation_type
      && item.source_layers.length === selection.source_layers.length
      && item.source_layers.every((layer, index) => layer === selection.source_layers[index]))
}

export function verifyStoryEvidence(page, team, revision, generation) {
  const rows = page?.observations
  if (page?.scope !== 'isolated_historical_game_lines' || page.current_serving_eligible !== false
    || page.team !== team || page.selection_revision !== revision || !digest(page.generation)
    || (generation !== null && page.generation !== generation) || !page.represented || !page.availability_reference
    || !digest(page.citation?.input_digest) || !digest(page.citation?.facts_digest)) return false
  if (withheld.has(page.qualification)) return rows === null && page.story_selection == null
  return page.qualification === 'game_lines_compared' && rows?.capability === 'story_observation_engine_v1'
    && rows.source === 'backend' && rows.team_id === team && typeof rows.team_name === 'string'
    && rows.data_through_date === page.represented && rows.reference_date === page.availability_reference
    && Array.isArray(rows.observations) && rows.observation_count === rows.observations.length
    && rows.observations.every(item => item?.team_id === team && item.team === rows.team_name
      && typeof item.type === 'string' && item.type.length > 0 && Array.isArray(item.source_layers) && item.source_layers.length > 0
      && item.source_layers.every(layer => typeof layer === 'string' && typeof page.coverage?.[layer] === 'string'))
    && matchesObservation(page.story_selection, rows.observations)
    && Array.isArray(page.source_games) && new Set(page.source_games).size === page.source_games.length
    && page.source_games.every(game => Number.isSafeInteger(game) && game > 0
      && Array.isArray(page.boxscore_digests?.[game]) && page.boxscore_digests[game].length > 0
      && page.boxscore_digests[game].every(digest))
}

export default function HistoricalStoryEvidence({ team, revision, generation }) {
  const request = useFetch(async options => {
    const page = await getRehearsalStoryEvidence(team, revision, options)
    if (!verifyStoryEvidence(page, team, revision, generation)) throw new Error('The historical story evidence could not be verified.')
    return page
  }, [team, revision, generation])
  if (request.loading) return <LoadingPane message="Loading historical observations…" />
  if (request.error) return <ErrorState message={request.error} onRetry={request.refetch} />
  const page = request.data
  const payload = page.observations
  return <main className="mx-auto max-w-5xl space-y-5 p-6">
    <header>
      <h1 className="font-display text-3xl">Historical story evidence · {payload?.team_name || `MLB club ${team}`}</h1>
      <p>For editorial review · Revision {revision}</p>
      <p>Data through {page.represented} · Availability reference {page.availability_reference}</p>
    </header>
    {!payload ? <p>Observations withheld · {label(page.qualification)}</p> : <>
      {payload.observations.length === 0 && <p>No qualifying observations in this edition.</p>}
      {payload.observations.map(item => <section key={item.type}>
        <h2 className="font-semibold capitalize">{label(item.type)}</h2>
        {page.story_selection?.observation_type === item.type && page.story_selection.status === 'selected'
          && <p>Selected by the historical story writer</p>}
        <ul aria-label="Source coverage">{item.source_layers.map(layer =>
          <li key={layer}>{label(layer)} · {label(page.coverage[layer])}</li>)}</ul>
        <details><summary>Inspect observation inputs</summary>
          <pre className="whitespace-pre-wrap break-words">{JSON.stringify({
            headline: item.headline_inputs, baseline: item.baseline_inputs, cause: item.cause_inputs, constraints: item.constraint_inputs,
          }, null, 2)}</pre>
        </details>
      </section>)}
      <details><summary>Game-side evidence ({page.source_games.length} {page.source_games.length === 1 ? 'game' : 'games'})</summary>
        {page.source_games.map(game => <p className="break-all" key={game}>MLB game {game} · {page.boxscore_digests[game].join(', ')}</p>)}
      </details>
    </>}
    <p className="break-all">Rotation input digest · {page.citation.input_digest}</p>
    <Link className="underline" to={buildRehearsalTeamBoardHref(team, revision, page.generation)}>Open this Team Board edition</Link>
  </main>
}
