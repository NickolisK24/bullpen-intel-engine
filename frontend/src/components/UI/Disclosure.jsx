export default function Disclosure({
  label,
  hint = null,
  children,
  open,
  defaultOpen = false,
  onToggle,
  ariaLabel,
  disabled = false,
  className = '',
  summaryClassName = '',
  contentClassName = '',
}) {
  const controlled = typeof open === 'boolean'
  const handleSummaryKeyDown = (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    if (disabled) return
    const details = event.currentTarget.parentElement
    if (details instanceof HTMLDetailsElement) details.open = !details.open
  }

  return (
    <details
      className={`rounded border border-dirt bg-dugout/45 ${className}`}
      open={controlled ? open : defaultOpen}
      onToggle={onToggle}
      aria-label={ariaLabel}
    >
      <summary
        aria-disabled={disabled || undefined}
        onClick={disabled ? event => event.preventDefault() : undefined}
        onKeyDown={handleSummaryKeyDown}
        className={`flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-chalk300 transition-colors hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60 ${summaryClassName}`}
      >
        <span>{label}</span>
        {hint && <span className="text-[10px] normal-case tracking-normal text-chalk600">{hint}</span>}
      </summary>
      <div className={`px-3 pb-3 ${contentClassName}`}>{children}</div>
    </details>
  )
}
