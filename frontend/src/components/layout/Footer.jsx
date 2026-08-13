import { Link } from 'react-router-dom'

// Trust-first footer navigation: the explainer and trust surfaces stay one
// click away from the bottom of every page.
const LEARN_LINKS = [
  { to: '/about', label: 'About' },
  { to: '/how-to-read', label: 'How to Read' },
  { to: '/methodology', label: 'Methodology' },
  { to: '/trust', label: 'Data & Trust' },
]

const CONNECT_LINKS = [
  {
    key: 'x',
    href: 'https://x.com/baseballoshq',
    ariaLabel: 'BaseballOS on X',
    external: true,
    iconClassName: 'text-chalk100 hover:text-amber',
  },
  {
    key: 'instagram',
    href: 'https://instagram.com/baseballoshq',
    ariaLabel: 'BaseballOS on Instagram',
    external: true,
    iconClassName: 'text-chalk300 hover:text-amber',
  },
  {
    key: 'email',
    href: 'mailto:baseballoshq@gmail.com',
    ariaLabel: 'Email BaseballOS',
    external: false,
    iconClassName: 'text-amber/80 hover:text-amber',
  },
]

function ConnectIcon({ type }) {
  if (type === 'x') {
    return (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M6.5 5.5l11 13m0-13l-11 13"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    )
  }

  if (type === 'instagram') {
    return (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="5" y="5" width="14" height="14" rx="4" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="3.2" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="16.7" cy="7.3" r="1" fill="currentColor" />
      </svg>
    )
  }

  if (type === 'email') {
    return (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="4" y="6" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <path d="M5 8l7 5 7-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }

  return null
}

function ConnectLinks() {
  return (
    <div className="flex items-center gap-2">
      {CONNECT_LINKS.map(link => (
        <a
          key={link.href}
          href={link.href}
          aria-label={link.ariaLabel}
          target={link.external ? '_blank' : undefined}
          rel={link.external ? 'noopener noreferrer' : undefined}
          className={`inline-flex h-[2.875rem] w-[2.875rem] items-center justify-center border border-line transition-colors hover:border-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-signal ${link.iconClassName}`}
        >
          <ConnectIcon type={link.key} />
        </a>
      ))}
    </div>
  )
}

export default function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-ink">
      <div className="bos-page py-8">
        <div className="grid gap-7 md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
          <div>
            <div className="font-display text-[1.1875rem] font-bold uppercase tracking-[0.15em] text-chalk100">BASEBALLOS</div>
            <p className="mt-2 max-w-measure text-sm leading-6 text-chalk400">
              Public MLB bullpen intelligence — a daily read on which bullpens are fresh, stretched, or vulnerable, and why.
            </p>
          </div>
          <ConnectLinks />
        </div>

        <nav aria-label="Learn and trust pages" className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-line pt-5">
          {LEARN_LINKS.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className="font-mono text-[11px] uppercase tracking-widest text-chalk400 transition-colors hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="mt-5 grid gap-2 border-t border-line pt-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          <div>
          <p className="max-w-definition text-xs leading-5 text-chalk500">
            BaseballOS is an independent baseball intelligence platform and is
            not affiliated with or endorsed by Major League Baseball or its
            clubs.
          </p>
          <p className="mt-2 text-xs leading-5 text-chalk500">
            Data is descriptive and drawn from public sources.
          </p>
          </div>
          <p className="font-mono text-[11px] uppercase tracking-widest text-chalk600">
            © 2026 BaseballOS — All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  )
}
