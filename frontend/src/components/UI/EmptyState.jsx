export default function EmptyState({ icon = '⚾', title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="text-4xl opacity-30">{icon}</div>
      {title && <p className="text-chalk200 font-medium">{title}</p>}
      {subtitle && <p className="text-chalk400 text-sm">{subtitle}</p>}
    </div>
  )
}
