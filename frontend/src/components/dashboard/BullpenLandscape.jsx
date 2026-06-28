import { Link } from 'react-router-dom'
import { getLandscapeView, getStorylines } from './bullpenLandscapeView'

// Tonight's Storylines — a compact, scannable recap of the most notable bullpen
// situations, summarized from the same landscape data in plain baseball language.
// Descriptive only: no charts, rankings, recommendations, or predictions.
function Storylines({ storylines }) {
  return (
    <div className="card mb-4 p-4" aria-label="Tonight's Storylines">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-amber" aria-hidden="true" />
        <h3 className="font-mono text-xs uppercase tracking-widest text-chalk400">Tonight's Storylines</h3>
      </div>
      {storylines.hasStorylines ? (
        <ul className="mt-3 space-y-1.5">
          {storylines.items.map((item, index) => (
            <li key={index} className="flex gap-2 text-sm leading-relaxed text-chalk200">
              <span className="select-none text-amber" aria-hidden="true">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-chalk500">{storylines.fallback}</p>
      )}
    </div>
  )
}

// One landscape team row. When a deep link is available it becomes a lightweight
// clickable link into that team's bullpen board — informational, not a button.
function EntryRow({ entry, column }) {
  const content = (
    <>
      <span className="truncate font-medium text-chalk200 group-hover:text-amber group-hover:underline" title={entry.teamName || entry.label}>
        {entry.label}
      </span>
      <span className="flex shrink-0 items-baseline gap-1 font-mono text-xs" style={{ color: column.tone.color }}>
        {entry[column.metric]} <span className="text-chalk600">{column.suffix}</span>
        {entry.teamHref && (
          <span className="text-chalk600 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true">→</span>
        )}
      </span>
    </>
  )

  if (!entry.teamHref) {
    return <li className="flex items-baseline justify-between gap-2">{content}</li>
  }
  return (
    <li>
      <Link
        to={entry.teamHref}
        className="group -mx-1 flex cursor-pointer items-baseline justify-between gap-2 rounded px-1 py-0.5 transition-colors hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
        aria-label={`Open the bullpen board for ${entry.teamName || entry.label}`}
      >
        {content}
      </Link>
    </li>
  )
}

// Tonight's Bullpen Landscape — league-wide orientation for first-time users.
// Descriptive context only: it surfaces which bullpens are most constrained /
// most available / carrying the most monitoring. It is NOT a ranking, a
// scoreboard, or a game forecast.
function Column({ column }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: column.tone.dot }} aria-hidden="true" />
        <h4 className="font-mono text-xs uppercase tracking-widest text-chalk400">{column.title}</h4>
      </div>
      {column.entries.length === 0 ? (
        <p className="mt-3 text-xs text-chalk600">None right now.</p>
      ) : (
        <ol className="mt-3 space-y-1">
          {column.entries.map(entry => (
            <EntryRow key={entry.teamId ?? entry.label} entry={entry} column={column} />
          ))}
        </ol>
      )}
    </div>
  )
}

function displayLandscapeNote(note) {
  return String(note ?? '')
    .replace(/\bSorted deterministically by\b/gi, 'Sorted by')
    .replace(/\bdeterministically\b/gi, 'consistently')
    .replace(/\bdeterministic\b/gi, 'consistent')
    .replace(/\bendpoints\b/gi, 'data feeds')
    .replace(/\bendpoint\b/gi, 'data feed')
    .replace(/\bbackend\b/gi, 'BaseballOS service')
    .replace(/\bsnapshot\b/gi, 'read')
}

export default function BullpenLandscape({ landscape }) {
  const view = getLandscapeView(landscape)
  if (!view.hasLandscape) return null

  const storylines = getStorylines(landscape)

  return (
    <section className="mb-6" aria-label="Tonight's Bullpen Landscape">
      <div className="mb-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-chalk400">Tonight's Bullpen Landscape</h2>
        <p className="mt-1 text-xs leading-relaxed text-chalk600">
          League-wide bullpen state across {view.teamsEvaluated} tracked team{view.teamsEvaluated === 1 ? '' : 's'}.
          This is bullpen context, not a game prediction.
        </p>
      </div>

      {/* Stored games anchor */}
      <div className="mb-4 flex flex-col gap-1 rounded-lg border border-dirt bg-field/50 px-4 py-2 sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-2">
        <span className="font-mono text-[11px] uppercase tracking-widest text-chalk500">Games</span>
        <span className="font-mono text-xs leading-relaxed text-chalk300">{view.games.label}</span>
      </div>

      {/* Quick-read recap, surfaced before the individual situation columns. */}
      <Storylines storylines={storylines} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {view.columns.map(column => (
          <Column key={column.key} column={column} />
        ))}
      </div>

      {view.notes.length > 0 && (
        <ul className="mt-3 space-y-1">
          {view.notes.map((note, index) => (
            <li key={index} className="text-[11px] leading-relaxed text-chalk600">• {displayLandscapeNote(note)}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
