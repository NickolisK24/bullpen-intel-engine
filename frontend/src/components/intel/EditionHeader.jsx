// The BaseballOS signature object: the Daily Intelligence Brief masthead.
//
// This is the edition marker for a finite daily read. It carries the edition
// identity, the lead statement, and the governed temporal context that makes
// the rest of the page checkable — and nothing else.
//
// Data authority: every fact in the masthead rail is supplied by the caller
// from governed application state. A fact with no current value is omitted
// entirely (`TrustFact` returns null), so the brief silently shrinks on a
// degraded day instead of showing a guessed date, an assumed coverage count,
// or a stale value presented as current. There is no hardcoded verification
// claim anywhere in this component.

import { TrustFact } from './TrustStrip'

export default function EditionHeader({
  eyebrow,
  editionLabel,
  title,
  standfirst,
  boundary,
  facts = [],
  actions,
  children,
}) {
  const visibleFacts = (Array.isArray(facts) ? facts : []).filter(fact => fact?.value)

  return (
    <header className="bos-edition overflow-hidden">
      <div className="px-4 pb-6 pt-6 sm:px-7 sm:pb-8 sm:pt-8 lg:px-9 lg:pb-9 lg:pt-9">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <p className="bos-eyebrow">{eyebrow}</p>
          {editionLabel && (
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-brass">
              {editionLabel}
            </p>
          )}
        </div>

        <div className="bos-edition-rule mt-4" aria-hidden="true" />

        {/* Lead statement and the governed rail sit side by side from lg up, so
            desktop reads as a briefing masthead instead of an oversized hero
            that consumes the first screen. Below lg they stack in reading
            order: answer first, then the context that qualifies it. */}
        <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(14rem,0.8fr)]">
          <div className="min-w-0">
            <h1 className="bos-hero max-w-[19ch]">
              {title}
            </h1>

            {standfirst && (
              <p className="bos-body mt-5 max-w-measure text-chalk300">
                {standfirst}
              </p>
            )}

            {boundary && (
              <p className="bos-meta mt-3 max-w-measure normal-case">
                {boundary}
              </p>
            )}
          </div>

          {/* On phones the rail follows the lead statement directly, so the
              date the read represents is reachable in the same short scroll as
              the answer. From lg it becomes the masthead's right rail. */}
          {visibleFacts.length > 0 && (
            <dl className="grid min-w-0 grid-cols-2 gap-x-6 gap-y-4 border-t border-line pt-5 sm:grid-cols-3 lg:grid-cols-1 lg:gap-y-4 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-1">
              {visibleFacts.map(fact => (
                <TrustFact
                  key={fact.label}
                  label={fact.label}
                  value={fact.value}
                  detail={fact.detail}
                />
              ))}
            </dl>
          )}
        </div>

        {actions && (
          <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            {actions}
          </div>
        )}

        {children}
      </div>
    </header>
  )
}
