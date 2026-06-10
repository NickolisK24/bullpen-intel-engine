import { fmtDataDate } from '../dashboard/syncStatusView'

// The Morning Bullpen Report — view-model for the story-led homepage.
//
// Everything on the homepage is derived from outputs the platform already
// publishes: the league dashboard payload (availability counts, team context,
// landscape) and the governed observation feed. This module only retells those
// signals in plain baseball language. Descriptive only — nothing here ranks
// pitchers, selects arms, recommends usage, or predicts outcomes.

const COUNT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six',
                     'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']

const countWord = (n) => COUNT_WORDS[n] || String(n)

const capitalize = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : text)

// "Toronto Blue Jays" → "Toronto Blue Jays'", "Milwaukee" → "Milwaukee's".
const possessive = (name) => (name?.endsWith('s') ? `${name}'` : `${name}'s`)

// Neutral display tones shared across the homepage. Tones describe the
// situation being observed (stress / watch / rest), never quality.
export const HOME_TONES = {
  stress: { color: '#fca5a5', dot: '#ef4444', borderColor: 'rgba(239,68,68,0.35)', backgroundColor: 'rgba(239,68,68,0.06)' },
  watch: { color: '#fde047', dot: '#eab308', borderColor: 'rgba(234,179,8,0.35)', backgroundColor: 'rgba(234,179,8,0.06)' },
  rest: { color: '#6ee7b7', dot: '#10b981', borderColor: 'rgba(16,185,129,0.35)', backgroundColor: 'rgba(16,185,129,0.06)' },
  neutral: { color: '#8899aa', dot: '#8899aa', borderColor: 'rgba(136,153,170,0.30)', backgroundColor: 'rgba(136,153,170,0.05)' },
}

export const homeTone = (key) => HOME_TONES[key] || HOME_TONES.neutral

// Deep-link into the existing bullpen board, reusing the /bullpen?view= pattern
// the rest of the app already understands. source= identifies the homepage
// section for later UX analytics.
export function buildHomeTeamHref(entry, source = 'home') {
  const param = entry?.team_abbreviation || entry?.abbr
    || (entry?.team_id != null ? String(entry.team_id) : null)
    || (entry?.teamId != null ? String(entry.teamId) : null)
  if (!param) return null
  const query = new URLSearchParams({ view: 'board', team: param, source })
  return `/bullpen?${query.toString()}`
}

function mapEntry(entry, source) {
  if (!entry) return null
  return {
    teamId: entry.team_id ?? null,
    teamName: entry.team_name || entry.team_abbreviation || null,
    abbr: entry.team_abbreviation || null,
    available: Number(entry.available) || 0,
    monitor: Number(entry.monitor) || 0,
    restricted: Number(entry.restricted) || 0,
    total: Number(entry.total_relievers) || 0,
    pctAvailable: Number(entry.pct_available) || 0,
    pctRestricted: Number(entry.pct_restricted) || 0,
    href: buildHomeTeamHref(entry, source),
  }
}

// The landscape's three situation lists, in plain objects the homepage can use.
function landscapeLists(dashboard, source = 'home') {
  const landscape = dashboard?.landscape || {}
  const mapList = (list) => (Array.isArray(list) ? list : [])
    .map(entry => mapEntry(entry, source))
    .filter(entry => entry && entry.teamName)
  return {
    constrained: mapList(landscape.constrained_bullpens),
    available: mapList(landscape.available_bullpens),
    monitoring: mapList(landscape.monitoring_concentration),
  }
}

function leagueMetrics(dashboard) {
  const metrics = dashboard?.context?.metrics || {}
  return {
    total: Number(metrics.total_relievers) || 0,
    available: Number(metrics.available) || 0,
    monitor: Number(metrics.monitor) || 0,
    restricted: Number(metrics.restricted) || 0,
    pctAvailable: Number(metrics.pct_available) || 0,
    pctRestricted: Number(metrics.pct_restricted) || 0,
  }
}

const heroChips = (team) => [
  { key: 'ready', label: 'Rested & Ready', value: team.available, tone: 'rest' },
  { key: 'watch', label: 'Workload Watch', value: team.monitor, tone: 'watch' },
  { key: 'rest', label: 'Needing Rest', value: team.restricted, tone: 'stress' },
  { key: 'total', label: 'Relievers', value: team.total, tone: 'neutral' },
]

