export const FEEDBACK_FORM_URL = 'https://forms.gle/NLCmLEtwJy4qamf77'

export function FeedbackLink({
  children = 'Give Feedback',
  className = '',
  ariaLabel = 'Give Feedback',
  ...props
}) {
  return (
    <a
      href={FEEDBACK_FORM_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={ariaLabel}
      className={className}
      {...props}
    >
      {children}
    </a>
  )
}

export function FeedbackCTA({
  title,
  body,
  eyebrow = 'User Feedback',
  className = '',
  compact = false,
}) {
  const shellClass = compact
    ? 'rounded border border-dirt bg-dugout/60 px-4 py-3'
    : 'card p-5'

  return (
    <section className={`${shellClass} ${className}`.trim()} aria-label={title}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          {eyebrow && (
            <div className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
              {eyebrow}
            </div>
          )}
          <h2 className={`${compact ? 'text-base' : 'text-xl'} mt-1 font-display tracking-wide text-chalk100`}>
            {title}
          </h2>
          {body && (
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-chalk400">
              {body}
            </p>
          )}
        </div>
        <FeedbackLink className="inline-flex shrink-0 items-center justify-center rounded border border-amber/30 bg-amber/5 px-3 py-2 font-mono text-xs uppercase tracking-wider text-amber transition-colors hover:border-amber/60 hover:bg-amber/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60">
          Give Feedback
        </FeedbackLink>
      </div>
    </section>
  )
}

export default FeedbackLink
