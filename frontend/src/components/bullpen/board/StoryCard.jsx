import { getStoryCardView } from './storyCardView'

function MetaPill({ children }) {
  if (!children) return null
  return (
    <span className="rounded border border-dirt bg-field/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-chalk500">
      {children}
    </span>
  )
}

function StoryShell({ children, tone = 'default' }) {
  const toneClass = tone === 'neutral'
    ? 'border-dirt bg-field/55'
    : tone === 'error'
      ? 'border-amber/30 bg-amber/5'
      : 'border-dirt bg-dugout/75'
  return (
    <section className={`mb-5 rounded-lg border p-4 sm:p-5 ${toneClass}`} aria-label="Bullpen story note">
      {children}
    </section>
  )
}

export default function StoryCard({
  story,
  loading = false,
  error = null,
  onRetry,
}) {
  if (loading) {
    return (
      <StoryShell tone="neutral">
        <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">Bullpen Note</div>
        <p className="mt-2 font-mono text-xs text-chalk500">Checking the team story note...</p>
      </StoryShell>
    )
  }

  if (error) {
    return (
      <StoryShell tone="error">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">Bullpen Note</div>
        <h3 className="mt-2 font-display text-xl tracking-wide text-chalk100">Story note paused</h3>
        <p className="mt-2 text-sm leading-relaxed text-chalk400">
          The bullpen board is still available; BaseballOS is holding this note until it can load cleanly.
        </p>
        {typeof onRetry === 'function' && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded border border-dirt bg-dugout px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-chalk300 transition-colors hover:border-amber/40 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
          >
            Retry note
          </button>
        )}
      </StoryShell>
    )
  }

  const view = getStoryCardView(story)

  if (!view.available) {
    return (
      <StoryShell tone="neutral">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-mono text-[10px] uppercase tracking-widest text-chalk500">Bullpen Note</div>
          <div className="flex flex-wrap gap-1.5">
            {view.meta.map(item => <MetaPill key={item}>{item}</MetaPill>)}
          </div>
        </div>
        <h3 className="mt-2 font-display text-xl tracking-wide text-chalk100">{view.title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-chalk400">{view.message}</p>
      </StoryShell>
    )
  }

  return (
    <StoryShell>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-mono text-[10px] uppercase tracking-widest text-amber/70">Bullpen Note</div>
        <div className="flex flex-wrap gap-1.5">
          {view.meta.map(item => <MetaPill key={item}>{item}</MetaPill>)}
        </div>
      </div>

      <h3 className="mt-2 font-display text-2xl leading-tight tracking-wide text-chalk100">
        {view.title}
      </h3>

      {view.paragraphs.length > 0 && (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {view.paragraphs.map(item => (
            <section key={item.key} className="min-w-0 border-l border-dirt/80 pl-3">
              <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
                {item.label}
              </div>
              <p className="mt-1 text-sm leading-relaxed text-chalk200">{item.text}</p>
            </section>
          ))}
        </div>
      )}
    </StoryShell>
  )
}
