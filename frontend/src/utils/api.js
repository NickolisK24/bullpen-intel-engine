const BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : '/api'

// Optional admin token for operational write endpoints (sync / recalculate).
// Left unset for local dev (the backend allows those routes when its own
// ADMIN_API_TOKEN is unset). Only set this for a build where you intend the
// operator UI to drive a token-protected backend.
const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_API_TOKEN

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (ADMIN_TOKEN) headers['X-Admin-Token'] = ADMIN_TOKEN
  try {
    const res = await fetch(`${BASE}${path}`, { ...options, headers })
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
    return await res.json()
  } catch (err) {
    console.error(`[API] ${path}`, err)
    throw err
  }
}

// ── Health ─────────────────────────────────────────────────
export const checkHealth = () => request('/health')

// ── Bullpen / Fatigue ───────────────────────────────────────
export const getFatigueScores  = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/fatigue${q ? `?${q}` : ''}`)
}
export const getPitcherFatigue = (id) => request(`/bullpen/fatigue/${id}`)
export const recalculateFatigue = () => request('/bullpen/fatigue/recalculate', { method: 'POST' })

export const getPitchers       = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/pitchers${q ? `?${q}` : ''}`)
}
export const getPitcherLogs    = (id, days = 30) => request(`/bullpen/pitchers/${id}/logs?days=${days}`)

export const getTeams          = () => request('/bullpen/teams')
export const getTeamBullpen    = (teamId, params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/bullpen/teams/${teamId}/bullpen${q ? `?${q}` : ''}`)
}
export const getBullpenOverview = () => request('/bullpen/stats/overview')
export const getSyncStatus     = () => request('/bullpen/sync/status')
export const getFatigueEraInsight = () => request('/bullpen/insights/fatigue-era')
// No public helper for /bullpen/fatigue/snapshot: latest-workload snapshot mode
// is admin/dev validation only and must not power current-availability UI.

// ── Prospects ───────────────────────────────────────────────
export const getProspects        = (params = {}) => {
  const q = new URLSearchParams(params).toString()
  return request(`/prospects/${q ? `?${q}` : ''}`)
}
export const getProspect         = (id) => request(`/prospects/${id}`)
export const getProspectsByTeam  = () => request('/prospects/by-team')
export const getProspectPipeline = () => request('/prospects/pipeline')
export const compareProspects    = (id1, id2) => request(`/prospects/compare?id1=${id1}&id2=${id2}`)
export const getPipelineOverview = () => request('/prospects/stats/overview')

// ── Methodology ───────────────────────────────────────────────
export const getMethodology = () => request('/methodology/')
