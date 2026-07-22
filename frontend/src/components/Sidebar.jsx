import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useFetch } from '../hooks/useFetch'
import { getBullpenDashboard, getSyncStatus } from '../utils/api'
import { getSyncStatusView } from './dashboard/syncStatusView'
import { PRIMARY_NAV, SUPPORTING_NAV, isNavDestinationActive } from '../utils/navigation'

const PRIMARY_NAVIGATION_ID = 'primary-navigation'

export function sidebarFreshness(syncStatus, loading, error, freshnessAuthority) {
  if (loading && !syncStatus) {
    return {
      lastChecked: 'Loading',
      lastDataUpdate: 'Loading',
      dataThrough: 'Loading',
    }
  }

  if (error && !syncStatus) {
    return {
      lastChecked: 'Unavailable',
      lastDataUpdate: 'Unavailable',
      dataThrough: 'Unavailable',
    }
  }

  const view = getSyncStatusView(syncStatus, { freshnessAuthority })
  return {
    lastChecked: view.lastCheckedValue || 'Unavailable',
    lastDataUpdate: view.lastDataUpdateValue || (
      view.syncLabel === 'No data loaded' ? 'No data loaded' : 'Unavailable'
    ),
    dataThrough: view.dataValue || 'Unavailable',
  }
}

function SidebarFreshnessItem({ label, value }) {
  return (
    <div>
      <div className="font-mono text-[9px] uppercase tracking-widest text-chalk600">
        {label}
      </div>
      <div className="mt-1 font-mono text-[11px] leading-tight text-chalk200">
        {value}
      </div>
    </div>
  )
}

export function SidebarDataFreshnessCard({ freshness }) {
  return (
    <div className="rounded-lg border border-dirt/80 bg-field/45 p-3">
      <div className="mb-3 font-mono text-[9px] uppercase tracking-widest text-amber/80">
        Data Freshness
      </div>
      <div className="space-y-3">
        <SidebarFreshnessItem label="Page checked" value={freshness.lastChecked} />
        <SidebarFreshnessItem label="Latest data update" value={freshness.lastDataUpdate} />
        <SidebarFreshnessItem label="Bullpen data through" value={freshness.dataThrough} />
      </div>
    </div>
  )
}

function NavDestination({ item, location, onNavigate }) {
  const active = isNavDestinationActive(item, location)
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={`nav-item ${active ? 'active' : ''}`}
    >
      <span className="text-base w-5 text-center" aria-hidden="true">{item.icon}</span>
      <span>{item.label}</span>
    </Link>
  )
}

export default function Sidebar() {
  // Mobile-only collapsible nav. On lg+ the nav is always shown and this
  // state is irrelevant (the hamburger is hidden and `lg:flex` forces it open).
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const dashboard = useFetch(getBullpenDashboard)
  const syncStatus = useFetch(getSyncStatus)
  const freshness = sidebarFreshness(
    syncStatus.data,
    syncStatus.loading,
    syncStatus.error,
    dashboard.data?.freshness || null,
  )

  // Close the mobile menu whenever the route changes so browser back/forward,
  // deep links, and in-app navigation never leave it stuck open.
  useEffect(() => {
    setOpen(false)
  }, [location.pathname, location.search])

  // Escape closes the mobile menu, matching the close control and destination
  // selection. Only bound while open so it never interferes with the page.
  useEffect(() => {
    if (!open) return undefined
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const closeMenu = () => setOpen(false)

  return (
    <aside className="w-full bg-dugout border-b border-dirt lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:w-56 lg:border-b-0 lg:border-r flex flex-col lg:h-screen lg:overflow-y-auto">
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
          aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
          aria-expanded={open}
          aria-controls={PRIMARY_NAVIGATION_ID}
          className="lg:hidden shrink-0 ml-3 h-11 w-11 flex items-center justify-center rounded-lg border border-dirt text-chalk200 hover:bg-chalk/50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/60"
        >
          <span className="text-lg leading-none" aria-hidden="true">{open ? '✕' : '☰'}</span>
        </button>
      </div>

      {/* Nav — hidden on mobile until toggled, always visible on lg+. Primary
          bullpen destinations first, then the supporting trust/explainer pages,
          kept visually distinct so first-time visitors can tell them apart. */}
      <nav
        id={PRIMARY_NAVIGATION_ID}
        aria-label="Primary"
        className={`${open ? 'flex' : 'hidden'} lg:flex flex-1 flex-col px-3 pb-4 pt-1 lg:py-5`}
      >
        <div className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <NavDestination key={item.key} item={item} location={location} onNavigate={closeMenu} />
          ))}
        </div>

        <div className="mt-4 border-t border-dirt pt-3">
          <div className="px-4 pb-1 font-mono text-[9px] uppercase tracking-widest text-chalk600">
            Learn &amp; Trust
          </div>
          <div className="space-y-1">
            {SUPPORTING_NAV.map((item) => (
              <NavDestination key={item.key} item={item} location={location} onNavigate={closeMenu} />
            ))}
          </div>
        </div>
      </nav>

      {/* Footer — follows the nav's mobile visibility, always shown on lg+ */}
      <div className={`${open ? 'block' : 'hidden'} lg:block mt-auto px-4 py-4 border-t border-dirt`}>
        <div className="space-y-3">
          <SidebarDataFreshnessCard freshness={freshness} />
        </div>
      </div>
    </aside>
  )
}