// ── Section 1 — What BaseballOS Sees Today ─────────────────────────────────
// One flagship observation, picked by a fixed priority: the most constrained
// pen, then the heaviest watch list, then the most rested group, then a quiet
// league day. Same data the landscape already publishes — retold as a story.
export function getHeroStory(dashboard, source = 'home-hero') {
  const { constrained, available, monitoring } = landscapeLists(dashboard, source)

  const stressed = constrained.find(entry => entry.restricted > 0)
  if (stressed) {
    return {
      hasStory: true,
      angle: 'stress',
      tone: 'stress',
      kicker: 'Workload Stress',
      team: stressed,
      headline: `The ${stressed.teamName} bullpen is running out of fresh arms`,
      observation: `BaseballOS counts ${stressed.restricted} of the ${possessive(stressed.teamName)} ${stressed.total} relievers as needing rest after their recent workloads — the most constrained pen in baseball today.`,
      whyItMatters: 'A short pen narrows the late innings. If the next few games stay close, the heaviest work lands on the arms that have already been carrying it.',
      chips: heroChips(stressed),
    }
  }

  const watched = monitoring.find(entry => entry.monitor > 0)
  if (watched) {
    return {
      hasStory: true,
      angle: 'concentration',
      tone: 'watch',
      kicker: 'Workload Watch',
      team: watched,
      headline: `${watched.teamName} keep going back to the same arms`,
      observation: `${watched.monitor} of the ${possessive(watched.teamName)} ${watched.total} relievers are carrying workloads heavy enough to watch — the largest watch list in baseball today, even with nobody down outright.`,
      whyItMatters: 'Workload that concentrates in a few relievers stacks up quietly. Heavy weeks tend to surface later as shorter outings and forced nights off.',
      chips: heroChips(watched),
    }
  }

  const rested = available.find(entry => entry.available > 0)
  if (rested) {
    return {
      hasStory: true,
      angle: 'rest',
      tone: 'rest',
      kicker: 'Fresh Arms',
      team: rested,
      headline: `The ${rested.teamName} bullpen comes in fully rested`,
      observation: `${rested.available} of the ${possessive(rested.teamName)} ${rested.total} relievers enter tonight rested and ready — the largest group of fresh arms in baseball today.`,
      whyItMatters: 'Rest is flexibility. A full pen lets a manager shape the late innings on his terms instead of his bullpen’s.',
      chips: heroChips(rested),
    }
  }

  return {
    hasStory: false,
    angle: 'quiet',
    tone: 'neutral',
    kicker: 'League Check-In',
    team: null,
    headline: 'A quiet morning across major-league bullpens',
    observation: dashboard?.context?.health?.label
      || 'No club stands out for bullpen stress or workload concentration in the current snapshot.',
    whyItMatters: 'Quiet days are when pens reset. The interesting stories usually start the night after.',
    chips: [],
  }
}

// ── Section 2 — League Intelligence Cards ──────────────────────────────────
export function getLeagueCards(dashboard) {
  const { constrained, available, monitoring } = landscapeLists(dashboard, 'home-cards')
  const metrics = leagueMetrics(dashboard)

  const stressLeader = constrained.find(entry => entry.restricted > 0) || null
  const restLeader = available.find(entry => entry.available > 0) || null
  const watchLeader = monitoring.find(entry => entry.monitor > 0) || null
  const stressedClubs = constrained.filter(entry => entry.restricted > 0).length

  let trend
  if (stressedClubs >= 2) {
    trend = {
      stat: String(stressedClubs),
      statLabel: 'clubs showing stress',
      line: `${capitalize(countWord(stressedClubs))} bullpens are carrying real stress at the same time — workload is the league-wide story today.`,
    }
  } else if (metrics.monitor > 0 && metrics.monitor >= metrics.restricted) {
    trend = {
      stat: String(metrics.monitor),
      statLabel: 'arms on workload watch',
      line: 'The watch list is the story today: heavy recent usage is spread across the league.',
    }
  } else if (metrics.pctAvailable > 0) {
    trend = {
      stat: `${metrics.pctAvailable}%`,
      statLabel: 'of arms rested league-wide',
      line: 'Most pens enter tonight with their arms rested.',
    }
  } else {
    trend = {
      stat: null,
      statLabel: null,
      line: 'No single league-wide trend stands out in the current snapshot.',
    }
  }

  return [
    {
      key: 'most-stressed',
      title: 'Most Stressed Bullpen',
      tone: 'stress',
      team: stressLeader,
      stat: stressLeader ? `${stressLeader.restricted} of ${stressLeader.total}` : null,
      statLabel: stressLeader ? 'arms needing rest' : null,
      line: stressLeader
        ? 'More relievers need a breather here than anywhere else in baseball.'
        : 'No bullpen is carrying notable stress in the current snapshot.',
      href: stressLeader?.href || '/bullpen',
      cta: stressLeader ? 'Step inside this pen' : 'Browse bullpens',
    },
    {
      key: 'most-rested',
      title: 'Most Rested Bullpen',
      tone: 'rest',
      team: restLeader,
      stat: restLeader ? `${restLeader.available} of ${restLeader.total}` : null,
      statLabel: restLeader ? 'arms rested & ready' : null,
      line: restLeader
        ? 'The largest group of fresh relievers in baseball today.'
        : 'No bullpen stands out for rest in the current snapshot.',
      href: restLeader?.href || '/bullpen',
      cta: restLeader ? 'Step inside this pen' : 'Browse bullpens',
    },
    {
      key: 'biggest-trend',
      title: 'Biggest Trend',
      tone: 'neutral',
      team: null,
      stat: trend.stat,
      statLabel: trend.statLabel,
      line: trend.line,
      href: '/dashboard',
      cta: 'See the league view',
    },
    {
      key: 'bullpen-to-watch',
      title: 'Bullpen To Watch',
      tone: 'watch',
      team: watchLeader,
      stat: watchLeader ? `${watchLeader.monitor} of ${watchLeader.total}` : null,
      statLabel: watchLeader ? 'arms on workload watch' : null,
      line: watchLeader
        ? 'Nobody is down yet — but the recent usage here is piling up.'
        : 'No watch list stands out in the current snapshot.',
      href: watchLeader?.href || '/bullpen',
      cta: watchLeader ? 'Step inside this pen' : 'Browse bullpens',
    },
  ]
}

