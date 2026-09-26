import { Link } from 'react-router-dom'
import { TONIGHT_COPY, leadView } from './tonightView'

// The frozen lead is compact: a measured headline, optional detail, and a
// handoff to the lead game's backend-authored Matchup link when present.
export default function LeadDevelopment({ lead, games }) {
  const view = leadView(lead)
  if (!view) return null
  const game = (Array.isArray(games) ? games : []).find(item => item?.game_pk === view.gamePk)
  const matchupHref = typeof game?.links?.matchup === 'string' ? game.links.matchup : null
  return (
    <section
      className="mt-section min-w-0 max-w-4xl rounded border border-amber/40 bg-dugout p-4 sm:p-5"
      aria-labelledby="tonight-lead-heading"
      data-testid="tonight-lead"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id="tonight-lead-heading" className="font-mono text-xs uppercase tracking-widest text-amber">
          Lead development
        </h2>
        {view.pregame && (
          <span className="font-mono text-[11px] uppercase tracking-wider text-chalk300" data-testid="tonight-lead-pregame">
            {TONIGHT_COPY.pregame}
          </span>
        )}
      </div>
      <p className="mt-2 max-w-3xl break-words font-display text-2xl leading-tight tracking-wide text-chalk100 sm:text-[1.75rem]">
        {view.headline}
      </p>
      {view.detail && (
        <p className="mt-2 max-w-3xl break-words text-sm leading-relaxed text-chalk300">{view.detail}</p>
      )}
      {matchupHref && (
        <Link
          to={matchupHref}
          className="mt-3 inline-flex min-h-11 items-center rounded border border-amber/50 px-3 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:bg-amber/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
          aria-label="Open the lead game Matchup"
          data-link="lead-matchup"
        >
          Matchup
        </Link>
      )}
    </section>
  )
}
