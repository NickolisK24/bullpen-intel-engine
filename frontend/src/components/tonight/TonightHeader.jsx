import { TONIGHT_COPY, editionHeader, summaryItems } from './tonightView'

export default function TonightHeader({ edition, summary }) {
  const { dateLabel, dataThroughLabel } = editionHeader(edition)
  const items = summaryItems(summary)
  return (
    <header className="min-w-0 border-b border-dirt pb-panel" data-testid="tonight-header">
      <h1 className="font-display text-3xl leading-none tracking-wide text-chalk100 sm:text-4xl lg:text-5xl">
        {TONIGHT_COPY.title}
      </h1>
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
}