// ── Section 3 — Today's Bullpen Stories ────────────────────────────────────
export const STORIES_FALLBACK =
  'No standout bullpen stories in the current snapshot — check back after tonight’s games.'

const OBSERVATION_KICKERS = {
  inventory: 'Depth Check',
  readiness: 'Readiness Note',
  workload_pressure: 'Workload Watch',
  constraint: 'Constraint Note',
  freshness: 'Data Check',
  trust: 'Data Check',
  availability_movement: 'Movement',
  snapshot_change: 'What Changed',
}

const OBSERVATION_TONES = {
  informational: 'neutral',
  monitor: 'watch',
  elevated: 'watch',
  significant: 'stress',
}

export function getBullpenStories(dashboard, observations = null) {
  const { constrained, available, monitoring } = landscapeLists(dashboard, 'home-stories')
  const hero = getHeroStory(dashboard)
  const usedTeamIds = new Set(hero.team?.teamId != null ? [hero.team.teamId] : [])

  const candidates = []

  // Hidden workload — a club whose surface looks calm but whose watch list is
  // long. The most magazine-worthy shape in the data when it shows up.
  const hidden = monitoring.find(entry => entry.monitor >= 3 && entry.restricted <= 1)
  if (hidden) {
    candidates.push({
      teamId: hidden.teamId,
      kicker: 'Hidden Workload Story',
      tone: 'watch',
      title: `${hidden.teamName} look fine on the surface — the workload says look closer`,
      body: `Nobody in this pen is flashing red yet, but ${hidden.monitor} of ${hidden.total} arms are carrying heavy recent usage. The surface is calmer than the workload underneath.`,
      href: hidden.href,
    })
  }

  const heaviest = monitoring.find(entry => entry.monitor > 0)
  if (heaviest) {
    candidates.push({
      teamId: heaviest.teamId,
      kicker: 'Carrying The Load',
      tone: 'watch',
      title: `${heaviest.teamName} keep handing the ball to the same relievers`,
      body: `${heaviest.monitor} of ${heaviest.total} arms sit on the workload watch list — the heaviest concentration of recent usage in baseball today.`,
      href: heaviest.href,
    })
  }

  const tightening = constrained.find(entry => entry.restricted > 0 && !usedTeamIds.has(entry.teamId))
  if (tightening) {
    candidates.push({
      teamId: tightening.teamId,
      kicker: 'Emerging Pressure Point',
      tone: 'stress',
      title: `The ${tightening.teamName} pen is tightening`,
      body: `${tightening.restricted} of ${tightening.total} relievers need rest tonight. One long, close game could stretch this group thin.`,
      href: tightening.href,
    })
  }

  const freshest = available.find(entry => entry.available > 0)
  if (freshest) {
    candidates.push({
      teamId: freshest.teamId,
      kicker: 'Fresh And Ready',
      tone: 'rest',
      title: `${freshest.teamName} bring the most rested pen to the park`,
      body: `${freshest.available} of ${freshest.total} relievers come in rested and ready — rest that buys a manager options late.`,
      href: freshest.href,
    })
  }

  const steady = available.find(entry => entry.available > 0 && entry.teamId !== freshest?.teamId)
  if (steady) {
    candidates.push({
      teamId: steady.teamId,
      kicker: 'Quiet Strength',
      tone: 'rest',
      title: `The ${steady.teamName} pen is in good shape`,
      body: `${steady.available} of ${steady.total} arms enter tonight rested, with no notable stress signals in the current snapshot.`,
      href: steady.href,
    })
  }

  // Governed observations, retold as league-level notes. Only a contract-safe
  // collection is used, and the governed title/summary text is shown verbatim.
  const observationItems = observations?.contractState === 'available'
    && Array.isArray(observations.observations)
    ? observations.observations
    : []
  for (const observation of observationItems.slice(0, 2)) {
    if (!observation?.title || !observation?.summary) continue
    candidates.push({
      teamId: null,
      kicker: OBSERVATION_KICKERS[observation.family] || 'League Note',
      tone: OBSERVATION_TONES[observation.severity] || 'neutral',
      title: observation.title,
      body: observation.summary,
      href: '/dashboard',
    })
  }

  const items = []
  for (const story of candidates) {
    if (story.teamId != null) {
      if (usedTeamIds.has(story.teamId)) continue
      usedTeamIds.add(story.teamId)
    }
    items.push(story)
    if (items.length >= 6) break
  }

  return { hasStories: items.length > 0, items, fallback: STORIES_FALLBACK }
}

