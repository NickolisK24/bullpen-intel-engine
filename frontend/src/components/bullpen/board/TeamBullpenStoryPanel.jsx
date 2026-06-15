import { getTeamBullpenStoryView } from './teamBullpenStoryView'
import { CONCEPT_DEFINITIONS } from '../../../utils/bullpenConcepts'
import { homeTone } from '../../home/homeIntelligenceView'

// Team Story Surface V1 — a compact analyst note that sits between the
// context strips and the availability board. It explains what BaseballOS sees
// inside this bullpen before the user reaches the detailed classifications.
export default function TeamBullpenStoryPanel({ board }) {
  const story = getTeamBullpenStoryView(board)
  if (!story.hasStory) return null

  return (
    <section
      className="mb-6 rounded-lg border border-dirt bg-dugout p-4 sm:p-5"
      aria-label="Team bullpen intelligence"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
          What BaseballOS Sees About This Bullpen
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

      <div className="mt-3 grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
            Observation
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-chalk200">{story.observation}</p>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
            Why It Matters
          </div>
          <p className="mt-1 text-sm leading-relaxed text-chalk200">{story.whyItMatters}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
            Evidence
          </div>
          <ul className="mt-2 space-y-1.5">
            {story.evidence.map((bullet, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk200">• {bullet}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk400">
            What BaseballOS Is Watching
          </div>
          <ul className="mt-2 space-y-1.5">
            {story.watchItems.map((bullet, index) => (
              <li key={index} className="text-xs leading-relaxed text-chalk200">• {bullet}</li>
            ))}
          </ul>
        </div>
      </div>

      <BaseballOSReads reads={story.reads} />

      <TeamBullpenShape reads={story.shapeReads} />

      <p className="mt-3 border-t border-dirt/60 pt-2 text-[11px] text-chalk600">{story.framing}</p>
    </section>
  )
}

function TeamBullpenShape({ reads }) {
  if (!Array.isArray(reads) || reads.length === 0) return null

  return (
    <section className="mt-4 border-t border-dirt/60 pt-3" aria-label="Today’s bullpen shape">
      <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">
        Today’s Bullpen Shape
      </div>
      <dl className="mt-2 grid gap-x-4 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-5">
        {reads.map(read => {
          const tone = homeTone(read.tone)
          return (
            <div key={read.key} className="min-w-0">
              <dt className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                {read.concept}
              </dt>
              <dd
                className="mt-0.5 min-w-0"
                title={read.explanation}
                aria-label={`${read.label}. ${read.explanation}`}
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
                  <span className="min-w-0 text-xs font-semibold leading-snug text-chalk100">
                    {read.label}
                  </span>
                </div>
                <p className="sr-only sm:not-sr-only sm:mt-0.5 sm:block sm:text-[11px] sm:leading-snug sm:text-chalk500">
                  {read.explanation}
                </p>
              </dd>
            </div>
          )
        })}
      </dl>
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
