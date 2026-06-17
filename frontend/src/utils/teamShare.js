export const TEAM_SHARE_ORIGIN = 'https://baseballos.vercel.app'

export function normalizeTeamShareAbbreviation(team) {
  const value = typeof team === 'string'
    ? team
    : team?.team_abbreviation
      ?? team?.teamAbbreviation
      ?? team?.abbr
      ?? team?.team?.team_abbreviation
      ?? team?.team?.teamAbbreviation
      ?? team?.team?.abbr
  const text = typeof value === 'string' ? value.trim().toUpperCase() : ''
  return text ? text.replace(/[^A-Z0-9-]/g, '') : ''
}

export function buildTeamSharePath(team) {
  const abbr = normalizeTeamShareAbbreviation(team)
  return abbr ? `/team/${encodeURIComponent(abbr)}` : ''
}

export function buildTeamShareUrl(team, origin = TEAM_SHARE_ORIGIN) {
  const path = buildTeamSharePath(team)
  if (!path) return ''
  return `${String(origin || TEAM_SHARE_ORIGIN).replace(/\/+$/, '')}${path}`
}

export function getShareTeamName(team, fallback = 'this team') {
  if (typeof team === 'string') return team.trim().toUpperCase() || fallback
  return team?.team_name
    || team?.teamName
    || team?.name
    || team?.team?.team_name
    || team?.team?.teamName
    || team?.team?.name
    || normalizeTeamShareAbbreviation(team)
    || fallback
}

function isShareCancel(error) {
  return ['AbortError', 'NotAllowedError'].includes(error?.name)
}

async function copyWithFallback(url, env) {
  const nav = env?.navigator
  if (nav?.clipboard?.writeText) {
    await nav.clipboard.writeText(url)
    return true
  }

  const documentRef = env?.document
  if (!documentRef?.createElement || !documentRef?.body?.appendChild) return false

  const input = documentRef.createElement('textarea')
  input.value = url
  input.setAttribute('readonly', '')
  input.style.position = 'fixed'
  input.style.top = '-9999px'
  documentRef.body.appendChild(input)
  input.select()
  let copied = false
  try {
    copied = Boolean(documentRef.execCommand?.('copy'))
  } finally {
    documentRef.body.removeChild(input)
  }
  return copied
}

export async function shareTeamUrl(team, env = globalThis) {
  const url = buildTeamShareUrl(team)
  if (!url) return { status: 'unavailable', url }

  const nav = env?.navigator
  if (nav?.share) {
    try {
      await nav.share({ url })
      return { status: 'shared', url }
    } catch (error) {
      if (isShareCancel(error)) return { status: 'cancelled', url }
    }
  }

  try {
    const copied = await copyWithFallback(url, env)
    return { status: copied ? 'copied' : 'unavailable', url }
  } catch {
    return { status: 'unavailable', url }
  }
}