// ── Section 4 — Rankings Preview ───────────────────────────────────────────
// A preview of where bullpen rankings are headed. The two live boards reuse
// the landscape's deterministic count ordering; the movement boards are
// placeholders until day-over-day tracking exists. No new backend signals.
export function getRankingsPreview(dashboard) {
  const { constrained, available } = landscapeLists(dashboard, 'home-rankings')

  const toEntries = (list, statFor) => list.map((team, index) => ({
    position: index + 1,
    abbr: team.abbr || team.teamName,
    teamName: team.teamName,
    stat: statFor(team),
    href: team.href,
  }))

  return {
    intro: 'Where full bullpen rankings are headed — assembled from the same availability signals on this page and refreshed as new games sync in.',
    boards: [
      {
        key: 'health',
        title: 'Top Bullpen Health',
        note: 'Most rested arms in today’s snapshot',
        placeholder: false,
        entries: toEntries(
          available.filter(team => team.available > 0),
          team => `${team.available}/${team.total} rested`,
        ),
      },
      {
        key: 'stress',
        title: 'Most Stressed Bullpens',
        note: 'Most arms needing rest tonight',
        placeholder: false,
        entries: toEntries(
          constrained.filter(team => team.restricted > 0),
          team => `${team.restricted}/${team.total} needing rest`,
        ),
      },
      {
        key: 'risers',
        title: 'Biggest Risers',
        note: 'Day-over-day improvement',
        placeholder: true,
        placeholderCopy: 'Movement tracking arrives with the full rankings release.',
        entries: [],
      },
      {
        key: 'fallers',
        title: 'Biggest Fallers',
        note: 'Day-over-day decline',
        placeholder: true,
        placeholderCopy: 'Movement tracking arrives with the full rankings release.',
        entries: [],
      },
    ],
  }
}

// ── Section 5 — Team Explorer ──────────────────────────────────────────────
export function getTeamExplorerView(teams, dashboard) {
  const { constrained, available, monitoring } = landscapeLists(dashboard, 'home-explorer')

  // Story hooks for clubs that show up in today's landscape. Later writes win,
  // so apply in reverse priority: rest, then watch, then stress.
  const tagByTeamId = new Map()
  for (const team of available) {
    if (team.teamId != null && team.available > 0) tagByTeamId.set(team.teamId, { label: 'Rested', tone: 'rest' })
  }
  for (const team of monitoring) {
    if (team.teamId != null && team.monitor > 0) tagByTeamId.set(team.teamId, { label: 'Watch', tone: 'watch' })
  }
  for (const team of constrained) {
    if (team.teamId != null && team.restricted > 0) tagByTeamId.set(team.teamId, { label: 'Stressed', tone: 'stress' })
  }

  const items = (Array.isArray(teams) ? teams : []).map(team => ({
    teamId: team.team_id,
    name: team.team_name || team.team_abbreviation || `Team ${team.team_id}`,
    abbr: team.team_abbreviation || '—',
    armsTracked: Number(team.pitcher_count) || 0,
    tag: tagByTeamId.get(team.team_id) || null,
    href: buildHomeTeamHref(team, 'home-explorer'),
  }))

  return { hasTeams: items.length > 0, items, count: items.length }
}

// ── Masthead ───────────────────────────────────────────────────────────────
export function getMastheadView(dashboard, now = new Date()) {
  const freshness = dashboard?.freshness || {}
  const dataThrough = fmtDataDate(freshness.data_through)
  const isLive = freshness.is_current !== false
    && (freshness.sync_status === 'success' || freshness.sync_status === 'ok')
  return {
    editionDate: now.toLocaleDateString('en-US', {
      weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
    }),
    dataLine: dataThrough
      ? `Built from completed games through ${dataThrough}`
      : 'Awaiting the first data sync',
    isLive,
  }
}
