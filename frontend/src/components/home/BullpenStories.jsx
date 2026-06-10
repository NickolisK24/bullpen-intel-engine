import { Link } from 'react-router-dom'
import { homeTone } from './homeIntelligenceView'

// Section 3 — Today's Bullpen Stories. Observation-led story cards in plain
// baseball language: what the workload data shows, never what anyone should
// do about it.
export default function BullpenStories({ stories }) {
  return (
    <section className="mb-8" aria-label="Today's bullpen stories">
      <SectionHeading
        title="Today’s Bullpen Stories"
        subtitle="What the workload data is saying around the league — observations, not verdicts."
      />

      {!stories?.hasStories ? (
        <div className="card p-5 text-sm text-chalk400">{stories?.fallback}</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {stories.items.map((story, index) => (
            <StoryCard key={`${story.kicker}-${index}`} story={story} />
          ))}
        </div>
      )}
    </section>
  )
}

export function SectionHeading({ title, subtitle, right }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2 border-b border-dirt pb-2">
      <div>
        <h2 className="font-display text-2xl tracking-wider text-chalk100 uppercase">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-chalk400">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

function StoryCard({ story }) {
  const tone = homeTone(story.tone)

  return (
    <Link
      to={story.href || '/bullpen'}
      className="card group flex flex-col p-4 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
    >
      <span
        className="inline-flex w-fit items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
        style={{ borderColor: tone.borderColor, backgroundColor: tone.backgroundColor, color: tone.color }}
      >
        <span className="h-1 w-1 rounded-full" style={{ backgroundColor: tone.dot }} aria-hidden="true" />
        {story.kicker}
      </span>

      <h3 className="mt-3 font-display text-xl leading-tight tracking-wide text-chalk100 group-hover:text-amber transition-colors">
        {story.title}
      </h3>

      <p className="mt-2 flex-1 text-sm leading-relaxed text-chalk400">{story.body}</p>

      <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-chalk600 group-hover:text-amber transition-colors">
        Open the full picture →
      </div>
    </Link>
  )
}
