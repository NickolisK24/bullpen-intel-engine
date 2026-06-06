import { getLandscapeView } from './bullpenLandscapeView'

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
        <ol className="mt-3 space-y-2">
          {column.entries.map(entry => (
            <li key={entry.teamId ?? entry.label} className="flex items-baseline justify-between gap-2">
              <span className="truncate font-medium text-chalk200" title={entry.teamName || entry.label}>
                {entry.label}
              </span>
              <span className="shrink-0 font-mono text-xs" style={{ color: column.tone.color }}>
                {entry[column.metric]} <span className="text-chalk600">{column.suffix}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

export default function BullpenLandscape({ landscape }) {
  const view = getLandscapeView(landscape)
  if (!view.hasLandscape) return null

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
      <div className="mb-4 rounded-lg border border-dirt bg-field/50 px-4 py-2">
        <span className="font-mono text-[11px] uppercase tracking-widest text-chalk500">Games</span>
        <span className="ml-2 font-mono text-xs text-chalk300">{view.games.label}</span>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {view.columns.map(column => (
          <Column key={column.key} column={column} />
        ))}
      </div>

      {view.notes.length > 0 && (
        <ul className="mt-3 space-y-1">
          {view.notes.map((note, index) => (
            <li key={index} className="text-[11px] leading-relaxed text-chalk600">• {note}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
