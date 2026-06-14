import { fmtDataDate } from '../dashboard/syncStatusView'
import { getReadsForLandscapeEntry } from '../../utils/bullpenConcepts'
import { SIGNAL_HEADLINES } from '../../utils/bullpenLanguage'
import {
  selectLeadStory,
  selectStoryCandidates,
} from './storyEngineV1'

// The Morning Bullpen Report — view-model for the story-led homepage.
//
// Everything on the homepage is derived from outputs the platform already
// publishes: the league dashboard payload (availability counts, team context,
// landscape) and the governed observation feed. This module only retells those
// signals in plain baseball language: ontology vocabulary stays on the
// evidence slots (read chips, stat labels, fact labels) while headlines and
// prose talk baseball. Descriptive only — nothing here ranks pitchers,
// selects arms, recommends usage, or predicts outcomes.

const COUNT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six',
                     'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']

const countWord = (n) => COUNT_WORDS[n] || String(n)

const capitalize = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : text)
const cleanStoryText = (value) => (typeof value === 'string' ? value.trim() : '')

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

function dashboardContinuityForTeam(dashboard, teamId) {
  if (teamId == null) return null
  const teams = dashboard?.continuity?.teams || {}
  return teams[String(teamId)] || teams[teamId] || null
}

function dashboardStoryContextForTeam(dashboard, teamId) {
  if (teamId == null) return null
  const teams = dashboard?.story_context?.teams || {}
  return teams[String(teamId)] || teams[teamId] || null
}

function mapEntry(entry, source, dashboard) {
  if (!entry) return null
  const teamId = entry.team_id ?? null
  const dashboardContinuity = dashboardContinuityForTeam(dashboard, teamId)
  const dashboardContext = dashboardStoryContextForTeam(dashboard, teamId)
  return {
    teamId,
    teamName: entry.team_name || entry.team_abbreviation || null,
    abbr: entry.team_abbreviation || null,
    available: Number(entry.available) || 0,
    monitor: Number(entry.monitor) || 0,
    restricted: Number(entry.restricted) || 0,
    total: Number(entry.total_relievers) || 0,
    pctAvailable: Number(entry.pct_available) || 0,
    pctRestricted: Number(entry.pct_restricted) || 0,
    continuityByType: dashboardContinuity?.by_type || {},
    dashboardContinuity,
    contextByType: dashboardContext?.by_type || {},
    dashboardContext,
    continuity_note: typeof entry.continuity_note === 'string' && entry.continuity_note.trim()
      ? entry.continuity_note
      : undefined,
    continuity: entry.continuity || undefined,
    href: buildHomeTeamHref(entry, source),
  }
}

function storyContextFits(storyKind, contextEntry) {
  const type = contextEntry?.context?.type
  const trend = contextEntry?.context?.evidence?.trend
  if (!type || typeof contextEntry?.context_note !== 'string') return false
  if (storyKind === 'team_recovery') {
    return (
      (type === 'usage_demand' && trend === 'decreasing_demand')
      || (type === 'rotation_length' && trend === 'longer_outings')
    )
  }
  if (
    storyKind === 'team_pressure'
    || storyKind === 'team_workload'
    || storyKind === 'team_workload_continuity'
  ) {
    return (
      (type === 'usage_demand' && trend === 'increasing_demand')
      || (type === 'rotation_length' && trend === 'shorter_outings')
    )
  }
  return false
}

function storyContextProps(team, storyKind) {
  if (!team) return {}
  const byType = team.contextByType || team.by_type || team.dashboardContext?.by_type || {}
  const entries = [
    byType.usage_demand,
    byType.rotation_length,
    team.context_note ? team : null,
    team.dashboardContext,
  ].filter(Boolean)
  const contextEntry = entries.find(entry => storyContextFits(storyKind, entry))
  const note = contextEntry?.context_note
  if (typeof note !== 'string' || !note.trim()) return {}
  return {
    context_note: note,
    ...(contextEntry.context ? { context: contextEntry.context } : {}),
  }
}

function continuityTypeForStoryKind(storyKind) {
  if (storyKind === 'team_workload_continuity') return 'workload_concentration'
  if (storyKind === 'team_recovery') return 'workload_easing'
  return null
}

function storyContinuityProps(team, storyKind) {
  const type = continuityTypeForStoryKind(storyKind)
  if (!type || !team) return {}
  const byType = team.continuityByType || team.by_type || team.dashboardContinuity?.by_type || {}
  const continuityEntry = byType[type]
    || (team.continuity?.type === type ? team : null)
    || (team.dashboardContinuity?.continuity?.type === type ? team.dashboardContinuity : null)
    || (!team.continuity?.type && typeof team.continuity_note === 'string' ? team : null)
  const note = continuityEntry?.continuity_note
  if (typeof note !== 'string' || !note.trim()) return {}
  return {
    continuity_note: note,
    ...(continuityEntry.continuity ? { continuity: continuityEntry.continuity } : {}),
  }
}

function withStoryContinuity(candidate, team = candidate?.team || candidate, dashboard = null) {
  const directProps = storyContinuityProps(team, candidate?.storyKind)
  const dashboardProps = Object.keys(directProps).length
    ? {}
    : storyContinuityProps(
      dashboardContinuityForTeam(dashboard, candidate?.teamId),
      candidate?.storyKind,
    )
  const directContextProps = storyContextProps(team, candidate?.storyKind)
  const dashboardContextProps = Object.keys(directContextProps).length
    ? {}
    : storyContextProps(
      dashboardStoryContextForTeam(dashboard, candidate?.teamId),
      candidate?.storyKind,
    )
  return {
    ...candidate,
    ...dashboardProps,
    ...directProps,
    ...dashboardContextProps,
    ...directContextProps,
  }
}

