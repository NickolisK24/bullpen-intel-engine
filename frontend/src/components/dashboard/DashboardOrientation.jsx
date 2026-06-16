import { Link } from 'react-router-dom'

// Dashboard Orientation Layer — a compact, always-visible "this is what this
// product does" strip. Product comprehension only: it explains BaseballOS and
// points to the next click. No analytics, recommendations, rankings, predictions,
// onboarding flows, or marketing copy.
const GUIDANCE = [
  { label: 'Explore Current Bullpen Landscape', to: null },          // the section just below
  { label: 'Select a team bullpen', to: '/bullpen?view=board' },
  { label: 'Compare bullpen conditions across teams', to: '/bullpen?view=compare' },
]

export default function DashboardOrientation() {
  return (
    <section
      className="mb-6 rounded-lg border border-dirt bg-field/40 px-4 py-3"
      aria-label="What BaseballOS is"
    >
      <div className="flex flex-col gap-2 lg:flex-row lg:items-baseline lg:justify-between lg:gap-6">
        <div className="min-w-0">
          <h2 className="font-mono text-xs uppercase tracking-widest text-amber/80">
            Bullpen Availability &amp; Workload Intelligence
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-chalk300">
            BaseballOS helps you understand bullpen availability, workload, readiness, and
            constraints across Major League Baseball bullpens — transparently, with the data
            date and confidence always shown.
          </p>
        </div>

        <div className="shrink-0 text-xs font-mono text-chalk500">
          <span className="uppercase tracking-widest text-chalk600">Start by</span>
          <ul className="mt-1 space-y-0.5">
            {GUIDANCE.map(item => (
              <li key={item.label} className="flex items-baseline gap-1.5">
                <span className="text-chalk600" aria-hidden="true">•</span>
                {item.to ? (
                  <Link to={item.to} className="text-chalk300 hover:text-amber hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
                    {item.label}
                  </Link>
                ) : (
                  <span className="text-chalk400">{item.label}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
