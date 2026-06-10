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

// The BaseballOS Reads strip — the four named reads in one tight row. Each
// chip pairs a muted concept name with its tone-colored value and explains
// itself on hover/focus; the collapsed disclosure carries the plain-English
// definitions so the chips themselves stay light.
function BaseballOSReads({ reads }) {
  if (!Array.isArray(reads) || reads.length === 0) return null

  return (
    <div className="mt-4">
      <dl className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5">
        <dt className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
          BaseballOS Reads
        </dt>
        {reads.map(read => {
          const tone = homeTone(read.tone)
          return (
            <dd
              key={read.key}
              className="inline-flex items-center gap-1.5 rounded border border-dirt/70 bg-field/40 px-2 py-0.5"
              title={`${read.display}: ${read.detail}`}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
              <span className="font-mono text-[10px] uppercase tracking-wide text-chalk400">{read.concept}</span>
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wide" style={{ color: tone.color }}>
                {read.label}
              </span>
            </dd>
          )
        })}
      </dl>
      <details className="mt-1.5">
        <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-chalk600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
          What these mean
        </summary>
        <ul className="mt-1.5 space-y-1">
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
