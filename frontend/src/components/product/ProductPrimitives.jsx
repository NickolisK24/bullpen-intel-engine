import { Link } from 'react-router-dom'

export const STATE_DEFINITIONS = {
  fresh: 'Comparatively stronger rested coverage and operating room.',
  stretched: 'Recent workload or coverage has narrowed the clean options.',
  vulnerable: 'A materially constrained picture with limited margin if more work is required.',
  withheld: 'The evidence required for a current Team State is incomplete.',
}

export function displayDate(value, { weekday = false } = {}) {
  if (!value) return null
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    month: 'long',
    day: 'numeric',
    year: weekday ? undefined : 'numeric',
    weekday: weekday ? 'long' : undefined,
  }).format(date)
}

export function ProductPageHeader({ eyebrow, title, description, facts = [] }) {
  const visibleFacts = facts.filter(fact => fact?.value)
  return (
    <header className="border-b border-line pb-6 md:pb-7">
      <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <p className="bos-eyebrow text-brass">{eyebrow}</p>
          <h1 className="mt-2 font-display text-[2.25rem] font-semibold leading-[1.05] tracking-[-0.015em] text-chalk100 md:text-[3rem]">
            {title}
          </h1>
          {description && <p className="mt-3 max-w-definition text-[0.9375rem] leading-6 text-chalk400">{description}</p>}
        </div>
        {visibleFacts.length > 0 && (
          <dl className="grid shrink-0 gap-1 text-left font-mono text-[11px] leading-5 text-chalk500 md:text-right">
            {visibleFacts.map(fact => (
              <div key={fact.label} className="flex gap-2 md:justify-end">
                <dt>{fact.label}</dt>
                <dd className="text-chalk300">{fact.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </header>
  )
}

export function StateRead({ state, label }) {
  const key = String(state || '').toLowerCase()
  const tone = {
    fresh: 'text-pine',
    stretched: 'text-warning',
    vulnerable: 'text-danger',
  }[key] || 'text-chalk400'
  return (
    <span className={`inline-flex items-center gap-2 font-display text-sm font-bold uppercase tracking-[0.16em] ${tone}`}>
      <span className="text-[0.65em]" aria-hidden="true">◆</span>
      <span className="sr-only">Team State: </span>{label || key || 'Withheld'}
    </span>
  )
}

export function QuietState({ title = 'No current read', children }) {
  return (
    <div className="border-l-2 border-line-strong py-2 pl-4">
      <p className="bos-eyebrow text-chalk500">{title}</p>
      <p className="mt-2 max-w-measure text-sm leading-6 text-chalk400">{children}</p>
    </div>
  )
}

export function TeamRoute({ team, children, source = 'league-board' }) {
  if (!team?.team_id) return children
  return (
    <Link to={`/bullpen?view=board&team=${team.team_id}&source=${source}`} className="focus:outline-none">
      {children}
    </Link>
  )
}
