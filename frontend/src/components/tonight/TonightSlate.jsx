import { useState } from 'react'
import TonightGameCard from './TonightGameCard'
import { TONIGHT_COPY, groupGamesByLifecycle } from './tonightView'

const COMPLETED_REGION_ID = 'tonight-completed-games'
const GRID = 'mt-2 grid min-w-0 grid-cols-1 gap-3 desktop:grid-cols-2'

function SlateGroup({ id, label, games, tone }) {
  if (games.length === 0) return null
  return (
    <section className="mt-4 min-w-0" aria-labelledby={`${id}-heading`} data-testid={id}>
      <h3 id={`${id}-heading`} className={`font-mono text-[11px] uppercase tracking-widest ${tone}`}>
        {label}
      </h3>
      <div className={GRID}>
        {games.map(game => (
          <TonightGameCard key={game.game_pk} game={game} idPrefix="slate" headingLevel={4} />
        ))}
      </div>
    </section>
  )
}

// Completed games stay reachable but secondary: a disclosure, collapsed on
// every load, whose cards mount only while expanded.
function CompletedGames({ games, initiallyExpanded }) {
  const [expanded, setExpanded] = useState(initiallyExpanded)
  if (games.length === 0) return null
  return (
    <section className="mt-5 min-w-0 border-t border-dirt pt-4" aria-labelledby="tonight-slate-completed-heading" data-testid="tonight-slate-completed">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h3 id="tonight-slate-completed-heading" className="font-mono text-[11px] uppercase tracking-widest text-chalk300">
          {TONIGHT_COPY.completedGames} ({games.length})
        </h3>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={COMPLETED_REGION_ID}
          onClick={() => setExpanded(open => !open)}
          className="inline-flex min-h-11 items-center rounded border border-dirt px-3 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
          data-testid="tonight-completed-toggle"
        >
          {expanded ? TONIGHT_COPY.hideCompleted : TONIGHT_COPY.showCompleted}
        </button>
      </div>
      <div id={COMPLETED_REGION_ID} hidden={!expanded} data-testid="tonight-completed-region">
        {expanded && (
          <div className={GRID}>
            {games.map(game => (
              <TonightGameCard key={game.game_pk} game={game} idPrefix="slate" headingLevel={4} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export default function TonightSlate({ games, initialCompletedExpanded = false }) {
  const groups = groupGamesByLifecycle(games)
  const total = groups.inProgress.length + groups.upcoming.length + groups.completed.length
  if (total === 0) return null
  const allFinal = groups.completed.length === total
  return (
    <section className="mt-section-lg min-w-0 border-t border-dirt pt-section" aria-labelledby="tonight-slate-heading" data-testid="tonight-slate">
      <h2 id="tonight-slate-heading" className="font-mono text-xs uppercase tracking-widest text-chalk300">
        Tonight&apos;s Slate
      </h2>
      {allFinal && (
        <p className="mt-3 text-sm text-chalk200" data-testid="tonight-all-final">{TONIGHT_COPY.allFinal}</p>
      )}
      <SlateGroup id="tonight-slate-in-progress" label={TONIGHT_COPY.inProgress} games={groups.inProgress} tone="text-chalk100" />
      <SlateGroup id="tonight-slate-upcoming" label={TONIGHT_COPY.upcoming} games={groups.upcoming} tone="text-chalk200" />
      <CompletedGames games={groups.completed} initiallyExpanded={initialCompletedExpanded} />
    </section>
  )
}
