// The BaseballOS signature object: the Daily Intelligence Brief masthead.
//
// This is the edition marker for a finite daily read. It carries the edition
// identity, the date the edition represents, and the governed temporal context
// that makes the rest of the page checkable — and nothing else.
//
// It is deliberately not a panel. The masthead sits directly on the page,
// marked by one hairline at the top edge and a very quiet field of depth behind
// it, so it reads as an edition masthead rather than as a system module. The
// left side is editorial; only the fact rail is allowed to look technical,
// because it is metadata.
//
// The title is a nameplate, not a statement. A masthead names the publication
// and dates the issue; it does not argue for the product, describe what the
// product can do for the reader, or ask the reader to go somewhere. Those are
// landing-page moves, and on a daily edition they push the day's baseball below
// the first screen. The edition's first substantive read follows immediately
// after this header.
//
// Data authority: every fact in the rail — and the dateline — is supplied by
// the caller from governed application state. A fact with no current value is
// omitted entirely (`TrustFact` returns null), and the dateline disappears when
// no represented date was served, so the brief silently shrinks on a degraded
// day instead of showing a guessed date, an assumed coverage count, or a stale
// value presented as current. The dateline is never taken from the reader's
// clock: an edition is dated by the baseball date it represents, not by when
// the page happened to be opened. There is no hardcoded verification claim
// anywhere in this component.

import { TrustFact } from './TrustStrip'

export default function EditionHeader({
  eyebrow,
  editionLabel,
  shortEditionLabel,
  title,
  editionDate,
  editionDateLabel,
  standfirst,
  facts = [],
  actions,
  children,
}) {
  const visibleFacts = (Array.isArray(facts) ? facts : []).filter(fact => fact?.value)

  return (
    <header className="bos-edition bos-depth pb-4 pt-9 sm:pb-6 sm:pt-12 lg:pb-8 lg:pt-14">
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2">
        <p className="bos-eyebrow">{eyebrow}</p>
        {/* The full masthead strapline is a desktop object. On a phone the
            eyebrow above already carries the edition identity, so only the
            cadence survives — the long line crowded the gutter and added a
            second competing label to the opening screen. */}
        {editionLabel && (
          <p className="bos-meta min-w-0 uppercase tracking-[0.12em] text-brass/80">
            <span className="hidden sm:inline">{editionLabel}</span>
            <span className="sm:hidden">{shortEditionLabel || editionLabel}</span>
          </p>
        )}
      </div>

      <div className="bos-edition-rule mt-5" aria-hidden="true" />

      {/* Nameplate, dateline, then the governed facts as a full-width bar
          beneath them — the order a masthead actually has.

          These used to sit in two columns, with the facts as a right rail. That
          worked while the left column carried a lead statement, a paragraph,
          and two buttons tall enough to balance five stacked facts. With the
          left column reduced to what a masthead owes the reader, the same grid
          left a column of dead space the height of the rail before the first
          read. A single column removes it, and the fact bar reads as the
          dateline furniture it is. */}
      <div className="mt-8 lg:mt-9">
        <h1 className="bos-hero">
          {title}
        </h1>

        {/* The dateline: the baseball date this edition represents, stated
            immediately under the nameplate the way a masthead dates an issue.
            Rendered only when the application served a date. */}
        {editionDate && (
          <p className="bos-value mt-5 text-sm text-chalk200 sm:text-base">
            {editionDateLabel && (
              <span className="bos-meta mr-2 text-chalk500">{editionDateLabel}</span>
            )}
            {editionDate}
          </p>
        )}

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

        {visibleFacts.length > 0 && (
          <dl className="mt-8 grid grid-cols-2 gap-x-8 gap-y-5 border-t border-line pt-6 sm:grid-cols-3 lg:mt-9 lg:grid-cols-5 lg:gap-x-10">
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

      {children}
    </header>
  )
}
