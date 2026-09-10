import { getStorylines } from './bullpenLandscapeView'

// Storylines remain backend-authored and optional. No league conclusion is
// generated from Team State distribution in the browser.
export default function DashboardStorylines({ landscape }) {
  const storylines = getStorylines(landscape)
  if (!storylines.hasStorylines) return null
  return (
    <section className="card mb-6 p-4" aria-label="Storylines">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-amber" aria-hidden="true" />
        <h2 className="font-mono text-xs uppercase tracking-widest text-chalk400">Storylines</h2>
      </div>
      <ul className="mt-3 space-y-1.5">
        {storylines.items.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm leading-relaxed text-chalk200">
            <span className="select-none text-amber" aria-hidden="true">•</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
