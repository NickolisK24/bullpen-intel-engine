import { getTeamGameContextView } from './teamGameContextView'

// Today's Game Context — a compact card that frames a team's bullpen with its
// most recent stored game. Derived from stored game logs only (labelled as
// such), never presented as a live schedule. Not a scoreboard, matchup engine,
// or prediction.
const HELPER_COPY =
  'Game context is provided to frame bullpen availability and workload. BaseballOS does not provide matchup advice or game predictions.'

function Field({ label, value, muted = false }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk600">{label}</dt>
      <dd className={`mt-0.5 font-mono text-xs ${muted ? 'text-chalk500' : 'text-chalk200'}`}>{value}</dd>
    </div>
  )
}

export default function TeamGameContextCard({ gameContext, loading = false, error = null }) {
  const view = getTeamGameContextView(gameContext)

  return (
    <section className="mb-5 rounded-lg border border-dirt bg-field/60 p-4" aria-label="Today's Game Context">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-mono text-xs uppercase tracking-widest text-chalk400">Today's Game Context</h3>
        <span className="rounded border border-dirt bg-dugout px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-chalk500">
          Stored game-log context
        </span>
      </div>

      {loading ? (
        <p className="mt-3 font-mono text-xs text-chalk500">Loading game context…</p>
      ) : error ? (
        <p className="mt-3 font-mono text-xs text-chalk500">Schedule context unavailable.</p>
      ) : !view.hasContext ? (
        <p className="mt-3 font-mono text-xs text-chalk500">Schedule context unavailable.</p>
      ) : !view.isPresent ? (
        <p className="mt-3 text-sm leading-relaxed text-chalk400">
          {view.state === 'no_game_found'
            ? 'No stored game-log context found for this date.'
            : (view.message || 'Schedule context unavailable.')}
        </p>
      ) : (
        <>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Field label="Opponent" value={view.opponent || '—'} />
            <Field label="Game date" value={view.gameDate || '—'} />
            <Field label="Data" value={`${view.dataStateLabel} · ${view.confidenceLabel} confidence`} muted />
            <Field label="Status" value={view.isToday ? 'Scheduled' : 'Final'} muted />
          </dl>
          {view.missingFields.length > 0 && (
            <p className="mt-2 font-mono text-[11px] text-chalk600">
              {view.missingFields.join(' and ')} unavailable in stored game-log data.
            </p>
          )}
        </>
      )}

      <p className="mt-3 border-t border-dirt/70 pt-2 text-[11px] leading-relaxed text-chalk500">
        {HELPER_COPY}
      </p>
    </section>
  )
}
