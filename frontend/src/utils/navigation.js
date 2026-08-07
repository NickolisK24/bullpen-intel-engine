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

// `masthead` controls only which destinations appear in the desktop masthead.
// It changes no route and hides nothing: every destination below is rendered in
// the mobile menu sheet, and Compare and Reliever Finder are also reachable
// from the Today entry row and from the Team Bullpens views themselves. The
// masthead stays six destinations wide so it reads as a publication header
// rather than a directory.
export const PRIMARY_NAV = [
  { key: 'today', to: '/', icon: '☀', label: 'Today' },
  { key: 'league-board', to: '/dashboard', icon: '⬡', label: 'League Board' },
  { key: 'team-bullpens', to: '/bullpen', icon: '🔥', label: 'Team Bullpens', bullpenView: BULLPEN_VIEWS.BOARD },
  { key: 'compare-bullpens', to: '/bullpen?view=compare', icon: '⚖', label: 'Compare Bullpens', bullpenView: BULLPEN_VIEWS.COMPARE, masthead: false },
  { key: 'reliever-finder', to: '/bullpen?view=pitchers', icon: '🔎', label: 'Reliever Finder', bullpenView: BULLPEN_VIEWS.PITCHERS, masthead: false },
  { key: 'stories', to: '/stories', icon: '📰', label: 'Stories' },
]

export const SUPPORTING_NAV = [
  { key: 'how-to-read', to: '/how-to-read', icon: '📖', label: 'How to Read' },
  { key: 'methodology', to: '/methodology', icon: '📐', label: 'Methodology', masthead: true },
  { key: 'data-trust', to: '/trust', icon: '🛡', label: 'Data & Trust', masthead: true },
  { key: 'about', to: '/about', icon: 'ⓘ', label: 'About' },
]

// The desktop masthead: the four primary bullpen lanes plus the two trust
// surfaces that make every other read credible.
export const MASTHEAD_NAV = [
  ...PRIMARY_NAV.filter(item => item.masthead !== false),
  ...SUPPORTING_NAV.filter(item => item.masthead === true),
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
