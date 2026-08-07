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
    // The action aligns with the title's baseline rather than dropping to the
    // bottom of a multi-line heading block, so it reads as part of the heading
    // instead of stranded beside the end of the subtitle.
    <div className={`mb-7 flex flex-col gap-4 md:mb-9 md:flex-row md:items-start md:justify-between md:gap-x-12 ${className}`}>
      <div className="min-w-0">
        {eyebrow && (
          <p className={`bos-eyebrow ${tone === 'brass' ? 'bos-eyebrow--brass' : ''}`}>
            {eyebrow}
          </p>
        )}
        <h2 id={id} className={`bos-section-title ${eyebrow ? 'mt-2.5' : ''}`}>
          {title}
        </h2>
        {subtitle && (
          <p className={`bos-support mt-3 ${action ? 'max-w-[52ch]' : 'max-w-measure'}`}>
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="shrink-0 md:mt-1">{action}</div>}
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
