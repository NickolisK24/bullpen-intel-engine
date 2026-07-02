const CONNECT_LINKS = [
  {
    key: 'x',
    href: 'https://x.com/baseballoshq',
    ariaLabel: 'BaseballOS on X',
    external: true,
  },
  {
    key: 'instagram',
    href: 'https://instagram.com/baseballoshq',
    ariaLabel: 'BaseballOS on Instagram',
    external: true,
  },
  {
    key: 'email',
    href: 'mailto:baseballoshq@gmail.com',
    ariaLabel: 'Email BaseballOS',
    external: false,
  },
]

function ConnectIcon({ type }) {
  if (type === 'x') {
    return (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="5" y="5" width="14" height="14" rx="4" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="3.2" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="16.7" cy="7.3" r="1" fill="currentColor" />
      </svg>
    )
  }

  if (type === 'email') {
    return (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="4" y="6" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <path d="M5 8l7 5 7-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }

  return null
}

function ConnectLinks() {
  return (
    <div className="mt-5 flex items-center justify-center gap-3">
      {CONNECT_LINKS.map(link => (
        <a
          key={link.href}
          href={link.href}
          aria-label={link.ariaLabel}
          target={link.external ? '_blank' : undefined}
          rel={link.external ? 'noopener noreferrer' : undefined}
          className="inline-flex h-11 w-11 items-center justify-center rounded border border-dirt bg-field/70 text-chalk300 transition-colors hover:border-amber/50 hover:bg-amber/10 hover:text-amber focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
        >
          <ConnectIcon type={link.key} />
        </a>
      ))}
    </div>
  )
}

export default function Footer() {
  return (
    <footer className="border-t border-dirt bg-field/95 px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl rounded-lg border border-dirt bg-dugout/80 px-5 py-7 text-center sm:px-8">
        <div className="font-display text-2xl uppercase tracking-widest text-chalk100">
          BaseballOS
        </div>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-chalk400">
          Public MLB bullpen intelligence — a daily read on which bullpens are
          fresh, stretched, or vulnerable, and why.
        </p>

        <ConnectLinks />

        <div className="mt-6 border-t border-dirt pt-5">
          <p className="mx-auto max-w-2xl text-xs leading-5 text-chalk500">
            BaseballOS is an independent baseball intelligence platform and is
            not affiliated with or endorsed by Major League Baseball or its
            clubs.
          </p>
          <p className="mt-2 text-xs leading-5 text-chalk500">
            Data is descriptive and drawn from public sources.
          </p>
          <p className="mt-5 font-mono text-[11px] uppercase tracking-widest text-chalk600">
            © 2026 BaseballOS — All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  )
}