// The landscape's three situation lists, in plain objects the homepage can use.
function landscapeLists(dashboard, source = 'home') {
  const landscape = dashboard?.landscape || {}
  const mapList = (list) => (Array.isArray(list) ? list : [])
    .map(entry => mapEntry(entry, source, dashboard))
    .filter(entry => entry && entry.teamName)
  return {
    constrained: mapList(landscape.constrained_bullpens),
    available: mapList(landscape.available_bullpens),
    monitoring: mapList(landscape.monitoring_concentration),
  }
}

function landscapeTeamLookup(dashboard, source = 'home') {
  const lists = landscapeLists(dashboard, source)
  const lookup = new Map()
  for (const entry of [...lists.constrained, ...lists.available, ...lists.monitoring]) {
    for (const key of [entry.teamId, entry.abbr, entry.teamName]) {
      if (key != null && !lookup.has(String(key))) lookup.set(String(key), entry)
    }
  }
  return lookup
}

function contextTeamKey(entry, fallbackKey) {
  return entry?.team_id ?? entry?.teamId ?? fallbackKey ?? null
}

function contextStoryEntry(entry = {}) {
  const byType = entry.by_type || entry.byType || {}
  return byType.usage_demand || byType.rotation_length || entry
}

function usageShiftTitle(teamName, context = {}) {
  const trend = cleanStoryText(context?.evidence?.trend)
  if (context?.type === 'rotation_length' && trend === 'shorter_outings') {
    return `Recent short starts are pushing more work toward the ${teamName} bullpen`
  }
  if (context?.type === 'rotation_length' && trend === 'longer_outings') {
    return `Longer starts are giving the ${teamName} bullpen more room`
  }
  if (trend === 'decreasing_demand') {
    return `The ${teamName} bullpen has more room after a quieter stretch`
  }
  return `The ${teamName} bullpen workload has shifted recently`
}

function usageShiftBody(teamName, context = {}) {
  const trend = cleanStoryText(context?.evidence?.trend)
  if (trend === 'decreasing_demand' || trend === 'longer_outings') {
    return `Recent usage has eased around the ${teamName}, giving the bullpen a different shape than it had in the prior window.`
  }
  return `Recent usage has picked up around the ${teamName}, giving the bullpen a different shape than it had in the prior window.`
}

