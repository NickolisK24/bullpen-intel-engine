// The BaseballOS vocabulary layer — four named reads that describe bullpen
// state in plain baseball language: Bullpen Pressure, Recovery Window,
// Workload Concentration, and Clean Options.
//
// These are descriptive product concepts, not metrics. Every label derives
// from the same availability counts the rest of the frontend already shows
// (rested / watch / needing-rest / total), with fixed, inspectable tiers —
// no scoring, no model, nothing the page can't explain in a sentence.

export const CONCEPT_DEFINITIONS = {
  pressure: {
    name: 'Bullpen Pressure',
    definition: 'How much strain the bullpen appears to be carrying today based on recent workload and availability.',
  },
  recovery: {
    name: 'Recovery Window',
    definition: 'How much clean rest the bullpen appears to have available today. This describes workload rest, not health.',
  },
  concentration: {
    name: 'Workload Concentration',
    definition: 'Whether recent bullpen work appears spread across the group or clustered among fewer arms.',
  },
  cleanOptions: {
    name: 'Clean Options',
    definition: 'How many arms appear to enter today without significant recent workload restriction.',
  },
}

export const LIMITED_READ_LABEL = 'Limited Read'

const arms = (n) => `${n} arm${n === 1 ? '' : 's'}`

function normalizeCounts(counts = {}) {
  const num = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : 0)
  const total = num(counts.total)
  return {
    total,
    ready: num(counts.ready),
    watch: num(counts.watch),
    needRest: num(counts.needRest),
    limitedRead: Boolean(counts.limitedRead) || total === 0,
  }
}

function limitedRead(key) {
  return {
    key,
    concept: CONCEPT_DEFINITIONS[key].name,
    definition: CONCEPT_DEFINITIONS[key].definition,
    label: LIMITED_READ_LABEL,
    display: LIMITED_READ_LABEL,
    tone: 'neutral',
    detail: 'Not enough current data for this read.',
  }
}

function pressureRead({ total, watch, needRest }) {
  const base = {
    key: 'pressure',
    concept: CONCEPT_DEFINITIONS.pressure.name,
    definition: CONCEPT_DEFINITIONS.pressure.definition,
  }
  if (needRest >= 3 || needRest / total >= 0.4) {
    return {
      ...base,
      label: 'High',
      display: 'High Bullpen Pressure',
      tone: 'stress',
      detail: `${arms(needRest)} of ${total} need rest — recent workload is squeezing today's options.`,
    }
  }
  if (needRest === 2 || (needRest >= 1 && watch >= 2)) {
    return {
      ...base,
      label: 'Elevated',
      display: 'Elevated Bullpen Pressure',
      tone: 'watch',
      detail: 'Enough recent workload here to tighten the late innings.',
    }
  }
  if (needRest === 1 || watch >= 2) {
    return {
      ...base,
      label: 'Manageable',
      display: 'Manageable Bullpen Pressure',
      tone: 'rest',
      detail: 'Some recent work to manage, nothing squeezing the pen yet.',
    }
  }
  return {
    ...base,
    label: 'Low',
    display: 'Low Bullpen Pressure',
    tone: 'rest',
    detail: 'Little recent strain on this group.',
  }
}

function recoveryRead({ total, ready }) {
  const base = {
    key: 'recovery',
    concept: CONCEPT_DEFINITIONS.recovery.name,
    definition: CONCEPT_DEFINITIONS.recovery.definition,
  }
  const share = ready / total
  if (ready >= 6 || share >= 0.65) {
    return {
      ...base,
      label: 'Wide',
      display: 'Wide Recovery Window',
      tone: 'rest',
      detail: `${arms(ready)} of ${total} come in rested — plenty of clean rest to work with.`,
    }
  }
  if (share >= 0.45) {
    return {
      ...base,
      label: 'Stable',
      display: 'Stable Recovery Window',
      tone: 'rest',
      detail: 'A workable amount of clean rest in the group.',
    }
  }
  if (share >= 0.25) {
    return {
      ...base,
      label: 'Narrow',
      display: 'Narrow Recovery Window',
      tone: 'watch',
      detail: 'Clean rest is in shorter supply than usual here.',
    }
  }
  return {
    ...base,
    label: 'Limited',
    display: 'Limited Recovery Window',
    tone: 'stress',
    detail: 'Very little clean rest available in this group today.',
  }
}

function concentrationRead({ watch, needRest }) {
  const base = {
    key: 'concentration',
    concept: CONCEPT_DEFINITIONS.concentration.name,
    definition: CONCEPT_DEFINITIONS.concentration.definition,
  }
  if (watch >= 3 || (watch >= 2 && needRest >= 2)) {
    return {
      ...base,
      label: 'Concentrated',
      display: 'Concentrated Workload',
      tone: 'watch',
      detail: `Recent work is clustering in a few arms — ${arms(watch)} on the watch list.`,
    }
  }
  if (watch === 2 || (watch >= 1 && needRest >= 1)) {
    return {
      ...base,
      label: 'Some Concentration',
      display: 'Some Concentration',
      tone: 'neutral',
      detail: 'A few arms are carrying more than their share of recent work.',
    }
  }
  return {
    ...base,
    label: 'Spread-Out',
    display: 'Spread-Out Workload',
    tone: 'rest',
    detail: 'Recent work looks spread across the group.',
  }
}

function cleanOptionsRead({ total, ready }) {
  const base = {
    key: 'cleanOptions',
    concept: CONCEPT_DEFINITIONS.cleanOptions.name,
    definition: CONCEPT_DEFINITIONS.cleanOptions.definition,
  }
  if (ready >= 6 || ready / total >= 0.7) {
    return {
      ...base,
      label: 'Deep',
      display: 'Deep Clean Options',
      tone: 'rest',
      detail: `${arms(ready)} enter today without significant recent restriction.`,
    }
  }
  if (ready >= 4 || ready / total >= 0.5) {
    return {
      ...base,
      label: 'Enough',
      display: 'Enough Clean Options',
      tone: 'rest',
      detail: 'A workable group of unrestricted arms for today.',
    }
  }
  if (ready >= 2) {
    return {
      ...base,
      label: 'Thin',
      display: 'Thin Clean Options',
      tone: 'watch',
      detail: 'Fewer unrestricted arms than a club would like today.',
    }
  }
  return {
    ...base,
    label: 'Very Thin',
    display: 'Very Thin Clean Options',
    tone: 'stress',
    detail: 'Almost no unrestricted arms in this pen today.',
  }
}

// All four reads from one set of counts:
// { total, ready, watch, needRest, limitedRead? }.
export function getBullpenReads(counts) {
  const normalized = normalizeCounts(counts)
  const keys = ['pressure', 'recovery', 'concentration', 'cleanOptions']

  if (normalized.limitedRead) {
    const reads = keys.map(key => limitedRead(key))
    return { reads, byKey: Object.fromEntries(reads.map(read => [read.key, read])) }
  }

  const reads = [
    pressureRead(normalized),
    recoveryRead(normalized),
    concentrationRead(normalized),
    cleanOptionsRead(normalized),
  ]
  return { reads, byKey: Object.fromEntries(reads.map(read => [read.key, read])) }
}

// Adapter for the landscape entry shape the homepage view-model uses
// ({ available, monitor, restricted, total }). The landscape's restricted
// bucket folds roster-unavailable arms in with workload restriction, which is
// fine for a descriptive read.
export function getReadsForLandscapeEntry(entry) {
  if (!entry) return getBullpenReads({ total: 0 })
  return getBullpenReads({
    total: entry.total,
    ready: entry.available,
    watch: entry.monitor,
    needRest: entry.restricted,
  })
}
