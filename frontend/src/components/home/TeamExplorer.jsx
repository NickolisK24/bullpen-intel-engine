import { Link } from 'react-router-dom'
import { SectionHeading } from './BullpenStories'
import { homeTone } from './homeIntelligenceView'

// Section 5 — Team Explorer. Every tracked club, one click from its bullpen
// board. Clubs that show up in today's landscape carry a story hook so the
// grid invites investigation instead of reading like a directory.
export default function TeamExplorer({ explorer }) {
  return (
    <section className="mb-8" aria-label="Team explorer">
      <SectionHeading
        title="Explore Every Bullpen"
        subtitle="Pick a club and step inside its pen. The clubs carrying today's storylines lead off; everyone else follows A to Z."
      />

      {!explorer?.hasTeams ? (
        <div className="card p-5 text-sm text-chalk400">
          Team list unavailable right now — head to the Bullpen page to pick a club directly.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {explorer.items.map(team => (
            <TeamCard key={team.teamId ?? team.abbr} team={team} />
          ))}
        </div>
      )}
    </section>
  )
}

function TeamCard({ team }) {
  const tone = team.tag ? homeTone(team.tag.tone) : null

  return (
    <Link
      to={team.href || '/bullpen'}
      className="card group relative flex flex-col p-3 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
    >
      {team.tag && (
        <span
          className="absolute right-2 top-2 inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest"
          style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
        >
          <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
          {team.tag.label}
        </span>
      )}

      <span className="font-display text-2xl tracking-wider text-chalk100 group-hover:text-amber transition-colors">
        {team.abbr}
      </span>
      <span className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-chalk400">{team.name}</span>
      <span className="mt-2 font-mono text-[10px] uppercase tracking-wider text-chalk600">
        {team.armsTracked} arms tracked
      </span>
    </Link>
  )
}
