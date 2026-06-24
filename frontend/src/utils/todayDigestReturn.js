import {
  normalizePreferredTeam,
  preferredTeamSelectionValue,
} from './preferredTeam'

function cleanText(value) {
  const text = value == null ? '' : String(value).trim()
  return text || null
}

function cleanTeamId(value) {
  if (value == null || value === '') return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

function cleanTeamAbbreviation(value) {
  const text = cleanText(value)
  if (!text || !/^[A-Za-z]{2,4}$/.test(text)) return null
  return text.toUpperCase()
}

function paramsFromSearch(search = '') {
  if (search instanceof URLSearchParams) return search
  const text = String(search || '')
  return new URLSearchParams(text.startsWith('?') ? text.slice(1) : text)
}

export function parseTodayTeamParam(search = '') {
  const params = paramsFromSearch(search)
  const rawTeam = cleanText(params.get('team'))
  const rawSource = cleanText(params.get('source'))
  const isDigestReturn = rawSource?.toLowerCase() === 'digest'

  if (!rawTeam) {
    return {
      hasTeamParam: false,
      valid: false,
      rawTeam: null,
      team_id: null,
      team_abbreviation: null,
      source: rawSource,
      isDigestReturn,
    }
  }

  const teamId = cleanTeamId(rawTeam)
  const teamAbbreviation = teamId == null ? cleanTeamAbbreviation(rawTeam) : null

  return {
    hasTeamParam: true,
    valid: teamId != null || teamAbbreviation != null,
    rawTeam,
    team_id: teamId,
    team_abbreviation: teamAbbreviation,
    source: rawSource,
    isDigestReturn,
  }
}

function teamMatchesParsedParam(team, parsed) {
  if (!team || !parsed?.valid) return false
  const normalized = normalizePreferredTeam(team)
  if (!normalized) return false
  if (parsed.team_id != null && normalized.team_id === parsed.team_id) return true
  return Boolean(
    parsed.team_abbreviation
    && normalized.team_abbreviation
    && normalized.team_abbreviation.toUpperCase() === parsed.team_abbreviation,
  )
}

function findUrlTeam(teams, parsed) {
  return (Array.isArray(teams) ? teams : [])
    .map(team => normalizePreferredTeam(team))
    .find(team => teamMatchesParsedParam(team, parsed)) || null
}

export function sameTodayTeam(left, right) {
  const leftValue = preferredTeamSelectionValue(left)
  const rightValue = preferredTeamSelectionValue(right)
  if (!leftValue || !rightValue) return false
  return leftValue === rightValue
}

export function resolveTodayViewTeam({
  search = '',
  teams = [],
  teamsLoaded = false,
  preferredTeam = null,
} = {}) {
  const parsed = parseTodayTeamParam(search)
  const normalizedPreferredTeam = normalizePreferredTeam(preferredTeam)
  const base = {
    parsed,
    viewTeam: normalizedPreferredTeam,
    urlTeam: null,
    urlTeamValid: false,
    urlTeamInvalid: false,
    urlTeamPending: false,
    isDigestReturn: parsed.isDigestReturn,
  }

  if (!parsed.hasTeamParam) return base
  if (!parsed.valid) {
    return {
      ...base,
      urlTeamInvalid: true,
    }
  }
  if (!teamsLoaded) {
    return {
      ...base,
      viewTeam: null,
      urlTeamPending: true,
    }
  }

  const urlTeam = findUrlTeam(teams, parsed)
  if (!urlTeam) {
    return {
      ...base,
      urlTeamInvalid: true,
    }
  }

  return {
    ...base,
    viewTeam: urlTeam,
    urlTeam,
    urlTeamValid: true,
  }
}

export function relationshipFor({
  urlTeamValid = false,
  authenticated = false,
  authLoading = false,
  viewTeam = null,
  followedTeam = null,
} = {}) {
  const isFollowing = sameTodayTeam(viewTeam, followedTeam)
  if (!viewTeam) {
    return {
      kind: 'none',
      isFollowing: false,
      showSwitchPrompt: false,
      showSignInPrompt: false,
    }
  }
  if (urlTeamValid && isFollowing) {
    return {
      kind: 'digest-followed',
      isFollowing: true,
      showSwitchPrompt: false,
      showSignInPrompt: false,
    }
  }
  if (urlTeamValid && authenticated && !authLoading) {
    return {
      kind: 'digest-switch',
      isFollowing: false,
      showSwitchPrompt: true,
      showSignInPrompt: false,
    }
  }
  if (urlTeamValid && !authenticated && !authLoading) {
    return {
      kind: 'digest-preview',
      isFollowing: false,
      showSwitchPrompt: false,
      showSignInPrompt: true,
    }
  }
  if (isFollowing) {
    return {
      kind: 'following',
      isFollowing: true,
      showSwitchPrompt: false,
      showSignInPrompt: false,
    }
  }
  return {
    kind: 'preview',
    isFollowing: false,
    showSwitchPrompt: false,
    showSignInPrompt: false,
  }
}
