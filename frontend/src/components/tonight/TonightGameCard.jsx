import { Link } from 'react-router-dom'
import TonightTeamSide from './TonightTeamSide'
import { TONIGHT_COPY, gameView } from './tonightView'

export default function TonightGameCard({ game, idPrefix = 'game' }) {
  const view = gameView(game)
  const headingId = `${idPrefix}-${view.gamePk ?? 'unknown'}-heading`
  const matchupName = `${view.away.abbreviation || view.away.name} at ${view.home.abbreviation || view.home.name}`
  return (
    <article
      className="card min-w-0 p-3 sm:p-4"
      aria-labelledby={headingId}
      data-testid="tonight-game-card"
      data-game-pk={view.gamePk ?? ''}
      data-game-state={view.state}
    >
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 id={headingId} className="min-w-0 break-words font-display text-xl leading-tight tracking-wide text-chalk100">
          {view.away.name} at {view.home.name}
          {view.gameNumber && view.gameNumber > 1 ? (
            <span className="ml-2 font-mono text-xs text-chalk400">Game {view.gameNumber}</span>
          ) : null}
        </h3>
        <p className="shrink-0 font-mono text-xs uppercase tracking-wider text-chalk300" data-testid="tonight-game-status">
          {view.statusLabel}
        </p>
      </div>

      <div className="mt-3 grid min-w-0 grid-cols-1 gap-4 tablet:grid-cols-2">
        <TonightTeamSide side={view.away} />
        <TonightTeamSide side={view.home} />
      </div>

      {view.contextSentence && (
        <div className="mt-3 border-t border-dirt pt-3" data-testid="tonight-context">
          {view.contextPregame && (
            <p className="font-mono text-[11px] uppercase tracking-wider text-chalk400" data-testid="tonight-context-pregame">
              {TONIGHT_COPY.pregame}
            </p>
          )}
          <p className="break-words text-sm leading-relaxed text-chalk200">{view.contextSentence}</p>
        </div>
      )}

      {view.matchupHref && (
        <div className="mt-3">
          <Link
            to={view.matchupHref}
            className="inline-flex min-h-11 items-center rounded border border-amber/50 px-3 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
            aria-label={`Open the ${matchupName} Matchup`}
            data-link="matchup"
          >
            Matchup
          </Link>
        </div>
      )}
    </article>
  )
}
