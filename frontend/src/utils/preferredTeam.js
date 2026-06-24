export const PREFERRED_TEAM_STORAGE_KEY = 'baseballos.preferredTeam'
export const LEGACY_FOLLOWED_TEAM_STORAGE_KEY = 'baseballos.followedTeam'
export const LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY = 'baseballos.whatChangedTeam'
export const PREFERRED_TEAM_CHANGED_EVENT = 'baseballos:preferred-team-changed'

function getBrowserStorage() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage || null
  } catch {
    return null
  }
}

function cleanText(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function cleanTeamId(value) {
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isInteger(id) ? id : null
}

function nowIso(now = () => new Date().toISOString()) {
  try {
    const value = now()
    return value ? String(value) : new Date().toISOString()
  } catch {
    return new Date().toISOString()
  }
}

function parseSelectionValue(value) {
  const text = cleanText(value)
  if (!text) return null
  const [kind, ...rest] = text.split(':')
  const raw = rest.join(':')
  if (!raw) return null
  if (kind === 'team') return { team_id: cleanTeamId(raw), team_abbreviation: null, team_name: null }
  if (kind === 'abbr') return { team_id: null, team_abbreviation: cleanText(raw)?.toUpperCase() || null, team_name: null }
  if (kind === 'name') return { team_id: null, team_abbreviation: null, team_name: cleanText(raw) }
  return null
}

export function normalizePreferredTeam(team) {
  if (!team || typeof team !== 'object') return null

  const teamId = cleanTeamId(team.team_id ?? team.teamId)
  const teamAbbreviation = cleanText(team.team_abbreviation ?? team.teamAbbreviation ?? team.teamAbbr)
  const teamName = cleanText(team.team_name ?? team.teamName)

  if (teamId == null && !teamAbbreviation && !teamName) return null

  return {
    team_id: teamId,
    team_abbreviation: teamAbbreviation,
    team_name: teamName,
  }
}

export function preferredTeamSelectionValue(team) {
  const normalized = normalizePreferredTeam(team)
  if (!normalized) return ''
  if (normalized.team_id != null) return `team:${normalized.team_id}`
  if (normalized.team_abbreviation) return `abbr:${normalized.team_abbreviation.toUpperCase()}`
  return normalized.team_name ? `name:${normalized.team_name.toLowerCase()}` : ''
}

function normalizePreferredTeamState(raw) {
  if (!raw || typeof raw !== 'object') {
    return { team: null, promptDismissed: false, savedAt: null, dismissedAt: null }
  }

  const team = normalizePreferredTeam(raw.team || raw)
  return {
    team,
    promptDismissed: raw.prompt_dismissed === true || raw.promptDismissed === true,
    savedAt: cleanText(raw.saved_at ?? raw.savedAt),
    dismissedAt: cleanText(raw.dismissed_at ?? raw.dismissedAt),
  }
}

function readJson(storage, key) {
  if (!storage) return null
  try {
    const raw = storage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function readStoredPreferredTeamState(storage) {
  return normalizePreferredTeamState(readJson(storage, PREFERRED_TEAM_STORAGE_KEY))
}

function readLegacyFollowedTeam(storage) {
  return normalizePreferredTeam(readJson(storage, LEGACY_FOLLOWED_TEAM_STORAGE_KEY))
}

function readLegacyWhatChangedTeam(storage) {
  if (!storage) return null
  try {
    return parseSelectionValue(storage.getItem(LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY))
  } catch {
    return null
  }
}

function writePreferredTeamState(state, storage, now) {
  if (!storage) return false
  const payload = {
    team: normalizePreferredTeam(state.team),
    prompt_dismissed: state.promptDismissed === true,
    saved_at: state.savedAt || (state.team ? nowIso(now) : null),
    dismissed_at: state.dismissedAt || null,
  }
  try {
    storage.setItem(PREFERRED_TEAM_STORAGE_KEY, JSON.stringify(payload))
    return true
  } catch {
    return false
  }
}

function clearLegacyPreferredTeamKeys(storage) {
  if (!storage) return
  for (const key of [LEGACY_FOLLOWED_TEAM_STORAGE_KEY, LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY]) {
    try {
      storage.removeItem(key)
    } catch {
      // Best-effort cleanup only.
    }
  }
}

function emitPreferredTeamChange(state) {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return
  try {
    window.dispatchEvent(new CustomEvent(PREFERRED_TEAM_CHANGED_EVENT, { detail: state }))
  } catch {
    // CustomEvent is not available in some test environments.
  }
}

export function readPreferredTeamState(storage = getBrowserStorage(), now = () => new Date().toISOString()) {
  const current = readStoredPreferredTeamState(storage)
  if (current.team || current.promptDismissed) return current

  const legacyTeam = readLegacyFollowedTeam(storage) || readLegacyWhatChangedTeam(storage)
  if (!legacyTeam) return current

  const migrated = {
    team: legacyTeam,
    promptDismissed: false,
    savedAt: nowIso(now),
    dismissedAt: null,
  }
  writePreferredTeamState(migrated, storage, () => migrated.savedAt)
  clearLegacyPreferredTeamKeys(storage)
  return migrated
}

export function readPreferredTeamPreference(storage = getBrowserStorage()) {
  return readPreferredTeamState(storage).team
}

export function savePreferredTeamPreference(
  team,
  storage = getBrowserStorage(),
  now = () => new Date().toISOString(),
) {
  const normalized = normalizePreferredTeam(team)
  if (!normalized) return null

  const state = {
    team: normalized,
    promptDismissed: false,
    savedAt: nowIso(now),
    dismissedAt: null,
  }
  writePreferredTeamState(state, storage, () => state.savedAt)
  clearLegacyPreferredTeamKeys(storage)
  emitPreferredTeamChange(state)
  return normalized
}

export function savePreferredTeamSelectionValue(
  value,
  storage = getBrowserStorage(),
  now = () => new Date().toISOString(),
) {
  return savePreferredTeamPreference(parseSelectionValue(value), storage, now) != null
}

export function dismissPreferredTeamPrompt(
  storage = getBrowserStorage(),
  now = () => new Date().toISOString(),
) {
  const current = readPreferredTeamState(storage, now)
  const state = {
    ...current,
    promptDismissed: true,
    dismissedAt: nowIso(now),
  }
  writePreferredTeamState(state, storage, () => state.dismissedAt)
  emitPreferredTeamChange(state)
  return true
}

export function clearPreferredTeamPreference(storage = getBrowserStorage()) {
  if (!storage) return false
  try {
    storage.removeItem(PREFERRED_TEAM_STORAGE_KEY)
    clearLegacyPreferredTeamKeys(storage)
    emitPreferredTeamChange({
      team: null,
      promptDismissed: false,
      savedAt: null,
      dismissedAt: null,
    })
    return true
  } catch {
    return false
  }
}

export function isPreferredTeamStorageEvent(event) {
  if (!event || !('key' in event)) return true
  return event.key == null || [
    PREFERRED_TEAM_STORAGE_KEY,
    LEGACY_FOLLOWED_TEAM_STORAGE_KEY,
    LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY,
  ].includes(event.key)
}

export function resolvePreferredTeam(preference, teams = []) {
  const normalized = normalizePreferredTeam(preference)
  if (!normalized) return null
  if (!Array.isArray(teams) || teams.length === 0) return normalized

  const byId = normalized.team_id == null
    ? null
    : teams.find(team => cleanTeamId(team?.team_id ?? team?.teamId) === normalized.team_id)
  if (byId) return normalizePreferredTeam(byId)

  const abbr = normalized.team_abbreviation?.toLowerCase()
  const byAbbr = abbr
    ? teams.find(team => cleanText(team?.team_abbreviation ?? team?.teamAbbr)?.toLowerCase() === abbr)
    : null
  if (byAbbr) return normalizePreferredTeam(byAbbr)

  const name = normalized.team_name?.toLowerCase()
  const byName = name
    ? teams.find(team => cleanText(team?.team_name ?? team?.teamName)?.toLowerCase() === name)
    : null
  return byName ? normalizePreferredTeam(byName) : normalized
}

export function buildPreferredTeamHref(team, source = 'preferred-team') {
  const normalized = normalizePreferredTeam(team)
  if (!normalized) return '/bullpen?view=board'

  const teamParam = normalized.team_abbreviation || (
    normalized.team_id != null ? String(normalized.team_id) : ''
  )
  if (!teamParam) return '/bullpen?view=board'

  const query = new URLSearchParams({
    view: 'board',
    team: teamParam,
    source,
  })
  return `/bullpen?${query.toString()}`
}

export function preferredTeamLabel(team, fallback = 'your team') {
  const normalized = normalizePreferredTeam(team)
  return normalized?.team_name
    || normalized?.team_abbreviation
    || fallback
}

export function preferredTeamShortLabel(team, fallback = 'Team') {
  const normalized = normalizePreferredTeam(team)
  return normalized?.team_abbreviation
    || normalized?.team_name
    || fallback
}

export function preferredTeamLogoUrl(team) {
  const normalized = normalizePreferredTeam(team)
  if (normalized?.team_id == null) return null
  return `https://www.mlbstatic.com/team-logos/${normalized.team_id}.svg`
}
