import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import FeedbackLink from './feedback/FeedbackLink'
import { usePreferredTeamPreference } from '../hooks/usePreferredTeamPreference'
import {
  buildPreferredTeamHref,
  preferredTeamLabel,
  preferredTeamShortLabel,
} from '../utils/preferredTeam'

const NAV = [
  { to: '/',            icon: '☀',  label: 'Today'       },
  { to: '/stories',     icon: '📰', label: 'Stories'     },
  { to: '/dashboard',   icon: '⬡',  label: 'Dashboard'   },
  { to: '/bullpen',     icon: '🔥', label: 'Bullpen'     },
  { to: '/methodology', icon: '📐', label: 'Methodology' },
  { to: '/trust',       icon: '🛡', label: 'Data & Trust' },
]

export default function Sidebar() {
  // Mobile-only collapsible nav. On lg+ the nav is always shown and this
  // state is irrelevant (the hamburger is hidden and `lg:flex` forces it open).
  const [open, setOpen] = useState(false)
  const { preferredTeam } = usePreferredTeamPreference()
  const preferredHref = buildPreferredTeamHref(preferredTeam, 'nav-my-team')

  return (
    <aside className="w-full lg:w-56 lg:shrink-0 bg-dugout border-b border-dirt lg:border-b-0 lg:border-r flex flex-col lg:min-h-screen lg:sticky lg:top-0">
      {/* Header row: logo + (mobile) hamburger */}
      <div className="flex items-center justify-between px-5 py-4 lg:py-6 lg:border-b lg:border-dirt">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-2xl">⚾</span>
          <div className="min-w-0">
            <div className="font-display text-2xl tracking-widest text-chalk100 leading-none truncate">BaseballOS</div>
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-widest mt-0.5">Bullpen Intelligence</div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle navigation"
          aria-expanded={open}
          className="lg:hidden shrink-0 ml-3 w-9 h-9 flex items-center justify-center rounded-lg border border-dirt text-chalk200 hover:bg-chalk/50 transition-colors"
        >
          <span className="text-lg leading-none">{open ? '✕' : '☰'}</span>
        </button>
      </div>

      {/* Nav — hidden on mobile until toggled, always visible on lg+ */}
      <nav className={`${open ? 'flex' : 'hidden'} lg:flex flex-1 flex-col px-3 pb-4 pt-1 lg:py-5 space-y-1`}>
        {NAV.map(({ to, icon, label, tag }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <span className="text-base w-5 text-center">{icon}</span>
            <span>{label}</span>
            {tag && (
              <span className="ml-auto text-[9px] font-mono uppercase tracking-widest text-chalk600 border border-dirt rounded px-1 py-0.5">
                {tag}
              </span>
            )}
          </NavLink>
        ))}
        {preferredTeam && (
          <NavLink
            to={preferredHref}
            onClick={() => setOpen(false)}
            className="mt-3 rounded-lg border border-dirt bg-field/40 px-3 py-2.5 text-left transition-colors hover:border-amber/30 hover:bg-amber/5"
          >
            <div className="font-mono text-[9px] uppercase tracking-widest text-chalk500">
              Following
            </div>
            <div className="mt-1.5 flex min-w-0 items-center gap-2">
              <span className="inline-flex h-6 w-8 shrink-0 items-center justify-center rounded border border-amber/25 bg-amber/5 font-mono text-[10px] tracking-wide text-amber">
                {preferredTeamShortLabel(preferredTeam).slice(0, 3)}
              </span>
              <span className="min-w-0 truncate text-sm text-chalk200">
                {preferredTeamLabel(preferredTeam)}
              </span>
            </div>
          </NavLink>
        )}
        <FeedbackLink
          className="nav-item"
          onClick={() => setOpen(false)}
        >
          <span className="text-base w-5 text-center">✎</span>
          <span>Give Feedback</span>
        </FeedbackLink>
      </nav>

      {/* Footer — follows the nav's mobile visibility, always shown on lg+ */}
      <div className={`${open ? 'block' : 'hidden'} lg:block px-5 py-4 border-t border-dirt`}>
        <div className="text-chalk600 text-[10px] font-mono leading-relaxed">
          <div className="text-chalk400 font-medium mb-1">Nikko</div>
          <div>Army Vet · Developer</div>
          <div className="mt-1 text-amber/70">Building to break in.</div>
          <div className="mt-3 border-t border-dirt pt-3 leading-relaxed">
            <div className="text-chalk500">Building BaseballOS in public. Have feedback?</div>
            <FeedbackLink className="mt-1 inline-flex text-amber/80 hover:text-amber hover:underline">
              Give Feedback
            </FeedbackLink>
          </div>
        </div>
      </div>
    </aside>
  )
}
