const BULLPEN_PATH = '/bullpen'

export const BULLPEN_VIEWS = Object.freeze({
  BOARD: 'board',
  COMPARE: 'compare',
  PITCHERS: 'pitchers',
})

export const BULLPEN_SOURCE_VALUES = Object.freeze([
  'today',
  'dashboard',
  'landscape',
  'stories',
  'comparison',
  'all_pitchers',
  'pitcher_search',
  'share',
  'share_link',
  'share_card',
  'since_yesterday',
])

export const EVIDENCE_SECTIONS = Object.freeze({
  TEAM_RELIEF_WORK: 'team-relief-work',
  PITCHER_LANES: 'pitcher-lanes',
  COMPARISON_EVIDENCE: 'comparison-evidence',
})

const VALID_VIEWS = new Set(Object.values(BULLPEN_VIEWS))
const VALID_SOURCES = new Set(BULLPEN_SOURCE_VALUES)
const BOARD_SECTIONS = new Set([
  EVIDENCE_SECTIONS.TEAM_RELIEF_WORK,
  EVIDENCE_SECTIONS.PITCHER_LANES,
])

function cleanText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function positiveInteger(value) {
  const text = String(value ?? '').trim()
  if (!/^\d+$/.test(text)) return null
  const parsed = Number(text)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

function teamValue(teamRef) {
  if (typeof teamRef === 'string' || typeof teamRef === 'number') return teamRef
  return teamRef?.team_abbreviation
    ?? teamRef?.teamAbbreviation
    ?? teamRef?.teamAbbr
    ?? teamRef?.abbr
    ?? teamRef?.team?.team_abbreviation
    ?? teamRef?.team?.teamAbbreviation
    ?? teamRef?.team?.teamAbbr
    ?? teamRef?.team?.abbr
    ?? teamRef?.team_id
    ?? teamRef?.teamId
    ?? teamRef?.team?.team_id
    ?? teamRef?.team?.teamId
}

export function normalizeTeamReference(teamRef) {
  const value = teamValue(teamRef)
  const numeric = positiveInteger(value)
  if (numeric != null) return String(numeric)
  const abbreviation = cleanText(value).toUpperCase()
  return /^[A-Z]{2,4}$/.test(abbreviation) ? abbreviation : null
}

export function resolveTeamReference(teamList, requested) {
  if (!Array.isArray(teamList) || requested == null) return null
  const raw = cleanText(String(requested))
  if (!raw) return null

  const requestedId = positiveInteger(raw)
  if (requestedId != null) {
    const byId = teamList.find(team => Number(team?.team_id ?? team?.teamId) === requestedId)
    if (byId) return byId
  }

  const lower = raw.toLowerCase()
  return teamList.find(team => (
    cleanText(team?.team_abbreviation ?? team?.teamAbbreviation).toLowerCase() === lower
    || cleanText(team?.team_name ?? team?.teamName).toLowerCase() === lower
  )) || null
}

export function resolveTeamId(teamList, requested) {
  const team = resolveTeamReference(teamList, requested)
  const teamId = Number(team?.team_id ?? team?.teamId)
  return Number.isSafeInteger(teamId) && teamId > 0 ? teamId : null
}

export function normalizePitcherId(pitcherId) {
  return positiveInteger(pitcherId)
}

export function normalizeBullpenSource(source) {
  const value = cleanText(source).toLowerCase()
  return VALID_SOURCES.has(value) ? value : null
}

export function normalizeEvidenceSection(section, view) {
  const value = cleanText(section).replace(/^#/, '')
  if (view === BULLPEN_VIEWS.BOARD && BOARD_SECTIONS.has(value)) return value
  if (view === BULLPEN_VIEWS.COMPARE && value === EVIDENCE_SECTIONS.COMPARISON_EVIDENCE) return value
  return null
}

function hrefFromParams(params, section) {
  const query = params.toString()
  return `${BULLPEN_PATH}${query ? `?${query}` : ''}${section ? `#${section}` : ''}`
}

export function buildTeamBoardHref(teamRef, options = {}) {
  const params = new URLSearchParams({ view: BULLPEN_VIEWS.BOARD })
  const team = normalizeTeamReference(teamRef)
  const pitcher = normalizePitcherId(options.pitcher ?? options.pitcherId)
  const source = normalizeBullpenSource(options.source)
  const section = normalizeEvidenceSection(options.section, BULLPEN_VIEWS.BOARD)
  if (team) params.set('team', team)
  if (pitcher != null) params.set('pitcher', String(pitcher))
  if (source) params.set('source', source)
  return hrefFromParams(params, section)
}

export function buildComparisonHref(teamARef, teamBRef, options = {}) {
  const params = new URLSearchParams({ view: BULLPEN_VIEWS.COMPARE })
  const teamA = normalizeTeamReference(teamARef)
  const teamB = normalizeTeamReference(teamBRef)
  const source = normalizeBullpenSource(options.source)
  const section = normalizeEvidenceSection(options.section, BULLPEN_VIEWS.COMPARE)
  if (teamA) params.set('team_a', teamA)
  if (teamB) params.set('team_b', teamB)
  if (source) params.set('source', source)
  return hrefFromParams(params, section)
}

export function buildPitcherHref(pitcherId, options = {}) {
  return buildTeamBoardHref(options.teamRef, {
    pitcher: pitcherId,
    source: options.source,
    section: options.section,
  })
}

export function buildAllPitchersHref(options = {}) {
  const params = new URLSearchParams({ view: BULLPEN_VIEWS.PITCHERS })
  const team = normalizeTeamReference(options.teamRef)
  const source = normalizeBullpenSource(options.source)
  if (team) params.set('team', team)
  if (source) params.set('source', source)
  return hrefFromParams(params)
}

export function readBullpenLocation(search = '', hash = '') {
  const params = new URLSearchParams(search)
  const requestedView = cleanText(params.get('view')).toLowerCase()
  const view = VALID_VIEWS.has(requestedView) ? requestedView : BULLPEN_VIEWS.BOARD
  const rawSection = cleanText(hash).replace(/^#/, '')
  return {
    view,
    requestedView,
    team: cleanText(params.get('team')) || null,
    teamA: cleanText(params.get('team_a')) || null,
    teamB: cleanText(params.get('team_b')) || null,
    pitcherId: normalizePitcherId(params.get('pitcher')),
    source: normalizeBullpenSource(params.get('source')),
    section: normalizeEvidenceSection(rawSection, view),
    unsupportedHash: rawSection && !normalizeEvidenceSection(rawSection, view) ? rawSection : null,
  }
}

export function buildCanonicalBullpenHref(state = {}) {
  const options = { source: state.source, section: state.section }
  if (state.view === BULLPEN_VIEWS.COMPARE) {
    return buildComparisonHref(state.teamA, state.teamB, options)
  }
  if (state.view === BULLPEN_VIEWS.PITCHERS) {
    return buildAllPitchersHref({ teamRef: state.team, source: state.source })
  }
  return buildTeamBoardHref(state.team, { ...options, pitcher: state.pitcherId })
}
