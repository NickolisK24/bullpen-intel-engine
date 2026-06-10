import { getTeamGameContextView } from './teamGameContextView'

// Game Context — frames a team's bullpen with its upcoming scheduled game or its
// most recent completed game (the heading reflects which). The opponent/matchup
// is the hero so a user instantly understands who the bullpen is connected to;
// trust metadata stays visible but subordinate. Derived from stored game logs
// only (labelled as such), never a live schedule. Not a scoreboard, matchup
// engine, or prediction.
const CONTEXT_BANNER =
  'Game context helps explain bullpen workload and availability. BaseballOS does not provide matchup advice or game predictions.'

function ContextBanner() {
  return (
    <p className="mt-4 rounded border-l-2 border-amber/40 bg-amber/5 px-3 py-2 text-[11px] leading-relaxed text-chalk400">
      {CONTEXT_BANNER}
    </p>
  )
}

function Matchup({ view }) {
  return (
    <div className="mt-3">
      {/* Hero: the opponent the bullpen is connected to is the dominant element. */}
      <div className="flex flex-col items-start gap-x-3 gap-y-0.5 sm:flex-row sm:flex-wrap sm:items-baseline">
        {view.teamName && (
          <span className="font-display text-xl tracking-wide text-chalk100">{view.teamName}</span>
        )}
        <span className="font-mono text-[11px] uppercase tracking-widest text-chalk500">vs</span>
        <span className="font-display text-2xl tracking-wide text-gradient-amber">
          {view.opponent || 'Opponent unavailable'}
        </span>
      </div>
      {view.gameDate && (
        <div className="mt-1 font-mono text-sm text-chalk300">{view.gameDate}</div>
      )}

      {/* Subordinate trust metadata — present but visually quiet. */}
      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] uppercase tracking-widest text-chalk500">
        <span>{view.dataStateLongLabel}</span>
        <span className="text-chalk700" aria-hidden="true">·</span>
        <span>{view.confidenceLabel}</span>
        <span className="text-chalk700" aria-hidden="true">·</span>
        <span>{view.statusLabel}</span>
      </div>
      {view.missingFields.length > 0 && (
        <p className="mt-2 font-mono text-[11px] text-chalk600">
          {view.missingFields.join(' and ')} unavailable in stored game-log data.
        </p>
      )}
    </div>
  )
}

function EmptyState({ message }) {
  return <p className="mt-3 text-sm leading-relaxed text-chalk400">{message}</p>
}

// Truthful, dynamic title. An upcoming scheduled game and a most-recent completed
// game are distinct states, and we never present a prior final under a "Today"
// heading. When no game can be resolved, the heading stays neutral and the body
// explains the unavailable state.
function cardTitleFor(view, { loading }) {
  if (loading) return 'Game Context'
  if (!view.hasContext || !view.isPresent) return 'Game Context'
  return view.isToday ? 'Upcoming Game Context' : 'Most Recent Completed Game'
}

export default function TeamGameContextCard({ gameContext, loading = false, error = null }) {
  const view = getTeamGameContextView(gameContext)
  const title = cardTitleFor(view, { loading })

  let body
  if (loading) {
    body = <p className="mt-3 font-mono text-xs text-chalk500">Loading game context…</p>
  } else if (error || !view.hasContext) {
    body = <EmptyState message="Schedule data unavailable." />
  } else if (!view.isPresent) {
    body = (
      <EmptyState
        message={view.state === 'no_game_found'
          ? 'No stored game-log context found for this team yet.'
          : (view.message || 'Schedule data unavailable.')}
      />
    )
  } else {
    body = <Matchup view={view} />
  }

  return (
    <section className="mb-5 rounded-lg border border-dirt bg-field/60 p-4" aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-mono text-xs uppercase tracking-widest text-chalk400">{title}</h3>
        <span className="rounded border border-dirt bg-dugout px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Stored game-log context
        </span>
      </div>

      {body}

      <ContextBanner />
    </section>
  )
}
