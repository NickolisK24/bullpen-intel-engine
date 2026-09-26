import { Link } from 'react-router-dom'
import { buildTeamBoardHref } from '../../utils/evidenceLinks'
import { leagueChangeView } from './tonightView'

// Backend order is authoritative: items are rendered as served, never grouped
// or re-sorted. The headline leads; team and date sit on a quieter meta row
// that also carries the Team Board handoff.
export default function LeagueChanges({ changes }) {
  const items = (Array.isArray(changes) ? changes : [])
    .map(change => leagueChangeView(change, buildTeamBoardHref(change?.team_abbreviation)))
    .filter(Boolean)
  if (items.length === 0) return null
  return (
    <section className="mt-section-lg min-w-0 border-t border-dirt pt-section" aria-labelledby="tonight-changes-heading" data-testid="tonight-changes">
      <h2 id="tonight-changes-heading" className="font-mono text-xs uppercase tracking-widest text-chalk300">
        What Changed
      </h2>
      <ul className="mt-2 min-w-0 max-w-3xl divide-y divide-dirt">
        {items.map(item => (
          <li key={item.key} className="min-w-0 py-2" data-testid="tonight-change">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <p className="min-w-0 font-mono text-[11px] uppercase tracking-wider text-chalk400">
                <span className="text-chalk200">{item.team}</span>
                {item.occurredOn && <span> · {item.occurredOn}</span>}
              </p>
              {item.boardHref && (
                <Link
                  to={item.boardHref}
                  className="inline-flex min-h-11 shrink-0 items-center rounded px-2 font-mono text-[11px] uppercase tracking-wider text-chalk200 underline-offset-4 transition-colors hover:text-amber hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
                  aria-label={`Open the ${item.team || 'team'} Team Board`}
                  data-link="team-board"
                >
                  Team Board
                </Link>
              )}
            </div>
            <p className="-mt-1 break-words text-sm leading-snug text-chalk100">{item.headline}</p>
            {item.detail && <p className="mt-0.5 break-words text-xs leading-relaxed text-chalk300">{item.detail}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}
