import { Link } from 'react-router-dom'
import { homeTone } from './homeIntelligenceView'

// Section 3 — Today's Short List. The briefing cut: only the few stories that
// matter most this morning, in plain baseball language — what the workload
// data shows, never what anyone should do about it. The full feed lives on
// the Stories page.
export const SHORT_LIST_LIMIT = 3

export default function BullpenStories({ stories }) {
  const shortList = (Array.isArray(stories?.items) ? stories.items : []).slice(0, SHORT_LIST_LIMIT)

  return (
    <section className="mb-8" aria-label="Today's short list">
      <SectionHeading
        title="Today’s Short List"
        subtitle="The bullpen stories that matter most this morning."
      />

      {!stories?.hasStories ? (
        <div className="card p-5 text-sm text-chalk400">{stories?.fallback}</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shortList.map((story, index) => (
            <StoryCard key={`${story.kicker}-${index}`} story={story} />
          ))}
        </div>
      )}

      <div className="mt-3 text-right">
        <Link
          to="/stories"
          className="inline-flex items-center rounded border border-dirt bg-dugout px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-chalk200 transition-colors hover:border-amber/40 hover:text-amber"
        >
          Open the full story feed →
        </Link>
      </div>
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

// A story card is a doorway: team stories step into that club's bullpen
// board, league notes open the league view, data notes open Data & Trust.
// A story with no meaningful destination renders as plain copy — no CTA, no
// pretend link.
function StoryCard({ story }) {
  const tone = homeTone(story.tone)
  const hasDestination = Boolean(story.href)

  const inner = (
    <>
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

      {hasDestination && (
        <div className="mt-3 font-mono text-[10px] uppercase tracking-widest text-chalk600 group-hover:text-amber transition-colors">
          {story.cta || 'Open the full picture'} →
        </div>
      )}
    </>
  )

  if (!hasDestination) {
    return <article className="card flex flex-col p-4">{inner}</article>
  }

  return (
    <Link
      to={story.href}
      className="card group flex flex-col p-4 transition-all duration-200 hover:border-amber/40 hover:bg-amber/5"
    >
      {inner}
    </Link>
  )
}
