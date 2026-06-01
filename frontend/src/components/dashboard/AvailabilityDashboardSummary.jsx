import { getAvailabilityDashboardSummaryView } from './availabilityDashboardSummaryView'

function DistributionRows({ title, rows, total }) {
  return (
    <div>
      <div className="mb-3 text-chalk600 text-[10px] font-mono uppercase tracking-wider">{title}</div>
      <div className="space-y-2.5">
        {rows.map((row) => {
          const pct = total > 0 ? Math.round((row.count / total) * 100) : 0
          return (
            <div key={row.key}>
              <div className="mb-1 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: row.style.color || '#94a3b8' }}
                    aria-hidden="true"
                  />
                  <span className="truncate font-mono text-xs text-chalk400">{row.label}</span>
                </div>
                <span className="shrink-0 font-mono text-xs font-semibold text-chalk200">
                  {row.count.toLocaleString()}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-dirt">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: row.style.color || '#94a3b8',
                  }}
                  title={`${row.label}: ${row.count.toLocaleString()} (${pct}%)`}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function AvailabilityDashboardSummary({ summary }) {
  if (!summary) return null

  const view = getAvailabilityDashboardSummaryView(summary)
  const trustClass = view.limitedByData
    ? 'border-amber/35 bg-amber/5 text-chalk200'
    : 'border-dirt bg-field/40 text-chalk400'

  return (
    <section className="card p-5 mb-8 animate-fade-up opacity-0 delay-3" style={{ animationFillMode: 'forwards' }}>
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="text-chalk400 font-mono text-xs uppercase tracking-widest">Availability Summary</div>
          <div className="mt-1 text-chalk600 font-mono text-[11px] leading-relaxed">
            {view.modeLabel} · {view.totalPitchers.toLocaleString()} classified pitchers
          </div>
        </div>
        <div className={`rounded border px-3 py-2 text-xs font-mono leading-relaxed ${trustClass}`}>
          {view.primaryTrustNote}
          {view.limitedByData && (
            <span className="block mt-1 text-chalk400">
              Show inactive pitchers or refresh sync data to inspect historical workload context.
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <DistributionRows title="Statuses" rows={view.statusRows} total={view.totalPitchers} />
        <DistributionRows title="Confidence" rows={view.confidenceRows} total={view.totalPitchers} />
        <DistributionRows title="Data State" rows={view.dataStateRows} total={view.totalPitchers} />
      </div>

      {view.notes.length > 1 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {view.notes.slice(1).map((note) => (
            <span key={note} className="rounded border border-dirt bg-chalk/30 px-2 py-1 font-mono text-[10px] text-chalk400">
              {note}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}
