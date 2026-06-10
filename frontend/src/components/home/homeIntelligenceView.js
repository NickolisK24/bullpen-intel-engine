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
// league day. Headlines state what the data shows today — present tense,
// defensible, no forecasts.
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
      headline: `The ${stressed.teamName} have baseball's most constrained bullpen today`,
      observation: `${stressed.restricted} of the pen's ${stressed.total} relievers come in needing rest after the work they've carried lately. No club enters the day with less late-inning flexibility.`,
      whyItMatters: 'A short bullpen narrows the late innings. If the next few games stay close, the heaviest work is likely to stay on the arms that have already been carrying it.',
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
      headline: `The ${watched.teamName} have baseball's most concentrated bullpen workload today`,
      observation: `${watched.monitor} of the pen's ${watched.total} relievers are carrying enough recent work to sit on the watch list — the longest list in baseball today, even with nobody down outright.`,
      whyItMatters: 'Concentrated work stacks up quietly. Heavy weeks tend to show up later as shorter outings and nights off the schedule didn’t plan for.',
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
      headline: `The ${rested.teamName} bring baseball's most rested bullpen into today`,
      observation: `${rested.available} of the pen's ${rested.total} relievers come in rested and ready — the cleanest availability picture in baseball today.`,
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
    headline: 'A quiet morning across baseball’s bullpens',
    observation: dashboard?.context?.health?.label
      || 'No club stands out for bullpen stress or heavy workload today. Around the league, the pens are in reasonable shape.',
    whyItMatters: 'Quiet days are when bullpens reset. The next story usually starts the night after.',
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
      statLabel: 'clubs working through stress',
      line: `Stress is not isolated to one club today — ${countWord(stressedClubs)} pens are carrying real workload at the same time.`,
    }
  } else if (metrics.monitor > 0 && metrics.monitor >= metrics.restricted) {
    trend = {
      stat: String(metrics.monitor),
      statLabel: 'arms on the watch list',
      line: 'The watch list is the story today — heavy recent use is spread around the league.',
    }
  } else if (metrics.pctAvailable > 0) {
    trend = {
      stat: `${metrics.pctAvailable}%`,
      statLabel: 'of arms rested league-wide',
      line: 'Most pens come into today rested, with stress the exception rather than the rule.',
    }
  } else {
    trend = {
      stat: null,
      statLabel: null,
      line: 'No single league-wide storyline stands out today.',
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
        ? 'More arms need a breather here than anywhere else in baseball.'
        : 'No pen is carrying outsized stress today — a clean league-wide picture.',
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
        ? 'This group brings the cleanest availability picture into today.'
        : 'No pen stands out for rest today.',
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
      statLabel: watchLeader ? 'arms on the watch list' : null,
      line: watchLeader
        ? 'The surface is not alarming yet, but the recent workload is worth watching.'
        : 'No watch list stands out today.',
      href: watchLeader?.href || '/bullpen',
      cta: watchLeader ? 'Step inside this pen' : 'Browse bullpens',
    },
  ]
}

// ── Section 3 — Today's Bullpen Stories ────────────────────────────────────
export const STORIES_FALLBACK =
  'A quiet day in the bullpens — no standout stories this morning. Check back after tonight’s games.'