function storyContextShiftCandidates(dashboard, source = 'home-stories') {
  const contextTeams = dashboard?.story_context?.teams || dashboard?.storyContext?.teams || {}
  const lookup = landscapeTeamLookup(dashboard, source)
  return Object.entries(contextTeams)
    .map(([key, entry]) => {
      const contextEntry = contextStoryEntry(entry)
      const context = contextEntry?.context
      const note = cleanStoryText(contextEntry?.context_note)
      const team = lookup.get(String(contextTeamKey(contextEntry, key))) || lookup.get(String(contextTeamKey(entry, key)))
      if (!team || !context || !note) return null
      if (!['usage_demand', 'rotation_length'].includes(context.type)) return null
      return {
        teamId: team.teamId,
        abbr: team.abbr,
        teamName: team.teamName,
        available: team.available,
        monitor: team.monitor,
        restricted: team.restricted,
        total: team.total,
        storyKind: 'team_usage_shift',
        archetype_key: 'usage_shift',
        read: team.monitor >= team.restricted
          ? getReadsForLandscapeEntry(team).byKey.concentration
          : getReadsForLandscapeEntry(team).byKey.pressure,
        kicker: 'Usage Shift',
        tone: team.restricted > 1 ? 'stress' : team.monitor > 1 ? 'watch' : 'neutral',
        title: usageShiftTitle(team.teamName, context),
        body: usageShiftBody(team.teamName, context),
        context_note: note,
        context,
        href: team.href,
        cta: 'Step inside this pen',
      }
    })
    .filter(Boolean)
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

function storyEngineContext(dashboard) {
  return {
    leagueMetrics: leagueMetrics(dashboard),
    freshness: dashboard?.freshness || {},
    games: dashboard?.landscape?.games || {},
    teamsEvaluated: Number(dashboard?.landscape?.teams_evaluated) || 0,
  }
}

// Count chips state plainly what each number counts; the concept vocabulary
// rides the hero's read chip, where it explains itself on hover.
const heroChips = (team) => [
  { key: 'clean', label: 'Rested Options', value: team.available, tone: 'rest' },
  { key: 'concentration', label: 'On Watch', value: team.monitor, tone: 'watch' },
  { key: 'recovery', label: 'Needing Rest', value: team.restricted, tone: 'stress' },
  { key: 'total', label: 'Relievers', value: team.total, tone: 'neutral' },
]

function continuityWindowNote(story) {
  const days = Number(story?.continuity?.window_days)
  if (!Number.isFinite(days) || days <= 1) return ''
  if (story?.storyKind === 'team_recovery') {
    return `This flexibility has been visible across the last ${days} days.`
  }
  return `This pattern has been visible across the last ${days} days.`
}

function flagshipContinuityNote(story) {
  const existing = cleanStoryText(story?.continuity_note)
  if (existing) return existing

  const windowNote = continuityWindowNote(story)
  if (windowNote) return windowNote

  if (story?.storyKind === 'team_pressure') {
    return 'At this point, this reads as a current-day pressure point rather than a confirmed weeklong trend.'
  }
  if (story?.storyKind === 'team_workload_continuity') {
    return 'This reads as an ongoing recent-use pattern rather than a one-night availability issue.'
  }
  if (story?.storyKind === 'team_recovery') {
    return 'At this point, this reads as a current-day flexibility window rather than a confirmed long reset.'
  }
  return 'At this point, the league read is quiet today rather than an ongoing stress pattern.'
}

function flagshipContextNote(story) {
  const existing = cleanStoryText(story?.context_note)
  if (existing) return existing

  if (story?.storyKind === 'team_pressure') {
    return 'The pressure is workload-driven: recent use has left fewer rested options behind the late innings.'
  }
  if (story?.storyKind === 'team_workload_continuity') {
    return 'Recent usage has centered tightly enough that the pen can look available while still leaning on the same core.'
  }
  if (story?.storyKind === 'team_recovery') {
    return 'The room comes from recent workload staying spread out enough that more relievers remain usable.'
  }
  return 'No club is separating for stress, watch-list volume, or unusually deep rest on the current bullpen board.'
}

function withFlagshipBriefingSupport(story, dashboard = null) {
  if (!story) return story
  const supported = {
    ...story,
    continuity_note: flagshipContinuityNote(story),
    context_note: flagshipContextNote(story),
  }
  return {
    ...supported,
    storyStatus: getFlagshipStoryStatus(dashboard, supported),
    whatBaseballOSSaw: flagshipEvidenceFacts(supported),
  }
}

function evidenceValueText(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

const SUMMARY_EVIDENCE_LABELS = new Set([
  'relievers needing rest',
  'watch-list arms',
  'rested options',
])

function evidenceKey(label, value) {
  return `${cleanStoryText(label).toLowerCase()}:${evidenceValueText(value).toLowerCase()}`
}

function comparableEvidenceText(value) {
  return evidenceValueText(value)
    .toLowerCase()
    .replace(/[^a-z0-9%\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function isSummaryCountEvidence(item) {
  const label = cleanStoryText(item?.label).toLowerCase()
  const sourceType = cleanStoryText(item?.sourceType || item?.source_type).toLowerCase()
  return sourceType === 'team_bullpen_counts' || SUMMARY_EVIDENCE_LABELS.has(label)
}

function flagshipStoryTextSections(story) {
  return [
    story?.observation,
    story?.continuity_note,
    story?.context_note,
    story?.whyItMatters,
  ].map(comparableEvidenceText).filter(Boolean)
}

function repeatsFlagshipStoryText(story, value) {
  const text = comparableEvidenceText(value)
  if (text.length < 24) return false
  return flagshipStoryTextSections(story).some(section => (
    section.includes(text) || text.includes(section)
  ))
}

function addFlagshipEvidenceFact(facts, seen, label, value, detail = '') {
  const cleanLabel = cleanStoryText(label)
  const cleanValue = evidenceValueText(value)
  if (!cleanLabel || !cleanValue) return

  const key = evidenceKey(cleanLabel, cleanValue)
  if (seen.has(key)) return
  seen.add(key)
  facts.push({
    key,
    label: cleanLabel,
    value: cleanValue,
    detail: cleanStoryText(detail),
  })
}

function flagshipEvidenceFacts(story) {
  const evidence = Array.isArray(story?.evidence) ? story.evidence : []
  const seen = new Set()
  const facts = []

  for (const item of evidence) {
    if (isSummaryCountEvidence(item)) continue
    if (repeatsFlagshipStoryText(story, item?.value)) continue
    addFlagshipEvidenceFact(facts, seen, item?.label, item?.value, item?.detail)
  }

  return facts.slice(0, 4)
}

function teamNameFromChange(item) {
  return cleanStoryText(
    item?.team_name
    || item?.teamName
    || item?.team?.team_name
    || item?.team?.teamName
    || item?.team_abbreviation
    || item?.team?.team_abbreviation,
  )
}

function normalizeHomepageChange(item, index) {
  const teamName = teamNameFromChange(item)
  const change = cleanStoryText(item?.change || item?.summary)
  const whyChanged = cleanStoryText(item?.why_changed || item?.whyChanged || item?.reason)
  if (!teamName || !change || !whyChanged) return null

  return {
    key: cleanStoryText(item?.key) || `${teamName}-${index}`,
    teamName,
    teamAbbr: cleanStoryText(item?.team_abbreviation || item?.teamAbbr || item?.team?.team_abbreviation),
    change,
    whyChanged,
  }
}

export function getWhatChangedSinceYesterday(dashboard) {
  const payload = dashboard?.what_changed_since_yesterday || dashboard?.whatChangedSinceYesterday
  const items = Array.isArray(payload?.items) ? payload.items : []
  const normalized = items
    .map(normalizeHomepageChange)
    .filter(Boolean)
    .slice(0, 3)

  return {
    hasChanges: normalized.length > 0,
    items: normalized,
    comparison: payload?.comparison || null,
  }
}

const STORY_STATUS_TONES = {
  new: 'neutral',
  ongoing: 'watch',
  returning: 'rest',
}

function storyStatusTheme(story) {
  const kind = cleanStoryText(story?.storyKind || story?.family || story?.kicker).toLowerCase()
  if (kind === 'team_pressure' || kind.includes('pressure') || kind.includes('stress')) return 'pressure'
  if (kind === 'team_workload_continuity' || kind.includes('workload') || kind.includes('watch')) return 'workload'
  if (kind === 'team_recovery' || kind.includes('recovery') || kind.includes('rest')) return 'recovery'
  if (kind === 'league_check_in' || kind.includes('quiet')) return 'quiet'
  return kind || null
}

function storyStatusTeamKey(story) {
  const team = story?.team || {}
  const teamId = story?.teamId ?? team.teamId ?? team.team_id
  if (teamId != null) return String(teamId)
  const abbr = cleanStoryText(story?.abbr || team.abbr || team.team_abbreviation)
  if (abbr) return abbr.toLowerCase()
  const teamName = cleanStoryText(story?.teamName || team.teamName || team.team_name)
  return teamName ? teamName.toLowerCase() : null
}

function storyStatusSignature(story) {
  const theme = storyStatusTheme(story)
  if (!theme) return null
  const teamKey = storyStatusTeamKey(story)
  return teamKey ? `team:${teamKey}|theme:${theme}` : `league|theme:${theme}`
}

function normalizeStoryStatus(item) {
  const status = cleanStoryText(item?.status).toLowerCase()
  if (!['new', 'ongoing', 'returning'].includes(status)) return null
  const label = cleanStoryText(item?.label)
  const description = cleanStoryText(item?.description)
  if (!label || !description) return null

  return {
    status,
    label,
    description,
    consecutiveDays: Number.isFinite(Number(item?.consecutive_days))
      ? Number(item.consecutive_days)
      : null,
    lookbackDays: Number.isFinite(Number(item?.lookback_days))
      ? Number(item.lookback_days)
      : null,
    tone: STORY_STATUS_TONES[status] || 'neutral',
  }
}

export function getFlagshipStoryStatus(dashboard, story) {
  const signature = storyStatusSignature(story)
  if (!signature) return null
  const payload = dashboard?.story_continuity || dashboard?.storyContinuity
  const items = Array.isArray(payload?.items) ? payload.items : []
  const match = items.find(item => cleanStoryText(item?.signature) === signature)
  return normalizeStoryStatus(match)
}

// ── Section 1 — What BaseballOS Sees Today ─────────────────────────────────
// One flagship observation, picked by a fixed priority: the most constrained
// pen, then the heaviest watch list, then the most rested group, then a quiet
// league day. Headlines state what the data shows today — present tense,
// defensible, no forecasts.
export function getHeroStory(dashboard, source = 'home-hero') {
  const { constrained, available, monitoring } = landscapeLists(dashboard, source)
  const candidates = []

  const stressed = constrained.find(entry => entry.restricted > 0)
  if (stressed) {
    candidates.push({
      hasStory: true,
      storyKind: 'team_pressure',
      angle: 'stress',
      tone: 'stress',
      kicker: 'Stretched Thin',
      team: stressed,
      read: getReadsForLandscapeEntry(stressed).byKey.pressure,
      headline: SIGNAL_HEADLINES.stretchedPen.hero(stressed.teamName),
      observation: `${stressed.restricted} of the pen's ${stressed.total} relievers come in needing rest after the work they've carried lately. That leaves less room to breathe late than any club in baseball today.`,
      whyItMatters: 'If the pattern continues, late-game flexibility could become increasingly concentrated. For fans, the key is whether the club still has more than one clean path through a close game.',
      chips: heroChips(stressed),
    })
  }

  const watched = monitoring.find(entry => entry.monitor > 0)
  if (watched) {
    candidates.push({
      hasStory: true,
      storyKind: 'team_workload_continuity',
      angle: 'concentration',
      tone: 'watch',
      kicker: 'Heavy Lifting',
      team: watched,
      read: getReadsForLandscapeEntry(watched).byKey.concentration,
      headline: SIGNAL_HEADLINES.sameArms.hero(watched.teamName),
      observation: `${watched.monitor} of the pen's ${watched.total} relievers are carrying enough recent work to sit on the watch list — the longest list in baseball today, even with nobody down outright.`,
      whyItMatters: 'If the pattern continues, late-game flexibility could become increasingly concentrated. The bullpen still has options, but the current workload distribution is becoming less balanced.',
      chips: heroChips(watched),
      ...storyContinuityProps(watched, 'team_workload_continuity'),
    })
  }

  const rested = available.find(entry => entry.available > 0)
  if (rested) {
    candidates.push({
      hasStory: true,
      storyKind: 'team_recovery',
      angle: 'rest',
      tone: 'rest',
      kicker: 'More Options',
      team: rested,
      read: getReadsForLandscapeEntry(rested).byKey.recovery,
      headline: SIGNAL_HEADLINES.freshPen.hero(rested.teamName),
      observation: `${rested.available} of the pen's ${rested.total} relievers come in rested enough to be usable. No pen in baseball has more late-inning room today.`,
      whyItMatters: 'Rested options give a club more ways to get through close innings. For fans, that matters because one busy stretch does not have to force the same small group into every late spot.',
      chips: heroChips(rested),
      ...storyContinuityProps(rested, 'team_recovery'),
    })
  }

  const lead = selectLeadStory(
    candidates.map(candidate => withStoryContinuity(candidate)),
    storyEngineContext(dashboard),
  )
  if (lead) {
    return withFlagshipBriefingSupport(lead, dashboard)
  }

  return withFlagshipBriefingSupport({
    hasStory: false,
    storyKind: 'league_check_in',
    angle: 'quiet',
    tone: 'neutral',
    kicker: 'League Check-In',
    team: null,
    read: null,
    headline: 'A quiet morning across baseball’s bullpens',
    observation: dashboard?.context?.health?.label
      || 'No club stands out for bullpen stress or heavy workload today. Around the league, the pens are in reasonable shape.',
    whyItMatters: 'Quiet days give bullpens a reset point. For fans, a balanced baseline makes the next real pressure point easier to spot.',
    chips: [],
  }, dashboard)
}

// ── Shared League Cards ────────────────────────────────────────────────────
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
      line: `The heavy lifting is not isolated to one bullpen — ${countWord(stressedClubs)} pens are carrying real workload at once.`,
    }
  } else if (metrics.monitor > 0 && metrics.monitor >= metrics.restricted) {
    trend = {
      stat: String(metrics.monitor),
      statLabel: 'arms on the watch list',
      line: 'The league-wide workload picture is tightening; heavy recent use is showing up across the board.',
    }
  } else if (metrics.pctAvailable > 0) {
    trend = {
      stat: `${metrics.pctAvailable}%`,
      statLabel: 'of arms rested league-wide',
      line: 'The league is not running on empty. Most pens still have room to maneuver.',
    }
  } else {
    trend = {
      stat: null,
      statLabel: null,
      line: 'No single league-wide storyline stands out today.',
    }
  }

  // Card titles talk baseball; the stat labels underneath keep the counts and
  // concept vocabulary as evidence.
  return [
    {
      key: 'most-stressed',
      title: 'The Most Stretched Pen',
      tone: 'stress',
      team: stressLeader,
      stat: stressLeader ? `${stressLeader.restricted} of ${stressLeader.total}` : null,
      statLabel: stressLeader ? 'arms needing rest' : null,
      line: stressLeader
        ? 'No pen has less room to breathe late today.'
        : 'No pen is carrying outsized stress today — a clean league-wide picture.',
      href: stressLeader?.href || '/bullpen',
      cta: stressLeader ? 'Step inside this pen' : 'Browse every bullpen',
    },
    {
      key: 'most-rested',
      title: 'Most Room To Maneuver',
      tone: 'rest',
      team: restLeader,
      stat: restLeader ? `${restLeader.available} of ${restLeader.total}` : null,
      statLabel: restLeader ? 'rested options' : null,
      line: restLeader
        ? 'No pen has more ways through the late innings today.'
        : 'No pen stands out for rest today.',
      href: restLeader?.href || '/bullpen',
      cta: restLeader ? 'Step inside this pen' : 'Browse every bullpen',
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
      title: 'Leaning On The Same Arms',
      tone: 'watch',
      team: watchLeader,
      stat: watchLeader ? `${watchLeader.monitor} of ${watchLeader.total}` : null,
      statLabel: watchLeader ? 'arms on the watch list' : null,
      line: watchLeader
        ? 'The surface can look calm while the same arms keep getting the call.'
        : 'No watch list stands out today.',
      href: watchLeader?.href || '/bullpen',
      cta: watchLeader ? 'Step inside this pen' : 'Browse every bullpen',
    },
  ]
}

// ── Section 2 — Three Things To Watch ──────────────────────────────────────
export const TODAY_WATCH_FALLBACK =
  'No extra watch items stand out behind the flagship story yet. Stories will fill in as the bullpen picture changes.'

function uniqueTeamKey(team) {
  return team?.teamId ?? team?.abbr ?? team?.teamName ?? null
}

export function getTodayWatchItems(dashboard) {
  const { constrained, available, monitoring } = landscapeLists(dashboard, 'today-watch')
  const hero = getHeroStory(dashboard)
  const usedTeams = new Set(hero.team ? [uniqueTeamKey(hero.team)] : [])
  const items = []

  const addItem = (team, item) => {
    const key = uniqueTeamKey(team)
    if (key != null) {
      if (usedTeams.has(key)) return
      usedTeams.add(key)
    }
    items.push(withStoryContinuity(item, team))
  }

  const pressure = constrained.find(entry => entry.restricted > 0 && !usedTeams.has(uniqueTeamKey(entry)))
  if (pressure) {
    addItem(pressure, {
      teamId: pressure.teamId,
      teamName: pressure.teamName,
      abbr: pressure.abbr,
      available: pressure.available,
      monitor: pressure.monitor,
      restricted: pressure.restricted,
      total: pressure.total,
      storyKind: 'team_pressure',
      kicker: 'Pressure Watch',
      tone: 'stress',
      title: `The ${pressure.teamName} enter today with a thin late-inning margin`,
      body: `The ${pressure.teamName} also have ${pressure.restricted} ${pressure.restricted === 1 ? 'reliever' : 'relievers'} needing rest after recent work. The late-inning bench is thinner here too.`,
      href: pressure.href,
      cta: 'Open the team board',
    })
  }

  const workload = monitoring.find(entry => entry.monitor > 0 && !usedTeams.has(uniqueTeamKey(entry)))
  if (workload) {
    addItem(workload, {
      teamId: workload.teamId,
      teamName: workload.teamName,
      abbr: workload.abbr,
      available: workload.available,
      monitor: workload.monitor,
      restricted: workload.restricted,
      total: workload.total,
      storyKind: 'team_workload_continuity',
      kicker: 'Heavy Lifting',
      tone: 'watch',
      title: `The ${workload.teamName} keep asking the same relievers for the heavy lifting`,
      body: `${workload.monitor} ${workload.monitor === 1 ? 'arm' : 'arms'} in the ${workload.teamName} pen ${workload.monitor === 1 ? 'has' : 'have'} been carrying the heavy work lately. That is the kind of quiet strain a box score can miss.`,
      href: workload.href,
      cta: 'Open the team board',
    })
  }

  const recovery = available.find(entry => entry.available > 0 && !usedTeams.has(uniqueTeamKey(entry)))
  if (recovery) {
    addItem(recovery, {
      teamId: recovery.teamId,
      teamName: recovery.teamName,
      abbr: recovery.abbr,
      available: recovery.available,
      monitor: recovery.monitor,
      restricted: recovery.restricted,
      total: recovery.total,
      storyKind: 'team_recovery',
      kicker: 'Rested Options',
      tone: 'rest',
      title: `The ${recovery.teamName} have more ways through the late innings`,
      body: `The ${recovery.teamName} have ${recovery.available} ${recovery.available === 1 ? 'reliever' : 'relievers'} rested enough to use today. That is the other side of the workload picture.`,
      href: recovery.href,
      cta: 'Open the team board',
    })
  }

  for (const shift of storyContextShiftCandidates(dashboard, 'today-watch')) {
    if (items.length >= 5) break
    addItem(shift, {
      ...shift,
      cta: 'Open the team board',
    })
  }

  const metrics = leagueMetrics(dashboard)
  if (items.length < 3 && metrics.monitor > 0) {
    items.push({
      teamId: null,
      storyKind: 'league_workload',
      kicker: 'Across The League',
      tone: 'watch',
      title: 'Several bullpens are carrying heavier late-inning work',
      body: `${metrics.monitor} tracked ${metrics.monitor === 1 ? 'arm sits' : 'arms sit'} on the watch list around the league. Heavy recent work is showing up in more than one place.`,
      href: '/stories',
      cta: 'Open Stories',
    })
  }

  if (items.length < 3 && metrics.available > 0) {
    items.push({
      teamId: null,
      storyKind: 'league_recovery',
      kicker: 'Rested Options',
      tone: 'rest',
      title: 'The league still has rested options in reserve',
      body: `${metrics.available} tracked ${metrics.available === 1 ? 'reliever is' : 'relievers are'} rested enough to be usable today. The pressure points matter, but the league is not running on empty.`,
      href: '/stories',
      cta: 'Open Stories',
    })
  }

  const selection = selectStoryCandidates(items, storyEngineContext(dashboard), { limit: 3, seedStories: [hero] })
  return {
    hasStories: selection.items.length > 0,
    items: selection.items,
    fallback: TODAY_WATCH_FALLBACK,
    suppressedCount: selection.suppressedCount,
    suppressionReasons: selection.suppressionReasons,
  }
}

// ── Section 3 — Short League Context ───────────────────────────────────────
export function getLeagueContext(dashboard) {
  const metrics = leagueMetrics(dashboard)
  const hasMetrics = metrics.total > 0

  const summary = hasMetrics
    ? `Around the league, ${metrics.restricted} tracked ${metrics.restricted === 1 ? 'arm needs' : 'arms need'} rest after recent work, ${metrics.monitor} ${metrics.monitor === 1 ? 'sits' : 'sit'} on the watch list, and ${metrics.available} ${metrics.available === 1 ? 'is' : 'are'} rested enough to be usable today. That is the bullpen map behind today's lead story.`
    : 'The league context is waiting on a complete bullpen dashboard.'

  // Fact labels keep the BaseballOS vocabulary; the values and details say
  // what is actually being counted.
  return {
    summary,
    facts: [
      {
        key: 'pressure',
        label: 'Bullpen Pressure',
        tone: metrics.restricted > 0 ? 'stress' : 'neutral',
        value: hasMetrics ? String(metrics.restricted) : '0',
        detail: 'arms needing rest after recent work',
      },
      {
        key: 'concentration',
        label: 'Usage Trend',
        tone: metrics.monitor > 0 ? 'watch' : 'neutral',
        value: hasMetrics ? String(metrics.monitor) : '0',
        detail: 'arms on the watch list',
      },
      {
        key: 'clean',
        label: 'Rested Options',
        tone: metrics.available > 0 ? 'rest' : 'neutral',
        value: hasMetrics ? `${metrics.pctAvailable}%` : '0%',
        detail: 'of tracked arms rested today',
      },
    ],
    href: '/stories',
    cta: 'Open Stories for more observations',
  }
}

// ── Section 4 — Stories Feed ───────────────────────────────────────────────
export const STORIES_FALLBACK =
  'A quiet day in the bullpens — no standout stories this morning. Check back after tonight’s games.'

export const STORY_TITLE_GUIDELINES = {
  prefer: [
    'Create curiosity before declaring a verdict.',
    'Highlight tension, hidden workload, or changing bullpen context.',
    'Use BaseballOS vocabulary without making the title sound like a grade.',
  ],
  avoid: [
    'Ranking language.',
    'Scouting-grade language.',
    'Final verdicts such as healthy, strong, or in good shape.',
  ],
}

// Governed observations arrive in system vocabulary ("Availability inventory
// is constrained."). The homepage retells each family in the words a baseball
// writer would use. Families without an editorial translation are left off
// the page rather than shown raw — the governed text remains available on the
// deeper surfaces. Each family also carries its most useful next click:
// league-shape stories open the league dashboard; data notes open the
// Data & Trust page that explains what the system is working from.
const OBSERVATION_STORY_COPY = {
  inventory: {
    kicker: 'Depth Picture',
    title: 'A few bullpens have less room to breathe',
    body: 'Around the league, some clubs are managing from a thinner late-inning bench. The usable options are there, but the margin is tighter.',
    href: '/dashboard',
    cta: 'See the league view',
  },
  readiness: {
    kicker: 'Availability Picture',
    title: "Rest is quietly changing tonight's bullpen map",
    body: 'Some managers have more ways through the late innings than others because the rested options are not spread evenly.',
    href: '/dashboard',
    cta: 'See the league view',
  },
  workload_pressure: {
    kicker: 'Usage Trend',
    title: 'The league-wide workload picture is starting to tighten',
    body: 'Several pens have been busy lately, and the work has not been spread evenly. The same pockets of arms are doing a lot of the lifting.',
    href: '/dashboard',
    cta: 'See the league view',
  },
  constraint: {
    kicker: 'Tight Margins',
    title: 'A few late-inning margins are getting thin',
    body: 'More than one club comes in with fewer rested options than it would like. The bullpen map has a few tighter routes today.',
    href: '/dashboard',
    cta: 'See the league view',
  },
  freshness: {
    kicker: 'Data Note',
    title: 'Today’s picture is waiting on completed games',
    body: 'Part of what BaseballOS sees comes from earlier in the week. The story sharpens as new completed games arrive.',
    href: '/trust',
    cta: 'Open the full picture',
  },
  trust: {
    kicker: 'Data Note',
    title: 'BaseballOS is staying quiet where the data is thin',
    body: 'When the inputs are not solid enough to stand behind, the page says less rather than guessing. A few reads are limited today.',
    href: '/trust',
    cta: 'Open the full picture',
  },
  availability_movement: {
    kicker: 'Movement',
    title: 'Who is rested changed overnight',
    body: 'Arms are rotating on and off rest around the league. Today’s picture is not yesterday’s.',
    href: '/dashboard',
    cta: 'See the league view',
  },
  snapshot_change: {
    kicker: 'What Changed',
    title: 'Last night rearranged a few bullpens',
    body: 'The newest completed games changed who is rested and who is not. Today’s bullpen picture reflects it.',
    href: '/dashboard',
    cta: 'See the league view',
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
      abbr: hidden.abbr,
      teamName: hidden.teamName,
      available: hidden.available,
      monitor: hidden.monitor,
      restricted: hidden.restricted,
      total: hidden.total,
      storyKind: 'team_workload_continuity',
      read: getReadsForLandscapeEntry(hidden).byKey.concentration,
      kicker: 'Hidden Workload',
      tone: 'watch',
      title: SIGNAL_HEADLINES.sameArms.hidden(hidden.teamName),
      body: `Nobody in this pen is flashing red, but ${hidden.monitor} of ${hidden.total} arms are carrying heavy recent work. That is how a calm-looking bullpen can still have a story underneath.`,
      href: hidden.href,
      cta: 'Step inside this pen',
      ...storyContinuityProps(hidden, 'team_workload_continuity'),
    })
  }

  const heaviest = monitoring.find(entry => entry.monitor > 0)
  if (heaviest) {
    candidates.push({
      teamId: heaviest.teamId,
      abbr: heaviest.abbr,
      teamName: heaviest.teamName,
      available: heaviest.available,
      monitor: heaviest.monitor,
      restricted: heaviest.restricted,
      total: heaviest.total,
      storyKind: 'team_workload',
      read: getReadsForLandscapeEntry(heaviest).byKey.concentration,
      kicker: 'Carrying The Load',
      tone: 'watch',
      title: SIGNAL_HEADLINES.sameArms.feed(heaviest.teamName),
      body: `${heaviest.monitor} of ${heaviest.total} arms sit on the watch list. No club is asking more of one group today.`,
      href: heaviest.href,
      cta: 'Step inside this pen',
    })
  }

  const tightening = constrained.find(entry => entry.restricted > 0 && !usedTeamIds.has(entry.teamId))
  if (tightening) {
    candidates.push({
      teamId: tightening.teamId,
      abbr: tightening.abbr,
      teamName: tightening.teamName,
      available: tightening.available,
      monitor: tightening.monitor,
      restricted: tightening.restricted,
      total: tightening.total,
      storyKind: 'team_pressure',
      read: getReadsForLandscapeEntry(tightening).byKey.pressure,
      kicker: 'Pressure Point',
      tone: 'stress',
      title: SIGNAL_HEADLINES.stretchedPen.feed(tightening.teamName),
      body: `${tightening.restricted} of ${tightening.total} relievers ${tightening.restricted === 1 ? 'needs' : 'need'} rest after recent work. This pen has less room to breathe late than it would like.`,
      href: tightening.href,
      cta: 'Step inside this pen',
    })
  }

  const widestWindow = available.find(entry => entry.available > 0)
  if (widestWindow) {
    candidates.push({
      teamId: widestWindow.teamId,
      abbr: widestWindow.abbr,
      teamName: widestWindow.teamName,
      available: widestWindow.available,
      monitor: widestWindow.monitor,
      restricted: widestWindow.restricted,
      total: widestWindow.total,
      storyKind: 'team_recovery',
      read: getReadsForLandscapeEntry(widestWindow).byKey.recovery,
      kicker: 'More Options',
      tone: 'rest',
      title: SIGNAL_HEADLINES.freshPen.feed(widestWindow.teamName),
      body: `${widestWindow.available} of ${widestWindow.total} relievers come in rested. That gives this pen more ways through the late innings.`,
      href: widestWindow.href,
      cta: 'Step inside this pen',
      ...storyContinuityProps(widestWindow, 'team_recovery'),
    })
  }

  const steady = available.find(entry => entry.available > 0 && entry.teamId !== widestWindow?.teamId)
  if (steady) {
    candidates.push({
      teamId: steady.teamId,
      abbr: steady.abbr,
      teamName: steady.teamName,
      available: steady.available,
      monitor: steady.monitor,
      restricted: steady.restricted,
      total: steady.total,
      storyKind: 'team_depth',
      read: getReadsForLandscapeEntry(steady).byKey.cleanOptions,
      kicker: 'Arms To Spare',
      tone: 'rest',
      title: SIGNAL_HEADLINES.freshPen.depth(steady.teamName),
      body: `${steady.available} of ${steady.total} arms come in rested enough to use, and nobody is carrying too much of the recent load. Depth is part of this pen’s story today.`,
      href: steady.href,
      cta: 'Step inside this pen',
    })
  }

  candidates.push(...storyContextShiftCandidates(dashboard, 'home-stories'))

  const metrics = leagueMetrics(dashboard)
  if (metrics.monitor > 0 || metrics.restricted > 0) {
    candidates.push({
      teamId: null,
      storyKind: 'league_workload',
      kicker: 'League Note',
      tone: metrics.restricted > metrics.monitor ? 'stress' : 'watch',
      title: 'The heavy lifting is not isolated to one bullpen',
      body: `${metrics.monitor} tracked ${metrics.monitor === 1 ? 'arm sits' : 'arms sit'} on the watch list and ${metrics.restricted} ${metrics.restricted === 1 ? 'needs' : 'need'} rest. Some of the strain is obvious, and some of it is hiding below a calm surface.`,
      href: '/dashboard',
      cta: 'See the league view',
    })
  }

  if (metrics.available > 0) {
    candidates.push({
      teamId: null,
      storyKind: 'league_recovery',
      kicker: 'The Other Side',
      tone: 'rest',
      title: 'The league is not running on empty',
      body: `${metrics.available} tracked ${metrics.available === 1 ? 'reliever is' : 'relievers are'} rested enough to be usable today. That does not erase the pressure points, but most bullpens still have room to maneuver.`,
      href: '/dashboard',
      cta: 'See the league view',
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
      family,
      sourceObservation: observation,
      storyKind: family === 'freshness' || family === 'trust'
        ? 'data_observation'
        : 'league_observation',
      kicker: copy.kicker,
      tone: OBSERVATION_TONES[observation.severity] || 'neutral',
      title: copy.title,
      body: copy.body,
      href: copy.href,
      cta: copy.cta,
    })
    if (seenFamilies.size >= 2) break
  }

  const selection = selectStoryCandidates(
    candidates.map(candidate => withStoryContinuity(candidate, candidate.team || candidate, dashboard)),
    storyEngineContext(dashboard),
    { limit: 8, excludedTeamIds: [...usedTeamIds], seedStories: [hero] },
  )

  return {
    hasStories: selection.items.length > 0,
    items: selection.items,
    fallback: STORIES_FALLBACK,
    suppressedCount: selection.suppressedCount,
    suppressionReasons: selection.suppressionReasons,
  }
}

