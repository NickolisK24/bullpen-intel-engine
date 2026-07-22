// Single source of truth for the public navigation destinations.
//
// Primary destinations are the core bullpen product surfaces a visitor comes
// for; supporting destinations are the trust and explainer pages. The mobile
// menu and the Today first-use entry area both read from here so a route's
// public label never drifts between them.
//
// Team Bullpens, Compare Bullpens, and Reliever Finder are three views of the
// single `/bullpen` route, distinguished by the `view` query. Their routes and
// query behavior are unchanged — this module only names them.

import { BULLPEN_VIEWS, readBullpenLocation } from './evidenceLinks'

export const PRIMARY_NAV = [
  { key: 'today', to: '/', icon: '☀', label: 'Today' },
  { key: 'league-board', to: '/dashboard', icon: '⬡', label: 'League Board' },
  { key: 'team-bullpens', to: '/bullpen', icon: '🔥', label: 'Team Bullpens', bullpenView: BULLPEN_VIEWS.BOARD },
  { key: 'compare-bullpens', to: '/bullpen?view=compare', icon: '⚖', label: 'Compare Bullpens', bullpenView: BULLPEN_VIEWS.COMPARE },
  { key: 'reliever-finder', to: '/bullpen?view=pitchers', icon: '🔎', label: 'Reliever Finder', bullpenView: BULLPEN_VIEWS.PITCHERS },
  { key: 'stories', to: '/stories', icon: '📰', label: 'Stories' },
]

export const SUPPORTING_NAV = [
  { key: 'how-to-read', to: '/how-to-read', icon: '📖', label: 'How to Read' },
  { key: 'methodology', to: '/methodology', icon: '📐', label: 'Methodology' },
  { key: 'data-trust', to: '/trust', icon: '🛡', label: 'Data & Trust' },
  { key: 'about', to: '/about', icon: 'ⓘ', label: 'About' },
]

// Active-state resolver. NavLink's built-in matching keys on pathname only, so
// it would mark all three `/bullpen` views active at once. Team Bullpens,
// Compare, and Reliever Finder are therefore matched on the `view` query the
// bullpen route reads, while every other destination matches on pathname.
export function isNavDestinationActive(item, location = {}) {
  const pathname = location.pathname || '/'
  if (item.bullpenView) {
    if (pathname !== '/bullpen') return false
    const { view } = readBullpenLocation(location.search || '', '')
    return view === item.bullpenView
  }
  if (item.to === '/') return pathname === '/'
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}
