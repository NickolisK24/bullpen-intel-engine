// BaseballOS vocabulary presentation.
//
// Data authority: `utils/bullpenConcepts.js`, the single public dictionary the
// rest of the product already shares. A concept card teaches a term and points
// at where the term is used — it never carries a live value.
//
// This is deliberate. Recovery Window, Bullpen Pressure, Workload Concentration,
// Clean Options, Coverage Safety, and Trusted Arms are descriptive concepts. No
// approved public numeric state exists for them, so the card explains the idea
// and links deeper rather than inventing a number, a tier, or a rating.

import { Link } from 'react-router-dom'

export function ConceptCard({ name, definition, to, linkLabel = 'Where this shows up' }) {
  if (!name || !definition) return null
  return (
    <div className="bos-panel bos-panel--interactive flex min-w-0 flex-col p-4 sm:p-5">
      <h3 className="bos-card-title">{name}</h3>
      <p className="bos-support mt-2 flex-1">{definition}</p>
      {to && (
        <Link
          to={to}
          className="mt-4 inline-flex min-h-10 w-fit items-center font-mono text-[11px] uppercase tracking-[0.16em] text-signal transition-colors hover:text-chalk100"
        >
          {linkLabel}
          <span aria-hidden="true" className="ml-2">→</span>
        </Link>
      )}
    </div>
  )
}

// Compact definition list used where a full card grid would over-card the page.
export function ConceptGlossary({ terms = [], className = '' }) {
  const rows = (Array.isArray(terms) ? terms : []).filter(term => term?.name && term?.definition)
  if (rows.length === 0) return null
  return (
    <dl className={`grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2 ${className}`}>
      {rows.map(term => (
        <div key={term.name} className="min-w-0 border-l-2 border-line-strong pl-4">
          <dt className="font-mono text-[11px] uppercase tracking-[0.16em] text-brass">
            {term.name}
          </dt>
          <dd className="bos-support mt-1.5">{term.definition}</dd>
        </div>
      ))}
    </dl>
  )
}

export default ConceptCard
