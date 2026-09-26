import { Link } from 'react-router-dom'
import TonightTeamSide from './TonightTeamSide'
import { TONIGHT_COPY, gameView } from './tonightView'

const ACTION_BASE = 'inline-flex min-h-11 items-center rounded border px-3 font-mono text-xs uppercase tracking-wider transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60'
const TEAM_BOARD_ACTION = `${ACTION_BASE} border-dirt text-chalk200 hover:border-amber hover:text-amber`
const MATCHUP_ACTION = `${ACTION_BASE} border-amber/50 text-amber hover:bg-amber/10`

function TeamBoardAction({ side }) {
  if (!side.boardHref) return null
  return (
    <Link
      to={side.boardHref}
      className={TEAM_BOARD_ACTION}
      aria-label={`Open the ${side.name} Team Board`}
      data-link="team-board"
    >
      {side.abbreviation ? `${side.abbreviation} Team Board` : `${side.role} Team Board`}
    </Link>
  )
}

// Reading order: matchup, status, each club's Team State and facts, the
// backend context sentence, then one shared action row.
export default function TonightGameCard({ game, idPrefix = 'game', headingLevel = 3 }) {
  const view = gameView(game)
  const headingId = `${idPrefix}-${view.gamePk ?? 'unknown'}-heading`
  const matchupName = `${view.away.abbreviation || view.away.name} at ${view.home.abbreviation || view.home.name}`
  const hasActions = Boolean(view.away.boardHref || view.home.boardHref || view.matchupHref)
  const Heading = headingLevel === 4 ? 'h4' : 'h3'
  return (
    <article
      className="card flex min-w-0 flex-col p-3 sm:p-4"
      aria-labelledby={headingId}
      data-testid="tonight-game-card"
      data-game-pk={view.gamePk ?? ''}
      data-game-state={view.state}
    >
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <Heading id={headingId} className="min-w-0 break-words font-display text-xl leading-tight tracking-wide text-chalk100">
          {view.away.name} at {view.home.name}
          {view.gameNumber && view.gameNumber > 1 ? (
            <span className="ml-2 font-mono text-xs text-chalk400">Game {view.gameNumber}</span>
          ) : null}
        </Heading>
        <p className="shrink-0 font-mono text-xs uppercase tracking-wider text-chalk300" data-testid="tonight-game-status">
          {view.statusLabel}
        </p>
      </div>

      <div className="mt-3 grid min-w-0 grid-cols-1 gap-x-5 gap-y-4 tablet:grid-cols-2">
        <TonightTeamSide side={view.away} />
        <TonightTeamSide side={view.home} />
      </div>

      {view.contextSentence && (
        <div className="mt-3 border-l-2 border-dirt pl-3" data-testid="tonight-context">
          {view.contextPregame && (
            <p className="font-mono text-[11px] uppercase tracking-wider text-chalk400" data-testid="tonight-context-pregame">
              {TONIGHT_COPY.pregame}
            </p>
          )}
          <p className="max-w-3xl break-words text-sm leading-relaxed text-chalk200">{view.contextSentence}</p>
        </div>
      )}

      {hasActions && (
        <div className="mt-auto flex min-w-0 flex-wrap gap-2 pt-3" data-testid="tonight-card-actions">
          <TeamBoardAction side={view.away} />
          <TeamBoardAction side={view.home} />
          {view.matchupHref && (
            <Link
              to={view.matchupHref}
              className={MATCHUP_ACTION}
              aria-label={`Open the ${matchupName} Matchup`}
              data-link="matchup"
            >
              Matchup
            </Link>
          )}
        </div>
      )}
    </article>
  )
}
