// ── Number formatting ────────────────────────────────────────
export const fmtAvg = (n) => n != null ? Number(n).toFixed(3).replace(/^0/, '') : '---'
export const fmtPct = (n) => n != null ? Number(n).toFixed(3).replace(/^0/, '') : '---'
export const fmtEra = (n) => n != null ? Number(n).toFixed(2) : '---'
export const fmtIP  = (n) => n != null ? Number(n).toFixed(1) : '0.0'
export const fmtNum = (n) => n != null ? n : '---'

// ── Fatigue ──────────────────────────────────────────────────
export const riskColor = (level) => ({
  LOW:      'text-emerald-400',
  MODERATE: 'text-yellow-400',
  HIGH:     'text-orange-400',
  CRITICAL: 'text-red-400',
}[level] || 'text-chalk400')

export const riskBg = (level) => ({
  LOW:      'bg-emerald-400',
  MODERATE: 'bg-amber-400',
  HIGH:     'bg-orange-400',
  CRITICAL: 'bg-red-500',
}[level] || 'bg-chalk400')

export const riskBadgeClass = (level) => ({
  LOW:      'badge-low',
  MODERATE: 'badge-moderate',
  HIGH:     'badge-high',
  CRITICAL: 'badge-critical',
}[level] || 'badge-low')

export const fatigueBarColor = (score) => {
  if (score >= 81) return 'bg-red-500'
  if (score >= 50) return 'bg-orange-400'
  if (score >= 25) return 'bg-amber-400'
  return 'bg-emerald-400'
}

// ── Grade scale (20-80) ──────────────────────────────────────
export const gradeLabel = (g) => {
  if (!g) return '---'
  if (g >= 70) return 'Elite'
  if (g >= 60) return 'Plus'
  if (g >= 50) return 'Avg'
  if (g >= 40) return 'Fringe'
  return 'Below'
}

export const gradeColor = (g) => {
  if (!g) return 'text-chalk400'
  if (g >= 70) return 'text-amber'
  if (g >= 60) return 'text-emerald-400'
  if (g >= 50) return 'text-chalk200'
  if (g >= 40) return 'text-chalk400'
  return 'text-red-400'
}

// ── Level ordering ───────────────────────────────────────────
export const LEVELS = ['ROK', 'A', 'A+', 'AA', 'AAA', 'MLB']

export const levelColor = (level) => ({
  'ROK': 'text-chalk400',
  'A':   'text-ice',
  'A+':  'text-sky-400',
  'AA':  'text-violet-400',
  'AAA': 'text-amber',
  'MLB': 'text-emerald-400',
}[level] || 'text-chalk400')

// ── Date formatting ──────────────────────────────────────────
// Date-only ISO strings like "2026-05-01" parse as midnight UTC by default,
// which shifts the display by one day in any timezone west of UTC. Detect
// that pattern and parse as local instead.
const parseLocalDate = (s) => {
  if (!s) return null
  if (typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split('-').map(Number)
    return new Date(y, m - 1, d)
  }
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

export const fmtDate = (s) => {
  const d = parseLocalDate(s)
  if (!d) return '---'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export const daysAgo = (s) => {
  const d = parseLocalDate(s)
  if (!d) return null
  const diff = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return '1d ago'
  return `${diff}d ago`
}
