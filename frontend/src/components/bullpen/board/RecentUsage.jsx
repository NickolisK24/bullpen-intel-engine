import { getRecentUsageView } from './recentUsageView'

function Shell({ children }) {
  return (
    <section
      className="self-start rounded border border-dirt bg-field/45 p-3"
      aria-labelledby="recent-usage-title"
      data-testid="recent-usage"
    >
      <h2 id="recent-usage-title" className="text-chalk600 text-[10px] font-mono uppercase tracking-wider">
        Recent Usage
      </h2>
      {children}
    </section>
  )
}

export default function RecentUsage({ payload, loading = false, error = null }) {
  if (loading) {
    return <Shell><p className="mt-2 font-mono text-sm text-chalk400">Loading recent usage…</p></Shell>
  }

  const view = getRecentUsageView(payload)
  if (error || !view.available) {
    return <Shell><p className="mt-2 font-mono text-sm text-chalk400">Recent usage unavailable.</p></Shell>
  }

  return (
    <Shell>
      <div className="mt-2 space-y-1.5">
        {view.summaryLines.map((sentence) => (
          <p key={sentence} className="font-mono text-sm leading-relaxed text-chalk200">{sentence}</p>
        ))}
      </div>
      {view.mostRecentSentence && (
        <div className="mt-3 border-t border-dirt/60 pt-2">
          <div className="font-mono text-[10px] uppercase tracking-wider text-chalk600">Most recent relief work</div>
          <p className="mt-1 font-mono text-sm leading-relaxed text-chalk200">{view.mostRecentSentence}</p>
        </div>
      )}
      {view.limitation && (
        <p className="mt-2 border-l-2 border-amber/40 pl-2 font-mono text-xs leading-relaxed text-chalk400">
          {view.limitation}
        </p>
      )}
    </Shell>
  )
}
