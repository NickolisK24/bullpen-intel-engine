import { getTeamBullpenStoryView } from './teamBullpenStoryView'
import { CONCEPT_DEFINITIONS } from '../../../utils/bullpenConcepts'
import { homeTone } from '../../home/homeIntelligenceView'

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

      <BaseballOSReads reads={story.reads} />

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

// The BaseballOS Reads strip — the four named reads in a compact row. Each
// chip explains itself on hover/focus, and the disclosure underneath spells
// out what every read means in one line.
function BaseballOSReads({ reads }) {
  if (!Array.isArray(reads) || reads.length === 0) return null

  return (
    <div className="mt-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
        BaseballOS Reads
      </div>
      <dl className="mt-2 flex flex-wrap gap-2">
        {reads.map(read => {
          const tone = homeTone(read.tone)
          return (
            <div
              key={read.key}
              className="inline-flex items-center gap-2 rounded border border-dirt bg-field/60 px-2.5 py-1"
              title={`${read.concept}: ${read.definition} ${read.detail}`}
            >
              <dt className="font-mono text-[10px] uppercase tracking-wider text-chalk400">
                {read.concept}
              </dt>
              <dd
                className="inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-wide"
                style={{ color: tone.color }}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
                {read.label}
              </dd>
            </div>
          )
        })}
      </dl>
      <details className="mt-2">
        <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
          What these mean
        </summary>
        <ul className="mt-2 space-y-1">
          {Object.values(CONCEPT_DEFINITIONS).map(concept => (
            <li key={concept.name} className="text-xs leading-relaxed text-chalk400">
              <span className="text-chalk200">{concept.name}</span> — {concept.definition}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}
