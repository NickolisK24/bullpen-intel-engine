const COPY = Object.freeze({
  unavailable: 'Not published',
  partial: 'Limited evidence',
  unknown: 'Unknown',
  error: 'Unavailable',
})

export default function CompactSectionState({ status = 'unavailable', title, message, className = '' }) {
  const label = title || COPY[status] || COPY.unavailable
  return (
    <div
      className={`rounded-sm border border-line-subtle bg-surface-raised/20 px-panel py-row ${className}`}
      role={status === 'error' ? 'alert' : 'status'}
      data-state={status}
    >
      <p className="type-compact text-text-secondary">
        <span className="font-semibold text-text-primary">{label}</span>
        {message ? <span className="text-text-tertiary"> · {message}</span> : null}
      </p>
    </div>
  )
}
