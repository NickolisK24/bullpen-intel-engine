export default function WorkloadOverview({ read }) {
  return (
    <section className="rounded-lg border border-dirt bg-field/40 p-3.5" aria-labelledby="workload-overview-title">
      <h2 id="workload-overview-title" className="font-display text-lg tracking-wide text-chalk100">Workload Overview</h2>
      {!read ? (
        <p className="mt-2 text-xs text-chalk500">Workload overview unavailable</p>
      ) : (
        <div className="mt-2">
          <div className="font-display text-base tracking-wide text-chalk100">{read.label}</div>
          <p className="mt-1 text-xs leading-relaxed text-chalk400">{read.summary}</p>
        </div>
      )}
    </section>
  )
}
