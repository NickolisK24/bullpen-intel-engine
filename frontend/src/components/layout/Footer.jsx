const CONNECT_LINKS = [
  {
    label: 'X: @baseballoshq',
    href: 'https://x.com/baseballoshq',
    ariaLabel: 'BaseballOS on X',
  },
  {
    label: 'Instagram: @baseballoshq',
    href: 'https://instagram.com/baseballoshq',
    ariaLabel: 'BaseballOS on Instagram',
  },
  {
    label: 'Email: baseballoshq@gmail.com',
    href: 'mailto:baseballoshq@gmail.com',
    ariaLabel: 'Email BaseballOS',
  },
]

function FooterHeading({ children }) {
  return (
    <h2 className="font-mono text-[10px] uppercase tracking-widest text-chalk600">
      {children}
    </h2>
  )
}

function ConnectLinks() {
  return (
    <div>
      <FooterHeading>Connect</FooterHeading>
      <ul className="mt-4 space-y-2.5">
        {CONNECT_LINKS.map(link => (
          <li key={link.href}>
            <a
              href={link.href}
              aria-label={link.ariaLabel}
              target={link.href.startsWith('http') ? '_blank' : undefined}
              rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
              className="text-sm text-chalk300 transition-colors hover:text-amber"
            >
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Footer() {
  return (
    <footer className="border-t border-dirt bg-field/95 px-5 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="max-w-xl">
            <div className="font-display text-2xl uppercase tracking-widest text-chalk100">
              BaseballOS
            </div>
            <p className="mt-3 max-w-lg text-sm leading-6 text-chalk400">
              Public MLB bullpen intelligence — a daily read on which bullpens
              are fresh, stretched, or vulnerable, and why.
            </p>
          </div>

          <ConnectLinks />
        </div>

        <div className="mt-10 border-t border-dirt pt-6">
          <div className="grid grid-cols-1 gap-4 text-xs leading-5 text-chalk500 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.8fr)_auto] lg:items-start">
            <p className="font-mono uppercase tracking-widest text-chalk300">
              Making bullpen context easier to understand.
            </p>
            <p>
              BaseballOS is an independent baseball intelligence platform and is
              not affiliated with or endorsed by Major League Baseball or its
              clubs. Data is descriptive and drawn from public sources.
            </p>
            <p className="font-mono uppercase tracking-widest text-chalk600 lg:text-right">
              © 2026 BaseballOS · All rights reserved.
            </p>
          </div>
        </div>
      </div>
    </footer>
  )
}
