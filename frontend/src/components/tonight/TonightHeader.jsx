import { forwardRef } from 'react'
import { SkeletonBlock } from '../UI'
import { TONIGHT_COPY, editionHeader, summaryItems } from './tonightView'

// Rendered in every page state at the same tree position, so the h1 node is
// stable across loading → error → retry → loaded and can hold focus.
const TonightHeader = forwardRef(function TonightHeader({ edition = null, summary = null, loading = false }, ref) {
  const { dateLabel, dataThroughLabel } = editionHeader(edition)
  const items = summaryItems(summary)
  return (
    <header className="min-w-0 border-b border-dirt pb-panel" data-testid="tonight-header">
      <h1
        ref={ref}
        tabIndex={-1}
        className="font-display text-3xl leading-none tracking-wide text-chalk100 focus:outline-none sm:text-4xl lg:text-5xl"
      >
        {TONIGHT_COPY.title}
      </h1>
      {loading && (
        <div aria-hidden="true" data-testid="tonight-header-skeleton">
          <SkeletonBlock className="mt-2 h-4 w-40" />
          <SkeletonBlock className="mt-1 h-4 w-32" />
          <SkeletonBlock className="mt-3 h-5 w-full max-w-xl" />
        </div>
      )}
      {dateLabel && (
        <p className="mt-2 font-mono text-xs uppercase tracking-widest text-chalk300" data-testid="tonight-date">
          {dateLabel}
        </p>
      )}
      {dataThroughLabel && (
        <p className="mt-1 text-xs text-chalk400" data-testid="tonight-data-through">
          {dataThroughLabel}
        </p>
      )}
      {items.length > 0 && (
        <ul className="mt-3 flex min-w-0 flex-wrap gap-x-4 gap-y-1 text-sm text-chalk200" aria-label="Tonight summary" data-testid="tonight-summary">
          {items.map(item => (
            <li key={item.key} className="min-w-0 break-words" data-summary={item.key}>
              {item.text}
            </li>
          ))}
        </ul>
      )}
    </header>
  )
})

export default TonightHeader
