import { Link } from 'react-router-dom'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
import { leagueChangeView } from './tonightView'

export default function LeagueChanges({ changes }) {
  const items = (Array.isArray(changes) ? changes : [])
    .map(change => leagueChangeView(change, buildTeamBoardHref(change?.team_abbreviation)))
    .filter(Boolean)
  if (items.length === 0) return null
  return (
    <section className="mt-section min-w-0" aria-labelledby="tonight-changes-heading" data-testid="tonight-changes">
      <h2 id="tonight-changes-heading" className="font-mono text-xs uppercase tracking-widest text-chalk300">
        What Changed
      </h2>
      <ul className="mt-3 min-w-0 divide-y divide-dirt border-y border-dirt">
        {items.map(item => (
          <li key={item.key} className="flex min-w-0 flex-col gap-2 py-3 tablet:flex-row tablet:items-start tablet:justify-between" data-testid="tonight-change">
            <div className="min-w-0">
              <p className="font-mono text-[11px] uppercase tracking-wider text-chalk400">
                {item.team}
                {item.occurredOn && <span> · {item.occurredOn}</span>}
              </p>
              <p className="mt-0.5 break-words text-sm text-chalk100">{item.headline}</p>
              {item.detail && <p className="mt-0.5 break-words text-xs text-chalk300">{item.detail}</p>}
            </div>
            {item.boardHref && (
              <Link
                to={item.boardHref}
                className="inline-flex min-h-11 shrink-0 items-center self-start rounded border border-dirt px-3 font-mono text-xs uppercase tracking-wider text-chalk200 transition-colors hover:border-amber hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
                aria-label={`Open the ${item.team || 'team'} Team Board`}
                data-link="team-board"
              >
                Team Board
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
