const EMPTY_WORKLOAD_FACTS = {
  days_since_last_appearance: null,
  appearances_last_7: null,
  pitches_last_7_days: null,
  back_to_back: null,
}

const countOrNull = value => Number.isInteger(value) && value >= 0 ? value : null
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

function parseIsoDate(value) {
  const match = ISO_DATE.exec(String(value || ''))
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  return date.toISOString().slice(0, 10) === value ? date : null
}

function addUtcDays(date, amount) {
  const next = new Date(date)
  next.setUTCDate(next.getUTCDate() + amount)
  return next
}

export function getGovernedWorkloadFacts(card) {
  const facts = card?.workload_facts
  if (!facts || typeof facts !== 'object' || Array.isArray(facts)) {
    return { ...EMPTY_WORKLOAD_FACTS }
  }
  return {
    days_since_last_appearance: countOrNull(facts.days_since_last_appearance),
    appearances_last_7: countOrNull(facts.appearances_last_7),
    pitches_last_7_days: countOrNull(facts.pitches_last_7_days),
    back_to_back: typeof facts.back_to_back === 'boolean' ? facts.back_to_back : null,
  }
}

export function getRestStatusView(restStatus) {
  if (!restStatus || typeof restStatus !== 'object' || restStatus.available !== true) {
    return { available: false }
  }
  const countKeys = [
    'active_arm_count',
    'rested_arm_count',
    'worked_yesterday_count',
    'back_to_back_count',
  ]
  const validCounts = countKeys.every(key => Number.isInteger(restStatus[key]) && restStatus[key] >= 0)
  const summary = typeof restStatus.summary === 'string' ? restStatus.summary.trim() : ''
  const countsFitActive = validCounts && countKeys.slice(1).every(key => restStatus[key] <= restStatus.active_arm_count)
  if (!validCounts || !countsFitActive || !summary) return { available: false }
  return {
    available: true,
    active_arm_count: restStatus.active_arm_count,
    rested_arm_count: restStatus.rested_arm_count,
    worked_yesterday_count: restStatus.worked_yesterday_count,
    back_to_back_count: restStatus.back_to_back_count,
    summary,
  }
}

export function getWorkloadWindowRows(workloadOverview) {
  const windows = Array.isArray(workloadOverview?.windows) ? workloadOverview.windows : []
  return windows.flatMap((window, index) => {
    const windowDays = countOrNull(window?.window_days)
    if (windowDays == null || windowDays === 0) return []
    return [{
      key: `window-${windowDays}-${index}`,
      label: `${windowDays} days`,
      through: parseIsoDate(window?.through) ? window.through : null,
      appearances: countOrNull(window?.relief_appearances),
      pitches: countOrNull(window?.pitches_total),
    }]
  })
}

export function getWorkloadColumns(rows) {
  const candidates = [
    { key: 'appearances', label: 'Appearances' },
    { key: 'pitches', label: 'Pitches' },
  ]
  return candidates.filter(column => rows.some(row => row[column.key] != null))
}

export function getWorkloadTrendView(reliefWork, days = 30) {
  const throughDate = parseIsoDate(reliefWork?.data_through)
  const groups = Array.isArray(reliefWork?.relief_by_date) ? reliefWork.relief_by_date : []
  if (!throughDate || days !== 30) return { available: false }

  const publishedByDate = new Map()
  for (const group of groups) {
    const date = parseIsoDate(group?.game_date)
    const outs = countOrNull(group?.outs_total)
    if (!date || outs == null || group?.available === false || publishedByDate.has(group.game_date)) continue
    publishedByDate.set(group.game_date, outs)
  }
  if (publishedByDate.size === 0) return { available: false }

  const firstDate = addUtcDays(throughDate, -(days - 1))
  const slots = Array.from({ length: days }, (_, index) => {
    const date = addUtcDays(firstDate, index).toISOString().slice(0, 10)
    const published = publishedByDate.has(date)
    return { date, published, outs: published ? publishedByDate.get(date) : null }
  })
  if (!slots.some(slot => slot.published)) return { available: false }

  return {
    available: true,
    dataThrough: reliefWork.data_through,
    slots,
    publishedDayCount: slots.filter(slot => slot.published).length,
  }
}
