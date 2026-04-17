// Thin horizontal rule. Optional `label` renders centered text on the line.
// `variant` — "solid" (default) or "dashed".
export default function Divider({ label, variant = 'solid' }) {
  const borderStyle = variant === 'dashed' ? 'border-dashed' : 'border-solid'

  if (!label) {
    return <div className={`my-4 border-t ${borderStyle} border-dirt`} />
  }

  return (
    <div className="flex items-center gap-3 my-4">
      <div className={`flex-1 border-t ${borderStyle} border-dirt`} />
      <span className="text-chalk600 text-xs font-mono uppercase tracking-widest whitespace-nowrap">
        {label}
      </span>
      <div className={`flex-1 border-t ${borderStyle} border-dirt`} />
    </div>
  )
}
