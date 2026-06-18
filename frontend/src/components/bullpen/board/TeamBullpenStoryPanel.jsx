import { getTeamBullpenStoryView } from './teamBullpenStoryView'
import { homeTone } from '../../home/homeIntelligenceView'
import TeamShareButton from '../../share/TeamShareButton'

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
        <div className="flex flex-wrap items-center justify-end gap-2">
          <TeamShareButton team={board?.team} />
          <span
            className="inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
            style={story.tone}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: story.tone.dot }} aria-hidden="true" />
            {story.label}
          </span>
        </div>
      </div>

      <h3 className="mt-2 font-display text-2xl leading-tight tracking-wide text-chalk100">
        {story.headline}
      </h3>

      <StoryNarrative text={story.narrative || story.observation} />

      <TeamBullpenShape reads={story.shapeReads} />

      <p className="mt-3 border-t border-dirt/60 pt-2 text-[11px] text-chalk600">{story.framing}</p>
    </section>
  )
}

function StoryNarrative({ text }) {
  const paragraphs = typeof text === 'string'
    ? text.split(/\n{2,}/).map(paragraph => paragraph.trim()).filter(Boolean)
    : []
  if (paragraphs.length === 0) return null

  return (
    <div className="mt-3 max-w-3xl space-y-2">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="text-sm leading-relaxed text-chalk200">{paragraph}</p>
      ))}
    </div>
  )
}

function TeamBullpenShape({ reads }) {
  if (!Array.isArray(reads) || reads.length === 0) return null

  return (
    <section className="mt-4 border-t border-dirt/60 pt-3" aria-label="Today’s bullpen shape">
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-widest text-amber/70">
        <span>Today’s Bullpen Shape</span>
        <span className="text-chalk600">{reads.length} reads</span>
      </div>
      <dl className="mt-2 grid gap-x-4 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
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
