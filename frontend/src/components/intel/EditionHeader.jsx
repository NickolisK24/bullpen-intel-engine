// The BaseballOS signature object: the Daily Intelligence Brief masthead.
//
// This is the edition marker for a finite daily read. It carries the edition
// identity, the lead statement, and the governed temporal context that makes
// the rest of the page checkable — and nothing else.
//
// It is deliberately not a panel. The masthead sits directly on the page,
// marked by one hairline at the top edge and a very quiet field of depth behind
// it, so it reads as an edition masthead rather than as a system module. The
// left side is editorial; only the fact rail is allowed to look technical,
// because it is metadata.
//
// Data authority: every fact in the rail is supplied by the caller from
// governed application state. A fact with no current value is omitted entirely
// (`TrustFact` returns null), so the brief silently shrinks on a degraded day
// instead of showing a guessed date, an assumed coverage count, or a stale
// value presented as current. There is no hardcoded verification claim
// anywhere in this component.

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
    <header className="bos-edition bos-depth pb-10 pt-9 sm:pb-14 sm:pt-12 lg:pb-16 lg:pt-14">
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2">
        <p className="bos-eyebrow">{eyebrow}</p>
        {editionLabel && (
          <p className="bos-meta min-w-0 uppercase tracking-[0.06em] text-brass/80 sm:tracking-[0.12em]">
            {editionLabel}
          </p>
        )}
      </div>

      <div className="bos-edition-rule mt-5" aria-hidden="true" />

      {/* Lead statement and the governed rail sit side by side from lg up, so
          desktop reads as a briefing masthead rather than an oversized hero
          that consumes the first screen. Below lg they stack in reading order:
          answer first, then the context that qualifies it. */}
      <div className="mt-9 grid grid-cols-1 gap-x-14 gap-y-9 lg:mt-12 lg:grid-cols-[minmax(0,1.65fr)_minmax(13rem,0.75fr)]">
        <div className="min-w-0">
          <h1 className="bos-hero max-w-[17ch]">
            {title}
          </h1>

          {standfirst && (
            <p className="bos-body mt-6 max-w-measure text-chalk300">
              {standfirst}
            </p>
          )}

          {actions && (
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              {actions}
            </div>
          )}
        </div>

        {/* On phones the rail follows the lead statement, so the date the read
            represents stays close to the answer. From lg it becomes the
            masthead's right rail behind a hairline. */}
        {visibleFacts.length > 0 && (
          <dl className="grid min-w-0 grid-cols-2 gap-x-8 gap-y-5 border-t border-line pt-6 sm:grid-cols-3 lg:grid-cols-1 lg:gap-y-6 lg:border-l lg:border-t-0 lg:pl-10 lg:pt-1.5">
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

      {/* The boundary statement stays on the page but sits below the brief as
          an ambient line rather than competing with the lead statement. */}
      {boundary && (
        <p className="bos-support mt-9 max-w-measure text-chalk500 lg:mt-11">
          {boundary}
        </p>
      )}

      {children}
    </header>
  )
}
