export const PUBLIC_ORIGIN = 'https://baseballos.app'
export const PUBLIC_TEAM_ABBREVIATIONS = Object.freeze([
  'ATH', 'ATL', 'AZ', 'BAL', 'BOS', 'CHC', 'CIN', 'CLE', 'COL', 'CWS',
  'DET', 'HOU', 'KC', 'LAA', 'LAD', 'MIA', 'MIL', 'MIN', 'NYM', 'NYY',
  'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL', 'TB', 'TEX', 'TOR', 'WSH',
])

export const ROUTE_ENTRY_METADATA = Object.freeze([
  {
    key: 'dashboard',
    path: '/dashboard',
    title: 'MLB Bullpen League Board | BaseballOS',
    description: 'Scan the current published Team State for every MLB bullpen, then open the teams that need a closer look.',
    canonical: '/dashboard',
  },
  {
    key: 'bullpen',
    path: '/bullpen',
    title: 'MLB Team Bullpens | BaseballOS',
    description: 'Open an MLB Team Board, compare two bullpens, or find a reliever from the BaseballOS bullpen workspace.',
    canonical: null,
  },
  {
    key: 'search',
    path: '/search',
    title: 'Search MLB Bullpens & Relievers | BaseballOS',
    description: 'Search BaseballOS for an MLB team or reliever and continue to the canonical bullpen view.',
    canonical: '/search',
  },
  {
    key: 'stories',
    path: '/stories',
    title: 'MLB Bullpen Stories | BaseballOS',
    description: 'Read the current published BaseballOS bullpen observations and follow each item to its team context.',
    canonical: '/stories',
  },
  {
    key: 'how-to-read',
    path: '/how-to-read',
    title: 'How to Read BaseballOS',
    description: 'Learn how to read Team State, Arm Reads, workload, rest, and currentness across BaseballOS.',
    canonical: '/how-to-read',
  },
  {
    key: 'methodology',
    path: '/methodology',
    title: 'BaseballOS Methodology',
    description: 'Review the governed definitions, windows, and descriptive boundaries behind BaseballOS bullpen intelligence.',
    canonical: '/methodology',
  },
  {
    key: 'trust',
    path: '/trust',
    title: 'BaseballOS Data & Trust',
    description: 'Review BaseballOS data sources, currentness, limitations, and the evidence boundaries behind public bullpen reads.',
    canonical: '/trust',
  },
  {
    key: 'about',
    path: '/about',
    title: 'About BaseballOS',
    description: 'BaseballOS organizes public MLB bullpen usage, rest, roles, and context into a descriptive daily operating view.',
    canonical: '/about',
  },
  {
    key: 'signin',
    path: '/signin',
    title: 'Sign In | BaseballOS',
    description: 'Sign in to BaseballOS.',
    canonical: null,
    robots: 'noindex,nofollow',
  },
  {
    key: 'auth-verify',
    path: '/auth/verify',
    title: 'Verify Sign In | BaseballOS',
    description: 'Complete BaseballOS sign-in verification.',
    canonical: null,
    robots: 'noindex,nofollow',
  },
  {
    key: 'pitcher',
    path: '/pitcher/:id',
    title: 'MLB Reliever Detail | BaseballOS',
    description: 'Review one MLB reliever’s recent workload, rest, and observed bullpen role in BaseballOS.',
    canonical: null,
  },
  {
    key: 'matchup',
    path: '/matchup/:gameId',
    title: 'MLB Bullpen Matchup | BaseballOS',
    description: 'Compare two published MLB bullpen operating pictures for a scheduled game without treating the result as a prediction.',
    canonical: null,
  },
  {
    key: 'team-history',
    path: '/history/team/:abbr',
    title: 'MLB Bullpen History | BaseballOS',
    description: 'Review a team’s published BaseballOS bullpen history and follow stable evidence links.',
    canonical: null,
  },
  {
    key: 'internal',
    path: '/internal',
    title: 'BaseballOS Internal',
    description: 'BaseballOS internal route.',
    canonical: null,
    robots: 'noindex,nofollow,noarchive',
  },
])

const BY_PATH = new Map(ROUTE_ENTRY_METADATA.map(entry => [entry.path, entry]))
const BULLPEN_IDENTITY_KEYS = Object.freeze(['view', 'team', 'team_a', 'team_b'])
const INTERNAL_PATHS = new Set([
  '/admin/product-intelligence',
  '/internal/share-artifacts/operations',
  '/posts-bpen-7f3d9c',
])

function canonicalUrl(path) {
  return `${PUBLIC_ORIGIN}${path === '/' ? '/' : path}`
}

export function canonicalBullpenPath(search = '') {
  const incoming = new URLSearchParams(search)
  const governed = new URLSearchParams()
  for (const key of BULLPEN_IDENTITY_KEYS) {
    const value = incoming.get(key)
    if (value) governed.set(key, value)
  }
  const query = governed.toString()
  return `/bullpen${query ? `?${query}` : ''}`
}

export function metadataForLocation(pathname = '/', search = '') {
  if (/^\/share\/[A-Za-z0-9._-]{1,64}$/.test(pathname)) {
    return { externallyManaged: true }
  }

  if (pathname === '/') {
    return {
      title: 'BaseballOS | MLB Bullpen Intelligence',
      description: 'BaseballOS reads public MLB usage and workload after every game, so you can tell which pens are gassed and which are loaded — with the data date and confidence always shown.',
      canonicalUrl: canonicalUrl('/'),
    }
  }

  if (pathname === '/bullpen') {
    const entry = BY_PATH.get('/bullpen')
    return { ...entry, canonicalUrl: canonicalUrl(canonicalBullpenPath(search)) }
  }

  const fixed = BY_PATH.get(pathname)
  if (fixed) {
    return {
      ...fixed,
      canonicalUrl: fixed.canonical ? canonicalUrl(fixed.canonical) : null,
    }
  }

  if (INTERNAL_PATHS.has(pathname)) {
    const entry = BY_PATH.get('/internal')
    return { ...entry, canonicalUrl: null }
  }

  const dynamic = [
    [/^\/pitcher\/[1-9]\d*$/, '/pitcher/:id'],
    [/^\/matchup\/[1-9]\d*$/, '/matchup/:gameId'],
  ].find(([pattern]) => pattern.test(pathname))
  if (dynamic) {
    const entry = BY_PATH.get(dynamic[1])
    return { ...entry, canonicalUrl: canonicalUrl(pathname) }
  }

  const historyMatch = pathname.match(/^\/history\/team\/([A-Z0-9-]+)$/)
  if (historyMatch && PUBLIC_TEAM_ABBREVIATIONS.includes(historyMatch[1])) {
    const entry = BY_PATH.get('/history/team/:abbr')
    return { ...entry, canonicalUrl: canonicalUrl(pathname) }
  }

  return null
}
