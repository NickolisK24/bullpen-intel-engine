import { Link } from 'react-router-dom'
import { homeTone } from './homeIntelligenceView'

// Section 2 — four league intelligence cards: Bullpen Pressure, Recovery
// Window, Biggest Trend, Workload Concentration. Each card is a doorway into
// an existing page, not a verdict — counts and situations only.
export default function LeagueIntelligenceCards({ cards }) {
  if (!Array.isArray(cards) || cards.length === 0) return null

  return (
    <section className="mb-8" aria-label="League intelligence">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card, index) => (
          <IntelligenceCard key={card.key} card={card} delayClass={`delay-${Math.min(index + 1, 5)}`} />
        ))}
      </div>
    </section>
  )
}

function IntelligenceCard({ card, delayClass }) {
  const tone = homeTone(card.tone)

  return (
    <Link
      to={card.href}
      className={`card group flex flex-col p-4 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5 animate-fade-up ${delayClass}`}
    >
      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-chalk400">
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
        {card.title}
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        {card.team ? (
          <span className="font-display text-4xl tracking-wider text-chalk100 group-hover:text-amber transition-colors">
            {card.team.abbr || card.team.teamName}
          </span>
        ) : card.stat ? (
          <span className="font-display text-4xl tracking-wider text-chalk100 group-hover:text-amber transition-colors">
            {card.stat}
          </span>
        ) : (
          <span className="font-display text-2xl tracking-wider text-chalk400">Quiet day</span>
        )}
      </div>
      {card.team?.teamName && (
        <div className="mt-0.5 truncate text-xs text-chalk400">{card.team.teamName}</div>
      )}

      {card.stat && (
        <div className="mt-2 font-mono text-sm" style={{ color: tone.color }}>
          {card.team ? `${card.stat} ` : ''}
          <span className="text-chalk400">{card.statLabel}</span>
        </div>
      )}

      <p className="mt-2 flex-1 text-xs leading-relaxed text-chalk400">{card.line}</p>

      <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-chalk400 group-hover:text-amber transition-colors">
        {card.cta} →
      </div>
    </Link>
  )
}
