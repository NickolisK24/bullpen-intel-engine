const VALID_STATUSES = new Set(['partial', 'error', 'unavailable'])

export default function SectionState({
  status = 'partial',
  title,
  message,
  onRetry,
  actionLabel = 'Try again',
  children,
  className = '',
}) {
  const resolvedStatus = VALID_STATUSES.has(status) ? status : 'partial'
  const role = resolvedStatus === 'error' ? 'alert' : 'status'

  return (
    <section
      className={`section-state section-state--${resolvedStatus} ${className}`.trim()}
      role={role}
      aria-live={resolvedStatus === 'error' ? 'assertive' : 'polite'}
      data-state={resolvedStatus}
    >
      {title && <h3 className="type-section-title">{title}</h3>}
      {message && <p className="type-compact mt-meta break-words">{message}</p>}
      {children && <div className="mt-row min-w-0">{children}</div>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="section-state__action min-h-11">
          {actionLabel}
        </button>
      )}
    </section>
  )
}