// ── Rankings Preview ───────────────────────────────────────────────────────
// A placeholder for where bullpen rankings may land later. This section does
// not order teams or link ranking rows; Today remains descriptive intelligence.
export function getRankingsPreview(dashboard) {
  return {
    framing: 'Preview only. Not yet validated. Coming later. Today remains descriptive intelligence, not a team ranking.',
    updateNote: 'No rankings are active on this page.',
    boards: [
      {
        key: 'shape',
        title: 'Bullpen Shape Preview',
        note: 'How each pen comes in, not a ranking',
        placeholder: true,
        placeholderCopy: 'Coming later after the preview is validated.',
        entries: [],
      },
      {
        key: 'recovery',
        title: 'Recovery Window Preview',
        note: 'Who has room to maneuver, not a ranking',
        placeholder: true,
        placeholderCopy: 'Not yet validated for team ordering.',
        entries: [],
      },
      {
        key: 'pressure',
        title: 'Bullpen Pressure Preview',
        note: 'Who is carrying the load, not a ranking',
        placeholder: true,
        placeholderCopy: 'Preview only until the full release is ready.',
        entries: [],
      },
      {
        key: 'movement',
        title: 'Movement Preview',
        note: 'Day-over-day story movement',
        placeholder: true,
        placeholderCopy: 'Coming later with validated movement tracking.',
        entries: [],
      },
    ],
  }
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
