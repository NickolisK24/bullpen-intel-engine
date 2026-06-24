import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuthState } from '../hooks/useAuthState'
import { useFetch } from '../hooks/useFetch'
import { usePreferredTeamPreference } from '../hooks/usePreferredTeamPreference'
import { getBullpenDashboard } from '../utils/api'
import {
  buildPreferredTeamHref,
  preferredTeamLabel,
} from '../utils/preferredTeam'
import TeamMark from './team/TeamMark'

const NAV = [
  { to: '/',            icon: '☀',  label: 'Today'       },
  { to: '/stories',     icon: '📰', label: 'Stories'     },
  { to: '/dashboard',   icon: '⬡',  label: 'Dashboard'   },
  { to: '/bullpen',     icon: '🔥', label: 'Bullpen'     },
  { to: '/methodology', icon: '📐', label: 'Methodology' },
  { to: '/trust',       icon: '🛡', label: 'Data & Trust' },
]

const TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/New_York',
})

const DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
})

function formatEasternTime(value) {
  if (!value) return 'Loading'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unavailable'
  return `${TIME_FORMATTER.format(date)} ET`
}

function formatDateOnly(value) {
  if (!value) return 'Loading'
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return 'Unavailable'
  const [, year, month, day] = match
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), 12))
  if (Number.isNaN(date.getTime())) return 'Unavailable'
  return DATE_FORMATTER.format(date)
}

function sidebarFreshness(dashboard, loading, error) {
  if (error && !dashboard) {
    return {
      lastSync: 'Unavailable',
      dataThrough: 'Unavailable',
    }
  }

  const freshness = dashboard?.freshness || {}
  const snapshot = dashboard?.snapshot || {}
  return {
    lastSync: loading && !dashboard
      ? 'Loading'
      : formatEasternTime(
        freshness.last_successful_sync
        || snapshot.published_at
        || snapshot.snapshot_generated_at
        || dashboard?.generated_at,
      ),
    dataThrough: loading && !dashboard
      ? 'Loading'
      : formatDateOnly(
        freshness.data_through
        || snapshot.data_through
        || freshness.latest_workload_date,
      ),
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

export default function Sidebar() {
  // Mobile-only collapsible nav. On lg+ the nav is always shown and this
  // state is irrelevant (the hamburger is hidden and `lg:flex` forces it open).
  const [open, setOpen] = useState(false)
  const authState = useAuthState()
  const { preferredTeam } = usePreferredTeamPreference()
  const dashboardFreshness = useFetch(getBullpenDashboard)
  const preferredHref = buildPreferredTeamHref(preferredTeam, 'nav-my-team')
  const freshness = sidebarFreshness(
    dashboardFreshness.data,
    dashboardFreshness.loading,
    dashboardFreshness.error,
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
              <TeamMark
                team={preferredTeam}
                className="h-8 w-8 border-amber/20 bg-white/[0.04] p-1"
                fallbackClassName="text-[10px]"
              />
              <span className="min-w-0 truncate text-sm text-chalk200">
                {preferredTeamLabel(preferredTeam)}
              </span>
            </div>
          </NavLink>
        )}
      </nav>

      {/* Footer — follows the nav's mobile visibility, always shown on lg+ */}
      <div className={`${open ? 'block' : 'hidden'} lg:block mt-auto px-4 py-4 border-t border-dirt`}>
        <div className="space-y-3">
          <SidebarAccountBlock
            authState={authState}
            onNavigate={() => setOpen(false)}
          />
          <div className="rounded-lg border border-dirt/80 bg-field/45 p-3">
            <div className="mb-3 font-mono text-[9px] uppercase tracking-widest text-amber/80">
              Data Freshness
            </div>
            <div className="space-y-3">
              <SidebarFreshnessItem label="Last Sync" value={freshness.lastSync} />
              <SidebarFreshnessItem label="Data Through" value={freshness.dataThrough} />
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}
