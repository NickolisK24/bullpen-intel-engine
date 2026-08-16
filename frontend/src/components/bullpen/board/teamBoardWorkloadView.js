const EMPTY_WORKLOAD_FACTS = {
  days_since_last_appearance: null,
  appearances_last_7: null,
  pitches_last_7_days: null,
  back_to_back: null,
}

const countOrNull = value => Number.isInteger(value) && value >= 0 ? value : null

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
