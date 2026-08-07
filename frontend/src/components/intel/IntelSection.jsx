// Section heading system for the intelligence surfaces.
//
// A section is a labelled region of the page, not another card: an eyebrow, a
// display headline, an optional one-line orientation sentence, and an optional
// aligned action. Sections are separated by rhythm and a hairline (`bos-section`
// in index.css) so a page reads as an authored sequence rather than a grid of
// equal-weight tiles.

export function SectionHeading({
  id,
  eyebrow,
  title,
  subtitle,
  action,
  tone = 'signal',
  className = '',
}) {
  return (
    <div className={`mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between ${className}`}>
      <div className="min-w-0">
        {eyebrow && (
          <p className={`bos-eyebrow ${tone === 'brass' ? 'bos-eyebrow--brass' : ''}`}>
            {eyebrow}
          </p>
        )}
        <h2 id={id} className="bos-section-title mt-2">
          {title}
        </h2>
        {subtitle && (
          <p className="bos-support mt-2 max-w-measure">
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="shrink-0 md:pb-1">{action}</div>}
    </div>
  )
}

export default function IntelSection({
  id,
  eyebrow,
  title,
  subtitle,
  action,
  tone,
  children,
  className = '',
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={`bos-section ${className}`}
    >
      <SectionHeading
        id={`${id}-title`}
        eyebrow={eyebrow}
        title={title}
        subtitle={subtitle}
        action={action}
        tone={tone}
      />
      {children}
    </section>
  )
}
