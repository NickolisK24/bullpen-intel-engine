import { getTeamBullpenStoryView } from './teamBullpenStoryView'

// Today's Bullpen Story — a compact analyst note that sits between the
// context strips and the availability board. It answers why BaseballOS is
// watching this pen, what the workload shape says, and what to look at on
// the board below. Additive context only; the board remains the detail.
export default function TeamBullpenStoryPanel({ board }) {
  const story = getTeamBullpenStoryView(board)
  if (!story.hasStory) return null

  return (
    <section
      className="mb-6 rounded-lg border border-dirt bg-dugout p-4 sm:p-5"
      aria-label="Today's bullpen story"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
          Why BaseballOS Is Watching This Pen
        </div>
        <span
          className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
          style={story.tone}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: story.tone.dot }} aria-hidden="true" />
          {story.label}
        </span>
      </div>

      <h3 className="mt-2 font-display text-2xl leading-tight tracking-wide text-chalk100">
        {story.headline}
      </h3>

      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-chalk200">{story.summary}</p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
            What The Workload Shape Says
          </div>
          <ul className="mt-2 space-y-1.5">
            {story.workloadBullets.map((bullet, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk200">• {bullet}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
            What To Watch On The Board
          </div>
          <ul className="mt-2 space-y-1.5">
            {story.watchBullets.map((bullet, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk200">• {bullet}</li>
            ))}
          </ul>
        </div>
      </div>

      <p className="mt-3 border-t border-dirt/60 pt-2 text-[11px] text-chalk600">{story.framing}</p>
    </section>
  )
}
