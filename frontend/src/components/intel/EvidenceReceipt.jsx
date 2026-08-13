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

import { Children, cloneElement, isValidElement } from 'react'

export function EvidenceList({ items = [], label, className = '' }) {
  const rows = (Array.isArray(items) ? items : []).filter(Boolean)
  if (rows.length === 0) return null
  return (
    <div className={className}>
      {label && <p className="bos-micro">{label}</p>}
      <ul className={label ? 'mt-3' : ''}>
        {rows.map((item, index) => (
          <li key={item} className="grid grid-cols-[22px_1px_minmax(0,1fr)] gap-x-3 py-2 first:pt-0">
            <span aria-hidden="true" className="font-mono text-[11px] tabular-nums text-brass-deep">
              E{index + 1}
            </span>
            <span aria-hidden="true" className="h-full min-h-6 bg-line" />
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
export function NamedArmReceipt({ name, detail, note, index, className = '' }) {
  if (!name) return null
  return (
    <li className={`grid min-w-0 grid-cols-[22px_1px_minmax(0,1fr)] gap-x-3 py-1 ${className}`}>
      <span aria-hidden="true" className="font-mono text-[11px] tabular-nums text-brass-deep">E{index || '—'}</span>
      <span aria-hidden="true" className="h-full min-h-10 bg-line" />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-base font-medium text-chalk100">{name}</span>
        {detail && <span className="font-mono text-sm tabular-nums text-chalk300">{detail}</span>}
        {note && <span className="text-[0.84375rem] leading-snug text-chalk400">{note}</span>}
      </span>
    </li>
  )
}

export function NamedArmReceipts({ label, children, className = '' }) {
  const indexedChildren = Children.map(children, (child, index) => (
    isValidElement(child) ? cloneElement(child, { index: index + 1 }) : child
  ))
  return (
    <div className={className}>
      {label && <p className="bos-micro">{label}</p>}
      <ul className={`${label ? 'mt-3' : ''} grid grid-cols-1 gap-3 sm:grid-cols-2`}>
        {indexedChildren}
      </ul>
    </div>
  )
}

export default EvidenceList
