import { Link } from 'react-router-dom'
import { SectionHeading } from './BullpenStories'

// Section 4 — Rankings Preview. Two boards run live off today's availability
// counts; the movement boards are honest placeholders until day-over-day
// tracking exists. Positions reflect today's deterministic count ordering.
export default function RankingsPreview({ rankings }) {
  if (!rankings) return null

  return (
    <section className="mb-8" aria-label="Bullpen rankings preview">
      <SectionHeading
        title="Bullpen Rankings"
        subtitle={rankings.intro}
        right={(
          <span className="rounded border border-amber/30 bg-amber/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-amber/80">
            Preview
          </span>
        )}
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {rankings.boards.map(board => (
          <RankingBoard key={board.key} board={board} />
        ))}
      </div>
    </section>
  )
}

function RankingBoard({ board }) {
  return (
    <div className="card flex flex-col p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">{board.title}</div>
      <div className="mt-0.5 text-[11px] text-chalk600">{board.note}</div>

      <div className="mt-3 flex-1 space-y-1.5">
        {board.placeholder ? (
          <PlaceholderRows copy={board.placeholderCopy} />
        ) : board.entries.length === 0 ? (
          <div className="py-2 text-xs text-chalk400">Nothing stands out in the current snapshot.</div>
        ) : (
          board.entries.map(entry => (
            <Link
              key={entry.position}
              to={entry.href || '/bullpen'}
              className="group flex items-center gap-3 rounded border border-transparent px-2 py-1.5 transition-colors hover:border-dirt hover:bg-chalk/40"
            >
              <span className="font-display text-lg text-amber/80 w-4 text-center">{entry.position}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-mono text-sm text-chalk100 group-hover:text-amber transition-colors">
                  {entry.abbr}
                </span>
                <span className="block truncate text-[11px] text-chalk600">{entry.teamName}</span>
              </span>
              <span className="font-mono text-[11px] text-chalk400">{entry.stat}</span>
            </Link>
          ))
        )}
      </div>
    </div>
  )
}

function PlaceholderRows({ copy }) {
  return (
    <div>
      {[1, 2, 3].map(position => (
        <div key={position} className="flex items-center gap-3 px-2 py-1.5 opacity-40" aria-hidden="true">
          <span className="font-display text-lg text-chalk600 w-4 text-center">{position}</span>
          <span className="h-2 flex-1 rounded bg-dirt" />
          <span className="h-2 w-10 rounded bg-dirt" />
        </div>
      ))}
      <div className="mt-2 flex items-center gap-2 px-2">
        <span className="rounded border border-dirt px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-chalk600">
          Coming Soon
        </span>
        <span className="text-[11px] leading-snug text-chalk400">{copy}</span>
      </div>
    </div>
  )
}
