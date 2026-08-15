import { Link } from 'react-router-dom'

const LINKS = [
  { to: '/how-to-read', label: 'Start Here' },
  { to: '/about', label: 'About' },
  { to: '/methodology', label: 'Methodology' },
  { to: '/trust', label: 'Data & Trust' },
]

export default function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-ink">
      <div className="bos-page flex flex-col gap-5 py-7 md:flex-row md:items-center md:justify-between">
        <p className="max-w-[76ch] text-xs leading-5 text-chalk500">
          BaseballOS is an independent bullpen intelligence platform and is not affiliated with or endorsed by Major League Baseball or its clubs. Reads describe observable present conditions drawn from public sources.
        </p>
        <nav aria-label="Learn and trust pages" className="flex shrink-0 flex-wrap gap-x-5 gap-y-3">
          {LINKS.map(link => (
            <Link key={link.to} to={link.to} className="font-mono text-[10px] uppercase tracking-[0.12em] text-chalk400 hover:text-chalk100">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  )
}
