// Bold section heading with subtle bottom border. `action` renders right-aligned.
//
// `as` chooses the heading element. It defaults to `h2` because almost every
// caller is a section inside a page that already owns its own H1 — the internal
// admin surfaces in particular render their H1 above this component, and a
// global promotion would give them two. A caller that IS the page's identity
// opts in explicitly with `as="h1"`; today that is only the /bullpen route
// shell, which is the one public route with no other level-one heading.
//
// The visual treatment is identical either way: `.section-title` carries all of
// it, so the semantic level changes without the page changing size.
export default function SectionHeader({ title, subtitle, action, as: Heading = 'h2' }) {
  return (
    <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3 lg:gap-4 mb-6 pb-3 border-b border-dirt">
      <div className="min-w-0">
        <Heading className="section-title">{title}</Heading>
        {subtitle && (
          <p className="text-chalk400 text-sm mt-1 font-mono">{subtitle}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
