import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/',            icon: '⬡',  label: 'Dashboard'   },
  { to: '/bullpen',     icon: '🔥', label: 'Bullpen'     },
  { to: '/prospects',   icon: '📈', label: 'Pipeline'    },
  { to: '/methodology', icon: '📐', label: 'Methodology' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-dugout border-r border-dirt flex flex-col min-h-screen sticky top-0">
      {/* Logo */}
      <div className="px-5 py-6 border-b border-dirt">
        <div className="flex items-center gap-2.5">
          <span className="text-2xl">⚾</span>
          <div>
            <div className="font-display text-2xl tracking-widest text-chalk100 leading-none">BaseballOS</div>
            <div className="text-chalk600 text-[10px] font-mono uppercase tracking-widest mt-0.5">Analytics Platform</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-5 space-y-1">
        {NAV.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <span className="text-base w-5 text-center">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-dirt">
        <div className="text-chalk600 text-[10px] font-mono leading-relaxed">
          <div className="text-chalk400 font-medium mb-1">Nikko</div>
          <div>Army Vet · Developer</div>
          <div className="mt-1 text-amber/70">Building to break in.</div>
        </div>
      </div>
    </aside>
  )
}