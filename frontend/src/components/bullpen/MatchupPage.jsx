import { useParams, useSearchParams } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getScheduledGameMatchup, getRehearsalMatchup } from '../../utils/api'
import { normalizeGameId, parseRehearsalRevision } from '../../utils/evidenceLinks'
import { formatUtcDateTimeEt } from '../../utils/dateDisplay'
import { formatFreshnessDate } from '../UI/Freshness'
import { EmptyState, ErrorState, LoadingPane } from '../UI'
import BullpenComparisonView from './board/BullpenComparisonView'

function gameTeamName(team, fallback) {
  return team?.team_name || team?.team_abbreviation || fallback
}

function gameStatus(status) {
  return status?.detailed || status?.normalized || status?.abstract || null
}

export function MatchupPageView({ payload, loading = false, error = null, onRetry = null, historical = false }) {
  if (loading) {
    return <LoadingPane message="Loading scheduled game matchup…" />
  }
  if (error || !payload?.game) {
    return <ErrorState message={error || 'This scheduled game could not be found.'} onRetry={onRetry} />
  }

  const game = payload.game
  const awayName = gameTeamName(game.away, 'Away team')
  const homeName = gameTeamName(game.home, 'Home team')
  const time = formatUtcDateTimeEt(game.game_time_utc, { includeDate: false })
  const date = formatFreshnessDate(game.reference_date)
  const status = gameStatus(game.status)
  const gameLabel = game.doubleheader_flag && game.doubleheader_flag !== 'N' && game.game_number
    ? `Game ${game.game_number}`
    : null
  const metadata = [date, gameLabel, time, status].filter(Boolean)
  // The backend marks a game that will not be played (cancelled, or removed
  // from MLB's schedule as an unneeded postseason game) as not upcoming.
  const notUpcoming = payload.status === 'not_upcoming'
  const gameLabelByState = { completed: 'Completed Game', live: 'Live Game' }

  return (
    <div className="space-y-6">
      <header className="border-b border-dirt pb-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-metadata-accent">
          {historical ? 'Historical matchup rehearsal' : notUpcoming ? 'Not Played' : (gameLabelByState[game.status?.normalized] || 'Scheduled Matchup')}
        </p>
        <h1 className="mt-2 break-words font-display text-3xl leading-tight tracking-wide text-chalk100 sm:text-4xl">
          {awayName} at {homeName}
        </h1>
        {metadata.length > 0 && (
          <p className="mt-2 font-mono text-xs uppercase tracking-wider text-chalk400">
            {metadata.join(' · ')}
          </p>
        )}
      </header>

      {notUpcoming ? (
        <EmptyState
          title="This game will not be played"
          subtitle={payload.reason_code === 'scheduled_game_removed_from_mlb_schedule'
            ? "It is no longer on MLB's schedule, so no bullpen comparison is shown for it."
            : 'MLB cancelled it, so no bullpen comparison is shown for it.'}
        />
      ) : payload.comparison ? (
        <BullpenComparisonView
          payload={payload}
          sideLabels={{ teamA: `Away · ${awayName}`, teamB: `Home · ${homeName}` }}
          historical={historical}
          showShare={false}
        />
      ) : (
        <EmptyState
          title="Bullpen comparison unavailable"
          subtitle={payload.reason_code === 'trusted_pregame_edition_unavailable'
            ? 'No trusted pregame comparison is available for this game date.'
            : 'A bullpen comparison could not be established for this game.'}
        />
      )}
    </div>
  )
}

export default function MatchupPage() {
  const { gameId: rawGameId } = useParams()
  const gameId = normalizeGameId(rawGameId)
  const [params] = useSearchParams()
  const generation = params.get('rehearsalGeneration')
  let revision
  try {
    revision = parseRehearsalRevision(params.get('rehearsalRevision'), params.getAll('rehearsalRevision').length > 1)
    if (generation !== null && (revision === null || !/^[a-f0-9]{64}$/.test(generation)
        || params.getAll('rehearsalGeneration').length > 1)) throw new Error('Invalid historical rehearsal generation.')
  } catch (error) {
    return <ErrorState message={error.message} />
  }
  return <MatchupEdition key={JSON.stringify([gameId, revision, generation])} {...{ gameId, revision, generation }} />
}

export function historicalMatchupPayload(response, gameId, revision, generation) {
  const comparison = response?.historical_comparison
  const game = comparison?.game
  const card = response?.games?.[0]
  const sidesMatch = (side, key) => Number.isSafeInteger(game?.[side]?.team_id)
    && game[side].team_id === card?.[side]?.team_id && game[side].team_id === comparison?.teams?.[key]?.team_id
  if (response?.status !== 'represented' || response.scope !== 'isolated_historical_core'
      || response.selection_revision !== revision || response.current_serving_eligible !== false
      || typeof response.generation !== 'string' || !/^[a-f0-9]{64}$/.test(response.generation)
      || (generation !== null && response.generation !== generation)
      || comparison?.scope !== response.scope || comparison.selection_revision !== revision
      || comparison.generation !== response.generation || comparison.current_serving_eligible !== false
      || comparison.publication_authority !== null || !['available', 'partial'].includes(comparison.status)
      || response.games?.length !== 1 || card?.game_pk !== gameId || game?.game_pk !== gameId
      || !response.data_through || comparison.represented_date !== response.data_through
      || !response.availability_reference || comparison.availability_reference_date !== response.availability_reference
      || game.reference_date !== response.availability_reference || !sidesMatch('away', 'team_a')
      || !sidesMatch('home', 'team_b') || game.home.team_id === game.away.team_id) {
    throw new Error('The requested historical matchup edition could not be verified.')
  }
  return { game, comparison }
}

function MatchupEdition({ gameId, revision, generation }) {
  const matchup = useFetch(async options => {
    if (gameId == null) throw new Error('This Matchup destination does not contain a valid game ID.')
    if (revision === null) return getScheduledGameMatchup(gameId, options)
    const response = await getRehearsalMatchup(revision, gameId, options)
    return historicalMatchupPayload(response, gameId, revision, generation)
  }, [gameId, revision, generation])

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <MatchupPageView
        historical={revision !== null}
        payload={matchup.data}
        loading={matchup.loading}
        error={matchup.error}
        onRetry={matchup.refetch}
      />
    </div>
  )
}
