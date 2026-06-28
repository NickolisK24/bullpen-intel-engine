import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuthState } from '../hooks/useAuthState'
import { useFetch } from '../hooks/useFetch'
import { usePreferredTeamPreference } from '../hooks/usePreferredTeamPreference'
import { getSyncStatus, getTeams } from '../utils/api'
import {
  buildPreferredTeamHref,
  preferredTeamLabel,
} from '../utils/preferredTeam'
import { getSyncStatusView } from './dashboard/syncStatusView'
import TeamMark from './team/TeamMark'

const NAV = [
  { to: '/',            icon: '☀',  label: 'Today'       },
  { to: '/dashboard',   icon: '⬡',  label: 'Dashboard'   },
  { to: '/bullpen',     icon: '🔥', label: 'Bullpen'     },
  { to: '/stories',     icon: '📰', label: 'Stories'     },
  { to: '/methodology', icon: '📐', label: 'Methodology' },
  { to: '/trust',       icon: '🛡', label: 'Data & Trust' },
]

export function sidebarFreshness(syncStatus, loading, error) {
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

  const view = getSyncStatusView(syncStatus)
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

export function SidebarAccountBlock({ authState, onNavigate }) {
  if (authState?.authenticated) {
    return (
      <div className="rounded-lg border border-dirt/80 bg-field/45 p-3">
        <div className="font-mono text-[9px] uppercase tracking-widest text-amber/80">
          Signed in
        </div>
        <div className="mt-2 truncate text-xs text-chalk300">
          {authState.user?.email || 'Account active'}
        </div>
        <button
          type="button"
          onClick={() => {
            authState.signOut?.()
            onNavigate?.()
          }}
          className="mt-3 w-full rounded border border-dirt bg-dugout px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-chalk300 transition-colors hover:border-amber/40 hover:text-amber"
        >
          Sign out
        </button>
      </div>
    )
  }

  if (authState?.loading) {
    return (
      <div className="rounded-lg border border-dirt/80 bg-field/45 p-3">
        <div className="font-mono text-[9px] uppercase tracking-widest text-chalk500">
          Account
        </div>
        <div className="mt-2 font-mono text-[11px] text-chalk500">
          Checking sign-in...
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-dirt/80 bg-field/45 p-3">
      <div className="font-mono text-[9px] uppercase tracking-widest text-chalk500">
        Account
      </div>
      <Link
        to="/signin"
        onClick={onNavigate}
        className="mt-3 inline-flex w-full justify-center rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15"
      >
        Sign in
      </Link>
    </div>
  )
}

export function SidebarFollowingCard({ preferredTeam, onNavigate }) {
  if (!preferredTeam) return null

  const preferredHref = buildPreferredTeamHref(preferredTeam, 'nav-my-team')
  const teamLabel = preferredTeamLabel(preferredTeam, 'Team')

  return (
    <NavLink
      to={preferredHref}
      onClick={onNavigate}
      className="mt-3 rounded-lg border border-dirt bg-field/40 px-3 py-2.5 text-left transition-colors hover:border-amber/30 hover:bg-amber/5"
    >
      <div className="font-mono text-[9px] uppercase tracking-widest text-chalk500">
        Following
      </div>
      <div className="mt-1.5 flex min-w-0 items-center gap-2">
        <TeamMark
          team={preferredTeam}
          className="h-8 w-8 border-amber/20 bg-white/[0.04] p-1"
          fallbackClassName="text-[10px]"
        />
        <span className="min-w-0 truncate text-sm text-chalk200">
          {teamLabel}
        </span>
      </div>
    </NavLink>
  )
}

export default function Sidebar() {
  // Mobile-only collapsible nav. On lg+ the nav is always shown and this
  // state is irrelevant (the hamburger is hidden and `lg:flex` forces it open).
  const [open, setOpen] = useState(false)
  const authState = useAuthState()
  const syncStatus = useFetch(getSyncStatus)
  const teams = useFetch(getTeams)
  const teamList = teams.data || []
  const { preferredTeam } = usePreferredTeamPreference(teamList)
  const freshness = sidebarFreshness(
    syncStatus.data,
    syncStatus.loading,
    syncStatus.error,
  )

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
        <SidebarFollowingCard
          preferredTeam={preferredTeam}
          onNavigate={() => setOpen(false)}
        />
      </nav>

      {/* Footer — follows the nav's mobile visibility, always shown on lg+ */}
      <div className={`${open ? 'block' : 'hidden'} lg:block mt-auto px-4 py-4 border-t border-dirt`}>
        <div className="space-y-3">
          <SidebarAccountBlock
            authState={authState}
            onNavigate={() => setOpen(false)}
          />
          <SidebarDataFreshnessCard freshness={freshness} />
        </div>
      </div>
    </aside>
  )
}