// Governed observations arrive in system vocabulary ("Availability inventory
// is constrained."). The homepage retells each family in the words a baseball
// writer would use. Families without an editorial translation are left off
// the page rather than shown raw — the governed text remains available on the
// deeper surfaces.
const OBSERVATION_STORY_COPY = {
  inventory: {
    kicker: 'Depth Check',
    title: 'Some clubs are running short on clean options',
    body: 'Around the league, a few pens come in with fewer fully rested arms than they would like. Depth is carrying more of the load than usual today.',
  },
  readiness: {
    kicker: 'Rest Watch',
    title: 'Rest is becoming part of the bullpen story',
    body: 'Not every arm on a roster is truly fresh today. A handful of pens are managing rest as carefully as they manage innings.',
  },
  workload_pressure: {
    kicker: 'Workload Watch',
    title: 'Bullpen work is running heavy around the league',
    body: 'Several pens have been busy lately, and the work has not been spread evenly. The arms carrying it have earned a closer look.',
  },
  constraint: {
    kicker: 'Tight Margins',
    title: 'Late-inning options are tighter than usual today',
    body: 'More than one club comes in with a shorter list of fresh arms than it would like. The margin for a long night is thin in places.',
  },
  freshness: {
    kicker: 'Data Note',
    title: 'Today’s picture is waiting on fresh games',
    body: 'Part of what BaseballOS sees comes from earlier in the week. The story sharpens as new completed games arrive.',
  },
  trust: {
    kicker: 'Data Note',
    title: 'BaseballOS is staying quiet where the data is thin',
    body: 'When the inputs are not solid enough to stand behind, the page says less rather than guessing. A few reads are limited today.',
  },
  availability_movement: {
    kicker: 'Movement',
    title: 'Availability is shifting around the league',
    body: 'Arms are rotating on and off rest around the league. Today’s availability picture is not yesterday’s.',
  },
  snapshot_change: {
    kicker: 'What Changed',
    title: 'Last night rearranged a few bullpens',
    body: 'The newest completed games changed who is rested and who is not. Today’s bullpen picture reflects it.',
  },
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
      kicker: 'Hidden Workload',
      tone: 'watch',
      title: `The ${hidden.teamName} box score looks calm. The bullpen does not.`,
      body: `Nobody in this pen is flashing red, but ${hidden.monitor} of ${hidden.total} arms are carrying heavy recent work. The quiet surface is doing a lot of hiding.`,
      href: hidden.href,
    })
  }

  const heaviest = monitoring.find(entry => entry.monitor > 0)
  if (heaviest) {
    candidates.push({
      teamId: heaviest.teamId,
      kicker: 'Carrying The Load',
      tone: 'watch',
      title: `The ${heaviest.teamName} keep handing the ball to the same relievers`,
      body: `${heaviest.monitor} of ${heaviest.total} arms sit on the watch list — the heaviest concentration of recent bullpen work in baseball today.`,
      href: heaviest.href,
    })
  }

  const tightening = constrained.find(entry => entry.restricted > 0 && !usedTeamIds.has(entry.teamId))
  if (tightening) {
    candidates.push({
      teamId: tightening.teamId,
      kicker: 'Pressure Point',
      tone: 'stress',
      title: `A thin late-inning margin is forming for the ${tightening.teamName}`,
      body: `${tightening.restricted} of ${tightening.total} relievers need rest today. One long night could leave this pen with very few clean options.`,
      href: tightening.href,
    })
  }

  const freshest = available.find(entry => entry.available > 0)
  if (freshest) {
    candidates.push({
      teamId: freshest.teamId,
      kicker: 'Fresh And Ready',
      tone: 'rest',
      title: `Nobody brings a more rested pen into today than the ${freshest.teamName}`,
      body: `${freshest.available} of ${freshest.total} relievers are rested and ready — the kind of depth that lets the late innings breathe.`,
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
      body: `${steady.available} of ${steady.total} arms come in rested, with nothing on the workload ledger to worry about today.`,
      href: steady.href,
    })
  }

  // Governed observations, retold in editorial language. Only a contract-safe
  // collection is used; only families with a translation are shown, one card
  // per family, two at most.
  const observationItems = observations?.contractState === 'available'
    && Array.isArray(observations.observations)
    ? observations.observations
    : []
  const seenFamilies = new Set()
  for (const observation of observationItems) {
    const family = observation?.family
    const copy = OBSERVATION_STORY_COPY[family]
    if (!copy || seenFamilies.has(family)) continue
    seenFamilies.add(family)
    candidates.push({
      teamId: null,
      kicker: copy.kicker,
      tone: OBSERVATION_TONES[observation.severity] || 'neutral',
      title: copy.title,
      body: copy.body,
      href: '/dashboard',
    })
    if (seenFamilies.size >= 2) break
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
    framing: 'Built from current workload and availability signals — not a talent ranking. This reflects today’s bullpen shape.',
    updateNote: 'Rankings update as new completed games enter the system.',
    boards: [
      {
        key: 'health',
        title: 'Top Bullpen Health',
        note: 'Most rested arms today',
        placeholder: false,
        entries: toEntries(
          available.filter(team => team.available > 0),
          team => `${team.available}/${team.total} rested`,
        ),
      },
      {
        key: 'stress',
        title: 'Most Stressed Bullpens',
        note: 'Most arms needing rest today',
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
// Clubs with a live storyline lead off — most stressed first, then the watch
// list, then the most rested — and everyone else follows alphabetically. The
// hooks use story language rather than status labels.
export function getTeamExplorerView(teams, dashboard) {
  const { constrained, available, monitoring } = landscapeLists(dashboard, 'home-explorer')

  const hookByTeamId = new Map()
  const addHooks = (list, countKey, label, tone, priority) => {
    list.forEach((team, index) => {
      if (team.teamId == null || !(team[countKey] > 0)) return
      const existing = hookByTeamId.get(team.teamId)
      if (existing && existing.priority <= priority) return
      hookByTeamId.set(team.teamId, { label, tone, priority, order: index })
    })
  }
  addHooks(constrained, 'restricted', 'Running Hot', 'stress', 0)
  addHooks(monitoring, 'monitor', 'Watch List', 'watch', 1)
  addHooks(available, 'available', 'Well Rested', 'rest', 2)

  const items = (Array.isArray(teams) ? teams : []).map(team => {
    const hook = hookByTeamId.get(team.team_id) || null
    return {
      teamId: team.team_id,
      name: team.team_name || team.team_abbreviation || `Team ${team.team_id}`,
      abbr: team.team_abbreviation || '—',
      armsTracked: Number(team.pitcher_count) || 0,
      tag: hook ? { label: hook.label, tone: hook.tone } : null,
      sortKey: hook ? hook.priority * 100 + hook.order : Number.MAX_SAFE_INTEGER,
      href: buildHomeTeamHref(team, 'home-explorer'),
    }
  })

  items.sort((a, b) => (
    a.sortKey - b.sortKey || a.name.localeCompare(b.name)
  ))

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
      : 'Waiting on the first completed games',
    isLive,
  }
}
