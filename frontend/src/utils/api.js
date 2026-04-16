const BASE = '/api'

async function request(path, options = {}) {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
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
export const getTeamBullpen    = (teamId) => request(`/bullpen/teams/${teamId}/bullpen`)
export const getBullpenOverview = () => request('/bullpen/stats/overview')
export const getSyncStatus     = () => request('/bullpen/sync/status')

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

// ── Portfolio ───────────────────────────────────────────────
export const getPortfolio = () => request('/portfolio/')
