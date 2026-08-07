// Evidence receipts — the inspectable half of every claim.
//
// Data authority: whichever backend contract supplied the row. Nothing here
// derives, totals, ranks, or rewrites an evidence value; the components only
// give supplied strings a consistent, scannable shape so evidence reads as a
// receipt rather than as body copy.
//
// `EvidenceList` is for short backend-authored evidence lines. `EvidenceRow`
// is for a labelled value pair. `NamedArmReceipt` is the compact named-reliever
// form: a name is content, so it gets its own recognizable object.

export function EvidenceList({ items = [], label, className = '' }) {
  const rows = (Array.isArray(items) ? items : []).filter(Boolean)
  if (rows.length === 0) return null
  return (
    <div className={className}>
      {label && <p className="bos-micro">{label}</p>}
      <ul className={label ? 'mt-2 space-y-1.5' : 'space-y-1.5'}>
        {rows.map(item => (
          <li key={item} className="flex gap-2.5">
            <span
              aria-hidden="true"
              className="mt-2 h-px w-3 shrink-0 bg-line-strong"
            />
            <span className="bos-evidence min-w-0 break-words">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function EvidenceRow({ label, value, detail, className = '' }) {
  if (value == null || value === '') return null
  return (
    <div className={`flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line py-2 last:border-b-0 ${className}`}>
      <dt className="bos-evidence min-w-0 text-chalk400">{label}</dt>
      <dd className="flex min-w-0 flex-wrap items-baseline gap-x-2 font-mono text-[13px] tabular-nums text-chalk100">
        <span>{value}</span>
        {detail && <span className="text-chalk500">{detail}</span>}
      </dd>
    </div>
  )
}

// A named arm carrying recent work. `name` is required; every other field is
// rendered only when the contract supplied it.
export function NamedArmReceipt({ name, detail, note, className = '' }) {
  if (!name) return null
  return (
    <li className={`flex min-w-0 flex-col gap-0.5 border-l-2 border-line-strong py-1 pl-3 ${className}`}>
      <span className="truncate text-sm font-medium text-chalk100">{name}</span>
      {detail && (
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-chalk500">
          {detail}
        </span>
      )}
      {note && <span className="bos-meta normal-case">{note}</span>}
    </li>
  )
}

export function NamedArmReceipts({ label, children, className = '' }) {
  return (
    <div className={className}>
      {label && <p className="bos-micro">{label}</p>}
      <ul className={`${label ? 'mt-2' : ''} grid grid-cols-1 gap-2 sm:grid-cols-2`}>
        {children}
      </ul>
    </div>
  )
}

export default EvidenceList
