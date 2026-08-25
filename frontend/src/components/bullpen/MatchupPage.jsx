import { useParams } from 'react-router-dom'
import { useFetch } from '../../hooks/useFetch'
import { getScheduledGameMatchup } from '../../utils/api'
import { normalizeGameId } from '../../utils/evidenceLinks'
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

export function MatchupPageView({ payload, loading = false, error = null, onRetry = null }) {
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

  return (
    <div className="space-y-6">
      <header className="border-b border-dirt pb-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-amber/75">Scheduled Matchup</p>
        <h1 className="mt-2 break-words font-display text-3xl leading-tight tracking-wide text-chalk100 sm:text-4xl">
          {awayName} at {homeName}
        </h1>
        {metadata.length > 0 && (
          <p className="mt-2 font-mono text-xs uppercase tracking-wider text-chalk400">
            {metadata.join(' · ')}
          </p>
        )}
      </header>

      {payload.comparison ? (
        <BullpenComparisonView
          payload={payload}
          sideLabels={{ teamA: `Away · ${awayName}`, teamB: `Home · ${homeName}` }}
          showShare={false}
        />
      ) : (
        <EmptyState
          title="Bullpen comparison unavailable"
          subtitle="The scheduled game is available, but its current bullpen comparison could not be established."
        />
      )}
    </div>
  )
}

export default function MatchupPage() {
  const { gameId: rawGameId } = useParams()
  const gameId = normalizeGameId(rawGameId)
  const matchup = useFetch(
    () => (gameId == null
      ? Promise.reject(new Error('This Matchup destination does not contain a valid game ID.'))
      : getScheduledGameMatchup(gameId)),
    [gameId],
  )

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <MatchupPageView
        payload={matchup.data}
        loading={matchup.loading}
        error={matchup.error}
        onRetry={matchup.refetch}
      />
    </div>
  )
}
