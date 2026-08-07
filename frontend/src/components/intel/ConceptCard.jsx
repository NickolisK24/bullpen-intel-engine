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

import ConceptGlyph from './ConceptGlyph'

// A named BaseballOS concept: an abstract mark, a large title, one concise
// explanation, and a route to where the term is used. The mark gives the
// vocabulary a recognizable identity; it is decorative and aria-hidden, and it
// can never carry a value because the glyph geometry is fixed.
export function ConceptCard({ name, definition, glyph, to, linkLabel = 'Where this shows up' }) {
  if (!name || !definition) return null
  return (
    // Open cell rather than a card: a top hairline, generous space, and type.
    <div className="flex min-w-0 flex-col border-t border-line pt-5 sm:pt-6">
      {glyph && <ConceptGlyph name={glyph} className="mb-4 text-signal/80 sm:mb-6" />}
      <h3 className="bos-concept-title">{name}</h3>
      <p className="bos-support mt-3 flex-1">{definition}</p>
      {to && (
        <Link to={to} className="bos-link mt-4 w-fit">
          {linkLabel}
          <span aria-hidden="true">&#8594;</span>
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
    <dl className={`grid grid-cols-1 gap-x-14 gap-y-6 sm:grid-cols-2 ${className}`}>
      {rows.map(term => (
        <div key={term.name} className="min-w-0">
          <dt className="text-[1.0625rem] font-semibold tracking-[-0.014em] text-brass">
            {term.name}
          </dt>
          <dd className="bos-support mt-1.5">{term.definition}</dd>
        </div>
      ))}
    </dl>
  )
}

export default ConceptCard
