// The public BaseballOS navigation shell.
//
// (The file keeps its historical `Sidebar.jsx` path so the eleven suites that
// import it by path stay untouched; the component it exports is the masthead.)
//
// From lg up this is a horizontal masthead: wordmark left, the six primary
// destinations centre, the ambient data-through stamp right. Below lg it is a
// compact header with a menu sheet. The public surfaces read as a publication
// rather than as an internal tool, so the navigation stays low-profile and the
// content owns the page.

import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useFetch } from '../hooks/useFetch'
import { getBullpenDashboard, getSyncStatus } from '../utils/api'
import { getSyncStatusView } from './dashboard/syncStatusView'
import { MASTHEAD_NAV, PRIMARY_NAV, SUPPORTING_NAV, isNavDestinationActive } from '../utils/navigation'

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
      <div className="text-[0.75rem] leading-snug text-chalk500">
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
    <div className="rounded-panel border border-line bg-panel-2 p-3">
      <div className="mb-3 text-[0.6875rem] font-medium uppercase tracking-[0.09em] text-signal">
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

// A destination in the mobile menu sheet: a full-width row with a blue rail on
// the active entry, paired with aria-current so the state never depends on
// colour alone.
function NavDestination({ item, location, onNavigate }) {
  const active = isNavDestinationActive(item, location)
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={`nav-item ${active ? 'active' : ''}`}
    >
      <span>{item.label}</span>
    </Link>
  )
}

// A destination in the desktop masthead: quiet text that brightens, marked
// active by a thin blue underline rather than a filled tab or a pill.
function MastheadDestination({ item, location }) {
  const active = isNavDestinationActive(item, location)
  return (
    <Link
      to={item.to}
      aria-current={active ? 'page' : undefined}
      className={`nav-top ${active ? 'active' : ''}`}
    >
      {item.label}
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

  // The masthead stamp is a claim about the data, so it appears only when the
  // application actually served one. Loading and unavailable are states of the
  // request, not dates, and never render as an ambient fact.
  const hasPublishedDataThrough = Boolean(freshness.dataThrough)
    && !['Loading', 'Unavailable', 'No data loaded'].includes(freshness.dataThrough)

  const wordmark = (
    <Link
      to="/"
      onClick={closeMenu}
      aria-current={location.pathname === '/' ? 'page' : undefined}
      className="flex min-w-0 shrink-0 items-center gap-2.5 rounded-panel focus:outline-none"
      aria-label="BaseballOS home"
    >
      <span
        aria-hidden="true"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-panel border border-signal/35 bg-signal-well font-mono text-[12px] font-semibold tracking-tight text-signal"
      >
        OS
      </span>
      <span className="min-w-0">
        <span className="block truncate font-display text-[1.375rem] leading-none tracking-[0.16em] text-chalk100">
          BaseballOS
        </span>
        <span className="mt-0.5 block text-[0.625rem] font-medium uppercase tracking-[0.11em] text-chalk600">
          Bullpen Intelligence
        </span>
      </span>
    </Link>
  )

  return (
    <header className="bos-masthead">
      <div className="bos-page flex h-16 items-center justify-between gap-6 lg:h-[4.5rem]">
        {wordmark}

        {/* Desktop masthead navigation. Only the six primary public
            destinations appear here; the supporting explainer and trust pages
            stay reachable from the footer, the menu sheet, and in-page links,
            so the masthead does not become a directory. */}
        <nav aria-label="Primary" className="hidden min-w-0 lg:flex lg:items-center lg:gap-1">
          {MASTHEAD_NAV.map((item) => (
            <MastheadDestination key={item.key} item={item} location={location} />
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-4">
          {/* Freshness is ambient: the represented baseball date sits in the
              masthead on every surface, not only where a page repeats it. */}
          {hasPublishedDataThrough && (
            <span className="hidden font-mono text-[11px] leading-tight text-chalk500 xl:inline">
              Data through <span className="text-chalk300">{freshness.dataThrough}</span>
            </span>
          )}

          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={open}
            aria-controls={PRIMARY_NAVIGATION_ID}
            className="lg:hidden h-11 w-11 flex shrink-0 items-center justify-center rounded-control border border-line text-chalk200 transition-colors hover:border-line-strong hover:bg-panel-2 focus:outline-none"
          >
            <span className="text-lg leading-none" aria-hidden="true">{open ? '\u2715' : '\u2630'}</span>
          </button>
        </div>
      </div>

      {/* Menu sheet — below lg only. Every destination lives here, including the
          supporting pages the desktop masthead deliberately leaves out. */}
      <div
        id={PRIMARY_NAVIGATION_ID}
        className={`${open ? 'block' : 'hidden'} border-t border-line lg:hidden`}
      >
        <div className="bos-page py-4">
          <nav aria-label="All destinations" className="flex flex-col">
            <div className="space-y-0.5">
              {PRIMARY_NAV.map((item) => (
                <NavDestination key={item.key} item={item} location={location} onNavigate={closeMenu} />
              ))}
            </div>

            <div className="mt-6 border-t border-line pt-4">
              <div className="px-4 pb-2 text-[0.6875rem] font-medium uppercase tracking-[0.09em] text-chalk600">
                Learn &amp; Trust
              </div>
              <div className="space-y-0.5">
                {SUPPORTING_NAV.map((item) => (
                  <NavDestination key={item.key} item={item} location={location} onNavigate={closeMenu} />
                ))}
              </div>
            </div>
          </nav>

          <div className="mt-6">
            <SidebarDataFreshnessCard freshness={freshness} />
          </div>
        </div>
      </div>
    </header>
  )
}
