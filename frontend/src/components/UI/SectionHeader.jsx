// Bold section heading with subtle bottom border. `action` renders right-aligned.
export default function SectionHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-6 pb-3 border-b border-dirt">
      <div className="min-w-0">
        <h2 className="section-title">{title}</h2>
        {subtitle && (
          <p className="text-chalk400 text-sm mt-1 font-mono">{subtitle}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
