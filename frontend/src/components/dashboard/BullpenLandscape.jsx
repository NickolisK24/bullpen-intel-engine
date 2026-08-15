import { Link } from 'react-router-dom'
import { Disclosure } from '../UI'
import { getLandscapeView, getStorylines } from './bullpenLandscapeView'

// Backend-authored Storylines — presented verbatim, with no client-side recap.
function Storylines({ storylines }) {
  if (!storylines.hasStorylines) return null
  return (
    <div className="card mb-4 p-4" aria-label="Storylines">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-amber" aria-hidden="true" />
        <h3 className="font-mono text-xs uppercase tracking-widest text-chalk400">Storylines</h3>
      </div>
      <ul className="mt-3 space-y-1.5">
        {storylines.items.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm leading-relaxed text-chalk200">
            <span className="select-none text-amber" aria-hidden="true">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// One landscape team row. When a deep link is available it becomes a lightweight
// clickable link into that team's bullpen board — informational, not a button.
// The canonical Team State chip. It shows only a backend-supplied Fresh /
// Stretched / Vulnerable label; a fail-closed read shows no chip at all rather
// than a fourth state. The label is text, so it reads without color.
function TeamStateChip({ teamState }) {
  if (!teamState?.available) return null
  return (
    <span
      className="inline-flex min-h-7 shrink-0 items-center rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-wider"
      style={{ borderColor: teamState.tone.borderColor, color: teamState.tone.color }}
    >
      {teamState.publicLabel}
    </span>
  )
}

function EntryRow({ entry, column }) {
  const metric = entry[column.metric]
  const content = (
    <>
      <span className="flex min-w-0 flex-wrap items-center gap-1.5">
        <span className="font-medium text-chalk200 group-hover:text-amber group-hover:underline">
          {entry.label}
        </span>
        <TeamStateChip teamState={entry.teamState} />
      </span>
      <span className="flex shrink-0 items-baseline gap-1 font-mono text-xs" style={{ color: column.tone.color }}>
        {metric == null ? 'Withheld' : metric} {metric != null && <span className="text-chalk600">{column.suffix}</span>}
        {entry.teamHref && (
          <span className="text-chalk600 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true">→</span>
        )}
      </span>
    </>
  )

  if (!entry.teamHref) {
    return <li className="flex min-h-11 items-center justify-between gap-2">{content}</li>
  }
  return (
    <li>
      <Link
        to={entry.teamHref}
        className="group -mx-1 flex min-h-11 cursor-pointer items-center justify-between gap-2 rounded px-1 py-1 transition-colors hover:bg-amber/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
        aria-label={`Open the bullpen board for ${entry.teamName || entry.label}`}
      >
        {content}
      </Link>
    </li>
  )
}

// Bullpen Landscape — partial league orientation for first-time users.
// Descriptive context only: the published lanes are not a ranking, scoreboard,
// complete league grouping, or game forecast.
function Column({ column }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: column.tone.dot }} aria-hidden="true" />
        <h4 className="font-mono text-xs uppercase tracking-widest text-chalk400">{column.title}</h4>
      </div>
      {column.subtitle && (
        <p className="mt-1 text-xs leading-relaxed text-chalk600">{column.subtitle}</p>
      )}
      {column.entries.length === 0 ? (
        <p className="mt-3 text-xs text-chalk600">None right now.</p>
      ) : (
        <ul className="mt-3 space-y-1">
          {column.entries.map(entry => (
            <EntryRow key={entry.teamId ?? entry.label} entry={entry} column={column} />
          ))}
        </ul>
      )}
    </div>
  )
}

// Landscape notes are backend-authored public sentences
// (services/game_context.py). They render verbatim: this component no longer
// rewrites BaseballOS public copy on its way to the reader.
function displayLandscapeNote(note) {
  return String(note ?? '')
}

export default function BullpenLandscape({ landscape }) {
  const view = getLandscapeView(landscape)
  if (!view.hasLandscape) return null

  const storylines = getStorylines(landscape)

  return (
    <section className="mb-6" aria-label="Bullpen Landscape">
      {/* Existing storylines lead; the partial lanes are supporting context. */}
      <Storylines storylines={storylines} />
      <div className="mb-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-chalk400">Published Situation Lanes</h2>
        <p className="mt-1 text-xs leading-relaxed text-chalk600">
          {view.teamsEvaluated == null
            ? 'Partial league context from the current published landscape.'
            : `Partial league context from ${view.teamsEvaluated} club${view.teamsEvaluated === 1 ? '' : 's'} in the current published landscape.`}
          {' '}
          These lanes are descriptive, not a complete league grouping or game prediction.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {view.columns.map(column => (
          <Column key={column.key} column={column} />
        ))}
      </div>

      {view.notes.length > 0 && (
        <Disclosure label="Limits on these lanes" className="mt-3">
          <ul className="space-y-1">
            {view.notes.map((note, index) => (
              <li key={index} className="text-[11px] leading-relaxed text-chalk600">• {displayLandscapeNote(note)}</li>
            ))}
          </ul>
        </Disclosure>
      )}
    </section>
  )
}
